#!/usr/bin/env python3
"""Structural tier — is this dossier shaped like evidence?

Ceiling SKETCH, not adversarial. Freeze completeness, every source identified and
dated, every derivation chain terminating, and no cycles. A cycle is not a chain:
two sources citing each other establish that they cite each other.

Usage:  structural.py <dossier.json> --claim <claim.json> [--json]
Exit:   0 pass, 1 fail, 2 error
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402

REQUIRED = ["statement", "assertion_kind", "scope.who", "scope.what", "scope.where",
            "scope.when", "claimed_independent_support", "falsification_conditions",
            "allowed_scope"]
KINDS = {"primary", "contemporary", "later_chronicle", "compilation", "translation",
         "modern_scholarship", "reference_work"}


def dig(obj, path):
    node = obj
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)})); return 2

    problems = []
    for path in REQUIRED:
        value = dig(claim, path)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{path} is absent or empty. 'unknown' is a frozen value; silence "
                            "is a hole nobody can see in a finished report")

    recomputed = al.target_sha256(claim)
    if claim.get("target_sha256") and claim["target_sha256"] != recomputed:
        problems.append("the claim has been edited since it was frozen")
    if dossier.get("target_sha256") not in (None, recomputed):
        problems.append("this dossier is bound to a different claim than the one supplied")

    sources = dossier.get("sources") or []
    if not sources:
        problems.append("no sources. There is nothing here to be independent of anything")
    index = al.index(sources)
    for source in sources:
        sid = source.get("id")
        if not sid:
            problems.append(f"a source has no id: {str(source)[:60]}"); continue
        if source.get("kind") not in KINDS:
            problems.append(f"source {sid!r} has kind {source.get('kind')!r}, not one of "
                            f"{sorted(KINDS)}. What a source CAN support follows from its kind")
        if not source.get("date"):
            problems.append(f"source {sid!r} has no date; a chain cannot be checked for order "
                            "without one")
        if not (source.get("shelfmark") or source.get("identifier") or source.get("url")):
            problems.append(f"source {sid!r} has no shelfmark, identifier, or location. A source "
                            "nobody can go and look at is a claim about the record, not a use of it")
        for parent in source.get("derives_from") or []:
            if parent not in index:
                problems.append(f"source {sid!r} derives from {parent!r}, which is not in the "
                                "dossier. The chain leaves the evidence set and cannot be followed")

    supporting = dossier.get("supporting_sources") or []
    for sid in supporting:
        if sid not in index:
            problems.append(f"supporting source {sid!r} is not in the dossier")
    if supporting:
        summary = al.independence(supporting, index)
        if summary["cycles"]:
            problems.append(f"citation cycles: {summary['cycles']}. Two sources citing each other "
                            "establish that they cite each other")

    result = {"tier": "structural", "verdict": "fail" if problems else "pass",
              "max_status": "SKETCH", "target_sha256": recomputed,
              "sources": len(index), "problems": problems,
              "failure_class": "dossier_structure" if problems else None}
    print(json.dumps(result, indent=2) if args.json else
          f"{result['verdict'].upper()} — {len(problems)} problem(s)")
    if not args.json:
        for p in problems: print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
