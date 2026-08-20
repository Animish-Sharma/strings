#!/usr/bin/env python3
"""Solve-claim gate — the four requirements before "solved" may be said.

Mathematical priority is real: a correct result that was already known is not a
discovery, and a correct result nobody else can re-derive is not yet a result.
So the gate is not just "did the kernel pass".

    1. audit_passed        every stage-1 condition below
    2. formal_receipt      for FORMAL_SOLVE: a real kernel receipt, not an
                           environment check that merely proved Lean runs
    3. independent_rederivation  a DIFFERENT run directory, passing its own
                           stage-1 audit, with a MATCHING frozen-target hash
    4. novelty NOVEL_CANDIDATE   KNOWN rejects on priority; LOCALLY_NEW_UNCHECKED
                           is not enough

Stage-1 conditions: frozen target present; every node strong or dead-with-no-
strong-dependents; every dependency of a strong node is strong; no cycle among
strong nodes; >= 3 passing skeptic reviews per strong node each checking drift,
hidden assumptions, circularity and weaker-target substitution; no unresolved
gap class on a strong node; disproof-first searched with zero witnesses; every
theorem precondition resolved.

Only SOLVE_ACCEPTED may be reported as a solve. REJECTED is terminal.

Usage:  solve_gate.py --claim <solve_claim.json> [--json]
Exit: 0 accepted, 1 not accepted, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

STRONG = {"PROVED_SKETCH","VERIFIED","VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL"}
DEAD = {"FAILED_ATTEMPT","ABANDONED","DEAD"}
RESOLVED_GAPS = {"", "none", "no_gap", "resolved", "closed", "benign"}
SKEPTIC_CHECKS = ("target_drift_checked","hidden_assumptions_checked",
                  "circularity_checked","weaker_target_checked")
MIN_SKEPTICS = 3

def stage1(run: dict) -> list[str]:
    missing = []
    if not run.get("target_hash"):
        missing.append("no frozen target hash")
    nodes = {n.get("node_id") or n.get("id"): n for n in run.get("nodes", [])}
    strong_ids = {i for i, n in nodes.items() if str(n.get("status","")).upper() in STRONG}

    for nid, n in nodes.items():
        status = str(n.get("status","")).upper()
        if status not in STRONG and status not in DEAD:
            missing.append(f"node {nid} is {status or 'OPEN'}: neither strong nor dead")
        if status in DEAD:
            for other, o in nodes.items():
                if other in strong_ids and nid in (o.get("depends_on") or []):
                    missing.append(f"strong node {other} depends on dead node {nid}")

    for nid in strong_ids:
        for dep in nodes[nid].get("depends_on", []) or []:
            if dep not in strong_ids:
                missing.append(f"strong node {nid} depends on {dep}, which is not strong")
        reviews = [r for r in run.get("skeptic_reviews", []) if r.get("node_id") == nid]
        passing = [r for r in reviews if r.get("verdict") == "pass"
                   and all(r.get(c) for c in SKEPTIC_CHECKS)]
        if len(passing) < MIN_SKEPTICS:
            missing.append(f"node {nid} has {len(passing)} fully-checked passing skeptic "
                           f"review(s), needs {MIN_SKEPTICS}")
        gap = str(run.get("gap_classes", {}).get(nid, "")).lower()
        if gap not in RESOLVED_GAPS:
            missing.append(f"node {nid} has unresolved gap class {gap!r}")

    colour = {}
    def visit(nid, stack):
        if colour.get(nid) == 2: return
        if colour.get(nid) == 1:
            missing.append(f"cycle among strong nodes: {' -> '.join(stack + [nid])}"); return
        colour[nid] = 1
        for dep in nodes.get(nid, {}).get("depends_on", []) or []:
            if dep in strong_ids: visit(dep, stack + [nid])
        colour[nid] = 2
    for nid in strong_ids: visit(nid, [])

    df = run.get("disproof_first", {})
    if not df.get("searched"):
        missing.append("disproof-first was not run — a proof campaign that never "
                       "tried to refute the statement skipped the cheapest check")
    if df.get("witnesses"):
        missing.append(f"disproof-first found {len(df['witnesses'])} witness(es): "
                       "the statement may be false")
    for t in run.get("theorem_preconditions", []):
        if str(t.get("status","")).upper() != "RESOLVED":
            missing.append(f"theorem precondition {t.get('name','?')} is not RESOLVED")
    return missing

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--claim", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    missing: list[str] = []
    audit = stage1(claim.get("run", {}))
    missing += [f"stage-1: {m}" for m in audit]

    stage = str(claim.get("stage","MATHEMATICAL_SOLVE")).upper()
    if stage == "FORMAL_SOLVE":
        receipt = claim.get("lean_receipt") or {}
        if not receipt.get("valid"):
            missing.append("FORMAL_SOLVE needs a validated kernel receipt "
                           "(an environment check that proves the toolchain runs is not one)")

    rederivations = [r for r in claim.get("rederivations", []) if r.get("verified")]
    if not rederivations:
        missing.append("no verified independent re-derivation: a result nobody else "
                       "can reach is not yet a result")
    else:
        for r in rederivations:
            if r.get("target_hash") != claim.get("run", {}).get("target_hash"):
                missing.append(f"re-derivation {r.get('run_dir','?')} has a different "
                               "target hash: it re-derived something else")
            if r.get("run_dir") and r.get("run_dir") == claim.get("run", {}).get("run_dir"):
                missing.append("the re-derivation is the same run directory; that is a "
                               "repeat, not independence")

    novelty = str(claim.get("novelty", {}).get("verdict","")).upper()
    if novelty != "NOVEL_CANDIDATE":
        missing.append(f"novelty verdict is {novelty or 'absent'}, needs NOVEL_CANDIDATE "
                       "(KNOWN rejects on priority; LOCALLY_NEW_UNCHECKED is not enough)")

    computed = "SOLVE_ACCEPTED" if not missing else "NOT_ACCEPTED"
    out = {"computed_status": computed, "stage": stage,
           "missing_requirements": missing,
           "note": "computed, never stored free-form. Only SOLVE_ACCEPTED may be "
                   "reported as a solve."}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"SOLVE GATE: {computed}")
        for m in missing: print(f"  missing: {m}")
    return 0 if computed == "SOLVE_ACCEPTED" else 1

if __name__ == "__main__":
    sys.exit(main())
