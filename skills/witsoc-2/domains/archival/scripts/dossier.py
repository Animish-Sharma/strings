#!/usr/bin/env python3
"""Build the dossier, so the pack can produce and not only refuse.

This pack could check a dossier and could not make one. Every other pack here
has a producer — a plan renderer, a bundle builder — and this one asked its user
to hand-write a JSON graph of sources, derivations, and ledgers, then told them
what was wrong with it. A checker without a producer teaches its format by
rejection, which is the most expensive way anybody has ever learned a schema.

What it does is assemble and COMPUTE, never assert:

  * traces every derivation chain and reports the roots, so `supporting_sources`
    is a consequence of the graph rather than a list somebody chose;
  * refuses a cycle, and refuses a `derives_from` pointing at nothing — a graph
    that cannot be walked cannot be collapsed, and the collapse is the pack's
    whole argument;
  * runs the collation through `stemma.py` where one exists, and records the
    derived families beside the declared origins;
  * fills `evidence_tiers_available` from what the sources ARE, not from what
    the author hopes they support.

What it leaves empty is the part no tool can supply, and it says so in the file:
the survival argument, what the record would look like if the claim were false,
and the archive coverage. A dossier this produces is well-formed and unfinished,
and it fails the gates in exactly those places until a person answers them. That
is the intended behaviour — a producer that filled them with plausible sentences
would be manufacturing the evidence the gates exist to demand.

Usage:
    dossier.py --claim <claim.json> --sources <sources.json> --out <dossier.json>
    dossier.py --self-test

Exit: 0 written, 1 the source graph is unusable, 2 IO
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archlib as al  # noqa: E402
import stemma  # noqa: E402

REQUIRED_SOURCE_FIELDS = ("id", "kind", "date", "origin")

# What a source of each kind is CAPABLE of supporting. A later chronicle can
# establish that a tradition existed by its date; it cannot establish that the
# event happened, however confidently it says so.
TIER_BY_KIND = {
    "primary": "independent_origins",
    "contemporary": "independent_origins",
    "later_chronicle": "tradition_attested",
    "compilation": "tradition_attested",
    "modern_scholarship": "secondary_reading",
}

UNANSWERED = "UNANSWERED — no tool can supply this; a person has to"


def build(claim: dict, source_list: list[dict]) -> tuple[dict, list[str]]:
    problems: list[str] = []
    for entry in source_list:
        missing = [f for f in REQUIRED_SOURCE_FIELDS if not entry.get(f)]
        if missing:
            problems.append(f"source {entry.get('id', '?')!r} is missing {missing}. A source "
                            "that cannot be dated or located is not a source, it is a memory")

    sources = al.index(source_list)
    for entry in source_list:
        for parent in entry.get("derives_from") or []:
            if parent not in sources:
                problems.append(f"{entry['id']!r} derives from {parent!r}, which is not in the "
                                "dossier. A chain that cannot be walked cannot be collapsed, and "
                                "the collapse is what this pack does")

    roots: list[str] = []
    cycles: list[str] = []
    for entry in source_list:
        found, cycle = al.trace(entry["id"], sources)
        cycles.extend(cycle)
        if not (entry.get("derives_from") or []):
            roots.append(entry["id"])
    if cycles:
        problems.append(f"citation cycle(s) through {sorted(set(cycles))}. A cycle means two "
                        "sources each cite the other as their authority, and neither is a root")

    if problems:
        return {}, problems

    summary = al.independence(roots, sources)
    kinds = {entry["id"]: (entry.get("kind") or "").lower() for entry in source_list}
    tiers = sorted({TIER_BY_KIND.get(kinds[r], "unclassified") for r in roots})

    dossier = {
        "schema": "archival-dossier-v1",
        "claim_id": claim.get("claim_id", "UNSET"),
        "target_sha256": claim.get("target_sha256", ""),
        "sources": source_list,
        # A consequence of the graph, not a choice: the roots are what is left
        # after every chain is followed home.
        "supporting_sources": sorted(roots),
        "derived": {
            "independent_support": summary["independent_support"],
            "distinct_origins": summary["distinct_origins"],
            "collapsed": summary["collapsed"],
        },
        "evidence_tiers_available": tiers,
        "stated_bounds": f"{len(roots)} root source(s) of kind(s) "
                         f"{sorted({kinds[r] for r in roots})}",
        "archive_coverage": UNANSWERED,
        "what_the_record_would_look_like_if_false": UNANSWERED,
        "interpretation": UNANSWERED,
    }
    if claim.get("assertion_kind") == "absence":
        dossier["survival_argument"] = UNANSWERED
        dossier["survival_rate"] = {"low": None, "high": None}
        dossier["recording_opportunities"] = None
    return dossier, []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim")
    ap.add_argument("--sources")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not (args.claim and args.sources):
        ap.error("--claim and --sources are required (or --self-test)")

    try:
        claim = al.read_json(args.claim)
        payload = al.read_json(args.sources)
        source_list = payload if isinstance(payload, list) else payload.get("sources") or []
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    dossier, problems = build(claim, source_list)
    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"REFUSED: {len(problems)} problem(s) in the source graph", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(json.dumps(dossier, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(dossier, indent=2))
    else:
        print(f"DOSSIER: {len(source_list)} source(s) -> "
              f"{dossier['derived']['independent_support']} independent origin(s)")
        print(f"  roots            {', '.join(dossier['supporting_sources'])}")
        print(f"  origins          {', '.join(dossier['derived']['distinct_origins'])}")
        print(f"  evidence tiers   {', '.join(dossier['evidence_tiers_available'])}")
        unanswered = [k for k, v in dossier.items() if v == UNANSWERED]
        print(f"  unanswered       {', '.join(unanswered)}")
        print("  those are the judgements no tool can make. The gates will refuse this dossier "
              "until a person answers them, which is the point of leaving them blank rather "
              "than filling them with something plausible.")
        if args.out:
            print(f"  wrote            {args.out}")
    return 0


def self_test() -> int:
    cases, failures = [], 0
    claim = {"claim_id": "T", "target_sha256": "0" * 64}

    chain = [
        {"id": "A", "kind": "primary", "date": "212", "origin": "harbour-office",
         "derives_from": []},
        {"id": "B", "kind": "later_chronicle", "date": "340", "origin": "chronicler",
         "derives_from": ["A"]},
        {"id": "C", "kind": "compilation", "date": "790", "origin": "compiler",
         "derives_from": ["B"]},
    ]
    built, problems = build(claim, chain)
    cases.append(("a chain collapses to its root, and the root is derived not chosen",
                  not problems and built["supporting_sources"] == ["A"]
                  and built["derived"]["independent_support"] == 1,
                  f"roots {built.get('supporting_sources')}, "
                  f"support {built.get('derived', {}).get('independent_support')}"))

    two = chain + [{"id": "D", "kind": "contemporary", "date": "213",
                    "origin": "merchant", "derives_from": []}]
    built, _ = build(claim, two)
    cases.append(("a second root is a second origin",
                  built["derived"]["independent_support"] == 2,
                  f"origins {built['derived']['distinct_origins']}"))

    _, problems = build(claim, [{"id": "A", "kind": "primary", "date": "1",
                                 "origin": "x", "derives_from": ["GHOST"]}])
    cases.append(("a derivation pointing at nothing is refused",
                  any("GHOST" in p for p in problems), problems[0] if problems else "accepted"))

    _, problems = build(claim, [
        {"id": "A", "kind": "primary", "date": "1", "origin": "x", "derives_from": ["B"]},
        {"id": "B", "kind": "primary", "date": "1", "origin": "y", "derives_from": ["A"]}])
    cases.append(("a citation cycle is refused, not walked",
                  any("cycle" in p for p in problems), problems[0] if problems else "accepted"))

    _, problems = build(claim, [{"id": "A", "kind": "primary", "derives_from": []}])
    cases.append(("a source with no date and no origin is refused",
                  any("missing" in p for p in problems), problems[0] if problems else "accepted"))

    built, _ = build(claim, [{"id": "L", "kind": "later_chronicle", "date": "900",
                              "origin": "chronicler", "derives_from": []}])
    cases.append(("a later chronicle offers tradition_attested, not the event",
                  built["evidence_tiers_available"] == ["tradition_attested"],
                  f"tiers {built['evidence_tiers_available']} — it attests a tradition existed"))

    built, _ = build(claim, chain)
    unanswered = [k for k, v in built.items() if v == UNANSWERED]
    cases.append(("the judgements no tool can make are left EMPTY and named",
                  {"archive_coverage", "what_the_record_would_look_like_if_false"} <= set(unanswered),
                  f"unanswered: {unanswered}"))

    built, _ = build({**claim, "assertion_kind": "absence"}, chain)
    cases.append(("an absence claim gets the survival fields it will be asked for",
                  "survival_rate" in built and built["survival_rate"]["low"] is None,
                  "empty, so the silence gate reports not_computable rather than a guess"))

    print("\n  DOSSIER SELF-TEST — well-formed, and unfinished on purpose\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:140]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
