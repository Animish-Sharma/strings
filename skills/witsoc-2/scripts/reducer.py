#!/usr/bin/env python3
"""The reducer — the only thing that may move a status.

Everything else in the frame proposes. This disposes, and it is the difference
between a system that documents discipline and one that enforces it.

Before this existed the architecture had a gap at its centre: its founding
premise is that an agent cannot be trusted to self-report correctness, and its
enforcement mechanism was trusting the agent to run the checks. A role could skip
every gate and assert `VERIFIED`. Now a status can only change by applying an
admission through this code, and an admission that skipped a check cannot be
applied.

What it refuses, and why each refusal exists:

  schema violation        a malformed packet is not a packet
  target mismatch         the packet is about a different claim than this state
  stale base_revision     the state moved underneath a long-running attempt; the
                          conclusion may rest on a premise that has since been
                          demoted. This is the lost-update guard and it bites
                          hardest on exactly the role that runs longest.
  broken seal             payload_sha256 does not cover the bytes presented
  unbound result          the result does not name the work item by seal, so the
                          dispatch constraints it answered cannot be checked
  check not PASS          an accepted status with any acceptance condition FAIL
                          or NOT_RUN. NOT_RUN is refused as firmly as FAIL: a
                          check that did not run is not a check that passed.
  check not DERIVED       the admission asserts a check the receipt does not
                          support. `checks` used to be read; it is now DERIVED
                          from the receipt and the supplied packets, and a
                          disagreement between what was asserted and what the
                          evidence shows is refused rather than silently
                          corrected — the disagreement is the finding.
  receipt not bound       an accepted status with no receipt_ref, or a receipt
                          whose seal does not match it. Without this the chain
                          of enforcement ended in a self-report at the one point
                          where self-reports are the thing being guarded against.
  ceiling above receipt   granting a status stronger than the tier that produced
                          the receipt can support. A pack whose backend tops out
                          at CHECKED_BOUNDED cannot yield VERIFIED however many
                          admissions arrive.
  wrong deciding role     an admission decided by anything but Explorer. A
                          production role admitting its own output is what the
                          no-merge invariant forbids, and this is where that
                          becomes mechanical.
  review of another result a review whose producer_ref does not name the result
                          actually supplied. An unbound review discharges
                          independence for work it never saw.
  attention as evidence   an admission whose evidence hashes to an entry in the
                          run's working memory. SOC memory is attention and is
                          allowed to be wrong; laundering it into a receipt is
                          how a hunch becomes a status. The schema already stops
                          the crude form — an insight id is not 64 hex — so the
                          form worth guarding is the careful one: hashing a soc
                          entry and offering the digest as evidence.
  same-domain review      a reviewer sharing the producer's role AND method
                          family. Two checks sharing a failure domain are one
                          check; this fails closed when either side declines to
                          say which family it used.
  dependency not closed   granting an accepted status to a claim resting on one
                          that is not accepted. AND needs all; OR needs one.
  ceiling exceeded        bounded evidence can never be lifted to VERIFIED by a
                          later admission, however many arrive
  injected claim          a delta adding a claim at anything but OPEN with no
                          evidence — that is how a pre-established conclusion
                          gets smuggled in as a side effect
  self-review             independent_review PASS with no review whose reviewer
                          differs from the producer

Usage:
    reducer.py init --claim <claim.json> --out <state.json>
    reducer.py show --state <state.json> [--json]
    reducer.py seal --packet <p.json>            compute payload_sha256
    reducer.py validate --packet <p.json> --kind claim|work-item|result|receipt|review|admission
    reducer.py replay --state <state.json> [--json]
    reducer.py apply --state <state.json> --admission <a.json> [--result <r.json>]
                     [--review <rev.json>] [--receipt <rc.json>]
                     [--artifact <path>] [--write]

`--artifact` is what makes receipt_freshness checkable: the reducer re-hashes the
live bytes and compares them against the hash the receipt recorded at
verification time. Without it freshness is NOT_RUN, which is refused for any
status needing the full check set — a passing run from an earlier edit is the
standard way a broken artifact launders itself.

Exit: 0 accepted, 1 refused, 2 IO/usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonschema_lite import validate  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = SKILL_ROOT / "schemas"

KIND_SCHEMA = {
    "claim": "frame-claim-v1", "work-item": "frame-work-item-v1",
    "result": "frame-result-v1", "receipt": "frame-receipt-v1",
    "review": "frame-review-v1", "admission": "frame-admission-v1",
    "state": "frame-state-v1",
}

ACCEPTED = {"CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED"}
# Statuses that assert something about the world and therefore need every check.
NEEDS_FULL_CHECKS = {"VERIFIED"}
CEILING_ORDER = ["OPEN", "CONJECTURE", "GAP", "FAILED_ATTEMPT", "REJECTED",
                 "CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED"]


def canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def seal(packet: dict) -> str:
    """payload_sha256 over the packet with that field removed."""
    return hashlib.sha256(canonical({k: v for k, v in packet.items()
                                     if k != "payload_sha256"}).encode()).hexdigest()


def state_hash(state: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in state.items()
                                     if k != "state_sha256"}).encode()).hexdigest()


def load_schema(kind: str) -> dict:
    return json.loads((SCHEMAS / f"{KIND_SCHEMA[kind]}.schema.json").read_text(encoding="utf-8"))


def rank(status: str) -> int:
    return CEILING_ORDER.index(status) if status in CEILING_ORDER else -1


def closure_satisfied(claim: dict, claims: dict) -> tuple[bool, str]:
    """AND needs every dependency accepted; OR needs one. LEAF needs none."""
    mode = claim.get("dependency_mode", "LEAF")
    deps = claim.get("dependencies") or []
    if mode == "LEAF" or not deps:
        return True, ""
    accepted = [d for d in deps if claims.get(d, {}).get("status") in ACCEPTED]
    if mode == "AND":
        missing = [d for d in deps if d not in accepted]
        return (not missing), (
            f"AND node needs every dependency accepted; {missing} are not" if missing else "")
    if mode == "OR":
        return bool(accepted), (
            "OR node needs at least one accepted dependency; none is" if not accepted else "")
    return False, f"unknown dependency_mode {mode!r}"


FULL_CHECKS = ["target_binding", "receipt_freshness", "refute_attempt",
               "dependency_closure", "no_open_gap", "fidelity", "independent_review"]

# What each status actually requires. Before this, every accepted status needed
# every check, which collapsed the vocabulary: if SKETCH and VERIFIED demand the
# same evidence there is no reason to have both words. The sets below follow from
# what each status MEANS in references/status_vocabulary.md.
#
#   SKETCH            a complete-looking argument, unchecked by any backend. It
#                     needs to be about the right target and nothing more; a
#                     SKETCH that required a passing receipt would be a lie about
#                     what the word means.
#   PARTIAL           a narrower product, so: real evidence, closed dependencies,
#                     and no requirement that the refutation gate was reached.
#   CHECKED_BOUNDED   bounded evidence that survived an attempt to break it.
#   CONDITIONAL       a claim about the general statement with one named open
#                     assumption. `no_open_gap` is deliberately absent — the gap
#                     is the point — and independent review is required precisely
#                     because someone other than the producer has to agree that
#                     the named condition is the ONLY gap.
#   VERIFIED          everything.
# ---------------------------------------------------------------- attestation
#
# Role separation was, until this landed, a STRING. `decided_by_role`,
# `emitted_by`, `reviewer_role` and `method_family` are fields in packets that
# one agent may write all of, and the reducer compared the labels. So the
# founding premise — an agent cannot be trusted to self-report correctness — was
# enforced rigorously for evidence and not at all for IDENTITY, which is what
# makes "a role may never accept its own work" mean anything.
#
# The frame cannot verify identity by itself: sessions, workers and processes
# belong to the orchestrator (SKILL.md, Boundary). What it can do is refuse to
# treat an unattested separation as evidence of one. So:
#
#   * every packet may carry an `actor` block — an opaque `actor_id` the
#     orchestrator assigns, and `attested_by`, which is either `orchestrator` or
#     `self`;
#   * two packets sharing an `actor_id` are the SAME actor whatever their role
#     labels say, and the pairs that must differ are refused outright;
#   * `attested_by: "self"`, or no actor block at all, means nobody outside the
#     run vouched for the separation. Independence is then NOT_RUN — not FAIL,
#     because nothing was shown to be wrong, and not PASS, because nothing was
#     shown at all.
#
# The consequence is deliberate and it is the honest one: without orchestrator
# attestation a run cannot reach CONDITIONAL or VERIFIED, because those are the
# statuses whose meaning depends on someone other than the producer agreeing.
# That is the same shape as the campaign loop's own ceiling, arrived at from the
# other direction.

SELF_ATTESTED = "self"
ORCHESTRATOR_ATTESTED = "orchestrator"


def actor_of(packet: dict | None) -> tuple[str | None, str]:
    """(actor_id, attested_by) for a packet. Absent means self-attested."""
    if not packet:
        return None, SELF_ATTESTED
    actor = packet.get("actor") or {}
    attested = (actor.get("attested_by") or SELF_ATTESTED).strip().lower()
    if attested != ORCHESTRATOR_ATTESTED:
        attested = SELF_ATTESTED
    return (actor.get("actor_id") or None), attested


def attestation_problems(admission: dict, result: dict | None,
                         reviews: list[dict]) -> tuple[list[str], str]:
    """Refuse shared actors; report how strong the separation evidence is.

    Returns the problems and one of `orchestrator`, `self`.
    """
    problems: list[str] = []
    admit_id, admit_attested = actor_of(admission)
    result_id, result_attested = actor_of(result)

    if admit_id and result_id and admit_id == result_id:
        problems.append(
            f"the admitting actor and the producing actor are the same ({admit_id!r}). "
            "Role labels differ and the actor does not — a producer admitting its own "
            "work is what the no-merge invariant forbids, and the label is not the fact")

    weakest = ORCHESTRATOR_ATTESTED
    for attested in (admit_attested, result_attested):
        if attested == SELF_ATTESTED:
            weakest = SELF_ATTESTED

    for review in reviews:
        review_id, review_attested = actor_of(review)
        if review_attested == SELF_ATTESTED:
            weakest = SELF_ATTESTED
        if review_id and result_id and review_id == result_id:
            problems.append(
                f"review {review.get('review_id')!r} was produced by the same actor as the "
                f"result ({review_id!r}). Self-review is not review, whatever the two "
                "role labels say")
        if review_id and admit_id and review_id == admit_id:
            problems.append(
                f"review {review.get('review_id')!r} shares its actor with the admission "
                f"({admit_id!r}). The role that decides may not also be the role that "
                "vouched")
    return problems, weakest


REQUIRED_BY_STATUS = {
    "SKETCH": ["target_binding"],
    "PARTIAL": ["target_binding", "receipt_freshness", "dependency_closure"],
    "CHECKED_BOUNDED": ["target_binding", "receipt_freshness", "refute_attempt",
                        "dependency_closure"],
    "CONDITIONAL": ["target_binding", "receipt_freshness", "refute_attempt",
                    "dependency_closure", "independent_review"],
    "VERIFIED": FULL_CHECKS,
}


def closure_check(state: dict, admission: dict) -> str:
    """PASS when every claim this admission moves has its dependencies discharged."""
    claims = state.get("claims") or {}
    moved = (admission.get("delta") or {}).get("update_claims", []) or []
    if not moved:
        return "NOT_RUN"
    for upd in moved:
        current = claims.get(upd.get("claim_id"))
        if current is None:
            return "FAIL"
        ok, _why = closure_satisfied({**current, **upd}, claims)
        if not ok:
            return "FAIL"
    return "PASS"


def derive_checks(state: dict, admission: dict, extras: dict) -> tuple[dict, list[str]]:
    """Compute each acceptance condition from the evidence, rather than reading
    what the admission says about it.

    This is the difference between an enforced chain and a documented one. Before
    it, `checks: {"refute_attempt": "PASS"}` was an assertion by whoever wrote the
    admission — the reducer guarded seals, staleness and closure, then took the
    verification result on trust, at the exact point where the architecture's
    founding premise says trust is unavailable.

    Every condition returns PASS, FAIL, or NOT_RUN, and NOT_RUN is the default:
    a condition whose evidence was not supplied has not been met. Returns the
    derived table plus any structural problems found along the way.
    """
    problems: list[str] = []
    checks: dict[str, str] = {name: "NOT_RUN" for name in FULL_CHECKS}

    receipt = extras.get("receipt")
    result = extras.get("result")
    reviews = extras.get("reviews") or []
    ref = admission.get("receipt_ref")

    # target_binding does not need a receipt: the admission and the state either
    # name the same frozen target or they do not.
    if admission.get("target_sha256") == state.get("target_sha256"):
        checks["target_binding"] = "PASS"
    else:
        checks["target_binding"] = "FAIL"

    if not ref:
        # Not an error by itself. A status that needs receipt-derived evidence
        # will fail on the NOT_RUN below; a status that does not need it (SKETCH)
        # is legitimately granted without one.
        #
        # DEPENDENCY CLOSURE is derived anyway. It is a walk over this state's
        # graph and needs no receipt at all, and returning here without it meant
        # a claim admitted on its dependencies was refused for failing a check
        # nothing had attempted — the one check it could actually have passed.
        checks["dependency_closure"] = closure_check(state, admission)
        return checks, problems
    if receipt is None:
        problems.append(
            f"receipt_ref names {ref.get('receipt_id')!r} but no --receipt was supplied. The "
            "reducer derives checks from the receipt; without it there is nothing to derive from")
        return checks, problems
    if seal(receipt) != ref.get("payload_sha256"):
        problems.append(
            "the supplied receipt does not match receipt_ref.payload_sha256. A reference bound "
            "by seal survives the receipt it names being re-run to a different verdict; this one "
            "names a different receipt")
        return checks, problems

    # --- target_binding, now with the receipt in the chain too
    #
    # The chain binds to the CLAIM being moved, which in a graph is usually not
    # the campaign root. Comparing everything against the root passed only for a
    # single-claim campaign and made every sub-claim unadmittable — a
    # decomposition could be recorded and nothing in it could ever close. The
    # guarantee is unchanged: receipt, admission and the claim's own frozen hash
    # must be the same value, and that value must belong to a claim in THIS
    # state rather than to any statement someone chose to name.
    claim_hashes = {c.get("target_sha256") for c in (state.get("claims") or {}).values()
                    if c.get("target_sha256")}
    claim_hashes.add(state.get("target_sha256"))
    bound = admission.get("target_sha256")
    if receipt.get("target_sha256") == bound and bound in claim_hashes:
        checks["target_binding"] = "PASS"
    else:
        checks["target_binding"] = "FAIL"
        problems.append(
            f"target mismatch across the chain: admission {str(bound)[:12]}..., "
            f"receipt {str(receipt.get('target_sha256'))[:12]}...; "
            + ("the receipt verifies a different statement than the admission names"
               if receipt.get("target_sha256") != bound else
               "no claim in this state was frozen at that statement"))

    # --- the receipt has to be a pass at all
    if receipt.get("verdict") != "pass":
        problems.append(
            f"the receipt's own verdict is {receipt.get('verdict')!r}. An admission cannot grant "
            "an accepted status on a verification that did not pass")

    # --- receipt_freshness: re-hash the live artifact, never trust the record
    live = extras.get("artifact_sha256")
    if live is None:
        checks["receipt_freshness"] = "NOT_RUN"
    elif live == receipt.get("artifact_sha256"):
        checks["receipt_freshness"] = "PASS"
    else:
        checks["receipt_freshness"] = "FAIL"
        problems.append(
            f"STALE RECEIPT: it verified {str(receipt.get('artifact_sha256'))[:12]}..., the "
            f"artifact is now {live[:12]}.... A passing run from an earlier edit is the standard "
            "way a broken artifact launders itself")

    # --- refute_attempt: survived, not merely attempted
    outcome = (receipt.get("refute_attempt") or {}).get("outcome")
    checks["refute_attempt"] = {"survived": "PASS", "broken": "FAIL"}.get(outcome, "NOT_RUN")

    # --- doctrine obligations, answered or not
    #
    # A role that ignored its doctrine entirely passed every check, because
    # everything downstream examines the ARTIFACT and nothing examined the
    # process that made it. An obligation issued with the work item and answered
    # in the result does not prove a step was done well; it makes skipping one
    # visible, which is the difference between a rule and a hope.
    #
    # `not_done` is a legitimate answer. Silence is not: a step nobody mentions
    # and a step nobody took are the same thing in a result.
    work_item = extras.get("work_item") or {}
    demanded = work_item.get("obligations") or []
    if demanded:
        answers = {a["id"]: a for a in (result or {}).get("obligations_answered", []) or []}
        unanswered, refused = [], []
        for obligation in demanded:
            oid = obligation["id"]
            answer = answers.get(oid)
            if answer is None:
                unanswered.append(oid)
            elif answer["outcome"] == "not_done":
                needed = obligation.get("required_for")
                if needed is None or admission.get("granted_status") in needed:
                    refused.append(f"{oid} ({obligation['demand'][:60]})")
        if unanswered:
            checks["obligations"] = "NOT_RUN"
            problems.append(
                f"the work item issued obligation(s) {unanswered} and the result does not "
                "mention them. A step nobody mentions and a step nobody took are the same "
                "thing here, so this is not read as done")
        elif refused:
            checks["obligations"] = "FAIL"
            problems.append(
                f"obligation(s) reported NOT DONE and required for this status: "
                f"{'; '.join(refused)}. The doctrine made them mandatory where the work was "
                "issued, which is the only place a process step can be made refusable")
        else:
            checks["obligations"] = "PASS"

    # --- who RAN the verification
    #
    # Attestation covered producer, reviewer and admitter and never asked this.
    # A tier declaring `authorship: independent` is a backend that knows nothing
    # about the run and cannot be talked into a pass, so the producer running it
    # is fine and the field has been saying so, unread, since it was written.
    # Any other tier is one the party being checked may have influenced, and
    # there the verifier has to be somebody else.
    authorship = (receipt.get("authorship") or "unstated").strip().lower()
    if authorship != "independent":
        verifier_id, verifier_attested = actor_of(receipt)
        if receipt.get("verifier"):
            verifier_id = receipt["verifier"].get("actor_id")
            verifier_attested = (receipt["verifier"].get("attested_by") or SELF_ATTESTED).lower()
        producer_id, _ = actor_of(result)
        if not verifier_id or verifier_attested != ORCHESTRATOR_ATTESTED:
            checks["verifier_independence"] = "NOT_RUN"
            problems.append(
                f"the tier's authorship is {authorship!r}, so the backend is not one that "
                "refuses on its own account, and no attested verifier ran it. Who checked this "
                "is then unknown, and an unknown checker is the party being checked until "
                "somebody says otherwise")
        elif producer_id and verifier_id == producer_id:
            checks["verifier_independence"] = "FAIL"
            problems.append(
                f"the verifier and the producer are the same actor ({verifier_id!r}) on a tier "
                f"whose authorship is {authorship!r}. A graded check run by the party being "
                "checked is that party's opinion with a receipt attached")
        else:
            checks["verifier_independence"] = "PASS"
    else:
        checks["verifier_independence"] = "PASS"

    # --- no_open_gap: from the receipt's own completeness record
    completeness = receipt.get("completeness")
    if completeness is None:
        checks["no_open_gap"] = "NOT_RUN"
    else:
        clean = (not completeness.get("open_gaps") and not completeness.get("rejections")
                 and not admission.get("remaining_gap_ids"))
        checks["no_open_gap"] = "PASS" if clean else "FAIL"

    # --- fidelity: does the checked artifact say what the target says? The
    # backend proves things about an encoding; whether the encoding is faithful
    # is a separate question it cannot answer, so it comes from the result.
    fidelity = (result or {}).get("fidelity_record")
    if fidelity is None:
        checks["fidelity"] = "NOT_RUN"
    else:
        # frame-result-v1 names this field `faithful`, a boolean. Reading a
        # differently-named key here returned None for every well-formed record
        # and derived FAIL from it — a check reporting a finding it never made,
        # which is the failure mode this whole derivation exists to prevent.
        ok = fidelity.get("faithful") is True
        if ok and fidelity.get("checked_by_ref") in (None, "", result.get("result_id"),
                                                     result.get("emitted_by")):
            problems.append(
                "fidelity_record is self-certified: checked_by_ref does not name someone other "
                "than the result's emitter")
            ok = False
        checks["fidelity"] = "PASS" if ok else "FAIL"

    # --- dependency_closure: the reducer's own computation, from the delta
    closure = []
    claims = dict(state.get("claims", {}))
    for upd in admission.get("delta", {}).get("update_claims", []) or []:
        current = claims.get(upd.get("claim_id"))
        if current is None:
            continue
        ok, _ = closure_satisfied({**current, **upd}, claims)
        closure.append(ok)
    checks["dependency_closure"] = ("PASS" if closure and all(closure)
                                    else "NOT_RUN" if not closure else "FAIL")

    # --- independent_review: bound to THIS result, by a distinct reviewer whose
    # role and method family do not collapse into the producer's.
    if not reviews:
        checks["independent_review"] = "NOT_RUN"
    else:
        usable = []
        for review in reviews:
            if review.get("verdict") != "accept" or review.get("independent") is not True:
                continue
            if review.get("producer_ref") == review.get("reviewer_ref"):
                problems.append(
                    f"review {review.get('review_id')!r} has the producer reviewing themselves")
                continue
            if result is not None and review.get("producer_ref") not in (
                    result.get("result_id"), result.get("emitted_by")):
                problems.append(
                    f"review {review.get('review_id')!r} names producer "
                    f"{review.get('producer_ref')!r}, which is not the result supplied "
                    f"({result.get('result_id')!r}). An unbound review discharges independence "
                    "for work it never saw")
                continue
            if result is not None and review.get("reviewer_role") == result.get("emitted_by"):
                families = (review.get("method_family"), result.get("method_family"))
                if None in families or families[0] == families[1]:
                    problems.append(
                        f"review {review.get('review_id')!r} shares the producer's role "
                        f"({result.get('emitted_by')}) and does not establish a different method "
                        "family. Two checks sharing a failure domain are one check, and this "
                        "fails closed when either side declines to say which family it used")
                    continue
            usable.append(review)
        checks["independent_review"] = "PASS" if usable else "FAIL"
        # An unattested separation is not a demonstrated one. Downgrading to
        # NOT_RUN rather than FAIL is the accurate reading: nothing here was
        # shown to be wrong, and nothing was shown to be independent either.
        _, strength = attestation_problems(admission, result, reviews)
        if checks["independent_review"] == "PASS" and strength == SELF_ATTESTED:
            checks["independent_review"] = "NOT_RUN"
            checks["independence_attestation"] = SELF_ATTESTED
        if not admission.get("review_refs"):
            problems.append("reviews were supplied but the admission lists no review_refs")

    shared, _strength = attestation_problems(admission, result, reviews)
    problems.extend(shared)

    return checks, problems


def replay(state: dict) -> dict:
    """Check the history actually accounts for the state.

    `frame-state-v1` calls its history append-only and says it is what makes a
    run replayable rather than merely logged. Nothing replayed it. An
    append-only log nobody re-derives from is a log, and the difference only
    shows when the two disagree — which is precisely when it matters.

    Three consistency claims, each of which can fail independently:

      * the revision count equals the number of applied admissions
      * every claim whose status moved names an admission, and that admission is
        in the history
      * no admission appears twice — a replayed admission is the classic way a
        status moves without new evidence
    """
    problems: list[str] = []
    history = state.get("history", []) or []
    applied = [h for h in history if h.get("decision") == "ACCEPT"]
    claims = state.get("claims", {}) or {}

    if state.get("revision") != len(applied):
        problems.append(
            f"revision is {state.get('revision')} and {len(applied)} admission(s) were accepted. "
            "One of the two is wrong, and the state cannot say which")

    known = {h.get("admission_id") for h in history}
    seen: set[str] = set()
    for entry in history:
        aid = entry.get("admission_id")
        if aid in seen:
            problems.append(f"admission {aid!r} appears twice in the history — a replayed "
                            "admission moves a status without new evidence")
        seen.add(aid)

    for claim_id, claim in claims.items():
        status = claim.get("status")
        if status in {"OPEN", "CONJECTURE"}:
            continue
        admitted_by = claim.get("admitted_by")
        if not admitted_by:
            problems.append(
                f"claim {claim_id!r} is {status} and names no admission. Only an admission may "
                "move a status, so a status with nothing behind it did not come through here")
        elif admitted_by not in known:
            problems.append(
                f"claim {claim_id!r} names admission {admitted_by!r}, which is not in the history")

    return {"consistent": not problems, "revisions": state.get("revision"),
            "history": history, "claims": len(claims), "problems": problems}


def refuse(state: dict, admission: dict, extras: dict) -> list[str]:
    """Every reason this admission may not be applied."""
    problems: list[str] = []

    errors: list[str] = []
    validate(admission, load_schema("admission"), "admission", errors)
    problems += errors
    if problems:
        return problems

    # An admission identifies the CLAIM it moves, which in a graph is usually not
    # the root. The state carries one target hash — the campaign's — and
    # comparing against it alone meant a sub-claim could never be admitted: a
    # decomposition could be recorded and then nothing in it could ever close.
    # The binding still has to hold, so the hash must match a claim that is
    # actually in this state, and the campaign root remains valid for itself.
    claim_targets = {c.get("target_sha256") for c in (state.get("claims") or {}).values()
                     if c.get("target_sha256")}
    if (admission.get("target_sha256") != state.get("target_sha256")
            and admission.get("target_sha256") not in claim_targets):
        problems.append(
            f"target mismatch: admission is about {admission.get('target_sha256','')[:16]}..., "
            f"this state is {state.get('target_sha256','')[:16]}...")

    if admission.get("base_revision") != state.get("revision"):
        problems.append(
            f"STALE: admission was cut against revision {admission.get('base_revision')}, "
            f"state is at {state.get('revision')}. The state moved underneath it, so its "
            "conclusion may rest on a premise that has since changed.")
    expected_hash = state_hash(state)
    if admission.get("base_state_sha256") not in (None, expected_hash):
        problems.append(
            f"base_state_sha256 {admission['base_state_sha256'][:16]}... does not match this "
            f"state ({expected_hash[:16]}...); it was derived from a different history")

    if admission.get("payload_sha256") and admission["payload_sha256"] != seal(admission):
        problems.append("broken seal: payload_sha256 does not cover these bytes")

    # Validate every supplied packet, not only the admission. A malformed
    # result was previously accepted as long as its seal matched — and a
    # fidelity_record with the wrong field names sailed through, because
    # nothing checked its shape and the derivation read a key that was not
    # there. Two bugs that cancelled, which is the kind that survives longest.
    for kind, packet in (("result", extras.get("result")),
                         ("receipt", extras.get("receipt"))):
        if packet is not None:
            shape: list[str] = []
            validate(packet, load_schema(kind), kind, shape)
            problems += shape
    for index, review in enumerate(extras.get("reviews") or []):
        shape = []
        validate(review, load_schema("review"), f"review[{index}]", shape)
        problems += shape
    if problems:
        return problems

    result = extras.get("result")
    if result is not None:
        ref = admission.get("result_ref", {})
        if seal(result) != ref.get("payload_sha256"):
            problems.append("the supplied result does not match result_ref.payload_sha256")
        if not result.get("work_item_sha256"):
            problems.append("result is not bound to a work item by seal, so the dispatch "
                            "constraints it answered cannot be checked")
        if result.get("trust_boundary") != "CANDIDATE_ONLY":
            problems.append("result does not carry trust_boundary CANDIDATE_ONLY")

    decision = admission.get("decision")
    granted = admission.get("granted_status")
    asserted = admission.get("checks", {})

    if decision == "ACCEPT":
        if admission.get("decided_by_role") != "explorer":
            problems.append(
                f"decided_by_role is {admission.get('decided_by_role')!r}. Only Explorer "
                "arbitrates; a production role admitting its own output is precisely what the "
                "no-merge invariant forbids")

        if not granted:
            problems.append("ACCEPT with no granted_status")
        elif granted in ACCEPTED:
            derived, notes = derive_checks(state, admission, extras)
            problems += notes

            # A claim whose content is exactly "all/one of these hold" has no
            # artifact and needs none: its evidence is the receipts its
            # dependencies were admitted on. Demanding a receipt of its own meant
            # the parent that motivated a decomposition could never be closed,
            # and the only way past it was to invent an artifact for a
            # conjunction — which is a fiction the frame otherwise refuses.
            #
            # The hole this could open is admitting a parent on nothing, so the
            # path is narrow: the claim must BE a dependency node, its closure
            # must hold, it must have at least one admitted dependency, and the
            # status it may be granted is capped at the WEAKEST of them. A
            # conjunction is never stronger than its weakest part.
            required = REQUIRED_BY_STATUS.get(granted, FULL_CHECKS)
            moved = [u for u in (admission.get("delta") or {}).get("update_claims", []) or []]
            if moved and not any(u.get("evidence_sha256") for u in moved):
                node = (state.get("claims") or {}).get(moved[0].get("claim_id")) or {}
                deps = node.get("dependencies") or []
                dep_statuses = [((state.get("claims") or {}).get(d) or {}).get("status", "OPEN")
                                for d in deps]
                admitted = [s for s in dep_statuses if s in ACCEPTED]
                if (node.get("dependency_mode") in {"AND", "OR"} and admitted
                        and derived.get("dependency_closure") == "PASS"):
                    weakest = min(admitted, key=rank)
                    if rank(granted) > rank(weakest):
                        problems.append(
                            f"cannot grant {granted} on closure alone: the weakest admitted "
                            f"dependency is {weakest}. A conjunction is never stronger than its "
                            "weakest part, and a disjunction is never stronger than the branch "
                            "that carried it")
                    else:
                        # Discharged BY the dependencies, each of which was
                        # admitted on a receipt that passed its own pack's gates.
                        required = [c for c in required
                                    if c not in {"receipt_freshness", "refute_attempt"}]
                        derived["closure_evidence"] = (
                            f"{len(admitted)} admitted dependenc(y/ies), weakest {weakest}")
            for name in required:
                actual = derived.get(name, "NOT_RUN")
                if actual != "PASS":
                    problems.append(
                        f"cannot grant {granted}: check '{name}' is {actual}"
                        + (" — a check that did not run is not a check that passed"
                           if actual == "NOT_RUN" else ""))
                claimed = asserted.get(name)
                if claimed is not None and claimed != actual:
                    problems.append(
                        f"the admission asserts '{name}' is {claimed} and the evidence shows "
                        f"{actual}. Checks are derived here, not read; a disagreement between "
                        "the two is the finding, not a formatting difference")

            receipt = extras.get("receipt")
            if receipt is not None:
                ceiling = receipt.get("max_status")
                if ceiling and rank(granted) > rank(ceiling):
                    problems.append(
                        f"cannot grant {granted}: the receipt's tier tops out at {ceiling}. "
                        "A ceiling is a property of the backend that produced the evidence, and "
                        "no number of admissions raises it")

    # Attention may not become evidence. Working memory is allowed to hold a
    # hunch — that permission is what makes it attention rather than a second,
    # unverified evidence store — so the one thing it must never do is appear
    # behind a status. The crude route is already closed by the schema: an
    # insight id is not sixty-four hex characters. The careful route is to hash
    # a soc entry and offer the digest, and that is what this closes.
    soc = extras.get("soc")
    if soc:
        attention: dict[str, str] = {}
        for insight in soc.get("insights", []) or []:
            attention[hashlib.sha256(
                canonical(insight).encode()).hexdigest()] = f"insight {insight.get('id')}"
            attention[hashlib.sha256(
                str(insight.get("text", "")).encode()).hexdigest()] = f"insight {insight.get('id')}"
        for failure in soc.get("failed_approaches", []) or []:
            attention[hashlib.sha256(
                canonical(failure).encode()).hexdigest()] = f"failure {failure.get('id')}"
        offered = []
        for upd in (admission.get("delta", {}) or {}).get("update_claims", []) or []:
            offered += list(upd.get("evidence_sha256") or [])
        for digest in offered:
            if digest in attention:
                problems.append(
                    f"evidence {digest[:12]}... is {attention[digest]} from the run's working "
                    "memory. Attention is allowed to be wrong, which is exactly why it may not "
                    "stand behind a status — hashing it does not change what it is")

    delta = admission.get("delta", {}) or {}
    claims = dict(state.get("claims", {}))

    for add in delta.get("add_claims", []) or []:
        if add.get("status") != "OPEN":
            problems.append(
                f"delta adds claim {add.get('claim_id')!r} at status {add.get('status')!r}; "
                "a new claim enters OPEN with no evidence, or a pre-established "
                "conclusion could be introduced as a side effect of an admission")
        if add.get("evidence_refs"):
            problems.append(f"delta adds claim {add.get('claim_id')!r} carrying evidence")

    for upd in delta.get("update_claims", []) or []:
        cid = upd.get("claim_id")
        current = claims.get(cid)
        if current is None:
            problems.append(f"delta updates unknown claim {cid!r}")
            continue
        if upd.get("from_status") != current.get("status"):
            problems.append(
                f"delta updates {cid!r} from {upd.get('from_status')!r} but it is "
                f"{current.get('status')!r} — the delta was computed against a different state")
        to_status = upd.get("to_status")
        if to_status in ACCEPTED:
            # Empty evidence is legitimate for a claim that IS a dependency node:
            # its evidence is the receipts its dependencies were admitted on. The
            # closure check below is what makes that safe, and the acceptance
            # path caps the status at the weakest admitted dependency.
            node_evidence = (current.get("dependency_mode") in {"AND", "OR"}
                             and (current.get("dependencies") or []))
            if not upd.get("evidence_sha256") and not node_evidence:
                problems.append(
                    f"{cid!r} -> {to_status} with no evidence, and it is not a dependency node. "
                    "A leaf claim's status rests on a receipt; there is nothing else it could "
                    "rest on")
            ok, why = closure_satisfied({**current, **upd}, claims)
            if not ok:
                problems.append(f"{cid!r} -> {to_status}: dependency closure fails. {why}")
            ceiling = current.get("ceiling")
            if ceiling and rank(to_status) > rank(ceiling):
                problems.append(
                    f"{cid!r} -> {to_status} exceeds its ceiling {ceiling}. Bounded evidence "
                    "does not become universal evidence by accumulating admissions.")
    return problems


def apply_delta(state: dict, admission: dict) -> dict:
    new = json.loads(json.dumps(state))
    delta = admission.get("delta", {}) or {}
    for add in delta.get("add_claims", []) or []:
        claim = {
            "claim_id": add["claim_id"], "status": "OPEN",
            "statement": add.get("statement", ""), "dependency_mode": "LEAF",
            "dependencies": [], "evidence_refs": [],
            # Required by the delta schema, validated on the way in, and thrown
            # away here until now — which is why an admission for a sub-claim
            # could never bind to anything.
            **({"target_sha256": add["target_sha256"]} if add.get("target_sha256") else {})}
        # A ceiling is set at creation and never raised: there is no delta
        # operation that lifts one. That is what makes a provisional pack's cap
        # enforceable rather than advisory.
        if add.get("ceiling"):
            claim["ceiling"] = add["ceiling"]
        new["claims"][add["claim_id"]] = claim
    for upd in delta.get("update_claims", []) or []:
        claim = new["claims"][upd["claim_id"]]
        claim["status"] = upd["to_status"]
        claim["admitted_by"] = admission["admission_id"]
        if upd.get("evidence_sha256"):
            claim["evidence_refs"] = list(upd["evidence_sha256"])
    # Race cancellation: an annotation, never a status. See the delta schema.
    for entry in delta.get("supersede", []) or []:
        claim = new["claims"].get(entry["claim_id"])
        winner = new["claims"].get(entry["superseded_by"])
        if claim is None or winner is None:
            continue
        # A race is decided by a sibling PASSING; cancelling on anything less
        # discards work for nothing.
        if rank(winner.get("status", "OPEN")) >= rank("CHECKED_BOUNDED"):
            claim["superseded_by"] = entry["superseded_by"]

    for dep in delta.get("set_dependencies", []) or []:
        claim = new["claims"].get(dep["claim_id"])
        if claim:
            claim["dependency_mode"] = dep["to_mode"]
            claim["dependencies"] = list(dep["to_dependencies"])
    if "active_obstruction" in delta:
        new["active_obstruction"] = delta["active_obstruction"]
    new["open_gaps"] = admission.get("remaining_gap_ids", new.get("open_gaps", []))

    # The rollup is about the ROOT, and it has to separate two situations that
    # called for opposite next moves and were reported with the same word: a
    # campaign that established its target as strongly as the pack allows, and
    # one where a sub-claim closed and the target is still open. Both read
    # PARTIAL, so a finished campaign was indistinguishable from one that had
    # barely started.
    root = new.get("root_claim_id")
    root_claim = new["claims"].get(root, {}) if root else {}
    root_status = root_claim.get("status")
    ceiling = root_claim.get("ceiling") or new.get("ceiling") or "VERIFIED"
    if root_status == "VERIFIED":
        new["outcome"] = "SOLVED"
    elif root_status == "REJECTED":
        new["outcome"] = "DISPROVED"
    elif root_status in ACCEPTED:
        # At the ceiling there is nothing further to reach here; below it there
        # is, and the difference is what a reader needs.
        new["outcome"] = "CLOSED" if rank(root_status) >= rank(ceiling) else "PARTIAL"
    elif any(c["status"] in ACCEPTED for c in new["claims"].values()):
        new["outcome"] = "PARTIAL"

    new["revision"] = state["revision"] + 1
    new["previous_state_sha256"] = state_hash(state)
    new.setdefault("history", []).append({
        "revision": new["revision"], "admission_id": admission["admission_id"],
        "decision": admission["decision"],
        "granted_status": admission.get("granted_status"),
        "claim_ids": [u["claim_id"] for u in (delta.get("update_claims") or [])],
        "admission_sha256": seal(admission)})
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--claim", required=True); i.add_argument("--out", required=True)
    i.add_argument("--ceiling", choices=["CONJECTURE", "SKETCH", "PARTIAL", "CHECKED_BOUNDED",
                                         "CONDITIONAL", "VERIFIED"],
                   help="strongest status this campaign may ever reach. Take it from "
                        "resolve_domain.py's max_admissible_status: a provisional pack caps at "
                        "SKETCH, and passing it here is what makes the cap enforced rather than "
                        "printed.")
    s = sub.add_parser("show"); s.add_argument("--state", required=True); s.add_argument("--json", action="store_true")
    se = sub.add_parser("seal"); se.add_argument("--packet", required=True)
    rp = sub.add_parser("replay"); rp.add_argument("--state", required=True)
    rp.add_argument("--json", action="store_true")
    v = sub.add_parser("validate"); v.add_argument("--packet", required=True)
    v.add_argument("--kind", required=True, choices=sorted(KIND_SCHEMA)); v.add_argument("--json", action="store_true")
    a = sub.add_parser("apply"); a.add_argument("--state", required=True)
    a.add_argument("--admission", required=True); a.add_argument("--result")
    a.add_argument("--review", nargs="*", default=[]); a.add_argument("--receipt")
    a.add_argument("--artifact", help="the live artifact, re-hashed to check receipt freshness")
    a.add_argument("--work-item", help="the work item this result answers; it carries the "
                   "doctrine obligations the result has to address, and without it the reducer "
                   "cannot tell an unanswered obligation from one never demanded")
    a.add_argument("--soc", help="the run's working memory. Supplying it lets the reducer refuse "
                   "an admission whose evidence is a laundered attention entry.")
    a.add_argument("--write", action="store_true"); a.add_argument("--json", action="store_true")
    args = ap.parse_args()

    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    try:
        if args.cmd == "init":
            claim = read(args.claim)
            state = {"schema": "frame-state-v1",
                     "target_sha256": claim["target_sha256"], "revision": 0,
                     "previous_state_sha256": None,
                     "root_claim_id": claim["claim_id"],
                     "claims": {claim["claim_id"]: {
                         "claim_id": claim["claim_id"], "statement": claim.get("exact_statement", ""),
                         "status": claim.get("status", "OPEN"),
                         "target_sha256": claim["target_sha256"],
                         "dependency_mode": claim.get("dependency_mode", "LEAF"),
                         "dependencies": claim.get("dependencies", []), "evidence_refs": [],
                         **({"ceiling": args.ceiling} if args.ceiling else {})}},
                     "active_obstruction": None, "open_gaps": [], "outcome": "OPEN",
                     "history": []}
            Path(args.out).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            print(f"initialized {args.out} at revision 0, state {state_hash(state)[:16]}...")
            print("  Nothing can move a status except an admission applied through this reducer.")
            if args.ceiling:
                print(f"  Ceiling {args.ceiling}: an admission above it is refused, not warned about.")
            return 0

        if args.cmd == "replay":
            state = read(args.state)
            report = replay(state)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"REPLAY: {'CONSISTENT' if report['consistent'] else 'BROKEN'} — "
                      f"{report['revisions']} revision(s), {len(report['history'])} admission(s)")
                for problem in report["problems"]:
                    print(f"  {problem}")
                if report["consistent"]:
                    print("  Every claim's status names the admission that set it, every "
                          "admission is in the history, and the revision count matches. The "
                          "history is a record and not a story told afterwards.")
            return 0 if report["consistent"] else 1

        if args.cmd == "seal":
            print(seal(read(args.packet)))
            return 0

        if args.cmd == "show":
            state = read(args.state)
            if args.json:
                print(json.dumps({**state, "state_sha256": state_hash(state)}, indent=2))
            else:
                print(f"revision {state['revision']}  outcome {state['outcome']}  "
                      f"state {state_hash(state)[:16]}...")
                for cid, c in state["claims"].items():
                    mark = " <- root" if cid == state.get("root_claim_id") else ""
                    print(f"    {c['status']:<16} {cid}{mark}")
            return 0

        if args.cmd == "validate":
            packet = read(args.packet)
            errors: list[str] = []
            validate(packet, load_schema(args.kind), args.kind, errors)
            if packet.get("payload_sha256") and packet["payload_sha256"] != seal(packet):
                errors.append("payload_sha256 does not cover these bytes")
            if args.json:
                print(json.dumps({"valid": not errors, "problems": errors}, indent=2))
            elif errors:
                print(f"INVALID {args.kind} — {len(errors)} problem(s)")
                for e in errors:
                    print(f"  {e}")
            else:
                print(f"VALID {args.kind}")
            return 1 if errors else 0

        state = read(args.state)
        admission = read(args.admission)
        extras = {"result": read(args.result) if args.result else None,
                  "reviews": [read(r) for r in (args.review or [])],
                  "receipt": read(args.receipt) if args.receipt else None,
                  "artifact_sha256": (
                      hashlib.sha256(Path(args.artifact).read_bytes()).hexdigest()
                      if args.artifact else None),
                  "soc": read(args.soc) if args.soc else None,
                  # The work item is what ISSUED the obligations, so without it
                  # the reducer cannot tell an unanswered one from one that was
                  # never demanded. Supplying it is how a process step becomes
                  # refusable at all.
                  "work_item": read(args.work_item) if args.work_item else None}
        problems = refuse(state, admission, extras)

        if problems:
            out = {"applied": False, "refusals": problems,
                   "revision": state["revision"]}
            if args.json:
                print(json.dumps(out, indent=2))
            else:
                print(f"REFUSED — {len(problems)} reason(s)\n")
                for p in problems:
                    print(f"  {p}")
                print("\n  The state is unchanged. Nothing moved a status.")
            return 1

        new = apply_delta(state, admission)
        if args.write:
            Path(args.state).write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        out = {"applied": True, "revision": new["revision"],
               "outcome": new["outcome"], "state_sha256": state_hash(new),
               "written": bool(args.write)}
        print(json.dumps(out, indent=2) if args.json else
              f"APPLIED  revision {state['revision']} -> {new['revision']}  "
              f"outcome {new['outcome']}"
              + ("" if args.write else "\n  (dry run; pass --write to persist)"))
        return 0

    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
