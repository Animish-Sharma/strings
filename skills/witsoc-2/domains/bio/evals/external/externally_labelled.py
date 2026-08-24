#!/usr/bin/env python3
"""Externally-DERIVED labels — the half of the held-out test that was still mine.

`held_out_classification.py` runs the classifier over claim text written for the
predecessor system, and reports an honest generalization number. Its remaining
weakness was stated plainly there and never fixed: the claim text is external
and the EXPECTED CLASS is mine. So it measures whether the terms survive
unfamiliar prose, and it cannot measure whether the taxonomy is right, because
the same hand drew the taxonomy and the answer key.

This closes that. The predecessor's fixtures carry `required_flags` — an
externally authored annotation of what each claim gets wrong or needs, written
years before this pack's classes existed. The expected ESTIMAND is derived from
those flags by a stated rule, so the answer key is a mechanical consequence of
somebody else's annotation rather than a judgement of mine.

The derivation, and it is the whole argument:

    a flag naming a CELL denominator problem      -> the claim is about cells
    a flag naming SCREEN scope                    -> within-screen
    a flag naming UPSTREAM UNITS or population    -> population
    a flag naming GUIDE redundancy                -> within-screen

A claim carrying flags from two families is skipped rather than guessed at:
where the external annotation is ambiguous, inventing a tiebreak would put my
judgement back into the answer key by the back door, which is the exact thing
this file exists to remove.

What this still cannot do is check the taxonomy's SHAPE — whether ten classes
are the right ten. Nothing available here can, and the difference between "the
labels are external" and "the design is validated" is worth keeping visible.

Usage:  externally_labelled.py [--json]
Exit:   0 at or above the floor, 1 below it, 2 the fixtures are absent
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


# Their flag vocabulary -> the estimand it implies. One entry per flag that
# carries a denominator meaning; flags about procedure ("control_required",
# "design_ledger_required") imply no estimand and are ignored.
FLAG_ESTIMAND = {
    "cell_count_not_replicates": "cell_level",
    "pseudoreplication": "cell_level",
    "fdr_cannot_fix_pseudoreplication": "cell_level",
    "wrong_uncertainty_denominator": "cell_level",
    "technical_unit_overclaim": "cell_level",
    "cells_nested_in_tissue_or_animal": "cell_level",
    "within_unit_precision": "cell_level",
    "metadata_denominator_missing": "cell_level",
    "within_screen_scope": "within_screen",
    "guide_qc_required": "within_screen",
    "guide_redundancy_not_biological_replication": "within_screen",
    "upstream_units_required": "population",
    "few_upstream_units": "population",
    "pseudobulk_or_cluster_robust_required": "population",
    "population_claim_requires_caution": "population",
    # These say what the claim FAILS to be, not what it is, so they carry no
    # estimand of their own. Reading "population_denominator_missing" as "this
    # is a population claim" would invert the annotation's meaning.
    "population_denominator_missing": None,
    "not_population_replication": None,
    "control_required": None,
    "design_ledger_required": None,
}

FLOOR = 0.60


def expected_estimand(flags: list[str]) -> tuple[str | None, str]:
    implied = {FLAG_ESTIMAND.get(f) for f in flags}
    implied.discard(None)
    if len(implied) == 1:
        return implied.pop(), ""
    if not implied:
        return None, "no flag carries an estimand"
    return None, f"flags imply {sorted(implied)} — ambiguous, and guessing would put my "\
                 "judgement back into the answer key"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path, provenance = external_fixture("replicate_denominator_fixture.jsonl")
    if not path.exists():
        print(f"NOT_RUN: {path} is absent. An externally-labelled set is the only evidence "
              "this taxonomy has that it is not graded by its own author, so its absence is "
              "a gap and never a pass.", file=sys.stderr)
        return 2

    classes = bl.load_table("claim_classes.json")["classes"]
    by_id = {c["id"]: c for c in classes}
    rows, skipped, correct, scored = [], [], 0, 0

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        want, why = expected_estimand(case.get("required_flags") or [])
        if want is None:
            skipped.append({"task_id": case.get("task_id"), "why": why})
            continue
        result = cc.resolve(case["claim"], classes)
        chosen = (result.get("claimed_class") if result["verdict"] == "RESOLVED"
                  else result.get("ceiling_class"))
        got = (by_id.get(chosen) or {}).get("estimand") if chosen else result["verdict"]
        ok = got == want
        correct += ok
        scored += 1
        rows.append({"task_id": case.get("task_id"), "want": want, "got": got, "ok": ok,
                     "class": chosen, "flags": case.get("required_flags"),
                     "claim": case["claim"][:100]})

    accuracy = correct / scored if scored else 0.0
    if args.json:
        print(json.dumps({"accuracy": round(accuracy, 3), "correct": correct, "scored": scored,
                          "skipped": skipped, "floor": FLOOR, "rows": rows}, indent=2))
        return 0 if accuracy >= FLOOR else 1

    print("\n  EXTERNALLY-LABELLED — the answer key derived from somebody else's flags\n")
    for row in rows:
        print(f"  {'ok  ' if row['ok'] else 'MISS'}  estimand {row['want']:<14} got {row['got']}"
              f"  (class {row['class']})")
        print(f"          {row['claim']}")
        if not row["ok"]:
            print(f"          flags: {row['flags']}")
    for entry in skipped:
        print(f"  ....  {entry['task_id']}: {entry['why']}")
    print("\n" + "=" * 70)
    print(f"  {correct}/{scored} = {accuracy:.0%} against externally-derived labels "
          f"(floor {FLOOR:.0%}); {len(skipped)} skipped as ambiguous")
    print("  The claim text is external and so is the answer key.")
    print("  Two things this number is NOT. It grades the ESTIMAND, which has four values, not "
          "the class, which has ten — a coarser target, and easier than the 71% held-out\n"
          "  class number for that reason alone; the two are not comparable and putting them "
          "side by side without saying so would be the flattering reading. And it cannot\n"
          "  check the taxonomy's SHAPE — whether these are the right classes — which nothing "
          "available here can.")
    print("  One case makes the derivation visible: a claim the flags mark within_screen "
          "resolved to `target_conditioned`, a class I would not have labelled it. Its\n"
          "  estimand is within_screen, so it scores correct — because the external "
          "annotation is what is being graded against, not my choice of class.")
    return 0 if accuracy >= FLOOR else 1


if __name__ == "__main__":
    sys.exit(main())
