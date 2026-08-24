#!/usr/bin/env python3
"""Everything this bundle still owes, in one answer.

Building a bundle for a real claim took EIGHT rounds of plumbing: a field named
`claim_element` and not `element`, a resolution spelled `unresolved_nonfatal`
and not `unresolved-nonfatal`, a metadata column the negative control needs and
nothing had asked for, a `--context` that had to be JSON. Each gate reported its
own failure, one at a time, and every round cost a full adapter run to learn one
field name.

That is teaching a format by rejection, and it is the most expensive way anybody
has ever learned a schema. It also selects for the wrong people: the pack
becomes usable by whoever wrote it and nobody else.

So this runs every gate in report-only mode and returns ONE list — what is
missing, where it goes, and the exact shape it has to take. It never says a
bundle is good: passing here means the gates have nothing left to ask for, and
what the gates ask for is the floor rather than the standard.

Usage:
    missing.py <bundle.json> --claim <claim.json> [--tier executable] [--json]

Exit: 0 nothing outstanding, 1 items outstanding, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import biolib as bl  # noqa: E402
import check as adapter  # noqa: E402

# The shapes a gate will not tell you until it refuses you. Each entry is a
# field the bundle needs, where it goes, and an example of the exact form —
# because "provenance_trace is incomplete" and "provenance_trace takes
# {claim_element, source_id, how}" are different amounts of help.
SHAPES = {
    "provenance_trace": {
        "where": "bundle.provenance_trace[]",
        "shape": {"claim_element": "biological_context.cell_type",
                  "source_id": "an id from source_ledger",
                  "how": "how that element was established from that source"},
        "note": "the key is `claim_element`, not `element`. Every entry in "
                "`elements_requiring_provenance` needs one"},
    "contradiction_ledger": {
        "where": "bundle.contradiction_ledger[]",
        "shape": {"source_id": "...", "finding": "what it says that disagrees",
                  "resolution": "resolved | unresolved_fatal | unresolved_nonfatal",
                  "differing_dimension": "the axis on which it differs",
                  "reason": "why that difference explains the disagreement"},
        "note": "underscores, not hyphens. An empty ledger needs a recorded, "
                "exhausted search or it is an absence nobody looked for"},
    "statistical_audit": {
        "where": "bundle.statistical_audit",
        "shape": {"estimand": "...", "identifiability": "...", "uncertainty": "...",
                  "prespecification": "...", "multiplicity": "...", "power": "...",
                  "specification_sensitivity": "..."},
        "note": "`uncertainty` and `power` are the key names; scripts/power.py and "
                "scripts/multiverse.py compute the last three"},
    "confounders_addressed": {
        "where": "bundle.confounders_addressed[]",
        "shape": {"id": "an id from data/confounders.json", "verdict": "clear | ...",
                  "result": "what the check returned", "computed_by": "optional tool"},
        "note": "eight of twelve are computable; pin the tool output under "
                "data.diagnostics and the sweep takes the computed verdict"},
    "data": {
        "where": "bundle.data",
        "shape": {"metadata_csv": "relative to the bundle", "value_column": "...",
                  "unit_column": "...", "label_column": "...",
                  "treatment_label": "...", "control_label": "...",
                  "negative_control": {"unit_column": "...", "label_column": "...",
                                       "labels": ["a", "b"]}},
        "note": "the negative-control columns must EXIST in the metadata table: the "
                "control condition split against itself is what the tier runs"},
}


def outstanding(bundle_path: Path, claim_path: Path, tier: str) -> dict:
    claim = bl.read_json(claim_path)
    results = adapter.run_gates(bundle_path, claim_path, tier)

    items: list[dict] = []
    for entry in results:
        if entry["verdict"] not in {"fail", "error"}:
            continue
        detail = str(entry.get("detail") or "")
        # Name the field the gate is really about, so the answer is a shape and
        # not a sentence about a shape.
        field = next((f for f in SHAPES if f in detail or f.replace("_", " ") in detail), None)
        if field is None:
            field = {"provenance-trace": "provenance_trace",
                     "contradiction-ledger": "contradiction_ledger",
                     "statistical-audit": "statistical_audit",
                     "confounder-sweep": "confounders_addressed"}.get(entry["gate"])
        item = {"gate": entry["gate"], "says": detail[:220]}
        if field and field in SHAPES:
            item.update({"field": field, **SHAPES[field]})
        items.append(item)

    # Columns the declared analysis needs and the table does not have — the one
    # class of problem that costs a whole adapter run to discover.
    bundle = bl.read_json(bundle_path)
    data = bundle.get("data") or {}
    csv_rel = data.get("metadata_csv")
    if csv_rel:
        csv_path = (bundle_path.parent / csv_rel)
        if csv_path.exists():
            fields, _rows = bl.read_csv(csv_path)
            wanted = {k: data.get(k) for k in
                      ("value_column", "unit_column", "biological_unit_column",
                       "label_column", "stratum_column")}
            nc = data.get("negative_control") or {}
            wanted["negative_control.unit_column"] = nc.get("unit_column")
            wanted["negative_control.label_column"] = nc.get("label_column")
            for key, column in wanted.items():
                if column and column not in fields:
                    items.append({
                        "gate": "data (pre-flight)", "field": f"data.{key}",
                        "says": f"the bundle names column {column!r} and {csv_path.name} has "
                                f"{fields}",
                        "where": csv_path.name,
                        "note": "add the column or point the bundle at the one that exists; "
                                "this is the class of problem that otherwise costs a whole "
                                "tier run to discover"})
        else:
            items.append({"gate": "data (pre-flight)", "field": "data.metadata_csv",
                          "says": f"{csv_rel!r} does not resolve beside the bundle",
                          "where": str(bundle_path.parent), "note": "paths are relative to the "
                                                                   "bundle, not the cwd"})
    return {"tier": tier, "outstanding": items,
            "gates_run": len(results), "gates_clean": sum(
                1 for r in results if r["verdict"] not in {"fail", "error"}),
            "reading": ("nothing outstanding: every gate has what it asks for. That is the "
                        "floor, not the standard — the gates check that the evidence is "
                        "PRESENT and the tiers check what it says"
                        if not items else
                        f"{len(items)} item(s) outstanding, with the field and shape for each")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle"); ap.add_argument("--claim", required=True)
    ap.add_argument("--tier", default="executable")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        out = outstanding(Path(args.bundle), Path(args.claim), args.tier)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(out, indent=2))
        return 1 if out["outstanding"] else 0
    print(f"MISSING at tier {out['tier']}: {out['reading']}\n")
    for item in out["outstanding"]:
        print(f"  {item['gate']}")
        print(f"    says   {item['says'][:150]}")
        if item.get("where"):
            print(f"    goes   {item['where']}")
        if item.get("shape"):
            print(f"    shape  {json.dumps(item['shape'])[:180]}")
        if item.get("note"):
            print(f"    note   {item['note'][:150]}")
        print()
    return 1 if out["outstanding"] else 0


if __name__ == "__main__":
    sys.exit(main())
