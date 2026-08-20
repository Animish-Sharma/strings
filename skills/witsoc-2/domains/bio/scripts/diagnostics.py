#!/usr/bin/env python3
"""Design diagnostics — compute the cheap confounder tests instead of asking for them.

`data/confounders.json` names the cheap test for each alternative explanation,
and the sweep gate then asks the author to have run it and written down the
result. That is the right demand and it left the work undone: an author facing
twelve blank `result` fields fills in what they remember, and what they remember
is what they expected.

Three of those tests need nothing but the metadata table, and all three are
computable here:

    batch confounding    cross-tabulate the condition against every technical
                         level. A ZERO CELL is fatal and no analysis fixes it —
                         treatment and that level are the same variable.
    depth                compare the observation count per unit and per arm.
                         A difference in how much was measured explains
                         differences in what was measured.
    unit balance         how many observations per unit, and how uneven. One
                         unit carrying half the data means the estimate is
                         mostly that unit.

It fills them in with numbers and a verdict, and leaves everything it cannot
compute blank — a diagnostic that guessed at ambient RNA would be worse than the
blank, because the blank is honest and the guess would clear the gate.

Usage:
    diagnostics.py --metadata <file.csv> --label <col> --unit <col>
                   [--technical <col> ...] [--emit-confounders] [--json]

Exit: 0 nothing fatal, 1 a fatal confound, 2 usage/IO
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402


def cross_tab(rows, label_col: str, other_col: str) -> dict:
    table: dict[str, dict[str, int]] = {}
    for row in rows:
        a = (row.get(label_col) or "").strip()
        b = (row.get(other_col) or "").strip()
        if a and b:
            table.setdefault(b, {}).setdefault(a, 0)
            table[b][a] += 1
    conditions = sorted({c for counts in table.values() for c in counts})
    empty = [(level, cond) for level, counts in table.items()
             for cond in conditions if counts.get(cond, 0) == 0]
    complete = bool(table) and len(empty) == len(table) * len(conditions) - len(table)
    return {"column": other_col, "levels": len(table), "conditions": conditions,
            "table": table, "empty_cells": empty,
            "completely_confounded": complete and len(conditions) > 1,
            "verdict": ("confounded" if empty and len(conditions) > 1 else "clear"),
            "reading": ("a zero cell means the condition and this level cannot be separated by "
                        "any analysis — it is a design failure, not a modelling problem"
                        if empty else
                        "every condition appears at every level of this column")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--technical", nargs="*", default=[])
    ap.add_argument("--emit-confounders", action="store_true",
                    help="print rows ready to paste into a bundle's confounders_addressed")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = Path(args.metadata)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 2
    fields, rows = bl.read_csv(path)
    classified = bl.classify_columns(fields)

    technical = args.technical or [c for c, level in classified.items()
                                   if level in {"technical_process_unit", "screen_process_unit"}]

    batch = [cross_tab(rows, args.label, column) for column in technical]
    fatal = [b for b in batch if b["empty_cells"] and len(b["conditions"]) > 1]

    per_unit: dict[str, int] = {}
    unit_arm: dict[str, str] = {}
    for row in rows:
        unit = (row.get(args.unit) or "").strip()
        if not unit:
            continue
        per_unit[unit] = per_unit.get(unit, 0) + 1
        unit_arm.setdefault(unit, (row.get(args.label) or "").strip())
    counts = sorted(per_unit.values())
    # Count observations per arm directly. Labelling each unit by the first arm
    # it appears in loses every unit that contributes to both — which in a
    # crossed design is all of them, and the first version reported one arm and
    # called the design balanced.
    by_arm: dict[str, list[int]] = {}
    arm_totals: dict[str, int] = {}
    for row in rows:
        arm = (row.get(args.label) or "").strip()
        if arm:
            arm_totals[arm] = arm_totals.get(arm, 0) + 1
    for arm, total in arm_totals.items():
        by_arm[arm] = [total]

    depth = {
        "observations_per_unit": {"min": counts[0] if counts else 0,
                                  "max": counts[-1] if counts else 0,
                                  "median": counts[len(counts) // 2] if counts else 0},
        "observations_per_arm": {arm: v[0] for arm, v in by_arm.items()},
        "largest_unit_share": (round(counts[-1] / sum(counts), 3) if counts else 0),
    }
    depth["verdict"] = "clear"
    depth["reading"] = "observation counts are comparable across arms and units"
    means = list(depth["observations_per_arm"].values())
    if means and max(means) > 1.5 * min(means):
        depth["verdict"] = "imbalanced"
        depth["reading"] = ("one arm carries substantially more observations than the other. A "
                            "difference in how much was measured explains differences in what "
                            "was measured")
    if depth["largest_unit_share"] > 0.5:
        depth["verdict"] = "imbalanced"
        depth["reading"] = (f"one unit carries {depth['largest_unit_share']:.0%} of the "
                            "observations, so the estimate is mostly that unit")

    result = {"metadata": path.name, "observations": len(rows),
              "technical_columns_checked": technical,
              "batch": batch, "depth": depth,
              "fatal": [b["column"] for b in fatal]}

    if args.emit_confounders:
        rowsout = []
        for b in batch:
            rowsout.append({"id": "batch", "result":
                            f"cross-tabulated {args.label} against {b['column']}: "
                            f"{len(b['empty_cells'])} empty cell(s) across {b['levels']} level(s)",
                            "verdict": "confounded" if b["empty_cells"] else "clear"})
        rowsout.append({"id": "depth", "result":
                        f"observations per unit {depth['observations_per_unit']}, per arm "
                        f"{depth['observations_per_arm']}", "verdict": depth["verdict"]})
        result["confounders_addressed"] = rowsout

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"DIAGNOSTICS: {path.name} — {len(rows)} observations\n")
        for b in batch:
            mark = "FATAL" if b["empty_cells"] and len(b["conditions"]) > 1 else "ok   "
            print(f"  [{mark}] {b['column']:<16} {b['levels']} level(s) x "
                  f"{len(b['conditions'])} condition(s), {len(b['empty_cells'])} empty cell(s)")
            if b["empty_cells"]:
                print(f"          {b['reading']}")
        mark = "ok   " if depth["verdict"] == "clear" else "warn "
        print(f"  [{mark}] depth            per-arm {depth['observations_per_arm']}, "
              f"largest unit holds {depth['largest_unit_share']:.0%}")
        print(f"          {depth['reading']}")
        if not technical:
            print("\n  no technical column was identified, so batch confounding was not checked. "
                  "That is a gap: an unchecked confound and a cleared one read the same")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
