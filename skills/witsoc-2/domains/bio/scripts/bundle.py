#!/usr/bin/env python3
"""Bundle — assemble the skeleton of an audit bundle from the data in hand.

A bundle is about two hundred lines of JSON and every field of it exists so some
check can fail. Writing one by hand is the reason a careful person skips the
audit, and a check that only runs when someone is feeling thorough is a check
that runs on the results nobody doubted.

So this builds the skeleton: it reads the metadata table, classifies the columns
against the unit taxonomy, proposes the experimental unit, pre-fills the
confounder list with the cheap test for each, wires the negative-control split,
and leaves **every result blank**. What it hands back is a form whose questions
are already the right ones.

The thing it will not do is answer them. Each `confounders_addressed` entry
arrives with `result: ""` and the sweep gate treats a blank result as
unaddressed, which is the entire point — a skeleton that pre-filled plausible
answers would convert the audit into a formality in one step, and it would be a
convincing formality because the questions really were the right ones.

Usage:
    bundle.py --self-test
    bundle.py --metadata <file.csv> --claim <claim.json> [--out <bundle.json>]
    bundle.py --metadata <file.csv> --statement "..." --class <claim_class>
              [--out <bundle.json>]

Exit: 0 skeleton written, 1 written with a design shortfall named, 2 usage/IO.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402


def negative_control_proposal(rows, proposed: dict, spec: dict) -> dict:
    """Propose the control-against-itself split from the data.

    This is the single most valuable check in the pack and the one most likely
    to be skipped, because it asks the author to invent a unit that does not
    exist in their metadata. So it is proposed here instead: split each control
    unit's observations in half, deterministically, and test the halves against
    each other. Two halves of one control condition differ by nothing, so a
    pipeline that finds a difference between them is measuring its own structure.

    The split is by row order within unit rather than at random, so it is
    reproducible from the metadata alone and nobody has to store a seed.
    """
    unit_col = proposed.get("unit_column")
    label_col = proposed.get("label_column")
    if not unit_col or not label_col:
        return {"unit_column": "FILL-ME", "label_column": "FILL-ME", "labels": ["a", "b"],
                "_why": "no unit or label column was identified, so no split can be proposed"}

    labels = [(r.get(label_col) or "").strip() for r in rows]
    distinct = sorted({l for l in labels if l})
    counts = {u: sum(1 for r in rows if (r.get(unit_col) or "").strip() == u)
              for u in {(r.get(unit_col) or "").strip() for r in rows} if u}
    smallest = min(counts.values()) if counts else 0

    proposal = {
        "unit_column": "nc_unit",
        "label_column": "nc_split",
        "labels": ["a", "b"],
        "_how_to_build": (
            f"add two columns to the metadata: `nc_split` alternating 'a'/'b' by row order "
            f"WITHIN each {unit_col}, and `nc_unit` = {unit_col} + '_' + nc_split, both left "
            f"empty for rows whose {label_col} is not the control condition"),
        "_candidate_control_labels": distinct,
        "_why": ("the control condition tested against itself must come back silent. A pipeline "
                 "never asked to find nothing has never shown that it can, and this is the check "
                 "most likely to fire on a sincere, careful, subtly broken analysis"),
    }
    if smallest and smallest < 4:
        proposal["_warning"] = (
            f"the smallest {unit_col} has {smallest} observation(s); halving it leaves too few "
            "to test. A negative control that cannot fail carries no information, and its pass "
            "looks exactly like a real one")
    return proposal


def propose_columns(classified: dict, taxonomy: dict) -> dict:
    """Which column plays which role, proposed and clearly labelled as a guess."""
    def first(level):
        return next((c for c, l in classified.items() if l == level), None)

    biological = first("biological_replicate_candidate")
    return {
        "biological_unit_column": biological,
        "unit_column": biological,
        "label_column": first("condition_or_time"),
        "stratum_column": biological,
        "observation_column": first("observation_unit"),
        "technical_columns": [c for c, l in classified.items()
                              if l in {"technical_process_unit", "screen_process_unit"}],
        "unclassified": [c for c, l in classified.items() if l == "unclassified"],
    }


def self_test() -> int:
    """Two properties, and the second is the one that matters.

    A skeleton must be WELL-FORMED — it passes the structural tier unaided, so
    the person filling it in is not also debugging it. And it must NOT PASS the
    adapter, because every answer in it is blank. A skeleton that passed would
    mean the audit can be satisfied by generating a file, which is the failure
    this whole pack exists to prevent, arriving through the front door.
    """
    import subprocess
    import tempfile

    here = Path(__file__).resolve().parent
    control = here / "negative_control"
    failures = []
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for name in ("good_metadata.csv", "good_claim.json"):
            (tmp / name).write_bytes((control / name).read_bytes())
        skeleton = tmp / "skeleton.json"
        code = subprocess.run(
            [sys.executable, str(here / "bundle.py"), "--metadata", str(tmp / "good_metadata.csv"),
             "--claim", str(tmp / "good_claim.json"), "--out", str(skeleton)],
            capture_output=True, text=True).returncode
        if code not in (0, 1) or not skeleton.exists():
            print("  MISS  the skeleton was not written")
            return 1

        structural = subprocess.run(
            [sys.executable, str(here / "tiers" / "structural.py"), str(skeleton),
             "--claim", str(tmp / "good_claim.json")], capture_output=True, text=True)
        ok = structural.returncode == 0
        print(f"  {'ok  ' if ok else 'MISS'}  the skeleton passes the structural tier unaided")
        print("          whoever fills it in is not also debugging it")
        if not ok:
            failures.append(f"structural rejected the skeleton: {structural.stdout[:300]}")

        adapter = subprocess.run(
            [sys.executable, str(here / "check.py"), "--artifact", str(skeleton),
             "--claim", str(tmp / "good_claim.json"), "--tier", "structural"],
            capture_output=True, text=True)
        refused = adapter.returncode != 0
        print(f"  {'ok  ' if refused else 'MISS'}  the adapter refuses it while the answers "
              "are blank")
        print("          an audit satisfied by generating a file is not an audit")
        if not refused:
            failures.append("the adapter accepted an entirely unanswered skeleton")

    print("\n" + "=" * 62)
    if failures:
        print(f"  BUNDLE SELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print("  BUNDLE SELF-TEST: PASS — well-formed, and empty until answered")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--metadata")
    ap.add_argument("--claim")
    ap.add_argument("--statement")
    ap.add_argument("--class", dest="claim_class")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.metadata:
        ap.error("--metadata is required unless --self-test")

    path = Path(args.metadata)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2

    claim = {}
    if args.claim:
        try:
            claim = bl.read_json(args.claim)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    claim_class = args.claim_class or claim.get("claim_class")
    statement = args.statement or claim.get("exact_statement") or claim.get("statement", "")
    if not claim_class:
        print("ERROR: supply --class or a --claim carrying claim_class", file=sys.stderr)
        return 2

    table = bl.load_table("claim_classes.json")
    spec = next((c for c in table["classes"] if c["id"] == claim_class), None)
    if spec is None:
        print(f"ERROR: unknown claim class {claim_class!r}", file=sys.stderr)
        return 2

    fields, rows = bl.read_csv(path)
    classified = bl.classify_columns(fields)
    taxonomy = bl.load_table("unit_taxonomy.json")["levels"]
    proposed = propose_columns(classified, taxonomy)
    confounders = bl.load_table("confounders.json")

    # Run the diagnostics that need nothing but this table.
    computed: dict = {}
    if proposed.get("label_column") and proposed.get("unit_column"):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "diagnostics.py"),
             "--metadata", str(path), "--label", proposed["label_column"],
             "--unit", proposed["unit_column"], "--emit-confounders", "--json"],
            capture_output=True, text=True)
        try:
            diag = json.loads(proc.stdout)
            for row in diag.get("confounders_addressed", []):
                existing = computed.get(row["id"])
                if existing is None or row["verdict"] != "clear":
                    computed[row["id"]] = {"result": row["result"], "verdict": row["verdict"],
                                           "computed_by": "scripts/diagnostics.py"}
        except json.JSONDecodeError:
            pass

    shortfall = []
    unit = proposed["biological_unit_column"]
    if spec["estimand"] == "population" and not unit:
        shortfall.append(
            "no biological replicate column exists in this table, so a population claim is not "
            "reachable from these data by any analysis")
    elif unit:
        n = len(bl.upstream_units(rows, unit))
        minimum = spec.get("min_upstream_units", 0)
        if n < minimum:
            shortfall.append(f"{unit!r} provides {n} unit(s); class {claim_class!r} needs "
                             f"{minimum}")

    bundle = {
        "schema": "bio-audit-bundle-v1",
        "_generated": ("skeleton from scripts/bundle.py. Every result below is BLANK on purpose: "
                       "a blank result is treated as unaddressed by the confounder sweep, and a "
                       "skeleton that guessed plausible answers would turn the audit into a "
                       "convincing formality."),
        "claim_id": claim.get("claim_id", "FILL-ME"),
        "target_sha256": claim.get("target_sha256", ""),
        "analysed_context": claim.get("biological_context") and {
            "biological_context": claim.get("biological_context"),
            "perturbation": {k: v for k, v in (claim.get("perturbation") or {}).items()
                             if k in {"entity", "modality", "dose", "duration"}},
            "assay": {k: v for k, v in (claim.get("assay") or {}).items()
                      if k in {"type", "readout", "experimental_unit"}},
            "dataset": {k: v for k, v in (claim.get("dataset") or {}).items()
                        if k in {"id", "version"}},
        } or {"_fill": "restate the context this analysis actually used"},
        "evidence_graph": {
            "nodes": [{"id": "S1", "kind": "source"}, {"id": "D1", "kind": "dataset"},
                      {"id": "A1", "kind": "assay"}, {"id": "R1", "kind": "replicate"},
                      {"id": "C1", "kind": "control"}, {"id": "AN1", "kind": "analysis"},
                      {"id": "E1", "kind": "endpoint"}, {"id": "CL1", "kind": "claim"}],
            "edges": [["S1", "D1"], ["D1", "A1"], ["A1", "R1"], ["C1", "AN1"],
                      ["R1", "AN1"], ["AN1", "E1"], ["E1", "CL1"]],
        },
        "data": {
            "metadata_csv": path.name,
            "value_column": "FILL-ME: the column holding the measured endpoint",
            "unit_column": proposed["unit_column"] or "FILL-ME",
            "biological_unit_column": proposed["biological_unit_column"] or "FILL-ME",
            "label_column": proposed["label_column"] or "FILL-ME",
            "treatment_label": "FILL-ME",
            "control_label": "FILL-ME",
            "stratum_column": proposed["stratum_column"],
            "negative_control": negative_control_proposal(rows, proposed, spec),
        },
        "_column_classification": classified,
        "_proposed_by_the_taxonomy": proposed,
        "design_evidence": [{"id": r, "detail": "FILL-ME"} for r in spec.get("requires", [])],
        "stated_conditions": list(spec.get("conditions_that_must_be_stated", [])),
        "preregistration": {"path": "FILL-ME.json", "sha256": "", "alpha": 0.05,
                            "estimand": "FILL-ME: the quantity, population, and intervention",
                            "primary_metric": "FILL-ME"},
        "source_ledger": [{"id": "S1", "kind": "dataset", "accession": "FILL-ME", "state": "ok"}],
        "elements_requiring_provenance": ["dataset.version", "biological_context.cell_type"],
        "provenance_trace": [{"claim_element": "dataset.version", "source_id": "S1"}],
        "contradiction_ledger": {"searched_and_found_none": False, "queries": [], "entries": []},
        # Three of the twelve are computable from this table, so they arrive
        # computed. The rest arrive blank, and blank means unaddressed — a
        # skeleton that pre-filled plausible answers would convert the audit into
        # a formality in one step, and a convincing one, because the questions
        # really were the right ones.
        "confounders_addressed": [
            {"id": c["id"], "question": c["question"], "cheap_test": c["cheap_test"],
             **(computed.get(c["id"]) or {"result": "", "verdict": ""})}
            for c in confounders["confounders"]],
        "negative_controls": [{"id": c["id"], "detail": "FILL-ME", "_why": c["why"]}
                              for c in confounders["required_negative_controls"]],
        "statistical_audit": {
            "estimand": "FILL-ME",
            "identifiability": "FILL-ME: what must hold for the estimate to mean the estimand",
            "uncertainty": "FILL-ME: at the estimand-matching denominator, method named",
            "multiplicity": "FILL-ME: how many comparisons, and what the correction controls",
            "power": {"minimum_detectable_effect": None,
                      "_how": "run scripts/power.py once the columns above are filled in"},
            "prespecification": "FILL-ME",
        },
        "evidence_tiers_available": [],
        "stated_bounds": claim.get("allowed_scope", "FILL-ME"),
        "interpretation": statement or "FILL-ME",
    }

    text = json.dumps(bundle, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")

    if args.json:
        print(text)
    else:
        blanks = text.count("FILL-ME")
        print(f"BUNDLE SKELETON for {claim_class}")
        print(f"  metadata          {path.name}: {len(rows)} rows, {len(fields)} columns")
        print(f"  proposed unit     {proposed['biological_unit_column'] or '(none found)'}")
        print(f"  proposed label    {proposed['label_column'] or '(none found)'}")
        if proposed["unclassified"]:
            print(f"  unclassified      {proposed['unclassified']}  <- levels nobody has "
                  "thought about; the wrong denominator usually hides in one")
        print(f"  confounder rows   {len(bundle['confounders_addressed'])}, every result blank")
        print(f"  blanks to fill    {blanks}")
        if args.out:
            print(f"  written           {args.out}")
        for item in shortfall:
            print(f"  SHORTFALL: {item}")
        print("\n  Next: fill the blanks, then")
        print("    python3 scripts/power.py --metadata ... --unit ... --value ...")
        print("    python3 scripts/check.py --artifact <bundle> --claim <claim> --tier structural")
    return 1 if shortfall else 0


if __name__ == "__main__":
    sys.exit(main())
