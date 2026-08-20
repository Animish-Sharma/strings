#!/usr/bin/env python3
"""Blueprint ledger — resumable obligations across sessions.

A proof DAG becomes a persistent worklist. The state that matters:

    PENDING      dependencies not yet closed
    READY        every dependency VERIFIED; dispatchable now
    VERIFIED     closed with evidence
    FAILED       attempted and did not close
    THEORY_GAP   blocked on a prerequisite that does not exist yet

THEORY_GAP is the interesting one. An unknown-identifier failure usually does not
mean the step is wrong — it means the thing it needs has never been defined. So
that failure auto-creates a prerequisite obligation (define it, then its basic
API) rather than being retried as if the checker were being difficult. Closing
the last gap returns the node to PENDING.

Usage:
    blueprint.py init --dag <dag.json> --out bp.json
    blueprint.py next --bp B [--limit N]
    blueprint.py record --bp B --node ID --status VERIFIED|FAILED [--evidence E] [--diagnostic D]
    blueprint.py status --bp B [--json]
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

# Real Lean 4 output, observed rather than assumed:
#     foo.lean:1:54: error(lean.unknownIdentifier): Unknown constant `Nat.no_such_lemma`
# It quotes with BACKTICKS, not the single quotes an earlier version of this
# regex expected — so it extracted nothing, theory-gap creation silently did not
# happen, and the node would be retried forever instead of getting its
# prerequisite. Accept all three quotings.
RE_UNKNOWN = re.compile(
    r"unknown (?:identifier|constant)\s*[:]?\s*"
    r"(?:`([^`]+)`|'([^']+)'|\"([^\"]+)\"|([\w.']+))",
    re.IGNORECASE)

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,d): Path(p).write_text(json.dumps(d,indent=2)+"\n", encoding="utf-8")

def recompute(bp: dict) -> None:
    by_id = {o["id"]: o for o in bp["obligations"]}
    for o in bp["obligations"]:
        if o["status"] in {"VERIFIED","FAILED"}: continue
        if o.get("theory_gaps"):
            o["status"] = "THEORY_GAP"; continue
        deps = o.get("depends_on", [])
        o["status"] = ("READY" if all(by_id.get(d,{}).get("status")=="VERIFIED" for d in deps)
                       else "PENDING")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--dag", required=True); i.add_argument("--out", required=True)
    n = sub.add_parser("next"); n.add_argument("--bp", required=True); n.add_argument("--limit", type=int, default=3)
    r = sub.add_parser("record"); r.add_argument("--bp", required=True); r.add_argument("--node", required=True)
    r.add_argument("--status", required=True, choices=["VERIFIED","FAILED"])
    r.add_argument("--evidence", default=""); r.add_argument("--diagnostic", default="")
    s = sub.add_parser("status"); s.add_argument("--bp", required=True); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        try: dag = load(a.dag)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr); return 2
        obligations = []
        for node in dag.get("nodes", []):
            nid = node.get("node_id") or node.get("id")
            already = str(node.get("status","")).upper() in {
                "VERIFIED","VERIFIED_LEAN","VERIFIED_WIT","VERIFIED_EXTERNAL"}
            obligations.append({"id":nid,"statement":node.get("statement",""),
                "depends_on":node.get("depends_on",[]),
                "status":"VERIFIED" if already else "PENDING",
                "attempts":0,"evidence":[],"theory_gaps":[]})
        bp = {"schema":"maths.blueprint.v1","obligations":obligations}
        recompute(bp); save(a.out, bp)
        print(f"initialized {a.out}: {len(obligations)} obligation(s)"); return 0

    try: bp = load(a.bp)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "next":
        recompute(bp); save(a.bp, bp)
        ready = [o for o in bp["obligations"] if o["status"]=="READY"][:a.limit]
        if not ready:
            gaps = [o for o in bp["obligations"] if o["status"]=="THEORY_GAP"]
            if gaps:
                print("nothing READY; blocked on prerequisite theory:")
                for g in gaps:
                    for t in g["theory_gaps"]: print(f"    define {t} (needed by {g['id']})")
            else:
                print("nothing READY — either all closed, or every open node is waiting "
                      "on a dependency")
            return 0
        for o in ready: print(f"  READY  {o['id']}: {o['statement'][:70]}")
        return 0

    if a.cmd == "record":
        for o in bp["obligations"]:
            if o["id"] == a.node:
                o["attempts"] += 1
                if a.status == "VERIFIED":
                    if not a.evidence:
                        print("REFUSED: VERIFIED needs evidence", file=sys.stderr); return 1
                    o["status"], _ = "VERIFIED", o["evidence"].append(a.evidence)
                else:
                    o["status"] = "FAILED"
                    unknown = [next(g for g in m if g) for m in RE_UNKNOWN.findall(a.diagnostic or "")]
                    if unknown:
                        o["theory_gaps"] = sorted(set(unknown))
                        o["status"] = "THEORY_GAP"
                        for name in o["theory_gaps"]:
                            bp["obligations"].append({
                                "id": f"theory::{name}", "statement": f"define {name} and its basic API",
                                "depends_on": [], "status":"PENDING", "attempts":0,
                                "evidence": [], "theory_gaps": [],
                                "origin": f"auto-created from an unknown-identifier failure in {a.node}"})
                        print(f"{a.node} -> THEORY_GAP on {o['theory_gaps']}")
                        print("  The step is not necessarily wrong: what it needs has never "
                              "been defined. Prerequisite obligation(s) created.")
                        recompute(bp); save(a.bp, bp); return 0
                recompute(bp); save(a.bp, bp)
                print(f"{a.node} -> {o['status']}"); return 0
        print(f"no obligation {a.node!r}", file=sys.stderr); return 1

    recompute(bp); save(a.bp, bp)
    counts = {}
    for o in bp["obligations"]: counts[o["status"]] = counts.get(o["status"],0)+1
    out = {"total":len(bp["obligations"]),"by_status":counts}
    print(json.dumps(out, indent=2) if a.json else
          f"BLUEPRINT {out['total']} obligation(s)  {counts}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
