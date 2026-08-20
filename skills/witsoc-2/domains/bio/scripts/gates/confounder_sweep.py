#!/usr/bin/env python3
"""Confounder-sweep gate — was every cheap alternative explanation actually tested?

Blocking from the executable tier up. A perturbation result competes against a
short list of explanations that are always available and mostly cheap to check:
batch, depth, guide capture, doublets, ambient RNA, cell cycle, generic stress,
composition shift, selection, off-target, pathway circularity, context reversal.

The list is in `data/confounders.json` with the cheap test for each, because a
confounder named without a test is a caveat, and caveats do not change verdicts.

Three severities, and they behave differently:

    fatal_if_complete   a confounder that is *completely* confounded with
                        treatment is unfixable by analysis. Nothing downstream
                        matters.
    fatal_if_dominant   generic stress that moves as much as the claimed pathway
                        means the claim is not specific, whatever its p-value.
    major               must be addressed with a result, not an intention.
    scope_limiting      does not block, but bounds what may be said.

A confounder marked `addressed` with no `result` is treated as unaddressed. That
is the single most common way this check gets defeated, so it is the one thing
it looks at hardest.

Usage:  confounder_sweep.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
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
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2

    table = bl.load_table("confounders.json")
    catalogue = {c["id"]: c for c in table["confounders"]}
    addressed = {}
    for entry in bundle.get("confounders_addressed") or []:
        if isinstance(entry, dict) and entry.get("id"):
            addressed[entry["id"]] = entry

    problems, scope_notes = [], []

    for cid, spec in catalogue.items():
        entry = addressed.get(cid)
        severity = spec["severity"]
        if entry is None:
            if severity == "scope_limiting":
                scope_notes.append(f"{cid}: not examined — {spec['question']}")
            else:
                problems.append(
                    f"{cid} not addressed. {spec['question']} Cheap test: {spec['cheap_test']}")
            continue
        result = (entry.get("result") or "").strip()
        verdict = (entry.get("verdict") or "").strip().lower()
        if not result:
            problems.append(
                f"{cid} is marked addressed with no recorded result. An intention to check is "
                "not a check; write down what the test returned")
            continue
        if severity == "fatal_if_complete" and verdict in {"confounded", "complete", "fatal"}:
            problems.append(
                f"{cid} is completely confounded with treatment ({result[:80]}). No analysis "
                "separates them — this is a design failure, not a modelling problem")
        if severity == "fatal_if_dominant" and verdict in {"dominant", "fatal"}:
            problems.append(
                f"{cid} explains as much as the claimed effect ({result[:80]}). The response is "
                "not specific to the perturbation, whatever its significance")
        if severity == "fatal_if_circular" and verdict in {"circular", "fatal"}:
            problems.append(
                f"{cid}: the gene set was defined using this data ({result[:80]}). The result is "
                "circular and the pathway statement carries no information")
        if verdict in {"unresolved", "unknown"} and severity != "scope_limiting":
            problems.append(f"{cid} was examined and left unresolved ({result[:80]})")
        if severity == "scope_limiting" and verdict not in {"clear", "resolved"}:
            scope_notes.append(f"{cid}: {result[:100]}")

    controls = {c.get("id") for c in bundle.get("negative_controls") or []
                if isinstance(c, dict)}
    for required in table["required_negative_controls"]:
        if required["id"] not in controls:
            problems.append(
                f"negative control {required['id']!r} is absent — {required['why']}. A pipeline "
                "never asked to find nothing has never demonstrated it can")

    for note in scope_notes:
        print(f"  scope: {note}")
    if problems:
        print(f"fail: {len(problems)} confounder problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: {len(catalogue)} confounders addressed with recorded results, "
          f"{len(controls)} negative control(s) present")
    if scope_notes:
        print("  scope-limiting findings above must appear in the report's bounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
