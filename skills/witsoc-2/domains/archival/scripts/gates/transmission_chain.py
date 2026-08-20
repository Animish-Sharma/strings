#!/usr/bin/env python3
"""Transmission gate — how much has happened to these words on the way here?

Blocking from the triangulation tier up. Between a claim and the document it
rests on there are usually several transformations: translation, abridgement,
paraphrase, editorial reconstruction. Each is a place where the wording that
carries the claim can change, and none of them is visible in a citation.

The gate counts the hops on the shortest path from each supporting source to its
root, and it wants two things:

- past a threshold of language changes, the claim's key wording must be quoted in
  the ORIGINAL language somewhere in the dossier. A claim resting on a phrase
  that has been through three translations is a claim about the third translator.
- a chain containing a reconstruction or an emendation must say so. An editor's
  conjecture printed without brackets becomes a fact within one generation.

Usage:  transmission_chain.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error, 3 nothing to trace
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402

TRANSLATION_LIMIT = 2
LOSSY = {"translation", "abridgement", "paraphrase", "reconstruction", "emendation"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}"); return 2

    sources = al.index(dossier.get("sources") or [])
    supporting = dossier.get("supporting_sources") or []
    if not supporting:
        print("not_run: nothing to trace"); return 3

    problems, notes = [], []
    for sid in supporting:
        languages, transforms, chain = [], [], []
        current, seen = sid, set()
        while current and current not in seen:
            seen.add(current)
            node = sources.get(current)
            if node is None:
                break
            chain.append(current)
            if node.get("language"):
                languages.append(node["language"].strip().lower())
            for step in node.get("transformations") or []:
                if str(step).strip().lower() in LOSSY:
                    transforms.append((current, step))
            parents = node.get("derives_from") or []
            current = parents[0] if parents else None

        hops = len({l for l in languages}) - 1 if languages else 0
        if hops > TRANSLATION_LIMIT:
            if not dossier.get("original_language_quotation"):
                problems.append(
                    f"{sid}: {hops} language change(s) along {' <- '.join(chain)} and no "
                    "original-language quotation in the dossier. Past this many hops the claim "
                    "rests on the wording of the last translator")
            else:
                notes.append(f"{sid}: {hops} language changes, original wording quoted")
        for where, step in transforms:
            if not (sources.get(where) or {}).get("transformation_note"):
                problems.append(
                    f"{sid}: the chain passes through a {step} at {where!r} with no note saying "
                    "what changed. An editor's conjecture printed without brackets becomes a fact "
                    "within one generation")

    for note in notes: print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} transmission problem(s)")
        for p in problems: print(f"  {p}")
        return 1
    print(f"pass: {len(supporting)} chain(s) traced, transformations accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
