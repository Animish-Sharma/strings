"""Typed, bounded Explorer to Researcher discovery episodes."""

from __future__ import annotations

import copy
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from .canonical import digest_value, seal_packet, verify_packet_seal
from . import contracts, exploration, kernel, loop_messages, reasoning, target_semantics


EPISODE_SCHEMA = "witsoc.research-episode.v1"
LEGACY_DELTA_SCHEMA = "witsoc.research-delta.v1"
DELTA_SCHEMA = "witsoc.research-delta.v2"
DELTA_SCHEMAS = {LEGACY_DELTA_SCHEMA, DELTA_SCHEMA}
ROOT = Path(__file__).resolve().parents[2]
LANES = {"RETRIEVE", "REFUTE", "REDUCE", "CONSTRUCT", "TRANSFER", "MEASURE", "VERIFY"}
OUTCOMES = {
    "ADMITTED_PRODUCT", "CANDIDATE_PRODUCT", "STRICT_REDUCTION", "FALSIFICATION",
    "TARGET_FALSIFIED", "ROUTE_REFUTED", "NEW_OBSTRUCTION", "METHOD_BARRIER",
    "CORE_SHARPENED", "POSITIVE_SIGNAL", "NO_PROGRESS", "NO_DELTA",
    "SESSION_CHECKPOINT", "WAITING_EXTERNAL",
}
# Only evidence that the exact route objective is false closes that route. A
# barrier or sharper core is a continuation signal, not evidence that the
# surrounding open problem has been exhausted.
EXHAUSTING = {"ROUTE_REFUTED"}
REFRAME_OUTCOMES = {
    "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED",
}
CHECKPOINT_OUTCOMES = {"SESSION_CHECKPOINT", "WAITING_EXTERNAL"}
ROUTE_FIELDS = {
    "method_family", "mechanism", "structural_object", "required_result",
    "target_effect", "assumptions",
}
FEATURE_WEIGHTS = {
    "target_leverage": 0.28,
    "expected_information_gain": 0.20,
    "checkability": 0.17,
    "reversibility": 0.12,
    "novelty": 0.11,
    "transfer_value": 0.07,
    "cost": -0.10,
    "recoupling_risk": -0.25,
}
OUTCOME_VALUE = {
    "ADMITTED_PRODUCT": 1.0,
    "CANDIDATE_PRODUCT": 0.8,
    "STRICT_REDUCTION": 0.85,
    "FALSIFICATION": 0.7,
    "TARGET_FALSIFIED": 0.7,
    "ROUTE_REFUTED": 0.65,
    "NEW_OBSTRUCTION": 0.62,
    "METHOD_BARRIER": 0.55,
    "CORE_SHARPENED": 0.78,
    "POSITIVE_SIGNAL": 0.58,
    "SESSION_CHECKPOINT": 0.1,
    "WAITING_EXTERNAL": 0.1,
    "NO_DELTA": 0.0,
    "NO_PROGRESS": 0.0,
}
TOKEN_ALIASES = {
    "approach": "method",
    "technique": "method",
    "strategy": "method",
    "demonstrate": "derive",
    "establish": "derive",
    "show": "derive",
    "proves": "derive",
    "proving": "derive",
    "needed": "require",
    "needs": "require",
    "required": "require",
    "requires": "require",
    "mapping": "transfer",
    "mapped": "transfer",
    "translate": "transfer",
    "translation": "transfer",
    "transformation": "transfer",
    "countermodel": "falsify",
    "contradiction": "falsify",
    "refutation": "falsify",
    "reduction": "reduce",
    "reducing": "reduce",
}
FILLER_TOKENS = {
    "a", "an", "the", "this", "that", "these", "those", "by", "via",
    "using", "use", "with", "for", "of", "on", "at", "as",
}
RELATION_TOKENS = {
    "after", "before", "decrease", "from", "if", "imply", "increase",
    "lower", "not", "only", "preserve", "require", "to", "under",
    "unless", "upper", "without",
}


