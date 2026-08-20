#!/usr/bin/env python3
"""Design — what experiment WOULD support this claim.

The denominator gate can tell you a design is wrong. It cannot tell you what
would be right, and for most of this pack's life that was the whole of its
contribution: a machine that says no, precisely, and offers nothing.

This is the inverse. Given a claim class and, optionally, the metadata that
exists, it emits the design that would support the claim: which unit carries it,
how many are needed, crossed against what, which controls, and what effect size
that design could actually detect. Everything it needs is already in
`data/claim_classes.json` — the table was only ever read in the demoting
direction.

Two things it will not do:

**It will not lower the claim to fit the data.** If the available metadata
cannot support the class, it says what is missing and how much of it, rather
than proposing the narrower claim the data happens to support. Choosing a
smaller claim is a decision about what you want to know, and it belongs to
whoever is asking, not to the tool that noticed the shortfall.

**It will not promise the design works.** A design that clears the class
requirements can still fail for reasons no table anticipates. What it clears is
the bar for being able to speak about the unit at all.

Usage:
    design.py --class <claim_class> [--metadata <file.csv>] [--json]
    design.py --list
    design.py --claim <claim.json> [--metadata <file.csv>]

Exit: 0 the design is achievable with what exists, 1 a shortfall is named,
      2 usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402

# What each requirement means as an instruction, rather than as a label to check
# off. The gate reads these names; this file is where they say what to do.
REQUIREMENT_ACTIONS = {
    "independent_upstream_units": "recruit units that are independent of each other — different "
                                  "donors, animals, or patients, not more cells from the same one",
    "replicate_aware_analysis": "aggregate to the unit before testing, or use a model that carries "
                                "the cluster structure. Correcting afterwards does not work",
    "confounder_sensitivity": "cross-tabulate treatment against every technical level first; a "
                              "zero cell ends the design before any sample is collected",
    "guide_assignment": "record which guide each observation carries, and the capture rate",
    "matched_controls": "non-targeting controls in the same units and the same batches",
    "guide_capture": "report assignment rate and multiplet rate per group",
    "perturbation_efficacy": "measure that the perturbation hit its target; an unverified "
                             "perturbation makes a null result uninterpretable",
    "multiple_guides_per_target": "at least two independent guides per target, agreeing in sign",
    "batch_aware_uncertainty": "batch enters the model; it is not averaged away",
    "spatial_autocorrelation_control": "neighbouring spots are not independent; account for it",
    "stated_identifying_assumptions": "write the assumptions down individually, before the analysis",
    "assumption_sensitivity": "show what the conclusion does when each assumption is wrong",
    "baseline_battery": "compute control_mean, global_mean, mean_delta, and (for combinations) "
                        "additive, before looking at the model",
    "clean_split": "hold out on the axis the claim is about, and check the held-out set really is",
    "metric_panel": "compute the whole panel, including the metrics that will look bad",
    "prespecified_thresholds": "fix the thresholds before seeing any result",
    "source_ledger": "pin every source by accession, DOI, or URL",
    "depth_control": "compare sequencing depth across groups before interpreting any difference",
}


def describe(spec: dict) -> dict:
    minimum = spec.get("min_upstream_units", 0)
    few = spec.get("few_cluster_warning_below")
    design = {
        "claim_class": spec["id"],
        "label": spec["label"],
        "estimand": spec["estimand"],
        "unit_that_carries_the_claim": spec["minimum_units"],
        "analysis_denominator": spec["denominator"],
        "minimum_independent_units": minimum,
        "comfortable_units": few or max(minimum, 3),
        "crossing": ("each unit must appear under both conditions, or the contrast is between "
                     "units rather than within them"
                     if spec["estimand"] == "population"
                     else "assignment-level units are not crossed with condition by construction; "
                          f"the bar is {spec.get('min_units_per_arm', 2)} independent units per arm"),
        "ceiling_if_met": spec["max_status"],
        "must_be_stated": spec.get("conditions_that_must_be_stated", []),
        "requirements": [{"id": r, "do": REQUIREMENT_ACTIONS.get(r, "see doctrine")}
                         for r in spec.get("requires", [])],
        "common_failure": spec["common_failure"],
    }
    if few and minimum < few:
        design["few_cluster_note"] = (
            f"between {minimum} and {few} units the design is legal and the uncertainty is "
            "unreliable; the report carries an explicit few-cluster caveat")
    return design


def against_metadata(spec: dict, csv_path: Path) -> dict:
    """What the data in hand can and cannot support. Never proposes a smaller claim."""
    fields, rows = bl.read_csv(csv_path)
    classified = bl.classify_columns(fields)
    taxonomy = bl.load_table("unit_taxonomy.json")["levels"]
    biological = [c for c, level in classified.items()
                  if taxonomy.get(level, {}).get("supports_population_claim")]

    assessment = {"columns": classified, "observations": len(rows),
                  "biological_unit_candidates": biological, "shortfall": []}

    if spec["estimand"] == "population" and not biological:
        assessment["shortfall"].append(
            "no column in this table is a biological replicate level. A population claim is not "
            "reachable from these data by any analysis — it needs different data, not a different "
            "model")
        return assessment

    best, best_count = None, 0
    for column in (biological or list(classified)):
        units = bl.upstream_units(rows, column)
        if len(units) > best_count:
            best, best_count = column, len(units)
    assessment["strongest_unit_column"] = best
    assessment["units_available"] = best_count

    minimum = spec.get("min_upstream_units", 0)
    if best_count < minimum:
        assessment["shortfall"].append(
            f"class {spec['id']!r} needs {minimum} independent units; {best!r} provides "
            f"{best_count}. The gap is {minimum - best_count} more unit(s), which is a "
            "collection problem")
    few = spec.get("few_cluster_warning_below")
    if few and minimum <= best_count < few:
        assessment["few_cluster"] = (
            f"{best_count} units clears the floor and sits below {few}: legal, with an explicit "
            "caveat, and uncomfortable")
    return assessment


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--class", dest="claim_class")
    ap.add_argument("--claim")
    ap.add_argument("--metadata")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    table = bl.load_table("claim_classes.json")
    classes = {c["id"]: c for c in table["classes"]}

    if args.list:
        for cid, spec in classes.items():
            print(f"  {cid:<34} ceiling {spec['max_status']:<16} "
                  f"min units {spec.get('min_upstream_units', 0)}")
            print(f"  {'':34} {spec['label']}")
        return 0

    claim_class = args.claim_class
    if args.claim:
        try:
            claim_class = bl.read_json(args.claim).get("claim_class")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    if claim_class not in classes:
        print(f"ERROR: --class must be one of {sorted(classes)}", file=sys.stderr)
        return 2

    spec = classes[claim_class]
    design = describe(spec)
    if args.metadata:
        path = Path(args.metadata)
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 2
        design["against_available_data"] = against_metadata(spec, path)

    shortfall = (design.get("against_available_data") or {}).get("shortfall", [])

    if args.json:
        print(json.dumps(design, indent=2))
        return 1 if shortfall else 0

    print(f"DESIGN for {design['claim_class']}  —  {design['label']}")
    print(f"  estimand              {design['estimand']}")
    print(f"  unit carrying it      {design['unit_that_carries_the_claim']}")
    print(f"  analysis denominator  {design['analysis_denominator']}")
    print(f"  units needed          {design['minimum_independent_units']} minimum, "
          f"{design['comfortable_units']} comfortable")
    print(f"  crossing              {design['crossing']}")
    print(f"  ceiling if met        {design['ceiling_if_met']}")
    print(f"  usual failure         {design['common_failure']}")
    if design.get("few_cluster_note"):
        print(f"  note                  {design['few_cluster_note']}")
    print("\n  What must be done:")
    for requirement in design["requirements"]:
        print(f"    - {requirement['id']}: {requirement['do']}")
    for condition in design["must_be_stated"]:
        print(f"    - state explicitly: {condition}")

    if "against_available_data" in design:
        data = design["against_available_data"]
        print(f"\n  Against the data in hand ({data['observations']} rows):")
        print(f"    strongest unit column   {data.get('strongest_unit_column')} "
              f"({data.get('units_available')} units)")
        if data.get("few_cluster"):
            print(f"    {data['few_cluster']}")
        for item in data["shortfall"]:
            print(f"    SHORTFALL: {item}")
        if not data["shortfall"]:
            print("    this design is reachable from these data")
    return 1 if shortfall else 0


if __name__ == "__main__":
    sys.exit(main())
