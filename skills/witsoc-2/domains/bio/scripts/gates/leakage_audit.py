#!/usr/bin/env python3
"""Leakage gate — did the held-out axis actually hold anything out?

Blocking for any claim involving a model or a generalization axis. Most
perturbation-prediction wins evaporate under this check, which is exactly why it
runs before the metrics rather than after: a leaked split makes every downstream
number a measurement of memorization on the precise axis being claimed.

Severity depends on what is claimed, not on what leaked:

    perturbation_leakage   fatal for a held-out-perturbation claim
    cell_line_leakage      fatal for a cross-context claim, a warning otherwise
    donor_leakage          fatal for a new-donor claim, a warning otherwise
    control_contamination  always fatal — the reference itself is contaminated
    batch_split_confound   warning; must be acknowledged, not silently carried

The asymmetry is deliberate. Overlap that is irrelevant to the claim is not a
defect, and treating it as one trains people to route around the check.

Usage:  leakage_audit.py <bundle.json> --claim <claim.json>
Exit:   0 clean or acknowledged warnings, 1 fatal leakage, 2 error,
        3 no split declared and none needed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402


def overlap(a, b) -> list:
    return sorted(set(a or []) & set(b or []))


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
            print("fail: the claim is about predictive superiority and the bundle declares no "
                  "model_evaluation. There is no split to audit and no claim to support")
            return 1
        print("not_run: no model_evaluation in this bundle and none required by the claim class")
        return 3

    split = model_eval.get("split") or {}
    if not split:
        print("fail: model_evaluation declares no split. An evaluation without a stated split "
              "policy has no held-out axis, so nothing about generalization can be read from it")
        return 1

    claims_new = {
        "perturbation": bool(split.get("held_out_perturbations")),
        "cell_line": bool(claim.get("generalization_axis") == "cell_line"),
        "donor": bool(claim.get("generalization_axis") == "donor"),
    }

    fatal, warnings = [], []

    def check(name, train_key, test_key, is_fatal, detail):
        shared = overlap(split.get(train_key), split.get(test_key))
        if shared:
            (fatal if is_fatal else warnings).append(f"{name}: {len(shared)} shared — {shared[:8]} ({detail})")

    check("perturbation_leakage", "train_perturbations", "test_perturbations",
          claims_new["perturbation"],
          "the held-out perturbation set is the claim; overlap measures memorization")
    check("cell_line_leakage", "train_cell_lines", "test_cell_lines", claims_new["cell_line"],
          "cross-context generalization was claimed on an axis that is shared")
    check("donor_leakage", "train_donors", "test_donors", claims_new["donor"],
          "new-donor generalization was claimed on donors the model has seen")

    controls_shared = overlap(split.get("train_controls"), split.get("test_controls"))
    if controls_shared:
        fatal.append(
            f"control_contamination: {len(controls_shared)} control unit(s) appear in both splits. "
            "Every control-referenced metric is computed against data the model trained on")

    train_batches = set(split.get("train_batches") or [])
    test_batches = set(split.get("test_batches") or [])
    if train_batches and test_batches and not (train_batches & test_batches):
        warnings.append(
            "batch_split_confound: the split falls exactly along batch lines, so batch effect and "
            "generalization are the same measurement")

    acknowledged = set(model_eval.get("acknowledged_leakage_warnings") or [])
    unacknowledged = [w for w in warnings if w.split(":")[0] not in acknowledged]

    if fatal:
        print(f"fail: {len(fatal)} fatal leakage finding(s)")
        for item in fatal:
            print(f"  {item}")
        return 1
    for item in warnings:
        print(f"  warning: {item}")
    if unacknowledged:
        print(f"fail: {len(unacknowledged)} leakage warning(s) not acknowledged in "
              "model_evaluation.acknowledged_leakage_warnings. A warning nobody has to read is "
              "not a warning")
        return 1
    print("pass: no fatal leakage on the axes this claim depends on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
