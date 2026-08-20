#!/usr/bin/env python3
"""Baseline gate — the burden of proof is on the model.

Blocking for a predictive-superiority claim. In perturbation-response
prediction, simple baselines are not a formality: predicting the control
profile, the global mean of training perturbations, control-plus-average-delta,
or (for combinations) the additive prediction are repeatedly competitive with,
and often better than, elaborate models. So "the model performs well" is not a
claim about the model until it is a claim relative to those.

The rule is deliberately harsh and deliberately simple: the model must beat the
strongest baseline on EVERY gate metric, by a stated margin. Not on average, not
on the headline, not on the metric the authors preferred. A model that wins one
gate metric and loses another has demonstrated a trade-off, and a trade-off is
not superiority.

Baselines are always reported in the table, whatever the outcome. A results
table with the baselines removed is the artifact this gate exists to prevent.

Usage:  baseline_gate.py <bundle.json> --claim <claim.json> [--margin 0.02]
Exit:   0 model beats every baseline, 1 demoted, 2 error, 3 not applicable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--margin", type=float, default=0.02)
    args = ap.parse_args()

    try:
        bundle = bl.read_json(args.bundle)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2

    model_eval = bundle.get("model_evaluation")
    if not model_eval:
        if claim.get("claim_class") == "model_predictive_superiority":
            print("fail: predictive-superiority claim with no model_evaluation")
            return 1
        print("not_run: no predictive claim in this bundle")
        return 3

    table = bl.load_table("metrics.json")
    gate_metrics = table["gate_metrics"]
    directions = {m["id"]: m["direction"] for m in table["metrics"]}
    required_baselines = {b["id"] for b in table["baselines"]}

    model = model_eval.get("metrics") or {}
    baselines = model_eval.get("baselines") or {}

    problems = []
    is_combination = bool(claim.get("perturbation", {}).get("is_combination"))
    expected = {"control_mean", "global_mean", "mean_delta"} | ({"additive"} if is_combination else set())
    missing = sorted(expected - set(baselines))
    if missing:
        problems.append(
            f"baselines {missing} were not run. A model is only ahead of the baselines that were "
            "actually computed" + (" — `additive` is mandatory for a combination claim, and it is "
                                   "the one that usually wins" if "additive" in missing else ""))

    comparison = {}
    for metric in gate_metrics:
        if metric not in model:
            problems.append(f"gate metric {metric!r} is missing from the model's results")
            continue
        higher_better = directions.get(metric) == "higher_better"
        scores = {name: vals.get(metric) for name, vals in baselines.items()
                  if isinstance(vals, dict) and vals.get(metric) is not None}
        if not scores:
            problems.append(f"no baseline reports {metric!r}, so the model's value is unanchored")
            continue
        best_name = max(scores, key=lambda n: scores[n]) if higher_better else \
            min(scores, key=lambda n: scores[n])
        best = scores[best_name]
        value = model[metric]
        beats = (value >= best + args.margin) if higher_better else (value <= best - args.margin)
        comparison[metric] = {"model": value, "best_baseline": best_name,
                              "baseline_value": best, "beats": beats}
        if not beats:
            problems.append(
                f"{metric}: model {value:.4g} against {best_name} {best:.4g} "
                f"(margin {args.margin}). The model does not beat the strongest baseline here, "
                "so the superiority claim fails on this metric")

    for metric, detail in comparison.items():
        mark = "beats" if detail["beats"] else "LOSES TO"
        print(f"  {metric:<18} model {detail['model']:.4g}  {mark}  "
              f"{detail['best_baseline']} {detail['baseline_value']:.4g}")

    if problems:
        print(f"\nfail: DEMOTED_DOES_NOT_BEAT_BASELINE — {len(problems)} problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"\npass: model beats the strongest baseline on all {len(gate_metrics)} gate metrics "
          f"by at least {args.margin}")
    print("  Necessary, not sufficient: this says the model is ahead of the trivial predictors, "
          "and nothing about whether the estimand or the biology is right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
