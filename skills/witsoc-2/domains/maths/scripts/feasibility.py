#!/usr/bin/env python3
"""Formalization feasibility — can this be encoded at all, and at what cost.

Separate from "is it true" and separate from "is it worth doing". A high score
with any blocker is still not READY: the gate is score AND empty blockers,
because one missing definition stops everything regardless of how good the rest
looks.

Bands:
    >= 78, no blockers  FORMALIZATION_READY        -> the kernel tier
    >= 62               NEEDS_LOCAL_DEFINITIONS    -> WIT first, then Lean
    >= 45               NEEDS_CORPUS_SEARCH        -> back to Explorer
    else                POOR_TARGET                -> decompose further

Usage:  feasibility.py --state <state.json> [--json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def assess(s: dict) -> dict:
    score, reasons, blockers = 50, [], []
    audit = s.get("theorem_audit", [])
    if audit:
        avail = sum(6 for t in audit if t.get("availability") == "yes")
        avail += sum(3 for t in audit if t.get("availability") == "partial")
        capped = min(18, avail); score += capped
        reasons.append(f"+{capped} external results resolved in the corpus")
        if not any(t.get("availability") for t in audit):
            score -= 15; reasons.append("-15 the audit records no availability at all")
    missing = [t for t in audit if t.get("missing_preconditions")]
    if missing:
        pen = min(18, 6*len(missing)); score -= pen
        reasons.append(f"-{pen} {len(missing)} cited result(s) with unmet preconditions")
    verified = [w for w in s.get("workers", []) if str(w.get("status","")).upper()
                in {"CHECKED","VERIFIED","VERIFIED_LEAN","VERIFIED_WIT"}]
    if s.get("workers"):
        if verified:
            b = min(12, 4*len(verified)); score += b; reasons.append(f"+{b} verified sub-results")
        else:
            score -= 8; reasons.append("-8 workers ran but nothing verified")
    if s.get("artifacts"): score += 10; reasons.append("+10 an artifact already exists")
    subcases = s.get("formalizable_subcases", [])
    if subcases:
        b = min(12, 3*len(subcases)); score += b
        reasons.append(f"+{b} {len(subcases)} formalizable subcase(s)")

    for d in s.get("undefined_concepts", []):
        blockers.append(f"no formal definition available for '{d}'")
    for p in s.get("unregistered_predicates", []):
        blockers.append(f"predicate '{p}' is not registered — it would formalize to a stub")

    score = max(0, min(100, score))
    if score >= 78 and not blockers:
        label, rec = "FORMALIZATION_READY", "kernel tier"
    elif score >= 62:
        label, rec = "NEEDS_LOCAL_DEFINITIONS", "WIT first, then Lean"
    elif score >= 45:
        label, rec = "NEEDS_CORPUS_SEARCH", "back to Explorer for premise retrieval"
    else:
        label, rec = "POOR_TARGET", "decompose further before formalizing"
    if blockers and label == "FORMALIZATION_READY":
        label, rec = "NEEDS_LOCAL_DEFINITIONS", "blockers present; resolve them first"
    return {"score": score, "label": label, "recommendation": rec,
            "reasons": reasons, "blockers": blockers,
            "gate_note": "READY requires score AND zero blockers"}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: s = json.loads(Path(a.state).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    r = assess(s)
    if a.json: print(json.dumps(r, indent=2))
    else:
        print(f"FEASIBILITY {r['score']}/100 — {r['label']}\n  recommend: {r['recommendation']}")
        for x in r["reasons"]: print(f"    {x}")
        for b in r["blockers"]: print(f"    BLOCKER: {b}")
    return 0 if r["label"] == "FORMALIZATION_READY" else 1

if __name__ == "__main__":
    sys.exit(main())
