#!/usr/bin/env python3
"""Adversarial self-test for the reducer.

The reducer is the only thing that may move a status, which makes it the one
component whose failure is unbounded: everything else in the frame proposes, and
a proposal that slips through a proposer is caught downstream. There is nothing
downstream of this.

So it is tested the way the packs test their adapters — by trying to break it.
Each case below is an admission an adversary would write. The reducer must
refuse every one, and must accept the single honest chain, and the accept case
matters as much as the refusals: a reducer that refuses everything enforces
nothing, it just stops.

The first case is the one that motivated all of this. Until the checks were
derived from the receipt, an admission asserting `checks: {..., "PASS"}` with no
receipt at all was applied, because the reducer read the assertion.

Usage:  reducer_selftest.py [--verbose]
Exit:   0 every case behaved as specified, 1 otherwise
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reducer import canonical, seal, state_hash  # noqa: E402

TARGET = hashlib.sha256(b"the frozen target of the self-test").hexdigest()
ARTIFACT_BYTES = b"the candidate artifact, exactly these bytes\n"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


def sealed(packet: dict) -> dict:
    packet = {k: v for k, v in packet.items() if k != "payload_sha256"}
    packet["payload_sha256"] = seal(packet)
    return packet


def build(state_rev0_hash: str) -> dict:
    """The honest chain: work item -> result -> receipt -> review -> admission."""
    work_item = sealed({
        "schema": "frame-work-item-v1", "work_item_id": "WI-1", "target_sha256": TARGET,
        "claim_id": "C1", "assigned_role": "generator",
        "expected_artifact": "a checkable artifact of the pack's declared kind",
        "falsifier": "the adapter returns fail on the frozen target",
        "forbidden_drift": ["the statement", "the frozen conditions"],
        "stop_rule": "two consecutive failures with the same signature",
        "obligations": [{"id": "falsify-first",
                         "demand": "run the degenerate and boundary cases before committing",
                         "doctrine": "doctrine/explorer.md"}],
        "base_revision": 0, "base_state_sha256": state_rev0_hash,
    })
    receipt = sealed({
        "schema": "frame-receipt-v1", "receipt_id": "RC-1", "target_sha256": TARGET,
        "artifact_sha256": ARTIFACT_SHA, "tier": "exact", "verdict": "pass", "authorship": "independent",
        "produced_at": "2026-08-21T00:00:00Z", "max_status": "VERIFIED",
        "refute_attempt": {"gate_name": "exact-recheck", "discharged_by": "adversarial_tier",
                           "outcome": "survived"},
        "completeness": {"all_obligations_covered": True, "concluding_step_covered": True,
                         "open_gaps": 0, "rejections": 0},
    })
    result = sealed({
        "schema": "frame-result-v1", "result_id": "RES-1", "work_item_id": "WI-1",
        "target_sha256": TARGET, "emitted_by": "generator", "candidate_status": "CHECKED_BOUNDED",
        "trust_boundary": "CANDIDATE_ONLY", "method_family": "direct-construction",
        "actor": {"actor_id": "worker-gen-7", "attested_by": "orchestrator"},
        "dependency_path_to_target": ["C1"],
        "obligations_answered": [{"id": "falsify-first", "outcome": "done",
                                  "detail": "empty, singleton and boundary instances checked"}],
        "work_item_sha256": work_item["payload_sha256"],
        "fidelity_record": {"faithful": True, "checked_by_ref": "REVIEWER-A",
                            "basis": "an independent reviewer compared the checked artifact "
                                     "against the frozen target"},
        "receipt_ref": {"receipt_id": "RC-1", "payload_sha256": receipt["payload_sha256"],
                        "target_sha256": TARGET},
    })
    review = sealed({
        "schema": "frame-review-v1", "review_id": "REV-1", "target_sha256": TARGET,
        "result_sha256": result["payload_sha256"], "producer_ref": "RES-1",
        "reviewer_ref": "REVIEWER-A", "reviewer_role": "researcher", "independent": True,
        "actor": {"actor_id": "worker-rev-3", "attested_by": "orchestrator"},
        "verdict": "accept", "method_family": "adversarial-recheck",
        "checks": {"target_fidelity": "PASS", "dependencies": "PASS",
                   "preconditions": "PASS", "circularity": "PASS"},
    })
    delta = {"update_claims": [{"claim_id": "C1", "from_status": "OPEN",
                               "to_status": "VERIFIED",
                               "evidence_sha256": [receipt["payload_sha256"]]}]}
    admission = sealed({
        "schema": "frame-admission-v1", "admission_id": "A-1", "target_sha256": TARGET,
        "actor": {"actor_id": "session-explorer-1", "attested_by": "orchestrator"},
        "base_revision": 0, "base_state_sha256": state_rev0_hash,
        "decided_by_role": "explorer",
        "result_ref": {"result_id": "RES-1", "payload_sha256": result["payload_sha256"]},
        "receipt_ref": {"receipt_id": "RC-1", "payload_sha256": receipt["payload_sha256"],
                        "target_sha256": TARGET},
        "decision": "ACCEPT", "granted_status": "VERIFIED",
        "checks": {"target_binding": "PASS", "receipt_freshness": "PASS",
                   "refute_attempt": "PASS", "dependency_closure": "PASS",
                   "no_open_gap": "PASS", "fidelity": "PASS",
                   "independent_review": "PASS"},
        "review_refs": [{"review_id": "REV-1", "payload_sha256": review["payload_sha256"]}],
        "delta": delta,
        "delta_sha256": hashlib.sha256(canonical(delta).encode()).hexdigest(),
        "rationale": "every condition derived from the supplied evidence",
    })
    return {"work_item": work_item, "receipt": receipt, "result": result,
            "review": review, "admission": admission}


def reseal_admission(admission: dict) -> dict:
    delta = admission.get("delta", {})
    admission["delta_sha256"] = hashlib.sha256(canonical(delta).encode()).hexdigest()
    return sealed(admission)


# Each mutation returns (packets, artifact_bytes) and must be REFUSED.
def m_no_receipt_ref(p, _):
    p["admission"].pop("receipt_ref")
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_receipt_withheld(p, _):
    p["_withhold_receipt"] = True
    return p, ARTIFACT_BYTES


def m_receipt_swapped(p, _):
    p["receipt"]["tier"] = "a different tier entirely"
    p["receipt"] = sealed(p["receipt"])
    return p, ARTIFACT_BYTES


def m_ceiling_exceeded(p, _):
    p["receipt"]["max_status"] = "CHECKED_BOUNDED"
    p["receipt"] = sealed(p["receipt"])
    p["admission"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["result"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["result"] = sealed(p["result"])
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_refute_broken(p, _):
    p["receipt"]["refute_attempt"]["outcome"] = "broken"
    p["receipt"] = sealed(p["receipt"])
    p["admission"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_stale_artifact(p, _):
    return p, b"the artifact, edited after it was verified\n"


def m_open_gap(p, _):
    p["receipt"]["completeness"]["open_gaps"] = 1
    p["receipt"] = sealed(p["receipt"])
    p["admission"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_producer_admits(p, _):
    p["admission"]["decided_by_role"] = "generator"
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_same_domain_review(p, _):
    p["review"]["reviewer_role"] = "generator"
    p["review"]["method_family"] = "direct-construction"
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_review_of_other_result(p, _):
    p["review"]["producer_ref"] = "RES-SOMETHING-ELSE"
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_lying_checks(p, _):
    p["review"]["verdict"] = "reject"
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_unfaithful(p, _):
    p["result"]["fidelity_record"] = {"faithful": False, "checked_by_ref": "REVIEWER-A",
                                      "basis": "the artifact states a weaker claim"}
    p["result"] = sealed(p["result"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["review"]["result_sha256"] = p["result"]["payload_sha256"]
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_no_artifact_supplied(p, _):
    p["_withhold_artifact"] = True
    return p, ARTIFACT_BYTES


def m_sketch_no_receipt(p, _):
    """Not a refusal case — SKETCH legitimately needs no backend receipt."""
    p["admission"].pop("receipt_ref")
    p["admission"]["granted_status"] = "SKETCH"
    p["admission"]["checks"] = {"target_binding": "PASS"}
    p["admission"]["delta"]["update_claims"][0]["to_status"] = "SKETCH"
    p["admission"] = reseal_admission(p["admission"])
    p["_withhold_receipt"] = True
    return p, ARTIFACT_BYTES


def m_self_certified_fidelity(p, _):
    p["result"]["fidelity_record"] = {"faithful": True, "checked_by_ref": "RES-1",
                                      "basis": "the producer says so"}
    p["result"] = sealed(p["result"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["review"]["result_sha256"] = p["result"]["payload_sha256"]
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_malformed_result(p, _):
    p["result"]["fidelity_record"] = {"verdict": "faithful", "detail": "wrong field names"}
    p["result"] = sealed(p["result"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["review"]["result_sha256"] = p["result"]["payload_sha256"]
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_same_actor_admits(p, _):
    """The role labels differ and the ACTOR does not.

    This is the case the label comparison could never see: one agent writing
    both packets, setting `emitted_by` to generator and `decided_by_role` to
    explorer, and admitting its own work with the invariant apparently intact.
    """
    p["admission"]["actor"] = {"actor_id": "worker-gen-7", "attested_by": "orchestrator"}
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_same_actor_reviews(p, _):
    """Self-review wearing a second role label."""
    p["review"]["actor"] = {"actor_id": "worker-gen-7", "attested_by": "orchestrator"}
    p["review"] = sealed(p["review"])
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_unattested_chain(p, _):
    """Nobody outside the run vouched that these were different actors.

    Not a lie and not evidence. Independence becomes NOT_RUN, so VERIFIED —
    whose meaning depends on someone other than the producer agreeing — is out
    of reach. The frame cannot verify identity itself; what it can do is refuse
    to treat an unattested separation as a demonstrated one.
    """
    for key in ("result", "review", "admission"):
        p[key].pop("actor", None)
    p["result"] = sealed(p["result"])
    p["review"] = sealed(p["review"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["admission"]["review_refs"][0]["payload_sha256"] = p["review"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_graded_tier_no_verifier(p, _):
    """A tier the party being checked could have influenced, and nobody says who
    ran it. Authorship is the pack's own declaration that its backend refuses on
    its own account; without it the checker is unknown, and an unknown checker is
    the party being checked until somebody says otherwise."""
    p["receipt"]["authorship"] = "producer"
    p["receipt"] = sealed(p["receipt"])
    p["admission"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_verifier_is_producer(p, _):
    """The graded check was run by the producer. That is the producer's opinion
    with a receipt attached."""
    p["receipt"]["authorship"] = "producer"
    p["receipt"]["verifier"] = {"actor_id": "worker-gen-7", "attested_by": "orchestrator"}
    p["receipt"] = sealed(p["receipt"])
    p["admission"]["receipt_ref"]["payload_sha256"] = p["receipt"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_obligation_unanswered(p, _):
    """The work item made a step mandatory and the result does not mention it.

    Everything else in this suite examines the artifact. This is the only check
    that examines the PROCESS, and it can only ask whether the role said what it
    did — which is exactly enough to make skipping visible."""
    p["result"].pop("obligations_answered", None)
    p["result"] = sealed(p["result"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


def m_obligation_skipped(p, _):
    """Honestly reported as not done — and it was required for this status."""
    p["result"]["obligations_answered"] = [
        {"id": "falsify-first", "outcome": "not_done", "detail": "went straight to the kernel"}]
    p["result"] = sealed(p["result"])
    p["admission"]["result_ref"]["payload_sha256"] = p["result"]["payload_sha256"]
    p["admission"] = reseal_admission(p["admission"])
    return p, ARTIFACT_BYTES


REFUSE_CASES = [
    ("an issued obligation the result never mentions", m_obligation_unanswered,
     "does not mention",
     "a step nobody mentions and a step nobody took are the same thing in a result"),
    ("an obligation honestly reported as not done", m_obligation_skipped,
     "NOT DONE",
     "the doctrine made it mandatory where the work was issued"),
    ("a graded tier with nobody attesting who ran it", m_graded_tier_no_verifier,
     "no attested verifier",
     "authorship is the pack declaring its backend refuses on its own account"),
    ("a graded tier verified by the producer", m_verifier_is_producer,
     "same actor",
     "a check run by the party being checked is that party's opinion with a receipt"),
    ("the admitting actor IS the producing actor", m_same_actor_admits,
     "same",
     "role labels differ and the actor does not; the label is not the fact"),
    ("the reviewing actor IS the producing actor", m_same_actor_reviews,
     "same actor",
     "self-review wearing a second role label"),
    ("nobody attested that the actors were different", m_unattested_chain,
     "independent_review",
     "an unattested separation is not a demonstrated one, so VERIFIED is out of reach"),
    ("forged checks, no receipt at all", m_no_receipt_ref,
     "check 'receipt_freshness' is NOT_RUN",
     "the case that motivated deriving checks: assertions with nothing behind them"),
    ("receipt_ref present, receipt withheld", m_receipt_withheld,
     "no --receipt was supplied", "a reference to evidence nobody has to produce"),
    ("receipt swapped after being referenced", m_receipt_swapped,
     "does not match receipt_ref", "the seal is what makes the reference survive a re-run"),
    ("granting above the tier's ceiling", m_ceiling_exceeded,
     "tops out at CHECKED_BOUNDED", "a bounded backend cannot yield an unbounded status"),
    ("refutation broke the result", m_refute_broken,
     "refute_attempt", "surviving the gate is the condition, not attempting it"),
    ("artifact edited after verification", m_stale_artifact,
     "STALE RECEIPT", "the standard way a broken artifact launders itself"),
    ("an obligation left open", m_open_gap,
     "no_open_gap", "completeness is read from the receipt, not asserted"),
    ("the producer admits its own work", m_producer_admits,
     "Only Explorer arbitrates", "the no-merge invariant, made mechanical"),
    ("same role and same method reviewing", m_same_domain_review,
     "sharing a failure domain", "two checks sharing a failure domain are one check"),
    ("review bound to a different result", m_review_of_other_result,
     "work it never saw", "an unbound review discharges independence for nothing"),
    ("admission asserts PASS, review says reject", m_lying_checks,
     "the evidence shows", "the disagreement is the finding"),
    ("fidelity record says the artifact drifted", m_unfaithful,
     "fidelity", "the backend checks the encoding, not whether it is faithful"),
    ("the producer certifies its own fidelity", m_self_certified_fidelity,
     "self-certified", "checked_by_ref naming the emitter is not an independent check"),
    ("a malformed result packet", m_malformed_result,
     "fidelity_record", "a supplied packet is validated, not merely seal-checked"),
    ("no live artifact supplied to re-hash", m_no_artifact_supplied,
     "receipt_freshness", "freshness needs the bytes; NOT_RUN is not a pass"),
]


def run(tmp: Path, packets: dict, artifact: bytes) -> tuple[int, str]:
    state = json.loads((tmp / "state.json").read_text())
    (tmp / "artifact.bin").write_bytes(artifact)
    for name in ("receipt", "result", "review", "admission", "work_item"):
        (tmp / f"{name}.json").write_text(json.dumps(packets[name], indent=2))
    cmd = [sys.executable, str(HERE / "reducer.py"), "apply",
           "--state", str(tmp / "state.json"),
           "--admission", str(tmp / "admission.json"),
           "--result", str(tmp / "result.json"),
           "--review", str(tmp / "review.json"),
           # The work item carries the obligations. Without it the reducer
           # cannot tell an unanswered one from one never demanded, so a suite
           # that omits it silently skips the only check that examines process.
           "--work-item", str(tmp / "work_item.json"), "--json"]
    if not packets.get("_withhold_receipt"):
        cmd += ["--receipt", str(tmp / "receipt.json")]
    if not packets.get("_withhold_artifact"):
        cmd += ["--artifact", str(tmp / "artifact.bin")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    _ = state
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        claim = {"claim_id": "C1", "target_sha256": TARGET,
                 "exact_statement": "the claim under test", "status": "OPEN"}
        (tmp / "claim.json").write_text(json.dumps(claim, indent=2))
        subprocess.run([sys.executable, str(HERE / "reducer.py"), "init",
                        "--claim", str(tmp / "claim.json"), "--out", str(tmp / "state.json")],
                       capture_output=True, text=True, check=True)
        rev0 = state_hash(json.loads((tmp / "state.json").read_text()))

        failures = []
        print("Adversarial cases — each must be REFUSED:\n")
        for label, mutate, expect, why in REFUSE_CASES:
            packets, artifact = mutate(build(rev0), None)
            code, out = run(tmp, packets, artifact)
            refused = code == 1
            right_reason = expect.lower() in out.lower()
            ok = refused and right_reason
            print(f"  {'ok  ' if ok else 'MISS'}  {label}")
            print(f"          {why}")
            if args.verbose and ok:
                line = next((l.strip() for l in out.splitlines()
                             if expect.lower() in l.lower()), "")
                print(f"          -> {line[:150]}")
            if not refused:
                failures.append(f"{label}: applied (exit {code})")
            elif not right_reason:
                failures.append(f"{label}: refused, but no refusal mentions {expect!r} — "
                                f"right answer, wrong reason")

        print("\nHonest chains — must be ACCEPTED:\n")
        accepts = [
            ("VERIFIED with the full chain", lambda p: (p, ARTIFACT_BYTES),
             "a reducer that refuses everything enforces nothing, it just stops"),
            ("SKETCH with no backend receipt", lambda p: m_sketch_no_receipt(p, None),
             "the vocabulary is not collapsed: SKETCH means an unchecked argument, so demanding "
             "a passing receipt for it would be a lie about what the word means"),
        ]
        for label, prepare, why in accepts:
            packets, artifact = prepare(build(rev0))
            code, out = run(tmp, packets, artifact)
            ok = code == 0
            print(f"  {'ok  ' if ok else 'MISS'}  {label}")
            print(f"          {why}")
            if not ok:
                failures.append(f"{label} was refused: {out[:500]}")

        print("\n" + "=" * 62)
        if failures:
            print(f"  SELF-TEST: FAIL — {len(failures)}")
            for failure in failures:
                print(f"    {failure}")
            return 1
        print(f"  SELF-TEST: PASS — {len(REFUSE_CASES)} refused for the stated reason, "
              f"{len(accepts)} accepted")
        return 0


if __name__ == "__main__":
    sys.exit(main())
