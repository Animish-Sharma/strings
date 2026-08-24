#!/usr/bin/env python3
"""Statistical-audit gate — the obligations a second pack would own.

Blocking from the executable tier up. Biological plausibility and statistical
validity are different competences and they fail in different directions: a
design can be biologically impeccable and statistically meaningless, and an
estimator can be provably correct about a quantity nobody should care about.

The frame's answer is two packs on one claim, not a fourth role
(ARCHITECTURE.md 2.2). Until a statistics pack is registered, this gate holds
the statistical obligations inside the bio pack and says so plainly, so the
dependency is visible instead of forgotten. When such a pack exists, this gate
becomes a delegation: the same obligations, audited by something that did not
also design the experiment.

The obligations, none of which is a matter of taste:

    estimand              what quantity, over what population, under what
                          intervention. Stated BEFORE the analysis, not read off it.
    identifiability       what has to be true for the estimate to mean the
                          estimand. Named assumptions, not implied ones.
    uncertainty           at the estimand-matching denominator, with the method
                          named. A confidence interval computed over the wrong
                          unit is precise about the wrong thing.
    multiplicity          how many things were tested and what the correction
                          controls. FDR across features does not fix a wrong
                          denominator, and offering it as if it does is itself a finding.
    power                 the smallest effect this design could have detected.
                          A null result without this is not evidence of absence.
    prespecification      what was decided before seeing the data.

Usage:  statistical_audit.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

OBLIGATIONS = {
    "estimand": "the quantity, population, and intervention this number estimates",
    "identifiability": "what must hold for the estimate to mean the estimand",
    "uncertainty": "interval or dispersion at the estimand-matching denominator, method named",
    "multiplicity": "how many comparisons were made and what the correction controls",
    "power": "the smallest effect this design could have detected",
    "prespecification": "what was fixed before the data were seen",
}

FDR_EXCUSE_TELLS = ("fdr", "benjamini", "multiple testing correction", "q-value", "corrected p")


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

    audit = bundle.get("statistical_audit") or {}
    problems, notes = [], []

    delegated = audit.get("delegated_to_pack")
    if delegated:
        notes.append(
            f"these obligations were audited by the {delegated!r} pack. A fatal objection from "
            "either pack blocks admission; verdicts are not averaged")

    for key, meaning in OBLIGATIONS.items():
        value = audit.get(key)
        if not value or (isinstance(value, str) and len(value.strip()) < 8):
            problems.append(f"{key} not stated — {meaning}")

    estimand = (audit.get("estimand") or "").lower()
    claim_class = claim.get("claim_class", "")
    if claim_class.endswith("population") or "population" in claim_class:
        # A PAIRED estimand is a population estimand. "The mean within-donor
        # difference over these donors" is exactly the population quantity a
        # crossed design identifies, and demanding the word "population" in it
        # rejects the strongest design this class admits while accepting any
        # cell-level statement that happens to use the word. The check is for
        # whether the estimand is about UNITS or about observations, so the
        # paired vocabulary counts.
        paired_forms = ("within-donor", "within donor", "within-unit", "within unit",
                        "paired", "per-donor difference", "matched")
        if ("population" not in estimand and "average" not in estimand
                and not any(form in estimand for form in paired_forms)):
            problems.append(
                f"the claim class is population-level but the estimand reads {estimand[:70]!r}. "
                "The estimand and the claim have to be about the same thing")

    multiplicity = (audit.get("multiplicity") or "").lower()
    unit_note = (audit.get("uncertainty") or "").lower()
    if any(tell in multiplicity for tell in FDR_EXCUSE_TELLS) and \
            ("cell" in unit_note and "cluster" not in unit_note and "mixed" not in unit_note):
        problems.append(
            "multiple-testing correction is offered alongside cell-level uncertainty. The "
            "correction controls error across features; it does not change the denominator, and "
            "the denominator is what is wrong. This is a demotion trigger in its own right")

    power = audit.get("power")
    if isinstance(power, dict) and power.get("minimum_detectable_effect") is None:
        problems.append("power is described without a minimum detectable effect, which is the "
                        "only part of it a null result depends on. `scripts/power.py` computes "
                        "it against the test that will actually be run")

    # Multiplicity and sensitivity both have computations now, and a gate that
    # accepts a sentence where a number exists is accepting the sentence.
    screen = audit.get("feature_universe") or audit.get("features_tested")
    if screen and not audit.get("multiplicity_computed"):
        problems.append(
            f"the endpoint came out of a universe of {screen} features and multiplicity is "
            "described in prose. Run `scripts/multiplicity.py` — the number that matters is how "
            "often the BEST of that many null features looks this good, and for a large screen "
            "it is not small")

    sensitivity = audit.get("specification_sensitivity")
    if sensitivity is None:
        problems.append(
            "no specification_sensitivity. Filtering, transform, and aggregation choices are all "
            "defensible and all arguable; `scripts/multiverse.py` re-runs the contrast under each "
            "and reports whether the result survives them. Claiming robustness without it is "
            "claiming something nobody measured")
    elif isinstance(sensitivity, dict):
        verdict = str(sensitivity.get("verdict", "")).upper()
        if verdict == "SPECIFICATION_DEPENDENT":
            problems.append(
                "the multiverse reports a sign flip across defensible specifications. The result "
                "is a statement about the pipeline, and no correction fixes that")
        elif verdict == "FRAGILE":
            notes.append(
                f"the effect survives {sensitivity.get('significant_in', 'some')} specifications. "
                "That is the finding and it belongs in the report — the pre-registered "
                "specification is still the answer, and this is its caveat")

    if not delegated:
        notes.append(
            "audited inside the bio pack, by the same pack that owns the design. Register a "
            "statistics pack and delegate this gate; a specialist who did not design the "
            "experiment is worth more here than any amount of care by one who did")

    for note in notes:
        print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} statistical obligation(s) unmet")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: all {len(OBLIGATIONS)} statistical obligations stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
