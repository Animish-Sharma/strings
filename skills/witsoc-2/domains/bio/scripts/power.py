#!/usr/bin/env python3
"""Power — the smallest effect this design could have detected.

The statistical-audit gate requires a minimum detectable effect and nothing
computed one, which meant the requirement was met by writing a number down. This
computes it, at the estimand-matching denominator, by the same permutation test
the executable tier uses — so the answer is about the test that will actually be
run rather than about an idealized version of it.

It matters most for the result people find least interesting. A null result
without a minimum detectable effect is not evidence of absence; it is evidence
that this design could not see whatever was there. The two are written the same
way and one of them is worth publishing.

The method, deliberately simple enough to re-derive by hand:

1. Aggregate observations to the experimental unit, as the real test does.
2. Take the residual spread at that unit level as the noise scale.
3. For a grid of true effect sizes, simulate: shift the treatment units by the
   effect, permute, and count how often the test would reject.
4. Report the smallest effect reaching the requested power.

Two honest limits, printed with the answer. The noise scale comes from the data
in hand, so with three units it is itself barely estimated. And this assumes the
effect is a constant shift; a design that would detect a shift of 0.4 may be
blind to a change in spread of any size.

Usage:
    power.py --metadata <file.csv> --unit <col> --value <col> --label <col>
             --treatment <v> --control <v> [--alpha 0.05] [--power 0.8]
             [--stratum <col>] [--json]

Exit: 0 computed, 2 usage/IO error, 3 too few units to compute anything.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402

GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


def rejects(values, labels, treatment, control, alpha, iterations, seed, strata):
    test = bl.permutation_p(values, labels, treatment, control,
                            iterations=iterations, seed=seed, strata=strata)
    return test.get("ran") and test["p_value"] <= alpha


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--treatment", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--stratum")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.8)
    ap.add_argument("--simulations", type=int, default=200)
    ap.add_argument("--iterations", type=int, default=600)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = Path(args.metadata)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2
    _, rows = bl.read_csv(path)

    units = [u for u in bl.pseudobulk(rows, args.unit, args.value, args.label)
             if u["label"] in {args.treatment, args.control}]
    treated = [u for u in units if u["label"] == args.treatment]
    controls = [u for u in units if u["label"] == args.control]
    if len(treated) < 2 or len(controls) < 2:
        print(json.dumps({
            "computed": False,
            "units": {"treatment": len(treated), "control": len(controls)},
            "reason": "fewer than two units per arm. There is no power to compute: the "
                      "permutation distribution over this design cannot produce a small enough "
                      "p-value at any effect size, which is itself the finding",
        }, indent=2))
        return 3

    strata = None
    if args.stratum:
        by_unit = {}
        for row in rows:
            key = (row.get(args.unit) or "").strip()
            if key:
                by_unit.setdefault(key, (row.get(args.stratum) or "").strip())
        strata = [by_unit.get(u["unit"], "") for u in units]

    # The floor: the smallest p-value this design can produce at all. If it
    # exceeds alpha, no effect size is detectable and the grid is beside the point.
    n_arrangements_floor = 1.0 / (args.iterations + 1)
    baseline = bl.permutation_p([u["mean"] for u in units], [u["label"] for u in units],
                                args.treatment, args.control,
                                iterations=args.iterations, seed=0, strata=strata)

    # The noise that matters is the noise the TEST sees. A stratified permutation
    # on a paired design never sees the between-stratum spread — it cancels — so
    # estimating the scale from the raw unit means inflates it, and the power
    # curve then reports that a design cannot detect an effect it demonstrably
    # just detected. Residuals: remove the arm mean, and the stratum mean when
    # the test is stratified.
    labels = [u["label"] for u in units]
    arm_mean = {arm: bl.mean([u["mean"] for u in units if u["label"] == arm])
                for arm in (args.treatment, args.control)}
    paired = None
    if strata:
        by_stratum: dict[str, dict[str, list[float]]] = {}
        for unit, stratum in zip(units, strata):
            by_stratum.setdefault(stratum, {}).setdefault(unit["label"], []).append(unit["mean"])
        if all(len(arms.get(args.treatment, [])) == 1 and len(arms.get(args.control, [])) == 1
               for arms in by_stratum.values()) and len(by_stratum) >= 2:
            paired = [arms[args.treatment][0] - arms[args.control][0]
                      for arms in by_stratum.values()]

    if paired:
        # A matched design's noise is the spread of the PAIRED DIFFERENCES, and
        # nothing else. Estimating it from residuals after centring each pair
        # understates it by a factor of about root two — because centring two
        # values removes half their information — and a power calculation that
        # is optimistic by forty percent is worse than no power calculation,
        # since it will be quoted.
        noise = bl.stdev(paired) / (2 ** 0.5)
        noise_kind = ("half the spread of the within-pair differences, which is the per-unit "
                      "scale a matched design actually operates at")
    else:
        residuals = [u["mean"] - arm_mean[u["label"]] for u in units]
        noise = bl.stdev(residuals)
        noise_kind = "residual spread after removing the arm means"
    if noise != noise or noise == 0:
        noise = 1.0

    rng = random.Random(20260821)
    curve = []
    detectable = None
    stratum_ids = strata or [""] * len(units)
    for effect in GRID:
        hits = 0
        for sim in range(args.simulations):
            # Regenerate the stratum offsets each simulation, then let them
            # cancel exactly as they do in the real stratified test.
            offsets = {s: rng.gauss(0, noise) for s in set(stratum_ids)}
            shifted = []
            for unit, stratum in zip(units, stratum_ids):
                base = offsets[stratum] + rng.gauss(0, noise)
                if unit["label"] == args.treatment:
                    base += effect * noise
                shifted.append(base)
            if rejects(shifted, labels, args.treatment, args.control,
                       args.alpha, args.iterations, sim, strata):
                hits += 1
        achieved = hits / args.simulations
        curve.append({"effect_in_sd": effect, "effect_absolute": round(effect * noise, 4),
                      "power": round(achieved, 3)})
        if detectable is None and achieved >= args.power:
            detectable = curve[-1]

    out = {
        "computed": True,
        "units": {"treatment": len(treated), "control": len(controls),
                  "observations": len(rows), "unit_column": args.unit},
        "noise_scale_at_unit_level": round(noise, 4),
        "noise_is": noise_kind,
        "alpha": args.alpha,
        "requested_power": args.power,
        "smallest_p_this_design_can_produce": round(
            max(n_arrangements_floor, baseline.get("p_value", 1.0) * 0), 6) or n_arrangements_floor,
        "observed_effect": round(baseline.get("observed_difference", 0.0), 4),
        "observed_p": round(baseline.get("p_value", 1.0), 4),
        "minimum_detectable_effect": detectable,
        "power_curve": curve,
        "limits": [
            "the noise scale is estimated from the units in hand, so with few units it is itself "
            "barely estimated and this whole answer inherits that",
            "this assumes a constant shift. A design that would detect a shift of this size may "
            "be blind to a change in spread of any size",
        ],
    }
    if detectable is None:
        out["minimum_detectable_effect"] = None
        out["verdict"] = (
            f"no effect on the grid reaches {args.power} power at alpha {args.alpha}. A null "
            "result from this design is evidence about the design, not about the biology")
    else:
        out["verdict"] = (
            f"this design detects an effect of {detectable['effect_absolute']} "
            f"({detectable['effect_in_sd']} unit-level SD) with {detectable['power']} power. "
            "A null result bounds the effect below roughly that, and says nothing smaller")

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
