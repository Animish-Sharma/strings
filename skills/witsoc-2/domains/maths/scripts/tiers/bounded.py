#!/usr/bin/env python3
"""Bounded tier — exhaustive or randomized search over a stated finite domain.

Adversarial within its range (an exhaustive search genuinely cannot be argued
into a false pass) and permanently capped at CHECKED_BOUNDED, because it
establishes nothing whatsoever outside the range it covered. Those two
properties are independent, which is why the manifest declares them separately.

The bounds and the seed come from the frozen claim, never from the command
line: a failing search must not be rescuable by quietly shrinking the range.

The predicate is supplied by the claim as a Python expression over the loop
variables. It is evaluated with no builtins.

One variable or several. Most interesting small-case questions are about a PAIR
— a graph on n vertices with m edges, a pair of exponents, a value and a modulus
— and a tier that could only write `for n in range(lo, hi)` could not ask them,
so a role told to "check small cases first" had to hand-write a harness and
usually did not. Both forms are accepted:

    "bounded_search": {"variable": "n", "lower": 0, "upper": 50,
                       "predicate": "n*n > n"}

    "bounded_search": {"variables": [{"name": "n", "lower": 1, "upper": 12},
                                     {"name": "k", "lower": 0, "upper": 12}],
                       "predicate": "k > n or comb(n, k) >= 1"}

The product is enumerated in a fixed order, so a counterexample list is
reproducible. `max_instances` (default 2,000,000) bounds the sweep; hitting it
returns UNKNOWN with `exhaustive: false`, never a pass. A budget stop is not a
refutation and it is not a confirmation — it is the search failing to finish,
and the receipt has to say which of the three happened.

Usage:  bounded.py --claim <claim.json> [--json]
Exit:   0 no counterexample in range, 1 counterexample found, 2 error, 3 budget
        exhausted before the range was covered.
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

    predicate = search["predicate"]
    if search.get("variables"):
        axes = [(v["name"], int(v["lower"]), int(v["upper"])) for v in search["variables"]]
    else:
        axes = [(search.get("variable", "n"), int(search["lower"]), int(search["upper"]))]
    for name, lo_, hi_ in axes:
        if hi_ < lo_:
            print(f"ERROR: {name} has upper {hi_} below lower {lo_}; an empty range is not a "
                  "search, and reporting it as a pass would be the worst available outcome",
                  file=sys.stderr)
            return 2
    budget = int(search.get("max_instances", 2_000_000))

    total = 1
    for _name, lo_, hi_ in axes:
        total *= (hi_ - lo_ + 1)

    counterexamples: list = []
    checked = 0
    truncated = total > budget

    def sweep(index: int, bindings: dict) -> str | None:
        """Depth-first over the product. Returns an error string, or None."""
        nonlocal checked
        if checked >= budget:
            return None
        if index == len(axes):
            checked += 1
            try:
                ok = evaluate(predicate, dict(bindings))
            except PredicateError as exc:   # an erroring predicate is not a failing one
                return f"predicate failed at {bindings}: {exc}"
            if not ok:
                counterexamples.append(dict(bindings) if len(axes) > 1
                                       else bindings[axes[0][0]])
            return None
        name, lo_, hi_ = axes[index]
        for value in range(lo_, hi_ + 1):
            bindings[name] = value
            problem = sweep(index + 1, bindings)
            if problem or len(counterexamples) >= 5 or checked >= budget:
                return problem
        return None

    problem = sweep(0, {})
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 2

    bounds = "; ".join(f"{name} in [{lo_}, {hi_}]" for name, lo_, hi_ in axes)
    incomplete = checked < total and not counterexamples
    result = {
        "verdict": ("fail" if counterexamples else "unknown" if incomplete else "pass"),
        "tier": "bounded",
        "max_status": "CHECKED_BOUNDED",
        "bounds": bounds,
        "variables": [name for name, _lo, _hi in axes],
        "exhaustive": not incomplete,
        "checked": checked,
        "range_size": total,
        "budget": budget,
        "counterexamples": counterexamples,
        "predicate_sha256": hashlib.sha256(predicate.encode()).hexdigest(),
        "note": ("Establishes nothing outside the stated bounds. A search that found "
                 "no counterexample is evidence only about the range it covered."
                 if not incomplete else
                 "The budget ran out before the stated range was covered. This is neither a "
                 "pass nor a refutation: the search did not finish, and reporting it as "
                 "either would be a claim nobody checked."),
    }
    if a.json:
        print(json.dumps(result, indent=2))
    elif counterexamples:
        print(f"BOUNDED: COUNTEREXAMPLE — {counterexamples}")
        print(f"  searched {bounds}; the claim is false as stated")
    elif incomplete:
        print(f"BOUNDED: UNKNOWN over {bounds}")
        print(f"  {checked} of {total} instances before the budget of {budget}. {result['note']}")
    else:
        print(f"BOUNDED: PASS over {bounds} ({checked} instances, exhaustive)")
        print(f"  Ceiling CHECKED_BOUNDED. {result['note']}")
    if counterexamples:
        return 1
    return 3 if incomplete else 0

if __name__ == "__main__":
    sys.exit(main())
