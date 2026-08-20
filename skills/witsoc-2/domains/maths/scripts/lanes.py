#!/usr/bin/env python3
"""Lane catalogue, ranking, and worker allocation.

A lane is a line of attack on the frozen target. Explorer builds a portfolio of
them; this module scores them and splits the available workers across them.

Ranking is advisory. The constraints at the bottom are not: they exist because a
portfolio optimized purely on score reliably collapses into "generate more
ideas", which is the cheapest thing to score well and the least likely to close
anything.

Usage:
    lanes.py list
    lanes.py rank --state <run_state.json> [--workers N] [--json]

Exit: 0 always (advisory); 2 on IO error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import LANE_WEIGHTS, clamp, weighted  # noqa: E402

# The lanes. `role` says which of the three frame roles executes it.
LANES = [
    {
        "name": "statement-freeze",
        "role": "explorer",
        "risk": "low",
        "outputs": ["frozen_target", "source_status_summary"],
        "why": "Nothing downstream is valid without it. Always first.",
    },
    {
        "name": "counterexample-pressure",
        "role": "explorer",
        "risk": "medium",
        "outputs": ["counterexample_search_report", "bounds_searched"],
        "why": "A counterexample at n=4 saves the whole campaign. Keep it alive "
               "while proving, not only before.",
    },
    {
        "name": "barrier-decomposition",
        "role": "researcher",
        "risk": "medium",
        "outputs": ["obligation_dag", "barrier_map"],
        "why": "Turns one hard target into named sub-obligations.",
    },
    {
        "name": "literature-grounding",
        "role": "explorer",
        "risk": "low",
        "outputs": ["source_ledger", "premise_availability"],
        "why": "Cheapest way to discover the problem is solved, or that the "
               "premise you need does not exist.",
    },
    {
        "name": "idea-generation",
        "role": "researcher",
        "risk": "high",
        "outputs": ["candidate_lemmas", "conjectures"],
        "why": "Necessary but unbounded. Capped, because it scores well and "
               "closes little.",
    },
    {
        "name": "skeptic-synthesis",
        "role": "researcher",
        "risk": "low",
        "outputs": ["skeptic_review", "synthesis"],
        "why": "Gates product promotion. Nothing is promoted without it.",
    },
    {
        "name": "formalizable-rungs",
        "role": "generator",
        "risk": "medium",
        "outputs": ["artifact", "formalization_scorecard"],
        "requires_artifact_request": True,
        "why": "Only when an artifact was actually asked for.",
    },
]

# Feature defaults, then keyword overrides. Deliberately coarse: this orders a
# handful of lanes, and precision here would be false precision.
DEFAULTS = {
    "cheapness": 0.75, "verifier_friendliness": 0.35, "expected_evidence_gain": 0.45,
    "uncertainty_reduction": 0.45, "novelty_potential": 0.35, "target_relevance": 0.55,
    "repeat_risk": 0.05,
}
OVERRIDES = {
    "counterexample": {"expected_evidence_gain": 0.72, "uncertainty_reduction": 0.75,
                       "cheapness": 0.70},
    "barrier": {"target_relevance": 0.80, "uncertainty_reduction": 0.72,
                "novelty_potential": 0.55},
    "formal": {"verifier_friendliness": 0.82, "expected_evidence_gain": 0.70},
    "idea": {"novelty_potential": 0.82, "expected_evidence_gain": 0.45, "cheapness": 0.45},
    "skeptic": {"uncertainty_reduction": 0.72, "verifier_friendliness": 0.60,
                "expected_evidence_gain": 0.55},
    "literature": {"uncertainty_reduction": 0.68, "target_relevance": 0.65,
                   "cheapness": 0.60},
    "freeze": {"target_relevance": 0.90, "cheapness": 0.90, "expected_evidence_gain": 0.30},
}

IDEA_GENERATION_CAP = 0.40   # of total workers


def features_for(lane: dict, state: dict) -> tuple[dict, list[str]]:
    feats = dict(DEFAULTS)
    reasons: list[str] = []
    name = lane["name"].lower()
    for key, override in OVERRIDES.items():
        if key in name:
            feats.update(override)
            reasons.append(f"matched profile '{key}'")

    if state.get("target_is_open"):
        if "counterexample" in name:
            feats["target_relevance"] = clamp(feats["target_relevance"] + 0.15)
            reasons.append("+0.15 target relevance: open target rewards refutation")
    if state.get("artifact_requested") and ("formal" in name or "artifact" in name):
        feats["target_relevance"] = clamp(feats["target_relevance"] + 0.15)
        reasons.append("+0.15 target relevance: an artifact was requested")

    tried = {t.lower() for t in state.get("lanes_already_run", [])}
    if lane["name"].lower() in tried:
        feats["repeat_risk"] = 0.60
        reasons.append("repeat risk 0.60: this lane already ran without closing")
    return feats, reasons


def rank(state: dict) -> list[dict]:
    ranked = []
    for lane in LANES:
        if lane.get("requires_artifact_request") and not state.get("artifact_requested"):
            continue
        feats, reasons = features_for(lane, state)
        score = weighted(feats, LANE_WEIGHTS)
        ranked.append({
            "name": lane["name"], "role": lane["role"], "risk": lane["risk"],
            "outputs": lane["outputs"], "score": round(score, 4),
            "features": {k: round(v, 3) for k, v in feats.items()},
            "reasons": reasons or ["defaults only"],
            "confidence_would_drop_if": (
                f"{lane['name']} runs once and returns no new evidence, or its "
                "outputs duplicate a lane already recorded"
            ),
        })
    return sorted(ranked, key=lambda r: (-r["score"], r["name"]))


def allocate(ranked: list[dict], workers: int, artifact_requested: bool) -> dict:
    """Proportional split, then the constraints that stop it degenerating."""
    if workers <= 0 or not ranked:
        return {"allocation": {}, "constraints_applied": []}

    total = sum(r["score"] for r in ranked) or 1.0
    alloc = {r["name"]: max(0, round(workers * r["score"] / total)) for r in ranked}

    # Repair rounding so the split sums exactly.
    while sum(alloc.values()) > workers:
        biggest = max(alloc, key=lambda k: alloc[k])
        alloc[biggest] -= 1
    while sum(alloc.values()) < workers:
        alloc[ranked[0]["name"]] += 1

    applied: list[str] = []
    names = {r["name"] for r in ranked}

    def donate_to(target: str, note: str) -> None:
        donors = sorted((k for k in alloc if k != target and alloc[k] > 1),
                        key=lambda k: alloc[k], reverse=True)
        if donors:
            alloc[donors[0]] -= 1
            alloc[target] += 1
            applied.append(note)

    # A campaign with no refutation lane will happily prove a false statement.
    if workers >= 2 and "counterexample-pressure" in names and \
            alloc.get("counterexample-pressure", 0) < 1:
        donate_to("counterexample-pressure",
                  "guaranteed >=1 counterexample-pressure worker: a campaign with no "
                  "refutation lane can spend everything establishing something false")

    # Nothing is promoted without a skeptic pass, so one must be resourced.
    if workers >= 3 and "skeptic-synthesis" in names and \
            alloc.get("skeptic-synthesis", 0) < 1:
        donate_to("skeptic-synthesis",
                  "guaranteed >=1 skeptic-synthesis worker: promotion is gated on it")

    if artifact_requested and "formalizable-rungs" in names and \
            alloc.get("formalizable-rungs", 0) < 1:
        donate_to("formalizable-rungs",
                  "guaranteed >=1 formalizable-rungs worker: an artifact was requested")

    # Idea generation scores well and closes little. Cap it.
    cap = max(1, int(IDEA_GENERATION_CAP * workers))
    if alloc.get("idea-generation", 0) > cap:
        excess = alloc["idea-generation"] - cap
        alloc["idea-generation"] = cap
        alloc[ranked[0]["name"]] += excess
        applied.append(
            f"idea-generation capped at {cap} ({int(IDEA_GENERATION_CAP*100)}% of "
            f"{workers}); {excess} worker(s) moved to '{ranked[0]['name']}'"
        )

    return {"allocation": {k: v for k, v in alloc.items() if v},
            "constraints_applied": applied}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("rank")
    r.add_argument("--state", help="run state JSON (target_is_open, artifact_requested, "
                                   "lanes_already_run)")
    r.add_argument("--workers", type=int, default=0)
    r.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "list":
        for lane in LANES:
            gate = "  (only when an artifact is requested)" if lane.get(
                "requires_artifact_request") else ""
            print(f"  {lane['name']:<26} {lane['role']:<11} risk={lane['risk']}{gate}")
            print(f"      {lane['why']}")
        return 0

    state = {}
    if args.state:
        try:
            state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    ranked = rank(state)
    result = {"ranked_lanes": ranked}
    if args.workers:
        result.update(allocate(ranked, args.workers, bool(state.get("artifact_requested"))))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Ranked lanes (advisory — ordering only, never acceptance):\n")
        for entry in ranked:
            print(f"  {entry['score']:.3f}  {entry['name']:<26} [{entry['role']}]")
            for reason in entry["reasons"]:
                print(f"           {reason}")
        if args.workers:
            print(f"\nAllocation over {args.workers} worker(s):")
            for name, count in result["allocation"].items():
                print(f"  {count:>2}  {name}")
            for note in result["constraints_applied"]:
                print(f"\n  constraint: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
