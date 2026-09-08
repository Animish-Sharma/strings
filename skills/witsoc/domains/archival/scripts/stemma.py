#!/usr/bin/env python3
"""Shared error — deriving independence instead of reading it off a label.

`archlib.independence` collapses the supporting sources to distinct origins, and
it learns which sources share an origin from the `origin` FIELD the dossier's
author wrote. That is the pack's central computation resting on a self-report,
in a frame whose founding premise is that self-reports do not count. Declare
five distinct origins and the pack believes you.

The discipline has a method for this and it is computable. **Agreement in error
indicates common descent; agreement in a correct reading indicates nothing.**
Two witnesses that both read `Constantinum` where the archetype had
`Constantium` are related — nobody makes the same slip twice independently. Two
witnesses that both read `Constantium` correctly have told you only that the
word was legible.

That asymmetry is the whole of it, and it is the thing a naive similarity
measure gets backwards: cluster witnesses by agreement and the correct readings,
which are the majority of every text, swamp the signal. This counts errors only.

## What it takes and what it refuses to guess

Per locus, the reading of each witness, and which reading is original where an
editor has judged one. Loci with no original judged are counted as UNRESOLVED
and excluded — a shared reading of unknown status is not evidence of anything,
and treating it as one would let a dossier manufacture kinship by supplying
ambiguity.

With no readings at all it returns `not_computable`, which is not `independent`.
The declared origins stand and the receipt says they were never checked.

## Against the declaration

The computed grouping is compared with the dossier's declared origins. Two
witnesses in one error-family and two declared origins is a CONTRADICTION, and
it fails: the dossier claims corroboration that the readings say is one voice
copied twice. The reverse — declared same, computed apart — is reported and does
not fail, because a dossier is entitled to be conservative about its own
independence.

Usage:
    stemma.py <dossier.json> [--min-shared-errors N] [--json]
    stemma.py --self-test

Exit: 0 computed and consistent, 1 contradiction, 2 IO, 3 not computable
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archlib as al  # noqa: E402

# One shared error is suggestive; two is the working threshold in practice,
# because a single coincident slip — a common abbreviation, an easy minim
# confusion — happens. Overridable, and stated in the receipt either way.
DEFAULT_MIN_SHARED = 2


def collate(dossier: dict) -> dict:
    """Per-locus readings, split into errors, correct readings, and unresolved."""
    loci = dossier.get("collation") or []
    errors: dict[str, set[str]] = {}       # witness -> set of "locus=reading"
    agrees: dict[str, set[str]] = {}
    unresolved = 0
    for entry in loci:
        locus = str(entry.get("locus", "?"))
        original = entry.get("original")
        readings = entry.get("readings") or {}
        if original is None:
            unresolved += 1
            continue
        for witness, reading in readings.items():
            key = f"{locus}={reading}"
            if reading == original:
                agrees.setdefault(witness, set()).add(key)
            else:
                errors.setdefault(witness, set()).add(key)
    return {"errors": errors, "agreements": agrees, "loci": len(loci),
            "unresolved_loci": unresolved}


def families(errors: dict[str, set[str]], threshold: int) -> list[list[str]]:
    """Group witnesses by shared error, transitively.

    Transitive because descent is: if B and C share an ancestor and C and D do,
    all three are in one family whether or not B and D happen to share a locus.
    """
    witnesses = sorted(errors)
    parent = {w: w for w in witnesses}

    def find(w):
        while parent[w] != w:
            parent[w] = parent[parent[w]]
            w = parent[w]
        return w

    shared_counts: dict[tuple[str, str], int] = {}
    for a, b in itertools.combinations(witnesses, 2):
        common = errors[a] & errors[b]
        shared_counts[(a, b)] = len(common)
        if len(common) >= threshold:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    groups: dict[str, list[str]] = {}
    for w in witnesses:
        groups.setdefault(find(w), []).append(w)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0]), shared_counts


def analyse(dossier: dict, threshold: int = DEFAULT_MIN_SHARED) -> dict:
    collation = collate(dossier)
    errors = collation["errors"]
    sources = al.index(dossier.get("sources") or [])
    declared = {sid: al.origin_of(sid, sources) for sid in sources}

    if not dossier.get("collation"):
        return {"verdict": "not_computable", "collation_loci": 0,
                "declared_origins": sorted(set(declared.values())),
                "reading": "the dossier records no collation, so kinship cannot be derived and "
                           "the declared origins stand unchecked. That is a gap in the "
                           "evidence, not a finding of independence"}
    if not errors:
        return {"verdict": "not_computable", "collation_loci": collation["loci"],
                "unresolved_loci": collation["unresolved_loci"],
                "reading": "no locus has both an original reading judged and a witness departing "
                           "from it, so there is no shared error to count. Agreement in correct "
                           "readings groups nothing"}

    groups, shared = families(errors, threshold)
    computed = {w: i for i, g in enumerate(groups) for w in g}

    contradictions = []
    for a, b in itertools.combinations(sorted(computed), 2):
        if computed[a] == computed[b] and declared.get(a) != declared.get(b):
            common = sorted((errors[a] & errors[b]))
            contradictions.append({
                "witnesses": [a, b],
                "declared_origins": [declared.get(a), declared.get(b)],
                "shared_errors": common,
                "reading": f"{a} and {b} are declared as separate origins and share "
                           f"{len(common)} error(s) {common[:3]}. Nobody makes the same slip "
                           "twice independently; this is one voice counted as two"})
    conservative = []
    for a, b in itertools.combinations(sorted(computed), 2):
        if computed[a] != computed[b] and declared.get(a) == declared.get(b):
            conservative.append({"witnesses": [a, b], "origin": declared.get(a)})

    return {
        "verdict": "contradiction" if contradictions else "consistent",
        "threshold": threshold,
        "collation_loci": collation["loci"],
        "unresolved_loci": collation["unresolved_loci"],
        "error_families": groups,
        "computed_independent_support": len(groups),
        "declared_origins": sorted(set(declared.values())),
        "shared_error_counts": {f"{a}|{b}": n for (a, b), n in shared.items() if n},
        "contradictions": contradictions,
        "declared_together_computed_apart": conservative,
        "reading": (f"{len(groups)} error-famil(y/ies) among {len(errors)} witness(es) with "
                    f"departures; the dossier declares {len(set(declared.values()))} origin(s)"
                    + (". They disagree." if contradictions else ". They agree.")),
    }


def self_test() -> int:
    cases, failures = [], 0

    def dossier(collation, origins):
        return {"sources": [{"id": w, "origin": o, "derives_from": []}
                            for w, o in origins.items()],
                "collation": collation}

    # 1. Shared ERRORS group. Two witnesses departing from the archetype the same
    #    way, twice, are one voice.
    shared = [{"locus": "1", "original": "Constantium",
               "readings": {"A": "Constantinum", "B": "Constantinum", "C": "Constantium"}},
              {"locus": "2", "original": "vidit",
               "readings": {"A": "audivit", "B": "audivit", "C": "vidit"}}]
    r = analyse(dossier(shared, {"A": "scriptorium-x", "B": "scriptorium-y", "C": "abbey-z"}))
    grouped = any(set(g) >= {"A", "B"} for g in r["error_families"])
    cases.append(("witnesses sharing two errors are one family", grouped, r["reading"]))
    cases.append(("and a dossier declaring them separate CONTRADICTS",
                  r["verdict"] == "contradiction",
                  r["contradictions"][0]["reading"] if r["contradictions"] else "no contradiction"))

    # 2. THE discriminating case. Agreement in CORRECT readings must group nothing
    #    — this is what a similarity measure gets backwards, and correct readings
    #    are the majority of every text.
    agree = [{"locus": "1", "original": "Constantium",
              "readings": {"A": "Constantium", "B": "Constantium", "C": "Constantinum"}},
             {"locus": "2", "original": "vidit",
              "readings": {"A": "vidit", "B": "vidit", "C": "audivit"}}]
    r = analyse(dossier(agree, {"A": "scriptorium-x", "B": "scriptorium-y", "C": "abbey-z"}))
    together = any(set(g) >= {"A", "B"} for g in r["error_families"])
    cases.append(("agreement in CORRECT readings groups nothing",
                  not together and r["verdict"] != "contradiction",
                  f"families {r.get('error_families')} — A and B agree twice and are unrelated"))

    # 3. One shared error is under the threshold: a single coincident slip happens.
    one = [{"locus": "1", "original": "vidit", "readings": {"A": "audivit", "B": "audivit"}},
           {"locus": "2", "original": "annum", "readings": {"A": "annos", "B": "annum"}}]
    r = analyse(dossier(one, {"A": "x", "B": "y"}))
    cases.append(("a single shared error is below the working threshold",
                  r["verdict"] == "consistent",
                  f"families {r['error_families']}; one coincidence is not descent"))

    # 4. Unique errors keep witnesses apart.
    unique = [{"locus": "1", "original": "vidit", "readings": {"A": "audivit", "B": "videt"}},
              {"locus": "2", "original": "annum", "readings": {"A": "annos", "B": "anno"}}]
    r = analyse(dossier(unique, {"A": "x", "B": "y"}))
    cases.append(("witnesses erring differently stay separate",
                  len(r["error_families"]) == 2, f"families {r['error_families']}"))

    # 5. Abstention, in both of its forms.
    r = analyse(dossier([], {"A": "x"}))
    cases.append(("no collation is not_computable, never independent",
                  r["verdict"] == "not_computable", r["reading"]))
    r = analyse(dossier([{"locus": "1", "readings": {"A": "x", "B": "x"}}], {"A": "x", "B": "y"}))
    cases.append(("a locus with no original judged is excluded, not counted",
                  r["verdict"] == "not_computable", r["reading"]))

    # 6. Transitivity: descent is transitive even when two witnesses share no locus.
    chain = [{"locus": "1", "original": "a", "readings": {"A": "z", "B": "z"}},
             {"locus": "2", "original": "b", "readings": {"A": "y", "B": "y"}},
             {"locus": "3", "original": "c", "readings": {"B": "w", "C": "w"}},
             {"locus": "4", "original": "d", "readings": {"B": "v", "C": "v"}}]
    r = analyse(dossier(chain, {"A": "x", "B": "y", "C": "z"}))
    cases.append(("kinship is transitive: A-B and B-C put all three in one family",
                  any(set(g) >= {"A", "B", "C"} for g in r["error_families"]),
                  f"families {r['error_families']}"))

    print("\n  STEMMA SELF-TEST — shared error, not similarity\n")
    for label, ok, note in cases:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        print(f"          {str(note)[:150]}")
        failures += 0 if ok else 1
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases)} case(s), {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier", nargs="?")
    ap.add_argument("--min-shared-errors", type=int, default=DEFAULT_MIN_SHARED)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.dossier:
        ap.error("a dossier is required (or --self-test)")
    try:
        dossier = al.read_json(args.dossier)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = analyse(dossier, args.min_shared_errors)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"STEMMA: {result['verdict']} — {result['reading']}")
        for group in result.get("error_families", []):
            print(f"  family   {', '.join(group)}")
        for entry in result.get("contradictions", []):
            print(f"  CONTRADICTION  {entry['reading']}")
    return {"consistent": 0, "contradiction": 1, "not_computable": 3}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
