#!/usr/bin/env python3
"""Attackability — is this target worth attacking now.

Every low signal emits a `raise_it_by` note, so the score doubles as a worklist:
a bad score tells you what to go and do, not just that the target is hard.

The boundary factor encodes a real observation: the winnable regime is where
existing technique covers most but not all of the problem. A target 40% covered
is out of reach; one 100% covered is already done.

Usage:  attackability.py --target <target.json> [--json]
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import ATTACKABILITY_WEIGHTS, clamp  # noqa: E402

COMPUTATION_DOMAINS = {"combinatorics","graph_theory","extremal","additive_combinatorics",
                       "number_theory","ramsey_theory"}
VARIATIONAL = re.compile(r"\b(max|min|extremal|bound|optim|largest|smallest|densest|longest)",
                         re.IGNORECASE)

def assess(t: dict) -> dict:
    f, notes = {}, []
    def note(key, msg): notes.append({"signal": key, "raise_it_by": msg})

    f["finite_reduction"] = 1.0 if t.get("finite_reducible") else 0.0
    if not f["finite_reduction"]:
        note("finite_reduction", "find a finite instance family whose behaviour brackets "
             "the general case; a bounded search you can actually run is worth more than "
             "a general argument you cannot")
    f["formalization"] = 1.0 if t.get("formal_statement") else 0.0
    if not f["formalization"]:
        note("formalization", "write the formal statement; encoding it early exposes "
             "quantifier and definition problems for free")
    hits = int(t.get("technique_hits", 0))
    f["technique_density"] = clamp(hits/3)
    if f["technique_density"] < 0.5:
        note("technique_density", "retrieve techniques from neighbouring results; fewer "
             "than three applicable techniques usually means the formulation is wrong")
    sources = t.get("sources", [])
    age = t.get("literature_age_days")
    f["literature"] = (0.5 if (age is not None and age <= 90) else 0.2) + \
                      clamp(0.1*sum(1 for s in sources if str(s.get("year","0")) >= "2020"), 0, 0.5)
    if f["literature"] < 0.5:
        note("literature", "refresh the source ledger; a stale landscape hides both "
             "prior art and new tools")
    n = len(sources)
    f["literature_scarcity"] = 0.0 if not t.get("has_source_ledger") else (
        1.0 if n <= 3 else 0.5 if n <= 10 else 0.1)
    if not t.get("has_source_ledger"):
        note("literature_scarcity", "build a source ledger — absence of one scores zero, "
             "because 'no sources found' and 'never looked' are different things")
    f["computation_domain"] = 1.0 if str(t.get("domain","")).lower() in COMPUTATION_DOMAINS else 0.0
    f["variational"] = 1.0 if VARIATIONAL.search(t.get("statement","")) else 0.0

    total = sum(f[k]*w for k, w in ATTACKABILITY_WEIGHTS.items())
    covered = float(t.get("boundary_fraction", 0.5))
    boundary = 1 - abs(0.9 - covered)
    total *= (0.5 + 0.5*boundary)
    return {"score": round(clamp(total)*100, 1), "signals": {k: round(v,2) for k,v in f.items()},
            "boundary_fraction": covered, "boundary_factor": round(boundary,3),
            "raise_it_by": notes,
            "note": "attention only; a high score never makes a claim more likely to be true"}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: t = json.loads(Path(a.target).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    r = assess(t)
    if a.json: print(json.dumps(r, indent=2))
    else:
        print(f"ATTACKABILITY {r['score']}/100  (boundary factor {r['boundary_factor']})")
        for k, v in r["signals"].items(): print(f"    {k:<22} {v}")
        if r["raise_it_by"]:
            print("\n  worklist:")
            for n in r["raise_it_by"]: print(f"    {n['signal']}: {n['raise_it_by']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
