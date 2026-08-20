#!/usr/bin/env python3
"""Proof DAG — maths node typology and the integrity rules a generic graph lacks.

The frame owns generic claim graphs. What it cannot know is what a mathematical
obligation looks like, and four rules that are specific to this field:

  a) every node's dependency_path_to_target must NAME a target node. A verified
     sub-result that cannot be traced to the target is not progress toward it,
     and this is where drift hides.
  b) an accepted node may not depend on an unusable one. Using a conjecture as
     a theorem is the single most common way a wrong result passes review.
  c) a weaker or conditional product needs a closure audit with >= 2 recorded
     closure attempts. Without it, "partial result" means "I stopped".
  d) accepted nodes need target_fidelity >= 0.75, or >= 0.95 when the status is
     not an explicitly partial product.

Usage:  proof_dag.py validate <dag.json> [--json]
Exit: 0 valid, 1 violations, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

NODE_TYPES = {"target","lemma","actual_barrier_lemma","mined_barrier_lemma","reduction",
    "special_case","conditional_theorem","obstruction","counterexample_search",
    "computational_certificate","external_theorem_precondition","precondition_bridge",
    "formalizable_subcase","formalization_bridge","hypothesis_isolation",
    "definition_audit","concept","failed_method"}
RELATIONS = {"implies","equivalent","reduces_to","instantiates","discharges_precondition",
    "supplies_witness","establishes_bound","rules_out_obstruction"}
FAILURE_CLASSES = {"none","false_claim","target_drift","weaker_target_substitution",
    "hidden_assumption","circularity","theorem_precondition_gap",
    "missing_actual_barrier_lemma","genuine_mathematical_barrier",
    "computational_obstruction","artifact_issue"}
UNUSABLE = {"OPEN","GAP","CONJECTURE","REJECTED","FAILED_ATTEMPT"}
ACCEPTED = {"CHECKED","CHECKED_BOUNDED","CHECKED_SYMBOLIC","VERIFIED","VERIFIED_WIT",
            "VERIFIED_LEAN","VERIFIED_EXTERNAL","PROVED_SKETCH"}
PRODUCT_STATUSES = {"PARTIAL","CONDITIONAL"}
SKEPTIC_CLASSES = {"target_drift","known_result_restatement","hidden_assumption",
                   "finite_evidence_only","genuine_progress","needs_repair"}

def validate(dag: dict) -> list[str]:
    problems: list[str] = []
    nodes = dag.get("nodes", [])
    if not nodes:
        return ["DAG has no nodes"]

    ids, seen = {}, set()
    for n in nodes:
        nid = n.get("node_id") or n.get("id")
        if not nid:
            problems.append("a node has no node_id"); continue
        if nid in seen:
            problems.append(f"duplicate node_id {nid!r}")
        seen.add(nid); ids[nid] = n

    targets = [n for n in nodes if n.get("type") == "target"]
    if not targets:
        problems.append("no node of type 'target' — nothing to be progress toward")
    target_ids = {t.get("node_id") or t.get("id") for t in targets}

    for nid, n in ids.items():
        t = n.get("type")
        if t not in NODE_TYPES:
            problems.append(f"{nid}: type {t!r} is not a maths node type")
        if not (n.get("statement") or "").strip():
            problems.append(f"{nid}: empty statement")
        if not n.get("target_hash"):
            problems.append(f"{nid}: no target_hash")
        fc = n.get("failure_class", "none")
        if fc not in FAILURE_CLASSES:
            problems.append(f"{nid}: failure_class {fc!r} unknown")

        # (a) the anti-drift teeth
        path = n.get("dependency_path_to_target") or []
        if t != "target":
            if not path:
                problems.append(f"{nid}: no dependency_path_to_target")
            elif not (set(path) & target_ids):
                problems.append(
                    f"{nid}: dependency_path_to_target {path} names no target node — "
                    "a sub-result that cannot be traced to the target is not progress "
                    "toward it")

        for dep in n.get("depends_on", []) or []:
            if dep not in ids:
                problems.append(f"{nid}: depends on {dep!r}, which does not exist")
        for rel in n.get("relations", []) or []:
            if isinstance(rel, dict) and rel.get("relation") not in RELATIONS:
                problems.append(f"{nid}: relation {rel.get('relation')!r} unknown")

        status = str(n.get("status", "OPEN")).upper()
        if status in ACCEPTED:
            # (b) no conjecture-as-theorem
            for dep in n.get("depends_on", []) or []:
                ds = str(ids.get(dep, {}).get("status", "OPEN")).upper()
                if ds in UNUSABLE:
                    problems.append(
                        f"{nid} is {status} but depends on {dep} which is {ds}: "
                        "an unestablished claim cannot be consumed as established")
            if not n.get("evidence"):
                problems.append(f"{nid}: {status} with no evidence")
            if not n.get("skeptic_review_id"):
                problems.append(f"{nid}: {status} with no skeptic_review_id")
            # (d) fidelity thresholds
            fid = n.get("target_fidelity")
            floor = 0.75 if status in PRODUCT_STATUSES else 0.95
            if fid is None:
                problems.append(f"{nid}: {status} with no target_fidelity")
            elif float(fid) < floor:
                problems.append(f"{nid}: target_fidelity {fid} < {floor} required for {status}")

        # (c) weaker products must show their work
        if t in {"special_case","conditional_theorem"} or status in PRODUCT_STATUSES:
            audit = n.get("closure_audit")
            if not audit:
                problems.append(
                    f"{nid}: a weaker/conditional product needs a closure_audit — "
                    "without one, 'partial result' means 'I stopped'")
            else:
                for field in ("remaining_gap_statement","why_not_full_solution",
                              "known_result_comparison","next_exact_experiment_or_lemma"):
                    if not audit.get(field):
                        problems.append(f"{nid}: closure_audit missing {field}")
                attempts = audit.get("closure_attempts") or []
                if len(attempts) < 2:
                    problems.append(
                        f"{nid}: closure_audit has {len(attempts)} closure_attempts, "
                        "needs >= 2")
                sc = audit.get("skeptic_claim_classification")
                if sc and sc not in SKEPTIC_CLASSES:
                    problems.append(f"{nid}: skeptic_claim_classification {sc!r} unknown")

        if t == "actual_barrier_lemma":
            if not n.get("actual_barrier_statement"):
                problems.append(f"{nid}: barrier lemma with no actual_barrier_statement")
            if status in {"GAP","FAILED_ATTEMPT"} and int(n.get("direct_attack_count", 0)) < 1:
                problems.append(
                    f"{nid}: reports {status} with no recorded direct attack — "
                    "an unattacked barrier is not a finding")

    # cycles
    colour: dict[str, int] = {}
    def visit(nid: str, stack: list[str]) -> None:
        if colour.get(nid) == 2: return
        if colour.get(nid) == 1:
            problems.append(f"cycle: {' -> '.join(stack + [nid])}"); return
        colour[nid] = 1
        for dep in ids.get(nid, {}).get("depends_on", []) or []:
            if dep in ids: visit(dep, stack + [nid])
        colour[nid] = 2
    for nid in ids: visit(nid, [])

    return problems

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["validate"]); ap.add_argument("dag")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        dag = json.loads(Path(a.dag).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    problems = validate(dag)
    if a.json:
        print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
    elif problems:
        print(f"PROOF DAG: INVALID — {len(problems)} problem(s)\n")
        for p in problems: print(f"  {p}")
    else:
        print(f"PROOF DAG: VALID — {len(dag.get('nodes', []))} node(s)")
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
