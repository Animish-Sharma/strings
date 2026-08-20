#!/usr/bin/env python3
"""Outcome evals for the archival pack.

Each case asserts what the adapter CONCLUDED — verdict, ceiling, which gate
blocked — and never which code path it took. An eval that asserts on mechanism
keeps passing after the mechanism stops being the right one, which is how a
suite comes to feel safe while it decays.

The pair worth watching is `two_origins_is_attested` against
`same_sources_as_attested_is_refuted`. Both run over dossiers built from the same
tradition; one passes and one is refuted, and the difference is how many
independent origins the claim asserts against how many survive the collapse. If
both ever pass, the collapse has stopped doing any work and the pack is a
spell-checker for bibliographies.

Usage:  run_evals.py [--case ID] [--verbose]
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
CONTROLS = PACK / "scripts" / "negative_control"


def run_case(case: dict) -> tuple[bool, list[str], dict]:
    proc = subprocess.run(
        [sys.executable, str(PACK / "scripts" / "check.py"),
         "--artifact", str(CONTROLS / case["dossier"]),
         "--claim", str(CONTROLS / case["claim"]),
         "--tier", case["tier"], "--json"], capture_output=True, text=True, timeout=600)
    try:
        receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, [f"no receipt: {(proc.stdout + proc.stderr)[:200]}"], {}

    problems = []
    if receipt.get("verdict") != case["expect_verdict"]:
        problems.append(f"verdict {receipt.get('verdict')!r}, expected {case['expect_verdict']!r}")
    if "expect_ceiling" in case and receipt.get("max_status") != case["expect_ceiling"]:
        problems.append(f"ceiling {receipt.get('max_status')!r}, expected {case['expect_ceiling']!r}")
    if "expect_failed_gate" in case:
        failed = receipt.get("failed_gates") or []
        if case["expect_failed_gate"] not in failed:
            problems.append(f"expected {case['expect_failed_gate']!r} to block; blocked: "
                            f"{failed or 'none'}"
                            + ("  (right answer, wrong reason)"
                               if receipt.get("verdict") == case["expect_verdict"] else ""))
    if "expect_failure_contains" in case:
        blob = json.dumps(receipt.get("problems", [])) + json.dumps(
            [g.get("detail", "") for g in receipt.get("gates", [])])
        if case["expect_failure_contains"].lower() not in blob.lower():
            problems.append(f"no failure mentions {case['expect_failure_contains']!r}; the "
                            "verdict may be right for the wrong reason")
    if receipt.get("verdict") != "pass" and receipt.get("supports_status") is not None:
        problems.append("a check that did not pass reports a supported status")
    if "VERIFIED" in (receipt.get("max_status"), receipt.get("supports_status")):
        problems.append("VERIFIED appeared; documentary evidence cannot reach it")
    return not problems, problems, receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case"); ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    cases = [c for c in spec["cases"] if not args.case or c["id"] == args.case]
    failed = 0
    for case in cases:
        ok, problems, receipt = run_case(case)
        print(f"  {'ok  ' if ok else 'FAIL'}  {case['id']}")
        print(f"          {case['why']}")
        if args.verbose and receipt:
            print(f"          verdict={receipt.get('verdict')} ceiling={receipt.get('max_status')} "
                  f"blocked={receipt.get('failed_gates')}")
        for problem in problems:
            print(f"          -> {problem}")
        failed += 0 if ok else 1

    print("\n" + "=" * 60)
    print(f"  {len(cases) - failed}/{len(cases)} cases behaved as specified")
    if failed:
        print("\n  A failing eval is information about the pack, not about the eval.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
