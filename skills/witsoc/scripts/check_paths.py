#!/usr/bin/env python3
"""Path checks — walk a whole campaign, not a component.

Four suites were green and twenty of twenty planted regressions were caught
while two packs were structurally incapable of admitting anything, a placeholder
could reach a backend as a target statement, and the documented repair loop
could not execute. None of that was a missing check. Each defect lived in a
SEAM: a receipt field one side never wrote and the other read as absent, a hole
the renderer counted as filled, a store the retry could not reach. A component
suite cannot see a seam, because both components are behaving.

So each case starts at a frozen claim and ends at an admission decision, and
asserts the outcome. Cases are declared BY THE PACK, in
`<pack>/evals/path/cases.json`, and run here — the frame supplies the walk and
learns nothing about the field. A case names the environment variables it needs
in `requires`; the frame checks they are set and resolve, and never learns what
they mean. A case whose requirements are absent is NOT_RUN, and NOT_RUN is never
counted as a pass.

Pairs are the point. A suite of things that must be refused proves only that the
gate can say no; each refusal here is paired with the artifact that must be
admitted, differing only in what the seam is supposed to notice.

Usage:  check_paths.py [--pack NAME] [--workers N] [--json]
Exit:   0 every case that ran behaved as specified, 1 otherwise, 2 IO.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN = HERE / "campaign.py"


def packs() -> list[str]:
    return sorted(p.name for p in (ROOT / "domains").iterdir()
                  if (p / "evals" / "path" / "cases.json").exists())


def outcome_of(text: str) -> str:
    for line in text.splitlines():
        if "OUTCOME:" in line:
            return line.split("OUTCOME:", 1)[1].strip().split()[0]
    return "NO_OUTCOME"


def unmet(case: dict) -> list[str]:
    out = []
    for name in case.get("requires") or []:
        value = os.environ.get(name)
        if not value or not Path(value).exists():
            out.append(name)
    return out


def walk(pack: str, case: dict) -> dict:
    base = ROOT / "domains" / pack
    missing = unmet(case)
    if missing:
        return {"pack": pack, "case": case["name"], "verdict": "NOT_RUN",
                "why": "needs " + ", ".join(missing)}
    with tempfile.TemporaryDirectory(prefix="paths_") as td:
        review = None
        if case.get("review_tier"):
            # Two steps, because that is what an independent review IS: produce
            # first, then hand the artifact to a different actor running a
            # different method family. A case that skipped the first step would
            # be reviewing nothing.
            first = subprocess.run(
                [sys.executable, str(CAMPAIGN), "run",
                 "--claim", str(base / case["claim"]),
                 "--artifact", str(base / case["artifact"]),
                 "--tier", case["tier"], "--domain", pack,
                 "--workdir", str(Path(td) / "produce"),
                 "--producer-actor", "path-producer",
                 "--admitter-actor", "path-admitter", "--write"],
                capture_output=True, text=True, timeout=2400)
            result = Path(td) / "produce" / "result.json"
            if result.exists():
                review = Path(td) / "review.json"
                subprocess.run(
                    [sys.executable, str(HERE / "review_harness.py"),
                     "--claim", str(base / case["claim"]),
                     "--artifact", str(base / case["artifact"]),
                     "--domain", pack, "--tier", case["review_tier"],
                     "--result", str(result), "--reviewer-actor", "path-reviewer",
                     "--out", str(review)],
                    capture_output=True, text=True, timeout=2400)
                if not review.exists():
                    return {"pack": pack, "case": case["name"], "verdict": "FAIL",
                            "got": "NO_REVIEW", "want": case["expect"],
                            "why": "the reviewing tier produced no review packet"}
            else:
                return {"pack": pack, "case": case["name"], "verdict": "FAIL",
                        "got": outcome_of(first.stdout + first.stderr),
                        "want": case["expect"],
                        "why": "production did not emit a result to review"}
        cmd = [sys.executable, str(CAMPAIGN), "run",
               "--claim", str(base / case["claim"]),
               "--artifact", str(base / case["artifact"]),
               "--tier", case["tier"], "--domain", pack,
               "--workdir", str(Path(td) / "run"),
               "--producer-actor", "path-producer",
               "--admitter-actor", "path-admitter", "--write"]
        if review is not None:
            cmd += ["--review", str(review)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2400)
            out = proc.stdout + proc.stderr
            got = outcome_of(out)
            # A case may pin the STATUS as well as the outcome. ADMITTED alone
            # does not distinguish the top status from the bounded one, and the
            # whole point of a cross-family review is which of the two it is.
            want_status = case.get("expect_status")
            if want_status and got == "ADMITTED":
                granted = next((l for l in out.splitlines() if "granted" in l), "")
                if want_status not in granted:
                    got = f"ADMITTED({granted.strip()[:40]})"
        except (OSError, subprocess.SubprocessError) as exc:
            got = f"ERROR({exc})"
    want = case["expect"]
    return {"pack": pack, "case": case["name"], "verdict": "ok" if got == want else "FAIL",
            "got": got, "want": want, "why": case.get("why", "")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pack")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    jobs = []
    for pack in packs():
        if a.pack and pack != a.pack:
            continue
        try:
            body = json.loads((ROOT / "domains" / pack / "evals" / "path" /
                               "cases.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {pack}: {exc}", file=sys.stderr)
            return 2
        jobs += [(pack, c) for c in body.get("cases", [])]

    if not jobs:
        print("PATHS: no cases declared")
        return 0
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        rows = list(pool.map(lambda j: walk(*j), jobs))

    ran = sum(1 for r in rows if r["verdict"] != "NOT_RUN")
    failures = sum(1 for r in rows if r["verdict"] == "FAIL")
    for r in rows:
        mark = {"ok": "ok  ", "FAIL": "FAIL", "NOT_RUN": "----"}[r["verdict"]]
        tail = (r.get("got", "") if r["verdict"] != "NOT_RUN" else r["why"])
        print(f"  {mark} {r['pack']:<9} {r['case']:<34} {tail}"
              + (f"   (wanted {r['want']})" if r["verdict"] == "FAIL" else ""))
    print()
    if failures:
        print(f"PATHS: FAIL — {failures} of {ran} case(s) that ran ended somewhere else")
        print("  A path failure is a seam. Every component upstream of it can be green "
              "and the campaign still end in the wrong place.")
    else:
        print(f"PATHS: PASS — {ran} of {len(rows)} declared case(s) ran; "
              f"{len(rows) - ran} NOT_RUN, counted as neither")
    # A machine-readable count for the suite's tally. The suite used to parse
    # this out of the prose above and matched the wrong number, undercounting
    # in the direction that makes a run look more complete than it was.
    if len(rows) - ran:
        print(f"NOT_RUN_COUNT={len(rows) - ran}")
    if a.json:
        print(json.dumps({"schema": "witsoc.paths.v1", "rows": rows,
                          "ran": ran, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
