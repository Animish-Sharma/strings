#!/usr/bin/env python3
"""Denominator gate — what unit does this evidence actually speak about?

Blocking, every tier, and the most important check in the pack. It is a GATE and
not a tier for a precise reason: it can only ever demote. No design, however
clean, is evidence that a claim is true — it decides how strong a claim the
design is CAPABLE of supporting, which is a ceiling, and ceilings belong to
gates. Treating it as a tier would let a well-designed experiment with no
results earn a status.

It matters because the dominant failure in perturbation biology is not a wrong
number. It is a correct number attached to the wrong denominator.

The arithmetic is the whole argument. Ten thousand cells from one donor, with
any intra-cluster correlation at all, carry roughly the information of one
donor: the design effect drives the effective sample size toward the number of
CLUSTERS, not observations. So a population claim resting on cell count is not
weakly supported, it is unsupported, and more cells make the confidence interval
narrower around an estimand nobody asked about.

What it does:

1. Classifies every metadata column against the unit taxonomy, reporting
   unclassified columns rather than dropping them.
2. Checks the claim's declared experimental unit is a level that can carry the
   claim's estimand at all.
3. Counts upstream units and checks they are CROSSED with the condition rather
   than confounded with it. A donor seen under one condition only contributes
   nothing to a within-donor contrast, however many cells it has.
4. Reports effective sample size across a grid of plausible intra-cluster
   correlations, so the design effect is visible instead of assumed away.
5. Applies the hard rejection rules and the class ceiling, and returns the
   strongest status this design could support.

Usage:  denominator_gate.py <bundle.json> --claim <claim.json> [--json]
Exit:   0 the design supports the claim's class, 1 demoted or rejected,
        2 error, 3 no metadata to analyse (NOT_RUN — a gap, never a pass)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

ICC_GRID = [0.0, 0.001, 0.01, 0.05, 0.1]

POPULATION_ESTIMANDS = {"population"}


def classify_claim(claim: dict, classes: list[dict]) -> dict | None:
    wanted = claim.get("claim_class")
    return next((c for c in classes if c["id"] == wanted), None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        bundle = bl.read_json(args.bundle)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)}))
        return 2

    table = bl.load_table("claim_classes.json")
    spec = classify_claim(claim, table["classes"])
    if spec is None:
        print(json.dumps({
            "gate": "denominator", "verdict": "fail", "max_status": "FAILED_ATTEMPT",
            "problems": [
                f"claim_class {claim.get('claim_class')!r} is not one of "
                f"{[c['id'] for c in table['classes']]}. The class determines the ceiling, so an "
                "unclassified claim has no ceiling and cannot be audited"],
        }, indent=2))
        return 1

    data = bundle.get("data") or {}
    metadata_path = data.get("metadata_csv")
    if not metadata_path:
        print(json.dumps({
            "gate": "denominator", "verdict": "not_run", "max_status": "CONJECTURE",
            "problems": ["bundle declares no metadata_csv, so the experimental unit cannot be "
                         "checked. This is a gap, not a pass: without it the denominator is "
                         "whatever the analysis happened to group by"],
        }, indent=2))
        return 3

    csv_path = (Path(args.bundle).parent / metadata_path).resolve()
    if not csv_path.exists():
        print(json.dumps({
            "gate": "denominator", "verdict": "not_run", "max_status": "CONJECTURE",
            "problems": [f"metadata_csv {metadata_path!r} does not exist at {csv_path}"],
        }, indent=2))
        return 3

    fields, rows = bl.read_csv(csv_path)
    classified = bl.classify_columns(fields)
    taxonomy = bl.load_table("unit_taxonomy.json")["levels"]

    # The unit that carries the CLAIM, which is not always the unit the analysis
    # aggregates to. In a paired design the analysis collapses to donor-by-
    # condition while the claim is about donors; checking the aggregation unit
    # would pass a design that has one donor and two conditions.
    unit_col = (data.get("biological_unit_column") or data.get("unit_column")
                or claim.get("assay", {}).get("experimental_unit"))
    cond_col = data.get("label_column")
    problems: list[str] = []
    flags: list[str] = []
    notes: list[str] = []

    if unit_col not in classified:
        problems.append(
            f"declared experimental unit {unit_col!r} is not a column in the metadata "
            f"({fields}). The unit the claim names and the unit the data has are different things"
        )
        level = None
    else:
        level = classified[unit_col]
        notes.append(f"biological unit {unit_col!r} classified as {level}")
        if data.get("unit_column") and data["unit_column"] != unit_col:
            notes.append(
                f"the analysis aggregates to {data['unit_column']!r}; the claim rests on "
                f"{unit_col!r}. Both are checked, because a design can aggregate correctly and "
                "still be about the wrong thing")

    estimand = spec["estimand"]
    if estimand in POPULATION_ESTIMANDS and level is not None:
        if not taxonomy.get(level, {}).get("supports_population_claim"):
            flags.append("pseudoreplication" if level == "observation_unit" else
                         "technical_unit_overclaim" if level in {"technical_process_unit", "screen_process_unit"} else
                         "guide_redundancy_not_biological_replication" if level == "assignment_unit" else
                         "unit_level_mismatch")
            problems.append(
                f"this is a {estimand}-level claim, but its experimental unit {unit_col!r} is a "
                f"{level}. {taxonomy.get(level, {}).get('role', '')} "
                "Aggregating more of them does not produce independent draws from the population"
            )

    unit_summary: dict = {}
    if unit_col in classified and cond_col in classified:
        crossing = bl.crossed(rows, unit_col, cond_col)
        unit_summary = crossing
        n_units = crossing["units"]

        # Crossing is a demand you can only make of a BIOLOGICAL unit. A donor
        # could have contributed cells under both conditions, so a donor that saw
        # one condition only is confounded with it. A guide could not: it is
        # targeting or non-targeting by construction. Demanding that guides be
        # crossed would reject every screen ever run, which is the over-rejection
        # failure this table exists to prevent in both directions.
        crossing_required = estimand in POPULATION_ESTIMANDS
        if crossing_required and crossing["completely_confounded"]:
            flags.append("condition_confounded_with_unit")
            problems.append(
                f"every {unit_col} appears under exactly one {cond_col}, and this is a "
                f"{estimand}-level claim. The contrast is entirely between units, so unit "
                "differences and treatment differences are the same number"
            )
        elif crossing_required and crossing["units_seeing_one_condition_only"]:
            notes.append(
                f"{len(crossing['units_seeing_one_condition_only'])} of {n_units} units see one "
                f"condition only; they contribute nothing to the within-unit contrast"
            )
        elif not crossing_required:
            notes.append(
                f"{unit_col!r} is an assignment-level unit and is not expected to be crossed with "
                f"{cond_col!r}; the bar here is independent units per arm, matched controls, and "
                "demonstrated perturbation efficacy"
            )
            per_arm = {}
            for row in rows:
                cond = (row.get(cond_col) or "").strip()
                unit = (row.get(unit_col) or "").strip()
                if cond and unit:
                    per_arm.setdefault(cond, set()).add(unit)
            floor = spec.get("min_units_per_arm", 0)
            thin = {c: len(u) for c, u in per_arm.items() if len(u) < floor}
            if thin:
                problems.append(
                    f"claim class {spec['id']!r} needs at least {floor} independent units per arm; "
                    f"{thin} fall short. A contrast between one unit and one unit is a contrast "
                    "between two units, whatever the cell count")
            else:
                notes.append(f"units per arm: { {c: len(u) for c, u in per_arm.items()} }")
        minimum = spec.get("min_upstream_units", 0)
        if n_units < minimum:
            problems.append(
                f"claim class {spec['id']!r} needs at least {minimum} independent upstream units; "
                f"this design has {n_units}"
            )
        few = spec.get("few_cluster_warning_below")
        if few and minimum <= n_units < few:
            flags.append("few_cluster_warning")
            notes.append(
                f"{n_units} upstream units is above the floor and below {few}: cluster-robust "
                "uncertainty is unreliable here, and the claim carries an explicit few-cluster caveat"
            )
    elif cond_col not in classified:
        problems.append(f"declared condition column {cond_col!r} is not in the metadata ({fields})")

    # Design effect. The point of showing the grid is that no ICC has to be
    # argued for: even 0.001 collapses cell-count-based confidence.
    # Compute the design effect at the strongest BIOLOGICAL level the table
    # actually has, not at whatever unit the bundle declared. Computing it at a
    # declared cell-level unit gives one observation per cluster and no design
    # effect at all — the arithmetic reports nothing precisely when the design is
    # at its worst, which is the moment the argument is needed.
    effect_col = unit_col
    if not taxonomy.get(classified.get(unit_col, ""), {}).get("supports_population_claim"):
        effect_col = next(
            (c for c, l in classified.items() if l == "biological_replicate_candidate"), unit_col)
    sizes: list[int] = []
    if effect_col in classified:
        counts: dict[str, int] = {}
        for row in rows:
            key = (row.get(effect_col) or "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
        sizes = sorted(counts.values(), reverse=True)
    design_effect = [
        {"icc": icc, "effective_n": round(bl.effective_n(sizes, icc), 2)} for icc in ICC_GRID
    ] if sizes else []
    if design_effect and len(sizes) >= 1:
        at_small_icc = next(d["effective_n"] for d in design_effect if d["icc"] == 0.01)
        if at_small_icc < sum(sizes) * 0.05:
            notes.append(
                f"at ICC 0.01 the effective sample size is {at_small_icc} against "
                f"{sum(sizes)} observations grouped by {effect_col!r} — the analysis has roughly "
                f"the information of {len(sizes)} unit{'s' if len(sizes) != 1 else ''}, which is the "
                f"number that belongs in the "
                "report"
            )

    # Requirements the class needs the bundle to declare.
    declared = {c.get("id") for c in (bundle.get("design_evidence") or []) if isinstance(c, dict)}
    missing = [r for r in spec.get("requires", []) if r not in declared]
    if missing:
        problems.append(
            f"claim class {spec['id']!r} requires {missing}, which the bundle does not declare "
            "under design_evidence. Each is a thing that must have been done, not a thing that "
            "must be asserted"
        )

    # Conditions the class requires to be STATED, not merely satisfied. This is
    # where the positive-case matrix's "conditional" ceiling lives: expressed as
    # an extra obligation rather than a lower ceiling, because a ceiling can be
    # met by doing nothing and an obligation cannot. See data/claim_classes.json
    # -> ceiling_note for why the frame's CONDITIONAL is not the matrix's.
    stated = " ".join(str(c) for c in (bundle.get("stated_conditions") or [])).lower()
    for condition in spec.get("conditions_that_must_be_stated", []) or []:
        key = condition.split(",")[0].strip().lower()[:28]
        if key not in stated:
            problems.append(
                f"claim class {spec['id']!r} requires this to be stated in "
                f"bundle.stated_conditions and it is not: {condition!r}")
    if "few_cluster_warning" in flags and "few-cluster" not in stated:
        problems.append(
            f"{spec.get('few_cluster_condition', 'few-cluster caveat')} — it must appear in "
            "bundle.stated_conditions, because a caveat nobody is required to write is a caveat "
            "nobody reads")

    # The ceiling: the class ceiling, lowered by anything found here.
    if any(f in {"pseudoreplication", "technical_unit_overclaim",
                 "guide_redundancy_not_biological_replication", "unit_level_mismatch",
                 "condition_confounded_with_unit"} for f in flags):
        ceiling = "REJECTED"
    elif problems:
        ceiling = "CONJECTURE"
    else:
        ceiling = spec["max_status"]

    result = {
        "gate": "denominator",
        "verdict": "pass" if not problems else "fail",
        "claim_class": spec["id"],
        "estimand": estimand,
        "max_status": ceiling,
        "refinement": spec.get("refinement"),
        "conditions_required": spec.get("conditions_that_must_be_stated", []),
        "class_ceiling": spec["max_status"],
        "experimental_unit": {"column": unit_col, "level": level},
        "column_classification": classified,
        "unclassified_columns": [c for c, l in classified.items() if l == "unclassified"],
        "crossing": unit_summary,
        "observations": len(rows),
        "upstream_units": len(sizes),
        "design_effect": design_effect,
        "design_effect_computed_at": effect_col,
        "flags": flags,
        "notes": notes,
        "problems": problems,
        "failure_class": flags[0] if flags else ("design_insufficient" if problems else None),
    }
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
