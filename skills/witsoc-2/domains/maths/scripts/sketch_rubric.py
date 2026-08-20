#!/usr/bin/env python3
"""Sketch rubric — are the gaps GOOD gaps.

Two decompositions of the same target are not equally useful. A good one leaves
small, independent, separately checkable holes. A bad one leaves one hole shaped
exactly like the original problem.

    score = 0.30*coverage + 0.30*atomicity + 0.15*dependency_quality
          + 0.10*type_diversity + 0.15*(1 - miracle_fraction)

A **miracle** is a node whose statement is nearly the target restated. It looks
like a step and is actually the whole problem wearing a label, which is why it is
penalized rather than merely noted — a sketch of three steps where one is a
miracle has decomposed nothing.

Usage:  sketch_rubric.py --sketch <s.json> [--json]
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

ATOMICITY = {"atomic":1.0, "conjunctive":0.6, "multi_step":0.3}
MIRACLE_THRESHOLD = 0.9

def toks(s): return {t for t in re.split(r"[^A-Za-z0-9_]+", (s or "").lower()) if len(t)>1}
def cosine(a, b):
    A, B = toks(a), toks(b)
    return len(A & B)/max(len(A|B),1)

def score(sketch: dict) -> dict:
    nodes = sketch.get("nodes", [])
    target = sketch.get("target","")
    if not nodes: return {"score":0.0,"why":"no nodes"}

    covered = sum(1 for n in nodes if n.get("formal_statement"))
    coverage = covered/len(nodes)
    atomicity = sum(ATOMICITY.get(n.get("granularity","multi_step"),0.3) for n in nodes)/len(nodes)
    with_deps = sum(1 for n in nodes if n.get("depends_on"))
    dependency = with_deps/len(nodes)
    kinds = {n.get("kind","lemma") for n in nodes}
    diversity = min(1.0, len(kinds)/4)
    miracles = [n for n in nodes if cosine(n.get("statement",""), target) > MIRACLE_THRESHOLD]
    miracle_fraction = len(miracles)/len(nodes)

    total = (0.30*coverage + 0.30*atomicity + 0.15*dependency +
             0.10*diversity + 0.15*(1-miracle_fraction))
    return {"score": round(total,4),
            "components":{"coverage":round(coverage,3),"atomicity":round(atomicity,3),
                          "dependency_quality":round(dependency,3),
                          "type_diversity":round(diversity,3),
                          "miracle_fraction":round(miracle_fraction,3)},
            "miracles":[n.get("id") for n in miracles],
            "note":("a miracle node restates the target; a sketch containing one has "
                    "decomposed nothing, whatever its other scores" if miracles else
                    "no miracle nodes")}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sketch", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: s = json.loads(Path(a.sketch).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    r = score(s)
    if a.json: print(json.dumps(r, indent=2))
    else:
        print(f"SKETCH {r['score']:.3f}")
        for k,v in r.get("components",{}).items(): print(f"    {k:<20} {v}")
        if r.get("miracles"): print(f"\n  MIRACLE nodes: {r['miracles']}\n  {r['note']}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
