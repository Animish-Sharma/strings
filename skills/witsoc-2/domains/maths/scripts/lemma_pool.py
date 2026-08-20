#!/usr/bin/env python3
"""Lemma pool — the per-campaign object that makes attempts compound.

The valuable operation is `mine`: probe a hard goal with a few structural
openers, read the checker's REAL residual goals out of the diagnostics, and
propose each one as a bridging lemma. The probe is EXPECTED to fail — the
diagnostics are the product, not a side effect.

That is the difference between a run that repeats and a run that accumulates.
Without it, each attempt at a hard goal starts from the same place; with it,
every failure deposits a smaller, named, separately attackable obligation.

Three attempts on a pooled lemma and it is INTRACTABLE, recorded with evidence.
A pool that never gives up fills with items nobody will ever close.

Usage:
    lemma_pool.py init --out pool.json
    lemma_pool.py propose --pool P --statement "..." [--origin mined|manual]
    lemma_pool.py mine --pool P --diagnostic <file.txt> [--goal "..."]
    lemma_pool.py record --pool P --id N --status PROVED|FAILED [--evidence "..."]
    lemma_pool.py status --pool P [--json]
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

ABANDON_AFTER = 3
OPENERS = ("intro", "intros", "constructor", "intro n", "intro x h", "refine <_, _>")
STATUSES = {"PROPOSED","PROVED","FAILED","INTRACTABLE"}
# Real residual goals as the checker prints them.
# Real Lean prints the goal block after "unsolved goals" with `case <name>`
# headers at column 0, so an earlier `(?=\n\S)` lookahead terminated the capture
# at the first case header and harvested nothing. Run to the next error or EOF
# instead. This matters: the whole-text fallback below would otherwise scoop up
# goals from UNRELATED errors and attribute them to this obligation.
RE_RESIDUAL = re.compile(
    r"unsolved goals?\s*\n(.*?)(?=^\S*?\.lean:\d+:\d+:|\Z)",
    re.DOTALL | re.IGNORECASE | re.MULTILINE)
RE_TURNSTILE = re.compile(r"^\s*[|]?\s*(?:⊢|\|-)\s*(.+)$", re.MULTILINE)

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,d): Path(p).write_text(json.dumps(d,indent=2)+"\n", encoding="utf-8")
def sha(s): return hashlib.sha256(s.strip().encode()).hexdigest()[:16]

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--out", required=True)
    p = sub.add_parser("propose"); p.add_argument("--pool", required=True)
    p.add_argument("--statement", required=True); p.add_argument("--origin", default="manual")
    m = sub.add_parser("mine"); m.add_argument("--pool", required=True)
    m.add_argument("--diagnostic", required=True); m.add_argument("--goal", default="")
    r = sub.add_parser("record"); r.add_argument("--pool", required=True)
    r.add_argument("--id", required=True); r.add_argument("--status", required=True, choices=["PROVED","FAILED"])
    r.add_argument("--evidence", default="")
    s = sub.add_parser("status"); s.add_argument("--pool", required=True); s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        save(a.out, {"schema":"maths.lemma_pool.v1","openers":list(OPENERS),
                     "abandon_after":ABANDON_AFTER,"lemmas":[]})
        print(f"initialized {a.out}"); return 0
    try: pool = load(a.pool)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    def add(statement: str, origin: str) -> str | None:
        key = sha(statement)
        if any(l["id"] == key for l in pool["lemmas"]): return None
        pool["lemmas"].append({"id":key,"statement":statement,"origin":origin,
                               "status":"PROPOSED","attempts":0,"evidence":[]})
        return key

    if a.cmd == "propose":
        key = add(a.statement, a.origin); save(a.pool, pool)
        print(f"proposed {key}" if key else "already in the pool (deduped by statement)")
        return 0

    if a.cmd == "mine":
        try: text = Path(a.diagnostic).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr); return 2
        goals = []
        for block in RE_RESIDUAL.findall(text):
            goals += [g.strip() for g in RE_TURNSTILE.findall(block) if g.strip()]
        if not goals:
            goals = [g.strip() for g in RE_TURNSTILE.findall(text) if g.strip()]
        added = [k for k in (add(g, "mined") for g in goals) if k]
        save(a.pool, pool)
        print(f"MINE: {len(goals)} residual goal(s) in the diagnostics, "
              f"{len(added)} new bridging lemma(s)")
        for g in goals[:8]: print(f"    {g[:96]}")
        if not goals:
            print("  no residual goals found. The probe either closed or failed before "
                  "producing goal state — a syntax error yields nothing to mine.")
        return 0

    if a.cmd == "record":
        for l in pool["lemmas"]:
            if l["id"].startswith(a.id):
                l["attempts"] += 1
                if a.evidence: l["evidence"].append(a.evidence)
                if a.status == "PROVED":
                    if not a.evidence:
                        print("REFUSED: PROVED needs evidence — a pool entry marked proved "
                              "with nothing behind it is worse than an open one",
                              file=sys.stderr); return 1
                    l["status"] = "PROVED"
                elif l["attempts"] >= ABANDON_AFTER:
                    l["status"] = "INTRACTABLE"
                else:
                    l["status"] = "FAILED"
                save(a.pool, pool)
                print(f"{l['id']} -> {l['status']} (attempt {l['attempts']})")
                if l["status"] == "INTRACTABLE":
                    print(f"  {ABANDON_AFTER} attempts spent. Recorded with evidence rather "
                          "than retried; a pool that never abandons fills with items "
                          "nobody will close.")
                if l["status"] == "PROVED":
                    print("  harvest this into the library so later attempts can use it.")
                return 0
        print(f"no lemma matching {a.id!r}", file=sys.stderr); return 1

    counts = {}
    for l in pool["lemmas"]: counts[l["status"]] = counts.get(l["status"],0)+1
    out = {"total":len(pool["lemmas"]),"by_status":counts,
           "mined":sum(1 for l in pool["lemmas"] if l["origin"]=="mined")}
    print(json.dumps(out, indent=2) if a.json else
          f"POOL {out['total']} lemma(s)  {counts}\n  {out['mined']} mined from real diagnostics")
    return 0
if __name__ == "__main__":
    sys.exit(main())
