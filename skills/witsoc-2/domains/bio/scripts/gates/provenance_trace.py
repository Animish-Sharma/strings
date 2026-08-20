#!/usr/bin/env python3
"""Provenance-trace gate — does every part of the claim come from somewhere?

Blocking, every tier. Two failures live here and they are opposites.

The first is an untraced element: the claim asserts a cell type, a dataset
version, a prior effect size, and nothing in the ledger says where it came from.
In a report this reads exactly like a traced element, which is why it needs a
mechanical check rather than a careful reader.

The second is a poisoned source. A retracted, corrected, or withdrawn paper does
not stop being cited — it stops being *checked*. So a retraction anywhere in the
ledger is a hard blocker on strong status regardless of how peripheral the source
looks, and a correction is a blocker until someone states which direction it cuts.

Preprints and method papers are handled separately: they can establish context
or method and cannot, by themselves, be the independent replication that lifts a
claim. That is a ceiling, not a rejection.

Usage:  provenance_trace.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

BLOCKING_SOURCE_STATES = {"retracted", "withdrawn"}
CAUTION_SOURCE_STATES = {"corrected", "expression_of_concern", "disputed"}
NON_INDEPENDENT_KINDS = {"preprint", "method_paper", "challenge_page", "benchmark_page",
                         "company_blog", "press_release"}


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

    ledger = bundle.get("source_ledger") or []
    trace = bundle.get("provenance_trace") or []
    problems, notes = [], []

    if not ledger:
        print("fail: empty source_ledger. Nothing in this bundle can be traced to anything")
        return 1

    known = {s.get("id") for s in ledger if isinstance(s, dict) and s.get("id")}
    for entry in trace:
        if not isinstance(entry, dict):
            continue
        source_id = entry.get("source_id")
        if source_id not in known:
            problems.append(
                f"claim element {entry.get('claim_element')!r} cites source {source_id!r}, "
                "which is not in the ledger")

    traced_elements = {e.get("claim_element") for e in trace if isinstance(e, dict)}
    for required in bundle.get("elements_requiring_provenance", []) or []:
        if required not in traced_elements:
            problems.append(
                f"claim element {required!r} has no provenance entry. Untraced and traced "
                "elements read identically in a report, which is why this is checked and not "
                "reviewed")

    for source in ledger:
        if not isinstance(source, dict):
            continue
        state = (source.get("state") or "ok").strip().lower()
        sid = source.get("id")
        if state in BLOCKING_SOURCE_STATES:
            problems.append(
                f"source {sid!r} is {state}. A {state} source blocks strong status wherever it "
                "sits in the graph — it stopped being checked, not merely cited")
        elif state in CAUTION_SOURCE_STATES:
            problems.append(
                f"source {sid!r} is {state} and the bundle does not record which direction the "
                f"change cuts. Resolve it explicitly; '{state}' is not a severity, it is an open "
                "question")
        if (source.get("kind") or "").strip().lower() in NON_INDEPENDENT_KINDS:
            notes.append(
                f"source {sid!r} is a {source.get('kind')}: usable for context or method, never "
                "as the independent replication that lifts a claim")
        if not source.get("accession") and not source.get("doi") and not source.get("url"):
            problems.append(f"source {sid!r} has no accession, DOI, or URL — it cannot be fetched, "
                            "so it cannot be checked")

    for note in notes:
        print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} provenance problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: {len(trace)} traced element(s) against {len(ledger)} pinned source(s), "
          "no blocking source state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
