#!/usr/bin/env python3
"""Tier availability — can this tier run at all, right now?

Cheap probes so a run can state an honest ceiling up front rather than
discovering after the budget is gone that the expensive tier was never going to
execute. The frame asks for this before tier selection; answering it late is one
of the more expensive mistakes available.

Bio's availability question differs from a formal domain's. There is no
toolchain to find — everything here is standard library — so what limits a tier
is DATA. The executable tier needs the pinned metadata table to exist and to
contain the columns the bundle names. The replication tier needs a second bundle
pinning a different source. Both can be answered in milliseconds, and both are
routinely assumed rather than checked.

Usage:
    availability.py --tier <name> [--bundle <bundle.json>]
    availability.py --all [--bundle <bundle.json>]

Exit: 0 available, 3 unavailable (matching the frame's NOT_RUN convention)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402

TIERS = ["structural", "denominator", "executable", "replication"]


def probe(tier: str, bundle_path: Path | None, replicate: Path | None = None) -> dict:
    if tier in {"structural"}:
        return {"tier": tier, "available": True,
                "detail": "reads the bundle and the claim; no external dependency"}

    if bundle_path is None or not bundle_path.exists():
        return {"tier": tier, "available": False,
                "detail": "no bundle supplied, so data availability cannot be established"}
    try:
        bundle = bl.read_json(bundle_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"tier": tier, "available": False, "detail": f"bundle unreadable: {exc}"}

    data = bundle.get("data") or {}
    csv_rel = data.get("metadata_csv")
    csv_path = (bundle_path.parent / csv_rel).resolve() if csv_rel else None

    if tier == "denominator":
        if not csv_path or not csv_path.exists():
            return {"tier": tier, "available": False,
                    "detail": f"metadata_csv {csv_rel!r} is not present; the experimental unit "
                              "cannot be checked against anything"}
        fields, rows = bl.read_csv(csv_path)
        return {"tier": tier, "available": True,
                "detail": f"{len(rows)} rows, {len(fields)} columns", "columns": fields}

    if tier == "executable":
        needed = ["metadata_csv", "value_column", "unit_column", "label_column",
                  "treatment_label", "control_label"]
        missing = [k for k in needed if not data.get(k)]
        if missing:
            return {"tier": tier, "available": False,
                    "detail": f"bundle.data is missing {missing}"}
        if not csv_path or not csv_path.exists():
            return {"tier": tier, "available": False, "detail": f"{csv_rel!r} not found"}
        fields, rows = bl.read_csv(csv_path)
        absent = [data[k] for k in ("value_column", "unit_column", "label_column")
                  if data[k] not in fields]
        if absent:
            return {"tier": tier, "available": False,
                    "detail": f"columns {absent} named by the bundle are not in the table "
                              f"({fields}). The analysis and the data disagree about what exists"}
        labels = {(r.get(data["label_column"]) or "").strip() for r in rows}
        for key in ("treatment_label", "control_label"):
            if data[key] not in labels:
                return {"tier": tier, "available": False,
                        "detail": f"{key} {data[key]!r} does not occur in "
                                  f"{data['label_column']!r} (present: {sorted(labels)[:8]})"}
        return {"tier": tier, "available": True, "detail": f"{len(rows)} observations, "
                f"columns and labels all present"}

    if tier == "replication":
        # A replicate bundle supplied on the command line is what makes this tier
        # runnable. Whether it is a LEGITIMATE replicate — a different accession,
        # a separately pinned analysis — is the tier's question, not availability's.
        # Answering it here would turn a rejection into an "unavailable", and the
        # two mean opposite things to a run.
        if replicate is not None:
            if not replicate.exists():
                return {"tier": tier, "available": False,
                        "detail": f"replicate bundle {replicate} does not exist"}
            return {"tier": tier, "available": True,
                    "detail": f"replicate bundle supplied: {replicate.name}"}
        ledger = bundle.get("source_ledger") or []
        accessions = {s.get("accession") for s in ledger if isinstance(s, dict) and s.get("accession")}
        if len(accessions) < 2 and not bundle.get("replicate_bundle"):
            return {"tier": tier, "available": False,
                    "detail": "only one pinned source and no replicate_bundle. Replication needs a "
                              "second source that shares nothing with the first"}
        return {"tier": tier, "available": True, "detail": f"{len(accessions)} pinned source(s)"}

    return {"tier": tier, "available": False, "detail": f"unknown tier {tier!r}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--tier", choices=TIERS)
    group.add_argument("--all", action="store_true")
    ap.add_argument("--bundle")
    ap.add_argument("--replicate", help="second bundle, when probing the replication tier")
    args = ap.parse_args()

    bundle_path = Path(args.bundle) if args.bundle else None
    replicate = Path(args.replicate) if args.replicate else None
    tiers = TIERS if args.all else [args.tier]
    results = [probe(t, bundle_path, replicate) for t in tiers]
    print(json.dumps(results if args.all else results[0], indent=2))
    return 0 if all(r["available"] for r in results) else 3


if __name__ == "__main__":
    sys.exit(main())
