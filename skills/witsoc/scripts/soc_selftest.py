#!/usr/bin/env python3
"""Adversarial self-test for working memory.

Working memory is the one component in the frame that is ALLOWED to be wrong,
which makes its boundary the only thing protecting it. Every case below tries to
cross that boundary or to defeat the gate that makes the memory worth keeping.

Usage:  soc_selftest.py [--verbose]
Exit:   0 every case behaved as specified, 1 otherwise
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
SOC = HERE / "soc_memory.py"
TARGET = hashlib.sha256(b"soc self-test target").hexdigest()


def soc(*args: str, expect: int | None = None) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SOC), *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        path = tmp / "soc.json"
        soc("init", "--out", str(path), "--target", TARGET, "--goal", "the self-test goal")

        cases = []

        # 1. a tier above CONJECTURE with nothing behind it
        code, out = soc("insight", "--soc", str(path), "--text",
                        "this is definitely true", "--tier", "VERIFIED")
        cases.append(("a tier above CONJECTURE with no evidence", code == 1,
                      "the tier is a claim about evidence; one with nothing behind it is "
                      "laundering"))

        # 2. the same, with evidence, is allowed — the gate must not just refuse
        code, out = soc("insight", "--soc", str(path), "--text",
                        "this is definitely true", "--tier", "CHECKED_BOUNDED",
                        "--evidence", "receipt:abc123")
        cases.append(("the same insight WITH evidence is recorded", code == 0,
                      "a memory that refuses everything holds nothing"))

        # 3. a failure with no revival condition is recorded AND flagged
        code, out = soc("failure", "--soc", str(path), "--method", "direct-attack",
                        "--statement", "the principal obstruction yields to a direct argument",
                        "--blocker", "the argument does not close the final case",
                        "--do-not-repeat", "the same direct argument")
        cases.append(("a failure with no revival is recorded and flagged", 
                      code == 0 and "closed forever" in out,
                      "a route closed with no revival condition is closed forever, which is "
                      "rarely what anyone meant"))

        # 4. the repeat gate fires on the same method and statement
        code, out = soc("check", "--soc", str(path), "--method", "direct-attack",
                        "--statement", "the principal obstruction yields to a direct argument")
        cases.append(("the repeat gate fires on a recorded failure", code == 1,
                      "this is the check that stops the twentieth attempt repeating the first"))

        # 5. and does NOT fire on a different method
        code, out = soc("check", "--soc", str(path), "--method", "contradiction",
                        "--statement", "the principal obstruction yields to a direct argument")
        cases.append(("it does not fire on a different method", code == 0,
                      "the same statement approached differently is a different attempt, and a "
                      "gate that cannot tell them apart blocks the work it exists to enable"))

        # 6. an invalid write is refused rather than persisted
        broken = json.loads(path.read_text())
        broken["insights"].append({"id": "bad", "text": "no tier at all"})
        (tmp / "broken.json").write_text(json.dumps(broken))
        code, out = soc("consolidate", "--soc", str(tmp / "broken.json"))
        cases.append(("an invalid soc is refused, not written", code == 2,
                      "a store that persists whatever it is handed is a file, not a store"))

        # 7. consolidation reports what it dropped
        for index in range(30):
            soc("insight", "--soc", str(path), "--text",
                f"observation number {index} about the obstruction and its behaviour")
        code, out = soc("consolidate", "--soc", str(path), "--max-insights", "10")
        after = json.loads(path.read_text())
        cases.append(("consolidation caps and says what it dropped",
                      code == 0 and len(after["insights"]) <= 10
                      and bool(after.get("consolidations")),
                      "a memory that compacts silently leaves a reader unable to tell "
                      "forgetting from never-knowing"))

        # 8. the file stays bound to its target
        cases.append(("the memory stays bound to its frozen target",
                      after.get("target_sha256") == TARGET,
                      "an unbound memory drifts onto the next problem and brings its "
                      "conclusions along"))

        print("Boundary and gate cases:\n")
        for label, ok, why in cases:
            print(f"  {'ok  ' if ok else 'MISS'}  {label}")
            print(f"          {why}")
            if not ok:
                failures.append(label)

    print("\n" + "=" * 62)
    if failures:
        print(f"  SOC SELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print(f"  SOC SELF-TEST: PASS — {len(cases)} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
