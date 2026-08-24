#!/usr/bin/env python3
"""Run one campaign end to end, through every packet the frame defines.

Until this existed, `frame-work-item-v1`, `frame-result-v1`, and
`frame-review-v1` were schemas with no writer: specifications that had never
been produced or consumed by anything. A schema nothing writes is a description
of an intention, and the gap between the adapter (which emits a receipt) and the
reducer (which consumes an admission) was filled by hand every time it was
crossed.

This closes that gap. One command drives:

    resolve pack -> freeze -> init state -> work item -> adapter -> receipt
    -> result -> [review] -> admission -> reducer -> state -> report

and every packet is validated against its schema and sealed on the way through,
so the run fails at the first place the chain does not actually hold together.

## What it deliberately cannot do

It cannot produce an independent review, so a fully automatic run **cannot reach
VERIFIED**. That is not a limitation to work around, it is the architecture
working: independent review means a reviewer who is not the producer, and a
single process driving both ends is exactly the failure the requirement exists
to catch. An automatic run tops out at CHECKED_BOUNDED, and the report says why.

Supply `--review <file>` when a genuine independent review exists, and the same
run reaches whatever the evidence supports.

## Working memory

Every run opens a `soc.json` beside its workdir and writes to it as it goes: what
it is pursuing, what it ruled out and why, what it decided and what that turned
out to be worth. It is ATTENTION and it is allowed to be wrong — which is why the
reducer is handed it too, and refuses any admission whose evidence hashes to
something in it. A memory that could stand behind a status would not be working
memory, it would be a second evidence store with no gates on it.

Before a work item is issued the run asks it whether this attempt has already
failed. That check costs nothing and is the difference between a campaign that
compounds and one whose twentieth attempt knows what the first one knew.

## Memory and blinding

Two frame components existed unwired for as long as the frame did, and both are
about what a later run is allowed to know.

`memory.py` records what happened so the next campaign against the same target
does not rediscover it. A campaign that forgets is a campaign whose twentieth
attempt knows what the first one knew — and the failure ledger already tracks
signatures within a run, but nothing carried them across runs.

`blind_packet.py` strips a result down to what a reviewer needs before the
reviewer sees it. Independent review means the reviewer did not produce the
work; it is worth much less when the reviewer can read the producer's reasoning,
because agreement then costs nothing. The blinded packet is written beside the
result so a review can be requested against it rather than against the full one.

## Failure is a first-class outcome

A failing adapter is not an error here. The failure is recorded in the ledger,
the escalation threshold is evaluated mechanically, and the report says whether
the next move is another attempt or the deep-attack role. That path is exercised
by `--self-test` alongside the success path, because a harness that only works
when things go well has not been tested against the case it exists for.

Usage:
    campaign.py run --claim <claim.json> --artifact <path> --tier <name>
                    [--domain <pack> | --statement "<problem>"]
                    [--workdir <dir>] [--review <review.json>] [--write]
                    [--governor <gov.json>] [--cost N]
                    [--producer-actor <id>] [--admitter-actor <id>]
    campaign.py self-test

Exit: 0 admitted, 1 refused or not admitted, 2 usage/IO error, 3 escalated,
      4 stopped on budget, 5 incomplete — a required check could not run.

## Three things this loop asks before it works

**Is the claim ready?** The planner reads the dependency graph and says so. A
claim whose dependencies are undischarged produces evidence that cannot close
anything, and working it anyway is the most expensive form of doing nothing.

**Can it be afforded?** With `--governor`, the tier's cost is charged against a
declared ceiling and a run that exceeds it STOPS. Without one, nothing stops
this on cost, and the report says which of the two happened rather than leaving
the reader to assume a limit existed.

**Who is acting?** With `--producer-actor` and `--admitter-actor` the chain is
attested and the reducer can grant a status that depends on independence.
Without them it is self-attested, independence reads NOT_RUN, and the ceiling is
CHECKED_BOUNDED — which is where this loop already topped out for a different
reason, and the two agreeing is a good sign about both.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from reducer import canonical, seal, state_hash, rank as rank_status  # noqa: E402
from jsonschema_lite import validate  # noqa: E402
import governor  # noqa: E402
import schedule  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(packet: dict) -> dict:
    body = {k: v for k, v in packet.items() if k != "payload_sha256"}
    body["payload_sha256"] = seal(body)
    return body


def load_schema(name: str) -> dict:
    return json.loads((SKILL_ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


def check_packet(packet: dict, schema_name: str, label: str) -> list[str]:
    errors: list[str] = []
    validate(packet, load_schema(schema_name), label, errors)
    return errors


def as_json(text: str) -> dict:
    """Parse a tool's stdout, or return nothing. A tool that prints plain text is
    not an error here — it is a tool with a different contract — so this returns
    an empty dict rather than raising, and the caller decides what absence means."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


# The frame holds no field's cost model, and `cost_hint` is a contract field with
# exactly these three values. Mapping them to numbers is the smallest thing that
# makes a budget mean something without the frame learning what a tier costs in
# any particular field — a pack that wants real numbers passes --cost.
COST_BY_HINT = {"cheap": 1, "moderate": 10, "expensive": 100}


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


