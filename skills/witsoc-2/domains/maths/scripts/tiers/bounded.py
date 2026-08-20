#!/usr/bin/env python3
"""Bounded tier — exhaustive or randomized search over a stated finite domain.

Adversarial within its range (an exhaustive search genuinely cannot be argued
into a false pass) and permanently capped at CHECKED_BOUNDED, because it
establishes nothing whatsoever outside the range it covered. Those two
properties are independent, which is why the manifest declares them separately.

The bounds and the seed come from the frozen claim, never from the command
line: a failing search must not be rescuable by quietly shrinking the range.

The predicate is supplied by the claim as a Python expression over the loop
variable. It is evaluated with no builtins.

Usage:  bounded.py --claim <claim.json> [--json]
Exit:   0 no counterexample in range, 1 counterexample found, 2 error.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safe_eval import PredicateError, evaluate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    frozen = claim.get("frozen_conditions", {})
    search = frozen.get("bounded_search")
    if not search:
        print("ERROR: claim has no frozen_conditions.bounded_search — bounds must be "
              "frozen before the search runs", file=sys.stderr)
        return 2

    lo, hi = int(search["lower"]), int(search["upper"])
    var = search.get("variable", "n")
    predicate = search["predicate"]

    counterexamples = []
    checked = 0
    for value in range(lo, hi + 1):
        checked += 1
        try:
            ok = evaluate(predicate, {var: value})
        except PredicateError as exc:   # an erroring predicate is not a failing one
            print(f"ERROR: predicate failed at {var}={value}: {exc}", file=sys.stderr)
            return 2
        if not ok:
            counterexamples.append(value)
            if len(counterexamples) >= 5:
                break

    bounds = f"{var} in [{lo}, {hi}]"
    result = {
        "verdict": "fail" if counterexamples else "pass",
        "tier": "bounded",
        "max_status": "CHECKED_BOUNDED",
        "bounds": bounds,
        "exhaustive": True,
        "checked": checked,
        "counterexamples": counterexamples,
        "predicate_sha256": hashlib.sha256(predicate.encode()).hexdigest(),
        "note": ("Establishes nothing outside the stated bounds. A search that found "
                 "no counterexample is evidence only about the range it covered."),
    }
    if a.json:
        print(json.dumps(result, indent=2))
    elif counterexamples:
        print(f"BOUNDED: COUNTEREXAMPLE — {var} = {counterexamples}")
        print(f"  searched {bounds}; the claim is false as stated")
    else:
        print(f"BOUNDED: PASS over {bounds} ({checked} instances, exhaustive)")
        print(f"  Ceiling CHECKED_BOUNDED. {result['note']}")
    return 1 if counterexamples else 0

if __name__ == "__main__":
    sys.exit(main())
