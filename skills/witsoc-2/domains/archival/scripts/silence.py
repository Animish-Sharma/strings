#!/usr/bin/env python3
"""The argument from silence, as arithmetic rather than as a paragraph.

The survivorship gate asks an absence claim to state why a record would have
survived had the thing happened. That is the right demand and it accepts prose,
so the answer is a sentence somebody wrote about their own claim — and the
sentence is always available, because every absence claim's author believes the
record would have shown it.

The question has a number in it. If the thing had happened, some class of
document would have recorded it. Documents of that class survive at some rate.
Given how many opportunities there were, the probability that ALL of them
vanished is computable, and that probability is exactly how much the silence is
worth:

    P(no surviving record | it happened) = (1 - r)^n

with `r` the survival-and-cataloguing rate for that class and `n` the number of
independent opportunities to have been recorded. Silence is evidence of absence
only when that number is small. When it is large, the archive is silent about
plenty of things that happened, and the claim is about the archive.

## The rate is a range, not a number

Nobody knows the survival rate of provincial tax registers to three figures. So
this takes an INTERVAL and reports the answer across it, and the verdict is
driven by the pessimistic end — the end most favourable to the thing having
happened unrecorded. A conclusion that holds only at the optimistic end of a
guessed rate is a conclusion about the guess.

## What it will not do

It will not invent a rate. With no `survival_rate` in the dossier it returns
`not_computable`, and the prose survival argument stands as the only support,
which is what the receipt then says. A default rate would be this file inventing
the number the whole exercise exists to make somebody state.

Usage:
    silence.py <dossier.json> --claim <claim.json> [--json]
    silence.py --self-test

Exit: 0 silence is informative, 1 silence is uninformative (the claim is about
      the archive), 2 IO, 3 not computable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archlib as al  # noqa: E402

# Above this, the archive would plausibly be silent anyway and the silence
# carries nothing. Stated rather than tuned: it is the same 1-in-20 convention
# the rest of the world argues about, and the receipt prints the probability so
# a reader can disagree with the threshold rather than with the arithmetic.
UNINFORMATIVE_ABOVE = 0.05


def probability_all_lost(rate: float, opportunities: int) -> float:
    if rate <= 0:
        return 1.0
    if rate >= 1:
        return 0.0 if opportunities > 0 else 1.0
    return (1.0 - rate) ** max(0, opportunities)


def analyse(dossier: dict, claim: dict) -> dict:
    survival = dossier.get("survival_rate") or {}
    low, high = survival.get("low"), survival.get("high")
    opportunities = dossier.get("recording_opportunities")

    if low is None or high is None or opportunities is None:
        return {"verdict": "not_computable",
                "reading": "the dossier states no survival_rate interval and/or no "
                           "recording_opportunities, so the silence cannot be priced. The prose "
                           "survival argument is then the only support there is, and a sentence "
                           "about one's own claim is the weakest thing this pack accepts"}
    try:
        low, high = float(low), float(high)
        opportunities = int(opportunities)
    except (TypeError, ValueError):
        return {"verdict": "not_computable",
                "reading": "survival_rate must be numeric bounds and recording_opportunities an "
                           "integer count"}
    if not (0.0 <= low <= high <= 1.0):
        return {"verdict": "not_computable",
                "reading": f"survival_rate interval [{low}, {high}] is not a rate; expected "
                           "0 <= low <= high <= 1"}

    # The pessimistic end is the LOW rate: fewest documents survive, so silence
    # is easiest to explain without the event. A verdict that needs the high end
    # is a verdict about the guess.
    p_pessimistic = probability_all_lost(low, opportunities)
    p_optimistic = probability_all_lost(high, opportunities)

    informative = p_pessimistic <= UNINFORMATIVE_ABOVE
    only_at_best = (not informative) and p_optimistic <= UNINFORMATIVE_ABOVE

    if informative:
        reading = (f"even at the pessimistic survival rate of {low:.0%}, the chance that all "
                   f"{opportunities} opportunities left no surviving record is "
                   f"{p_pessimistic:.1%}. The silence is evidence")
    elif only_at_best:
        reading = (f"the silence is informative only at the optimistic end: {p_optimistic:.1%} "
                   f"at a {high:.0%} survival rate against {p_pessimistic:.1%} at {low:.0%}. A "
                   "conclusion that needs the favourable end of a guessed rate is a conclusion "
                   "about the guess, and the claim should be worded about the archive")
    else:
        reading = (f"the chance that all {opportunities} opportunities left no surviving record "
                   f"is {p_pessimistic:.1%} even at {low:.0%} survival. The archive is silent "
                   "about plenty of things that happened; this silence is not evidence that "
                   "this one did not")

    return {"verdict": "informative" if informative else "uninformative",
            "survival_rate": {"low": low, "high": high},
            "recording_opportunities": opportunities,
            "p_all_lost_pessimistic": round(p_pessimistic, 6),
            "p_all_lost_optimistic": round(p_optimistic, 6),
            "threshold": UNINFORMATIVE_ABOVE,
            "informative_only_at_optimistic_end": only_at_best,
            "reading": reading}


def self_test() -> int:
    cases, failures = [], 0

    def d(low, high, n):
        return {"survival_rate": {"low": low, "high": high}, "recording_opportunities": n}

    r = analyse(d(0.30, 0.50, 20), {})
    cases.append(("many opportunities and a decent survival rate: silence is evidence",
                  r["verdict"] == "informative", r["reading"]))

    r = analyse(d(0.02, 0.10, 3), {})
    cases.append(("few opportunities and a poor survival rate: silence carries nothing",
                  r["verdict"] == "uninformative", r["reading"]))

    # The case the interval exists for.
    r = analyse(d(0.05, 0.60, 5), {})
    cases.append(("a conclusion that needs the optimistic end is refused and named",
                  r["verdict"] == "uninformative" and r["informative_only_at_optimistic_end"],
                  r["reading"]))

    r = analyse({}, {})
    cases.append(("no rate stated is not_computable — it does not invent one",
                  r["verdict"] == "not_computable", r["reading"]))

    r = analyse({"survival_rate": {"low": 0.9, "high": 0.2}, "recording_opportunities": 5}, {})
    cases.append(("an interval that is not a rate is refused",
                  r["verdict"] == "not_computable", r["reading"]))

    r = analyse(d(0.5, 0.5, 0), {})
    cases.append(("zero opportunities can never make silence informative",
                  r["verdict"] == "uninformative",
                  f"p={r['p_all_lost_pessimistic']} — nothing had a chance to record it"))

    # Monotonicity: more opportunities can only strengthen the argument.
    a = analyse(d(0.1, 0.2, 5))["p_all_lost_pessimistic"] if False else \
        analyse(d(0.1, 0.2, 5), {})["p_all_lost_pessimistic"]
    b = analyse(d(0.1, 0.2, 40), {})["p_all_lost_pessimistic"]
    cases.append(("more opportunities can only strengthen the argument", b < a,
                  f"5 opportunities p={a:.3f}, 40 opportunities p={b:.5f}"))

    print("\n  SILENCE SELF-TEST — the argument from silence, priced\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier", nargs="?")
    ap.add_argument("--claim")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.dossier and args.claim):
        ap.error("a dossier and --claim are required (or --self-test)")
    try:
        dossier, claim = al.read_json(args.dossier), al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = analyse(dossier, claim)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"SILENCE: {result['verdict']}")
        print(f"  {result['reading']}")
    return {"informative": 0, "uninformative": 1, "not_computable": 3}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
