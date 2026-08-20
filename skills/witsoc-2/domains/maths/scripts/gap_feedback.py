#!/usr/bin/env python3
"""Gap feedback — classify a failure, propose ONE axis, block a bare retry.

Every non-closed node gets exactly one gap class and exactly one proposed
one-axis mutation. Axes ROTATE across rounds, so round two never re-proposes
round one's axis.

The dispatch guard is the point: a node whose statement is unchanged since its
last failure and whose entry records no mutation_applied is BLOCKED_NO_MUTATION.
Re-running an attempt that already failed for a known reason is the dominant
waste mode in a long campaign.

Usage:
    gap_feedback.py classify --results <results.json> [--round N] [--json]
    gap_feedback.py check-dispatch --node <node.json> [--json]
Exit: 0 ok, 1 blocked/problem, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

GAP_CLASSES = {
    "prover_search_gap":  "the tactic portfolio missed it; the maths may be fine",
    "genuine_barrier":    "the mathematics resisted after real external pressure",
    "formalization_block":"the checker never saw a real goal",
    "precondition_gap":   "a needed premise is missing or unmet",
}
# Axis menus per class, in rotation order.
AXES = {
    "prover_search_gap":   ["method","encoding","object_class","computational_bound"],
    "genuine_barrier":     ["invariant","statement_strength","object_class","encoding"],
    "formalization_block": ["formalization_target","encoding","statement_strength","method"],
    "precondition_gap":    ["theorem_source","statement_strength","invariant","method"],
}
DEFAULT_AXIS = {"genuine_barrier":"invariant","formalization_block":"formalization_target",
                "precondition_gap":"theorem_source","prover_search_gap":"method"}

def classify_one(result: dict) -> str:
    status = str(result.get("status","OPEN")).upper()
    fc = str(result.get("failure_class","")).lower()
    if fc in {"target_drift","artifact_issue","forbidden_escape"} or status == "REJECTED":
        return "formalization_block"
    if fc in {"missing_premise","precondition_not_discharged","theorem_precondition_gap",
              "unknown_identifier","import_missing","out_of_scope_reference"}:
        return "precondition_gap"
    if fc in {"genuine_mathematical_barrier","missing_actual_barrier_lemma",
              "false_statement","hidden_assumption"}:
        return "genuine_barrier"
    if status == "GAP" or not result.get("lean_statement"):
        return "formalization_block"
    return "prover_search_gap"

def statement_sha(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode()).hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify"); c.add_argument("--results", required=True)
    c.add_argument("--round", type=int, default=1); c.add_argument("--json", action="store_true")
    d = sub.add_parser("check-dispatch"); d.add_argument("--node", required=True)
    d.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        payload = json.loads(Path(getattr(a, "results", None) or a.node).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "check-dispatch":
        node = payload
        last = node.get("last_failed_statement_sha")
        now = statement_sha(node.get("statement",""))
        mutation = node.get("mutation_applied")
        if last and last == now and not mutation:
            out = {"dispatch": "BLOCKED_NO_MUTATION",
                   "why": ("the statement is unchanged since its last failure and no "
                           "mutation_applied is recorded. Re-running it would repeat a "
                           "known failure. Change one axis, or change the statement.")}
            print(json.dumps(out, indent=2) if a.json else
                  f"DISPATCH: BLOCKED_NO_MUTATION\n  {out['why']}")
            return 1
        out = {"dispatch": "ALLOWED",
               "why": "statement changed" if last != now else "mutation recorded"}
        print(json.dumps(out, indent=2) if a.json else f"DISPATCH: ALLOWED ({out['why']})")
        return 0

    results = payload if isinstance(payload, list) else payload.get("results", [])
    entries = []
    for res in results:
        if str(res.get("status","")).upper() in {"CHECKED","VERIFIED","VERIFIED_LEAN",
                                                  "VERIFIED_WIT","CLOSED"}:
            continue
        gap = classify_one(res)
        menu = AXES[gap]
        axis = menu[(a.round - 1) % len(menu)]
        entries.append({
            "node_id": res.get("node_id") or res.get("id"),
            "gap_class": gap, "why_this_class": GAP_CLASSES[gap],
            "failed_statement_sha": statement_sha(res.get("statement","")),
            "proposed_mutation": {"axis": axis, "round": a.round,
                "note": f"round {a.round} axis; round {a.round+1} would propose "
                        f"'{menu[a.round % len(menu)]}'"},
            "default_axis_for_class": DEFAULT_AXIS[gap],
            "do_not_repeat": f"{gap} via {res.get('method_family','unrecorded method')}",
            "revival_condition": "a new admitted sub-claim, a refuted obstruction, or a "
                                 "new counterexample family re-prices this branch",
        })

    out = {"round": a.round, "nodes": entries,
           "note": "one class and one axis per node; axes rotate so a later round "
                   "cannot re-propose this round's axis"}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"GAP FEEDBACK round {a.round} — {len(entries)} open node(s)\n")
        for e in entries:
            print(f"  {e['node_id']}: {e['gap_class']}")
            print(f"      {e['why_this_class']}")
            print(f"      mutate axis '{e['proposed_mutation']['axis']}'")
    return 0

if __name__ == "__main__":
    sys.exit(main())
