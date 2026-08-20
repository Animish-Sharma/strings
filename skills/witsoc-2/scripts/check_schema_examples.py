#!/usr/bin/env python3
"""Schema-example round-trip — does anything actually satisfy these schemas?

A schema is a claim about what a valid packet looks like, and a claim nothing
has ever satisfied is untested in the specific way that matters: it can require
a field no producer writes, or contradict itself across two keywords, and it
will validate zero packets forever without complaining.

This finds a real instance of each packet kind — from the packs' fixtures, from
the reducer's self-test, from anywhere in the tree — and validates it. A schema
with no instance anywhere is reported as unexercised, which is not a failure and
is worth knowing before something is built on it.

The check is deliberately about EXISTENCE rather than about a curated example
file. A curated example is maintained alongside the schema and drifts with it; a
real packet from a real run cannot, because if it drifted the run would have
failed.

Usage:  check_schema_examples.py [--json]
Exit:   0 every schema has at least one instance that validates, 1 otherwise
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from jsonschema_lite import validate  # noqa: E402

SKIP = {".git", "__pycache__", ".venv"}


def candidates() -> list[Path]:
    out = []
    for path in SKILL_ROOT.rglob("*.json"):
        if any(part in SKIP for part in path.relative_to(SKILL_ROOT).parts):
            continue
        if path.name.endswith(".schema.json"):
            continue
        out.append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    schemas = sorted((SKILL_ROOT / "schemas").glob("*.schema.json"))
    instances: list[tuple[Path, dict]] = []
    for path in candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            instances.append((path, data))

    report, unexercised, broken = [], [], []
    for schema_path in schemas:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_id = schema.get("$id", schema_path.stem)
        matched = None
        for path, data in instances:
            # A packet declares its own kind, which is what makes this
            # unambiguous: guessing by shape would match the wrong schema and
            # report a pass for a packet nobody validates.
            # A packet declares `schema`; a pack manifest declares
            # `contract_version` instead, because it is a manifest and not a
            # packet. Matching only on `schema` left the contract schemas
            # unexercised while four packs satisfied them daily.
            declares = data.get("schema") or data.get("$id")
            is_pack = (schema_id.startswith("frame-domain-pack-v")
                       and data.get("contract_version") == schema_id.rsplit("v", 1)[-1])
            # A pack's receipt declares its OWN schema id and still has to
            # satisfy the frame's, because contract item 3 says it extends it.
            # Matching only on an exact id left frame-receipt-v1 unexercised
            # while four packs emitted conforming receipts continuously — the
            # schema most central to admission was the one nothing validated.
            extends_frame = (schema_id == "frame-receipt-v1"
                             and isinstance(declares, str)
                             and declares.endswith("-receipt-v1")
                             and "artifact_sha256" in data and "tier" in data)
            if declares == schema_id or is_pack or extends_frame:
                errors: list[str] = []
                validate(data, schema, schema_id, errors)
                matched = {"instance": str(path.relative_to(SKILL_ROOT)), "errors": errors}
                if not errors:
                    break
        if matched is None:
            unexercised.append(schema_id)
            report.append({"schema": schema_id, "status": "unexercised"})
        elif matched["errors"]:
            broken.append((schema_id, matched))
            report.append({"schema": schema_id, "status": "instance does not validate", **matched})
        else:
            report.append({"schema": schema_id, "status": "ok", "instance": matched["instance"]})

    if args.json:
        print(json.dumps({"schemas": len(schemas), "report": report}, indent=2))
    else:
        print(f"SCHEMA EXAMPLES: {len(schemas)} schema(s)\n")
        for row in report:
            mark = {"ok": "ok  ", "unexercised": "----",
                    "instance does not validate": "FAIL"}[row["status"]]
            print(f"  {mark}  {row['schema']:<28} {row.get('instance', row['status'])}")
        if unexercised:
            print(f"\n  {len(unexercised)} schema(s) have no instance anywhere in the tree. Not a "
                  "failure — and a schema nothing has ever satisfied can require a field no "
                  "producer writes and validate zero packets forever without complaining.")
        for schema_id, matched in broken:
            print(f"\n  {schema_id}: {matched['instance']} does not validate")
            for error in matched["errors"][:4]:
                print(f"      {error}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
