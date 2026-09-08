#!/usr/bin/env python3
"""Dating gate — can this chain have happened in this order?

Blocking, every tier. A source cannot derive from something written after it, and
a contemporary witness cannot postdate what it witnesses by a century. Both
errors survive review easily, because dates in a bibliography are read as labels
rather than as constraints.

Dates here are ordinal, not exact: a range is compared by its bounds, an
uncertain date must say so, and `circa` is not a licence to ignore an ordering
violation of two hundred years.

Usage:  dating_consistency.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402


def year(value) -> tuple[int, int] | None:
    """Earliest and latest year a date string could mean."""
    if value is None:
        return None
    text = str(value).strip().lower()
    years = [int(m) * (-1 if "bc" in text or "bce" in text else 1)
             for m in re.findall(r"\d{1,4}", text)]
    if not years:
        return None
    return (min(years), max(years))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}"); return 2

    sources = al.index(dossier.get("sources") or [])
    event = year((claim.get("scope") or {}).get("when"))
    problems, notes = [], []

    for sid, source in sources.items():
        span = year(source.get("date"))
        if span is None:
            problems.append(f"source {sid!r} has an unparseable date {source.get('date')!r}")
            continue
        for parent_id in source.get("derives_from") or []:
            parent = sources.get(parent_id)
            parent_span = year(parent.get("date")) if parent else None
            if parent_span and span[1] < parent_span[0]:
                problems.append(
                    f"source {sid!r} ({source.get('date')}) derives from {parent_id!r} "
                    f"({parent.get('date')}), which is later. A chain cannot run backwards")
        if event and source.get("kind") in {"primary", "contemporary"}:
            gap = span[0] - event[1]
            if gap > 100:
                problems.append(
                    f"source {sid!r} is declared {source.get('kind')} but is dated "
                    f"{source.get('date')}, roughly {gap} years after the event. That is not a "
                    "contemporary witness however early it is relative to the other sources")
            elif gap > 40:
                notes.append(f"source {sid!r} postdates the event by about {gap} years; "
                             "contemporary is a strong word for it")

    for note in notes:
        print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} dating problem(s)")
        for p in problems: print(f"  {p}")
        return 1
    print(f"pass: {len(sources)} source(s) in consistent order")
    return 0


if __name__ == "__main__":
    sys.exit(main())
