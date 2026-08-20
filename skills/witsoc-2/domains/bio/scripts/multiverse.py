#!/usr/bin/env python3
"""Multiverse — how much of this result is the analysis rather than the data?

`doctrine/claim_freeze.md` asks for "sensitivity to preprocessing and reasonable
analysis alternatives" and nothing computed it. So the pack could demand the
check, accept a sentence saying it was done, and never see the number.

Every perturbation analysis makes choices nobody would defend as the only
possible one: which cells to filter, whether to log-transform, whether to trim
outliers, which unit to aggregate to, whether to exclude a batch. Each is
defensible. The question is whether the result depends on them.

This re-runs the same contrast under every combination of the declared
alternatives and reports the spread. Three outcomes and they mean different
things:

    ROBUST      the effect keeps its sign and rough size everywhere. The
                analysis choices were not doing the work.
    FRAGILE     the effect survives in some universes and not others. That is
                not a reason to pick the surviving one — it is the finding, and
                the report has to carry it.
    SPECIFICATION-DEPENDENT
                the sign flips. The result is a statement about the pipeline.

The trap this avoids is the one it is named for: running many analyses and
reporting the best is how a fragile result becomes a published one. Here every
universe is reported, and the one that was pre-registered is marked — because a
pre-registered choice that turns out fragile is still the answer, and the
alternatives are the caveat.

Usage:
    multiverse.py --metadata <file.csv> --value <col> --unit <col> --label <col>
                  --treatment <v> --control <v> [--stratum <col>]
                  [--alternatives <spec.json>] [--json]

Exit: 0 robust · 1 fragile or specification-dependent · 2 usage/IO
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402

# The choices that are always available and always arguable. Each is a function
# from the observation rows to a filtered/transformed set.
DEFAULT_ALTERNATIVES = {
    "transform": ["none", "log1p"],
    "outliers": ["keep", "trim_1pct"],
    "min_cells_per_unit": [0, 5],
}


def applicable(mode: str, values: list[float]) -> str | None:
    """Why this specification cannot be applied to this data, if it cannot.

    An alternative that is not defensible for the data in hand is not an
    alternative — it is a different question. `log1p` on a signed score produces
    NaN, and a NaN effect compared against a real one manufactures a sign flip:
    the first version of this reported SPECIFICATION_DEPENDENT on data whose
    effect never moved, which is the worst possible error for a check whose whole
    job is to say whether the analysis is doing the work.
    """
    if mode == "log1p" and any(v <= -1 for v in values):
        return ("log1p is undefined on values at or below -1; this endpoint is signed, so the "
                "transform is not a defensible alternative for it")
    return None


def apply_transform(value: float, mode: str) -> float:
    if mode == "log1p":
        return math.log1p(value) if value > -1 else float("nan")
    return value


def universe(rows, spec, data) -> tuple[list[float], list[str], list[str] | None, str | None]:
    value_col, unit_col, label_col = data["value"], data["unit"], data["label"]
    stratum_col = data.get("stratum")

    numeric = []
    for row in rows:
        try:
            numeric.append((row, float(row[value_col])))
        except (KeyError, ValueError):
            continue

    blocked = applicable(spec["transform"], [v for _, v in numeric])
    if blocked:
        return [], [], None, blocked

    if spec["outliers"] == "trim_1pct" and len(numeric) > 100:
        ordered = sorted(numeric, key=lambda rv: rv[1])
        cut = max(1, len(ordered) // 100)
        numeric = ordered[cut:-cut]

    kept = []
    for row, value in numeric:
        row = dict(row)
        row[value_col] = str(apply_transform(value, spec["transform"]))
        kept.append(row)

    units = bl.pseudobulk(kept, unit_col, value_col, label_col)
    if spec["min_cells_per_unit"]:
        units = [u for u in units if u["n_observations"] >= spec["min_cells_per_unit"]]
    units = [u for u in units if u["label"] in (data["treatment"], data["control"])]

    strata = None
    if stratum_col:
        by_unit = {}
        for row in kept:
            key = (row.get(unit_col) or "").strip()
            if key:
                by_unit.setdefault(key, (row.get(stratum_col) or "").strip())
        strata = [by_unit.get(u["unit"], "") for u in units]
    return [u["mean"] for u in units], [u["label"] for u in units], strata, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--treatment", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--stratum")
    ap.add_argument("--alternatives")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--iterations", type=int, default=1500)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = Path(args.metadata)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2
    _, rows = bl.read_csv(path)

    alternatives = DEFAULT_ALTERNATIVES
    if args.alternatives:
        alternatives = json.loads(Path(args.alternatives).read_text(encoding="utf-8"))

    data = {"value": args.value, "unit": args.unit, "label": args.label,
            "stratum": args.stratum, "treatment": args.treatment, "control": args.control}

    keys = sorted(alternatives)
    results = []
    for combo in itertools.product(*(alternatives[k] for k in keys)):
        spec = dict(zip(keys, combo))
        values, labels, strata, blocked = universe(rows, spec, data)
        if blocked:
            results.append({**spec, "ran": False, "why": blocked})
            continue
        if labels.count(args.treatment) < 2 or labels.count(args.control) < 2:
            results.append({**spec, "ran": False,
                            "why": "fewer than two units per arm survive this specification"})
            continue
        test = bl.permutation_p(values, labels, args.treatment, args.control,
                                iterations=args.iterations, seed=0, strata=strata)
        results.append({**spec, "ran": True,
                        "effect": round(test["observed_difference"], 4),
                        "p": round(test["p_value"], 4),
                        "significant": test["p_value"] <= args.alpha,
                        "units": {"treatment": test["n_treatment"],
                                  "control": test["n_control"]}})

    live = [r for r in results if r.get("ran")]
    effects = [r["effect"] for r in live if r["effect"] == r["effect"]]  # drop NaN
    signs = {1 if e > 0 else -1 if e < 0 else 0 for e in effects}
    significant = [r for r in live if r["significant"]]

    if not live:
        verdict = "UNRUNNABLE"
    elif len(signs) > 1:
        verdict = "SPECIFICATION_DEPENDENT"
    elif len(significant) == len(live):
        verdict = "ROBUST"
    else:
        verdict = "FRAGILE"

    summary = {
        "verdict": verdict,
        "universes": len(results),
        "ran": len(live),
        "significant_in": f"{len(significant)}/{len(live)}",
        "effect_range": [min(effects), max(effects)] if effects else None,
        "sign_flips": len(signs) > 1,
        "results": results,
        "reading": {
            "ROBUST": "the analysis choices were not doing the work",
            "FRAGILE": ("the effect survives some defensible specifications and not others. "
                        "This is the finding, not a menu — the pre-registered specification is "
                        "the answer and these are its caveat"),
            "SPECIFICATION_DEPENDENT": ("the sign flips across defensible choices. The result is "
                                        "a statement about the pipeline"),
            "UNRUNNABLE": "no specification leaves enough units to test",
        }[verdict],
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"MULTIVERSE: {verdict} — significant in {summary['significant_in']} "
              f"of {summary['ran']} runnable specification(s)\n")
        for r in results:
            spec = ", ".join(f"{k}={r[k]}" for k in keys)
            if r.get("ran"):
                mark = "*" if r["significant"] else " "
                print(f"  {mark} {spec:<52} effect {r['effect']:>9}  p {r['p']:.4f}")
            else:
                print(f"    {spec:<52} {r['why']}")
        if summary["effect_range"]:
            lo, hi = summary["effect_range"]
            print(f"\n  effect ranges {lo} to {hi} across specifications")
        print(f"  {summary['reading']}")
    return 0 if verdict == "ROBUST" else 1


if __name__ == "__main__":
    sys.exit(main())
