#!/usr/bin/env python3
"""Executable tier — recompute the effect from the pinned data.

Ceiling CHECKED_BOUNDED, adversarial. This is the only tier in the pack whose
pass is evidence rather than eligibility, and it earns that by never reading a
reported number. The bundle may say the effect was large and the p-value small;
this tier recomputes both from the metadata table and ignores what was claimed.
A pipeline that reports its own verdict is not a check, it is a claim with extra
steps.

Four things happen, in this order, and any of them can end it:

1. PINNING. Every declared input is re-hashed. A preregistration whose hash no
   longer matches its file was edited after the fact, which is the specific move
   that turns an exploratory result into a confirmatory one on paper.
2. AGGREGATION. Observations collapse to one value per experimental unit before
   anything is tested. This is the fix for pseudoreplication and it is four
   lines; the hard part was deciding the unit, which the denominator tier did.
3. TEST. A stratified permutation test on unit-level means. Labels are shuffled
   within stratum, so the batch structure survives the shuffle and only the
   treatment assignment is destroyed. Shuffling across batches would break the
   confounding too, and make a confounded result look clean.
4. REFUTE. The permutation null IS the refute-attempt gate, and it is joined by
   a negative-control contrast: comparing two control groups against each other
   must produce nothing. A pipeline that finds an effect between two halves of
   the control condition is measuring its own structure, and every result it has
   ever produced is worthless until that is fixed. This is the check most likely
   to fail on a real, sincere, subtly broken analysis.

Usage:  executable.py <bundle.json> --claim <claim.json> [--iterations N] [--seed N]
Exit:   0 pass, 1 fail, 2 error, 3 not runnable (NOT_RUN — a gap, never a pass)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

DEFAULT_ALPHA = 0.05


def resolve(bundle_path: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    return (bundle_path.parent / rel).resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--iterations", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    bundle_path = Path(args.bundle)
    try:
        bundle = bl.read_json(bundle_path)
        claim = bl.read_json(args.claim)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)}))
        return 2

    data = bundle.get("data") or {}
    required = ["metadata_csv", "value_column", "unit_column", "label_column",
                "treatment_label", "control_label"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        print(json.dumps({
            "tier": "executable", "verdict": "not_run", "max_status": "CONJECTURE",
            "problems": [f"bundle.data is missing {missing}; there is nothing to recompute. "
                         "Reported numbers are not evidence here — this tier only trusts what "
                         "it can compute itself"]}, indent=2))
        return 3

    csv_path = resolve(bundle_path, data["metadata_csv"])
    if csv_path is None or not csv_path.exists():
        print(json.dumps({
            "tier": "executable", "verdict": "not_run", "max_status": "CONJECTURE",
            "problems": [f"metadata_csv {data['metadata_csv']!r} not found"]}, indent=2))
        return 3

    problems: list[str] = []
    notes: list[str] = []

    # 1. Pinning.
    inputs = []
    for label, rel in [("metadata_csv", data.get("metadata_csv")),
                       ("preregistration", (bundle.get("preregistration") or {}).get("path"))]:
        path = resolve(bundle_path, rel)
        if path and path.exists():
            inputs.append({"input": label, "path": rel, "sha256": bl.sha256_file(path)})

    prereg = bundle.get("preregistration") or {}
    prereg_path = resolve(bundle_path, prereg.get("path"))
    if not prereg:
        problems.append(
            "no preregistration. Without one, the primary endpoint and the alpha are whatever "
            "the analysis found, and the test below is descriptive rather than confirmatory")
    elif prereg_path and prereg_path.exists():
        live = bl.sha256_file(prereg_path)
        if prereg.get("sha256") and prereg["sha256"] != live:
            problems.append(
                f"preregistration hash mismatch: declared {prereg['sha256'][:16]}..., file is "
                f"{live[:16]}.... The plan was edited after it was registered")
    elif prereg.get("sha256"):
        notes.append("preregistration hash declared but the file is not in the bundle; "
                     "the hash cannot be checked and so does not count for anything")

    alpha = float(prereg.get("alpha", DEFAULT_ALPHA))

    # 2. Aggregation.
    _, rows = bl.read_csv(csv_path)
    treatment, control = data["treatment_label"], data["control_label"]
    units = bl.pseudobulk(rows, data["unit_column"], data["value_column"], data["label_column"])
    mixed = [u["unit"] for u in units if u["label"] == "MIXED"]

    # A unit appearing in BOTH arms has no single arm to belong to, and the first
    # version excluded it — which for a fully crossed design excludes everything.
    # The donor-replicated population class REQUIRES donors crossed with the
    # condition, so the pack was demanding a design it could not analyse.
    #
    # A crossed design is not a weaker between-unit design. It is a stronger
    # paired one: each unit is its own control, the between-donor variation that
    # dominates this data cancels, and the estimand is the mean within-unit
    # difference tested by sign flip.
    pairs, incomplete = bl.paired_units(rows, data["unit_column"], data["value_column"],
                                        data["label_column"], treatment, control)
    if mixed and len(pairs) >= 2:
        differences = [p["difference"] for p in pairs]
        null = bl.sign_flip_p(differences, iterations=args.iterations,
                              seed=args.seed)
        effect = bl.mean(differences)
        result = {
            "tier": "executable", "design": "paired",
            "verdict": "pass" if (null["p_value"] is not None
                                  and null["p_value"] <= 0.05) else "fail",
            "max_status": "CHECKED_BOUNDED",
            "units": {"paired": len(pairs), "incomplete": incomplete},
            "effect": round(effect, 6),
            "refute_attempt": {"gate_name": "permutation-null",
                               "discharged_by": "adversarial_tier",
                               "outcome": ("survived" if (null["p_value"] or 1) <= 0.05
                                           else "broken"),
                               "perturbation": "signs flipped within unit; the exact null for a "
                                               "paired design"},
            "null": null,
            "notes": notes + [
                f"{len(pairs)} unit(s) appear in both arms, so this is analysed as a PAIRED "
                "design: one within-unit difference each, tested by sign flip. Excluding them "
                "as MIXED would have discarded the whole design the claim class requires.",
                f"the smallest attainable two-sided p at {len(pairs)} units is "
                f"{null['smallest_attainable_p']:.4f} — a design limit, stated before the "
                "number is read"],
        }
        if incomplete:
            result["notes"].append(
                f"{len(incomplete)} unit(s) appear in only one arm and contribute nothing to a "
                "paired contrast: " + ", ".join(incomplete[:5]))
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "pass" else 1

    if mixed:
        notes.append(
            f"{len(mixed)} unit(s) contain more than one condition and fewer than two of them "
            "carry both arms, so no paired contrast exists either. Their unit mean averages "
            "across the contrast, so they are excluded from the between-unit test")
    usable = [u for u in units if u["label"] != "MIXED"]

    values = [u["mean"] for u in usable]
    labels = [u["label"] for u in usable]
    strata = None
    if data.get("stratum_column"):
        by_unit = {}
        for row in rows:
            key = (row.get(data["unit_column"]) or "").strip()
            if key:
                by_unit.setdefault(key, (row.get(data["stratum_column"]) or "").strip())
        strata = [by_unit.get(u["unit"], "") for u in usable]

    n_t = labels.count(treatment)
    n_c = labels.count(control)
    if n_t < 2 or n_c < 2:
        print(json.dumps({
            "tier": "executable", "verdict": "not_run", "max_status": "CONJECTURE",
            "units": {"treatment": n_t, "control": n_c},
            "problems": [
                f"{n_t} treatment and {n_c} control units after aggregation. A between-unit test "
                "needs at least two of each; with fewer, the smallest p-value the permutation "
                "distribution can produce is larger than any sensible alpha. This is a design "
                "limit, not a computation that failed"]}, indent=2))
        return 3

    # 3. Test.
    test = bl.permutation_p(values, labels, treatment, control,
                            iterations=args.iterations, seed=args.seed, strata=strata)
    interval = bl.bootstrap_interval(values, labels, treatment, control,
                                     iterations=min(args.iterations, 4000), seed=args.seed,
                                     strata=strata)
    effect = test["observed_difference"]
    d = bl.cohens_d([v for v, l in zip(values, labels) if l == treatment],
                    [v for v, l in zip(values, labels) if l == control])

    smallest_possible = 1.0 / (args.iterations + 1)
    if test["p_value"] > alpha:
        problems.append(
            f"recomputed permutation p = {test['p_value']:.4f} at the unit level, against a "
            f"preregistered alpha of {alpha}. Whatever the bundle reports, this design does not "
            "distinguish the effect from label assignment")

    # An interval that crosses zero and a p-value below alpha disagree, and the
    # disagreement is information rather than an inconsistency to smooth over.
    if interval.get("ran") and interval["crosses_zero"] and test["p_value"] <= alpha:
        notes.append(
            f"the interval [{interval['lower']:.4g}, {interval['upper']:.4g}] includes zero while "
            f"the permutation p is {test['p_value']:.4f}. The test and the bound disagree, which "
            "with few units usually means the point estimate is unstable — report both")

    claimed_direction = (claim.get("claimed_effect") or {}).get("direction", "").lower()
    observed_direction = "increase" if effect > 0 else "decrease" if effect < 0 else "none"
    if claimed_direction in {"increase", "decrease"} and claimed_direction != observed_direction:
        problems.append(
            f"the claim says {claimed_direction}, the recomputation says {observed_direction} "
            f"(difference {effect:.4g}). A result in the wrong direction refutes the claim as "
            "stated rather than partially supporting it")

    # 4. Refute: the negative control contrast.
    negative = {"ran": False}
    nc = data.get("negative_control") or {}
    if nc.get("unit_column") and nc.get("label_column") and len(nc.get("labels") or []) == 2:
        a, b = nc["labels"]
        # Split the control condition against itself, at a finer unit so the
        # comparison has enough groups to be able to fail. A negative control
        # whose smallest achievable p-value exceeds alpha cannot detect anything
        # and is worse than none, because it looks like a passed check.
        nc_units = [u for u in bl.pseudobulk(rows, nc["unit_column"], data["value_column"],
                                             nc["label_column"]) if u["label"] in {a, b}]
        negative = bl.permutation_p([u["mean"] for u in nc_units],
                                    [u["label"] for u in nc_units], a, b,
                                    iterations=args.iterations, seed=args.seed + 1)
        negative["units"] = len(nc_units)
        floor = 1.0 / (args.iterations + 1)
        if negative.get("ran") and negative.get("smallest_possible", floor) > alpha:
            notes.append("the negative control has too few units to reach alpha; it cannot fail, "
                         "so its pass carries no information")
        if negative.get("ran") and negative["p_value"] <= alpha:
            problems.append(
                f"NEGATIVE CONTROL FAILED: comparing {a!r} against {b!r} — two groups that "
                f"differ by nothing — gives p = {negative['p_value']:.4f}. The pipeline finds "
                "structure where there is none, so its positive result carries no information "
                "either. Fix this before interpreting anything above")
    else:
        notes.append(
            "no negative_control declared, so the pipeline was never asked to find "
            "nothing. Splitting the control condition in half and testing it against itself is "
            "the cheapest audit available and it belongs in every bundle")

    verdict = "fail" if problems else "pass"
    result = {
        "tier": "executable",
        "verdict": verdict,
        "max_status": "CHECKED_BOUNDED",  # what a pass here could support; the outcome is `verdict`
        "recomputed": {
            "unit_column": data["unit_column"],
            "units_treatment": n_t,
            "units_control": n_c,
            "observations": len(rows),
            "difference_in_unit_means": effect,
            "cohens_d": d,
            "permutation": test,
            "interval": interval,
            "smallest_reportable_p": smallest_possible,
            "alpha": alpha,
        },
        "negative_control": negative,
        "refute_attempt": {
            "gate_name": "permutation-null",
            "method": "labels shuffled within stratum on unit-level means; the observed "
                      "difference must sit outside the resulting null",
            "outcome": ("survived" if verdict == "pass" else "broken"),
        },
        "inputs": inputs,
        "unit_table": usable,
        "notes": notes,
        "problems": problems,
        "failure_class": ("negative_control_failure" if any("NEGATIVE CONTROL" in p for p in problems)
                          else "effect_not_distinguishable" if problems else None),
    }
    print(json.dumps(result, indent=2, default=str))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
