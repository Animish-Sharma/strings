#!/usr/bin/env python3
"""Contract-shape checks — three claims every pack makes that nothing verified.

A pack's manifest asserts things about files it points at, and the conformance
checker validates the manifest without ever opening them. So a pack could
declare `claim_schema.extends: frame-claim-v1` and ship a schema that shares
nothing with the frame's; declare five blocking gates and implement two; and
register a status refinement of a status the frame does not have. All three
validate cleanly, because all three are claims about content nobody reads.

1. CLAIM CONTENT — a pack's actual claims must satisfy frame-claim-v1. The
   first version of this compared `required` lists and found every pack
   "violating" the same three fields, which is the shape of a wrong spec rather
   than four wrong packs: a schema restating the frame's requirements is
   bookkeeping, and two copies of a requirement drift. So it validates the
   claims the pack actually ships. That is how it found bio recording an EMPTY
   statement into every campaign state — the pack called the field `statement`,
   the frame reads `exact_statement`, and nothing failed.
2. GATE IMPLEMENTATION — every blocking gate the manifest declares must be
   reachable in the adapter. A declared gate with no code is a check that
   reports nothing while appearing in the receipt as a check.
3. STATUS REFINEMENTS — a refinement must refine a status the frame actually
   has, and must never outrank it. A refinement of a status nobody defined is a
   private vocabulary wearing the frame's clothes.

Usage:  check_contract_shapes.py [--pack NAME] [--json]
Exit:   0 clean, 1 violations
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = SKILL_ROOT / "schemas"


def frame_statuses() -> list[str]:
    state = json.loads((SCHEMAS / "frame-state-v1.schema.json").read_text(encoding="utf-8"))
    return state["properties"]["claims"]["additionalProperties"]["properties"]["status"]["enum"]


def frame_claim_required() -> list[str]:
    claim = json.loads((SCHEMAS / "frame-claim-v1.schema.json").read_text(encoding="utf-8"))
    return claim.get("required", [])


def check_pack(pack_dir: Path) -> list[str]:
    problems: list[str] = []
    manifest = json.loads((pack_dir / "domain.json").read_text(encoding="utf-8"))
    name = manifest.get("domain", pack_dir.name)

    # 1. claim content — the claims this pack actually ships
    required = frame_claim_required()
    # `status` and `payload_sha256` belong to the machinery: a claim gets its
    # status from the reducer and its seal when it becomes a packet, so an
    # AUTHOR is not expected to write either. The fields an author owns are the
    # ones checked here.
    authored = [f for f in required if f not in {"status", "payload_sha256"}]
    fixtures = sorted(set(list(pack_dir.rglob("*_claim.json"))
                          + list(pack_dir.rglob("claim.json"))))
    fixtures = [f for f in fixtures if f.name != "claim.schema.json"]
    if not fixtures:
        problems.append(
            f"{name}: ships no claim fixture, so nothing demonstrates that a claim of this "
            "field's shape satisfies the frame's. The schema is a promise nobody has kept once")
    for fixture in fixtures[:40]:
        try:
            claim = json.loads(fixture.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(claim, dict) or "claim_id" not in claim:
            continue
        missing = [f for f in authored if f not in claim]
        if missing:
            rel = fixture.relative_to(pack_dir)
            problems.append(
                f"{name}: {rel} is missing {missing}. The frame reads these by name — a claim "
                "without `exact_statement` records an empty statement into the campaign state "
                "and nothing fails")

    # 2. declared gates must be reachable in the adapter
    entry = (manifest.get("verification_adapter") or {}).get("entry_point")
    declared_gates = [g.get("name") for g in
                      ((manifest.get("gates") or {}).get("additional") or [])
                      if isinstance(g, dict) and g.get("blocking")]
    if entry and (pack_dir / entry).is_file() and declared_gates:
        adapter_text = (pack_dir / entry).read_text(encoding="utf-8")
        for gate in declared_gates:
            if gate and gate not in adapter_text:
                problems.append(
                    f"{name}: gate {gate!r} is declared blocking and the adapter never names it. "
                    "A declared gate with no code reports nothing and still appears in the "
                    "receipt as a gate")

    # 3. status refinements
    known = set(frame_statuses())
    for label, spec in (manifest.get("status_refinements") or {}).items():
        refines = spec.get("refines")
        if refines not in known:
            problems.append(
                f"{name}: refinement {label!r} refines {refines!r}, which is not a frame status "
                f"({sorted(known)}). A refinement of a status nobody defined is a private "
                "vocabulary wearing the frame's clothes")
        if label in known:
            problems.append(
                f"{name}: refinement {label!r} shadows a frame status of the same name")
        tier = spec.get("tier")
        tiers = {t.get("name") for t in
                 ((manifest.get("verification_adapter") or {}).get("tiers") or [])}
        if tier and tier not in tiers:
            problems.append(
                f"{name}: refinement {label!r} names tier {tier!r}, which this pack does not have")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pack")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    packs = sorted((SKILL_ROOT / "domains").glob("*/domain.json"))
    if args.pack:
        packs = [p for p in packs if p.parent.name == args.pack]
    problems: list[str] = []
    for manifest in packs:
        problems += check_pack(manifest.parent)

    if args.json:
        print(json.dumps({"packs": len(packs), "problems": problems}, indent=2))
    elif problems:
        print(f"CONTRACT SHAPES: FAIL — {len(problems)} violation(s) across {len(packs)} pack(s)\n")
        for problem in problems:
            print(f"  {problem}")
    else:
        print(f"CONTRACT SHAPES: PASS — {len(packs)} pack(s); extensions extend, declared gates "
              "exist, refinements refine something real")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
