#!/usr/bin/env python3
"""What to do now — exactly one action, in a fixed order.

Long campaigns die on turn discipline more often than on the mathematics. So
this returns ONE action and its exact command, never a menu.

Priority order (first match wins) — and the ordering is the content:
    1  no frozen target        freeze it; nothing downstream is valid without it
    2  no reduction ledger     seed it WITH an honest open core
    3  reduction not audited   audit coverage adversarially
    4  no obligation DAG       decompose
    5  repair budget spent     escalate; more edits are waste
    6  open nodes remain       crank the loop
    7  all closed              run the solve gate
Usage:  next_action.py --state <state.json> [--json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def decide(s: dict) -> dict:
    if not s.get("frozen_target"):
        return {"action":"freeze_target","command":"(Explorer) freeze the exact statement",
                "why":"nothing downstream is valid without it"}
    if not s.get("reduction_ledger"):
        return {"action":"seed_reduction",
                "command":"reduction_ledger.py init --target ... && open-core --add ...",
                "why":"declare the open core now, so progress is scored against the "
                      "target rather than against whichever obligations were seeded"}
    if not s.get("reduction_coverage_audited"):
        return {"action":"audit_reduction_coverage",
                "command":"reduction_ledger.py audit --ledger ...",
                "why":"find an instance covered by neither an obligation nor the open "
                      "core; such a hole makes the decomposition unsound, not incomplete"}
    if not s.get("proof_dag"):
        return {"action":"decompose","command":"proof_dag.py validate <dag.json>",
                "why":"the target needs sub-obligations before work can be dispatched"}
    repair = s.get("repair_status")
    if repair in {"ESCALATE","SKETCH_EXHAUSTED","BLOCKED"}:
        return {"action":"escalate_to_researcher","command":"(hand the obstruction over)",
                "why":f"repair cycle is {repair}; further local edits are waste"}
    if s.get("open_nodes"):
        return {"action":"crank_loop","command":"select.py barrier --candidates ...",
                "why":f"{len(s['open_nodes'])} node(s) still open"}
    return {"action":"run_solve_gate","command":"solve_gate.py --claim solve_claim.json",
            "why":"everything is closed; the gate decides whether that is a solve"}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: s = json.loads(Path(a.state).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    d = decide(s)
    print(json.dumps(d, indent=2) if a.json else
          f"NEXT: {d['action']}\n  {d['command']}\n  why: {d['why']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
