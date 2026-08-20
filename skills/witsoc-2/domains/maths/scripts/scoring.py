#!/usr/bin/env python3
"""Shared scoring surface for the maths pack.

Every weight the pack uses to *order* work lives here, in one file, so tuning is
a single-surface change rather than an archaeology exercise.

Nothing here decides truth. These scores rank attention only: they choose what
to look at next and in what order. A score can waste effort; it can never make a
claim true, upgrade a status, or close an obligation. That separation is the
frame's rule and this module is the part of the pack most likely to erode it, so
it is stated at the top.

Every score returns a reason list alongside the number. A score with no reason
is not reviewable, and one with no falsifiable `confidence_would_drop_if` is not
calibrated.
"""

from __future__ import annotations

# --- lane ranking -----------------------------------------------------------
LANE_WEIGHTS = {
    "expected_evidence_gain": 0.30,
    "target_relevance": 0.20,
    "verifier_friendliness": 0.15,
    "uncertainty_reduction": 0.15,
    "novelty_potential": 0.10,
    "cheapness": 0.10,
    "repeat_risk": -0.25,
}

# --- product selection ------------------------------------------------------
PRODUCT_WEIGHTS = {
    "evidence_strength": 0.35,
    "target_fidelity": 0.25,
    "dependency_path_quality": 0.15,
    "novelty": 0.10,
    "formalization_readiness": 0.10,
    "user_value": 0.05,
    "remaining_gap_penalty": -0.30,
}

# --- barrier selection ------------------------------------------------------
BARRIER_WEIGHTS = {
    "dependency_centrality": 0.35,
    "unlock_value": 0.25,
    "formalization_readiness": 0.15,
    "evidence_available": 0.15,
    "theorem_connectivity": 0.10,
    "repeat_failure_risk": -0.25,
}

# --- mutation selection -----------------------------------------------------
MUTATION_WEIGHTS = {
    "gap_class_match": 0.30,
    "one_axis_clarity": 0.20,
    "expected_unlock": 0.20,
    "verifier_friendliness": 0.15,
    "novelty_against_failures": 0.15,
    "used_axis_penalty": -0.35,
}

# --- attackability (target selection) ---------------------------------------
# Weights sum to 1.0 before the boundary factor is applied.
ATTACKABILITY_WEIGHTS = {
    "finite_reduction": 0.30,
    "formalization": 0.20,
    "technique_density": 0.10,
    "literature": 0.10,
    "computation_domain": 0.10,
    "literature_scarcity": 0.10,
    "variational": 0.10,
}

# --- rung scoring -----------------------------------------------------------
RUNG_WEIGHTS = {"formal": 0.32, "attack": 0.28, "novelty": 0.18, "value": 0.22}

# --- how strong a status is as evidence for reporting -----------------------
# Ordering only. It never licenses a status; the transition lattice in status.py
# and the frame's admission gate decide what a claim may be called.
STATUS_STRENGTH = {
    "FORMAL_SOLVE": 1.00,
    "VERIFIED_LEAN": 0.95,
    "VERIFIED_WIT": 0.90,
    "VERIFIED": 0.90,
    "VERIFIED_PARTIAL": 0.82,
    "CHECKED_SYMBOLIC": 0.74,
    "CHECKED_BOUNDED": 0.72,
    "CHECKED": 0.70,
    "CONDITIONAL": 0.62,
    "PARTIAL": 0.58,
    "REDUCTION": 0.55,
    "COUNTEREXAMPLE": 0.52,
    "OBSTRUCTION": 0.50,
    "PROVED_SKETCH": 0.40,
    "FAILED_ATTEMPT": 0.34,
    "CONJECTURE": 0.22,
    "OPEN": 0.05,
    "GAP": 0.03,
    "REJECTED": 0.00,
}

REPORTABILITY = [
    "verified_partial_or_better",
    "checked_bounded",
    "conditional",
    "partial_progress",
    "obstruction_or_counterexample",
    "failed_attempt_with_barrier",
    "weak_candidate",
]

# The eleven method families. Diversity is counted over these: two attempts in
# one family are one attempt.
METHOD_FAMILIES = [
    "extremal",
    "probabilistic",
    "algebraic_spectral",
    "construction",
    "induction_descent",
    "compactness_model_theory",
    "computational",
    "formalization_first",
    "duality",
    "analytic_asymptotic",
    "reduction",
]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def weighted(features: dict[str, float], weights: dict[str, float]) -> float:
    """Dot product over the named weights, clamped to [0, 1]."""
    return clamp(sum(features.get(k, 0.0) * w for k, w in weights.items()))


def repeat_risk(node: dict, gap_feedback_ids: set[str], failed_approaches: list) -> float:
    """How likely this is a repeat of something already tried.

    A node already classified in gap feedback is the strongest signal — it
    failed, was diagnosed, and has not changed since.
    """
    if node.get("mutation_applied"):
        return 0.05
    if node.get("id") in gap_feedback_ids:
        return 0.75
    if failed_approaches:
        return 0.45
    return 0.15


def evidence_strength(status: str, evidence: list | None = None,
                      has_artifact_hash: bool = False) -> float:
    """Status strength, nudged by what actually backs it."""
    score = STATUS_STRENGTH.get(str(status).upper(), 0.0)
    text = " ".join(str(e) for e in (evidence or [])).lower()
    if any(word in text for word in ("receipt", "kernel", "certificate", "exhaustive")):
        score += 0.18
    if has_artifact_hash:
        score += 0.10
    return clamp(score)


def reportability(status: str, has_barrier: bool = False) -> str:
    """Map a status to how strongly the run may be described."""
    upper = str(status).upper()
    if upper in {"VERIFIED", "VERIFIED_WIT", "VERIFIED_LEAN", "FORMAL_SOLVE",
                 "VERIFIED_PARTIAL"}:
        return "verified_partial_or_better"
    if upper in {"CHECKED_BOUNDED", "CHECKED", "CHECKED_SYMBOLIC"}:
        return "checked_bounded"
    if upper == "CONDITIONAL":
        return "conditional"
    if upper == "PARTIAL":
        return "partial_progress"
    if upper in {"COUNTEREXAMPLE", "OBSTRUCTION", "REDUCTION"}:
        return "obstruction_or_counterexample"
    if upper == "FAILED_ATTEMPT" and has_barrier:
        return "failed_attempt_with_barrier"
    return "weak_candidate"
