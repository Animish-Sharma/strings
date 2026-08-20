#!/usr/bin/env python3
"""Cross-run memory — the only thing in the frame that compounds.

Implements references/memory.md. Two tiers, kept apart on purpose:

    attention   failures, do-not-repeat entries, method priors. Ranks work.
                Never evidence, never in a receipt, never moves a status.
    reuse       admitted results from earlier runs, reusable ONLY on exact
                context match. Still produces a candidate, not an admission.

The contamination guard is the reason this is a tool and not a dict. A store
that learns from outcomes preferentially retains what scored well, and if the
scoring ever saw the answer, the store has laundered it into a prior that looks
like accumulated skill. So held-out material is refused at the door, and entries
with unknown provenance cannot enter the reuse tier.

Usage:
    memory.py init --out mem.json
    memory.py record-failure --mem M --statement "..." --method F --why "..." \
        --revival "..." [--blocker B]
    memory.py record-result --mem M --statement "..." --admission-id A --context '{...}'
    memory.py check --mem M --statement "..." --method F        (repeat?)
    memory.py reuse --mem M --statement "..." --context '{...}' (exact match only)
    memory.py revive --mem M --event "..."                      (re-price blocked routes)
Exit: 0 ok, 1 blocked/refused, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

HELD_OUT_MARKERS = ("held_out","heldout","answer_key","evaluation_key","benchmark_target",
                    "ground_truth","solution_key","test_answer")
PROMOTE_AT = 3   # failures sharing a blocker before it becomes a named obstruction

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p,d): Path(p).write_text(json.dumps(d,indent=2)+"\n", encoding="utf-8")
def sha(s): return hashlib.sha256(" ".join(str(s).split()).encode()).hexdigest()[:16]

def contaminated(blob: str) -> str | None:
    low = blob.lower()
    return next((m for m in HELD_OUT_MARKERS if m in low), None)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--out", required=True)
    f = sub.add_parser("record-failure"); f.add_argument("--mem", required=True)
    f.add_argument("--statement", required=True); f.add_argument("--method", required=True)
    f.add_argument("--why", required=True); f.add_argument("--revival", required=True)
    f.add_argument("--blocker", default="")
    r = sub.add_parser("record-result"); r.add_argument("--mem", required=True)
    r.add_argument("--statement", required=True); r.add_argument("--admission-id", required=True)
    r.add_argument("--context", required=True)
    c = sub.add_parser("check"); c.add_argument("--mem", required=True)
    c.add_argument("--statement", required=True); c.add_argument("--method", required=True)
    u = sub.add_parser("reuse"); u.add_argument("--mem", required=True)
    u.add_argument("--statement", required=True); u.add_argument("--context", required=True)
    v = sub.add_parser("revive"); v.add_argument("--mem", required=True); v.add_argument("--event", required=True)
    a = ap.parse_args()

    if a.cmd == "init":
        save(a.out, {"schema":"frame.memory.v1","attention":[],"reuse":[],"obstructions":[]})
        print(f"initialized {a.out}  (attention and reuse tiers kept separate)"); return 0
    try: mem = load(a.mem)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "record-failure":
        marker = contaminated(a.statement + a.why)
        if marker:
            print(f"REFUSED: content mentions {marker!r}. Held-out material never enters "
                  "memory — a store that can absorb the answer will hand it back as a "
                  "prior, and nothing downstream can tell that apart from insight.",
                  file=sys.stderr)
            return 1
        entry = {"tier":"attention","statement_sha":sha(a.statement),
                 "statement":a.statement,"method_family":a.method,"why_failed":a.why,
                 "blocker":a.blocker,"revival_condition":a.revival,"revived":False}
        mem["attention"].append(entry)
        if a.blocker:
            same = [e for e in mem["attention"] if e.get("blocker") == a.blocker]
            if len(same) >= PROMOTE_AT and a.blocker not in mem["obstructions"]:
                mem["obstructions"].append(a.blocker)
                save(a.mem, mem)
                print(f"recorded. {len(same)} failures now share blocker {a.blocker!r} — "
                      "PROMOTED to a named obstruction. That is the run finding something "
                      "real rather than being unlucky.")
                return 0
        save(a.mem, mem); print("recorded (attention tier)"); return 0

    if a.cmd == "record-result":
        try: ctx = json.loads(a.context)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --context is not JSON: {exc}", file=sys.stderr); return 2
        marker = contaminated(a.statement + a.context)
        if marker:
            print(f"REFUSED: content mentions {marker!r}; held-out material stays out.",
                  file=sys.stderr); return 1
        if not a.admission_id:
            print("REFUSED: the reuse tier takes admitted results only. Unknown "
                  "provenance fails closed.", file=sys.stderr); return 1
        mem["reuse"].append({"tier":"reuse","statement_sha":sha(a.statement),
            "statement":a.statement,"admission_id":a.admission_id,"context":ctx})
        save(a.mem, mem); print("recorded (reuse tier, admitted)"); return 0

    if a.cmd == "check":
        hits = [e for e in mem["attention"]
                if e["statement_sha"] == sha(a.statement)
                and e["method_family"] == a.method and not e.get("revived")]
        if hits:
            h = hits[0]
            print(f"BLOCKED: this statement/method already failed.\n"
                  f"  why: {h['why_failed']}\n"
                  f"  revival condition: {h['revival_condition']}\n"
                  "  Change an axis, or wait for the revival condition to fire.")
            return 1
        print("no recorded failure for this statement and method"); return 0

    if a.cmd == "reuse":
        try: ctx = json.loads(a.context)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --context is not JSON: {exc}", file=sys.stderr); return 2
        target = sha(a.statement)
        for e in mem["reuse"]:
            if e["statement_sha"] != target: continue
            differing = [k for k in set(e["context"]) | set(ctx)
                         if e["context"].get(k) != ctx.get(k)]
            if differing:
                print(f"NO REUSE: statement matches but context differs on {differing}.\n"
                      "  A near-match skips the work AND the correctness, which is worse "
                      "than starting cold.")
                return 1
            print(f"REUSE: admitted as {e['admission_id']}, context matches on every axis.\n"
                  "  This is evidence about CHECKABILITY, not about truth — the new claim "
                  "still needs its own admission.")
            return 0
        print("no reusable admitted result for this statement"); return 1

    revived = [e for e in mem["attention"]
               if not e.get("revived") and e["revival_condition"].lower() in a.event.lower()
               or (not e.get("revived") and any(w in a.event.lower()
                   for w in e["revival_condition"].lower().split()[:3]))]
    for e in revived: e["revived"] = True
    save(a.mem, mem)
    print(f"event: {a.event}\n  {len(revived)} blocked route(s) re-priced and reopened")
    for e in revived[:5]: print(f"    {e['statement'][:60]}  ({e['method_family']})")
    if not revived:
        print("  no revival conditions matched — the blocked routes stay blocked")
    return 0
if __name__ == "__main__":
    sys.exit(main())
