#!/usr/bin/env python3
"""Interest gate — does anyone here have a reason to say this?

Blocking from the triangulation tier up. A source with a stake in the claim is
not disqualified: interested parties are often the only people present, and
discarding them would empty most archives. What is disqualifying is every
independent origin sharing the same interest, because then the agreement between
them is explained by the interest and needs no other cause.

So the check is not "is this source biased". It is: after collapsing to distinct
origins, is there anything left that did not want this to be true.

Usage:  interest_audit.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error, 3 no supporting sources yet
"""
from __future__ import annotations
import argparse
import re, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}"); return 2

    sources = al.index(dossier.get("sources") or [])
    supporting = dossier.get("supporting_sources") or []
    if not supporting:
        print("not_run: no supporting sources declared"); return 3

    summary = al.independence(supporting, sources)
    problems, notes = [], []

    undeclared = [sid for sid in summary["distinct_roots"]
                  if sid in sources and "interest" not in sources[sid]]
    if undeclared:
        problems.append(
            f"root source(s) {undeclared} declare no `interest` field. An undeclared interest and "
            "a disinterested source are written the same way, which is why this is required "
            "rather than reviewed")

    interests = {}
    for sid in summary["distinct_roots"]:
        source = sources.get(sid) or {}
        stake = (source.get("interest") or "").strip().lower()
        interests[sid] = stake

    # A source declaring no stake usually says WHY — "none, an unrelated group",
    # "no stake in this voyage". Matching the field as a bare token made the
    # natural way of writing it read as a stake, so the gate fired on a dossier
    # that had answered it honestly. The leading clause is the answer; whatever
    # follows is the explanation, and refusing an explained answer teaches the
    # format by rejection.
    def disinterested(stake: str) -> bool:
        head = re.split(r"[—,;:(-]", stake, maxsplit=1)[0].strip()
        return (head in {"none", "disinterested", "unknown", "no stake", "no interest"}
                or head.startswith(("none", "no stake", "no interest", "disinterested")))

    stated = [s for s in interests.values() if s and not disinterested(s)]
    if stated and len(stated) == len(interests) and interests:
        shared = len(set(stated)) == 1
        problems.append(
            f"every independent origin has a stake ({sorted(set(stated))})"
            + (". They share it, so their agreement is explained by the interest and needs no "
               "other cause" if shared else
               ". Different stakes are better than one, but nothing here is disinterested"))
    elif stated:
        notes.append(f"{len(stated)} of {len(interests)} origins have a declared stake; at least "
                     "one does not, which is what makes the agreement worth something")

    unknown = [sid for sid, stake in interests.items() if stake == "unknown"]
    if unknown:
        notes.append(f"origin(s) {unknown} record their interest as unknown. That is honest and "
                     "it is not the same as disinterested")

    for note in notes: print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} interest problem(s)")
        for p in problems: print(f"  {p}")
        return 1
    print(f"pass: {len(interests)} independent origin(s), interests declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
