#!/usr/bin/env python3
"""Scope gate — does the wording claim more than the documents can carry?

Blocking, every tier. Three different statements get written the same way:

    documented   a surviving source says this
    attested     independent origins say this
    occurred     this happened

The distance between the first and the third is the entire discipline, and the
prose crosses it for free. A single chronicle becomes "sources record", becomes
"it is established that", with no new evidence at any step.

Each escalation requires something the dossier must declare. It is not a word
blocklist: the words are available to anyone who has the evidence tier that
licenses them.

Usage:  scope_language.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402

ESCALATIONS = {
    "attested": {
        "terms": ["sources record", "sources agree", "widely reported", "corroborated",
                  "multiple accounts", "it is attested"],
        "requires": "independent_origins",
        "why": "plural wording needs more than one origin after the chains are collapsed",
    },
    "occurred": {
        "terms": ["it is established", "certainly", "undoubtedly", "proves", "demonstrates that",
                  "in fact", "definitively"],
        "requires": "corroborated_occurrence",
        "why": "a document establishes that something was written; that it happened is a further "
               "claim needing further evidence",
    },
    "motive": {
        "terms": ["intended to", "in order to", "motivated by", "sought to", "believed that",
                  "wanted"],
        "requires": "stated_intent_in_source",
        "why": "interior states are not in the record unless someone wrote them down, and then "
               "what is in the record is that they wrote them down",
    },
    "generality": {
        "terms": ["typical", "commonly", "throughout the period", "everywhere", "as a rule",
                  "characteristic of"],
        "requires": "systematic_sample",
        "why": "the surviving record is not a sample of the period; generalizing from it needs an "
               "argument about what survived",
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
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}"); return 2

    text = " ".join(str(dossier.get(k, "")) for k in
                    ("interpretation", "summary", "conclusion")) + " " + str(claim.get("exact_statement") or claim.get("statement", ""))
    lowered = text.lower()
    declared = set(dossier.get("evidence_tiers_available") or [])
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
            problems.append(f"{tier}: uses {hits[:3]} without declaring {spec['requires']!r}. "
                            f"{spec['why']}")

    if not (dossier.get("stated_bounds") or claim.get("allowed_scope")):
        problems.append("no stated bounds. Every claim here is bounded by what survived, what was "
                        "searched, and what could be read")

    if problems:
        print(f"fail: {len(problems)} scope escalation(s)")
        for p in problems: print(f"  {p}")
        print("  Either declare the evidence tier or write the narrower sentence.")
        return 1
    print("pass: wording matches the evidence tiers declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
