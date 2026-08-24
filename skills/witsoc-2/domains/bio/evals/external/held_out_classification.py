#!/usr/bin/env python3
"""Held-out classification — statements this pack's terms were not written for.

`classify_claim.py --calibrate` scores 12/12, and that number is close to
worthless on its own: the same person wrote the selection terms and the test
statements, so it measures self-consistency. A bag-of-words scorer tuned on its
own examples always scores well on its own examples.

This runs the classifier over claims taken from the PREDECESSOR's fixtures —
`witsoc/references/witsoc-bio/fixtures/` — written for a different system,
against a different design, before this pack existed. Nobody phrased them to
match terms that did not yet exist.

What is external and what is not, precisely, because the distinction is the
whole value of the exercise:

    EXTERNAL   the claim text. This is what the classifier reads, and it is the
               thing that would have been tuned against.
    MINE       the expected class for each. There is no way around that — the
               predecessor has no notion of this pack's classes — so this is a
               generalization test of the TERMS, not an independent check of the
               taxonomy.

A drop from the in-house number is the finding, not a failure of the run. It
measures the distance between prose written to match the terms and prose written
without them, and that distance is what the in-house set cannot see.

Usage:  held_out_classification.py [--json]
Exit:   0 accuracy at or above the floor, 1 below it, 2 the fixtures are absent
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
sys.path.insert(0, str(PACK / "scripts"))
import biolib as bl              # noqa: E402
import classify_claim as cc      # noqa: E402

PREDECESSOR = PACK.parent.parent.parent / "witsoc" / "references" / "witsoc-bio" / "fixtures"

VENDORED = HERE / "vendored"


def external_fixture(name: str) -> tuple[Path | None, str]:
    """The sibling's copy when it is installed, else the vendored one.

    Returns the path and which of the two it is, because a reader is entitled to
    know whether the number came from the live source or from a copy taken at a
    stated hash. A divergence between them is a finding, not a detail: the
    vendored MANIFEST.json records what was copied.
    """
    live = PREDECESSOR / name
    if live.exists():
        return live, "sibling"
    local = VENDORED / name
    if local.exists():
        return local, "vendored"
    return None, "absent"


# The claim text is theirs; the expected class is mine. Keyed by their task_id so
# the mapping is auditable against the source rather than restated from it.
EXPECTED = {
    "cell-count-population-causal-overclaim": "cell_level_association",
    "within-screen-guide-conditioned-effect": "guide_conditioned_within_screen",
    "donor-replicated-perturbseq-upgrade": "donor_replicated_population",
    "gem-groups-are-biological-replicates": "cell_level_association",
    "fdr-fixes-pseudoreplication": "cell_level_association",
    "multiple-guides-not-biological-replication": "target_conditioned",
    "cells-improve-within-unit-precision": "cell_level_association",
    "replogle-public-metadata-cell-denominator": "cell_level_association",
    # Relabelled on inspection of the TUNE half, and the correction is mine to
    # make there: the claim's subject is whether CELLS are independent
    # replicates, and "spatial or in vivo" is the context it says that about.
    # Labelling it spatial_tissue was reading the setting instead of the claim.
    "spatial-invivo-cells-nested": "cell_level_association",
    "few-donor-positive-case-caution": "donor_replicated_population",
    "dixit-immune-tf-direct-cell-evidence": "cell_level_association",
    "dixit-cells-as-replicates-overclaim": "cell_level_association",
    "adamson-upr-jurkat-context": "cell_level_association",
    "datlinger-cropseq-guide-readable": "guide_conditioned_within_screen",
}

# Below this, the terms do not generalize and the in-house score is measuring
# nothing. Set before the first run, so it is a threshold and not a description
# of whatever came back. The first run returned 21%.
FLOOR = 0.60

# The set is SPLIT, and the split is the methodology.
#
# Tuning terms against a held-out set turns it into an in-house set — quietly,
# and the number afterwards looks like generalization while measuring the same
# self-consistency as before. So half of these are visible for fixing and half
# are not, by a deterministic rule (sorted task_id, alternating), and the
# reported figure is the HOLDOUT half.
#
# The tune half is burned the moment it is used and stays in the file as a
# regression test, which is what it is now good for. When the holdout half is
# eventually used to fix something too, it must be replaced rather than reused,
# and the replacement has to come from outside again.
def split(tasks: list[str]) -> tuple[set[str], set[str]]:
    ordered = sorted(tasks)
    return set(ordered[0::2]), set(ordered[1::2])


def load_claims() -> list[tuple[str, str]]:
    out = []
    for name in ("replicate_denominator_fixture.jsonl", "real_claim_fixtures.jsonl"):
        path, provenance = external_fixture(name)
        if path is None:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            task, claim = row.get("task_id"), row.get("claim")
            if task in EXPECTED and claim:
                out.append((task, claim))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    claims = load_claims()
    if not claims:
        print(f"NOT_RUN: no predecessor fixtures under {PREDECESSOR}. External evaluation is "
              "the only evidence this pack has that it works on material its author did not "
              "write, so its absence is a gap and never a pass.", file=sys.stderr)
        return 2

    tune, holdout = split([task for task, _ in claims])
    classes = bl.load_table("claim_classes.json")["classes"]
    rows, correct = [], 0
    for task, claim in sorted(claims):
        result = cc.resolve(claim, classes)
        got = (result.get("claimed_class") if result["verdict"] == "RESOLVED"
               else result["verdict"])
        want = EXPECTED[task]
        ok = got == want
        correct += ok
        rows.append({"task_id": task, "half": "tune" if task in tune else "holdout",
                     "want": want, "got": got, "ok": ok,
                     "top": [(r["id"], r["score"]) for r in result["ranked"][:2]],
                     "claim": claim[:110]})

    accuracy = correct / len(rows)
    held = [r for r in rows if r["half"] == "holdout"]
    tuned = [r for r in rows if r["half"] == "tune"]
    held_acc = sum(r["ok"] for r in held) / len(held) if held else 0.0
    tune_acc = sum(r["ok"] for r in tuned) / len(tuned) if tuned else 0.0
    if args.json:
        print(json.dumps({"holdout_accuracy": round(held_acc, 3),
                          "tune_accuracy": round(tune_acc, 3),
                          "overall": round(accuracy, 3), "correct": correct,
                          "total": len(rows), "floor": FLOOR, "rows": rows}, indent=2))
        return 0 if held_acc >= FLOOR else 1

    print("\n  HELD-OUT CLASSIFICATION — claim text written for the predecessor\n")
    for half in ("tune", "holdout"):
        print(f"  {half.upper()} half")
        for row in [r for r in rows if r["half"] == half]:
            print(f"    {'ok  ' if row['ok'] else 'MISS'}  {row['want']:<32} got {row['got']}")
            print(f"            {row['claim']}")
            if not row["ok"]:
                print(f"            top: {row['top']}")
    print("\n" + "=" * 70)
    print(f"  HOLDOUT  {sum(r['ok'] for r in held)}/{len(held)} = {held_acc:.0%}   "
          f"<- the honest number (floor {FLOOR:.0%})")
    print(f"  tune     {sum(r['ok'] for r in tuned)}/{len(tuned)} = {tune_acc:.0%}   "
          "   burned: these informed the terms and are now a regression test")
    print(f"  overall  {correct}/{len(rows)} = {accuracy:.0%}")
    print("\n  The in-house calibration is 12/12 and measures self-consistency: the same "
          "hand wrote the terms and the test. The holdout number is the only one here\n"
          "  that measures whether the terms survive prose written without them.")
    return 0 if held_acc >= FLOOR else 1


if __name__ == "__main__":
    sys.exit(main())
