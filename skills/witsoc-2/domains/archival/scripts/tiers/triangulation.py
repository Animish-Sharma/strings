#!/usr/bin/env python3
"""Triangulation tier — how many of the agreeing sources are actually independent?

Ceiling CHECKED_BOUNDED, adversarial. This is the pack's whole argument and its
refute gate in one operation.

When five sources agree, that is either five observations or one observation
copied four times, and in a bibliography the two are identical. Following each
chain home and counting the distinct ORIGINS is what separates them, and no
amount of argument changes the answer: the chains either root in different places
or they do not.

The refute attempt — `cascade-collapse` — is not a separate step bolted on. It is
the same computation read the other way: the claim asserts N independent
supports, the collapse says how many survive, and a claim whose corroboration
collapses to one source has been refuted AS CORROBORATION, whether or not it is
true.

Two origins are the same origin when they share an author or an archive.
Independence is about who observed, not about how many volumes the observation
was printed in.

Usage:  triangulation.py <dossier.json> --claim <claim.json>
Exit:   0 pass, 1 fail, 2 error, 3 nothing to triangulate
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import archlib as al  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dossier"); ap.add_argument("--claim", required=True)
    args = ap.parse_args()
    try:
        dossier = al.read_json(args.dossier); claim = al.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)})); return 2

    sources = al.index(dossier.get("sources") or [])
    supporting = dossier.get("supporting_sources") or []
    if not supporting:
        print(json.dumps({"tier": "triangulation", "verdict": "not_run",
                          "max_status": "CONJECTURE",
                          "problems": ["the dossier names no supporting sources, so there is "
                                       "nothing to triangulate. This is a gap, not a pass"]},
                         indent=2))
        return 3

    summary = al.independence(supporting, sources)
    required = int(claim.get("claimed_independent_support") or 1)
    problems, notes = [], []

    if summary["cycles"]:
        problems.append(f"citation cycles present: {summary['cycles']}")

    if summary["independent_support"] < required:
        problems.append(
            f"CASCADE: {summary['supporting_sources']} agreeing sources collapse to "
            f"{summary['independent_support']} independent origin(s) "
            f"({summary['distinct_origins']}), against {required} claimed. Agreement between "
            "copies of one report is not corroboration, and it is the form corroboration takes "
            "when there is none")
    else:
        notes.append(f"{summary['supporting_sources']} sources collapse to "
                     f"{summary['independent_support']} origins, which meets the {required} claimed")

    if summary["collapsed"]:
        notes.append(f"{summary['collapsed']} source(s) collapsed into another chain; the "
                     "bibliography overstates the support by that many")

    # A single origin is worth saying out loud even when the claim only asked for one.
    if summary["independent_support"] == 1:
        notes.append("everything here rests on one origin. That can be enough for a documented "
                     "claim and is never enough for a contested one")

    verdict = "fail" if problems else "pass"
    print(json.dumps({
        "tier": "triangulation", "verdict": verdict, "max_status": "CHECKED_BOUNDED",
        "independence": summary, "claimed_independent_support": required,
        "refute_attempt": {
            "gate_name": "cascade-collapse",
            "method": "each supporting source is followed back along derives_from to its root, "
                      "roots are merged by author or archive, and the surviving count is compared "
                      "against the claim",
            "outcome": "survived" if verdict == "pass" else "broken",
        },
        "notes": notes, "problems": problems,
        "failure_class": "citation_cascade" if problems else None,
    }, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
