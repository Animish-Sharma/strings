#!/usr/bin/env python3
"""Archival verification adapter — the pack's entry point.

Implements the frame's adapter signature and calling convention:

    check.py --artifact <dossier.json> --claim <claim.json> --tier <name> --json

The artifact is a DOSSIER: the claim's sources, their derivation chains, the
archives searched, and the transformations the wording passed through. It is not
an essay.

Two tiers, and the second is where the field's one hard result lives:

    structural      dossier shape, dating, chains terminate     SKETCH
    triangulation   collapse the citation graph to origins      CHECKED_BOUNDED  adversarial

**This pack never reaches VERIFIED.** A surviving document establishes that
something was written. That it happened is a further claim, and no quantity of
documents closes that gap — which is why the ceiling is a property of the field
rather than a caution about this implementation.

Usage:
    check.py --artifact <dossier.json> --claim <claim.json> --tier <name> [--json]
    check.py --self-test

Exit: 0 pass, 1 fail, 2 error, 3 tier unavailable or not run.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archlib as al  # noqa: E402

TIERS = {
    "structural": {"max_status": "SKETCH", "adversarial": False},
    "triangulation": {"max_status": "CHECKED_BOUNDED", "adversarial": True},
}

GATES_BY_TIER = {
    "structural": ["dating-consistency", "scope-language", "survivorship"],
    "triangulation": ["dating-consistency", "scope-language", "survivorship",
                      "transmission-chain", "interest-audit"],
}

GATE_SCRIPTS = {
    "dating-consistency": "dating_consistency.py",
    "scope-language": "scope_language.py",
    "survivorship": "survivorship.py",
    "transmission-chain": "transmission_chain.py",
    "interest-audit": "interest_audit.py",
}


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def run_gates(artifact: Path, claim_path: Path, tier: str) -> list[dict]:
    results = []
    for name in GATES_BY_TIER[tier]:
        code, output = run([sys.executable, str(HERE / "gates" / GATE_SCRIPTS[name]),
                            str(artifact), "--claim", str(claim_path)])
        results.append({
            "gate": name,
            "verdict": ("pass" if code == 0 else "error" if code == 2
                        else "not_run" if code == 3 else "fail"),
            "detail": output.splitlines()[-1] if output else "",
        })
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--artifact"); ap.add_argument("--claim")
    ap.add_argument("--tier", choices=sorted(TIERS))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.artifact and args.claim and args.tier):
        ap.error("--artifact, --claim and --tier are required unless --self-test")

    artifact, claim_path = Path(args.artifact), Path(args.claim)
    try:
        claim = al.read_json(claim_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)})); return 2

    script = HERE / "tiers" / f"{args.tier}.py"
    cmd = [sys.executable, str(script), str(artifact), "--claim", str(claim_path)]
    if args.tier == "structural":
        cmd.append("--json")
    code, out = run(cmd)
    try:
        tier_result = json.loads(out)
    except json.JSONDecodeError:
        tier_result = {"verdict": "error", "log_excerpt": out[:2000]}

    gates = run_gates(artifact, claim_path, args.tier)
    tier_pass = tier_result.get("verdict") == "pass"
    gates_ok = all(g["verdict"] in {"pass", "not_run"} for g in gates)
    verdict = ("not_run" if tier_result.get("verdict") == "not_run"
               else "pass" if tier_pass and gates_ok else "fail")

    adversarial = TIERS[args.tier]["adversarial"]
    refute = tier_result.get("refute_attempt") or {
        "gate_name": "cascade-collapse",
        "discharged_by": "adversarial_tier" if adversarial else "not_discharged",
        "outcome": "not_run",
    }
    if not adversarial:
        refute["note"] = ("the structural tier only checks shape; the cascade collapse is still "
                          "owed and is discharged at the triangulation tier")

    receipt = al.receipt(
        args.tier, claim, artifact, verdict,
        al.weakest(tier_result.get("max_status", TIERS[args.tier]["max_status"]),
                   TIERS[args.tier]["max_status"]),
        supports_status=(al.weakest(tier_result.get("max_status", "CONJECTURE"),
                                    TIERS[args.tier]["max_status"])
                         if verdict == "pass" else None),
        adversarial=adversarial, refute_attempt=refute, gates=gates,
        failed_gates=[g["gate"] for g in gates if g["verdict"] in {"fail", "error"}],
        independence=tier_result.get("independence", {}),
        failure_class=tier_result.get("failure_class"),
        problems=tier_result.get("problems", []), notes=tier_result.get("notes", []),
    )

    if args.json:
        print(json.dumps(receipt, indent=2, default=str))
    else:
        print(f"{receipt['verdict'].upper()}  tier={args.tier}  ceiling={receipt['max_status']}")
        for g in gates:
            print(f"  [{g['verdict']:<7}] {g['gate']}  {g['detail'][:90]}")
        for p in receipt.get("problems", [])[:6]:
            print(f"  - {p}")
    return {"pass": 0, "fail": 1, "error": 2, "not_run": 3}.get(receipt["verdict"], 2)


def self_test() -> int:
    controls = al.read_json(HERE / "negative_control" / "controls.json")
    failures = []
    print("Known-bad dossiers — each must be REJECTED:\n")
    for case in controls["reject"]:
        code, _ = run([sys.executable, __file__, "--artifact",
                       str(HERE / "negative_control" / case["dossier"]),
                       "--claim", str(HERE / "negative_control" / case["claim"]),
                       "--tier", case["tier"], "--json"])
        ok = code == 1
        print(f"  {'ok  ' if ok else 'MISS'}  {case['dossier']:<34} {case['why']}")
        if not ok:
            failures.append(f"{case['dossier']} was not rejected (exit {code})")
    print("\nThe good dossier — must PASS:\n")
    for case in controls["accept"]:
        code, out = run([sys.executable, __file__, "--artifact",
                         str(HERE / "negative_control" / case["dossier"]),
                         "--claim", str(HERE / "negative_control" / case["claim"]),
                         "--tier", case["tier"], "--json"])
        ok = code == 0
        print(f"  {'ok  ' if ok else 'MISS'}  {case['dossier']:<34} {case['why']}")
        if not ok:
            failures.append(f"{case['dossier']} did not pass: {out[:400]}")
    if failures:
        print(f"\nSELF-TEST: FAIL — {len(failures)}")
        for f in failures: print(f"  {f}")
        return 1
    print(f"\nSELF-TEST: PASS — {len(controls['reject'])} rejected, {len(controls['accept'])} accepted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