class Campaign:
    def __init__(self, workdir: Path, quiet: bool = False):
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.quiet = quiet
        self.steps: list[dict] = []
        # Set when a governor is in play, so the outcome can be attached to the
        # charge once the admission decision exists.
        self._gov_state: dict | None = None
        self._gov_path: Path | None = None
        self._gov_worker: str = ""

    def say(self, text: str) -> None:
        if not self.quiet:
            print(text)

    def step(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append({"step": name, "ok": ok, "detail": detail})
        self.say(f"  [{'ok  ' if ok else 'STOP'}] {name}" + (f"  {detail}" if detail else ""))

    def write(self, name: str, packet: dict) -> Path:
        path = self.dir / f"{name}.json"
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        return path

    # ---------------------------------------------------------------- the run

    def escalation_packet(self, claim: dict, target: str, state: dict, pack: str,
                          plan: dict, cause: dict) -> Path:
        """The work item the ladder hands to the deep-attack role.

        Escalation was mechanical, defended at length, and handed off to NOBODY:
        the ladder fired, the campaign returned ESCALATED, and the Researcher was
        a document with no invocation path. A trigger whose consequence is a
        printed word is theatre — the frame does not dispatch, and it must at
        least produce the packet the orchestrator dispatches.

        It carries what the next role actually needs and would otherwise
        reconstruct by reading this run's logs: the exact obstruction, the
        failure signature that fired, and where the field's obstruction
        catalogue lives.
        """
        obstruction = cause.get("obstruction") or "production failed repeatedly on this claim"
        item = sealed({
            "schema": "frame-work-item-v1",
            "work_item_id": f"WI-ESC-{target[:8]}",
            "target_sha256": target,
            "claim_id": claim.get("claim_id", ""),
            "assigned_role": "researcher",
            "expected_artifact": (
                "an obstruction record: what was attempted exactly, the specific way it failed, "
                "whether the failure is about this instance or the approach, and the minimal "
                "missing evidence that would settle it"),
            "falsifier": (
                "a counterexample, a refutation of the blocking sub-claim, or a demonstration "
                "that the obstruction does not apply"),
            "forbidden_drift": ["the frozen statement", "the frozen conditions",
                                "the claim this obstruction blocks"],
            "stop_rule": (
                "three genuinely distinct method families attempted, or the obstruction shown to "
                "require evidence that does not exist yet — an honest STOPPED with the missing "
                "evidence named is a legitimate result"),
            "base_revision": state["revision"],
            "base_state_sha256": state_hash(state),
            "obstruction": obstruction,
            "escalated_by": cause.get("escalated_by", "failure ladder"),
            "failure_signature": cause.get("signature"),
            "consecutive_failures": cause.get("streak"),
            "pack": pack,
            "read_first": [plan["role_doctrine"]["researcher"]] + [
                r for r in plan.get("shared_doctrine", [])
                if any(k in r for k in ("obstruction", "barrier", "reduction", "unconventional"))],
        })
        path = self.dir / "escalation_work_item.json"
        path.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
        return path

    def execute(self, claim_path: Path, artifact: Path, tier: str,
                domain: str | None, statement: str | None,
                review_path: Path | None, write: bool,
                receipt_path: Path | None = None,
                governor_path: Path | None = None, cost: int | None = None,
                producer_actor: dict | None = None,
                admitter_actor: dict | None = None,
                state_in: Path | None = None,
                also: list[tuple[str, str, str]] | None = None) -> dict:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        target = claim.get("target_sha256")
        also = also or []

        # 1. resolve the pack ------------------------------------------------
        cmd = [sys.executable, str(HERE / "resolve_domain.py"), "--json"]
        cmd += ["--domain", domain] if domain else ["--statement", statement or ""]
        code, out, err = run(cmd)
        try:
            resolution = json.loads(out)
        except json.JSONDecodeError:
            self.step("resolve pack", False, (out + err)[:200])
            return self.report("UNRESOLVED")
        if resolution.get("decision") != "SELECTED":
            self.step("resolve pack", False,
                      f"{resolution['decision']} — nothing can be admitted without an adapter")
            return self.report(resolution["decision"])
        pack = resolution["domain"]
        plan = resolution["load"][pack]
        ceiling = plan["max_admissible_status"]
        self.step("resolve pack", True, f"{pack}, ceiling {ceiling}")

        # 2. freeze ----------------------------------------------------------
        #
        # An EXISTING state may be supplied, and until it could be the loop and
        # the claim graph were separate universes: this always initialised a
        # fresh single-claim state, so a campaign could never advance a
        # decomposition somebody had already made. Explorer's whole output is a
        # graph, and the only thing that can run work is this — they had no way
        # to meet.
        if state_in is not None:
            state_path = self.dir / "state.json"
            state_path.write_text(state_in.read_text(encoding="utf-8"), encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            known = state.get("claims") or {}
            if claim.get("claim_id") not in known:
                self.step("freeze target", False,
                          f"{claim.get('claim_id')!r} is not a claim in the supplied state. A "
                          "campaign advances a graph that already has it; adding one is a "
                          "structural admission, not a side effect of running work")
                return self.report("STOPPED")
            self.step("freeze target", True,
                      f"joined an existing graph at revision {state['revision']}, "
                      f"{len(known)} claim(s), ceiling {ceiling}")
        else:
            state_path = self.dir / "state.json"
            code, out, err = run([sys.executable, str(HERE / "reducer.py"), "init",
                                  "--claim", str(claim_path), "--out", str(state_path),
                                  "--ceiling", ceiling])
            if code != 0:
                self.step("freeze target", False, (out + err)[:200])
                return self.report("STOPPED")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.step("freeze target", True, f"revision 0, ceiling {ceiling}")

        # 2b. working memory ---------------------------------------------------
        soc_path = self.dir / "soc.json"
        if not soc_path.exists():
            run([sys.executable, str(HERE / "soc_memory.py"), "init", "--out", str(soc_path),
                 "--target", target, "--goal", claim.get("exact_statement", "")[:200]])
        code, out, _ = run([sys.executable, str(HERE / "soc_memory.py"), "check",
                            "--soc", str(soc_path), "--json",
                            "--statement", claim.get("exact_statement", "")[:300],
                            "--method", f"{pack}:{tier}"])
        risk = as_json(out)
        if risk.get("repeat_risk") == "HIGH":
            # A recorded repeat IS the escalation condition — "the same failure
            # twice changed nothing the checker could see" — reached before any
            # budget is spent rather than after the threshold counts to it. So
            # the outcome is the same and the cost is not: the obstruction goes
            # to the deep-attack role, and production stops on this claim.
            self.step("repeat check", False,
                      "this attempt matches a recorded failure — " +
                      "; ".join(m.get("do_not_repeat", "") for m in risk.get("matches", [])[:2]))
            self.step("escalation", True,
                      "ESCALATE — reached by the repeat gate before the threshold, which is the "
                      "same conclusion for less")
            packet = self.escalation_packet(
                claim, target, state, pack, plan,
                {"escalated_by": "repeat gate",
                 "obstruction": "; ".join(m.get("do_not_repeat", "")
                                          for m in risk.get("matches", [])[:2]),
                 "signature": (risk.get("matches") or [{}])[0].get("signature")})
            self.step("hand off", True,
                      f"{packet.name} — a work item for the deep-attack role, with the "
                      "obstruction, the signature that fired, and the doctrine to read first. "
                      "The frame does not dispatch it; it does have to write it")
            return self.report("ESCALATED", target_sha256=target, repeat=risk,
                               escalated_by="repeat gate", work_item=str(packet))
        self.step("repeat check", True,
                  "no recorded failure matches; that is not evidence it will work")

        # 3. work item -------------------------------------------------------
        work_item = sealed({
            "schema": "frame-work-item-v1",
            "work_item_id": f"WI-{target[:8]}",
            "target_sha256": target,
            "claim_id": claim["claim_id"],
            "assigned_role": "generator",
            "expected_artifact": plan["tiers"][0].get("name", "an artifact the adapter can check"),
            "verification_tier": tier,
            "falsifier": {
                "criterion": f"the {pack} adapter returns fail on the frozen target at tier {tier}",
                "test": f"run the declared adapter entry point at tier {tier} against the "
                        "artifact and the frozen claim",
                "scope": f"this artifact at tier {tier}; a failure here does not refute the claim",
            },
            "forbidden_drift": "the frozen statement, the frozen conditions, and the target hash. "
                               "A changed context is a new claim with a new hash, never an edit "
                               "to this one",
            "stop_rule": f"escalate after {plan['escalate_after']} consecutive failures "
                         "with the same signature",
            "base_revision": state["revision"],
            "base_state_sha256": state_hash(state),
        })
        errors = check_packet(work_item, "frame-work-item-v1", "work_item")
        self.step("issue work item", not errors, "; ".join(errors)[:200] or work_item["work_item_id"])
        if errors:
            return self.report("STOPPED")
        self.write("work_item", work_item)

        # 4. adapter ---------------------------------------------------------
        # A supplied receipt is re-admitted rather than re-earned. This is not a
        # shortcut around verification: the reducer still re-hashes the live
        # artifact against what the receipt verified, so a stale one is refused
        # exactly as before. What it avoids is paying for an expensive tier again
        # to re-admit evidence that already exists — and it is what makes the
        # campaign's own determinism checkable, since a receipt carries the one
        # thing that legitimately differs between runs.
        # 3b. is this claim even ready, and can it be afforded ---------------
        #
        # Both questions were answerable and neither was asked. The planner and
        # the governor existed as libraries nothing in the runtime path called,
        # which is the same failure as a component named in an architecture and
        # absent from the tree, one layer in: present, tested, and doing nothing.
        state = json.loads(state_path.read_text(encoding="utf-8"))
        wave = schedule.plan(state, None)
        claim_id = claim.get("claim_id")
        # `blocked` is the authoritative signal, not "absent from the wave". The
        # first version guarded on a non-empty wave to avoid tripping when there
        # was nothing to run, which turned the gate off in exactly the case it
        # exists for: everything blocked means an EMPTY wave. The reducer refused
        # the admission downstream anyway — defence in depth working — but by
        # then the tier had already been paid for, and saving that is the whole
        # reason to ask before instead of after.
        if claim_id and claim_id in wave["blocked"]:
            self.step("readiness", False,
                      f"{claim_id} is not ready: {wave['blocked'][claim_id]}. Working a claim "
                      "whose dependencies are undischarged produces evidence that cannot close "
                      "anything, which is the most expensive way to do nothing")
            return self.report("BLOCKED")
        self.step("readiness", True,
                  f"{claim_id or 'the claim'} is ready"
                  + (f"; {len(wave['races'])} race group(s) in the graph" if wave["races"] else "")
                  + (f"; {len(wave['blocked'])} other claim(s) blocked" if wave["blocked"] else ""))

        gov_state = None
        charge = cost
        if governor_path is not None:
            gov_state = governor.load(governor_path)
            hint = next((entry.get("cost_hint") for entry in plan.get("tiers", [])
                         if entry.get("name") == tier), "moderate")
            if charge is None:
                charge = COST_BY_HINT.get(hint, 10)
            decision = governor.ask(gov_state, hint, charge)
            if decision["verdict"] != governor.ALLOW:
                self.step("budget", False, f"{decision['verdict']}: {decision['reading']}")
                return self.report("STOPPED_ON_BUDGET")
            self._gov_state, self._gov_path = gov_state, governor_path
            self._gov_worker = f"campaign-{claim_id or 'claim'}"
            governor.start(gov_state, hint, f"campaign-{claim_id or 'claim'}", charge,
                           claim_id)
            governor.save(governor_path, gov_state)
            self.step("budget", True,
                      f"{decision['reading']}. A run stopped on budget is a legitimate result; "
                      "one that continued past a ceiling nobody raised is not")

        if receipt_path is not None:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.step("reuse receipt", True,
                      f"{receipt.get('receipt_id')} — the reducer will still re-hash the "
                      "artifact against it")
            out, err = json.dumps(receipt), ""
        else:
            adapter = SKILL_ROOT / plan["adapter"]
            code, out, err = run([sys.executable, str(adapter), "--artifact", str(artifact),
                                  "--claim", str(claim_path), "--tier", tier, "--json"])
        try:
            receipt = json.loads(out)
        except json.JSONDecodeError:
            self.step("run adapter", False, (out + err)[:200])
            return self.report("STOPPED")
        # §2.2 — a claim may engage more than one pack, and until now nothing
        # could run one. Resolution could report AMBIGUOUS and the architecture
        # could state the rules; the loop took a single --domain and there was
        # no way to obtain a second pack's verdict at all, so "a fatal objection
        # from any engaged pack blocks admission" was a rule about a situation
        # the system could not reach.
        paired_receipts = []
        for extra_pack, extra_tier, extra_artifact in also:
            # Resolve the second pack the same way the first was. Reaching into
            # the first resolution's `load` would only ever find the pack that
            # resolution was asked about.
            code2, out2, _e = run([sys.executable, str(HERE / "resolve_domain.py"),
                                   "--domain", extra_pack, "--json"])
            try:
                extra_plan = json.loads(out2)["load"][extra_pack]
            except (json.JSONDecodeError, KeyError):
                self.step(f"pair {extra_pack}", False,
                          f"{extra_pack!r} did not resolve; a pack that cannot be loaded cannot "
                          "object, and silently proceeding would make its silence look like "
                          "assent")
                return self.report("STOPPED")
            code2, out2, err2 = run([sys.executable, str(SKILL_ROOT / extra_plan["adapter"]),
                                     "--artifact", str(extra_artifact), "--claim",
                                     str(claim_path), "--tier", extra_tier, "--json"])
            try:
                extra_receipt = json.loads(out2)
            except json.JSONDecodeError:
                self.step(f"pair {extra_pack}", False, (out2 + err2)[:200])
                return self.report("STOPPED")
            paired_receipts.append((extra_pack, extra_receipt))
            self.step(f"pair {extra_pack}", True,
                      f"verdict {extra_receipt['verdict']}, tier ceiling "
                      f"{extra_receipt['max_status']}")

        if paired_receipts:
            # Verdicts are NOT averaged. A pass in one field never compensates
            # for a failure in another, and the ceiling is the weakest of them
            # because establishing something in one field establishes nothing in
            # the other.
            objectors = [name for name, r in paired_receipts if r["verdict"] == "fail"]
            if receipt["verdict"] == "fail":
                objectors.insert(0, pack)
            if objectors:
                self.step("paired verdict", False,
                          f"fatal objection from {', '.join(objectors)}. Verdicts are not "
                          "averaged: a pass in one field never compensates for a failure in "
                          "another, so this is blocked whatever the others said")
                return self.report("BLOCKED_BY_PAIR", objectors=objectors)
            ceilings = [receipt["max_status"]] + [r["max_status"] for _n, r in paired_receipts]
            weakest = min(ceilings, key=rank_status)
            if weakest != receipt["max_status"]:
                receipt = {**receipt, "max_status": weakest}
            self.step("paired verdict", True,
                      f"{1 + len(paired_receipts)} pack(s) engaged, none objecting; ceiling is "
                      f"the weakest of {ceilings} = {weakest}. Support in one field does not "
                      "establish anything in another")

        errors = check_packet(receipt, "frame-receipt-v1", "receipt")
        if errors:
            self.step("run adapter", False,
                      "the receipt does not satisfy frame-receipt-v1: " + "; ".join(errors)[:200])
            return self.report("STOPPED")
        self.write("receipt", receipt)
        verdict = receipt["verdict"]
        if receipt_path is not None:
            self.steps.append({"step": "run adapter", "ok": True,
                               "detail": "skipped; a receipt was supplied"})
        # The step succeeded whatever the verdict was. A failing adapter is a
        # result, not an error, and marking it as an error is how a system learns
        # to treat negative evidence as a malfunction.
        self.step("run adapter", True,
                  f"verdict {verdict}, tier ceiling {receipt['max_status']}")

        if gov_state is not None:
            # The outcome is attached once the admission decision exists — see
            # `record_outcome` at the end of the run. Until that call existed the
            # comment was the only thing attaching it.
            closed = governor.done(gov_state, f"campaign-{claim_id or 'claim'}", charge)
            governor.save(governor_path, gov_state)
            self.step("charge", True,
                      f"{closed['reading']}; {closed['remaining']:.0f} of budget remains")

        # 5. result ----------------------------------------------------------
        fidelity_record = None
        if review_path:
            supplied = json.loads(review_path.read_text(encoding="utf-8"))
            if (supplied.get("checks") or {}).get("target_fidelity") == "PASS" \
                    and supplied.get("independent") is True:
                fidelity_record = {
                    "faithful": True,
                    "checked_by_ref": supplied.get("reviewer_ref", "unknown-reviewer"),
                    "basis": (f"review {supplied.get('review_id')} asserts target_fidelity PASS "
                              f"by an independent {supplied.get('reviewer_role')} reviewer using "
                              f"the {supplied.get('method_family')} method family"),
                }

        result = sealed({
            "schema": "frame-result-v1",
            "result_id": f"RES-{sha256_file(artifact)[:8]}",
            "work_item_id": work_item["work_item_id"],
            "target_sha256": target,
            "emitted_by": "generator",
            "trust_boundary": "CANDIDATE_ONLY",
            # Attestation, when the orchestrator supplied one. Absent, the chain
            # is self-attested and the reducer reads independence as NOT_RUN —
            # which is exactly right for a single process claiming to be two
            # roles, and is the same ceiling this loop already declared for
            # itself from the evidence side.
            **({"actor": producer_actor} if producer_actor else {}),
            # A result is a CANDIDATE. VERIFIED is not in the enum here at all,
            # because only an admission grants it — the schema refuses to let a
            # producer even propose the word.
            # A GAP and a FAILURE are different, and collapsing them was the
            # single most consequential thing wrong with this mapping. The
            # adapter has three verdicts: `pass`, `fail`, and `incomplete`. An
            # incomplete receipt means a required check COULD NOT RUN — no
            # independent judge, an absent backend — and the route may be
            # perfectly sound. Recording that as FAILED_ATTEMPT states that the
            # approach was shown not to work, and then feeds it to the ladder,
            # which escalates a deep-attack role at a formalization the kernel
            # already accepted. The remedy for a gap is to get the missing
            # check; the remedy for a failure is a different route.
            "candidate_status": ("CHECKED_BOUNDED" if receipt["max_status"] == "VERIFIED"
                                 else receipt["max_status"]) if verdict == "pass"
                                else "GAP" if verdict == "incomplete"
                                else "FAILED_ATTEMPT",
            "method_family": "direct-production",
            "dependency_path_to_target": [claim["claim_id"]],
            "work_item_sha256": work_item["payload_sha256"],
            "receipt_ref": {"receipt_id": receipt["receipt_id"],
                            "payload_sha256": receipt["payload_sha256"],
                            "target_sha256": target},
            # Fidelity is only recorded when someone else established it. The
            # schema requires `checked_by_ref` to differ from the emitter, and
            # this harness is the emitter — so a record it wrote about its own
            # artifact would be self-certified, which the frame refuses.
            #
            # A supplied review is the exception, and not a loophole:
            # `target_fidelity` is one of the four checks frame-review-v1
            # REQUIRES, so a review asserting it PASS is an independent fidelity
            # judgement that already exists. Transcribing it, with the reviewer
            # named as the checker, is reporting someone else's finding rather
            # than making one.
            **({"fidelity_record": fidelity_record} if fidelity_record else {}),
            "base_revision": state["revision"],
            "base_state_sha256": state_hash(state),
        })
        errors = check_packet(result, "frame-result-v1", "result")
        self.step("emit result", not errors,
                  "; ".join(errors)[:200] or f"candidate {result['candidate_status']}, "
                                             "CANDIDATE_ONLY")
        if errors:
            return self.report("STOPPED")
        self.write("result", result)

        # 6. failure path ----------------------------------------------------
        if verdict != "pass":
            # Two records of the same failure, and they are not redundant. The
            # ledger holds a normalized SIGNATURE, which is what escalation
            # counts; working memory holds the reason and the revival condition,
            # which is what stops the next attempt repeating it. A count cannot
            # tell you what to change, and a reason cannot fire a threshold.
            run([sys.executable, str(HERE / "soc_memory.py"), "failure",
                 "--soc", str(soc_path), "--method", f"{pack}:{tier}",
                 "--statement", claim.get("exact_statement", "")[:300],
                 "--blocker", str(receipt.get("failure_class") or verdict)[:200],
                 "--do-not-repeat", f"the {tier} tier on this artifact unchanged",
                 "--revival", "a changed artifact, a new premise, or a refuted obstruction"])

            # An incomplete run does not enter the failure ledger. The ladder
            # counts attempts that were shown not to work, and a streak of "the
            # judge was unavailable" escalates for a reason the deep-attack role
            # cannot act on.
            if verdict == "incomplete":
                missing = [g["gate"] for g in receipt.get("gates", [])
                           if g.get("verdict") == "not_run"]
                self.step("incomplete", True,
                          f"required check(s) could not run: {', '.join(missing) or 'unnamed'}. "
                          "That is a GAP, not a failed attempt — nothing here was shown not to "
                          "work, so the ladder is not advanced and the missing check is the "
                          "next move")
                return self.report("INCOMPLETE", pack=pack, ceiling=ceiling, receipt=receipt,
                                   missing_checks=missing)

            # A streak that resets every attempt is not a streak. The ledger
            # lived in the workdir, and a workdir is per-attempt — so three
            # identical failures in a row each read "1 of 2" and the escalation
            # ladder, which exists to hand a repeated obstruction to the
            # Researcher, never fired in normal use. Persist it where the
            # campaign's identity lives: beside the claim graph when there is
            # one, else the shared store, else the workdir.
            ledger = self.failure_ledger_path(state_in, target)
            code, out, err = run([
                sys.executable, str(HERE / "failure_ledger.py"), "record",
                "--ledger", str(ledger), "--target", target, "--claim", claim["claim_id"],
                "--pack", pack, "--failure-class", str(receipt.get("failure_class") or verdict),
                "--detail", json.dumps(receipt.get("problems") or receipt.get("log_excerpt") or "")])
            assessment = json.loads(out) if out.strip().startswith("{") else {}
            escalate = bool(assessment.get("escalate"))
            self.step("record failure", True,
                      f"streak {assessment.get('consecutive_failures')} / "
                      f"{assessment.get('threshold')}, signature {assessment.get('recorded')}")
            self.step("escalation check", True,
                      "ESCALATE to the deep-attack role" if escalate
                      else "continue: another attempt is still worth its cost")
            if escalate:
                packet = self.escalation_packet(
                    claim, target, state, pack, plan,
                    {"escalated_by": "failure ladder",
                     "obstruction": (receipt.get("failure_class") or verdict),
                     "signature": assessment.get("recorded"),
                     "streak": assessment.get("consecutive_failures")})
                self.step("hand off", True,
                          f"{packet.name} — the obstruction, the signature, and the doctrine "
                          "to read first, so the next role does not reconstruct this run's logs")
                return self.report("ESCALATED", pack=pack, ceiling=ceiling, receipt=receipt,
                                   escalate=True, work_item=str(packet))
            return self.report("FAILED_ATTEMPT", pack=pack, ceiling=ceiling, receipt=receipt,
                               escalate=False)

        # 6b. blind the result for review -------------------------------------
        blinded = self.dir / "result.blinded.json"
        code, out, _ = run([sys.executable, str(HERE / "blind_packet.py"),
                            "--result", str(self.dir / "result.json"),
                            "--out", str(blinded), "--json"])
        if blinded.exists():
            self.step("blind for review", True,
                      "result.blinded.json — request the review against this; a reviewer who can "
                      "read the producer's reasoning agrees for free")

        # 7. review ----------------------------------------------------------
        reviews = []
        if review_path:
            review = json.loads(review_path.read_text(encoding="utf-8"))
            errors = check_packet(review, "frame-review-v1", "review")
            self.step("independent review", not errors, "; ".join(errors)[:200] or
                      f"{review.get('reviewer_role')} reviewer, verdict {review.get('verdict')}")
            if errors:
                return self.report("STOPPED")
            reviews.append(self.write("review", review))
        else:
            self.step("independent review", True,
                      "NOT_RUN — one process cannot be both producer and independent reviewer, "
                      "so VERIFIED is out of reach for this run by construction")

        # 8. admission -------------------------------------------------------
        # What to propose. Without an independent review and an independently
        # checked fidelity record, the reducer will derive both as NOT_RUN, and
        # VERIFIED and CONDITIONAL both require them. Proposing a status the
        # evidence cannot support would produce a refusal rather than a result,
        # so the honest proposal is the strongest status the chain can actually
        # reach.
        granted = receipt["max_status"]
        if not reviews and granted in {"VERIFIED", "CONDITIONAL"}:
            granted = "CHECKED_BOUNDED"
        delta = {"update_claims": [{"claim_id": claim["claim_id"], "from_status": "OPEN",
                                    "to_status": granted,
                                    "evidence_sha256": [receipt["payload_sha256"]]}]}
        admission = sealed({
            "schema": "frame-admission-v1",
            "admission_id": f"ADM-{target[:8]}",
            "target_sha256": target,
            "base_revision": state["revision"],
            "base_state_sha256": state_hash(state),
            "decided_by_role": "explorer",
            **({"actor": admitter_actor} if admitter_actor else {}),
            "result_ref": {"result_id": result["result_id"],
                           "payload_sha256": result["payload_sha256"]},
            "receipt_ref": {"receipt_id": receipt["receipt_id"],
                            "payload_sha256": receipt["payload_sha256"],
                            "target_sha256": target},
            "decision": "ACCEPT",
            "granted_status": granted,
            "checks": {},
            "review_refs": [{"review_id": json.loads(r.read_text())["review_id"],
                             "payload_sha256": json.loads(r.read_text())["payload_sha256"]}
                            for r in reviews],
            "delta": delta,
            "delta_sha256": hashlib.sha256(canonical(delta).encode()).hexdigest(),
            "rationale": f"the {pack} adapter returned a passing receipt at tier {tier}; every "
                         "acceptance condition is left for the reducer to derive",
        })
        errors = check_packet(admission, "frame-admission-v1", "admission")
        self.step("build admission", not errors,
                  "; ".join(errors)[:200] or f"proposing {granted}")
        if errors:
            return self.report("STOPPED")
        admission_path = self.write("admission", admission)

        # 9. reduce ----------------------------------------------------------
        cmd = [sys.executable, str(HERE / "reducer.py"), "apply",
               "--state", str(state_path), "--admission", str(admission_path),
               "--result", str(self.dir / "result.json"),
               "--receipt", str(self.dir / "receipt.json"),
               "--artifact", str(artifact), "--soc", str(soc_path), "--json"]
        if reviews:
            cmd += ["--review"] + [str(r) for r in reviews]
        if write:
            cmd.append("--write")
        code, out, err = run(cmd)
        try:
            outcome = json.loads(out)
        except json.JSONDecodeError:
            self.step("apply admission", False, (out + err)[:300])
            return self.report("STOPPED")
        applied = bool(outcome.get("applied"))
        self.step("apply admission", applied,
                  f"revision {outcome.get('revision')}" if applied
                  else f"REFUSED — {'; '.join(outcome.get('refusals', []))[:300]}")

        if applied:
            run([sys.executable, str(HERE / "soc_memory.py"), "insight", "--soc", str(soc_path),
                 "--text", f"{granted} admitted for {claim.get('claim_id')} at tier {tier}",
                 "--tier", granted, "--evidence", receipt["payload_sha256"][:16],
                 "--polarity", "supports"])
            run([sys.executable, str(HERE / "soc_memory.py"), "render", "--soc", str(soc_path),
                 "--out", str(self.dir / "run.soc")])

        # 10. remember --------------------------------------------------------
        memory = self.dir.parent / "campaign_memory.json"
        if not memory.exists():
            run([sys.executable, str(HERE / "memory.py"), "init", "--out", str(memory)])
        if applied:
            # The reuse cache is keyed on FULL CONTEXT MATCH, so the context is
            # what makes a later hit legitimate rather than a coincidence of
            # wording. This call omitted it entirely: `--context` is required,
            # the call failed, `run()` discarded the exit code, and the step
            # below reported success — so every campaign has been printing "a
            # later campaign starts from what this one learned" over an empty
            # file. A step that reports success while doing nothing is the exact
            # failure this system exists to make impossible, and it survived
            # because cross-run memory has no test.
            # A JSON object, not a label: the cache is keyed on FULL CONTEXT
            # MATCH, and a string that happens to collide is exactly the kind of
            # false hit that lets an answer launder itself back in as a prior.
            context = json.dumps({"pack": pack, "tier": tier,
                                  "claim_id": claim.get("claim_id", ""),
                                  "target_sha256": target,
                                  "toolchain": receipt.get("toolchain", "")})
            code, out, err = run([
                sys.executable, str(HERE / "memory.py"), "record-result",
                "--mem", str(memory), "--statement", claim.get("exact_statement", "")[:300],
                "--admission-id", admission["admission_id"], "--context", context])
            self.step("remember", code == 0,
                      (f"recorded in {memory.name} under context {context!r}; a later campaign "
                       "in the same context starts from what this one learned")
                      if code == 0 else
                      f"NOT recorded: {(out + err).strip()[:160]}. The run stands; what it "
                      "learned does not carry.")

        return self.report("ADMITTED" if applied else "REFUSED",
                           pack=pack, ceiling=ceiling, granted=granted if applied else None,
                           receipt=receipt, refusals=outcome.get("refusals", []),
                           revision=outcome.get("revision"))

    def failure_ledger_path(self, state_path: Path | None, target: str) -> Path:
        key = (target or "unkeyed")[:16]
        if state_path is not None:
            return state_path.parent / f"failures-{key}.json"
        store = os.environ.get("WITSOC2_SOC_STORE")
        if store:
            Path(store).mkdir(parents=True, exist_ok=True)
            return Path(store) / f"failures-{key}.json"
        return self.dir / "failures.json"

    def report(self, outcome: str, **extra) -> dict:
        # Tie the spend to what it bought. The charge was closed before the
        # admission decision existed, so this is the only point at which the
        # ledger can be told whether anything was granted.
        if self._gov_state is not None and self._gov_path is not None:
            governor.record_outcome(self._gov_state, self._gov_worker, outcome)
            governor.save(self._gov_path, self._gov_state)
        return {"outcome": outcome, "steps": self.steps, "workdir": str(self.dir), **extra}


def check_idempotent(tmp: Path, claim_path: Path, artifact: Path, domain: str) -> list[str]:
    """Two runs over the same inputs must produce byte-identical packets.

    A packet that differs between runs carries something that is not evidence —
    a timestamp, a path, an ordering — and every hash downstream of it becomes
    unreproducible. The reducer binds admissions to results by seal, so a result
    that reseals differently is a result no earlier review can be bound to.
    """
    problems: list[str] = []
    seals = []
    receipt_path = None
    for index in (1, 2):
        run_dir = tmp / f"idem-{index}"
        Campaign(run_dir, quiet=True).execute(claim_path, artifact, "exact", domain,
                                              None, None, True, receipt_path)
        # Hold the receipt fixed after the first run. A receipt records WHEN it
        # was produced and that is real evidence about freshness, so two receipts
        # legitimately differ. The question worth asking is whether the campaign
        # builds the same packets from the same evidence — not whether a
        # timestamp can be made timeless.
        if receipt_path is None:
            receipt_path = run_dir / "receipt.json"
        seals.append({name: json.loads((run_dir / f"{name}.json").read_text())["payload_sha256"]
                      for name in ("work_item", "result", "admission")
                      if (run_dir / f"{name}.json").exists()})
    for name in seals[0]:
        if seals[0][name] != seals[1].get(name):
            problems.append(
                f"{name} seals differently across two identical runs "
                f"({seals[0][name][:12]}... vs {str(seals[1].get(name))[:12]}...). Something in "
                "it is not evidence, and every hash downstream of it is unreproducible")
    return problems


def self_test() -> int:
    """Both paths, against the fixture pack: a run that is admitted and a run
    that fails and escalates. A harness tested only on the success path has not
    been tested against the case it exists for."""
    mock = SKILL_ROOT / "domains" / "_mock"
    failures = []

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        claim = {"claim_id": "SELFTEST-1",
                 "exact_statement": "the artifact equals the expected value",
                 "expected_value": "hello frame"}
        claim["target_sha256"] = hashlib.sha256(
            canonical(claim).encode()).hexdigest()
        claim_path = tmp / "claim.json"
        claim_path.write_text(json.dumps(claim, indent=2))

        good = tmp / "good.txt"
        good.write_text("hello frame")
        bad = tmp / "bad.txt"
        bad.write_text("something else entirely")

        print("A passing artifact — the loop must close:\n")
        run_dir = tmp / "run-pass"
        report = Campaign(run_dir).execute(claim_path, good, "exact", "_mock", None, None, True)
        ok = report["outcome"] == "ADMITTED"
        print(f"\n  -> {report['outcome']}"
              + (f", granted {report.get('granted')} at revision {report.get('revision')}"
                 if ok else ""))
        if not ok:
            failures.append(f"the passing run ended {report['outcome']}: "
                            f"{report.get('refusals')}")
        elif report.get("granted") == "VERIFIED":
            failures.append(
                "an unreviewed automatic run reached VERIFIED. One process cannot be both "
                "producer and independent reviewer, and the ceiling that stops it is the point")

        print("\nThe same inputs twice — the packets must seal identically:\n")
        idem = check_idempotent(tmp, claim_path, good, "_mock")
        print(f"  {'ok  ' if not idem else 'MISS'}  work item, result, and admission are "
              "byte-identical across runs")
        print("          a packet that differs run to run carries something that is not evidence")
        failures.extend(idem)

        print("\nA failing artifact — the ladder must engage:\n")
        run_dir = tmp / "run-fail"
        campaign = Campaign(run_dir)
        first = campaign.execute(claim_path, bad, "exact", "_mock", None, None, True)
        # A second identical failure must trip the repeat trigger. The ledger
        # persists in the same workdir, which is what makes the streak visible.
        second = Campaign(run_dir).execute(claim_path, bad, "exact", "_mock", None, None, True)
        print(f"\n  -> first {first['outcome']}, second {second['outcome']}")
        if first["outcome"] != "FAILED_ATTEMPT":
            failures.append(f"the first failure ended {first['outcome']}, expected FAILED_ATTEMPT")
        if second["outcome"] != "ESCALATED":
            failures.append(
                f"the second identical failure ended {second['outcome']}, expected ESCALATED — "
                "an attempt that produced the same signature changed nothing the checker could see")
        packet = second.get("work_item")
        ok = bool(packet) and Path(packet).exists()
        print(f"  {'ok  ' if ok else 'MISS'}  the escalation produced a work item for the "
              "deep-attack role")
        print("          a trigger whose only consequence is a printed word hands off to nobody")
        if not ok:
            failures.append("ESCALATED produced no work item")
        else:
            item = json.loads(Path(packet).read_text(encoding="utf-8"))
            complete = (item.get("assigned_role") == "researcher" and item.get("obstruction")
                        and item.get("read_first") and item.get("stop_rule"))
            print(f"  {'ok  ' if complete else 'MISS'}  it names the role, the obstruction, the "
                  "doctrine to read first, and a stop rule")
            if not complete:
                failures.append(f"the escalation work item is incomplete: {sorted(item)}")
        if second.get("escalated_by") == "repeat gate":
            print("          (escalated by the repeat gate, before the threshold counted to it — "
                  "same conclusion, less spent)")

        print("\nA claim whose dependency is undischarged — the loop must not work it:\n")
        blocked_claim = {"claim_id": "SELFTEST-BLOCKED",
                         "exact_statement": "the artifact equals the expected value",
                         "expected_value": "hello frame",
                         "dependency_mode": "AND", "dependencies": ["SUB-1"]}
        blocked_claim["target_sha256"] = hashlib.sha256(
            canonical(blocked_claim).encode()).hexdigest()
        blocked_path = tmp / "blocked_claim.json"
        blocked_path.write_text(json.dumps(blocked_claim, indent=2))
        blocked = Campaign(tmp / "run-blocked").execute(
            blocked_path, good, "exact", "_mock", None, None, True)
        ok = blocked["outcome"] == "BLOCKED"
        print(f"  {'ok  ' if ok else 'MISS'}  {blocked['outcome']}")
        print("          evidence produced under an undischarged dependency cannot close "
              "anything, so producing it is the most expensive way to do nothing")
        if not ok:
            failures.append(f"a claim with an undischarged AND dependency ended "
                            f"{blocked['outcome']}, expected BLOCKED")

        print("\nA check that could not run — a GAP, and never a failed attempt:\n")
        gap_claim = dict(claim)
        gap_claim["claim_id"] = "SELFTEST-GAP"
        gap_claim["frozen_conditions"] = {"unrunnable_gate": "fidelity-review"}
        gap_claim.pop("target_sha256", None)
        gap_claim["target_sha256"] = hashlib.sha256(
            canonical(gap_claim).encode()).hexdigest()
        gap_path = tmp / "gap_claim.json"
        gap_path.write_text(json.dumps(gap_claim, indent=2))
        gap_dir = tmp / "run-gap"
        gap = Campaign(gap_dir).execute(gap_path, good, "exact", "_mock", None, None, True)
        ok = gap["outcome"] == "INCOMPLETE" and "fidelity-review" in (gap.get("missing_checks") or [])
        print(f"  {'ok  ' if ok else 'MISS'}  {gap['outcome']}, missing "
              f"{gap.get('missing_checks')}")
        print("          recording it as FAILED_ATTEMPT would say the route was shown not to "
              "work, and would feed the ladder a signal the deep-attack role cannot act on")
        if not ok:
            failures.append(f"an unrunnable required check ended {gap['outcome']}, "
                            f"expected INCOMPLETE naming the gate")
        ledger_exists = (gap_dir / "failures.json").exists()
        print(f"  {'ok  ' if not ledger_exists else 'MISS'}  the failure ledger was not advanced")
        print("          a streak of 'the judge was unavailable' must not escalate")
        if ledger_exists:
            failures.append("an incomplete run wrote to the failure ledger")

        print("\nTwo packs on one claim — a fatal objection from EITHER blocks:\n")
        pair_claim = dict(claim); pair_claim["claim_id"] = "SELFTEST-PAIR"
        pair_claim.pop("target_sha256", None)
        pair_claim["target_sha256"] = hashlib.sha256(canonical(pair_claim).encode()).hexdigest()
        pair_path = tmp / "pair_claim.json"; pair_path.write_text(json.dumps(pair_claim, indent=2))
        both = Campaign(tmp / "run-pair").execute(
            pair_path, good, "exact", "_mock", None, None, True, None, None, None, None, None,
            None, [("_mock", "exact", str(good))])
        ok = both["outcome"] == "ADMITTED"
        print(f"  {'ok  ' if ok else 'MISS'}  {both['outcome']} with both packs passing")
        print("          a rule that blocks every paired claim enforces nothing, it just stops")
        if not ok:
            failures.append(f"a paired claim both packs accept ended {both['outcome']}")

        objecting = Campaign(tmp / "run-pair-block").execute(
            pair_path, good, "exact", "_mock", None, None, True, None, None, None, None, None,
            None, [("_mock", "exact", str(bad))])
        ok = objecting["outcome"] == "BLOCKED_BY_PAIR"
        print(f"  {'ok  ' if ok else 'MISS'}  {objecting['outcome']} when the second pack fails")
        print("          verdicts are not averaged; a pass in one field never compensates for a "
              "failure in another")
        if not ok:
            failures.append(f"a paired claim with one failing pack ended {objecting['outcome']}")

        print("\nA declared budget — the run must stop rather than overrun it:\n")
        gov_path = tmp / "gov.json"
        gov_path.write_text(json.dumps(governor.new_state(5, {"cheap": 4, "moderate": 4,
                                                             "expensive": 2})))
        broke = Campaign(tmp / "run-broke").execute(
            claim_path, good, "exact", "_mock", None, None, True, None, gov_path, 500)
        ok = broke["outcome"] == "STOPPED_ON_BUDGET"
        print(f"  {'ok  ' if ok else 'MISS'}  {broke['outcome']}")
        print("          a ceiling that queues is not a ceiling; stopping and reporting what "
              "was reached is a legitimate result")
        if not ok:
            failures.append(f"a run costing 500 against a budget of 5 ended {broke['outcome']}")

        print("\nAn affordable run — the budget must be charged, not merely consulted:\n")
        gov_path.write_text(json.dumps(governor.new_state(1000, {"cheap": 4, "moderate": 4,
                                                                 "expensive": 2})))
        Campaign(tmp / "run-charged").execute(
            claim_path, good, "exact", "_mock", None, None, True, None, gov_path, 40)
        after = governor.load(gov_path)
        ok = after["spent"] == 40 and not after["running"]
        print(f"  {'ok  ' if ok else 'MISS'}  spent {after['spent']}, "
              f"{len(after['running'])} worker(s) still reserved")
        print("          a governor consulted and never charged reports a budget nobody spent")
        if not ok:
            failures.append(f"after an affordable run the governor shows spent={after['spent']} "
                            f"running={after['running']}")

        print("\nOne process wearing two role labels — the reducer must refuse:\n")
        same = {"actor_id": "one-process", "attested_by": "orchestrator"}
        collide = Campaign(tmp / "run-collide").execute(
            claim_path, good, "exact", "_mock", None, None, True, None, None, None, same, same)
        ok = collide["outcome"] != "ADMITTED"
        print(f"  {'ok  ' if ok else 'MISS'}  {collide['outcome']}")
        print("          the labels differ and the actor does not; attestation is what makes "
              "that visible")
        if not ok:
            failures.append("a chain whose producer and admitter share an actor was ADMITTED")

        print("\nTwo attested actors — the loop must still close:\n")
        attested = Campaign(tmp / "run-attested").execute(
            claim_path, good, "exact", "_mock", None, None, True, None, None, None,
            {"actor_id": "worker-a", "attested_by": "orchestrator"},
            {"actor_id": "session-b", "attested_by": "orchestrator"})
        ok = attested["outcome"] == "ADMITTED"
        print(f"  {'ok  ' if ok else 'MISS'}  {attested['outcome']}, "
              f"granted {attested.get('granted')}")
        print("          a check that refuses every attested chain enforces nothing, it "
              "just stops")
        if not ok:
            failures.append(f"an attested chain ended {attested['outcome']}: "
                            f"{attested.get('refusals')}")

    print("\n" + "=" * 62)
    if failures:
        print(f"  CAMPAIGN SELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print("  CAMPAIGN SELF-TEST: PASS — the loop closes, the ladder engages, the budget "
          "stops it, and one process cannot admit its own work")
    return 0


def campaign_status(state_path: Path, governor_path: Path | None, as_json: bool) -> int:
    """Where is this campaign.

    `run` and `self-test` were the whole surface. Once a campaign became a GRAPH
    — several claims, several packs, six revisions, a governor with a spent
    budget — there was no way to ask what state it was in without reading the
    JSON, and no way at all to pick one up after an interruption.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    plan = schedule.plan(state, governor.load(governor_path) if governor_path else None)
    claims = state.get("claims") or {}
    root = state.get("root_claim_id")
    spend = None
    if governor_path:
        gov = governor.load(governor_path)
        spend = {"budget": gov.get("budget_total"), "spent": gov.get("spent"),
                 "remaining": governor.remaining(gov)}

    payload = {"revision": state.get("revision"), "outcome": state.get("outcome"),
               "root": root, "root_status": (claims.get(root) or {}).get("status"),
               "ceiling": (claims.get(root) or {}).get("ceiling"),
               "claims": {k: v.get("status") for k, v in claims.items()},
               "ready": [w["claim_id"] for w in plan["wave"]],
               "blocked": plan["blocked"], "races": plan["races"], "budget": spend}
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"CAMPAIGN  revision {payload['revision']}  outcome {payload['outcome']}")
    print(f"  root      {root} — {payload['root_status']} (ceiling {payload['ceiling']})")
    for cid, status in payload["claims"].items():
        mark = "root" if cid == root else "    "
        extra = ""
        if cid in payload["blocked"]:
            extra = f"  blocked: {payload['blocked'][cid]}"
        elif cid in payload["ready"]:
            extra = "  READY"
        elif (claims.get(cid) or {}).get("superseded_by"):
            extra = f"  superseded by {claims[cid]['superseded_by']}"
        print(f"  [{mark}] {cid:<12} {status:<16}{extra}")
    for race in payload["races"]:
        print(f"  race under {race['parent']}: {', '.join(race['siblings'])}")
    if spend:
        print(f"  budget    {spend['spent']} spent of {spend['budget']}, "
              f"{spend['remaining']:.0f} remaining")
    if not payload["ready"]:
        print("  nothing is ready. Either the root is closed or every open claim waits on "
              "something, and the outcome above says which")
    return 0


def campaign_doctor(state_path: Path, as_json: bool) -> int:
    """Invariants a campaign state must satisfy, checked rather than assumed.

    Every one of these was violated at some point by a real run in this repo,
    and each time it was found by a downstream refusal rather than by asking.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    claims = state.get("claims") or {}
    problems: list[str] = []

    root = state.get("root_claim_id")
    if root not in claims:
        problems.append(f"root_claim_id {root!r} is not among the claims")
    for cid, claim in claims.items():
        if not claim.get("target_sha256"):
            problems.append(f"{cid}: no target_sha256 — the claim is bound to no frozen "
                            "statement, so no admission can ever match it")
        for dep in claim.get("dependencies") or []:
            if dep not in claims:
                problems.append(f"{cid}: depends on {dep!r}, which is not in this state")
        mode = claim.get("dependency_mode", "LEAF")
        if mode in {"AND", "OR"} and not (claim.get("dependencies") or []):
            problems.append(f"{cid}: mode {mode} with no dependencies — it can never close")
        ceiling = claim.get("ceiling")
        if ceiling and rank_status(claim.get("status", "OPEN")) > rank_status(ceiling):
            problems.append(f"{cid}: status {claim['status']} is above its ceiling {ceiling}")
        if claim.get("superseded_by") and claim["superseded_by"] not in claims:
            problems.append(f"{cid}: superseded by {claim['superseded_by']!r}, which is not here")

    # a cycle means no claim in it can ever be discharged
    seen, stack = set(), set()

    def walk(cid):
        if cid in stack:
            problems.append(f"dependency cycle through {cid!r}: nothing in it can be discharged")
            return
        if cid in seen:
            return
        stack.add(cid); seen.add(cid)
        for dep in (claims.get(cid) or {}).get("dependencies") or []:
            if dep in claims:
                walk(dep)
        stack.discard(cid)

    for cid in claims:
        walk(cid)

    if as_json:
        print(json.dumps({"problems": problems, "claims": len(claims),
                          "revision": state.get("revision")}, indent=2))
        return 1 if problems else 0
    print(f"DOCTOR  {len(claims)} claim(s) at revision {state.get('revision')}")
    for problem in problems:
        print(f"  FAIL  {problem}")
    print("  PASS — the graph is walkable, bound, and within its ceilings"
          if not problems else f"  {len(problems)} problem(s)")
    return 1 if problems else 0


def campaign_resume(state_path: Path, db: Path | None, run_id: str | None,
                    as_json: bool) -> int:
    """Pick up a campaign that stopped, and say what it was in the middle of.

    `--state` let a run JOIN a graph and nothing detected an INTERRUPTED one: a
    workdir holding a work item and no admission looked exactly like a workdir
    nobody had touched. The evidence chain survives — every revision names its
    predecessor — so what was missing was somebody reading it back.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    claims = state.get("claims") or {}
    leased: list[dict] = []
    if db and run_id:
        import registry
        conn = registry.connect(db)
        try:
            leased = registry.leases(conn, run_id, time.time())
        finally:
            conn.close()

    stale = [entry for entry in leased if entry["expired"]]
    live = [entry for entry in leased if not entry["expired"]]
    plan = schedule.plan(state, None, {entry["claim_id"] for entry in live})
    payload = {"revision": state.get("revision"), "outcome": state.get("outcome"),
               "in_flight": live, "abandoned": stale,
               "ready": [w["claim_id"] for w in plan["wave"]],
               "blocked": plan["blocked"]}
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"RESUME  revision {payload['revision']}  outcome {payload['outcome']}  "
          f"{len(claims)} claim(s)")
    for entry in live:
        print(f"  in flight  {entry['claim_id']:<14} {entry['actor']} "
              f"({entry['expires_in']:.0f}s left)")
    for entry in stale:
        print(f"  ABANDONED  {entry['claim_id']:<14} {entry['actor']} — the lease expired and "
              "nothing released it. Whatever that worker was doing, nobody is doing it now")
    if payload["ready"]:
        print(f"  pick up    {', '.join(payload['ready'])}")
    else:
        print("  nothing to pick up. Either the root is closed or every open claim waits on "
              "something, and the outcome above says which")
    if not leased and db:
        print("  no leases recorded for this run — either it never took one, or the registry "
              "is not the one it used")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--claim", required=True)
    r.add_argument("--artifact", required=True)
    r.add_argument("--tier", required=True)
    source = r.add_mutually_exclusive_group(required=True)
    source.add_argument("--domain")
    source.add_argument("--statement")
    r.add_argument("--workdir")
    r.add_argument("--review")
    r.add_argument("--receipt", help="re-admit an existing receipt instead of re-running the "
                   "adapter. The reducer still re-hashes the artifact against it.")
    r.add_argument("--governor", help="a governor state from scripts/governor.py init. "
                   "Without one nothing stops this run on cost.")
    r.add_argument("--cost", type=int, help="what this tier run costs, overriding the "
                   "tier's cost_hint")
    r.add_argument("--producer-actor", help="orchestrator-assigned actor id for the producing "
                   "role. Without it the chain is self-attested and cannot pass CHECKED_BOUNDED.")
    r.add_argument("--admitter-actor", help="orchestrator-assigned actor id for the admitting "
                   "role. Must differ from --producer-actor; the reducer refuses when it does "
                   "not, because the label is not the fact.")
    r.add_argument("--also", action="append", default=[], metavar="PACK:TIER:ARTIFACT",
                   help="a second pack this claim also engages (ARCHITECTURE.md 2.2). Its "
                        "adapter runs on the same frozen claim, a fail from ANY engaged pack "
                        "blocks, and the ceiling becomes the weakest of them.")
    r.add_argument("--state", help="an existing campaign state to advance. Without it this "
                   "initialises a fresh single-claim state, and the decomposition Explorer made "
                   "has no way to meet the work that closes it.")
    r.add_argument("--write", action="store_true")
    r.add_argument("--json", action="store_true")
    s = sub.add_parser("status", help="where is this campaign")
    s.add_argument("--state", required=True); s.add_argument("--governor")
    s.add_argument("--json", action="store_true")
    dr = sub.add_parser("doctor", help="invariants a campaign state must satisfy")
    dr.add_argument("--state", required=True); dr.add_argument("--json", action="store_true")
    rs = sub.add_parser("resume", help="pick up a campaign that stopped")
    rs.add_argument("--state", required=True); rs.add_argument("--registry")
    rs.add_argument("--run"); rs.add_argument("--json", action="store_true")
    sub.add_parser("self-test")
    args = ap.parse_args()

    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "status":
        return campaign_status(Path(args.state),
                               Path(args.governor) if args.governor else None, args.json)
    if args.cmd == "doctor":
        return campaign_doctor(Path(args.state), args.json)
    if args.cmd == "resume":
        return campaign_resume(Path(args.state),
                               Path(args.registry) if args.registry else None,
                               args.run, args.json)

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="campaign-"))
    campaign = Campaign(workdir, quiet=args.json)
    try:
        def actor(value: str | None) -> dict | None:
            return ({"actor_id": value, "attested_by": "orchestrator"} if value else None)

        report = campaign.execute(
            Path(args.claim), Path(args.artifact), args.tier, args.domain, args.statement,
            Path(args.review) if args.review else None, args.write,
            Path(args.receipt) if args.receipt else None,
            Path(args.governor) if args.governor else None, args.cost,
            actor(args.producer_actor), actor(args.admitter_actor),
            Path(args.state) if args.state else None,
            [tuple(spec.split(":", 2)) for spec in args.also])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n  OUTCOME: {report['outcome']}")
        if report.get("granted"):
            print(f"  granted {report['granted']} at revision {report.get('revision')}, "
                  f"pack ceiling {report.get('ceiling')}")
        for refusal in report.get("refusals", []):
            print(f"    refused: {refusal}")
        print(f"  packets in {report['workdir']}")

    return {"ADMITTED": 0, "ESCALATED": 3, "STOPPED_ON_BUDGET": 4,
            "INCOMPLETE": 5, "BLOCKED_BY_PAIR": 6}.get(report["outcome"], 1)


if __name__ == "__main__":
    sys.exit(main())
