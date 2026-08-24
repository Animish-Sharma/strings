#!/usr/bin/env python3
"""Role evals — the DECISION, not the artifact.

The adapter self-test asks whether a bad dossier is refused. It cannot ask
whether the Explorer read a cascade correctly, whether the producer DERIVES the
roots rather than accepting a list, or whether the shared-error analysis groups
on error and not on agreement — which is the one place this method can be
silently wrong, because correct readings are most of every text and a naive
similarity measure would cluster on them.

Usage:  run_roles.py [--role explorer|generator|researcher] [--json]
Exit:   0 all correct, 1 failures, 2 IO
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
sys.path.insert(0, str(PACK / "scripts"))

import archlib as al       # noqa: E402
import dossier as ds       # noqa: E402
import silence             # noqa: E402
import stemma              # noqa: E402

CLAIM = {"claim_id": "ROLE", "target_sha256": "0" * 64}

SOURCE_SETS = {
    # Four agreeing sources, one register behind all of them.
    "cascade": [
        {"id": "REG", "kind": "primary", "date": "212", "origin": "harbour-office",
         "derives_from": []},
        {"id": "CHRON", "kind": "later_chronicle", "date": "340", "origin": "chronicler",
         "derives_from": ["REG"]},
        {"id": "COMP", "kind": "compilation", "date": "790", "origin": "compiler",
         "derives_from": ["CHRON"]},
        {"id": "MOD", "kind": "modern_scholarship", "date": "1962", "origin": "editor",
         "derives_from": ["COMP"]},
    ],
    "two_origins": [
        {"id": "REG", "kind": "primary", "date": "212", "origin": "harbour-office",
         "derives_from": []},
        {"id": "LET", "kind": "contemporary", "date": "213", "origin": "merchant",
         "derives_from": []},
    ],
    "long_chain": [
        {"id": f"S{i}", "kind": "compilation", "date": str(300 + 50 * i),
         "origin": f"copyist-{i}", "derives_from": ([f"S{i-1}"] if i else [])}
        for i in range(5)
    ],
    "cycle": [
        {"id": "A", "kind": "primary", "date": "1", "origin": "x", "derives_from": ["B"]},
        {"id": "B", "kind": "primary", "date": "1", "origin": "y", "derives_from": ["A"]},
    ],
    "dangling": [
        {"id": "A", "kind": "primary", "date": "1", "origin": "x", "derives_from": ["GHOST"]},
    ],
}

COLLATIONS = {
    "shared": [
        {"locus": "1", "original": "Constantium",
         "readings": {"A": "Constantinum", "B": "Constantinum"}},
        {"locus": "2", "original": "vidit", "readings": {"A": "audivit", "B": "audivit"}},
    ],
    "agree": [
        {"locus": "1", "original": "Constantium",
         "readings": {"A": "Constantium", "B": "Constantium", "C": "Constantinum"}},
        {"locus": "2", "original": "vidit",
         "readings": {"A": "vidit", "B": "vidit", "C": "audivit"}},
    ],
    "none": [],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--role", choices=["explorer", "generator", "researcher"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    results = []

    if args.role in (None, "explorer"):
        for case in spec["explorer"]:
            sources = SOURCE_SETS[case["sources"]]
            index = al.index(sources)
            roots = [s["id"] for s in sources if not (s.get("derives_from") or [])]
            got = al.independence(roots + [s["id"] for s in sources], index)["independent_support"]
            results.append({"role": "explorer", "id": case["id"], "want": case["expect_support"],
                            "got": got, "ok": got == case["expect_support"], "why": case["why"]})

    if args.role in (None, "generator"):
        for case in spec["generator"]:
            built, problems = ds.build(CLAIM, SOURCE_SETS[case["sources"]])
            if case.get("expect_refused"):
                got, want = bool(problems), True
            else:
                got, want = built.get("supporting_sources"), case["expect_roots"]
            results.append({"role": "generator", "id": case["id"], "want": want, "got": got,
                            "ok": got == want, "why": case["why"]})

    if args.role in (None, "researcher"):
        for case in spec["researcher"]:
            if "collation" in case:
                doc = {"sources": [{"id": w, "origin": f"origin-{w}", "derives_from": []}
                                   for w in ("A", "B", "C")],
                       "collation": COLLATIONS[case["collation"]]}
                got = stemma.analyse(doc)["verdict"]
            else:
                low, high, n = case["silence"]
                got = silence.analyse({"survival_rate": {"low": low, "high": high},
                                       "recording_opportunities": n}, CLAIM)["verdict"]
            results.append({"role": "researcher", "id": case["id"], "want": case["expect"],
                            "got": got, "ok": got == case["expect"], "why": case["why"]})

    failures = [r for r in results if not r["ok"]]
    if args.json:
        print(json.dumps({"results": results, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    current = None
    print("\n  ROLE EVALS — the decision, not the artifact\n")
    for entry in results:
        if entry["role"] != current:
            current = entry["role"]
            print(f"  {current.upper()}")
        print(f"    {'ok  ' if entry['ok'] else 'FAIL'}  {entry['id']:<30} "
              f"want {str(entry['want']):<18} got {entry['got']}")
        print(f"            {entry['why'][:110]}")
    print("\n" + "=" * 66)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(results) - len(failures)}"
          f"/{len(results)} decisions correct")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
