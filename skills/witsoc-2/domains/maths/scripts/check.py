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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    results = []
    for name, cmd in gates:
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
            "detail": output.splitlines()[0] if output else "",
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
        "verdict": verdict,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "max_status": TIERS[tier]["max_status"],
        "refute_attempt": {
            "gate_name": "kernel-recheck",
            "discharged_by": "adversarial_tier" if adversarial else "skeptic_pass",
            "outcome": ("survived" if verdict == "pass"
                        else "not_run" if verdict == "not_run" else "broken"),
        },
        "completeness": {
            "all_obligations_covered": tier == "kernel" and verdict == "pass",
            "concluding_step_covered": tier == "kernel" and verdict == "pass",
            "open_gaps": len(blocking_gaps),
            "rejections": len(blocking_failed) + (0 if tier_pass else 1),
        },
        "supports_status": (TIERS[tier]["max_status"] if verdict == "pass" else None),
        "gaps": [g["gate"] for g in blocking_gaps],
        "not_applicable": [g["gate"] for g in gates if g["verdict"] == "not_applicable"],
        "gates": gates,
        "toolchain": toolchain,
        "axiom_audit": (
            "not_run — requires a kernel pass" if tier != "kernel" or verdict != "pass"
            else "pending: enumerate dependencies and compare against the allowlist"
        ),
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

    placeholder = HERE / "negative_control" / "placeholder.lean"
    placeholder.write_text("theorem t : True := by\n  sorry\n", encoding="utf-8")
    code, _ = run([sys.executable, str(HERE / "gates" / "placeholder_scan.py"), str(placeholder)])
    ok = code == 1
    print(f"\n  {'ok  ' if ok else 'MISS'}  placeholder.lean rejected by placeholder-scan")
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

    code, probe = run([sys.executable, str(HERE / "availability.py"),
                       "--tier", args.tier, "--json"])
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
