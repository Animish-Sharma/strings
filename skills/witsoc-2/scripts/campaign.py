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
    campaign.py self-test

Exit: 0 admitted, 1 refused or not admitted, 2 usage/IO error, 3 escalated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from reducer import canonical, seal, state_hash  # noqa: E402
from jsonschema_lite import validate  # noqa: E402


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


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


class Campaign:
    def __init__(self, workdir: Path, quiet: bool = False):
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.quiet = quiet
        self.steps: list[dict] = []

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

    def execute(self, claim_path: Path, artifact: Path, tier: str,
                domain: str | None, statement: str | None,
                review_path: Path | None, write: bool,
                receipt_path: Path | None = None) -> dict:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        target = claim.get("target_sha256")

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
            return self.report("ESCALATED", target_sha256=target, repeat=risk,
                               escalated_by="repeat gate")
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
            # A result is a CANDIDATE. VERIFIED is not in the enum here at all,
            # because only an admission grants it — the schema refuses to let a
            # producer even propose the word.
            "candidate_status": ("CHECKED_BOUNDED" if receipt["max_status"] == "VERIFIED"
                                 else receipt["max_status"]) if verdict == "pass"
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

            ledger = self.dir / "failures.json"
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
            return self.report("ESCALATED" if escalate else "FAILED_ATTEMPT",
                               pack=pack, ceiling=ceiling, receipt=receipt,
                               escalate=escalate)

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
            run([sys.executable, str(HERE / "memory.py"), "record-result",
                 "--mem", str(memory), "--statement", claim.get("exact_statement", "")[:300],
                 "--admission-id", admission["admission_id"]])
            self.step("remember", True,
                      f"recorded in {memory.name}; a later campaign against this target starts "
                      "from what this one learned")

        return self.report("ADMITTED" if applied else "REFUSED",
                           pack=pack, ceiling=ceiling, granted=granted if applied else None,
                           receipt=receipt, refusals=outcome.get("refusals", []),
                           revision=outcome.get("revision"))

    def report(self, outcome: str, **extra) -> dict:
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
        elif second.get("escalated_by") == "repeat gate":
            print("          (escalated by the repeat gate, before the threshold counted to it — "
                  "same conclusion, less spent)")

    print("\n" + "=" * 62)
    if failures:
        print(f"  CAMPAIGN SELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print("  CAMPAIGN SELF-TEST: PASS — the loop closes, and the ladder engages")
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
    r.add_argument("--write", action="store_true")
    r.add_argument("--json", action="store_true")
    sub.add_parser("self-test")
    args = ap.parse_args()

    if args.cmd == "self-test":
        return self_test()

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="campaign-"))
    campaign = Campaign(workdir, quiet=args.json)
    try:
        report = campaign.execute(
            Path(args.claim), Path(args.artifact), args.tier, args.domain, args.statement,
            Path(args.review) if args.review else None, args.write,
            Path(args.receipt) if args.receipt else None)
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

    return {"ADMITTED": 0, "ESCALATED": 3}.get(report["outcome"], 1)


if __name__ == "__main__":
    sys.exit(main())
