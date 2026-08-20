#!/usr/bin/env python3
"""Source-capability gate — can these sources support the status being sought?

`scripts/corpus.py` classifies every source by what it is CAPABLE of
supporting, and until now nothing called it. The manifest declared a corpus,
the doctrine told Explorer to retrieve against one, and the adapter never
asked it anything — so the classification existed and never touched a verdict.

The question it answers is not whether a source agrees. It is whether a source
of that KIND could establish the thing it is being used for. A preprint
reporting exactly your effect and an independent replication of it look
identical in a citation list and are worth different amounts, and the difference
only shows when something checks.

Two failures, in opposite directions, and the second is the quiet one:

- **Over-reach.** The bundle claims independent replication and every source is
  a preprint, a method paper, or a benchmark page. None of those can be the
  replication, whatever they report.
- **Under-use.** A dataset accession sits in the ledger unused while the claim
  rests on a review of it. The primary evidence was there and the report cites
  the summary.

Usage:  source_capability.py <bundle.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error, 3 no ledger to classify
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import biolib as bl  # noqa: E402


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

    ledger = bundle.get("source_ledger") or []
    if not ledger:
        print("not_run: no source_ledger to classify")
        return 3

    proc = subprocess.run(
        [sys.executable, str(HERE.parent / "corpus.py"), "--ledger", args.bundle, "--json"],
        capture_output=True, text=True, timeout=120)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"error: corpus.py returned nothing readable — {proc.stderr[:200]}")
        return 2

    problems, notes = [], []

    # Blocking source states are the provenance gate's business; this one is
    # about capability. Report them and do not double-count them as failures.
    if report.get("blocking_states"):
        notes.append(f"source(s) {report['blocking_states']} are retracted or withdrawn — the "
                     "provenance gate owns that; noting it so the two reports agree")

    replication_capable = report.get("replication_capable") or []
    wants_replication = (bundle.get("claims_replication") is True
                         or claim.get("claim_class") == "donor_replicated_population"
                         and bundle.get("replicate_bundle") is not None)
    if wants_replication and not replication_capable:
        problems.append(
            "this bundle reaches for independent replication and no source in the ledger is "
            "capable of being it. A preprint, a method paper, and a benchmark page can each "
            "establish context or method and none of them is a second observation")

    unclassified = [e for e in report.get("entries", []) if e.get("problem")]
    for entry in unclassified:
        problems.append(f"source {entry.get('id')!r}: {entry['problem']}")

    # Under-use: primary evidence present and the claim resting on something weaker.
    traced = {t.get("source_id") for t in (bundle.get("provenance_trace") or [])
              if isinstance(t, dict)}
    primary = [e["id"] for e in report.get("entries", [])
               if "bounded_empirical" in (e.get("can_support") or [])]
    unused_primary = [p for p in primary if p not in traced]
    if unused_primary and traced:
        notes.append(
            f"primary source(s) {unused_primary} are in the ledger and nothing in the claim "
            "traces to them. If the claim rests on a summary of evidence that is sitting right "
            "there, cite the evidence")

    for note in notes:
        print(f"  note: {note}")
    if problems:
        print(f"fail: {len(problems)} source-capability problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"pass: {len(ledger)} source(s) classified; "
          f"{len(replication_capable)} could support replication")
    return 0


if __name__ == "__main__":
    sys.exit(main())
