#!/usr/bin/env python3
"""Barrier and mutation selection.

Which obstruction to attack next, and which single axis to change. Both are
advisory rankings; neither closes anything.

The mutation axes are keyed by gap class, which is the useful part: it converts
a diagnosed failure into a concrete next move instead of a feeling.

Usage:
    select.py barrier --candidates <f.json> [--json]
    select.py mutation --gap-class C [--used AXIS ...] [--json]
    select.py axes
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import BARRIER_WEIGHTS, MUTATION_WEIGHTS, clamp, weighted  # noqa: E402

AXES_BY_GAP = {
    "theorem_precondition_gap": ["replace the cited theorem","weaken the local premise",
        "establish the missing precondition","retrieve an alternate theorem",
        "formalize a finite subcase"],
    "precondition_gap": ["establish the missing precondition","retrieve an alternate theorem",
        "weaken the local premise","isolate the hypothesis"],
    "missing_barrier_lemma": ["split the barrier claim","strengthen the invariant",
        "prove an obstruction","change the encoding"],
    "genuine_barrier": ["strengthen the invariant","dualize","extremal pivot",
        "reduction pivot","algebraize"],
    "genuine_mathematical_barrier": ["strengthen the invariant","dualize","extremal pivot",
        "reduction pivot","algebraize"],
    "target_drift": ["restore the frozen target","add the dependency path",
        "narrow the claim honestly","skeptic review"],
    "artifact_issue": ["formalize a finite subcase","repair the artifact target",
        "minimize the proof object","replace the artifact dependency"],
    "formalization_block": ["formalize a finite subcase","change the encoding",
        "state a smaller obligation","register the missing predicate"],
    "false_claim": ["search a counterexample family","prove an obstruction",
        "demote the claim","change the encoding"],
    "computational_obstruction": ["minimize the witness","raise the bounded search",
        "derive an obstruction lemma","change the encoding"],
    "hidden_assumption": ["isolate the hypothesis","establish the missing precondition",
        "weaken the local premise","skeptic review"],
    "prover_search_gap": ["change the method","change the encoding","change the object class",
        "raise the computational bound"],
}

def score_barrier(node: dict, total_nodes: int, gap_ids: set, failed: list) -> tuple[float, list[str]]:
    path = node.get("dependency_path_to_target") or []
    feats = {
        "dependency_centrality": clamp(len(path)/max(total_nodes,1)),
        "unlock_value": clamp(len(node.get("unlocks", []))/4) if node.get("unlocks")
                        else (0.55 if node.get("relation") in {"direct","target","unlocks_target"} else 0.25),
        "formalization_readiness": 0.75 if (node.get("lean_statement") or
                                            node.get("smallest_formalizable_subcase")) else 0.25,
        "evidence_available": 0.7 if node.get("evidence") else 0.3,
        "theorem_connectivity": 0.70 if (node.get("precondition_gap") or
                                         node.get("candidate_theorem")) else 0.35,
        "repeat_failure_risk": (0.05 if node.get("mutation_applied") else
                               0.75 if (node.get("id") in gap_ids) else
                               0.45 if failed else 0.15),
    }
    reasons = [f"{k}={v:.2f}" for k, v in feats.items()]
    return round(weighted(feats, BARRIER_WEIGHTS), 4), reasons

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("barrier"); b.add_argument("--candidates", required=True)
    b.add_argument("--json", action="store_true")
    m = sub.add_parser("mutation"); m.add_argument("--gap-class", required=True)
    m.add_argument("--used", nargs="*", default=[]); m.add_argument("--json", action="store_true")
    sub.add_parser("axes")
    a = ap.parse_args()

    if a.cmd == "axes":
        for gap, axes in sorted(AXES_BY_GAP.items()):
            print(f"  {gap}:")
            for x in axes: print(f"      {x}")
        return 0

    if a.cmd == "mutation":
        axes = AXES_BY_GAP.get(a.gap_class)
        if not axes:
            print(f"unknown gap class {a.gap_class!r}; known: {sorted(AXES_BY_GAP)}",
                  file=sys.stderr); return 2
        used = {u.lower() for u in a.used}
        ranked = []
        for axis in axes:
            feats = {"gap_class_match": 0.85, "one_axis_clarity": 0.9 if len(axis.split())<=4 else 0.65,
                     "expected_unlock": 0.75 if any(w in axis for w in
                        ("precondition","invariant","obstruction","reduction","theorem")) else 0.55,
                     "verifier_friendliness": 0.72 if any(w in axis for w in
                        ("formalize","finite","precondition","artifact")) else 0.45,
                     "novelty_against_failures": 0.25 if axis.lower() in used else 0.82,
                     "used_axis_penalty": 1.0 if axis.lower() in used else 0.0}
            ranked.append({"axis": axis, "score": round(weighted(feats, MUTATION_WEIGHTS),4),
                           "already_used": axis.lower() in used})
        ranked.sort(key=lambda r: -r["score"])
        out = {"gap_class": a.gap_class, "ranked_axes": ranked,
               "rule": "change exactly one axis; record what was held constant"}
        print(json.dumps(out, indent=2) if a.json else
              "\n".join(f"  {r['score']:.3f}  {r['axis']}" +
                        ("   (already used)" if r["already_used"] else "") for r in ranked))
        return 0

    try:
        payload = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    nodes = payload if isinstance(payload, list) else payload.get("nodes", [])
    gap_ids = set(payload.get("gap_feedback_ids", [])) if isinstance(payload, dict) else set()
    failed = payload.get("failed_approaches", []) if isinstance(payload, dict) else []
    ranked = []
    for n in nodes:
        score, reasons = score_barrier(n, len(nodes), gap_ids, failed)
        ranked.append({"id": n.get("id") or n.get("node_id"), "score": score, "reasons": reasons})
    ranked.sort(key=lambda r: -r["score"])
    print(json.dumps({"ranked": ranked}, indent=2) if a.json else
          "\n".join(f"  {r['score']:.3f}  {r['id']}" for r in ranked))
    return 0

if __name__ == "__main__":
    sys.exit(main())
