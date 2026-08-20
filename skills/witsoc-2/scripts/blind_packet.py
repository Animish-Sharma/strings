#!/usr/bin/env python3
"""Blind packet — strip a result down for independent re-derivation.

Frame-level and domain-neutral: any field needs this, because "independent
re-derivation" is worthless if the second attempt can see the first one's
reasoning. A reviewer handed the original argument will find it convincing; that
is what arguments are for.

So the packet keeps the QUESTION and removes the ANSWER and everything that
leaks it: the derivation, the method family, the sources consulted, the author,
and any commentary. What survives is the frozen claim and its declared
conditions.

Also usable for blinded review, where the reviewer must not know who produced
the artifact or with what.

Usage:
    blind_packet.py --result <result.json> [--out packet.json] [--json]
    blind_packet.py --check <packet.json>      verify nothing leaked
Exit: 0 clean, 1 leak detected, 2 IO error.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

# Field names that leak the answer. Deliberately GENERIC: a frame script that
# hardcoded a particular field's vocabulary would be the same domain bleed this
# tool guards against. A pack extends the list with its own field names via
# --also-strip, because only the pack knows what it calls things.
PRIVATE_FIELDS = {
    "derivation", "reasoning", "rationale", "explanation", "commentary", "notes",
    "answer", "solution", "result_value", "witness", "construction",
    "method", "method_family", "approach", "strategy", "technique",
    "sources", "citations", "references", "premises_used",
    "author", "producer", "producer_ref", "emitted_by", "reviewer_ref",
    "log_excerpt", "diagnostic", "artifact_refs", "receipt_ref", "evidence",
    "closure_audit", "next_mutation", "provider", "model", "session_id",
}
# The question, and the conditions under which it is asked.
KEEP = {"claim_id","exact_statement","formal_target","definitions","assumptions",
        "objective","success_condition","failure_condition","frozen_conditions",
        "target_sha256","canonical_fields","allowed_external_facts","status"}


def strip(node, private, depth: int = 0):
    if isinstance(node, dict):
        return {k: strip(v, private, depth+1) for k, v in node.items()
                if k.lower() not in private}
    if isinstance(node, list):
        return [strip(v, private, depth+1) for v in node]
    return node

def find_leaks(node, private, path: str = "") -> list[str]:
    leaks = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in private:
                leaks.append(f"{path}.{k}" if path else k)
            leaks += find_leaks(v, private, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            leaks += find_leaks(v, private, f"{path}[{i}]")
    return leaks

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--result"); ap.add_argument("--check")
    ap.add_argument("--out"); ap.add_argument("--json", action="store_true")
    ap.add_argument("--also-strip", nargs="*", default=[],
                    help="extra field names this domain uses for its derivation")
    a = ap.parse_args()
    if not (a.result or a.check):
        ap.error("--result or --check is required")
    private = PRIVATE_FIELDS | {f.lower() for f in a.also_strip}
    try:
        data = json.loads(Path(a.check or a.result).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    if a.check:
        leaks = find_leaks(data, private)
        out = {"blind": not leaks, "leaked_fields": leaks,
               "why": ("a packet carrying the original derivation cannot produce an "
                       "independent re-derivation; the second attempt would be "
                       "following, not deriving")}
        print(json.dumps(out, indent=2) if a.json else
              (f"BLIND PACKET: clean" if not leaks else
               f"BLIND PACKET: LEAK — {len(leaks)} field(s)\n  " + "\n  ".join(leaks)
               + f"\n\n  {out['why']}"))
        return 1 if leaks else 0

    packet = strip(data, private)
    kept = sorted(k for k in packet if k in KEEP)
    packet["_blinding"] = {
        "stripped_field_families": sorted(private),
        "note": "the question and its frozen conditions only. A re-derivation from "
                "this packet is independent; one from the full result is a review.",
    }
    if a.out:
        Path(a.out).write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    if a.json: print(json.dumps(packet, indent=2))
    else:
        print(f"BLIND PACKET built  ({len(kept)} question field(s) kept)")
        print(f"  kept: {', '.join(kept) or '(none — check the input shape)'}")
        if a.out: print(f"  wrote {a.out}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
