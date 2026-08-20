#!/usr/bin/env python3
"""Speculative arena — conditional results, ranked by leverage.

A verified `H -> T` is cheap compared to establishing T, and it is a real
product. So: build the consequence structure first, rank the candidate bridges by
how much each would unlock if it held, then spend on establishing the single
highest-leverage one.

This turns one expensive all-or-nothing attempt into a cheap map plus one
targeted spend.

The discipline that keeps it honest: a verified conditional is a CONDITIONAL
fact, not a solve. `T` moves only when `H` itself is established, and then by
composing two verified results — never by the conditional quietly losing its
antecedent.

Usage:
    speculative.py rank --bridges <b.json> [--json]
    speculative.py compose --bridge-id H --conditional-receipt R --antecedent-receipt A
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def leverage(bridge: dict, all_bridges: list[dict]) -> tuple[float, list[str]]:
    reasons = []
    sufficient = 1.0 if bridge.get("sufficient_for_target") else 0.0
    if sufficient: reasons.append("sufficient for the target on its own")
    implied = [b for b in all_bridges
               if bridge.get("id") in (b.get("implied_by") or [])]
    breadth = min(1.0, len(implied)/3)
    if implied: reasons.append(f"implies {len(implied)} other bridge(s)")
    cost = {"cheap":1.0,"moderate":0.6,"expensive":0.3}.get(bridge.get("cost_hint","moderate"),0.6)
    score = 0.5*sufficient + 0.3*breadth + 0.2*cost
    return round(score,4), reasons or ["no leverage recorded"]

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rank"); r.add_argument("--bridges", required=True); r.add_argument("--json", action="store_true")
    c = sub.add_parser("compose"); c.add_argument("--bridge-id", required=True)
    c.add_argument("--conditional-receipt", required=True); c.add_argument("--antecedent-receipt", required=True)
    a = ap.parse_args()

    if a.cmd == "compose":
        for label, path in (("H -> T", a.conditional_receipt), ("H", a.antecedent_receipt)):
            if not Path(path).exists():
                print(f"REFUSED: no receipt for {label} at {path}. Composition needs BOTH "
                      "verified; a conditional without its antecedent is still conditional.",
                      file=sys.stderr); return 1
        print(f"COMPOSED: {a.bridge_id} established and {a.bridge_id} -> T established.\n"
              "  The target may now move — by composition of two receipts, not by the\n"
              "  conditional dropping its antecedent. Re-verify the composition.")
        return 0

    try: payload = json.loads(Path(a.bridges).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    bridges = payload if isinstance(payload, list) else payload.get("bridges", [])
    ranked = []
    for b in bridges:
        score, reasons = leverage(b, bridges)
        ranked.append({"id":b.get("id"),"statement":b.get("statement",""),"score":score,
                       "reasons":reasons,"status":"OPEN_UNFALSIFIED",
                       "conditional_status":"CONDITIONAL on this bridge"})
    ranked.sort(key=lambda x: -x["score"])
    out = {"ranked":ranked,
           "rule":"establish the highest-leverage bridge first; every conditional "
                  "result stays CONDITIONAL until its antecedent is established"}
    if a.json: print(json.dumps(out, indent=2))
    else:
        for x in ranked:
            print(f"  {x['score']:.3f}  {x['id']}: {x['statement'][:60]}")
            for r in x["reasons"]: print(f"           {r}")
        print(f"\n  {out['rule']}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
