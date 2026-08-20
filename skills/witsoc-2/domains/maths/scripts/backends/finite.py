#!/usr/bin/env python3
"""Finite enumeration backend.

Deterministic and intentionally exponential. It settles a stated finite instance
and never an asymptotic or infinite statement — the two get conflated constantly,
because "verified for all n up to 10^6" reads like "verified".

Ceiling: CHECKED_BOUNDED, with the bounds recorded on the certificate so a reader
cannot mistake the range for the family.

Usage:  finite.py enumerate --spec <spec.json> [--json]
Exit: 0 no counterexample in range, 1 counterexample, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safe_eval import PredicateError, evaluate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["enumerate"]); ap.add_argument("--spec", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    universe = spec.get("universe")
    size = int(spec.get("size", 1))
    predicate = spec["predicate"]
    if universe is None:
        lo, hi = int(spec.get("lower",0)), int(spec.get("upper",10))
        universe = list(range(lo, hi+1))
    combos = itertools.product(universe, repeat=size)

    checked, witnesses = 0, []
    for combo in combos:
        checked += 1
        try:
            if not evaluate(predicate, {"x": combo, "n": combo[0]}):
                witnesses.append(list(combo))
                if len(witnesses) >= 5: break
        except PredicateError as exc:
            print(f"ERROR: predicate failed on {combo}: {exc}", file=sys.stderr); return 2

    bounds = f"|universe|={len(universe)}, tuples of size {size}"
    out = {"backend":"finite","verdict":"counterexample" if witnesses else "no_counterexample",
           "checked":checked,"bounds":bounds,"exhaustive":not witnesses,
           "witnesses":witnesses,"max_status":"CHECKED_BOUNDED",
           "certificate_sha256":hashlib.sha256((predicate+bounds).encode()).hexdigest(),
           "note":"settles this finite instance only. It is not evidence about the "
                  "asymptotic or infinite statement, however large the range."}
    print(json.dumps(out, indent=2) if a.json else
          (f"FINITE: counterexample {witnesses}" if witnesses else
           f"FINITE: no counterexample over {bounds} ({checked} checked)\n  {out['note']}"))
    return 1 if witnesses else 0
if __name__ == "__main__":
    sys.exit(main())
