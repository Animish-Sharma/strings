#!/usr/bin/env python3
"""Generate or verify Witsoc's deterministic runtime contract artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from witsoc_core import runtime_contracts
from witsoc_core.canonical import atomic_write_json


ROOT = Path(__file__).resolve().parent.parent


def atomic_write_text(path: Path, content: str) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.write:
            contract = runtime_contracts.build(ROOT)
            atomic_write_json(ROOT / runtime_contracts.CONTRACT_PATH, contract)
            atomic_write_text(
                ROOT / runtime_contracts.CONTRACT_DOC_PATH,
                runtime_contracts.render_markdown(contract),
            )
        report = runtime_contracts.check(ROOT)
    except (OSError, ValueError, runtime_contracts.RuntimeContractError) as exc:
        report = {"ok": False, "problems": [str(exc)]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "RUNTIME CONTRACTS: "
            + ("PASS" if report["ok"] else "FAIL")
            + (f" - {report.get('content_sha256', '')[:12]}" if report["ok"] else "")
        )
        for problem in report.get("problems", []):
            print(f"  {problem}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
