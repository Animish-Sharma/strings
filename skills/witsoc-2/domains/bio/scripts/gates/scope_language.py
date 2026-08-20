#!/usr/bin/env python3
"""Scope-language gate — does the wording claim more than the readout measured?

Blocking, every tier. This is the last place a bounded result becomes an
unbounded one, and it happens in the prose rather than in the numbers. A
transcriptomic readout in one cell line at one dose becomes "X drives Y",
becomes "X is a therapeutic target", and nothing in the analysis changed.

The gate works from what the assay actually measured. Each escalation tier below
requires evidence the readout does not supply, so using its vocabulary without
declaring that evidence is a fail:

    association -> mechanism     needs an intervention on the intermediate,
                                 not a correlation with it
    association -> causality     needs the perturbation to be the only thing
                                 that changed, defended, not assumed
    cellular -> organismal       needs an organism
    organismal -> clinical       needs a trial
    effect -> generality         needs a second context

It is not a word blocklist. A bundle may use any of these words by declaring the
evidence tier it has: the check is that the vocabulary and the evidence agree.
The pack's preferred wording is in `doctrine/report_language.md` and it is
boring on purpose — supported under this dataset, this context, this
perturbation, this analysis, this metric set; not established outside them.

Usage:  scope_language.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

ESCALATIONS = {
    "mechanism": {
        "terms": ["mechanism", "mechanistic", "acts through", "via the", "mediated by",
                  "drives", "regulates", "controls expression of"],
        "requires": "intervention_on_intermediate",
        "why": "a mechanism claim needs the intermediate to have been perturbed, not correlated with",
    },
    "causality": {
        "terms": ["causes", "causal", "causally", "is responsible for", "leads to"],
        "requires": "causal_design",
        "why": "a causal claim needs the perturbation to be the only thing that differed, argued explicitly",
    },
    "organismal": {
        "terms": ["in vivo", "organism", "systemic", "phenotype in mice", "animal model",
                  "physiological"],
        "requires": "organismal_evidence",
        "why": "cells are not an organism, and a cellular readout cannot reach past the dish",
    },
    "clinical": {
        "terms": ["therapeutic", "drug target", "treatment", "patients would", "clinically",
                  "efficacy", "safe", "indication"],
        "requires": "clinical_evidence",
        "why": "clinical language needs clinical evidence; nothing upstream of a trial supplies it",
    },
    "generality": {
        "terms": ["in general", "universally", "across cell types", "all contexts",
                  "generalizes", "any cell"],
        "requires": "second_context",
        "why": "generality needs a second context; one context establishes one context",
    },
}


# A disclaimer contains the word it disclaims. "nothing here speaks to how
# typical this was" trips a naive term match on "typical", and failing the honest
# sentence while passing the evasive one is the worst possible direction for this
# check to be wrong in. So a hit preceded by a negation inside a short window is
# read as a bound rather than a claim.
NEGATIONS = ("not ", "no ", "nothing", "never", "cannot", "can not", "without",
             "neither", "nor ", "does not", "did not", "is not", "are not",
             "rather than", "instead of", "beyond", "outside")
NEGATION_WINDOW = 60


def negated(text: str, position: int) -> bool:
    window = text[max(0, position - NEGATION_WINDOW):position]
    return any(marker in window for marker in NEGATIONS)


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

    text = " ".join(str(bundle.get(k, "")) for k in
                    ("interpretation", "summary", "conclusion", "report_language"))
    text += " " + str(claim.get("statement", ""))
    lowered = text.lower()

    declared = set(bundle.get("evidence_tiers_available") or [])
    problems = []

    for tier, spec in ESCALATIONS.items():
        hits, disclaimed = [], []
        for term in spec["terms"]:
            for match in re.finditer(rf"(?<![\w-]){re.escape(term)}(?![\w-])", lowered):
                (disclaimed if negated(lowered, match.start()) else hits).append(term)
        hits = sorted(set(hits))
        if disclaimed:
            print(f"  note: {sorted(set(disclaimed))} appear only inside a negation — read as "
                  "stated bounds, not as claims")
        if hits and spec["requires"] not in declared:
            problems.append(
                f"{tier}: uses {hits[:3]} without declaring {spec['requires']!r} in "
                f"evidence_tiers_available. {spec['why']}")

    bounds = bundle.get("stated_bounds") or claim.get("allowed_scope")
    if not bounds:
        problems.append(
            "no stated bounds. Every result here is bounded by dataset, context, perturbation, "
            "analysis, and metric set; a report that does not say so will be read as unbounded")

    if problems:
        print(f"fail: {len(problems)} scope escalation(s)")
        for problem in problems:
            print(f"  {problem}")
        print("  Either supply the evidence tier or write the narrower sentence. "
              "See doctrine/report_language.md")
        return 1
    print("pass: vocabulary matches the evidence tiers declared, bounds stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
