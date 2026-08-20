#!/usr/bin/env python3
"""Problem theory — the living model of WHY this problem is hard.

The single most valuable artifact in a long campaign, and the one a generic
frame cannot supply. It answers questions no claim graph holds:

  enemy_profile      what must a counterexample LOOK like? Each constraint
                     traced to the fragment that forces it.
  method_failures    the MECHANISM, never the label. "density increment loses a
                     log factor at step 3" is theory; "genuine_barrier" is a
                     shrug with a name.
  example_zoo        positive and negative instances, with how to regenerate them
  main_attack        the committed strategy and its exact stall point

Every revision requires --why. A loop that ends with no theory diff learned
nothing, however busy it looked.

Usage:
    problem_theory.py init --target "..." --out theory.json
    problem_theory.py add-constraint --theory T --constraint "..." --because "..." --why "..."
    problem_theory.py add-failure --theory T --method M --mechanism "..." --why "..."
    problem_theory.py stall --theory T --attack "..." --at "..." --why "..."
    problem_theory.py insight --theory T [--json]
    problem_theory.py context --theory T [--max-words 250]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

WEIGHTS = {"enemy_constraints":2.0,"refuted_candidates":2.0,"pool_lemmas_proved":2.0,
           "failure_mechanisms_named":1.5,"theory_revisions":1.0,"pool_dead_ends":1.0,
           "examples_in_zoo":0.5,"techniques_tried":0.5}

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def save(p, d): Path(p).write_text(json.dumps(d, indent=2)+"\n", encoding="utf-8")
def log(t, why): t.setdefault("theory_log", []).append({"revision": len(t.get("theory_log",[]))+1, "why": why})

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.add_argument("--target", required=True); i.add_argument("--out", required=True)
    c = sub.add_parser("add-constraint"); c.add_argument("--theory", required=True)
    c.add_argument("--constraint", required=True); c.add_argument("--because", required=True); c.add_argument("--why", required=True)
    f = sub.add_parser("add-failure"); f.add_argument("--theory", required=True)
    f.add_argument("--method", required=True); f.add_argument("--mechanism", required=True); f.add_argument("--why", required=True)
    s = sub.add_parser("stall"); s.add_argument("--theory", required=True)
    s.add_argument("--attack", required=True); s.add_argument("--at", required=True); s.add_argument("--why", required=True)
    n = sub.add_parser("insight"); n.add_argument("--theory", required=True); n.add_argument("--json", action="store_true")
    x = sub.add_parser("context"); x.add_argument("--theory", required=True); x.add_argument("--max-words", type=int, default=250)
    a = ap.parse_args()

    if a.cmd == "init":
        save(a.out, {"schema":"maths.problem_theory.v1","target":a.target,"formulations":[],
                     "example_zoo":{"positive":[],"negative":[]},
                     "enemy_profile":{"constraints":[],"refuted_candidates":[],"verdict":"unknown"},
                     "method_failures":[],"main_attack":None,"techniques_tried":[],"theory_log":[]})
        print(f"initialized {a.out}\n  Start with the enemy profile: what must a "
              "counterexample look like?")
        return 0

    try: t = load(a.theory)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.cmd == "add-constraint":
        t["enemy_profile"]["constraints"].append({"constraint": a.constraint, "forced_by": a.because})
        log(t, a.why); save(a.theory, t)
        print(f"enemy constraint {len(t['enemy_profile']['constraints'])}: {a.constraint}")
    elif a.cmd == "add-failure":
        if len(a.mechanism.split()) < 4:
            print("REFUSED: record the MECHANISM, not a label. 'genuine_barrier' is a "
                  "shrug; 'density increment loses a log factor at step 3' is theory.",
                  file=sys.stderr); return 1
        t["method_failures"].append({"method": a.method, "mechanism": a.mechanism})
        t.setdefault("techniques_tried", []).append(a.method)
        log(t, a.why); save(a.theory, t); print(f"failure mechanism recorded for {a.method}")
    elif a.cmd == "stall":
        t["main_attack"] = {"strategy": a.attack, "stall_point": a.at}
        log(t, a.why); save(a.theory, t); print(f"main attack stalls at: {a.at}")
    elif a.cmd == "insight":
        counts = {"enemy_constraints": len(t["enemy_profile"]["constraints"]),
                  "refuted_candidates": len(t["enemy_profile"]["refuted_candidates"]),
                  "pool_lemmas_proved": t.get("pool_lemmas_proved", 0),
                  "failure_mechanisms_named": len(t["method_failures"]),
                  "theory_revisions": len(t.get("theory_log", [])),
                  "pool_dead_ends": t.get("pool_dead_ends", 0),
                  "examples_in_zoo": len(t["example_zoo"]["positive"]) + len(t["example_zoo"]["negative"]),
                  "techniques_tried": len(set(t.get("techniques_tried", [])))}
        score = sum(counts[k]*w for k, w in WEIGHTS.items())
        out = {"insight_score": round(score,2), "components": counts,
               "note": "understanding, not trust. Never a status."}
        print(json.dumps(out, indent=2) if a.json else
              f"INSIGHT {out['insight_score']}\n" + "\n".join(
                  f"  {k:<26} {v}" for k, v in counts.items()))
    else:
        parts = [f"TARGET: {t['target']}"]
        if t.get("main_attack"):
            parts.append(f"ATTACK: {t['main_attack']['strategy']} — stalls at "
                         f"{t['main_attack']['stall_point']}")
        for c in t["enemy_profile"]["constraints"][:6]:
            parts.append(f"ENEMY MUST: {c['constraint']} (forced by {c['forced_by']})")
        for m in t["method_failures"][:6]:
            parts.append(f"FAILED {m['method']}: {m['mechanism']}")
        text = " | ".join(parts)
        print(" ".join(text.split()[:a.max_words]))
    return 0

if __name__ == "__main__":
    sys.exit(main())