class DiscoveryError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise DiscoveryError(f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiscoveryError(f"{label} must be a number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise DiscoveryError(f"{label} must be a finite number in [0, 1]")
    return result


def _semantic_tokens(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"\\(?:operatorname|mathrm|mathbf|mathcal)\s*\{([^{}]+)\}", r" \1 ", text)
    text = text.replace("->", " imply ").replace("=>", " imply ")
    tokens = re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)?", text)
    return [TOKEN_ALIASES.get(token, token) for token in tokens if token not in FILLER_TOKENS]


def _semantic_field(value: str) -> dict[str, Any]:
    tokens = _semantic_tokens(value)
    if not tokens:
        raise DiscoveryError("semantic route field has no identifying terms")
    relations = [
        " ".join(tokens[max(0, index - 2):index + 3])
        for index, token in enumerate(tokens)
        if token in RELATION_TOKENS
    ]
    return {"terms": sorted(tokens), "relations": relations}


def canonical_route(route: Mapping[str, Any]) -> dict[str, Any]:
    _closed(route, ROUTE_FIELDS, "semantic route")
    for field in ROUTE_FIELDS - {"assumptions"}:
        if not isinstance(route[field], str) or not route[field].strip():
            raise DiscoveryError(f"semantic route {field} is empty")
    if not isinstance(route["assumptions"], list) or any(
        not isinstance(item, str) or not item.strip() for item in route["assumptions"]
    ):
        raise DiscoveryError("semantic route assumptions must be an array")
    return {
        key: (
            _semantic_field(value)
            if isinstance(value, str)
            else sorted(
                (_semantic_field(item) for item in value),
                key=lambda item: (item["terms"], item["relations"]),
            )
        )
        for key, value in sorted(route.items())
    }


def route_fingerprints(route: Mapping[str, Any]) -> tuple[str, str]:
    normalized = canonical_route(route)
    core = {
        key: normalized[key]
        for key in ("structural_object", "required_result", "target_effect", "assumptions")
    }
    return digest_value(normalized), digest_value(core)


def _score(features: Mapping[str, float], weights: Mapping[str, float]) -> float:
    raw = sum(features[name] * weights[name] for name in FEATURE_WEIGHTS)
    return round(max(0.0, min(1.0, raw)), 6)


def adaptive_policy(state: Mapping[str, Any]) -> dict[str, Any]:
    attempts = list(state.get("route_attempts", []))[-24:]
    if not attempts:
        return {
            "window": 0,
            "mean_outcome_value": None,
            "stagnation": 0.0,
            "expansion_pressure": 0.0,
            "waiting": 0.0,
            "effective_weights": copy.deepcopy(FEATURE_WEIGHTS),
        }
    values = [OUTCOME_VALUE.get(item.get("outcome"), 0.0) for item in attempts]
    stagnation = sum(item.get("outcome") in {"NO_PROGRESS", "NO_DELTA"} for item in attempts) / len(attempts)
    expansion_pressure = sum(item.get("outcome") in REFRAME_OUTCOMES for item in attempts) / len(attempts)
    waiting = sum(item.get("outcome") == "WAITING_EXTERNAL" for item in attempts) / len(attempts)
    productive = sum(value >= 0.7 for value in values) / len(values)
    weights = copy.deepcopy(FEATURE_WEIGHTS)
    weights["target_leverage"] += 0.04 * productive
    weights["expected_information_gain"] += 0.08 * (stagnation + expansion_pressure)
    weights["checkability"] += 0.05 * waiting
    weights["reversibility"] += 0.06 * stagnation
    weights["novelty"] += 0.10 * (stagnation + expansion_pressure)
    weights["transfer_value"] += 0.04 * (stagnation + expansion_pressure)
    weights["cost"] -= 0.05 * (stagnation + waiting)
    weights["recoupling_risk"] -= 0.15 * stagnation
    return {
        "window": len(attempts),
        "mean_outcome_value": round(sum(values) / len(values), 6),
        "stagnation": round(stagnation, 6),
        "expansion_pressure": round(expansion_pressure, 6),
        "waiting": round(waiting, 6),
        "effective_weights": {key: round(value, 6) for key, value in weights.items()},
    }


def _proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "proposal_id", "node_id", "lane", "route", "objective", "evaluator",
        "expected_delta", "changed_axis", "revival_evidence", "features",
    }
    condition_fields = {"return_condition", "stop_condition"} & set(value)
    if len(condition_fields) != 1:
        raise DiscoveryError("discovery proposal requires exactly one return_condition")
    _closed(value, required | condition_fields, "discovery proposal")
    proposal = copy.deepcopy(dict(value))
    proposal["return_condition"] = proposal.pop("stop_condition", proposal.get("return_condition"))
    if proposal["lane"] not in LANES:
        raise DiscoveryError(f"unknown discovery lane {proposal['lane']!r}")
    for field in ("proposal_id", "node_id", "objective", "evaluator", "expected_delta", "return_condition"):
        if not isinstance(proposal[field], str) or not proposal[field].strip():
            raise DiscoveryError(f"proposal {field} is empty")
    route_fp, core_fp = route_fingerprints(proposal["route"])
    features = proposal["features"]
    if not isinstance(features, dict) or set(features) != set(FEATURE_WEIGHTS):
        raise DiscoveryError("proposal features do not match the declared value function")
    normalized_features = {name: _number(features[name], f"features.{name}") for name in FEATURE_WEIGHTS}
    proposal["features"] = normalized_features
    proposal["route_fingerprint"] = route_fp
    proposal["core_fingerprint"] = core_fp
    proposal["score"] = _score(normalized_features, FEATURE_WEIGHTS)
    return proposal


def prepare_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    """Public, copy-returning proposal validator used by round coordination."""
    return _proposal(value)


def _jaccard(left: set[str], right: set[str]) -> float:
    return exploration.term_similarity(left, right)


