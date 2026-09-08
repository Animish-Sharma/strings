#!/usr/bin/env python3
"""Alignment with the predecessor architecture — asserted for a long time, now checked.

`ARCHITECTURE.md` opens by saying the two documents "describe one design and
must stay aligned", and lists what they share: the same three protected roles,
the same contract items, the same two structural refinements, the same
governance rules. Nothing verified any of it. That is a promise with no
mechanism, in a document whose entire argument is that mechanisms beat promises
— and the two files are edited by different hands at different times, which is
the condition under which prose alignment always loses.

So: extract the comparable invariants from both, compare, and require every
difference to be DECLARED in `references/alignment.json` with a reason. A
declared divergence is a design decision. An undeclared one is drift, and the
difference between the two is whether anyone chose it.

Three invariants, chosen because they are the ones both documents actually
assert about each other:

    ROLES        both must name Explorer, Generator, Researcher and no fourth
    GOVERNANCE   the numbered rules, compared by their leading phrase
    CONTRACT     how many items the contract has

The contract count is the interesting one. The predecessor says "five-item
contract" in three places; this frame has six, because `selection` was added
here. That IS a real divergence and it is declared — which is what this check
should say about it, instead of either failing forever or noticing nothing.

Usage:  check_alignment.py [--other <path/to/ARCHITECTURE.md>] [--json]
Exit:   0 aligned or every divergence declared, 1 undeclared drift, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OTHER = ROOT.parent / "witsoc" / "ARCHITECTURE.md"
DECLARED = ROOT / "references" / "alignment.json"

ROLES = ("Explorer", "Generator", "Researcher")
RULE = re.compile(r"^(\d+)\.\s+\*\*(.+?)[.,]?\*\*", re.MULTILINE)
ITEM = re.compile(r"^(\d+)\.\s+\*\*([A-Z][^*]+?)\*\*\s+—", re.MULTILINE)


def governance_rules(text: str) -> dict[int, str]:
    """Rule number -> normalized leading phrase.

    Normalized to the first three words, lowercased. The two documents word the
    same rule differently on purpose — one says "Import-direction enforcement"
    and the other "Reference-direction enforcement" — and a check that demanded
    identical prose would fail on synonyms while missing a rule that had
    actually changed meaning.
    """
    section = text
    marker = text.find("## 6. Governance")
    if marker != -1:
        section = text[marker:]
    out: dict[int, str] = {}
    for number, phrase in RULE.findall(section):
        words = re.sub(r"[^a-z ]", " ", phrase.lower()).split()
        out.setdefault(int(number), " ".join(words[:3]))
    return out


def contract_items(text: str) -> int:
    """How many items the contract declares, counted from the item list."""
    numbers = {int(n) for n, _ in ITEM.findall(text)}
    return max(numbers) if numbers else 0


def roles_named(text: str) -> set[str]:
    return {role for role in ROLES if re.search(rf"\b{role}\b", text)}


def compare(mine: str, theirs: str) -> list[dict]:
    findings: list[dict] = []

    my_roles, their_roles = roles_named(mine), roles_named(theirs)
    if my_roles != set(ROLES) or their_roles != set(ROLES):
        findings.append({"invariant": "roles", "mine": sorted(my_roles),
                         "theirs": sorted(their_roles),
                         "detail": "both documents must name all three protected roles"})

    my_items, their_items = contract_items(mine), contract_items(theirs)
    if my_items != their_items:
        findings.append({"invariant": "contract_items", "mine": my_items, "theirs": their_items,
                         "detail": f"this frame declares {my_items} contract items and the "
                                   f"predecessor declares {their_items}"})

    my_rules, their_rules = governance_rules(mine), governance_rules(theirs)
    for number in sorted(set(my_rules) | set(their_rules)):
        a, b = my_rules.get(number), their_rules.get(number)
        if a is None or b is None:
            findings.append({"invariant": f"governance_rule_{number}", "mine": a, "theirs": b,
                             "detail": "one document has this rule and the other does not"})
        elif a.split()[0] != b.split()[0]:
            findings.append({"invariant": f"governance_rule_{number}", "mine": a, "theirs": b,
                             "detail": "the rules at this number are about different things"})
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--other", default=str(DEFAULT_OTHER))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    mine_path = ROOT / "ARCHITECTURE.md"
    other_path = Path(args.other)
    provenance = "sibling"
    if not other_path.exists():
        # A snapshot taken at a stated hash, so the divergence question can be
        # asked on a checkout without the sibling installed. references/vendored
        # records where it came from and what it hashed to.
        fallback = ROOT / "references" / "vendored" / "predecessor-ARCHITECTURE.md"
        if fallback.exists():
            other_path, provenance = fallback, "vendored snapshot"
    if not other_path.exists():
        print(f"NOT_RUN: {other_path} is not present. The alignment claim cannot be checked "
              "here, which is a gap and not a pass — say so rather than reporting green.",
              file=sys.stderr)
        # This said "not a pass" and returned 0, which IS a pass. On a checkout
        # without the predecessor installed the alignment claim went unchecked
        # and the suite printed green; its own planted-regression test could not
        # catch anything either, because there was nothing to compare.
        return 3
    try:
        mine, theirs = mine_path.read_text(encoding="utf-8"), other_path.read_text(encoding="utf-8")
        declared = json.loads(DECLARED.read_text(encoding="utf-8")) if DECLARED.exists() else {}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    known = {d["invariant"]: d for d in declared.get("declared_divergences", [])}
    findings = compare(mine, theirs)
    if provenance != "sibling":
        print(f"  (compared against a {provenance}; the installed sibling was not present)")
    undeclared = [f for f in findings if f["invariant"] not in known]
    accounted = [f for f in findings if f["invariant"] in known]

    if args.json:
        print(json.dumps({"undeclared": undeclared, "declared": accounted}, indent=2))
        return 1 if undeclared else 0

    for finding in accounted:
        reason = known[finding["invariant"]].get("reason", "")
        print(f"  declared  {finding['invariant']}: {finding['detail']}")
        print(f"            {reason[:130]}")
    for finding in undeclared:
        print(f"  DRIFT     {finding['invariant']}: {finding['detail']}")
        print(f"            mine={finding['mine']!r} theirs={finding['theirs']!r}")
    print()
    if undeclared:
        print(f"  ALIGNMENT: FAIL — {len(undeclared)} undeclared difference(s)")
        print("  Either bring the two documents back together, or declare the divergence in "
              "references/alignment.json with the reason. A divergence someone chose is a "
              "design decision; one nobody noticed is drift.")
        return 1
    print(f"  ALIGNMENT: PASS — {len(accounted)} declared divergence(s), none undeclared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
