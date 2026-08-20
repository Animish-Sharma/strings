#!/usr/bin/env python3
"""Reduction ledger — obligations, the open core, and honest progress.

The contract a reduction claims:

    target  <==  (every obligation discharged)  AND  (open_core empty)

The **open core** is the residual the obligations do not cover, named
explicitly. It is the whole point. Without it, a run that discharges eight of
ten seeded obligations reports 80% progress on a conjecture it has not touched —
because the ten obligations were themselves chosen to be tractable.

So progress is capped by the state of the reduction, not by the count of closed
obligations. Closing easy obligations is not closing the conjecture.

Usage:
    reduction_ledger.py init --target "..." --out ledger.json
    reduction_ledger.py add --ledger L --statement "..." --applies-because "..." --covers "..."
    reduction_ledger.py open-core --ledger L --add "..."
    reduction_ledger.py discharge --ledger L --id N --status CHECKED
    reduction_ledger.py audit --ledger L [--hole "..."]
    reduction_ledger.py assess --ledger L [--json]
Exit: 0 ok, 1 problem, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

OBLIGATION_STATUSES = {"OPEN","FORMALIZED","DISCHARGED","REFUTED"}
DISCHARGED = {"CHECKED","VERIFIED","VERIFIED_LEAN","VERIFIED_WIT","DISCHARGED",
              "PROOF_DISCHARGED","RECEIPT_ACCEPTED"}
JUSTIFICATION = {"UNJUSTIFIED","ASSERTED","KERNEL_CHECKED"}
# An `applies_because` that says nothing is how a generic template injects
# irrelevant obligations into every problem that shares a keyword.
PLACEHOLDER = {"pending","relevant","tbd","n/a","na","applies","see above","obvious",
               "clear","standard","todo",""}

def applicability_ok(text: str, statement: str) -> tuple[bool, str]:
    t = (text or "").strip().lower()
    if t in PLACEHOLDER:
        return False, f"applies_because is a placeholder ({text!r})"
    if len(t) < 12:
        return False, "applies_because is under 12 characters — say why it applies"
    if t == (statement or "").strip().lower():
        return False, "applies_because merely echoes the statement"
    return True, ""

def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

def assess(ledger: dict) -> dict:
    obligations = ledger.get("obligations", [])
    core = ledger.get("open_core", [])
    holes = ledger.get("coverage_holes", [])
    justification = ledger.get("justification_status", "UNJUSTIFIED")

    total = len(obligations)
    done = sum(1 for o in obligations if o.get("status") in DISCHARGED
               or o.get("status") == "DISCHARGED")
    refuted = [o for o in obligations if o.get("status") == "REFUTED"]
    coverage = (done / total) if total else 0.0

    if refuted:
        band, cap = "REFUTED_OBLIGATION", 5
        why = ("an obligation was refuted, so the reduction as stated is false; "
               "the decomposition must change before any progress is claimed")
    elif holes:
        band, cap = "COVERAGE_HOLE", 5
        why = ("an instance satisfies the target's hypotheses but is covered by no "
               "obligation and no open-core item: the decomposition is UNSOUND, "
               "not merely incomplete")
    elif core:
        band, cap = "OPEN_CORE_OPEN", int(8 + 12 * coverage)
        why = (f"the open core is still open ({len(core)} item(s)). Discharging "
               f"obligations while the core stands is not progress on the target.")
    elif total and done < total:
        band, cap = "CORE_CLOSED_OBLIGATIONS_OPEN", int(40 + 40 * coverage)
        why = "the core is closed; the remaining obligations are the real work"
    elif justification == "UNJUSTIFIED":
        band, cap = "UNJUSTIFIED_REDUCTION", 45
        why = "nothing has checked that the obligations actually imply the target"
    elif justification == "ASSERTED":
        band, cap = "REDUCED_ASSERTED", 85
        why = "the reduction is asserted but not kernel-checked"
    else:
        band, cap = "REDUCED", 100
        why = "complete, kernel-checked, no coverage hole"

    return {"band": band, "progress_cap": cap, "why": why,
            "obligations_total": total, "obligations_discharged": done,
            "coverage": round(coverage, 3), "open_core_items": len(core),
            "coverage_holes": len(holes), "justification_status": justification,
            "solve_ready": band == "REDUCED"}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--target", required=True); i.add_argument("--out", required=True)
    a = sub.add_parser("add"); a.add_argument("--ledger", required=True)
    a.add_argument("--statement", required=True); a.add_argument("--applies-because", required=True)
    a.add_argument("--covers", required=True); a.add_argument("--kind", default="lemma")
    c = sub.add_parser("open-core"); c.add_argument("--ledger", required=True); c.add_argument("--add", required=True)
    d = sub.add_parser("discharge"); d.add_argument("--ledger", required=True)
    d.add_argument("--id", type=int, required=True); d.add_argument("--status", required=True)
    u = sub.add_parser("audit"); u.add_argument("--ledger", required=True); u.add_argument("--hole")
    s = sub.add_parser("assess"); s.add_argument("--ledger", required=True); s.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "init":
        save(args.out, {"schema":"maths.reduction_ledger.v1","target":args.target,
                        "obligations":[],"open_core":[],"coverage_holes":[],
                        "justification_status":"UNJUSTIFIED","coverage_audited":False})
        print(f"initialized {args.out}\n  Declare the open core before adding obligations — "
              "the residual is the part that matters.")
        return 0

    try:
        led = load(args.ledger)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if args.cmd == "add":
        ok, why = applicability_ok(args.applies_because, args.statement)
        if not ok:
            print(f"REFUSED: {why}", file=sys.stderr); return 1
        led["obligations"].append({"id": len(led["obligations"]) + 1,
            "statement": args.statement, "applies_because": args.applies_because,
            "covers": args.covers, "kind": args.kind, "status": "OPEN"})
        save(args.ledger, led); print(f"added obligation {len(led['obligations'])}"); return 0

    if args.cmd == "open-core":
        led["open_core"].append(args.add); led["coverage_audited"] = False
        save(args.ledger, led)
        print(f"open core now has {len(led['open_core'])} item(s)"); return 0

    if args.cmd == "discharge":
        for o in led["obligations"]:
            if o["id"] == args.id:
                o["status"] = args.status.upper(); save(args.ledger, led)
                print(f"obligation {args.id} -> {o['status']}")
                if led["open_core"]:
                    print("  note: the open core is still open; this does not move the target.")
                return 0
        print(f"no obligation {args.id}", file=sys.stderr); return 1

    if args.cmd == "audit":
        if args.hole:
            led["coverage_holes"].append(args.hole)
            print(f"COVERAGE HOLE recorded: {args.hole}\n"
                  "  The decomposition is unsound: an instance escapes both the "
                  "obligations and the open core.")
        led["coverage_audited"] = True; save(args.ledger, led); return 0

    result = assess(led)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"REDUCTION: {result['band']}  (progress cap {result['progress_cap']}/100)")
        print(f"  {result['why']}")
        print(f"  obligations {result['obligations_discharged']}/{result['obligations_total']}"
              f"   open core {result['open_core_items']}   holes {result['coverage_holes']}")
        print(f"  solve ready: {result['solve_ready']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
