#!/usr/bin/env python3
"""Result library — tiered, with a one-way promotion gate.

Three trust tiers, and the gap between them is the point:

    1 WIT_STRUCTURE   the shape checks out. Says nothing about truth.
    2 WIT_RECEIPT     an external review accepted every obligation.
    3 LEAN_VERIFIED   the kernel elaborated it AND a soundness scan found no
                      escape hatch.

That last conjunction is load-bearing. A green build over a `sorry` is only a
warning in Lean, so the build alone does not earn tier 3 — the scan is what makes
the tier mean anything.

`promote` copies live entries into the reference set and is the ONLY live ->
reference path. It copies tier 3 only. Lower tiers are structurally excluded
rather than filtered, so a future edit cannot widen it by accident.

Usage:
    library.py init --out lib.json
    library.py add --lib L --statement "..." --tier N --artifact PATH [--target-hash H]
    library.py verify-lean --lib L --id ID --artifact PATH   (scan + tier upgrade)
    library.py search --lib L --query "..." [--min-tier N] [--json]
    library.py promote --lib L --reference R
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

TIERS = {1:"WIT_STRUCTURE", 2:"WIT_RECEIPT", 3:"LEAN_VERIFIED"}
LEAN_BOOST = 0.5
ESCAPES = ("sorry","admit","sorryAx","native_decide")
RE_LOCAL_AXIOM = re.compile(r"^\s*(axiom|constant)\s+", re.MULTILINE)

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,d): Path(p).write_text(json.dumps(d,indent=2)+"\n", encoding="utf-8")
def toks(s): return {t for t in re.split(r"[^A-Za-z0-9_]+", s.lower()) if len(t)>1}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--out", required=True)
    a1 = sub.add_parser("add"); a1.add_argument("--lib", required=True)
    a1.add_argument("--statement", required=True); a1.add_argument("--tier", type=int, required=True, choices=[1,2,3])
    a1.add_argument("--artifact", required=True); a1.add_argument("--target-hash", default="")
    v = sub.add_parser("verify-lean"); v.add_argument("--lib", required=True)
    v.add_argument("--id", required=True); v.add_argument("--artifact", required=True)
    s = sub.add_parser("search"); s.add_argument("--lib", required=True)
    s.add_argument("--query", required=True); s.add_argument("--min-tier", type=int, default=1)
    s.add_argument("--json", action="store_true")
    pr = sub.add_parser("promote"); pr.add_argument("--lib", required=True); pr.add_argument("--reference", required=True)
    a = ap.parse_args()

    if a.cmd == "init":
        save(a.out, {"schema":"maths.library.v1","entries":[]}); print(f"initialized {a.out}"); return 0
    try: lib = load(a.lib)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "add":
        if a.tier == 3:
            print("REFUSED: tier 3 is reached only through `verify-lean`, never asserted. "
                  "Add at tier 1 or 2 and let the scan decide.", file=sys.stderr); return 1
        eid = hashlib.sha256(a.statement.strip().encode()).hexdigest()[:16]
        lib["entries"].append({"id":eid,"statement":a.statement,"tier":a.tier,
            "tier_name":TIERS[a.tier],"artifact":a.artifact,"target_hash":a.target_hash})
        save(a.lib, lib); print(f"added {eid} at tier {a.tier} ({TIERS[a.tier]})"); return 0

    if a.cmd == "verify-lean":
        try: src = Path(a.artifact).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr); return 2
        found = [e for e in ESCAPES if re.search(rf"(?<![\w]){re.escape(e)}(?![\w])", src)]
        if RE_LOCAL_AXIOM.search(src): found.append("local axiom/constant")
        if found:
            print(f"REFUSED tier 3: soundness scan found {found}\n"
                  "  A green build over an escape hatch is only a warning in Lean. The "
                  "scan is what makes LEAN_VERIFIED mean anything.", file=sys.stderr)
            return 1
        for e in lib["entries"]:
            if e["id"].startswith(a.id):
                e["tier"], e["tier_name"] = 3, TIERS[3]
                e["soundness_scan"] = "clean"
                save(a.lib, lib); print(f"{e['id']} -> tier 3 (LEAN_VERIFIED); scan clean"); return 0
        print(f"no entry {a.id!r}", file=sys.stderr); return 1

    if a.cmd == "promote":
        eligible = [e for e in lib["entries"] if e["tier"] == 3]
        ref = load(a.reference) if Path(a.reference).exists() else {"schema":"maths.reference.v1","entries":[]}
        existing = {e["id"] for e in ref["entries"]}
        added = [e for e in eligible if e["id"] not in existing]
        ref["entries"] += added; save(a.reference, ref)
        print(f"promoted {len(added)} entry(ies) to {a.reference}")
        print(f"  {len(lib['entries'])-len(eligible)} entry(ies) excluded: only "
              "LEAN_VERIFIED crosses this boundary, and it is the only path across it.")
        return 0

    q = toks(a.query); ranked = []
    for e in lib["entries"]:
        if e["tier"] < a.min_tier: continue
        d = toks(e["statement"])
        score = len(q & d)/len(q | d) if (q|d) else 0.0
        if e["tier"] == 3: score += LEAN_BOOST * score
        if score > 0: ranked.append({**e, "score": round(score,4)})
    ranked.sort(key=lambda r: -r["score"])
    print(json.dumps({"results":ranked}, indent=2) if a.json else
          "\n".join(f"  {r['score']:.3f}  [{r['tier_name']}] {r['statement'][:70]}"
                    for r in ranked) or "  no match")
    return 0
if __name__ == "__main__":
    sys.exit(main())
