#!/usr/bin/env python3
"""Multiplicity — the pack tests one endpoint; real screens test thousands.

Everything else here audits a single frozen endpoint, which is the right unit
for a claim. But the endpoint usually came out of a screen, and a screen's
selection is part of the claim's provenance whether or not the report mentions
it. An endpoint chosen because it was the most significant of twenty thousand is
a different object from one chosen in advance, and the two are written the same
way.

So this computes what the correction actually buys, over the feature universe
the analysis really tested:

    Benjamini-Hochberg    the standard, and it controls the false DISCOVERY rate
                          across features — not the denominator, which is the
                          error this field makes
    Bonferroni            for comparison; conservative and easy to check by hand
    selection inflation   what the winning p-value looks like once you account
                          for it having been the winner

The last is the one people skip. If the reported endpoint is the minimum of a
screen, then the honest question is not "is this p below alpha" but "how often
does the minimum of N draws from the null fall below it" — and for a large N
the answer is "very often".

**This does not rescue a wrong denominator.** A correction across features and a
correction across units are different corrections, and offering the first for the
second is a demotion trigger in its own right (`doctrine/denominators.md`).

Usage:
    multiplicity.py --p-values <file.json|csv> [--alpha 0.05] [--selected P]
    multiplicity.py --reported-p 0.001 --features 20000 [--alpha 0.05]

Exit: 0 the reported finding survives, 1 it does not, 2 usage/IO
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path


def benjamini_hochberg(pvalues: list[float], alpha: float) -> dict:
    ordered = sorted((p, i) for i, p in enumerate(pvalues))
    n = len(ordered)
    threshold, cutoff = 0.0, 0
    for rank, (p, _) in enumerate(ordered, start=1):
        if p <= alpha * rank / n:
            threshold, cutoff = p, rank
    return {"method": "benjamini-hochberg", "alpha": alpha, "features": n,
            "rejected": cutoff, "largest_rejected_p": threshold,
            "controls": "the expected proportion of false findings AMONG the findings"}


def bonferroni(pvalues: list[float], alpha: float) -> dict:
    n = len(pvalues)
    cut = alpha / n if n else alpha
    return {"method": "bonferroni", "alpha": alpha, "features": n,
            "threshold": cut, "rejected": sum(1 for p in pvalues if p <= cut),
            "controls": "the probability of ANY false finding; conservative by design"}


def selection_inflation(reported: float, features: int, trials: int = 20000) -> dict:
    """How often the minimum of `features` null draws lands below `reported`.

    Closed form is 1 - (1 - p)^N; the simulation is here because it is the same
    number and nobody argues with a count.
    """
    rng = random.Random(20260821)
    if features <= 1:
        return {"applicable": False,
                "note": "one feature; there was no selection to correct for"}
    analytic = 1.0 - (1.0 - reported) ** features
    hits = 0
    for _ in range(min(trials, 20000)):
        if min(rng.random() for _ in range(min(features, 500))) <= reported:
            hits += 1
    return {
        "applicable": True,
        "reported_p": reported,
        "features_searched": features,
        "chance_under_the_null": round(analytic, 6),
        "simulated": round(hits / min(trials, 20000), 4),
        "simulation_note": ("simulated over at most 500 features for cost; the analytic figure "
                            "is the one to quote" if features > 500 else "exact"),
        "meaning": ("this is how often the BEST of that many null features looks at least this "
                    "good. If it is not small, the endpoint's significance is a property of the "
                    "search, not of the biology"),
    }


def read_pvalues(path: Path) -> list[float]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("p_values") or data.get("pvalues") or []
        return [float(v) for v in data]
    values = []
    for line in text.splitlines()[1:]:
        for cell in line.replace("\t", ",").split(","):
            try:
                values.append(float(cell))
                break
            except ValueError:
                continue
    return values


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--p-values")
    ap.add_argument("--reported-p", type=float)
    ap.add_argument("--features", type=int)
    ap.add_argument("--selected", type=float,
                    help="the p-value of the reported endpoint, if it came from the file")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result: dict = {"alpha": args.alpha}

    if args.p_values:
        path = Path(args.p_values)
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 2
        pvalues = read_pvalues(path)
        if not pvalues:
            print("ERROR: no p-values read", file=sys.stderr)
            return 2
        result["bh"] = benjamini_hochberg(pvalues, args.alpha)
        result["bonferroni"] = bonferroni(pvalues, args.alpha)
        reported = args.selected if args.selected is not None else min(pvalues)
        result["selection"] = selection_inflation(reported, len(pvalues))
        survives = reported <= result["bh"]["largest_rejected_p"] if result["bh"]["rejected"] else False
    elif args.reported_p is not None and args.features:
        result["selection"] = selection_inflation(args.reported_p, args.features)
        result["bonferroni"] = {"method": "bonferroni", "features": args.features,
                                "threshold": args.alpha / args.features,
                                "survives": args.reported_p <= args.alpha / args.features}
        survives = result["bonferroni"]["survives"]
    else:
        ap.error("supply --p-values, or --reported-p with --features")

    result["survives_correction"] = survives
    result["warning"] = ("a correction across FEATURES is not a correction across UNITS. If the "
                         "denominator is wrong, none of this helps and offering it as though it "
                         "did is itself a demotion trigger")

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"MULTIPLICITY: the reported finding "
              f"{'survives' if survives else 'DOES NOT survive'} correction")
        if "bh" in result:
            bh = result["bh"]
            print(f"  benjamini-hochberg  {bh['rejected']}/{bh['features']} rejected at "
                  f"alpha {bh['alpha']} (largest rejected p {bh['largest_rejected_p']:.3g})")
        if "bonferroni" in result and "threshold" in result["bonferroni"]:
            print(f"  bonferroni          threshold {result['bonferroni']['threshold']:.3g}")
        sel = result.get("selection", {})
        if sel.get("applicable"):
            print(f"  selection           p={sel['reported_p']:.3g} as the best of "
                  f"{sel['features_searched']} — under the null that happens "
                  f"{sel['chance_under_the_null']:.3f} of the time")
            print(f"                      {sel['meaning']}")
        print(f"  {result['warning']}")
    return 0 if survives else 1


if __name__ == "__main__":
    sys.exit(main())
