#!/usr/bin/env python3
"""Maths status lattice — which transitions are legal.

The frame owns the generic vocabulary. This is the maths refinement, and it
exists because two structural facts are easy to get wrong:

  1. CHECKED_BOUNDED has NO edge to any VERIFIED_*. Bounded evidence never
     becomes universal evidence by accumulating. The only routes onward are
     CHECKED_SYMBOLIC or PROVED_SKETCH, both of which require a different kind
     of argument, not more instances.
  2. Coarse and granular labels are BOTH first class. A gate written against
     {VERIFIED, CHECKED} once let VERIFIED_LEAN through with no evidence,
     because the granular label was not in the set it checked.

Usage:
    status.py check --from S --to T [--evidence ...] [--json]
    status.py demote --from S --to T --barrier "..." [--json]
    status.py table
Exit: 0 legal, 1 illegal, 2 usage error.
"""
from __future__ import annotations
import argparse, json, sys

STRUCTURAL = {"DRAFT","OPEN","UNVERIFIED","CONJECTURE","FAILED_ATTEMPT","REJECTED",
              "DEMOTED","GAP","PLANNED","SELECTED","READY"}
VERIFIED = {"VERIFIED","VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL"}
CHECKED  = {"CHECKED","CHECKED_BOUNDED","CHECKED_SYMBOLIC"}
SKETCH   = {"PROVED_SKETCH"}
PRODUCT  = {"PARTIAL","CONDITIONAL"}
# Any status asserting a result needs evidence. Both coarse and granular.
NEEDS_EVIDENCE = VERIFIED | CHECKED | SKETCH | PRODUCT

TRANSITIONS = {
    "DRAFT":            {"OPEN","CONJECTURE","FAILED_ATTEMPT","REJECTED"},
    "OPEN":             {"CONJECTURE","CHECKED","CHECKED_BOUNDED","FAILED_ATTEMPT","REJECTED","GAP"},
    "UNVERIFIED":       {"OPEN","CONJECTURE","CHECKED","CHECKED_BOUNDED","GAP","REJECTED"},
    "CONJECTURE":       {"CHECKED","CHECKED_BOUNDED","CHECKED_SYMBOLIC","PROVED_SKETCH",
                         "FAILED_ATTEMPT","REJECTED","DEMOTED","GAP"},
    "CHECKED":          {"CHECKED_BOUNDED","CHECKED_SYMBOLIC","PROVED_SKETCH","VERIFIED",
                         "PARTIAL","CONDITIONAL","DEMOTED"},
    # No VERIFIED_* edge. This is the load-bearing omission.
    "CHECKED_BOUNDED":  {"CHECKED_SYMBOLIC","PROVED_SKETCH","PARTIAL","CONDITIONAL",
                         "FAILED_ATTEMPT","DEMOTED"},
    "CHECKED_SYMBOLIC": {"PROVED_SKETCH","VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL",
                         "PARTIAL","CONDITIONAL","DEMOTED"},
    "PROVED_SKETCH":    {"VERIFIED","VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL",
                         "PARTIAL","CONDITIONAL","DEMOTED"},
    "VERIFIED":         {"VERIFIED_WIT","VERIFIED_LEAN","VERIFIED_EXTERNAL","DEMOTED"},
    "VERIFIED_WIT":     {"VERIFIED_LEAN","VERIFIED_EXTERNAL","DEMOTED"},
    "VERIFIED_LEAN":    {"DEMOTED"},
    "VERIFIED_EXTERNAL":{"VERIFIED_LEAN","DEMOTED"},
    "PARTIAL":          {"VERIFIED_WIT","VERIFIED_EXTERNAL","DEMOTED"},
    "CONDITIONAL":      {"VERIFIED_WIT","VERIFIED_EXTERNAL","DEMOTED"},
    "FAILED_ATTEMPT":   {"OPEN","CONJECTURE","DEMOTED"},
    "GAP":              {"OPEN","CONJECTURE","FAILED_ATTEMPT","DEMOTED"},
    "DEMOTED":          {"OPEN","CONJECTURE"},
    "REJECTED":         {"DEMOTED"},
}

def check(src: str, dst: str, evidence: list[str] | None) -> tuple[bool, list[str]]:
    src, dst = src.upper(), dst.upper()
    problems = []
    if src not in TRANSITIONS:
        return False, [f"unknown source status {src!r}"]
    if dst not in TRANSITIONS and dst not in {"DEMOTED"}:
        return False, [f"unknown target status {dst!r}"]
    if dst not in TRANSITIONS[src]:
        problems.append(f"{src} -> {dst} is not a legal transition; "
                        f"legal targets are {sorted(TRANSITIONS[src])}")
        if src == "CHECKED_BOUNDED" and dst in VERIFIED:
            problems.append(
                "specifically: bounded evidence never becomes universal evidence. "
                "Route through CHECKED_SYMBOLIC or PROVED_SKETCH — both require a "
                "different KIND of argument, not more instances.")
    if dst in NEEDS_EVIDENCE and not evidence:
        problems.append(f"{dst} asserts a result and needs evidence "
                        "(receipt, certificate, artifact hash, or skeptic review id)")
    return (not problems), problems

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--from", dest="src", required=True)
    c.add_argument("--to", dest="dst", required=True)
    c.add_argument("--evidence", nargs="*", default=[]); c.add_argument("--json", action="store_true")
    d = sub.add_parser("demote"); d.add_argument("--from", dest="src", required=True)
    d.add_argument("--to", dest="dst", required=True)
    d.add_argument("--barrier", required=True,
                   help="the obstruction that blocked the original; required")
    d.add_argument("--json", action="store_true")
    sub.add_parser("table")
    a = ap.parse_args()

    if a.cmd == "table":
        for src in sorted(TRANSITIONS):
            print(f"  {src:<20} -> {', '.join(sorted(TRANSITIONS[src])) or '(terminal)'}")
        print("\n  note: CHECKED_BOUNDED has no edge to any VERIFIED_*.")
        return 0

    if a.cmd == "demote":
        ok, problems = check(a.src, a.dst, ["demotion"])
        if not a.barrier.strip():
            ok, problems = False, problems + ["a demotion must name the obstruction "
                                              "that blocked the original"]
        out = {"legal": ok, "problems": problems, "barrier": a.barrier}
        print(json.dumps(out, indent=2) if a.json else
              (f"DEMOTE {a.src} -> {a.dst}: {'ok' if ok else 'ILLEGAL'}\n  barrier: {a.barrier}"
               + ("" if ok else "\n  " + "\n  ".join(problems))))
        return 0 if ok else 1

    ok, problems = check(a.src, a.dst, a.evidence)
    if a.json:
        print(json.dumps({"legal": ok, "from": a.src.upper(), "to": a.dst.upper(),
                          "problems": problems}, indent=2))
    elif ok:
        print(f"LEGAL: {a.src.upper()} -> {a.dst.upper()}")
    else:
        print(f"ILLEGAL: {a.src.upper()} -> {a.dst.upper()}\n")
        for p in problems: print(f"  {p}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