def _prior_route_semantics(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    dispositions = {
        item["route_fingerprint"]: item.get(
            "route_disposition",
            "EXHAUSTED" if item.get("outcome") in EXHAUSTING else "LIVE",
        )
        for item in state["route_attempts"]
    }
    records: list[dict[str, Any]] = []
    for event in state["events"]:
        if event["kind"] != "ARBITRATION_RECORDED":
            continue
        selected = event["payload"]["arbitration"].get("selected_route")
        if selected is None:
            continue
        records.append({
            **copy.deepcopy(selected),
            "disposition": dispositions.get(selected["route_fingerprint"], "LIVE"),
        })
    return records


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    benefits = (
        "target_leverage", "expected_information_gain", "checkability",
        "reversibility", "novelty", "transfer_value",
    )
    costs = ("cost", "recoupling_risk")
    no_worse = all(left["metrics"][key] >= right["metrics"][key] for key in benefits)
    no_worse = no_worse and all(left["metrics"][key] <= right["metrics"][key] for key in costs)
    strictly_better = any(left["metrics"][key] > right["metrics"][key] for key in benefits)
    strictly_better = strictly_better or any(
        left["metrics"][key] < right["metrics"][key] for key in costs
    )
    return no_worse and strictly_better


def plan_portfolio(
    state_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    portfolio_exception: str = "",
    selected_proposal_id: str | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if len(proposals) > exploration.FIXED_LIMITS["max_live_proposals"]:
        raise DiscoveryError("portfolio exceeds the live-proposal limit")
    items = {item["item_id"]: item for item in state["frontier"]["items"]}
    barriers = {
        item.get("core_fingerprint")
        for item in state["frontier"]["obstructions"]
        if item.get("core_fingerprint")
    }
    exhausted = {
        item["route_fingerprint"]
        for item in state["route_attempts"]
        if item.get("exhausted", item["outcome"] in EXHAUSTING)
    }
    stalled = {
        item["route_fingerprint"]
        for item in state["route_attempts"]
        if item.get("outcome") in {"NO_PROGRESS", "NO_DELTA"}
    }
    attempt_counts: dict[str, int] = {}
    for attempt in state["route_attempts"]:
        fingerprint = attempt["route_fingerprint"]
        attempt_counts[fingerprint] = attempt_counts.get(fingerprint, 0) + 1
    policy = adaptive_policy(state)
    prior_routes = _prior_route_semantics(state)
    eligible: list[dict[str, Any]] = []
    prepared_all: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_routes: list[dict[str, Any]] = []
    for raw in proposals:
        identifier = str(raw.get("proposal_id", "<missing>"))
        try:
            proposal = exploration.prepare_proposal(ROOT, state, raw)
            prepared_all.append(proposal)
            route_fp, core_fp = exploration.proposal_fingerprints(proposal)
            if proposal["proposal_id"] in seen_ids:
                raise DiscoveryError("proposal id is duplicated")
            seen_ids.add(proposal["proposal_id"])
            if proposal["node_id"] not in items:
                raise DiscoveryError("proposal names an unknown frontier item")
            route_terms = exploration.proposal_terms(proposal)
            core_terms = exploration.proposal_terms(proposal, core=True)
            route_similarity = max(
                (_jaccard(route_terms, set(item["route_terms"])) for item in prior_routes),
                default=0.0,
            )
            core_similarity = max(
                (_jaccard(core_terms, set(item["core_terms"])) for item in prior_routes),
                default=0.0,
            )
            similar_exhausted = any(
                item["disposition"] == "EXHAUSTED"
                and _jaccard(route_terms, set(item["route_terms"])) >= 0.82
                for item in prior_routes
            )
            similar_core = any(
                item["disposition"] == "EXHAUSTED"
                and _jaccard(core_terms, set(item["core_terms"])) >= 0.72
                for item in prior_routes
            )
            repeated = route_fp in exhausted or similar_exhausted
            recoupled = core_fp in barriers or similar_core
            unchanged_stalled = route_fp in stalled
            mutated = (
                proposal["changed_axis"].strip()
                and proposal["revival_evidence"].strip()
                and proposal["revival_predicate"].strip()
            )
            if (repeated or recoupled or unchanged_stalled) and not mutated:
                raise DiscoveryError(
                    "semantic route repeats a stalled/exhausted route or obstruction without a changed axis and revival evidence"
                )
            if attempt_counts.get(route_fp, 0) >= proposal["max_attempts"]:
                raise DiscoveryError("semantic route has reached its sealed attempt limit")
            if any(
                exploration.semantic_similarity(proposal, item) >= 0.82
                for item in seen_routes
            ):
                raise DiscoveryError("portfolio duplicates or paraphrases a semantic route")
            recoupling_risk = max(
                1.0 if recoupled else 0.0,
                core_similarity,
                0.75 * route_similarity,
            )
            metrics = exploration.proposal_metrics(proposal, recoupling_risk)
            proposal["route_fingerprint"] = route_fp
            proposal["core_fingerprint"] = core_fp
            proposal["metrics"] = metrics
            proposal["score"] = exploration.proposal_score(metrics)
            proposal["migrated_from_legacy"] = raw.get("schema") != exploration.PROPOSAL_SCHEMA
            seen_routes.append(proposal)
            eligible.append(proposal)
        except (DiscoveryError, exploration.ExplorationError, kernel.KernelError) as exc:
            refused.append({"proposal_id": identifier, "reason": str(exc)})
    pareto_ids = {
        item["proposal_id"]
        for item in eligible
        if not any(
            other["proposal_id"] != item["proposal_id"] and _dominates(other, item)
            for other in eligible
        )
    }
    eligible.sort(key=lambda item: (
        item["proposal_id"] not in pareto_ids,
        -exploration.EVIDENCE_RANK[item["evidence_ceiling"]],
        -item["metrics"]["expected_information_gain"],
        item["metrics"]["cost"],
        -item["score"],
        item["proposal_id"],
    ))
    lanes = sorted({item["lane"] for item in eligible})
    route_count = len({item["route_fingerprint"] for item in eligible})
    core_count = len({item["core_fingerprint"] for item in eligible})
    failure_domains = sorted({item["failure_domain"] for item in eligible})
    diversity_ok = (
        len(lanes) >= 3
        and route_count >= 3
        and core_count >= 2
        and len(failure_domains) >= 2
    )
    exception = portfolio_exception.strip()
    dispatchable = bool(eligible) and (diversity_ok or bool(exception))
    ranked_ids = {item["proposal_id"] for item in eligible}
    if selected_proposal_id is not None:
        if selected_proposal_id not in ranked_ids:
            raise DiscoveryError("Explorer selected a refused or unknown proposal")
        selected = selected_proposal_id
    else:
        selected = eligible[0]["proposal_id"] if dispatchable else None
    return {
        "schema": "witsoc.discovery-plan.v2",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "proposal_set_sha256": exploration.proposal_set_sha256(prepared_all),
        "ranked": [
            {
                "proposal_id": item["proposal_id"],
                "proposal_sha256": item["payload_sha256"],
                "node_id": item["node_id"],
                "lane": item["lane"],
                "score": item["score"],
                "metrics": item["metrics"],
                "pareto": item["proposal_id"] in pareto_ids,
                "evidence_ceiling": item["evidence_ceiling"],
                "cost_class": item["cost_class"],
                "failure_domain": item["failure_domain"],
                "route_fingerprint": item["route_fingerprint"],
                "core_fingerprint": item["core_fingerprint"],
                "migrated_from_legacy": item["migrated_from_legacy"],
            }
            for item in eligible
        ],
        "refused": refused,
        "adaptive_policy": policy,
        "lane_coverage": lanes,
        "failure_domain_coverage": failure_domains,
        "semantic_route_count": route_count,
        "semantic_core_count": core_count,
        "diversity_requirement": {
            "minimum_lanes": 3,
            "minimum_semantic_routes": 3,
            "minimum_semantic_cores": 2,
            "minimum_failure_domains": 2,
        },
        "diversity_ok": diversity_ok,
        "portfolio_exception": exception,
        "dispatchable": dispatchable,
        "selected_proposal_id": selected if dispatchable else None,
        "advisory": True,
        "scores_are_evidence": False,
    }


def novelty_audit(
    root: Path,
    candidate_value: Mapping[str, Any],
    source_map_value: Mapping[str, Any],
    comparisons: list[Mapping[str, Any]],
    *,
    report_id: str,
) -> dict[str, Any]:
    candidate = contracts.validate_packet(root, "witsoc.candidate.v2", candidate_value)
    source_map = contracts.validate_packet(root, "witsoc.source-map.v2", source_map_value)
    if candidate["target_sha256"] != source_map["target_sha256"]:
        raise DiscoveryError("novelty audit crosses a frozen target boundary")
    if not report_id.strip():
        raise DiscoveryError("novelty audit report id is empty")
    source_ids = {item["source_id"] for item in source_map["entries"]}
    required = {
        "source_id", "relation", "scope_match", "assumptions_match",
        "conclusion_match", "evidence_ref", "rationale",
    }
    relations = {
        "SAME", "KNOWN_STRONGER", "CANDIDATE_STRONGER", "OVERLAP",
        "DISJOINT", "UNKNOWN",
    }
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in comparisons:
        _closed(raw, required, "novelty comparison")
        item = copy.deepcopy(dict(raw))
        if item["source_id"] not in source_ids or item["source_id"] in seen:
            raise DiscoveryError("novelty comparison names an unknown or repeated source")
        if item["relation"] not in relations:
            raise DiscoveryError(f"unknown novelty relation {item['relation']!r}")
        for field in ("scope_match", "assumptions_match", "conclusion_match"):
            if not isinstance(item[field], bool):
                raise DiscoveryError(f"novelty comparison {field} must be boolean")
        for field in ("evidence_ref", "rationale"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise DiscoveryError(f"novelty comparison {field} is empty")
        seen.add(item["source_id"])
        normalized.append(item)
    missing = sorted(source_ids - seen)
    exact = [
        item for item in normalized
        if item["scope_match"] and item["assumptions_match"] and item["conclusion_match"]
    ]
    if any(item["relation"] == "SAME" for item in exact):
        status = "KNOWN"
    elif any(item["relation"] == "KNOWN_STRONGER" for item in exact):
        status = "DOMINATED_BY_KNOWN_RESULT"
    elif missing or source_map["unresolved"] or any(
        item["relation"] == "UNKNOWN" for item in normalized
    ):
        status = "UNCONFIRMED"
    elif any(item["relation"] == "CANDIDATE_STRONGER" for item in exact):
        status = "STRICT_REFINEMENT_CANDIDATE"
    else:
        status = "DISTINCT_CANDIDATE"
    disposition = (
        "BLOCKED" if status in {"KNOWN", "DOMINATED_BY_KNOWN_RESULT"}
        else "ADVISORY" if status == "UNCONFIRMED"
        else "READY"
    )
    report = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": report_id,
        "kind": "NOVELTY_AUDIT",
        "target_sha256": candidate["target_sha256"],
        "source_refs": sorted({
            candidate["payload_sha256"], source_map["payload_sha256"],
            *(item["evidence_ref"] for item in normalized),
        }),
        "body": {
            "candidate_id": candidate["candidate_id"],
            "source_map_id": source_map["source_map_id"],
            "novelty_status": status,
            "comparisons": sorted(normalized, key=lambda item: item["source_id"]),
            "missing_source_comparisons": missing,
            "source_map_unresolved": list(source_map["unresolved"]),
            "correctness_inference": "NONE",
        },
        "disposition": disposition,
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", report)
    except contracts.ContractError as exc:
        raise DiscoveryError(str(exc)) from exc


def build_episode(
    state_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    episode_id: str,
    portfolio_exception: str = "",
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if state["pending_episode"] is not None:
        raise DiscoveryError("the bounded loop already has a pending episode")
    if state["mode"] == "OPEN_DISCOVERY":
        raise DiscoveryError(
            "open discovery must use issue_best with a sealed Explorer state so arbitration is recorded"
        )
    plan = plan_portfolio(state, proposals, portfolio_exception)
    if not plan["dispatchable"]:
        if plan["ranked"]:
            raise DiscoveryError(
                "portfolio lacks three lanes, three semantic routes, or two semantic cores and has no exception"
            )
        reasons = "; ".join(item["reason"] for item in plan["refused"][:3])
        raise DiscoveryError("no proposal is dispatchable" + (f": {reasons}" if reasons else ""))
    selected_id = plan["selected_proposal_id"]
    selected = next(
        exploration.prepare_proposal(ROOT, state, item)
        for item in proposals
        if item.get("proposal_id") == selected_id
    )
    return _episode_from_prepared(state, selected, episode_id, plan)


def _episode_from_prepared(
    state: Mapping[str, Any],
    selected: Mapping[str, Any],
    episode_id: str,
    plan: Mapping[str, Any],
    arbitration_ref: str | None = None,
    source_map_ref: str | None = None,
    source_refs: list[str] | None = None,
    source_verified_refs: list[str] | None = None,
    target_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = next(item for item in state["frontier"]["items"] if item["item_id"] == selected["node_id"])
    route_fp, core_fp = exploration.proposal_fingerprints(selected)
    selected_record = next(
        (
            copy.deepcopy(dict(item)) for item in plan.get("ranked", [])
            if item.get("proposal_id") == selected["proposal_id"]
        ),
        None,
    )
    adjudication = {
        "schema": plan["schema"],
        "target_sha256": plan["target_sha256"],
        "base_revision": plan["base_revision"],
        "base_state_sha256": plan["base_state_sha256"],
        "proposal_set_sha256": plan["proposal_set_sha256"],
        "selected_proposal_id": selected["proposal_id"],
        "ranked": [selected_record] if selected_record is not None else [],
        "portfolio_exception": plan["portfolio_exception"],
        "dispatchable": plan["dispatchable"],
        "scores_are_evidence": False,
        "context_policy": "REFERENCE_FIRST_SELECTED_ROUTE_ONLY",
        "arbitration_ref": arbitration_ref,
        "source_map_ref": source_map_ref,
        "source_refs": list(source_refs or []),
        "source_verified_refs": list(source_verified_refs or []),
        "target_contract": copy.deepcopy(
            dict(target_contract) if target_contract is not None else None
        ),
    }
    packet = {
        "schema": EPISODE_SCHEMA,
        "episode_id": episode_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "node_id": selected["node_id"],
        "claim": item["statement"],
        "lane": selected["lane"],
        "route": selected["route"],
        "route_fingerprint": route_fp,
        "core_fingerprint": core_fp,
        "objective": selected["objective"],
        "evaluator": selected["evaluator"],
        "expected_delta": selected["expected_delta"],
        "return_condition": selected["return_condition"],
        "campaign_authority": False,
        "changed_axis": selected["changed_axis"],
        "revival_evidence": selected["revival_evidence"],
        "adjudication": adjudication,
    }
    return validate_episode(seal_packet(packet), state)


def validate_episode(value: Mapping[str, Any], state_value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    required = {
        "schema", "episode_id", "target_sha256", "base_revision", "base_state_sha256",
        "node_id", "claim", "lane", "route", "route_fingerprint", "core_fingerprint",
        "objective", "evaluator", "expected_delta", "changed_axis",
        "revival_evidence", "adjudication", "payload_sha256",
    }
    condition_fields = {"return_condition", "stop_condition"} & set(value)
    if len(condition_fields) != 1:
        raise DiscoveryError("research episode requires exactly one return condition")
    authority_fields = {"campaign_authority"} & set(value)
    _closed(value, required | condition_fields | authority_fields, "research episode")
    episode = copy.deepcopy(dict(value))
    if episode["schema"] != EPISODE_SCHEMA or episode["lane"] not in LANES:
        raise DiscoveryError("research episode schema or lane is invalid")
    if not verify_packet_seal(episode):
        raise DiscoveryError("research episode seal is broken")
    if episode.get("campaign_authority", False) is not False:
        raise DiscoveryError("Researcher episodes cannot carry campaign authority")
    selected = next(
        (
            item for item in episode["adjudication"].get("ranked", [])
            if item.get("proposal_id") == episode["adjudication"].get("selected_proposal_id")
        ),
        None,
    )
    if selected and selected.get("proposal_sha256"):
        route_fp, core_fp = selected["route_fingerprint"], selected["core_fingerprint"]
    else:
        route_fp, core_fp = route_fingerprints(episode["route"])
    if (route_fp, core_fp) != (episode["route_fingerprint"], episode["core_fingerprint"]):
        raise DiscoveryError("research episode route fingerprints are stale")
    arbitration_ref = episode["adjudication"].get("arbitration_ref")
    source_map_ref = episode["adjudication"].get("source_map_ref")
    source_refs = episode["adjudication"].get("source_refs", [])
    source_verified_refs = episode["adjudication"].get("source_verified_refs", [])
    target_contract = episode["adjudication"].get("target_contract")
    if source_map_ref is not None and not re.fullmatch(r"[0-9a-f]{64}", source_map_ref):
        raise DiscoveryError("research episode source-map reference is invalid")
    if not isinstance(source_refs, list) or any(
        not isinstance(reference, str) or not reference for reference in source_refs
    ) or len(source_refs) != len(set(source_refs)):
        raise DiscoveryError("research episode source refs are malformed")
    if source_map_ref is None and source_refs:
        raise DiscoveryError("research episode has source refs without a source map")
    if source_map_ref is not None and not source_refs:
        raise DiscoveryError("research episode lacks entry-level source refs")
    if not isinstance(source_verified_refs, list) or len(source_verified_refs) != len(
        set(source_verified_refs)
    ) or set(source_verified_refs) - set(source_refs):
        raise DiscoveryError("research episode source-verified refs are malformed")
    if arbitration_ref is not None and episode["lane"] != "RETRIEVE" and source_map_ref is None:
        raise DiscoveryError("non-retrieval open discovery lacks Explorer source context")
    if target_contract is not None:
        try:
            target_semantics.validate(ROOT, target_contract)
        except target_semantics.TargetSemanticsError as exc:
            raise DiscoveryError(str(exc)) from exc
        if target_contract["target_sha256"] != episode["target_sha256"]:
            raise DiscoveryError("research episode target contract belongs to another target")
    if arbitration_ref is not None and target_contract is None:
        raise DiscoveryError("Explorer-authorized episode lacks its target acceptance contract")
    if state_value is not None:
        state = kernel.validate_state(state_value)
        expected = {
            "target_sha256": state["target"]["canonical_sha256"],
            "base_revision": state["revision"],
            "base_state_sha256": state["state_sha256"],
        }
        for key, expected_value in expected.items():
            if episode[key] != expected_value:
                raise DiscoveryError(f"research episode {key} does not bind current state")
    return episode


def issue_best(
    state_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    episode_id: str,
    portfolio_exception: str = "",
    explorer_state_value: Mapping[str, Any] | None = None,
    source_map_value: Mapping[str, Any] | None = None,
    stop_review_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = kernel.validate_state(state_value)
    if state["pending_episode"] is not None:
        raise DiscoveryError("the bounded loop already has a pending episode")
    arbitration_ref = None
    if state["mode"] == "OPEN_DISCOVERY":
        if explorer_state_value is None:
            raise DiscoveryError(
                "OPEN_DISCOVERY issuance requires a sealed Explorer state and arbitration"
            )
        try:
            arbitration, prepared = exploration.build_arbitration(
                ROOT, state, explorer_state_value, proposals,
                source_map_value, stop_review_value,
            )
        except exploration.ExplorationError as exc:
            raise DiscoveryError(str(exc)) from exc
        if arbitration["action"] not in exploration.DISPATCH_ACTIONS:
            raise DiscoveryError("Explorer arbitration does not authorize worker dispatch")
        if arbitration["action"] == "WORK_ITEM_TO_GENERATOR":
            raise DiscoveryError(
                "WORK_ITEM_TO_GENERATOR cannot enter the Researcher episode path; "
                "use artifact production with a typed generator handoff"
            )
        plan = plan_portfolio(
            state,
            proposals,
            portfolio_exception,
            selected_proposal_id=arbitration["selected_proposal_id"],
        )
        if plan["proposal_set_sha256"] != arbitration["proposal_set_sha256"]:
            raise DiscoveryError("portfolio bytes differ from the Explorer arbitration")
        try:
            state = exploration.apply_arbitration(ROOT, state, arbitration)
        except exploration.ExplorationError as exc:
            raise DiscoveryError(str(exc)) from exc
        selected = next(
            item for item in prepared
            if item["proposal_id"] == arbitration["selected_proposal_id"]
        )
        arbitration_ref = arbitration["payload_sha256"]
        source_map_ref = explorer_state_value["source_coverage"]["source_map_ref"]
        episode = _episode_from_prepared(
            state,
            selected,
            episode_id,
            plan,
            arbitration_ref,
            source_map_ref,
            arbitration.get("source_refs", []),
            arbitration.get("source_verified_refs", []),
            arbitration["target_contract"],
        )
    else:
        episode = build_episode(state, proposals, episode_id, portfolio_exception)
    event = kernel.build_event(
        state,
        "EPISODE_ISSUED",
        {"episode": episode},
        f"issue:{episode_id}",
    )
    return kernel.apply_event(state, event), episode


def validate_delta_binding(
    value: Mapping[str, Any],
    state_value: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    base_revision: int,
    base_state_sha256: str,
) -> dict[str, Any]:
    """Validate one delta against an explicit issued-episode binding."""
    base_required = {
        "schema", "delta_id", "episode_id", "episode_sha256", "target_sha256",
        "base_revision", "base_state_sha256", "outcome", "evidence_refs",
        "frontier_measure_before", "frontier_measure_after", "new_frontier",
        "new_obstruction", "admission_ref", "independent_review",
        "remaining_obstruction", "revival_condition", "next_proposals", "changed_axis",
        "payload_sha256",
    }
    schema = value.get("schema")
    required = base_required | ({"reasoning", "messages"} if schema == DELTA_SCHEMA else set())
    _closed(value, required, "research delta")
    delta = copy.deepcopy(dict(value))
    state = kernel.validate_state(state_value)
    if delta["schema"] not in DELTA_SCHEMAS or delta["outcome"] not in OUTCOMES:
        raise DiscoveryError("research delta schema or outcome is invalid")
    try:
        delta = contracts.validate_packet(ROOT, delta["schema"], delta)
    except contracts.ContractError as exc:
        raise DiscoveryError(str(exc)) from exc
    for field in ("delta_id", "episode_id", "remaining_obstruction", "revival_condition", "changed_axis"):
        if not isinstance(delta[field], str):
            raise DiscoveryError(f"research delta {field} must be a string")
    for field in ("evidence_refs", "new_frontier", "next_proposals"):
        if not isinstance(delta[field], list):
            raise DiscoveryError(f"research delta {field} must be an array")
    if any(not isinstance(reference, str) or not reference.strip() for reference in delta["evidence_refs"]):
        raise DiscoveryError("research delta evidence references must be non-empty strings")
    if delta["episode_id"] != binding.get("episode_id"):
        raise DiscoveryError("research delta does not answer the bound episode")
    expected = {
        "episode_sha256": binding.get("payload_sha256"),
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": base_revision,
        "base_state_sha256": base_state_sha256,
    }
    for key, expected_value in expected.items():
        if delta[key] != expected_value:
            raise DiscoveryError(f"research delta {key} does not bind the issued state")
    before, after = delta["frontier_measure_before"], delta["frontier_measure_after"]
    if not isinstance(before, int) or not isinstance(after, int) or before < 0 or after < 0:
        raise DiscoveryError("frontier measures must be non-negative integers")
    if delta["outcome"] == "STRICT_REDUCTION" and after >= before:
        raise DiscoveryError("STRICT_REDUCTION requires a strictly smaller frontier measure")
    if delta["outcome"] == "ADMITTED_PRODUCT":
        review = delta["independent_review"] or {}
        if not delta["admission_ref"] or review.get("status") != "PASS" or not review.get("evidence_ref"):
            raise DiscoveryError("ADMITTED_PRODUCT requires admission and independent PASS references")
    elif delta["admission_ref"] is not None:
        raise DiscoveryError("only ADMITTED_PRODUCT may carry an admission reference")
    if delta["outcome"] in {
        "CANDIDATE_PRODUCT", "FALSIFICATION", "TARGET_FALSIFIED",
        "ROUTE_REFUTED", "STRICT_REDUCTION", "CORE_SHARPENED", "POSITIVE_SIGNAL",
    } and not delta["evidence_refs"]:
        raise DiscoveryError(f"{delta['outcome']} requires evidence references")
    if delta["outcome"] in {
        "NO_PROGRESS", "NO_DELTA", "ROUTE_REFUTED", "NEW_OBSTRUCTION",
        "METHOD_BARRIER", "CORE_SHARPENED", "SESSION_CHECKPOINT",
    }:
        if not delta["remaining_obstruction"].strip() or not delta["revival_condition"].strip():
            raise DiscoveryError("stagnant outcomes require an obstruction and revival condition")
    obstruction_outcomes = {"NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED"}
    if delta["outcome"] in {"NEW_OBSTRUCTION", "METHOD_BARRIER"} and delta["new_obstruction"] is None:
        raise DiscoveryError("method-barrier outcomes require a typed obstruction record")
    if delta["outcome"] not in obstruction_outcomes and delta["new_obstruction"] is not None:
        raise DiscoveryError("only an obstruction or core-sharpening outcome may carry an obstruction record")
    if delta["outcome"] in {"STRICT_REDUCTION", "CORE_SHARPENED"} and not delta["new_frontier"]:
        raise DiscoveryError("a reduction or sharpened core must return attackable frontier children")
    if delta["schema"] == DELTA_SCHEMA and delta["outcome"] in {
        "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED",
        "ROUTE_REFUTED", "NO_PROGRESS", "NO_DELTA", "POSITIVE_SIGNAL",
    } and not delta["next_proposals"]:
        raise DiscoveryError("an unresolved Researcher return must include at least one follow-up seed")
    if delta["new_obstruction"] is not None:
        required_obstruction = {
            "obstruction_id", "statement", "route_fingerprint", "core_fingerprint",
            "evidence_refs", "revival_condition",
        }
        if set(delta["new_obstruction"]) != required_obstruction:
            raise DiscoveryError("new_obstruction shape is invalid")
        obstruction = delta["new_obstruction"]
        if (
            obstruction["route_fingerprint"] != binding.get("route_fingerprint")
            or obstruction["core_fingerprint"] != binding.get("core_fingerprint")
        ):
            raise DiscoveryError("new obstruction is not bound to the attempted semantic route")
        if not isinstance(obstruction["evidence_refs"], list):
            raise DiscoveryError("new obstruction evidence_refs must be an array")
        for field in ("obstruction_id", "statement", "revival_condition"):
            if not isinstance(obstruction[field], str) or not obstruction[field].strip():
                raise DiscoveryError(f"new obstruction {field} is empty")
    if delta["schema"] == DELTA_SCHEMA:
        episode = issued_episode(state, binding)
        contract = reasoning.build_contract(state, episode)
        try:
            reasoning_state = reasoning.validate_state(
                ROOT,
                delta["reasoning"],
                contract,
                expected_outcome=delta["outcome"],
                final=True,
            )
        except reasoning.ReasoningError as exc:
            raise DiscoveryError(str(exc)) from exc
        if len(delta["messages"]) != 1:
            raise DiscoveryError("reasoning-bound delta requires one typed return message")
        try:
            message = loop_messages.validate(ROOT, delta["messages"][0], contract)
        except loop_messages.LoopMessageError as exc:
            raise DiscoveryError(str(exc)) from exc
        if message != loop_messages.research_return(contract, reasoning_state):
            raise DiscoveryError("Researcher return message differs from its reasoning state")
        route = reasoning_state["route_compliance"]
        if route["status"] == "ASSIGNED" and delta["changed_axis"]:
            raise DiscoveryError("assigned-route delta cannot claim a changed axis")
        if route["status"] == "LOCAL_MUTATION" and delta["changed_axis"] != route["changed_axis"]:
            raise DiscoveryError("delta changed axis differs from reasoning route compliance")
        if delta["new_obstruction"] is not None:
            certificate = reasoning_state["obstruction_certificate"]
            obstruction = delta["new_obstruction"] or {}
            if (
                certificate is None
                or certificate["scope_statement"] != obstruction.get("statement")
                or certificate["revival_condition"] != obstruction.get("revival_condition")
            ):
                raise DiscoveryError("typed obstruction and reasoning certificate differ")
    frontier_ids = {item["item_id"] for item in state["frontier"]["items"]}
    for item in delta["new_frontier"]:
        frontier_ids.add(kernel._frontier_item(item)["item_id"])
    seen_followups: set[str] = set()
    for raw in delta["next_proposals"]:
        proposal = _proposal(raw)
        if proposal["node_id"] not in frontier_ids:
            raise DiscoveryError("next proposal names an unknown current or returned frontier item")
        fingerprint, core_fingerprint = route_fingerprints(proposal["route"])
        if fingerprint == binding.get("route_fingerprint"):
            raise DiscoveryError("a follow-up seed repeats the just-attempted semantic route")
        if (
            core_fingerprint == binding.get("core_fingerprint")
            and not proposal["changed_axis"].strip()
        ):
            raise DiscoveryError(
                "a same-core follow-up seed must name the changed semantic axis"
            )
        if fingerprint in seen_followups:
            raise DiscoveryError("follow-up seeds repeat the same semantic route")
        seen_followups.add(fingerprint)
    return delta


def issued_episode(
    state_value: Mapping[str, Any], binding: Mapping[str, Any]
) -> dict[str, Any]:
    """Recover the immutable issued episode from replayable state history."""
    state = kernel.validate_state(state_value)
    episode_id = binding.get("episode_id")
    expected_sha = binding.get("payload_sha256")
    for event in reversed(state["events"]):
        if event["kind"] == "EPISODE_ISSUED":
            episode = event["payload"]["episode"]
            if episode.get("episode_id") == episode_id:
                if episode.get("payload_sha256") != expected_sha:
                    raise DiscoveryError("issued episode history differs from pending work")
                return validate_episode(episode)
        if event["kind"] == "ROUND_ISSUED":
            for wrapped in event["payload"]["round"]["episodes"]:
                episode = wrapped["episode"]
                if episode.get("episode_id") == episode_id:
                    if episode.get("payload_sha256") != expected_sha:
                        raise DiscoveryError("issued round history differs from pending work")
                    return validate_episode(episode)
    raise DiscoveryError("pending work has no replayable issued episode")


def validate_delta(value: Mapping[str, Any], state_value: Mapping[str, Any]) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    pending = state["pending_episode"]
    if pending is not None and pending.get("kind") == "ROUND":
        raise DiscoveryError("use the round return path for an independent-round child delta")
    if pending is None:
        raise DiscoveryError("research delta does not answer the pending episode")
    return validate_delta_binding(
        value,
        state,
        pending,
        base_revision=state["revision"],
        base_state_sha256=state["state_sha256"],
    )


def apply_delta(state_value: Mapping[str, Any], delta_value: Mapping[str, Any]) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    delta = validate_delta(delta_value, state)
    event = kernel.build_event(
        state,
        "EPISODE_RETURNED",
        {"delta": delta},
        f"return:{delta['delta_id']}",
    )
    # Deliberately returns control with no successor episode. Explorer must
    # adjudicate the changed frontier and issue a fresh, separately sealed one.
    return kernel.apply_event(state, event)
