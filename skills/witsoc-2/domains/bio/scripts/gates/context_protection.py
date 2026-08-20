#!/usr/bin/env python3
"""Context-protection gate — did the analysed context drift from the frozen one?

Blocking, every tier. The maths pack guards against a target weakened to
something trivially true. The empirical version of that move is quieter and far
more common: nobody rewrites the claim, they just analyse a subset. The dose
becomes the dose that worked, the timepoint becomes the timepoint with the
signal, the cell type becomes the one line where it replicated — and the
sentence at the top of the report never changes.

So this gate diffs what the bundle says it analysed against what the claim
froze, dimension by dimension, and treats any difference as a fail. The remedy
is never to edit the claim: a changed context is a NEW claim with a new hash and
its own lineage, and a result for the new one is not a result for the old one.

Usage:  context_protection.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 drift found, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

# Dimensions where a silent change alters what the result means.
GUARDED = [
    "biological_context.cell_type", "biological_context.tissue",
    "biological_context.disease_state", "biological_context.donor_or_model_system",
    "perturbation.entity", "perturbation.modality", "perturbation.dose",
    "perturbation.duration", "assay.type", "assay.readout", "assay.experimental_unit",
    "dataset.id", "dataset.version",
]


def dig(obj, path):
    node = obj
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def norm(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(sorted(str(v).strip().lower() for v in value))
    return str(value).strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    args = ap.parse_args()

    try:
        bundle = bl.read_json(args.bundle)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2

    analysed = bundle.get("analysed_context") or {}
    if not analysed:
        print("fail: bundle declares no analysed_context. The gate cannot compare what was "
              "analysed against what was frozen, and an unstated context is the one that drifts")
        return 1

    drift = []
    for path in GUARDED:
        frozen, actual = norm(dig(claim, path)), norm(dig(analysed, path))
        if not actual:
            continue  # not restated; the claim's value stands
        if frozen and actual != frozen:
            drift.append(f"{path}: frozen {frozen!r}, analysed {actual!r}")

    subset = bundle.get("analysis_subset")
    if subset:
        drift.append(
            f"the analysis was restricted to {subset!r}. A subset is a narrower claim: freeze it "
            "as a new claim with its own hash rather than reporting it against this one")

    if drift:
        print(f"fail: context drift on {len(drift)} dimension(s)")
        for item in drift:
            print(f"  {item}")
        print("  A changed context starts a new claim. It does not update this one.")
        return 1

    print(f"pass: analysed context matches the frozen claim on all {len(GUARDED)} guarded dimensions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
