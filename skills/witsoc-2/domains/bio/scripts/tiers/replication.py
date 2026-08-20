#!/usr/bin/env python3
"""Replication tier — does the effect survive a source that shares nothing with the first?

Ceiling CHECKED_BOUNDED at the frame level; it is what grants the pack's
`CHECKED_REPRODUCED` refinement. Adversarial: it cannot be argued into a pass,
because either a second, independently produced dataset shows the same thing or
it does not.

The word doing the work is *independent*. Replication means a different source
and a separately pinned analysis path. It does not mean:

- more cells from the same donors,
- a second screen of the same cell line in the same lab,
- the same data re-analysed with a different tool,
- or the same analysis re-run with a different seed.

Each of those is worth doing and none of them is replication, so this tier
refuses them explicitly rather than accepting them quietly. Two bundles that
share a dataset accession are one experiment described twice.

Agreement is checked on sign first and magnitude second. A replication that
reverses the sign is a contradiction, not a weak confirmation — and it is
reported as one, because the alternative is a literature where every effect is
"broadly consistent".

Usage:  replication.py <primary.json> --replicate <second.json> --claim <claim.json>
Exit:   0 replicated, 1 not replicated, 2 error, 3 not runnable
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import biolib as bl  # noqa: E402

HERE = Path(__file__).resolve().parent


def run_executable(bundle: Path, claim: Path, seed: int) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HERE / "executable.py"), str(bundle), "--claim", str(claim),
         "--seed", str(seed)],
        capture_output=True, text=True, timeout=900)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"verdict": "error", "detail": (proc.stdout + proc.stderr)[:800]}


def accession(bundle: dict) -> str:
    sources = bundle.get("source_ledger") or []
    ids = sorted({(s.get("accession") or "").strip() for s in sources
                  if isinstance(s, dict) and s.get("accession")})
    return "|".join(ids)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("primary")
    ap.add_argument("--replicate", required=True)
    ap.add_argument("--claim", required=True)
    args = ap.parse_args()

    try:
        primary = bl.read_json(args.primary)
        replicate = bl.read_json(args.replicate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error", "detail": str(exc)}))
        return 2

    problems: list[str] = []

    a, b = accession(primary), accession(replicate)
    if not a or not b:
        problems.append("one or both bundles pin no dataset accession, so their independence "
                        "cannot be established and this tier has nothing to check")
    elif a == b:
        problems.append(
            f"both bundles pin the same source ({a}). This is the same experiment analysed "
            "twice; it can raise confidence in the analysis and cannot raise confidence in "
            "the biology")

    pa = (primary.get("preregistration") or {}).get("sha256")
    pb = (replicate.get("preregistration") or {}).get("sha256")
    if pa and pb and pa == pb:
        problems.append(
            "both bundles share one preregistration hash — the analysis path was not "
            "independently pinned, so a shared analysis error would reproduce perfectly")

    first = run_executable(Path(args.primary), Path(args.claim), seed=0)
    second = run_executable(Path(args.replicate), Path(args.claim), seed=17)
    for label, result in (("primary", first), ("replicate", second)):
        if result.get("verdict") == "error":
            print(json.dumps({"tier": "replication", "verdict": "error",
                              "detail": f"{label}: {result.get('detail')}"}, indent=2))
            return 2
        if result.get("verdict") == "not_run":
            print(json.dumps({
                "tier": "replication", "verdict": "not_run", "max_status": "CONJECTURE",
                "problems": [f"{label} bundle is not runnable at the executable tier, so there "
                             "is nothing to replicate"] + result.get("problems", [])}, indent=2))
            return 3

    ea = first.get("recomputed", {}).get("difference_in_unit_means")
    eb = second.get("recomputed", {}).get("difference_in_unit_means")
    ia = (first.get("recomputed", {}) or {}).get("interval") or {}
    ib = (second.get("recomputed", {}) or {}).get("interval") or {}
    agreement = {}
    if ea is not None and eb is not None:
        same_sign = (ea > 0) == (eb > 0) and ea != 0 and eb != 0
        ratio = abs(eb / ea) if ea else float("inf")
        agreement = {"primary_effect": ea, "replicate_effect": eb,
                     "same_sign": same_sign, "magnitude_ratio": ratio}

        # Overlapping intervals is the question a ratio only gestures at. Two
        # point estimates differing by 3x may be perfectly compatible if both
        # are imprecise, and two differing by 1.2x may be incompatible if both
        # are tight. A magnitude ratio cannot tell those apart and an interval
        # comparison can, which is why the ratio alone was the wrong test.
        if ia.get("ran") and ib.get("ran"):
            overlap = not (ia["upper"] < ib["lower"] or ib["upper"] < ia["lower"])
            agreement["intervals"] = {
                "primary": [ia["lower"], ia["upper"]],
                "replicate": [ib["lower"], ib["upper"]],
                "overlap": overlap,
                "reading": ("the intervals overlap, so the two estimates are compatible — which "
                            "is the question, and a ratio of point estimates cannot answer it"
                            if overlap else
                            "the intervals do not overlap. The replication contradicts the "
                            "primary at the precision both were measured to, and that is a "
                            "finding rather than a caveat"),
            }
            if not overlap:
                problems.append(
                    f"the intervals do not overlap: primary [{ia['lower']:.4g}, "
                    f"{ia['upper']:.4g}] against replicate [{ib['lower']:.4g}, {ib['upper']:.4g}]. "
                    "Two estimates that exclude each other are not a replication with caveats")
        else:
            agreement["intervals"] = {
                "ran": False,
                "reading": ("no interval on one side or both, so compatibility was judged by the "
                            "ratio of point estimates alone — which cannot distinguish two "
                            "imprecise estimates that agree from two precise ones that do not")}
        if not same_sign:
            problems.append(
                f"the effects point in opposite directions ({ea:.4g} against {eb:.4g}). That is "
                "a contradiction to record in the ledger, not a replication with caveats")
        elif not 0.25 <= ratio <= 4.0:
            problems.append(
                f"same sign, but the magnitudes differ by {ratio:.2f}x. The direction replicates "
                "and the effect size does not; a claim about magnitude is not supported")

    if first.get("verdict") != "pass" or second.get("verdict") != "pass":
        problems.append("at least one bundle does not pass the executable tier on its own; "
                        "replication cannot rescue a result that was never established")

    verdict = "fail" if problems else "pass"
    print(json.dumps({
        "tier": "replication",
        "verdict": verdict,
        "max_status": "CHECKED_BOUNDED",
        "status_refinement": "CHECKED_REPRODUCED" if verdict == "pass" else None,
        "independence": {"primary_accession": a, "replicate_accession": b,
                         "separate_preregistration": bool(pa and pb and pa != pb)},
        "agreement": agreement,
        "problems": problems,
        "failure_class": "replication_failed" if problems else None,
    }, indent=2, default=str))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
