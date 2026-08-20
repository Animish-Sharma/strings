#!/usr/bin/env python3
"""Doctrine coverage — does a pack's doctrine tell its roles about its own gates?

A pack declares blocking gates and writes doctrine for three roles. Nothing
connected the two, so a pack could ship a gate that stops every campaign and
never mention it to the role whose work it stops — and the role would meet it as
a refusal rather than as a rule.

The asymmetry matters: a gate the doctrine never names is a rule discovered by
failing it, which is the most expensive way to learn one and the one most likely
to be worked around rather than satisfied.

Two checks, and neither is about prose quality:

1. Every blocking gate is named somewhere in the pack's doctrine.
2. Every role has doctrine that is more than a stub — a role file that says
   nothing is the same as no role file, and the contract check only verifies
   that the path resolves.

Reported per pack. This is advisory by default because doctrine is prose and a
hard failure on prose invites keyword-stuffing; `--strict` makes it blocking for
a pack that wants the guarantee.

Usage:  check_doctrine_coverage.py [--pack NAME] [--strict] [--json]
Exit:   0 covered (or advisory), 1 gaps under --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
STUB_BYTES = 400


def check(pack_dir: Path) -> dict:
    manifest = json.loads((pack_dir / "domain.json").read_text(encoding="utf-8"))
    name = manifest.get("domain", pack_dir.name)
    doctrine = manifest.get("doctrine", {}) or {}

    texts = {}
    for role, rel in (doctrine.get("roles") or {}).items():
        path = pack_dir / rel
        texts[f"role:{role}"] = path.read_text(encoding="utf-8") if path.is_file() else ""
    for rel in doctrine.get("rules") or []:
        path = pack_dir / rel
        texts[f"rule:{rel}"] = path.read_text(encoding="utf-8") if path.is_file() else ""
    corpus = "\n".join(texts.values()).lower()

    gates = [(manifest.get("gates", {}).get("refute_attempt") or {}).get("name")]
    gates += [g.get("name") for g in (manifest.get("gates", {}).get("additional") or [])
              if isinstance(g, dict) and g.get("blocking")]
    gates = [g for g in gates if g]

    unmentioned = []
    for gate in gates:
        # Match the gate name or its words — doctrine writes "the denominator
        # gate", not "denominator-gate", and demanding the exact token would
        # reward keyword-stuffing over explanation.
        words = [w for w in gate.replace("-", " ").split() if len(w) > 3]
        if gate.lower() not in corpus and not all(w in corpus for w in words):
            unmentioned.append(gate)

    stubs = [role for role, text in texts.items()
             if role.startswith("role:") and len(text) < STUB_BYTES]

    return {"pack": name, "gates": len(gates), "unmentioned": unmentioned,
            "stub_roles": stubs, "doctrine_files": len(texts),
            "doctrine_bytes": len(corpus)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pack"); ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifests = sorted((SKILL_ROOT / "domains").glob("*/domain.json"))
    if args.pack:
        manifests = [m for m in manifests if m.parent.name == args.pack]
    results = [check(m.parent) for m in manifests]
    gaps = [r for r in results if r["unmentioned"] or r["stub_roles"]]

    if args.json:
        print(json.dumps({"packs": results}, indent=2))
    else:
        print(f"DOCTRINE COVERAGE — {len(results)} pack(s)\n")
        for r in results:
            mark = "ok  " if not (r["unmentioned"] or r["stub_roles"]) else "gap "
            print(f"  [{mark}] {r['pack']:<12} {r['gates']} blocking gate(s), "
                  f"{r['doctrine_files']} doctrine file(s), {r['doctrine_bytes'] // 1000}KB")
            for gate in r["unmentioned"]:
                print(f"          gate {gate!r} is blocking and the doctrine never names it — a "
                      "rule discovered by failing it")
            for role in r["stub_roles"]:
                print(f"          {role} is under {STUB_BYTES} bytes; a role file that says "
                      "nothing is the same as no role file")
        if gaps and not args.strict:
            print("\n  Advisory. Doctrine is prose, and failing a build on prose invites "
                  "keyword-stuffing; --strict makes it blocking for a pack that wants the "
                  "guarantee.")
    return 1 if (gaps and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
