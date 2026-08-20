#!/usr/bin/env python3
"""Lean receipt validity — is this receipt about the artifact that exists now.

Two failure modes, both common:

  STALE   the receipt predates the artifact's last edit. A passing build from a
          previous version trivially launders a later broken one, so a receipt
          older than the file it describes is not evidence about that file.
  HOLLOW  the run proved the toolchain works, not the claim. Environment checks,
          placeholder files, and "cannot auto-translate" messages all exit zero
          and all establish nothing.

Usage:  lean_receipt.py --receipt <r.json> --artifact <a.lean> [--json]
Exit: 0 valid, 1 invalid, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime
from pathlib import Path

HOLLOW = ("placeholder_check","this file just verifies lean is working",
          "cannot auto-translate","please provide explicit lean_statement",
          "environment check","no theorem to check")
RE_DECL = re.compile(r"^\s*(?:theorem|lemma)\s+[\w.']+", re.MULTILINE)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--receipt", required=True); ap.add_argument("--artifact", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        receipt = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
        art = Path(a.artifact); source = art.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    problems = []
    live = hashlib.sha256(source.encode()).hexdigest()
    recorded = receipt.get("artifact_sha256")
    if not recorded:
        problems.append("receipt records no artifact_sha256, so it cannot be bound to "
                        "any particular version of the file")
    elif recorded != live:
        problems.append(f"STALE: receipt covers {recorded[:16]}... but the artifact is now "
                        f"{live[:16]}...  A pass from an earlier edit is not evidence "
                        "about the file that exists now.")
    produced = receipt.get("produced_at")
    if produced:
        try:
            ts = datetime.fromisoformat(produced.replace("Z","+00:00")).timestamp()
            if ts + 1 < art.stat().st_mtime:
                problems.append("STALE: the receipt predates the artifact's last modification")
        except ValueError:
            problems.append(f"produced_at {produced!r} is not parseable")
    if receipt.get("exit_code") not in (0, None) and receipt.get("verdict") == "pass":
        problems.append("receipt claims pass with a non-zero exit code")
    if not receipt.get("command"):
        problems.append("receipt records no command, so the run is not reproducible")

    blob = json.dumps(receipt).lower()
    for phrase in HOLLOW:
        if phrase in blob:
            problems.append(f"HOLLOW: receipt output contains {phrase!r} — this run "
                            "established that the toolchain works, not the claim")
            break
    if not RE_DECL.search(source):
        problems.append("the artifact declares no theorem or lemma; there is nothing "
                        "for a receipt to be about")

    out = {"valid": not problems, "problems": problems, "artifact_sha256": live}
    if a.json: print(json.dumps(out, indent=2))
    elif problems:
        print(f"LEAN RECEIPT: INVALID — {len(problems)} problem(s)\n")
        for p in problems: print(f"  {p}")
    else: print("LEAN RECEIPT: valid — fresh, bound, and about a real declaration")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
