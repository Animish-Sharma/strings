#!/usr/bin/env python3
"""Contradiction-ledger gate — was anyone looked for who disagrees?

Blocking from the denominator tier up. A confirming literature search is not
evidence; it is a search that stopped when it found what it wanted. This gate
asks for the opposite artifact: a list of sources that contradict, fail to
replicate, or bound the claim, each with a recorded resolution.

Three resolutions are legal and one is not:

    resolved              the contradiction is explained, with the reason stated
    unresolved_nonfatal   it stands, it narrows scope, the report must say so
    unresolved_fatal      it stands and it kills the claim as written

A fourth thing happens constantly and is refused here: prose dismissal. "That
study used a different system" is a hypothesis about why the results differ, not
a resolution of the difference — unless the bundle says which dimension differed
and why that dimension changes the answer.

An empty ledger is a fail, not a pass. Every real claim in this field has
something against it, and a ledger with nothing in it says the search was not
run rather than that nothing was found. `searched_and_found_none` with the
queries recorded is the honest way to say the other thing.

Usage:  contradiction_ledger.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

RESOLUTIONS = {"resolved", "unresolved_nonfatal", "unresolved_fatal"}
DISMISSAL_TELLS = ("different system", "not comparable", "older study", "low quality",
                   "not relevant", "underpowered study", "we disagree")


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

    ledger = bundle.get("contradiction_ledger")
    if ledger is None:
        print("fail: no contradiction_ledger. A search that only looked for agreement is not a "
              "search; record what was queried and what came back")
        return 1

    if isinstance(ledger, dict) and ledger.get("searched_and_found_none"):
        queries = ledger.get("queries") or []
        if not queries:
            print("fail: contradiction_ledger claims nothing was found but records no queries. "
                  "'We looked and found nothing' is only checkable if the looking is written down")
            return 1
        print(f"pass: contradiction search recorded across {len(queries)} quer(ies), none found")
        return 0

    entries = ledger if isinstance(ledger, list) else ledger.get("entries", [])
    if not entries:
        print("fail: contradiction_ledger is empty and does not claim an exhausted search")
        return 1

    problems, fatal = [], []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"malformed ledger entry: {entry!r}")
            continue
        eid = entry.get("source_id") or entry.get("id") or "<unnamed>"
        resolution = (entry.get("resolution") or "").strip().lower()
        if resolution not in RESOLUTIONS:
            problems.append(
                f"{eid}: resolution {resolution!r} is not one of {sorted(RESOLUTIONS)}")
            continue
        reason = (entry.get("reason") or "").strip()
        if resolution == "resolved":
            if len(reason) < 20:
                problems.append(
                    f"{eid}: marked resolved with no substantive reason. State which dimension "
                    "differs and why that dimension changes the result")
            elif any(tell in reason.lower() for tell in DISMISSAL_TELLS) and \
                    not entry.get("differing_dimension"):
                problems.append(
                    f"{eid}: resolved by dismissal ({reason[:60]!r}) without naming the differing "
                    "dimension. That is a hypothesis about the disagreement, not a resolution")
        if resolution == "unresolved_fatal":
            fatal.append(eid)

    if fatal:
        print(f"fail: {len(fatal)} unresolved fatal contradiction(s): {fatal}")
        print("  A fatal contradiction blocks admission. It is not outweighed by supporting "
              "evidence and it does not average against it")
        return 1
    if problems:
        print(f"fail: {len(problems)} ledger problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1

    nonfatal = [e.get("source_id") for e in entries
                if isinstance(e, dict) and e.get("resolution") == "unresolved_nonfatal"]
    print(f"pass: {len(entries)} contradiction(s) recorded, none fatal")
    if nonfatal:
        print(f"  {len(nonfatal)} unresolved-nonfatal: these narrow the scope and must appear in "
              f"the report — {nonfatal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
