#!/usr/bin/env python3
"""Dependency availability packet.

Every external result an artifact cites must be resolved and evidenced before
another repair attempt is spent. The reason is narrow and important: **a guessed
name is not repair evidence.** An attempt that cites a plausible-looking
declaration nobody confirmed exists will fail, and the failure will look like a
mathematical problem rather than a bookkeeping one.

Accepted availability: verified | available | local | builtin | imported
Rejected:              unknown | guessed | missing | unresolved | nonexistent

Usage:  dependency_packet.py --packet <p.json> [--json]
Exit: 0 all resolved, 1 unresolved present, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ACCEPTED = {"verified","available","local","builtin","imported"}
REJECTED = {"unknown","guessed","missing","unresolved","nonexistent"}
CHECKED_BY = {"corpus","type_check","import_smoke_test","local_declaration"}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--packet", required=True); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try: packet = json.loads(Path(a.packet).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    problems = []
    for dep in packet.get("dependencies", []):
        name = dep.get("name","?")
        avail = str(dep.get("availability","unknown")).lower()
        if avail in REJECTED:
            problems.append(f"{name}: availability {avail!r} — a guessed name is not "
                            "repair evidence; resolve it before spending another attempt")
        elif avail not in ACCEPTED:
            problems.append(f"{name}: availability {avail!r} is not a recognized value")
        elif not dep.get("checked_by"):
            problems.append(f"{name}: claims {avail!r} with no checked_by "
                            f"(one of {sorted(CHECKED_BY)})")
        elif dep.get("checked_by") not in CHECKED_BY:
            problems.append(f"{name}: checked_by {dep['checked_by']!r} unrecognized")
    for edge in packet.get("edge_case_obligations", []):
        if str(edge.get("status","")).lower() in {"unknown","unhandled","pending"}:
            problems.append(f"edge case {edge.get('case','?')!r} is "
                            f"{edge.get('status')} — an unhandled edge case is an open "
                            "obligation, not a detail")
    out = {"verdict":"FAIL" if problems else "PASS",
           "dependencies":len(packet.get("dependencies",[])),"problems":problems}
    if a.json: print(json.dumps(out, indent=2))
    else:
        print(f"DEPENDENCY PACKET: {out['verdict']} ({out['dependencies']} dependency(ies))")
        for p in problems: print(f"  {p}")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
