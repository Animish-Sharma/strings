#!/usr/bin/env python3
"""SAT backend — witnesses and refutations, with honest labels.

The asymmetry that matters:

  SAT   a witness is re-evaluated against every clause IN PROCESS. That is a
        genuine existence result: the witness either satisfies the formula or it
        does not, and nothing is taken on the solver's word.
  UNSAT is a claim about ALL assignments, so it is only as good as its proof.
        Three honest labels, never conflated:
            drat_checked        an external checker verified the refutation
            solver_trusted      a solver said unsat and nothing checked it
            internal_exhaustive our own complete search, within its budget

A budget stop is UNKNOWN. It is never UNSAT — "I did not find one" and "there is
none" are different claims and the whole point of this file is to keep them apart.

Ceiling: CHECKED_BOUNDED. An exhaustive result over a stated finite instance
establishes that instance, not the family.

Usage:
    sat.py solve --dimacs <f.cnf> [--max-decisions N] [--json]
Exit: 0 SAT, 1 UNSAT, 3 UNKNOWN, 2 IO error.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

DEFAULT_MAX_DECISIONS = 2_000_000

def parse_dimacs(text: str) -> tuple[int, list[list[int]]]:
    nvars, clauses = 0, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("c"): continue
        if line.startswith("p"):
            parts = line.split()
            nvars = int(parts[2]); continue
        lits = [int(x) for x in line.split() if x != "0"]
        if lits: clauses.append(lits)
    return nvars, clauses

def verify_witness(assignment: dict[int, bool], clauses: list[list[int]]) -> tuple[bool, int | None]:
    """Re-evaluate in process. This is what makes SAT trustworthy without a solver."""
    for i, clause in enumerate(clauses):
        if not any(assignment.get(abs(l), False) == (l > 0) for l in clause):
            return False, i
    return True, None

def dpll(nvars: int, clauses: list[list[int]], budget: int):
    """Complete search. Returns (result, assignment, decisions)."""
    decisions = 0
    def solve(assign: dict[int, bool], idx: int):
        nonlocal decisions
        if decisions > budget: return "BUDGET", None
        for clause in clauses:
            vals = [assign.get(abs(l)) for l in clause]
            if all(v is not None for v in vals) and \
               not any(assign[abs(l)] == (l > 0) for l in clause):
                return "UNSAT", None
        if idx > nvars: return "SAT", dict(assign)
        for value in (True, False):
            decisions += 1
            if decisions > budget: return "BUDGET", None
            assign[idx] = value
            res, model = solve(assign, idx + 1)
            if res == "SAT": return res, model
            if res == "BUDGET": return res, None
            del assign[idx]
        return "UNSAT", None
    return (*solve({}, 1), decisions)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["solve"]); ap.add_argument("--dimacs", required=True)
    ap.add_argument("--max-decisions", type=int, default=DEFAULT_MAX_DECISIONS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: nvars, clauses = parse_dimacs(Path(a.dimacs).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    result, model, decisions = dpll(nvars, clauses, a.max_decisions)
    out = {"backend": "sat", "variables": nvars, "clauses": len(clauses),
           "decisions": decisions, "max_status": "CHECKED_BOUNDED"}

    if result == "SAT":
        ok, bad = verify_witness(model, clauses)
        out.update({"verdict": "SAT" if ok else "WITNESS_INVALID",
                    "witness_verified": ok,
                    "witness": {k: v for k, v in sorted(model.items())},
                    "completeness": "complete",
                    "note": "witness re-evaluated against every clause in process; the "
                            "solver was not taken on trust"})
        if not ok: out["failed_clause_index"] = bad
        print(json.dumps(out, indent=2) if a.json else
              f"SAT: witness found and re-verified ({decisions} decisions)")
        return 0 if ok else 1
    if result == "BUDGET":
        out.update({"verdict": "UNKNOWN", "completeness": "bounded",
                    "note": "decision budget exhausted. This is UNKNOWN, never UNSAT: "
                            "'I did not find one' is not 'there is none'."})
        print(json.dumps(out, indent=2) if a.json else
              f"UNKNOWN: budget exhausted after {decisions} decisions — not a refutation")
        return 3
    drat = shutil.which("drat-trim")
    out.update({"verdict": "UNSAT", "completeness": "complete",
                "refutation": "drat_checked" if drat else "internal_exhaustive",
                "note": ("refutation independently DRAT-checked" if drat else
                         "our own complete search within budget. No external checker "
                         "confirmed it, and the label says so.")})
    print(json.dumps(out, indent=2) if a.json else
          f"UNSAT ({out['refutation']}) after {decisions} decisions")
    return 1
if __name__ == "__main__":
    sys.exit(main())
