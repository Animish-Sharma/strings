#!/usr/bin/env python3
"""Outcome evals for the bio pack.

Every case asserts on what the adapter CONCLUDED — verdict, ceiling, which gate
blocked — and never on which code path it took. An eval that asserts on
mechanism keeps passing after the mechanism stops being the right one, which is
the failure mode that makes a suite feel safe while it decays.

Two things this suite is built to catch that a self-test cannot:

1. **Over-rejection.** `within_screen_is_legitimate` and
   `same_data_as_population_claim_is_rejected` run against the SAME metadata
   table with the same numbers. One must pass and one must be rejected, and the
   only difference between them is the claim class. If both fail, the pack has
   become a machine for saying no, and a check that always refuses carries no
   information.

2. **Ordering.** The leakage case must be blocked by `leakage-audit` rather than
   by a metric gate. A leaked split makes every downstream number a measurement
   of something else, so being caught late is being caught for the wrong reason.

Usage:  run_evals.py [--case <id>] [--verbose]
Exit:   0 all cases behaved as specified, 1 otherwise
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
FIXTURES = HERE / "fixtures"
CHECK = PACK / "scripts" / "check.py"


def run_case(case: dict) -> tuple[bool, list[str], dict]:
    cmd = [sys.executable, str(CHECK),
           "--artifact", str(FIXTURES / case["bundle"]),
           "--claim", str(FIXTURES / case["claim"]),
           "--tier", case["tier"], "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    try:
        receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, [f"adapter produced no receipt: {(proc.stdout + proc.stderr)[:300]}"], {}

    problems = []
    verdict = receipt.get("verdict")
    if verdict != case["expect_verdict"]:
        problems.append(f"verdict {verdict!r}, expected {case['expect_verdict']!r}")

    if "expect_ceiling" in case and receipt.get("max_status") != case["expect_ceiling"]:
        problems.append(f"ceiling {receipt.get('max_status')!r}, "
                        f"expected {case['expect_ceiling']!r}")

    if "expect_refinement" in case and receipt.get("status_refinement") != case["expect_refinement"]:
        problems.append(f"refinement {receipt.get('status_refinement')!r}, "
                        f"expected {case['expect_refinement']!r}")

    if "expect_failed_gate" in case:
        failed = receipt.get("failed_gates") or []
        if case["expect_failed_gate"] not in failed:
            problems.append(
                f"expected gate {case['expect_failed_gate']!r} to block; blocked: {failed or 'none'}"
                + ("  (right answer, wrong reason)" if verdict == case["expect_verdict"] else ""))

    if "expect_failure_contains" in case:
        text = json.dumps(receipt.get("problems", [])) + json.dumps(
            [g.get("detail", "") for g in receipt.get("gates", [])])
        if case["expect_failure_contains"].lower() not in text.lower():
            problems.append(f"no failure mentions {case['expect_failure_contains']!r}; "
                            "the verdict may be right for the wrong reason")

    if verdict != "pass" and receipt.get("supports_status") is not None:
        problems.append(
            f"verdict is {verdict!r} but supports_status is "
            f"{receipt['supports_status']!r}; a check that did not pass supports nothing")

    if receipt.get("max_status") == "VERIFIED" or receipt.get("supports_status") == "VERIFIED":
        problems.append("VERIFIED appeared in a bio receipt; this pack must never reach it")

    return not problems, problems, receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    cases = [c for c in spec["cases"] if not args.case or c["id"] == args.case]
    if not cases:
        print(f"no case named {args.case!r}", file=sys.stderr)
        return 1

    failed = 0
    for case in cases:
        ok, problems, receipt = run_case(case)
        print(f"  {'ok  ' if ok else 'FAIL'}  {case['id']}")
        print(f"          {case['why']}")
        if args.verbose and receipt:
            print(f"          verdict={receipt.get('verdict')} "
                  f"ceiling={receipt.get('max_status')} "
                  f"supports={receipt.get('supports_status')} "
                  f"blocked={receipt.get('failed_gates')}")
        for problem in problems:
            print(f"          -> {problem}")
        failed += 0 if ok else 1

    print("\n" + "=" * 60)
    print(f"  {len(cases) - failed}/{len(cases)} cases behaved as specified")
    if failed:
        print("\n  A failing eval is information about the pack, not about the eval. Read the "
              "difference before changing either.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
