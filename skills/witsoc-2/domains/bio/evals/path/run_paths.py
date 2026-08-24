#!/usr/bin/env python3
"""Pack-owned path checks — the loop the frame cannot walk for this pack.

`scripts/check_paths.py` walks one campaign and asserts where it ends. The
escalation ladder is not one campaign: it is the SAME obstruction hit more than
once, and it exists so that a repeated failure stops being retried and gets
handed to the role built to attack it.

It never fired. The streak counter lived in the workdir, a workdir is
per-attempt, and so three identical failures in a row each read "1 of 2". A
ladder whose counter resets every rung is a ladder with one rung, and no
component check could see it because a component check runs once.

Usage:  run_paths.py [--json]
Exit:   0 the ladder behaved as specified, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
ROOT = PACK.parent.parent
CAMPAIGN = ROOT / "scripts" / "campaign.py"
REDUCER = ROOT / "scripts" / "reducer.py"


def outcome_of(text: str) -> str:
    for line in text.splitlines():
        if "OUTCOME:" in line:
            return line.split("OUTCOME:", 1)[1].strip().split()[0]
    return "NO_OUTCOME"


def ladder_escalates_on_a_repeat(tmp: Path) -> tuple[str, str]:
    claim = PACK / "evals/path/confounded_claim.json"
    artifact = PACK / "evals/path/confounded_bundle.json"
    state = tmp / "graph.json"
    subprocess.run([sys.executable, str(REDUCER), "init", "--claim", str(claim),
                    "--out", str(state), "--ceiling", "CHECKED_BOUNDED"],
                   capture_output=True, text=True, timeout=600)
    env = dict(os.environ, WITSOC2_SOC_STORE=str(tmp / "memory"))
    seen = []
    for attempt in (1, 2):
        proc = subprocess.run(
            [sys.executable, str(CAMPAIGN), "run", "--claim", str(claim),
             "--artifact", str(artifact), "--tier", "executable", "--domain", "bio",
             "--workdir", str(tmp / f"run{attempt}"), "--state", str(state),
             "--producer-actor", "ladder-producer",
             "--admitter-actor", "ladder-admitter", "--write"],
            capture_output=True, text=True, timeout=1200, env=env)
        seen.append(outcome_of(proc.stdout + proc.stderr))
    return " -> ".join(seen), "FAILED_ATTEMPT -> ESCALATED"


CASES = [("the ladder escalates when the same obstruction repeats",
          ladder_escalates_on_a_repeat)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows, failures = [], 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory(prefix="biopaths_") as td:
            got, want = fn(Path(td))
        ok = got == want
        failures += not ok
        rows.append({"case": name, "verdict": "ok" if ok else "FAIL",
                     "got": got, "want": want})
        print(f"  {'ok  ' if ok else 'FAIL'} {name:<48} {got}"
              + ("" if ok else f"   (wanted {want})"))
    print()
    print(f"BIO PATHS: {'FAIL' if failures else 'PASS'} — {len(rows)} case(s)")
    if a.json:
        print(json.dumps({"schema": "bio.paths.v1", "rows": rows}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
