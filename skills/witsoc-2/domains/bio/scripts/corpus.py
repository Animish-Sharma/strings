#!/usr/bin/env python3
"""Source corpus — what each source can support, decided by kind rather than by tone.

The frame requires Explorer to retrieve against a domain corpus. In this field
the corpus is not a library of theorems, it is a ledger of sources, and the
question that matters about a source is not whether it agrees but what class of
claim it is *capable* of supporting. A preprint reporting exactly your effect and
a peer-reviewed independent replication of it look identical in a citation list
and are worth entirely different amounts.

So this classifies deterministically and says what each entry may be used for:

    dataset / accession    the primary evidence; can support a bounded claim
    journal_article        can support context, method, and prior effect
    independent_replication  the only kind that lifts a claim to reproduced
    preprint               context and method only; not independent replication
    method_paper           method only
    challenge_page,
    benchmark_page         method and leaderboard context; never biology
    company_blog,
    press_release          a claim, not a validation of one
    review                 orientation; its citations are the evidence, not it

And it enforces two states that stop everything: `retracted` and `withdrawn`. A
retracted paper does not stop being cited — it stops being checked — so it
blocks strong status from wherever it sits in the graph. `corrected` and
`expression_of_concern` block until someone records which direction the change
cuts, because "corrected" is an open question rather than a severity.

No network access. It normalizes, classifies, and audits a ledger the run
supplies; discovery is the orchestrator's job, and pretending otherwise would
make an offline run silently return an empty literature.

Usage:
    corpus.py --ledger <source_ledger.json> [--for-claim <claim.json>] [--json]
    corpus.py --explain-kinds

Exit: 0 usable ledger, 1 a blocking source state, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402

CAPABILITY = {
    "dataset":                 ["bounded_empirical", "context", "method"],
    "accession":               ["bounded_empirical", "context", "method"],
    "journal_article":         ["context", "method", "prior_effect"],
    "independent_replication": ["context", "method", "prior_effect", "replication"],
    "preprint":                ["context", "method"],
    "method_paper":            ["method"],
    "challenge_page":          ["method", "leaderboard_context"],
    "benchmark_page":          ["method", "leaderboard_context"],
    "review":                  ["orientation"],
    "company_blog":            ["orientation"],
    "press_release":           ["orientation"],
}

BLOCKING = {"retracted", "withdrawn"}
UNRESOLVED = {"corrected", "expression_of_concern", "disputed"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger")
    ap.add_argument("--for-claim")
    ap.add_argument("--explain-kinds", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.explain_kinds:
        print(json.dumps(CAPABILITY, indent=2))
        return 0
    if not args.ledger:
        ap.error("--ledger is required unless --explain-kinds")

    try:
        raw = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    entries = raw if isinstance(raw, list) else raw.get("source_ledger", [])

    report, blocking, unresolved = [], [], []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = (entry.get("kind") or "unknown").strip().lower()
        state = (entry.get("state") or "ok").strip().lower()
        identifier = entry.get("accession") or entry.get("doi") or entry.get("url")
        capability = CAPABILITY.get(kind, [])
        row = {
            "id": entry.get("id"),
            "kind": kind,
            "state": state,
            "identifier": identifier,
            "can_support": capability,
            "cannot_support": sorted(
                {c for caps in CAPABILITY.values() for c in caps} - set(capability)),
        }
        if not identifier:
            row["problem"] = "no accession, DOI, or URL — it cannot be fetched, so it cannot be checked"
        if kind not in CAPABILITY:
            row["problem"] = f"unrecognised kind {kind!r}; classify it before relying on it"
        if state in BLOCKING:
            blocking.append(entry.get("id"))
        elif state in UNRESOLVED:
            unresolved.append(entry.get("id"))
        report.append(row)

    replication_capable = [r["id"] for r in report if "replication" in r["can_support"]]

    summary = {
        "sources": len(report),
        "entries": report,
        "blocking_states": blocking,
        "unresolved_states": unresolved,
        "replication_capable": replication_capable,
        "note": (
            "no source in this ledger can support independent replication; a bounded result "
            "here cannot become a reproduced one until one does"
            if not replication_capable else
            f"{len(replication_capable)} source(s) could support replication"),
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for row in report:
            mark = "BLOCK" if row["state"] in BLOCKING else \
                   "OPEN " if row["state"] in UNRESOLVED else "ok   "
            print(f"  [{mark}] {str(row['id']):<6} {row['kind']:<24} "
                  f"supports: {', '.join(row['can_support']) or 'nothing'}")
            if row.get("problem"):
                print(f"           {row['problem']}")
        print(f"\n  {summary['note']}")

    if blocking:
        print(f"\nfail: {len(blocking)} source(s) retracted or withdrawn: {blocking}")
        print("  A retracted source blocks strong status wherever it sits in the graph.")
        return 1
    if unresolved:
        print(f"\nfail: {len(unresolved)} source(s) corrected or disputed with no recorded "
              f"direction: {unresolved}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
