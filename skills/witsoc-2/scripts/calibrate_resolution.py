#!/usr/bin/env python3
"""Calibrate the resolution weights against every pack's declared cases.

Governance rule 9 says an optimization proves it pays. `resolve_domain.py` ships
five numbers that were never measured — signal weight 1, strong weight 3,
exclude weight -3, a margin of 3, and a default threshold of 3 — chosen because
they seemed reasonable. Reasonable is not a measurement, and a scoring rule
nobody has swept is a scoring rule that happens to work on its author's examples.

The corpus is already there: every pack declares `examples` that must resolve to
it and `counter_examples` that must not, and `--self-test` replays them. This
sweeps the weights over that corpus and reports what the numbers should be.

Two honest limits, printed with the result:

**The corpus is small and self-selected.** Thirty-odd cases written by whoever
wrote the packs. A weighting that scores perfectly here has been shown to fit
these cases and nothing else, and the right response to a perfect score is
suspicion rather than confidence.

**Ties are the finding.** When many settings score identically — which is what
usually happens on a small corpus — the sweep has established that the corpus
cannot distinguish them, not that the current values are right. That result is
reported as a tie rather than resolved by picking the first.

Usage:  calibrate_resolution.py [--json]
Exit:   0 the shipped weights are among the best, 1 something else scores better.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import resolve_domain as rd  # noqa: E402

SIGNAL_WEIGHTS = [0.5, 1.0, 1.5, 2.0]
STRONG_WEIGHTS = [2.0, 3.0, 4.0, 6.0]
EXCLUDE_WEIGHTS = [-1.0, -2.0, -3.0, -5.0]
MARGINS = [1.0, 2.0, 3.0, 5.0]


def corpus(packs: list[dict]) -> list[tuple[str, str, bool]]:
    """(statement, pack, should_select). Both directions, because a rule that
    only has to accept is trivially satisfied by accepting everything."""
    cases = []
    for pack in packs:
        selection = pack.get("selection") or {}
        name = pack.get("domain", pack["_dir"].name)
        if not selection or selection.get("explicit_only"):
            continue
        for text in selection.get("examples", []) or []:
            cases.append((text, name, True))
        for text in selection.get("counter_examples", []) or []:
            cases.append((text, name, False))
    return cases


def score_setting(packs, cases, weights, margin) -> dict:
    original_weight, original_margin = dict(rd.WEIGHT), rd.MARGIN
    rd.WEIGHT.update(weights)
    rd.MARGIN = margin
    try:
        right = ambiguous = wrong_pack = missed = false_positive = 0
        for text, pack, should in cases:
            got = rd.decide(packs, rd.normalize(text))
            selected = got["domain"] if got["decision"] == "SELECTED" else None
            if should:
                if selected == pack:
                    right += 1
                elif got["decision"] == "AMBIGUOUS":
                    ambiguous += 1
                elif selected is None:
                    missed += 1
                else:
                    wrong_pack += 1
            else:
                if selected == pack:
                    false_positive += 1
                else:
                    right += 1
        return {"correct": right, "ambiguous": ambiguous, "missed": missed,
                "wrong_pack": wrong_pack, "false_positive": false_positive,
                "score": right - 2 * wrong_pack - 2 * false_positive - ambiguous * 0.5}
    finally:
        rd.WEIGHT.clear(); rd.WEIGHT.update(original_weight)
        rd.MARGIN = original_margin


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    packs, _ = rd.load_packs()
    cases = corpus(packs)
    if not cases:
        print("no declared cases to calibrate against", file=sys.stderr)
        return 1

    shipped = {"signals": 1.0, "strong_signals": 3.0, "excludes": -3.0}
    results = []
    for sw in SIGNAL_WEIGHTS:
        for tw in STRONG_WEIGHTS:
            for ew in EXCLUDE_WEIGHTS:
                for margin in MARGINS:
                    weights = {"signals": sw, "strong_signals": tw, "excludes": ew}
                    outcome = score_setting(packs, cases, weights, margin)
                    results.append({"weights": weights, "margin": margin, **outcome})

    best = max(r["score"] for r in results)
    winners = [r for r in results if r["score"] == best]
    shipped_result = next(r for r in results
                          if r["weights"] == shipped and r["margin"] == 3.0)
    shipped_is_best = shipped_result["score"] == best

    summary = {
        "cases": len(cases),
        "settings_swept": len(results),
        "best_score": best,
        "settings_achieving_it": len(winners),
        "shipped": {"weights": shipped, "margin": 3.0, **{k: v for k, v in
                    shipped_result.items() if k not in {"weights", "margin"}}},
        "shipped_is_among_the_best": shipped_is_best,
        "limits": [
            f"{len(cases)} cases, all written by whoever wrote the packs. A perfect score here "
            "shows a fit to these cases and nothing else",
            "where many settings tie, the corpus cannot distinguish them — that is the finding, "
            "not a licence to pick one",
        ],
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"RESOLUTION CALIBRATION — {len(cases)} declared case(s), "
              f"{len(results)} setting(s) swept\n")
        print(f"  shipped  weights {shipped}, margin 3.0")
        print(f"           correct {shipped_result['correct']}/{len(cases)}  "
              f"missed {shipped_result['missed']}  wrong-pack {shipped_result['wrong_pack']}  "
              f"false-positive {shipped_result['false_positive']}")
        print(f"  best score {best}, achieved by {len(winners)} of {len(results)} settings")
        if shipped_is_best:
            print("\n  The shipped weights are among the best. That is the honest outcome and it\n"
                  "  is weaker than it sounds: with this many ties, the corpus has shown it\n"
                  "  cannot distinguish the settings, not that these ones are right.")
        else:
            example = winners[0]
            print(f"\n  Something scores better: weights {example['weights']}, "
                  f"margin {example['margin']} -> {example['score']}")
            print("  Change the shipped values only if the improvement survives new cases; a\n"
                  "  gain measured on the corpus that chose it is not a gain.")
        for limit in summary["limits"]:
            print(f"\n  limit: {limit}")
    return 0 if shipped_is_best else 1


if __name__ == "__main__":
    sys.exit(main())
