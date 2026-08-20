#!/usr/bin/env python3
"""Dialectic — refute instances before spending more on proving.

For any obligation of the form "for all n, P(n)", check small instances first.
The cheapest high-yield move available: a witness at n=4 ends the attempt
immediately, and an exhausted search becomes a real enemy constraint.

Three outcomes, all useful:

  WITNESS_FOUND     the node is REFUTED_INSTANCE. The next action is one-axis
                    STATEMENT REPAIR, never another proof attempt — the
                    statement is false as written and proving it harder will
                    not help.
  SEARCH_EXHAUSTED  bounded negative evidence: "no counterexample below N".
                    That is a publishable enemy constraint, not nothing.
  UNDECIDED         the predicate could not be evaluated. Reported as such.

Usage:
    dialectic.py --claim <claim.json> [--bound 10] [--json]
Exit: 0 exhausted (no witness), 1 witness found, 3 undecided, 2 IO error.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_eval import PredicateError, evaluate  # noqa: E402

DEFAULT_BOUND = 10

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim", required=True); ap.add_argument("--bound", type=int, default=DEFAULT_BOUND)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    spec = claim.get("frozen_conditions", {}).get("bounded_search")
    if not spec:
        out = {"outcome": "UNDECIDED",
               "why": "the claim declares no evaluable predicate; instance refutation "
                      "needs one to check anything"}
        print(json.dumps(out, indent=2) if a.json else f"DIALECTIC: UNDECIDED — {out['why']}")
        return 3

    var, pred = spec.get("variable","n"), spec["predicate"]
    lo = int(spec.get("lower", 0)); hi = min(int(spec.get("upper", a.bound)), lo + a.bound)
    witnesses = []
    for value in range(lo, hi + 1):
        try:
            if not evaluate(pred, {var: value}):
                witnesses.append(value)
        except PredicateError as exc:
            out = {"outcome": "UNDECIDED", "why": f"predicate failed at {var}={value}: {exc}"}
            print(json.dumps(out, indent=2) if a.json else f"DIALECTIC: UNDECIDED — {out['why']}")
            return 3

    if witnesses:
        out = {"outcome": "WITNESS_FOUND", "witnesses": witnesses[:5],
               "node_status": "REFUTED_INSTANCE",
               "next_action": "one-axis STATEMENT REPAIR",
               "why": ("the statement is false as written. Another proof attempt cannot "
                       "succeed and must not be dispatched — repair the statement, or "
                       "add the hypothesis the witness violates."),
               "enemy_constraint": f"any true variant must exclude {var} = {witnesses[:5]}"}
        print(json.dumps(out, indent=2) if a.json else
              f"DIALECTIC: WITNESS at {var}={witnesses[:5]}\n  node -> REFUTED_INSTANCE\n"
              f"  next: {out['next_action']} — {out['why']}")
        return 1

    out = {"outcome": "SEARCH_EXHAUSTED", "searched": f"{var} in [{lo}, {hi}]",
           "enemy_constraint": f"no counterexample with {var} <= {hi}",
           "status_ceiling": "CHECKED_BOUNDED",
           "why": ("bounded negative evidence. It constrains what a counterexample can "
                   "look like, which is real progress — and it is not a proof.")}
    print(json.dumps(out, indent=2) if a.json else
          f"DIALECTIC: no witness in {out['searched']}\n  enemy constraint: {out['enemy_constraint']}\n"
          f"  {out['why']}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
