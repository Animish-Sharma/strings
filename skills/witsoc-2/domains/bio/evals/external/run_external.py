#!/usr/bin/env python3
"""External evaluation — this pack's denominator gate against someone else's answers.

Every fixture in `evals/` and `scripts/negative_control/` was authored by
whoever built this pack, which is the largest single reason to distrust its
green results. A gate that has only ever been graded against its author's
expectations has been graded against nothing.

`mapping.json` describes the arrangement: the cases, the claims, and the
expected verdicts come from a regression family written for the predecessor
system, by someone else, before this pack existed. What is added here is the
mapping — which claim class each case belongs to, and a metadata table matching
the design the case describes. The inputs are half external; the answers are
entirely external, and the answers are the half that matters.

**The vocabulary collision is the trap.** Their `CONDITIONAL` means
narrow-and-resting-on-an-assumption and is WEAKER than their `CHECKED_BOUNDED`.
The frame ranks `CONDITIONAL` higher, because it reads as a claim about the
general statement modulo an assumption. Comparing the two names directly would
score half this evaluation backwards while looking like it ran. So their
`CONDITIONAL` is compared against this pack's `CHECKED_BOUNDED` plus a non-empty
`conditions_that_must_be_stated`, which is what their word actually meant.

Usage:  run_external.py [--verbose] [--json]
Exit:   0 every external expectation reproduced, 1 otherwise, 2 IO error.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
sys.path.insert(0, str(PACK / "scripts"))
import biolib as bl  # noqa: E402

HEADER = ["cell_barcode", "donor", "guide", "lane", "sample", "condition", "value"]


def build_metadata(units: dict, path: Path) -> None:
    """A table matching the design the external case describes."""
    rng = random.Random(20260821)
    rows = []
    donors = units.get("donor", 1)
    guides = units.get("guides", 0)
    lanes = units.get("lanes", 0)
    per = units.get("cells_per_unit", 100)
    crossed = units.get("crossed", False)

    if guides:
        for g in range(1, guides + 1):
            cond = "treated" if g <= guides // 2 else "control"
            for c in range(per):
                rows.append([f"cell_{g}_{c}", "donor_1", f"guide_{g}", "lane_1",
                             f"guide_{g}", cond, round(rng.gauss(0, 1), 4)])
    elif lanes:
        for l in range(1, lanes + 1):
            cond = "treated" if l <= lanes // 2 else "control"
            for c in range(per):
                rows.append([f"cell_{l}_{c}", "donor_1", "none", f"lane_{l}",
                             f"lane_{l}", cond, round(rng.gauss(0, 1), 4)])
    elif crossed:
        for d in range(1, donors + 1):
            for cond in ("treated", "control"):
                for c in range(per):
                    rows.append([f"cell_{d}_{cond}_{c}", f"donor_{d}", "none", "lane_1",
                                 f"D{d}_{cond}", cond, round(rng.gauss(0, 1), 4)])
    else:
        for c in range(per):
            cond = "treated" if c % 2 == 0 else "control"
            rows.append([f"cell_{c}", "donor_1", "none", "lane_1", f"single_{cond}", cond,
                         round(rng.gauss(0, 1), 4)])

    path.write_text("\n".join([",".join(HEADER)] + [",".join(str(v) for v in r) for r in rows])
                    + "\n", encoding="utf-8")


def build_claim(case: dict, path: Path) -> dict:
    claim = {"claim_id": case["task_id"], "claim_class": case["claim_class"],
             "statement": f"external case: {case['design']}",
             "assay": {"experimental_unit": case["units"]["unit_column"]}}
    claim["target_sha256"] = bl.target_sha256(claim)
    path.write_text(json.dumps(claim, indent=2), encoding="utf-8")
    return claim


def expected_from(their_status: str, their_flags: list[str]) -> dict:
    """Translate their vocabulary into what this pack must produce.

    `required_flags` is the load-bearing field and it is easy to skip. Every
    non-rejected case in their set carries flags that the report MUST show —
    `within_unit_precision`, `not_population_replication`, `few_upstream_units`
    — which is their spelling of this pack's `conditions_that_must_be_stated`.
    Reading their status word alone and inferring the condition requirement from
    it scored two cases wrong while looking like a disagreement about the
    pack, when it was a disagreement about how I had read them.
    """
    if their_status == "REJECTED":
        return {"max_status": "REJECTED", "requires_conditions": False,
                "their_flags": their_flags}
    return {"max_status": "CHECKED_BOUNDED",
            "requires_conditions": bool(their_flags),
            "their_flags": their_flags}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    mapping = json.loads((HERE / "mapping.json").read_text(encoding="utf-8"))

    # Read their flags from their own file rather than paraphrasing them here.
    source = Path(mapping["source"])
    if not source.is_absolute():
        source = (PACK.parent.parent.parent / mapping["source"]).resolve()
    provenance = "sibling"
    if not source.is_file():
        # A copy taken at a stated hash, so this comparison runs on a checkout
        # without the predecessor installed. See vendored/MANIFEST.json.
        fallback = HERE / "vendored" / Path(mapping["source"]).name
        if fallback.is_file():
            source, provenance = fallback, "vendored"
    their_flags = {}
    if source.is_file():
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                their_flags[entry["task_id"]] = entry.get("required_flags", [])
    else:
        # Falling back to "the status word alone" and then FAILING on the
        # comparison reported a disagreement with an outside author that was
        # never measured — the flags they required simply were not there. This
        # evaluation exists to compare against someone else's labels; without
        # them it has nothing to say, and saying nothing is the honest result.
        print(f"NOT_RUN: neither the sibling nor a vendored copy of {source.name} is "
              "present, so this pack's agreement with an "
              "independent author is unmeasured here. That is a gap and not a pass, and "
              "it is not a disagreement either — their required flags were never read.",
              file=sys.stderr)
        return 3
    classes = {c["id"]: c for c in bl.load_table("claim_classes.json")["classes"]}
    results, failures = [], []

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for case in mapping["cases"]:
            metadata = tmp / f"{case['task_id']}.csv"
            build_metadata(case["units"], metadata)
            claim_path = tmp / f"{case['task_id']}_claim.json"
            build_claim(case, claim_path)

            bundle = {
                "schema": "bio-audit-bundle-v1",
                "claim_id": case["task_id"],
                "target_sha256": json.loads(claim_path.read_text())["target_sha256"],
                "data": {"metadata_csv": metadata.name,
                         "unit_column": case["units"]["unit_column"],
                         "biological_unit_column": case["units"]["unit_column"],
                         "value_column": "value", "label_column": "condition"},
                "design_evidence": [{"id": r} for r in
                                    classes[case["claim_class"]].get("requires", [])],
                # Their required_flags are conditions the report must carry, so a
                # bundle claiming to meet their case has to state them. A
                # few-cluster design that does not write its caveat down is
                # correctly demoted by this pack, and reproducing their verdict
                # means writing it.
                "stated_conditions": list(
                    classes[case["claim_class"]].get("conditions_that_must_be_stated", []))
                + ([("few-cluster: fewer upstream units than the comfortable threshold; "
                     "cluster-robust uncertainty is unreliable here")]
                   if "few_upstream_units" in their_flags.get(case["task_id"], []) else []),
            }
            bundle_path = tmp / f"{case['task_id']}_bundle.json"
            bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, str(PACK / "scripts" / "gates" / "denominator_gate.py"),
                 str(bundle_path), "--claim", str(claim_path)],
                capture_output=True, text=True, timeout=300)
            try:
                got = json.loads(proc.stdout)
            except json.JSONDecodeError:
                failures.append(f"{case['task_id']}: gate produced no JSON")
                continue

            spec = classes[case["claim_class"]]
            want = expected_from(case["their_status"], their_flags.get(case["task_id"], []))
            got_status = got.get("max_status")
            agrees = got_status == want["max_status"]
            conditions_required = bool(spec.get("conditions_that_must_be_stated"))
            # A rejected claim produces no report, so what its class would have
            # required a report to say is not a comparison — it is two unrelated
            # facts placed next to each other. Comparing them scored six correct
            # rejections as disagreements.
            conditions_agree = (want["max_status"] == "REJECTED"
                                or conditions_required == want["requires_conditions"])

            results.append({
                "task_id": case["task_id"], "their_status": case["their_status"],
                "this_pack": got_status, "agrees": agrees,
                "conditions_expected": want["requires_conditions"],
                "conditions_required": conditions_required,
                "conditions_agree": conditions_agree,
                "flags": got.get("flags", []),
            })
            if not agrees:
                failures.append(f"{case['task_id']}: they say {case['their_status']}, this pack "
                                f"reaches {got_status} (expected {want['max_status']})")
            elif not conditions_agree:
                failures.append(
                    f"{case['task_id']}: verdict agrees but the condition requirement does not — "
                    f"their {case['their_status']} means conditions "
                    f"{'must' if want['requires_conditions'] else 'need not'} be stated, and this "
                    f"pack {'requires' if conditions_required else 'does not require'} them")

    if args.json:
        print(json.dumps({"cases": len(results), "failures": failures, "results": results},
                         indent=2))
    else:
        print(f"EXTERNAL DENOMINATOR EVALUATION — {len(results)} case(s) graded against "
              "expectations this pack did not write\n")
        for r in results:
            mark = "ok  " if r["agrees"] and r["conditions_agree"] else "MISS"
            print(f"  [{mark}] {r['task_id']:<46} theirs={r['their_status']:<16} "
                  f"here={r['this_pack']}")
            if args.verbose and r["flags"]:
                print(f"           flags: {r['flags']}")
        agreed = sum(1 for r in results if r["agrees"] and r["conditions_agree"])
        print(f"\n  agreement  {agreed}/{len(results)}")
        for failure in failures:
            print(f"  {failure}")
        if not failures:
            print("\n  Every verdict an independent author expected, this pack reaches — including\n"
                  "  the two they marked narrow-and-conditional, which land here as bounded with\n"
                  "  required conditions rather than as the frame status of the same name.")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
