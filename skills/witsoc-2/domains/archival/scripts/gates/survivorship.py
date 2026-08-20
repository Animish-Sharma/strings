#!/usr/bin/env python3
"""Survivorship gate — what would the record look like if this were false?

Blocking, every tier. The archive is a survivorship-biased sample of a
survivorship-biased sample: what was written, of what happened; what survived, of
what was written; what was catalogued, of what survived. Every claim resting on
the record inherits all three filters, and claims of ABSENCE inherit them fatally.

Two things are checked:

1. An absence claim ("there is no record of X", "X did not happen") must state
   why a record would have survived if the thing had occurred. Without that, the
   claim is about the archive and not about the past, and it should be worded
   that way.
2. Any claim must state what the record would look like if the claim were false.
   If the answer is "the same", the dossier does not discriminate, and its
   sources are consistent with the claim rather than evidence for it.

The second is the more useful of the two and the more often missing.

Usage:  survivorship.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402

ABSENCE_MARKERS = ("no record", "no evidence", "never", "did not", "was not", "absent",
                   "nothing survives", "unattested")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}"); return 2

    problems = []
    statement = (claim.get("exact_statement") or claim.get("statement") or "").lower()
    is_absence = (claim.get("assertion_kind") == "absence"
                  or any(m in statement for m in ABSENCE_MARKERS))

    if is_absence and not dossier.get("survival_argument"):
        problems.append(
            "this is an absence claim and the dossier gives no survival_argument. State why a "
            "record would exist and survive if the thing had happened — otherwise the claim is "
            "about the archive, not about the past, and should say so")

    discriminator = (dossier.get("what_the_record_would_look_like_if_false") or "").strip()
    if len(discriminator) < 20:
        problems.append(
            "the dossier does not say what the record would look like if the claim were false. "
            "If the answer is 'the same', these sources are consistent with the claim rather than "
            "evidence for it, and that difference is the whole of the audit")

    coverage = dossier.get("archive_coverage")
    if not coverage:
        problems.append(
            "no archive_coverage: which archives were searched, which were not, and which are "
            "known to be lost. An unrecorded search cannot be distinguished from one nobody ran")

    if problems:
        print(f"fail: {len(problems)} survivorship problem(s)")
        for p in problems: print(f"  {p}")
        return 1
    print("pass: survival and discrimination both stated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
