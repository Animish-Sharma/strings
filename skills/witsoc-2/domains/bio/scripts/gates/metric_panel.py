#!/usr/bin/env python3
"""Metric-panel gate — is the whole panel reported, and is it stable?

Blocking for a predictive claim. Every metric in this field is gameable by
something: a discrimination score by embedding structure alone, a differential
expression score by predicting globally frequent genes, an absolute error by
predicting that nothing changed. Reporting one metric is therefore not a summary
of performance, it is a choice of which failure mode to hide.

Three checks:

1. COMPLETENESS — every metric in the panel is present, including the ones that
   make the result look worse. A missing metric is treated as a failed one,
   because "we didn't compute it" and "we computed it and didn't like it" are
   indistinguishable from the outside.
2. REPORT-ONLY DISCIPLINE — metrics flagged report-only exist to expose an
   artifact, not to rank models. A claim that leans on one is refused.
3. RANK STABILITY — if the model's rank against the baselines moves by two or
   more places across the gate metrics, the panel disagrees with itself. That is
   a real finding about a fragile result, and the report must show it rather
   than quietly presenting the ordering that flatters.

Diagnostics: `control_bias` and `signal_dilution` catch a prediction that is
scoring well by predicting the control or by shrinking everything toward the
mean — the two ways a model wins a cheap metric without learning anything.

Usage:  metric_panel.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error, 3 not applicable
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
            print("fail: predictive claim with no model_evaluation")
            return 1
        print("not_run: no predictive claim in this bundle")
        return 3

    table = bl.load_table("metrics.json")
    specs = {m["id"]: m for m in table["metrics"]}
    model = model_eval.get("metrics") or {}
    baselines = model_eval.get("baselines") or {}
    problems, notes = [], []

    missing = [m for m in specs if m not in model]
    if missing:
        problems.append(
            f"panel incomplete: {missing} not reported. A metric that was not computed and a "
            "metric that was computed and set aside look the same in a table, so both count as "
            "failures here")

    headline = model_eval.get("headline_metric")
    if headline and specs.get(headline, {}).get("report_only"):
        problems.append(
            f"{headline!r} is a report-only metric — it is in the panel to expose an artifact, "
            f"not to rank on. {specs[headline]['gameable_by']}")

    if model_eval.get("composite_score") is not None and not model_eval.get("per_metric_preserved"):
        problems.append(
            "a composite score is reported without the per-metric results. Compositing is where "
            "a loss on a discriminative metric gets absorbed by a win on a dilution-prone one")

    # Rank stability across the gate metrics.
    ranks = {}
    for metric in table["gate_metrics"]:
        if metric not in model:
            continue
        higher_better = specs[metric]["direction"] == "higher_better"
        field = [("model", model[metric])] + [
            (name, vals[metric]) for name, vals in baselines.items()
            if isinstance(vals, dict) and vals.get(metric) is not None]
        ordered = sorted(field, key=lambda kv: kv[1], reverse=higher_better)
        ranks[metric] = [name for name, _ in ordered].index("model") + 1

    instability = None
    if len(ranks) >= 2:
        spread = max(ranks.values()) - min(ranks.values())
        instability = {"ranks": ranks, "spread": spread, "unstable": spread >= 2}
        if spread >= 2:
            notes.append(
                f"metric_picks_winner_flag: the model ranks {min(ranks.values())} on one gate "
                f"metric and {max(ranks.values())} on another. The choice of metric is doing more "
                "work than the model; this must appear in the report, not be resolved by picking one")

    # Diagnostics for the two classic ways of scoring well while learning nothing.
    control_mean = (baselines.get("control_mean") or {})
    for metric in table["gate_metrics"]:
        if metric in model and metric in control_mean:
            if abs(model[metric] - control_mean[metric]) < 1e-6:
                notes.append(
                    f"control_bias: the model's {metric} is identical to the control-mean "
                    "baseline's, which is what predicting 'no perturbation' looks like")
    if model.get("mae") is not None and control_mean.get("mae") is not None:
        if model["mae"] < control_mean["mae"] and model.get("weighted_pearson", 1) < 0.1:
            notes.append(
                "signal_dilution: a better absolute error alongside a near-zero DEG-weighted "
                "correlation is the signature of shrinking predictions toward the mean")

    for note in notes:
        print(f"  flag: {note}")
    if problems:
        print(f"fail: {len(problems)} panel problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: full panel of {len(specs)} metrics reported"
          + (f"; rank spread {instability['spread']}" if instability else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
