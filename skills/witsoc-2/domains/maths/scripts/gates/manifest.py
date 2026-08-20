#!/usr/bin/env python3
"""WIT/Lean manifest gate — the three hashes must agree.

An informal artifact and a formal one are two encodings of one claim. If they
drift apart, the kernel checks the Lean, the reviewer reads the WIT, and nobody
checks the same thing twice.

So: frozen_target_sha256 == wit_target_sha256 == lean_target_sha256, all three
present and all three equal. Plus a non-empty label mapping, so every WIT step
can be located in the Lean.

Usage:  manifest.py <manifest.json> [--json]
Exit: 0 valid, 1 violations, 2 IO error.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED = ("wit_path","lean_path","frozen_target_sha256","wit_target_sha256",
            "lean_target_sha256","label_mappings")

def validate(m: dict, base: Path) -> list[str]:
    problems = [f"missing '{f}'" for f in REQUIRED if f not in m]
    if problems: return problems
    for key in ("wit_path","lean_path"):
        if not (base / m[key]).exists():
            problems.append(f"{key} points at {m[key]!r}, which does not exist")
    hashes = {k: m[k] for k in ("frozen_target_sha256","wit_target_sha256","lean_target_sha256")}
    if len(set(hashes.values())) != 1:
        problems.append(
            "the three target hashes disagree — the informal and formal artifacts "
            f"are not encodings of the same claim: {hashes}")
    if not m["label_mappings"]:
        problems.append("label_mappings is empty: no WIT step can be located in the Lean, "
                        "so a per-step verdict cannot be attributed")
    for i, mapping in enumerate(m["label_mappings"]):
        for field in ("wit_label","lean_declaration"):
            if not mapping.get(field):
                problems.append(f"label_mappings[{i}] missing {field}")
    return problems

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifest"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        path = Path(a.manifest); m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    problems = validate(m, path.parent)
    if a.json: print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
    elif problems:
        print(f"MANIFEST: INVALID — {len(problems)} problem(s)\n")
        for p in problems: print(f"  {p}")
    else:
        print(f"MANIFEST: VALID — {len(m['label_mappings'])} label mapping(s), hashes agree")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
