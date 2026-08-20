#!/usr/bin/env python3
"""Bio verification adapter — the pack's entry point.

Implements the frame's adapter signature:

    (candidate artifact, claim, tier) -> (pass/fail, receipt)

The artifact here is an *audit bundle*: the frozen claim's evidence, its pinned
sources, the analysis inputs, and the ledgers, in one file. It is not a report.
Nothing in it is taken at its word — the tiers recompute what can be recomputed
and refuse the rest.

Three tiers, and the ceiling is the point:

    structural    bundle shape, freeze, graph connectivity   SKETCH
    executable    recomputed effect + permutation null       CHECKED_BOUNDED  adversarial
    replication   independent source, separately pinned      CHECKED_BOUNDED  adversarial
                  (grants the CHECKED_REPRODUCED refinement)

The denominator analysis — which unit the design can speak about — is a blocking
GATE rather than a tier, because it can only demote. A clean design with no
results is not evidence of anything, and a tier is a thing whose pass supports a
status.

**This pack never reaches VERIFIED, at any tier, under any evidence.** That is
not caution, it is what the status means. VERIFIED is for a claim checked
against something that cannot be argued with, about the general statement.
Empirical support is always support *for the frozen dataset, context, and
analysis*; calling it VERIFIED would erase the distinction the vocabulary exists
to draw, and would put a Perturb-seq result and a kernel-checked identity in the
same box.

Gates are scoped to the tier's ceiling. Demanding a full confounder sweep before
a structural check is theatre; skipping it before a CHECKED_BOUNDED claim is
negligence.

Usage:
    check.py --artifact <bundle.json> --claim <claim.json> --tier <name> [--json]
    check.py --artifact <bundle.json> --claim <claim.json> --tier replication \\
             --replicate <second_bundle.json>
    check.py --self-test        run the negative controls; each must be rejected

Exit: 0 pass, 1 fail, 2 error, 3 tier unavailable or not run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl  # noqa: E402

TIERS = {
    "structural": {"max_status": "SKETCH", "adversarial": False},
    "executable": {"max_status": "CHECKED_BOUNDED", "adversarial": True},
    "replication": {"max_status": "CHECKED_BOUNDED", "adversarial": True},
}

# Which gates guard which ceiling. Read this as: what would have to be true for
# a claim to deserve the status this tier can grant.
GATES_BY_TIER = {
    "structural": ["context-protection", "provenance-trace", "source-capability",
                   "scope-language", "denominator"],
    "executable": ["context-protection", "provenance-trace", "source-capability",
                   "scope-language", "denominator", "contradiction-ledger",
                   "confounder-sweep", "statistical-audit", "leakage-audit",
                   "baseline-gate", "metric-panel"],
    "replication": ["context-protection", "provenance-trace", "source-capability",
                    "scope-language", "denominator", "contradiction-ledger",
                    "confounder-sweep", "statistical-audit", "leakage-audit",
                    "baseline-gate", "metric-panel"],
}

GATE_SCRIPTS = {
    "denominator": "denominator_gate.py",
    "source-capability": "source_capability.py",
    "context-protection": "context_protection.py",
    "provenance-trace": "provenance_trace.py",
    "scope-language": "scope_language.py",
    "contradiction-ledger": "contradiction_ledger.py",
    "confounder-sweep": "confounder_sweep.py",
    "statistical-audit": "statistical_audit.py",
    "leakage-audit": "leakage_audit.py",
    "baseline-gate": "baseline_gate.py",
    "metric-panel": "metric_panel.py",
}


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def run_gates(artifact: Path, claim_path: Path, tier: str) -> list[dict]:
    results = []
    for name in GATES_BY_TIER[tier]:
        code, output = run([sys.executable, str(HERE / "gates" / GATE_SCRIPTS[name]),
                            str(artifact), "--claim", str(claim_path)])
        entry = {}
        if name == "denominator":
            # This gate reports the ceiling the DESIGN supports, which the
            # receipt has to carry: a passing tier on an underpowered design
            # still cannot reach past what the design can speak about.
            try:
                payload = json.loads(output)
                entry = {"design_ceiling": payload.get("max_status"),
                         "design_refinement": payload.get("refinement"),
                         "claim_class": payload.get("claim_class"),
                         "flags": payload.get("flags", []),
                         "upstream_units": payload.get("upstream_units"),
                         "design_effect": payload.get("design_effect"),
                         "experimental_unit": payload.get("experimental_unit")}
                output = "; ".join(payload.get("problems") or payload.get("notes") or
                                   [f"design supports {payload.get('max_status')}"])
            except json.JSONDecodeError:
                pass
        results.append({
            "gate": name,
            **entry,
            # 3 is NOT_RUN — a gap. It is never a pass, and the receipt keeps the
            # two distinguishable so a skipped check cannot read as a cleared one.
            "verdict": ("pass" if code == 0 else "error" if code == 2
                        else "not_run" if code == 3 else "fail"),
            "detail": output.splitlines()[0] if output else "",
        })
    return results


def run_tier(tier: str, artifact: Path, claim_path: Path, replicate: str | None) -> dict:
    script = HERE / "tiers" / f"{tier}.py"
    cmd = [sys.executable, str(script), str(artifact), "--claim", str(claim_path)]
    if tier == "structural":
        cmd.append("--json")
    if tier == "replication":
        if not replicate:
            return {"verdict": "not_run", "problems": [
                "the replication tier needs --replicate <second bundle>. Replication is a second "
                "source, not a second run"]}
        cmd = [sys.executable, str(script), str(artifact), "--replicate", replicate,
               "--claim", str(claim_path)]
    code, out = run(cmd)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        payload = {"verdict": "error", "log_excerpt": out[:2000]}
    payload["_exit"] = code
    return payload


def build_receipt(tier: str, artifact: Path, claim: dict, tier_result: dict,
                  gates: list[dict]) -> dict:
    tier_pass = tier_result.get("verdict") == "pass"
    gates_pass = all(g["verdict"] in {"pass", "not_run"} for g in gates)
    blocking_not_run = [g["gate"] for g in gates if g["verdict"] == "not_run"]
    failed = [g["gate"] for g in gates if g["verdict"] in {"fail", "error"}]

    if tier_result.get("verdict") == "not_run":
        verdict = "not_run"
    elif tier_pass and gates_pass:
        verdict = "pass"
    else:
        verdict = "fail"

    # Two different things, kept apart because conflating them is how a failed
    # check gets read as a weak pass. `max_status` is structural: the strongest
    # status a pass at this tier on this design could EVER support.
    # `supports_status` is the outcome: what this receipt actually establishes,
    # which is nothing at all unless the verdict is a pass.
    supported = tier_result.get("max_status", TIERS[tier]["max_status"])
    design_ceiling = next((g.get("design_ceiling") for g in gates
                           if g["gate"] == "denominator" and g.get("design_ceiling")), None)
    ceiling = bl.weakest(*[s for s in (supported, TIERS[tier]["max_status"], bl.PACK_CEILING,
                                       design_ceiling) if s])

    adversarial = TIERS[tier]["adversarial"]
    refute = tier_result.get("refute_attempt") or {
        "gate_name": "permutation-null",
        "discharged_by": "adversarial_tier" if adversarial else "not_discharged",
        "outcome": "not_run",
    }
    if not adversarial:
        refute["note"] = (
            f"the {tier} tier is not adversarial: it can demote a claim and cannot confirm one. "
            "The refute-attempt gate is still owed and is discharged at the executable tier")

    return bl.receipt(
        tier, claim, artifact,
        verdict if verdict != "pass" else "pass",
        ceiling,
        supports_status=(ceiling if verdict == "pass" else None),
        adversarial=adversarial,
        refute_attempt=refute,
        gates=gates,
        failed_gates=failed,
        gates_not_run=blocking_not_run,
        claim_class=claim.get("claim_class"),
        status_refinement=(tier_result.get("status_refinement")
                           or next((g.get("design_refinement") for g in gates
                                    if g["gate"] == "denominator" and g.get("design_refinement")),
                                   None)),
        analysis=tier_result.get("recomputed") or tier_result.get("agreement") or {},
        design=next(({"upstream_units": g.get("upstream_units"),
                      "experimental_unit": g.get("experimental_unit"),
                      "design_effect": g.get("design_effect"),
                      "design_ceiling": g.get("design_ceiling"),
                      "flags": g.get("flags")} for g in gates if g["gate"] == "denominator"), {}),
        failure_class=tier_result.get("failure_class"),
        problems=tier_result.get("problems", []),
        notes=tier_result.get("notes", []),
    )


def self_test() -> int:
    """Every negative control must be rejected, and the positive control must pass.

    This is what turns `adversarial: true` in the manifest from a self-report by
    the party being checked into something with a test behind it. A backend
    nothing has ever failed is unaudited, not trustworthy.
    """
    control_dir = HERE / "negative_control"
    manifest = bl.read_json(control_dir / "controls.json")
    failures = []

    print("Negative controls — each must be REJECTED:\n")
    for case in manifest["reject"]:
        bundle = control_dir / case["bundle"]
        claim = control_dir / case["claim"]
        code, out = run([sys.executable, __file__, "--artifact", str(bundle),
                         "--claim", str(claim), "--tier", case["tier"], "--json"])
        rejected = code == 1
        print(f"  {'ok  ' if rejected else 'MISS'}  {case['bundle']:<34} {case['why']}")
        if not rejected:
            failures.append(f"{case['bundle']} was not rejected at tier {case['tier']} (exit {code})")

    for case in manifest.get("reject_replication", []):
        code, _ = run([sys.executable, __file__,
                       "--artifact", str(control_dir / case["primary"]),
                       "--replicate", str(control_dir / case["replicate"]),
                       "--claim", str(control_dir / case["claim"]),
                       "--tier", "replication", "--json"])
        rejected = code == 1
        print(f"  {'ok  ' if rejected else 'MISS'}  {case['replicate']:<34} {case['why']}")
        if not rejected:
            failures.append(f"{case['replicate']} was accepted as a replication (exit {code})")

    print("\nPositive control — must PASS:\n")
    for case in manifest["accept"]:
        bundle = control_dir / case["bundle"]
        claim = control_dir / case["claim"]
        code, out = run([sys.executable, __file__, "--artifact", str(bundle),
                         "--claim", str(claim), "--tier", case["tier"], "--json"])
        ok = code == 0
        print(f"  {'ok  ' if ok else 'MISS'}  {case['bundle']:<34} {case['why']}")
        if not ok:
            try:
                receipt = json.loads(out)
                detail = receipt.get("problems") or receipt.get("failed_gates")
            except json.JSONDecodeError:
                detail = out[:400]
            failures.append(f"{case['bundle']} did not pass at tier {case['tier']}: {detail}")

    if failures:
        print(f"\nSELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"\nSELF-TEST: PASS — "
          f"{len(manifest['reject']) + len(manifest.get('reject_replication', []))} rejected, "
          f"{len(manifest['accept'])} accepted")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--artifact")
    ap.add_argument("--claim")
    ap.add_argument("--tier", choices=sorted(TIERS))
    ap.add_argument("--replicate", help="second bundle, for the replication tier")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.artifact and args.claim and args.tier):
        ap.error("--artifact, --claim and --tier are required unless --self-test")

    artifact = Path(args.artifact)
    claim_path = Path(args.claim)
    try:
        claim = bl.read_json(claim_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)}))
        return 2

    probe_cmd = [sys.executable, str(HERE / "availability.py"),
                 "--tier", args.tier, "--bundle", str(artifact)]
    if args.replicate:
        probe_cmd += ["--replicate", args.replicate]
    available = json.loads(run(probe_cmd)[1])
    if not available.get("available"):
        print(json.dumps({
            "schema": "bio-receipt-v1", "tier": args.tier, "verdict": "not_run",
            "max_status": "CONJECTURE",
            "detail": available.get("detail"),
            "note": "A tier that could not run has not passed. Say NOT_RUN and mean it",
        }, indent=2))
        return 3

    tier_result = run_tier(args.tier, artifact, claim_path, args.replicate)
    gates = run_gates(artifact, claim_path, args.tier)
    receipt = build_receipt(args.tier, artifact, claim, tier_result, gates)

    if args.json:
        print(json.dumps(receipt, indent=2, default=str))
    else:
        print(f"{receipt['verdict'].upper()}  tier={args.tier}  "
              f"ceiling={receipt['max_status']}  "
              f"supports={receipt.get('supports_status') or 'nothing'}  "
              f"class={receipt.get('claim_class')}")
        for gate in gates:
            print(f"  [{gate['verdict']:<7}] {gate['gate']}  {gate['detail'][:90]}")
        for problem in receipt.get("problems", [])[:10]:
            print(f"  - {problem}")

    return {"pass": 0, "fail": 1, "error": 2, "not_run": 3}.get(receipt["verdict"], 2)


if __name__ == "__main__":
    sys.exit(main())
