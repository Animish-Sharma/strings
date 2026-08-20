#!/usr/bin/env python3
"""Tier availability for the archival pack.

The frame asks whether a tier can run before a run commits to it. In a formal
domain that means a toolchain; in an empirical one, data. Here it means neither
— everything is stdlib and the evidence is in the dossier — so the honest answer
is that availability is about the DOSSIER: whether it names sources at all, and
whether the chains it declares can be followed.

Saying that plainly is better than inventing a probe. A pack that reports
"available" for a tier that will immediately return not_run has made the check
worse than absent.

Usage:  availability.py --tier <name> [--bundle <dossier.json>] | --all
Exit:   0 available, 3 unavailable
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import archlib as al  # noqa: E402

TIERS = ["structural", "triangulation"]


def probe(tier: str, dossier_path: Path | None) -> dict:
    if tier == "structural":
        return {"tier": tier, "available": True,
                "detail": "reads the dossier and the claim; no external dependency"}
    if dossier_path is None or not dossier_path.exists():
        return {"tier": tier, "available": False,
                "detail": "no dossier supplied, so there is nothing to triangulate"}
    try:
        dossier = al.read_json(dossier_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"tier": tier, "available": False, "detail": f"dossier unreadable: {exc}"}
    supporting = dossier.get("supporting_sources") or []
    if len(supporting) < 2:
        return {"tier": tier, "available": False,
                "detail": f"{len(supporting)} supporting source(s). Triangulation needs at least "
                          "two to have anything to collapse; with one the answer is known in "
                          "advance and running it would dress that up as a finding"}
    return {"tier": tier, "available": True,
            "detail": f"{len(supporting)} supporting sources over "
                      f"{len(dossier.get('sources') or [])} in the dossier"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tier", choices=TIERS); g.add_argument("--all", action="store_true")
    ap.add_argument("--bundle")
    args = ap.parse_args()
    path = Path(args.bundle) if args.bundle else None
    results = [probe(t, path) for t in (TIERS if args.all else [args.tier])]
    print(json.dumps(results if args.all else results[0], indent=2))
    return 0 if all(r["available"] for r in results) else 3


if __name__ == "__main__":
    sys.exit(main())
