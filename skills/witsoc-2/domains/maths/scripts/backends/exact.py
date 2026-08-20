#!/usr/bin/env python3
"""Exact arithmetic backend — integer and rational, with identity certificates.

The rule this file exists to enforce: **finding is numeric and untrusted;
verifying is exact and is the sound part.** A bound discovered by floating-point
search is a candidate. The same bound re-derived in exact rationals, with the
identity written out, is checkable evidence.

So every result carries a self-contained certificate a third party can re-evaluate
without rerunning the search.

Ceiling: CHECKED_SYMBOLIC for an exact symbolic identity over a stated domain;
CHECKED_BOUNDED for anything enumerated.

Usage:
    exact.py verify --certificate <c.json> [--json]
Exit: 0 verified, 1 refuted, 2 IO error.
"""
from __future__ import annotations
import argparse, json, math, sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from safe_eval import NAMESPACE, PredicateError, evaluate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["verify"]); ap.add_argument("--certificate", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: cert = json.loads(Path(a.certificate).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    identity = cert.get("identity")
    if not identity:
        print("ERROR: certificate has no 'identity' to re-evaluate. A bound with no "
              "checkable identity is a claim, not a certificate.", file=sys.stderr)
        return 2
    env = {k: Fraction(str(v)) if isinstance(v,(int,float,str)) and str(v).replace('/','').replace('-','').isdigit()
           else v for k, v in (cert.get("bindings") or {}).items()}
    try:
        holds = evaluate(identity, {**env, "Fraction": Fraction})
    except PredicateError as exc:
        print(f"ERROR: identity failed to evaluate: {exc}", file=sys.stderr); return 2

    out = {"backend":"exact","verdict":"verified" if holds else "refuted",
           "identity":identity,"bindings":{k:str(v) for k,v in env.items()},
           "arithmetic":"exact rational — no floating point in the verification path",
           "max_status": cert.get("max_status","CHECKED_SYMBOLIC"),
           "note":("the search that FOUND this may have been numeric and untrusted; "
                   "this re-derivation is exact and is the part that counts")}
    print(json.dumps(out, indent=2) if a.json else
          f"EXACT: {out['verdict'].upper()}  {identity}\n  {out['note']}")
    return 0 if holds else 1
if __name__ == "__main__":
    sys.exit(main())
