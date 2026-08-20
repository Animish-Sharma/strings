#!/usr/bin/env python3
"""Result ladder and rung generation.

The default deliverable on a hard target is NOT a solution. It is a rung: the
strongest honest product reachable now. Full attack is legitimate only after the
lower rungs have identified the mechanism — otherwise it is a guess with a large
budget attached.

Each rung declares the ceiling it can reach, so a rung cannot be reported as
more than its kind allows.

Usage:  rungs.py ladder | templates [--domain D] | score --rungs <f.json> [--top N]
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import RUNG_WEIGHTS, clamp  # noqa: E402

LADDER = [
    ("toy_case",            "CHECKED_BOUNDED", "smallest nontrivial instances by hand"),
    ("finite_search",       "CHECKED_BOUNDED", "exhaustive over a stated finite range"),
    ("special_class",       "PARTIAL",         "a restricted family where it holds"),
    ("obstruction",         "PARTIAL",         "a proof that a whole approach class fails"),
    ("conditional_theorem", "CONDITIONAL",     "holds given an explicit unproved assumption"),
    ("improved_bound",      "PARTIAL",         "a better constant or exponent"),
    ("reduction",           "PARTIAL",         "target follows from a named residual"),
    ("full_target",         "VERIFIED",        "the whole statement; needs a kernel receipt"),
]

UNIVERSAL = [
    ("definition_audit", 76, "unfold every definition; many targets dissolve or sharpen"),
    ("minimal_counterexample", 82, "assume a minimal violator and derive structure"),
    ("precondition_bridge", 84, "a known result is one unmet hypothesis away; establish it"),
    ("counterexample_pressure", 74, "bounded hunt over the standard families"),
    ("invariant_strengthening", 78, "strengthen the induction hypothesis"),
    ("obstruction_conversion", 75, "turn a repeated failure into a proved obstruction"),
]
DOMAIN_TEMPLATES = {
    "number_theory": [("residue_ladder",83,"split by residue class and handle each"),
                      ("valuation_descent",80,"p-adic valuation descent"),
                      ("parametric_witness",81,"construct a witness family in a parameter")],
    "graph_theory": [("finite_graph_certificate",82,"exhaustive certificate on small graphs"),
                     ("degree_reduction",80,"reduce to a bounded-degree case"),
                     ("deletion_contraction",79,"induct on edges")],
    "combinatorics": [("finite_graph_certificate",82,"exhaustive small-case certificate"),
                      ("double_counting",79,"count one quantity two ways")],
    "additive_combinatorics": [("density_increment",83,"iterate a density increment"),
                               ("energy_increment",81,"iterate an energy increment")],
    "extremal": [("blow_up_family",80,"test blow-ups of a small extremal example"),
                 ("stability",78,"near-extremal configurations are near-structured")],
}

def score_rung(r: dict) -> tuple[float, list[str]]:
    reasons = []
    formal = 0.9 if r.get("lean_statement") else (
        0.42 if "formal" in str(r.get("relation","")).lower() else 0.25)
    kind = str(r.get("kind","")).lower()
    attack = 0.82 if r.get("lean_statement") else (
        0.66 if ("search" in kind or "bounded" in kind) else 0.46)
    novelty = 0.72 if kind in {"reduction","barrier","bridge","invariant","obstruction"} else 0.5
    value = clamp(float(r.get("priority", 50)) / 100, 0.2, 0.95)
    reasons.append(f"formal {formal:.2f} attack {attack:.2f} novelty {novelty:.2f} value {value:.2f}")
    total = (RUNG_WEIGHTS["formal"]*formal + RUNG_WEIGHTS["attack"]*attack +
             RUNG_WEIGHTS["novelty"]*novelty + RUNG_WEIGHTS["value"]*value)
    return round(total, 4), reasons

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ladder")
    t = sub.add_parser("templates"); t.add_argument("--domain")
    s = sub.add_parser("score"); s.add_argument("--rungs", required=True)
    s.add_argument("--top", type=int, default=24); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "ladder":
        print("Result ladder — the default deliverable is a rung, not a solution:\n")
        for i, (name, ceiling, why) in enumerate(LADDER, 1):
            print(f"  {i}. {name:<20} ceiling {ceiling:<16} {why}")
        print("\n  Full attack is legitimate only after lower rungs identify the mechanism.")
        return 0

    if a.cmd == "templates":
        print("Universal:")
        for name, pri, why in UNIVERSAL: print(f"  {pri:>3}  {name:<26} {why}")
        doms = [a.domain] if a.domain else sorted(DOMAIN_TEMPLATES)
        for d in doms:
            if d in DOMAIN_TEMPLATES:
                print(f"\n{d}:")
                for name, pri, why in DOMAIN_TEMPLATES[d]: print(f"  {pri:>3}  {name:<26} {why}")
        return 0

    try:
        rungs = json.loads(Path(a.rungs).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    rungs = rungs if isinstance(rungs, list) else rungs.get("rungs", [])
    seen, out = {}, []
    for r in rungs:
        key = hashlib.sha256((r.get("statement","")+r.get("lean_statement","")).encode()).hexdigest()
        score, reasons = score_rung(r)
        if key not in seen or score > seen[key]["score"]:
            seen[key] = {**r, "score": score, "reasons": reasons,
                         "status": "OPEN_UNFALSIFIED"}
    out = sorted(seen.values(), key=lambda x: (-x["score"], -x.get("priority",0)))[:a.top]
    if a.json: print(json.dumps({"rungs": out}, indent=2))
    else:
        for r in out: print(f"  {r['score']:.3f}  {r.get('kind','?'):<24} {r.get('statement','')[:60]}")
        print("\n  All rungs enter OPEN_UNFALSIFIED. A rung is a target, not a result.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
