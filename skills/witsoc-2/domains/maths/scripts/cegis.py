#!/usr/bin/env python3
"""CEGIS ledger — counterexample-guided refinement, with a hard ceiling.

The refinement loop is where the temptation lives: a candidate survives ten
checks, then a hundred, and the pressure to call it proved becomes enormous.

So the ceiling is structural, not advisory. The strongest positive status a
candidate can ever reach here is SURVIVED_CHECKS. Proof statuses are refused by
the ledger itself — unbounded finite verification of a universally quantified
statement is not evidence of the universal, and no number of passes changes the
quantifier.

A failing check does not go through `check`; it goes through `counterexample`,
which requires a concrete witness. "It seemed to fail" is not a refutation.

Usage:
    cegis.py init --candidate "..." --kind conjecture --out ledger.json
    cegis.py check --ledger L --evaluator E --scope S --result passed|inconclusive
    cegis.py counterexample --ledger L --witness '{"n": 7}' --falsified-clause "..."
    cegis.py refine --ledger L --rationale "..." --change "..."
    cegis.py status --ledger L [--json]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

KINDS = {"conjecture","reduction","invariant","definition"}
STATUSES = {"PROPOSED","UNDER_TEST","SURVIVED_CHECKS","REFINED","REFUTED","WITHDRAWN","EXHAUSTED"}
FORBIDDEN = {"PROVED","THEOREM","VERIFIED","VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL"}
STRONGEST = "SURVIVED_CHECKS"

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,d): Path(p).write_text(json.dumps(d,indent=2)+"\n", encoding="utf-8")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--candidate", required=True)
    i.add_argument("--kind", default="conjecture", choices=sorted(KINDS)); i.add_argument("--out", required=True)
    c = sub.add_parser("check"); c.add_argument("--ledger", required=True)
    c.add_argument("--evaluator", required=True); c.add_argument("--scope", required=True)
    c.add_argument("--result", required=True, choices=["passed","inconclusive"])
    x = sub.add_parser("counterexample"); x.add_argument("--ledger", required=True)
    x.add_argument("--witness", required=True); x.add_argument("--falsified-clause", required=True)
    r = sub.add_parser("refine"); r.add_argument("--ledger", required=True)
    r.add_argument("--rationale", required=True); r.add_argument("--change", required=True)
    s = sub.add_parser("status"); s.add_argument("--ledger", required=True); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        save(a.out, {"schema":"maths.cegis.v1","candidate":a.candidate,"kind":a.kind,
            "status":"PROPOSED","checks":[],"counterexamples":[],"history":[],
            "contract":{"proof_promotion_allowed":False,"strongest_positive_status":STRONGEST,
                "why":"unbounded finite verification of a universal statement is not "
                      "evidence of the universal"}})
        print(f"initialized {a.out}  (ceiling: {STRONGEST})"); return 0

    try: led = load(a.ledger)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    if led.get("status") in FORBIDDEN:
        print(f"REFUSED: ledger carries forbidden status {led['status']}", file=sys.stderr); return 1

    n = len(led["history"]) + 1
    if a.cmd == "check":
        led["checks"].append({"sequence":n,"evaluator":a.evaluator,"scope":a.scope,"result":a.result})
        led["history"].append({"sequence":n,"event":"check","result":a.result})
        if a.result == "passed" and len(led["checks"]) >= 3:
            led["status"] = STRONGEST
        elif led["status"] == "PROPOSED":
            led["status"] = "UNDER_TEST"
        save(a.ledger, led)
        print(f"check {n}: {a.result}  status={led['status']}")
        if led["status"] == STRONGEST:
            print(f"  ceiling reached. More passing checks change nothing — only "
                  "refinement, or an independent establishment elsewhere, moves this.")
        return 0
    if a.cmd == "counterexample":
        led["counterexamples"].append({"sequence":n,"witness":json.loads(a.witness),
                                       "falsified_clause":a.falsified_clause})
        led["status"] = "REFUTED"; led["history"].append({"sequence":n,"event":"counterexample"})
        save(a.ledger, led)
        print(f"REFUTED by witness {a.witness}\n  falsified: {a.falsified_clause}")
        return 0
    if a.cmd == "refine":
        led["status"] = "REFINED"
        led["history"].append({"sequence":n,"event":"refine","rationale":a.rationale,"change":a.change})
        save(a.ledger, led); print(f"refined: {a.change}"); return 0

    out = {"candidate":led["candidate"],"status":led["status"],
           "checks_passed":sum(1 for c in led["checks"] if c["result"]=="passed"),
           "counterexamples":len(led["counterexamples"]),
           "ceiling":STRONGEST,"proof_promotion_allowed":False}
    print(json.dumps(out, indent=2) if a.json else
          f"CEGIS {out['status']}  ({out['checks_passed']} passing checks)\n"
          f"  ceiling {STRONGEST} — passing checks never become a proof")
    return 0
if __name__ == "__main__":
    sys.exit(main())
