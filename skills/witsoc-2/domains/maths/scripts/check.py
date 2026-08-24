#!/usr/bin/env python3
"""Mathematics verification adapter — the pack's entry point.

Implements the frame's adapter signature:

    (candidate artifact, claim, tier) -> (pass/fail, receipt)

and dispatches over three tiers. The frame never needs to know which one ran;
it only needs a frame-receipt-v1 back.

    structural  WIT shape check          ceiling SKETCH             not adversarial
    bounded     finite search            ceiling CHECKED_BOUNDED    adversarial in range
    kernel      elaboration vs Mathlib   ceiling VERIFIED           adversarial

Blocking gates run before any tier verdict is reported as a pass, because a
placeholder makes anything elaborate and a drifted statement makes anything
easy. A tier pass with a failed gate is a fail.

Usage:
    check.py --artifact <path> --claim <claim.json> --tier <name> [--json]
    check.py --self-test          run the negative controls; each must be rejected

Exit: 0 pass, 1 fail, 2 error, 3 tier unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The tier's authorship, copied from this pack's own manifest so the receipt
# states who stands behind the verification. `independent` means the backend
# knows nothing about the run and cannot be talked into a pass; anything else
# means the frame will require a verifier distinct from the producer. The
# manifest declared this from the beginning and nothing read it.
TIER_AUTHORSHIP = {
    "structural": "independent",
    "kernel": "independent",
    "bounded": "independent"
}

TIERS = {
    "structural": {"max_status": "SKETCH", "adversarial": False},
    "bounded": {"max_status": "CHECKED_BOUNDED", "adversarial": True},
    "kernel": {"max_status": "VERIFIED", "adversarial": True},
}


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


# A gate reports its verdict on stdout; Python writes warnings to stderr, and
# both are captured together. Taking line one meant a DeprecationWarning could
# appear in the receipt AS the gate's stated reason — a stack-trace fragment
# where the finding belongs. Prefer the first line that reads like a verdict.
VERDICT_LINE = re.compile(
    r"^\s*(?:[A-Z][A-Z \-]{2,}:|pass\b|fail\b|error\b|scope\b|note\b|not_run\b)",
    re.IGNORECASE)
# Strongest first. A gate that prints a scope note and then fails must be
# reported by the failure, not by the note that happened to come first.
VERDICT_RANK = (("fail", "error", "refused"), ("not_run", "not_applicable"),
                ("pass",), ("scope", "note"))


def verdict_detail(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    candidates = [ln for ln in lines if VERDICT_LINE.match(ln)]
    for tier in VERDICT_RANK:
        for line in candidates:
            if line.lower().lstrip().startswith(tier) or any(
                    t in line.split(":", 1)[0].lower() for t in tier):
                return line
    return candidates[0] if candidates else (lines[0] if lines else "")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Which artifact kinds each gate reads, from this pack's own manifest. Walked
# rather than indexed by path: the manifest nests gates under the verification
# block, and a lookup that guessed the location silently returned nothing.
def _manifest_gates(node):
    if isinstance(node, dict):
        if node.get("name") and node.get("script"):
            yield node
        for value in node.values():
            yield from _manifest_gates(value)
    elif isinstance(node, list):
        for value in node:
            yield from _manifest_gates(value)


GATE_APPLIES = {g["name"]: g.get("applies_to") for g in _manifest_gates(
    json.loads((HERE.parent / "domain.json").read_text(encoding="utf-8")))}


def run_gates(artifact: Path, claim_path: Path, tier: str,
              judges: str | None = None) -> list[dict]:
    """Blocking gates, scoped to what the tier can actually claim.

    A gate guards a status ceiling. The structural tier tops out at SKETCH, so
    demanding an independent fidelity panel before it is theatre. The kernel tier
    reaches VERIFIED, so every gate applies: a placeholder makes anything
    elaborate, an unaudited axiom makes anything derivable, and a faithful-looking
    encoding of the WRONG statement passes the checker perfectly.
    """
    gates = [
        ("placeholder-scan", [sys.executable, str(HERE / "gates" / "placeholder_scan.py"),
                              str(artifact)]),
        ("target-protection-diff", [sys.executable, str(HERE / "gates" / "target_protection.py"),
                                    str(artifact), "--claim", str(claim_path)]),
    ]
    if tier == "kernel":
        gates += [
            ("premise-precondition-audit",
             [sys.executable, str(HERE / "gates" / "premise_audit.py"),
              str(artifact), "--claim", str(claim_path)]),
            ("fidelity-review",
             [sys.executable, str(HERE / "gates" / "fidelity.py"),
              str(artifact), "--claim", str(claim_path)]
             + (["--judge-verdicts", judges] if judges else [])),
        ]
        if str(artifact).endswith(".lean"):
            gates.append(("axiom-audit",
                          [sys.executable, str(HERE / "gates" / "axiom_audit.py"),
                           str(artifact), "--claim", str(claim_path)]))
            # Only meaningful once the claim names something the proof must not
            # cite; the gate reports not_applicable otherwise rather than
            # failing every campaign whose target the library does not contain.
            circ = [sys.executable, str(HERE / "gates" / "circularity_audit.py"),
                    str(artifact), "--claim", str(claim_path)]
            # Without the index the gate can only check names the claim thought
            # to forbid. With it, `allowed_external_facts` becomes a check
            # against the proof term instead of a description of the plan.
            corpus = os.environ.get("WITSOC2_MATHS_CORPUS")
            if corpus and Path(corpus).exists():
                circ += ["--corpus", corpus]
            gates.append(("circularity-audit", circ))
    # A gate that does not read this artifact kind must report NOT_APPLICABLE,
    # not pass. Running it anyway produced a receipt line that looked like a
    # check and was one gate auditing zero citations — the same shape as the
    # drift gate that compared nothing on a checked artifact.
    kind = Path(artifact).suffix.lstrip(".")
    skipped = {name for name, applies in GATE_APPLIES.items()
               if applies and kind not in applies}
    results = []
    for name, cmd in gates:
        if name in skipped:
            results.append({"gate": name, "verdict": "not_applicable",
                            "detail": f"does not read a {kind!r} artifact; "
                                      "declared applies_to in the manifest"})
            continue
        code, output = run(cmd)
        results.append({
            "gate": name,
            # Four gate outcomes, and the two middle ones are routinely conflated.
            # not_run  (3): the gate applies and could not be run. A GAP.
            # not_applicable (4): the gate does not apply to this claim at all.
            # Collapsing them makes a claim that never needed a check look like
            # one that skipped it, and teaches readers to ignore both.
            "verdict": ("pass" if code == 0 else "error" if code == 2
                        else "not_run" if code == 3
                        else "not_applicable" if code == 4 else "fail"),
            "detail": verdict_detail(output),
        })
    return results


def run_tier(tier: str, artifact: Path, claim_path: Path, full_build: bool) -> dict:
    if tier == "structural":
        code, out = run([sys.executable, str(HERE / "tiers" / "structural.py"),
                         str(artifact), "--json"])
    elif tier == "bounded":
        code, out = run([sys.executable, str(HERE / "tiers" / "bounded.py"),
                         "--claim", str(claim_path), "--json"])
    else:
        cmd = [sys.executable, str(HERE / "tiers" / "kernel.py"), str(artifact), "--json"]
        if full_build:
            cmd.append("--full-build")
        code, out = run(cmd)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        payload = {"verdict": "error", "log_excerpt": out[:2000]}
    payload["_exit"] = code
    return payload


def axiom_audit_summary(tier: str, tier_pass: bool, gates: list[dict]) -> str:
    """What the axiom audit actually found.

    A receipt that contradicts itself is worse than one that omits a field: a
    reader resolves the contradiction by picking whichever half suits them, and
    a machine reads whichever half it was pointed at.
    """
    entry = next((g for g in gates if g["gate"] == "axiom-audit"), None)
    if tier != "kernel":
        return "not_run — the axiom audit needs a kernel elaboration to enumerate"
    if not tier_pass:
        return "not_run — the kernel did not elaborate, so there is nothing to enumerate"
    if entry is None:
        return "not_run — the gate was not dispatched"
    return f"{entry['verdict']} — {entry.get('detail', '')}".strip()


def build_receipt(tier: str, artifact: Path, claim: dict, tier_result: dict,
                  gates: list[dict], toolchain: str) -> dict:
    tier_pass = tier_result.get("verdict") == "pass"
    blocking_failed = [g for g in gates if g["verdict"] in {"fail", "error"}]
    blocking_gaps = [g for g in gates if g["verdict"] == "not_run"]
    if tier_result.get("verdict") == "not_run":
        verdict = "not_run"
    elif not tier_pass or blocking_failed:
        verdict = "fail"
    elif blocking_gaps:
        # The tier passed and a blocking gate never ran. That is neither a pass
        # nor a failure, and frame-receipt-v1 has had a word for it all along.
        verdict = "incomplete"
    else:
        verdict = "pass"

    adversarial = TIERS[tier]["adversarial"]
    receipt = {
        "schema": "maths-receipt-v1",
        "receipt_id": f"maths-{sha256_file(artifact)[:12]}-{tier}",
        "target_sha256": claim.get("target_sha256", ""),
        "artifact_sha256": sha256_file(artifact),
        "tier": tier,
        "authorship": TIER_AUTHORSHIP.get(tier, "unstated"),
        "verdict": verdict,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "max_status": TIERS[tier]["max_status"],
        # Each field states what ITS OWN evidence shows, not what the aggregate
        # verdict was. Keying them off the overall verdict made a receipt lie
        # about itself: on a run where the kernel elaborated cleanly and one
        # separate gate could not run, this reported the refutation as BROKEN —
        # a false statement about the adversarial tier, in the field the frame's
        # reducer derives `refute_attempt` from. The reducer would then refuse a
        # refutation that had in fact survived, and the refusal would look
        # principled.
        #
        # This is the frame's own derive-don't-read rule, applied one level
        # further in: a receipt is evidence about several separate things, and
        # collapsing them to one verdict throws away exactly the distinctions
        # the reducer was built to read.
        "refute_attempt": {
            "gate_name": "kernel-recheck",
            # Naming `skeptic_pass` at a tier that ran no skeptic validated and
            # was untrue. The method that will discharge this is the
            # adversarial tier; `outcome` already says it has not run.
            "discharged_by": "adversarial_tier",
            "outcome": ("not_run" if tier_result.get("verdict") == "not_run"
                        else "survived" if tier_pass else "broken"),
        },
        "completeness": {
            # What the TIER covered. A blocking gate that could not run leaves a
            # gap in the receipt and takes nothing away from what the kernel
            # elaborated.
            "all_obligations_covered": tier == "kernel" and tier_pass,
            "concluding_step_covered": tier == "kernel" and tier_pass,
            "open_gaps": len(blocking_gaps),
            "rejections": len(blocking_failed) + (0 if tier_pass else 1),
        },
        "supports_status": (TIERS[tier]["max_status"] if verdict == "pass" else None),
        "gaps": [g["gate"] for g in blocking_gaps],
        "not_applicable": [g["gate"] for g in gates if g["verdict"] == "not_applicable"],
        "gates": gates,
        "toolchain": toolchain,
        # From the gate that actually ran, not from the aggregate. This field
        # said "not_run — requires a kernel pass" while the axiom-audit gate in
        # the same receipt said `pass`, three lines below it.
        "axiom_audit": axiom_audit_summary(tier, tier_pass, gates),
        "environment": {"fresh_process": True, "fresh_copy": False, "restricted_env": False},
        "log_excerpt": json.dumps(tier_result)[:2000],
    }
    if not adversarial:
        receipt["refute_attempt"]["perturbation"] = (
            "structural tier is not adversarial; a separate refute-attempt is still owed"
        )
    if tier_result.get("failure_class"):
        receipt["failure_class"] = tier_result["failure_class"]
        receipt["failure_signature"] = tier_result.get("failure_signature", "")
    if tier == "bounded" and tier_result.get("bounds"):
        receipt["bounds"] = tier_result["bounds"]
    # Sealed: a receipt that cannot be bound to an admission by hash is a receipt
    # the reducer has to take on trust, which is the one thing it must not do.
    receipt["payload_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in receipt.items() if k != "payload_sha256"},
                   sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return receipt


def self_test() -> int:
    """Every negative control must be rejected. This is what turns the manifest's
    `adversarial: true` from a self-report into a test."""
    controls = sorted((HERE / "negative_control").glob("*.wit"))
    expect_reject = [c for c in controls if c.stem != "good"]
    expect_pass = [c for c in controls if c.stem == "good"]
    failures = []

    print("Negative controls — each must be REJECTED:\n")
    for control in expect_reject:
        code, _ = run([sys.executable, str(HERE / "tiers" / "structural.py"), str(control)])
        ok = code == 1
        print(f"  {'ok  ' if ok else 'MISS'}  {control.name}")
        if not ok:
            failures.append(f"{control.name} was not rejected (exit {code})")

    print("\nPositive control — must PASS:\n")
    for control in expect_pass:
        code, _ = run([sys.executable, str(HERE / "tiers" / "structural.py"), str(control)])
        ok = code == 0
        print(f"  {'ok  ' if ok else 'MISS'}  {control.name}")
        if not ok:
            failures.append(f"{control.name} did not pass (exit {code})")

    # The bounded tier declares `adversarial: true` in the manifest. Until this
    # ran, nothing tested it: the tier had a registered negative control and the
    # self-test never opened it, so the strongest claim in the manifest was the
    # least examined one. A search backend that silently returns "no
    # counterexample" is indistinguishable from one that works, and the only way
    # to tell them apart is an input where the answer is known to be no.
    print("\nBounded-tier negative controls — each must be REFUTED:\n")
    for control, why in (("bounded_false_claim.json", "n^2 > n fails at n = 0 and n = 1"),
                         ("bounded_false_pair.json", "C(n,0) = 1 < n — needs the second axis")):
        path = HERE / "negative_control" / control
        code, out = run([sys.executable, str(HERE / "tiers" / "bounded.py"),
                         "--claim", str(path), "--json"])
        refuted = code == 1
        print(f"  {'ok  ' if refuted else 'MISS'}  {control:<28} {why}")
        if not refuted:
            failures.append(f"{control} was not refuted by the bounded tier (exit {code})")

    placeholder = HERE / "negative_control" / "placeholder.lean"
    placeholder.write_text("theorem t : True := by\n  sorry\n", encoding="utf-8")
    code, _ = run([sys.executable, str(HERE / "gates" / "placeholder_scan.py"), str(placeholder)])
    ok = code == 1
    print(f"\n  {'ok  ' if ok else 'MISS'}  placeholder.lean rejected by placeholder-scan")

    # Two gates were inert on a Lean artifact and nobody noticed, because every
    # component check fed them a WIT file.
    #
    #  * target-protection parsed GIVEN:/CLAIM: blocks, which a .lean file does
    #    not have, and had an explicit .lean exemption — so it compared NOTHING
    #    and returned pass. An artifact that replaced the frozen target with
    #    `True` cleared the drift gate.
    #  * axiom-audit wrote its probe beside the artifact and ran the toolchain
    #    from the PROJECT directory, so a relative artifact path made the probe
    #    unreachable and the gate reported NOT_RUN — silently, and only for the
    #    callers who type relative paths, which is all of them.
    print("\nLean artifacts — the gates must not be inert on them:\n")
    lean_cases = [
        ("even_prod_drifted.lean", "target_protection.py", 1,
         "a statement replaced by True must be caught as drift"),
        ("even_prod_proved.lean", "target_protection.py", 0,
         "the honest artifact must still pass"),
        ("even_prod_postulated.lean", "axiom_audit.py", 1,
         "a locally postulated axiom must be caught through a RELATIVE path"),
    ]
    claim = HERE.parent / "evals" / "path" / "even_prod_claim.json"
    for name, gate, want, why in lean_cases:
        artifact = HERE.parent / "evals" / "path" / name
        if not artifact.exists() or not claim.exists():
            print(f"  ----  {name}: fixture missing, not run")
            continue
        # Deliberately relative: that is the shape that silently disabled one.
        rel = artifact.relative_to(Path.cwd()) if str(artifact).startswith(str(Path.cwd())) \
            else artifact
        code, _ = run([sys.executable, str(HERE / "gates" / gate), str(rel),
                       "--claim", str(claim)])
        hit = code == want
        print(f"  {'ok  ' if hit else 'MISS'}  {name}: {why}")
        if not hit:
            failures.append(f"{name} through {gate}: wanted exit {want}, got {code}")
    if not ok:
        failures.append("placeholder.lean was not rejected")

    if failures:
        print(f"\nSELF-TEST: FAIL — {len(failures)}")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nSELF-TEST: PASS — the adapter demonstrably rejects bad input")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--artifact")
    ap.add_argument("--claim")
    ap.add_argument("--tier", choices=sorted(TIERS))
    ap.add_argument("--full-build", action="store_true")
    ap.add_argument("--judges", help="JSON list of independent fidelity verdicts. Usually "
                    "unnecessary: the frozen claim's `fidelity_judgements` is the normal route, "
                    "and being frozen means they cannot be added later to rescue a failing run.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.artifact and args.claim and args.tier):
        ap.error("--artifact, --claim and --tier are required (or use --self-test)")

    artifact, claim_path = Path(args.artifact), Path(args.claim)
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        artifact.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # The claim goes to the probe. Whether the kernel tier needs a LIBRARY is a
    # property of the claim — a target citing no external results needs the
    # kernel and not Mathlib — and asking without it made the adapter refuse to
    # run a tier that would have worked, understating what the run could
    # establish. That is the same class of error as overstating, facing the
    # other way, and it is the quieter one.
    code, probe = run([sys.executable, str(HERE / "availability.py"),
                       "--tier", args.tier, "--claim", str(args.claim), "--json"])
    toolchain = ""
    if code == 3:
        detail = json.loads(probe).get(args.tier, {}) if probe.startswith("{") else {}
        print(json.dumps({
            "verdict": "not_run", "tier": args.tier,
            "failure_class": "toolchain_unavailable",
            "detail": detail.get("detail", "tier unavailable"),
            "note": "A check that could not run is a gap, never a pass, and never support.",
        }, indent=2))
        return 3
    if probe.startswith("{"):
        toolchain = json.loads(probe).get(args.tier, {}).get("detail", "")

    gates = run_gates(artifact, claim_path, args.tier, args.judges)
    tier_result = run_tier(args.tier, artifact, claim_path, args.full_build)
    receipt = build_receipt(args.tier, artifact, claim, tier_result, gates, toolchain)

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"TIER {args.tier}: {receipt['verdict'].upper()} "
              f"(ceiling {receipt['max_status']})")
        for gate in gates:
            print(f"  gate {gate['gate']:<24} {gate['verdict']}")
        if receipt.get("failure_class"):
            print(f"  failure class: {receipt['failure_class']}")
    # `incomplete` and `fail` both exit 1 — neither is admissible — but they are
    # reported separately, because a check that found something and a check that
    # never ran are different facts about the artifact.
    return {"pass": 0, "not_run": 3, "error": 2}.get(receipt["verdict"], 1)


if __name__ == "__main__":
    sys.exit(main())
