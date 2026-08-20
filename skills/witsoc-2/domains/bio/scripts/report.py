#!/usr/bin/env python3
"""Report — assemble the finding from the receipt, not from memory.

The last place a bounded result becomes an unbounded one is the prose, and until
now the prose was written by hand from whatever the author remembered. So the
scope-language gate could pass a report whose numbers had drifted from the
receipt it was supposedly describing, because nothing connected them.

This writes the report FROM the receipt and the bundle. Every number in it came
out of a check; every bound came out of the class table; the status is the one
the receipt supports and not the one anybody hoped for. Where a value is
missing, it says so rather than omitting the line — a report with a gap and a
report that never had the field look identical once the gap is silent.

Three things it refuses to do:

- upgrade the wording past what the receipt supports. `supports_status` is null
  unless the verdict was a pass, and the report says "establishes nothing" when
  it is.
- drop the negative results. A confounder left open, a contradiction unresolved,
  a specification the effect did not survive — these go in the report at the
  same weight as the finding.
- say VERIFIED. This pack cannot reach it, and a report is the place that fact
  most needs to survive.

Usage:
    report.py --receipt <receipt.json> --bundle <bundle.json> --claim <claim.json>
              [--out report.md]

Exit: 0 written, 2 usage/IO
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import biolib as bl  # noqa: E402


def line(label: str, value, missing: str = "not recorded") -> str:
    return f"- **{label}:** {value if value not in (None, '', [], {}) else f'_{missing}_'}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--claim", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    try:
        receipt = bl.read_json(args.receipt)
        bundle = bl.read_json(args.bundle)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    supports = receipt.get("supports_status")
    verdict = receipt.get("verdict")
    analysis = receipt.get("analysis") or {}
    design = receipt.get("design") or {}
    interval = (analysis.get("interval") or {})
    perm = (analysis.get("permutation") or {})

    classes = {c["id"]: c for c in bl.load_table("claim_classes.json")["classes"]}
    spec = classes.get(claim.get("claim_class"), {})

    open_confounders = [c.get("id") for c in (bundle.get("confounders_addressed") or [])
                        if isinstance(c, dict) and str(c.get("verdict", "")).lower()
                        not in {"clear", "resolved"}]
    ledger = bundle.get("contradiction_ledger")
    unresolved = []
    if isinstance(ledger, list):
        unresolved = [e.get("source_id") for e in ledger
                      if isinstance(e, dict) and str(e.get("resolution", "")).startswith("unresolved")]
    sensitivity = (bundle.get("statistical_audit") or {}).get("specification_sensitivity") or {}

    out = []
    out.append(f"# {claim.get('claim_id', 'claim')}\n")
    out.append(f"> {claim.get('exact_statement', '_no statement frozen_')}\n")

    out.append("## What this establishes\n")
    if verdict == "pass" and supports:
        refinement = receipt.get("status_refinement")
        out.append(f"**{supports}**" + (f" ({refinement})" if refinement else "") + " — "
                   f"supported under the frozen dataset, context, perturbation, analysis, and "
                   f"metric set. Not established outside them.\n")
    else:
        out.append(f"**Nothing.** The {receipt.get('tier')} tier returned `{verdict}`, so this "
                   "receipt supports no status. What follows is the record of an attempt, and "
                   "an honest stop is a legitimate result.\n")

    out.append("## The design\n")
    out.append(line("claim class", f"`{claim.get('claim_class')}` — {spec.get('label', '')}"))
    out.append(line("unit carrying the claim", (design.get("experimental_unit") or {}).get("column")))
    out.append(line("independent units", design.get("upstream_units")))
    out.append(line("ceiling this design supports", design.get("design_ceiling")))
    effect = design.get("design_effect") or []
    if effect:
        at_small = next((e for e in effect if e.get("icc") == 0.01), None)
        if at_small:
            out.append(f"- **effective sample size at ICC 0.01:** {at_small['effective_n']} — "
                       "the number that belongs in any statement about precision")
    out.append("")

    out.append("## The number\n")
    out.append(line("effect (difference in unit means)", analysis.get("difference_in_unit_means")))
    if interval.get("ran"):
        out.append(f"- **95% interval:** [{interval['lower']:.4g}, {interval['upper']:.4g}] "
                   f"({interval.get('resampled')}). The interval is the bound; the p-value only "
                   "says whether zero is inside it.")
    out.append(line("permutation p", perm.get("p_value")))
    out.append(line("refutation", (receipt.get("refute_attempt") or {}).get("outcome")))
    nc = receipt.get("negative_control") or analysis.get("negative_control") or {}
    if nc.get("ran"):
        out.append(f"- **negative control:** p = {nc.get('p_value'):.4g} on the control condition "
                   "split against itself. A pipeline that finds a difference here is measuring "
                   "its own structure.")
    out.append("")

    out.append("## What must not be claimed on the strength of this\n")
    for condition in spec.get("conditions_that_must_be_stated", []) or []:
        out.append(f"- {condition}")
    out.append(f"- nothing outside: {bundle.get('stated_bounds') or claim.get('allowed_scope', '_no bounds stated_')}")
    out.append("- not `VERIFIED`. This field cannot reach it: a surviving measurement is support "
               "for a frozen dataset, context, and analysis, and no quantity of it closes that gap.\n")

    out.append("## What is still open\n")
    if open_confounders:
        out.append(f"- confounders not cleared: {open_confounders}")
    if unresolved:
        out.append(f"- contradictions unresolved: {unresolved}")
    gaps = receipt.get("gaps") or receipt.get("gates_not_run") or []
    if gaps:
        out.append(f"- checks that did not run: {gaps} — a gap, not a pass")
    if sensitivity:
        out.append(f"- specification sensitivity: {sensitivity.get('verdict')} "
                   f"({sensitivity.get('significant_in', '?')} specifications)")
    if not (open_confounders or unresolved or gaps or sensitivity):
        out.append("- nothing recorded as open. That is a claim in itself, and it is only true "
                   "if the ledgers above were actually filled in.")
    out.append("")

    out.append("## Provenance\n")
    out.append(line("artifact", receipt.get("artifact_sha256", "")[:16] + "..."))
    out.append(line("frozen target", receipt.get("target_sha256", "")[:16] + "..."))
    out.append(line("tier", receipt.get("tier")))
    out.append(line("produced", receipt.get("produced_at")))
    out.append(line("sources", len(bundle.get("source_ledger") or [])))
    out.append("")
    out.append("_Every number above was read out of the receipt. Nothing here was written from "
               "memory, which is the only reason the report and the check agree._\n")

    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} bytes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
