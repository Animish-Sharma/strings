#!/usr/bin/env python3
"""Repair cycle state machine.

doctrine/repair.md states the budget. This enforces it, because a budget nobody
counts is a budget nobody keeps — and the dominant waste mode in formal work is
re-running an attempt that already failed for a known reason.

Two counters:
  same_class_no_reduction  counts back from the latest attempt, breaking on a
                           class change OR on obligation_delta == "reduced".
                           Three means: stop editing, go back to the sketch.
  expensive_count          eight expensive runs on one approach means that
                           approach is exhausted, whatever the class mix.

Hard errors (not warnings):
  - an expensive attempt with no repair_hypothesis. If you cannot say what will
    be different, it is compiler-chasing, not repair.
  - a duplicate attempt_id, or a changed target hash mid-cycle.

Usage:
    repair_cycle.py init --state S --target-hash H --artifact A
    repair_cycle.py record --state S --failure-class C --diagnostic "..." \
        --obligation-delta reduced|same|worse|unknown [--hypothesis "..."] [--expensive]
    repair_cycle.py status --state S [--json]
Exit: 0 ok, 1 refused/blocked, 2 IO error.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

MAX_SAME_CLASS = 3
MAX_EXPENSIVE = 8
DELTAS = {"reduced","same","worse","unknown"}

# Who owns the fix. Routing a maths problem to the artifact engine wastes both.
GENERATOR_LOCAL = {"import_missing","type_mismatch","coercion_issue","unsolved_goal",
                   "step_too_compressed","case_not_closed","algebra_logic_error",
                   "unknown_identifier"}
NEEDS_RESEARCH  = {"target_drift","missing_premise","precondition_not_discharged",
                   "quantifier_or_domain_mismatch","vacuous_proof","false_statement",
                   "out_of_scope_reference","forbidden_escape"}

def signature(failure_class: str, diagnostic: str) -> str:
    """Normalized so the same failure twice looks the same: positions, metavariable
    numbers, and trailing indices stripped."""
    first = next((l for l in (diagnostic or "").splitlines() if l.strip()), "")
    first = re.sub(r"\d+:\d+", "L:C", first)
    first = re.sub(r"[?]m\.\d+|\bm\.\d+", "?m", first)
    first = re.sub(r"\.\d+\b", "", first)
    return f"{failure_class}|{' '.join(first.split())[:120]}"

def compute(state: dict) -> dict:
    attempts = state.get("attempts", [])
    expensive = sum(1 for a in attempts if a.get("expensive_run"))
    same = 0
    if attempts:
        latest = attempts[-1]["failure_class"]
        for a in reversed(attempts):
            if a["failure_class"] != latest or a.get("obligation_delta") == "reduced":
                break
            same += 1
    seen = [a["failure_signature"] for a in attempts]
    repeated = len(seen) != len(set(seen))

    status, why = "READY_TO_REPAIR", "budget remains"
    if any(a["failure_class"] == "forbidden_escape" for a in attempts):
        status, why = "BLOCKED", "a placeholder or escape hatch is present; it voids any verdict"
    elif any(a["failure_class"] == "target_drift" for a in attempts):
        status, why = "BLOCKED", "the artifact no longer states the frozen target"
    elif expensive >= MAX_EXPENSIVE:
        status, why = "SKETCH_EXHAUSTED", (
            f"{expensive} expensive runs on one approach; rotate the approach rather "
            "than editing it further")
    elif same >= MAX_SAME_CLASS:
        status, why = "ESCALATE", (
            f"{same} consecutive '{attempts[-1]['failure_class']}' failures with no "
            "obligation reduced; go back to the sketch level")
    elif repeated:
        status, why = "ESCALATE", (
            "a failure signature repeated: the last attempt changed nothing the "
            "checker could see")
    elif attempts and attempts[-1]["failure_class"] in NEEDS_RESEARCH:
        status, why = "ROUTE_TO_RESEARCHER", (
            f"'{attempts[-1]['failure_class']}' is a mathematical gap, not an "
            "artifact defect")
    elif attempts and attempts[-1]["failure_class"] == "toolchain_unavailable":
        status, why = "TOOLCHAIN_BLOCKED", "the checker could not run; this is a gap, not a pass"

    return {"status": status, "why": why, "attempts": len(attempts),
            "same_class_no_reduction": same, "expensive_count": expensive,
            "repeated_signature": repeated,
            "budget": {"max_same_class": MAX_SAME_CLASS, "max_expensive": MAX_EXPENSIVE}}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--state", required=True)
    i.add_argument("--target-hash", required=True); i.add_argument("--artifact", required=True)
    r = sub.add_parser("record"); r.add_argument("--state", required=True)
    r.add_argument("--failure-class", required=True); r.add_argument("--diagnostic", default="")
    r.add_argument("--obligation-delta", required=True, choices=sorted(DELTAS))
    r.add_argument("--hypothesis", default=""); r.add_argument("--expensive", action="store_true")
    r.add_argument("--attempt-id")
    s = sub.add_parser("status"); s.add_argument("--state", required=True); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        Path(a.state).write_text(json.dumps({"schema":"maths.repair_cycle.v1",
            "target_hash":a.target_hash,"artifact":a.artifact,"attempts":[]}, indent=2)+"\n")
        print(f"initialized {a.state}"); return 0

    try:
        st = json.loads(Path(a.state).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "record":
        if a.expensive and not a.hypothesis.strip():
            print("REFUSED: an expensive attempt needs a repair hypothesis. If you "
                  "cannot say what will be different, that is compiler-chasing, not "
                  "repair.", file=sys.stderr)
            return 1
        aid = a.attempt_id or f"repair-{len(st['attempts'])+1}"
        if any(x["attempt_id"] == aid for x in st["attempts"]):
            print(f"REFUSED: duplicate attempt_id {aid!r}", file=sys.stderr); return 1
        st["attempts"].append({"attempt_id": aid, "failure_class": a.failure_class,
            "diagnostic_excerpt": (a.diagnostic or "")[:1200],
            "failure_signature": signature(a.failure_class, a.diagnostic),
            "repair_hypothesis": a.hypothesis, "obligation_delta": a.obligation_delta,
            "expensive_run": bool(a.expensive),
            "owner": ("generator" if a.failure_class in GENERATOR_LOCAL else
                      "researcher" if a.failure_class in NEEDS_RESEARCH else "unknown")})
        Path(a.state).write_text(json.dumps(st, indent=2)+"\n")
        result = compute(st)
        print(f"recorded {aid}  ->  {result['status']}")
        print(f"  {result['why']}")
        return 0 if result["status"] == "READY_TO_REPAIR" else 1

    result = compute(st)
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"REPAIR CYCLE: {result['status']}")
        print(f"  {result['why']}")
        print(f"  attempts {result['attempts']}   same-class {result['same_class_no_reduction']}"
              f"/{MAX_SAME_CLASS}   expensive {result['expensive_count']}/{MAX_EXPENSIVE}")
    return 0 if result["status"] == "READY_TO_REPAIR" else 1

if __name__ == "__main__":
    sys.exit(main())
