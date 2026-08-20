#!/usr/bin/env python3
"""Placeholder / escape-hatch scan.

A placeholder makes anything type-check, so its presence does not reduce the
kernel's verdict — it voids it. This gate is blocking for exactly that reason.

Usage:  placeholder_scan.py <artifact> [--json]
Exit:   0 clean, 1 placeholder found, 2 IO error.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

# Escape hatches that let an artifact elaborate without establishing anything.
TOKENS = {
    "sorry": "admits the goal outright",
    "admit": "admits the goal outright",
    "axiom": "postulates rather than establishes",
    "constant": "postulates rather than establishes",
    "opaque": "hides the body from the checker",
    "unsafe": "bypasses the checker's guarantees",
    "native_decide": "trusts the compiler rather than the kernel",
    "by?": "an unfilled suggestion hole",
    "?_": "an unfilled goal hole",
    "TODO": "unfinished content",
    "TBD": "unfinished content",
    "REPLACE_ME": "unfinished content",
    "FILL_ME": "unfinished content",
    "fill in": "unfinished content",
    "left to the reader": "an omission wearing a polite phrase",
    "FIXME": "unfinished content",
    "placeholder": "unfinished content",
    "omitted": "unfinished content",
}
# `--` in WIT and `--`/`/- -/` in Lean.
RE_LINE_COMMENT = re.compile(r"--.*$")

def scan(text: str) -> list[dict]:
    found = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = RE_LINE_COMMENT.sub("", raw)
        for token, why in TOKENS.items():
            pattern = (rf"(?<![\w?]){re.escape(token)}(?![\w])"
                       if token.isalpha() else re.escape(token))
            if re.search(pattern, line, re.IGNORECASE if token.isupper() else 0):
                found.append({"line": line_no, "token": token, "why": why,
                              "text": raw.strip()[:100]})
    return found

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        text = Path(a.artifact).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    found = scan(text)
    if a.json:
        print(json.dumps({"verdict": "fail" if found else "pass", "findings": found}, indent=2))
    elif found:
        print(f"PLACEHOLDER SCAN: FAIL — {len(found)} escape hatch(es)\n")
        for f in found:
            print(f"  line {f['line']}: '{f['token']}' — {f['why']}\n      {f['text']}")
        print("\nA placeholder voids the checker's verdict; it does not merely weaken it.")
    else:
        print("PLACEHOLDER SCAN: PASS — no escape hatches")
    return 1 if found else 0

if __name__ == "__main__":
    sys.exit(main())
