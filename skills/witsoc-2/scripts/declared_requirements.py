#!/usr/bin/env python3
"""Environment names the installed packs say they need.

The frame does not know what any pack's backend is called, and a runner that
hard-coded one would have learned it. Each pack names what its own cases
require; this collects those names and nothing else.

Usage:  declared_requirements.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    names: list[str] = []
    for cases in sorted(ROOT.glob("domains/*/evals/path/cases.json")):
        try:
            body = json.loads(cases.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for case in body.get("cases", []):
            for name in case.get("requires", []) or []:
                if name not in names:
                    names.append(name)
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
