#!/usr/bin/env python3
"""Predicate registry — a mined statement must be dispatchable by construction.

If a miner may propose "P(n) implies Q(n)", then P and Q need formal templates
BEFORE mining, or the proposal formalizes to a stub and the stub gets counted as
a formalization. Registration is where faithfulness responsibility lives.

An unregistered predicate is an honest BLOCKER, never a guess.

Usage:
    predicates.py list
    predicates.py implication --p P --q Q [--var n] [--json]
    predicates.py register --name N --template "..." [--registry R]
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

FORBIDDEN = ("sorry","admit","axiom ","unsafe ","opaque ")
BUILTIN = {
 "prime":        "Nat.Prime {v}",
 "even":         "Even {v}",
 "odd":          "Odd {v}",
 "square":       "∃ k, {v} = k * k",
 "squarefree":   "Squarefree {v}",
 "positive":     "0 < {v}",
 "composite":    "¬ Nat.Prime {v} ∧ 1 < {v}",
 "divisible_by_three": "3 ∣ {v}",
 "power_of_two": "∃ k, {v} = 2 ^ k",
}

def load_registry(path: str | None) -> dict:
    reg = dict(BUILTIN)
    path = path or os.environ.get("WITSOC2_PREDICATES")
    if path and Path(path).exists():
        try: user = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return reg
        for name, template in user.items():
            if name in BUILTIN:      # built-ins are frozen
                continue
            if any(f in template.lower() for f in FORBIDDEN):
                continue
            reg[name] = template
    return reg

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("--registry", nargs="?")
    i = sub.add_parser("implication"); i.add_argument("--p", required=True)
    i.add_argument("--q", required=True); i.add_argument("--var", default="n")
    i.add_argument("--registry"); i.add_argument("--json", action="store_true")
    r = sub.add_parser("register"); r.add_argument("--name", required=True)
    r.add_argument("--template", required=True); r.add_argument("--registry", required=True)
    a = ap.parse_args()
    reg = load_registry(getattr(a, "registry", None))

    if a.cmd == "list":
        for name, tpl in sorted(reg.items()):
            print(f"  {name:<22} {tpl}")
        return 0
    if a.cmd == "register":
        if any(f in a.template.lower() for f in FORBIDDEN):
            print("REFUSED: template contains an escape hatch", file=sys.stderr); return 1
        if a.name in BUILTIN:
            print(f"REFUSED: {a.name!r} is a built-in and may not be shadowed",
                  file=sys.stderr); return 1
        path = Path(a.registry)
        user = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        user[a.name] = a.template
        path.write_text(json.dumps(user, indent=2)+"\n", encoding="utf-8")
        print(f"registered {a.name}"); return 0

    missing = [n for n in (a.p, a.q) if n not in reg]
    if missing:
        out = {"blocker": True, "missing_predicates": missing,
               "why": "an unregistered predicate would formalize to a stub, and a stub "
                      "that type-checks is worse than no statement at all",
               "fix": f"predicates.py register --name {missing[0]} --template '...'"}
        print(json.dumps(out, indent=2) if a.json else
              f"BLOCKER: unregistered predicate(s) {missing}\n  {out['why']}\n  {out['fix']}")
        return 1
    lean = f"∀ {a.var} : ℕ, ({reg[a.p].format(v=a.var)}) → ({reg[a.q].format(v=a.var)})"
    out = {"blocker": False, "lean_statement": lean}
    print(json.dumps(out, indent=2) if a.json else f"  {lean}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
