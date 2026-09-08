"""Bounded Explorer reasoning, proposal compilation, and return arbitration."""

from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from . import contracts, kernel, target_semantics
from .canonical import digest_value, seal_packet


CONTRACT_SCHEMA = "witsoc.explorer-contract.v1"
STATE_SCHEMA = "witsoc.explorer-state.v1"
DRAFT_SCHEMA = "witsoc.explorer-state-draft.v1"
ARBITRATION_SCHEMA = "witsoc.explorer-arbitration.v1"
PROPOSAL_SCHEMA = "witsoc.discovery-proposal.v2"
PROPOSAL_DRAFT_SCHEMA = "witsoc.discovery-proposal-draft.v2"
SOURCE_MAP_SCHEMA = "witsoc.source-map.v2"
SOURCE_MAP_DRAFT_SCHEMA = "witsoc.source-map-draft.v2"
CONTROL_REPORT_SCHEMA = "witsoc.control-report.v1"

LANES = {"RETRIEVE", "REFUTE", "REDUCE", "CONSTRUCT", "TRANSFER", "MEASURE", "VERIFY"}
ACTIONS = {
    "REFRAME_FRONTIER", "EXPAND_FRONTIER", "PAUSE_WITH_FRONTIER", "DIRECT_ANSWER",
    "WORK_ITEM_TO_GENERATOR", "WORK_ITEM_TO_RESEARCHER", "RETRY_WITH_MUTATION",
    "DEMOTE", "WAIT_EXTERNAL", "HONEST_STOP",
}
DISPATCH_ACTIONS = {
    "WORK_ITEM_TO_GENERATOR", "WORK_ITEM_TO_RESEARCHER", "RETRY_WITH_MUTATION",
}
TERMINAL_ACTIONS = {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}
CLOSURE_SAFE = {"EXACT", "SOURCE_VERIFIED"}
BOUNDED_EVIDENCE = {"COMPUTATIONAL_BOUNDED", "EMPIRICAL", "SEARCH_BOUNDED", "UNKNOWN"}
STOP_CONCLUSIONS = {
    "ALL_RECORDED_ROUTES_ADJUDICATED",
}
PROHIBITED_SOURCE_TYPES = {
    "EXPLORER_OUTPUT", "EXPLORER_SYNTHESIS", "RUN_RESULT", "RUN_SUMMARY",
    "ARBITRATION", "MISSION_REPORT",
}
PROHIBITED_SOURCE_BASENAMES = {
    "explorer.json", "explorer.draft.json", "arbitration.json", "result.md",
}
FIXED_LIMITS = {
    "max_frontier_nodes": 32,
    "max_live_proposals": 5,
    "max_route_memory": 24,
    "max_open_contradictions": 8,
    "max_source_queries": 24,
    "max_target_ambiguities": 8,
}
FRONTIER_KINDS = {
    "TARGET", "ENDPOINT", "EQUIVALENT_CORE", "NECESSARY_CONDITION",
    "SUFFICIENT_CONDITION", "INTERMEDIATE_CLAIM", "DISCRIMINATOR", "EXTERNAL_DEPENDENCY",
    "EMPIRICAL_SIGNAL", "OPEN_CORE", "REDUCTION", "HYPOTHESIS",
    "COMPUTATION", "RETRIEVAL", "VERIFICATION_OBLIGATION", "PRODUCT",
}
RELATIONS = {
    "EQUIVALENT_TO", "NECESSARY_FOR", "SUFFICIENT_FOR", "IMPLIES",
    "REDUCES_TO", "BLOCKS", "DISCRIMINATES", "SUPPORTS", "EMPIRICAL_ONLY",
}
RETURN_IMPACTS = {
    "ADMITTED_PRODUCT": {"LOCAL_PRODUCT", "TARGET_PROGRESS"},
    "CANDIDATE_PRODUCT": {"LOCAL_PRODUCT", "TARGET_PROGRESS"},
    "STRICT_REDUCTION": {"CORE_SHARPENED"},
    "FALSIFICATION": {"TARGET_PROGRESS"},
    "TARGET_FALSIFIED": {"TARGET_PROGRESS"},
    "ROUTE_REFUTED": {"ROUTE_REFUTED"},
    "NEW_OBSTRUCTION": {"CORE_SHARPENED"},
    "METHOD_BARRIER": {"CORE_SHARPENED"},
    "CORE_SHARPENED": {"CORE_SHARPENED"},
    "POSITIVE_SIGNAL": {"EMPIRICAL_SIGNAL", "LOCAL_PRODUCT"},
    "NO_PROGRESS": {"NO_PROGRESS"},
    "NO_DELTA": {"NO_PROGRESS"},
    "SESSION_CHECKPOINT": {"NO_PROGRESS"},
    "WAITING_EXTERNAL": {"EXTERNAL_WAIT"},
    "MERGEABLE": {
        "TARGET_PROGRESS", "LOCAL_PRODUCT", "ROUTE_REFUTED", "CORE_SHARPENED",
        "EMPIRICAL_SIGNAL", "SOURCE_UPDATE", "NO_PROGRESS",
    },
    "CONFLICT": {"CONFLICT"},
}
EVIDENCE_RANK = {
    "UNKNOWN": 0,
    "SEARCH_BOUNDED": 1,
    "EMPIRICAL": 2,
    "COMPUTATIONAL_BOUNDED": 3,
    "SOURCE_VERIFIED": 4,
    "EXACT": 5,
}
COST_RANK = {"tiny": 0, "small": 1, "medium": 2, "large": 3, "external": 4}
TERM_ALIASES = {
    "approach": "method", "strategy": "method", "technique": "method",
    "demonstrate": "derive", "establish": "derive", "prove": "derive",
    "proves": "derive", "proving": "derive", "show": "derive",
    "mapping": "transfer", "mapped": "transfer", "translate": "transfer",
    "translation": "transfer", "counterexample": "falsify",
    "countermodel": "falsify", "refutation": "falsify",
    "reduction": "reduce", "reducing": "reduce", "needed": "require",
    "needs": "require", "required": "require", "requires": "require",
}
FILLER_TERMS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "of",
    "on", "or", "the", "this", "to", "using", "via", "with",
}


class ExplorationError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise ExplorationError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _unique(items: list[Mapping[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in items:
        identifier = raw[field]
        if identifier in result:
            raise ExplorationError(f"{label} identifier {identifier!r} is duplicated")
        result[identifier] = copy.deepcopy(dict(raw))
    return result


def _last_event(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    events = state.get("events") or []
    return events[-1] if events else None


def phase_for(state_value: Mapping[str, Any]) -> str:
    state = kernel.validate_state(state_value)
    if state["pending_episode"] is not None:
        return "WAITING_RETURN"
    last = _last_event(state)
    if last is None:
        return "TRIAGE"
    if last["kind"] in {"EPISODE_RETURNED", "ROUND_RETURNED"}:
        return "RETURN_ARBITRATION"
    if last["kind"] == "ARBITRATION_RECORDED":
        action = last["payload"]["arbitration"]["action"]
        return "TERMINAL" if action in TERMINAL_ACTIONS else "POST_ARBITRATION"
    if last["kind"] == "DECISION_RECORD":
        action = last["payload"]["decision"]["action"]
        return "TERMINAL" if action in TERMINAL_ACTIONS else "POST_ARBITRATION"
    return "TRIAGE"


def build_contract(state_value: Mapping[str, Any]) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    last = _last_event(state)
    return seal_packet({
        "schema": CONTRACT_SCHEMA,
        "contract_id": f"explorer-contract:{state['kernel_id']}:{state['revision']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "phase": phase_for(state),
        "trigger_ref": last["payload_sha256"] if last is not None else None,
        "limits": copy.deepcopy(FIXED_LIMITS),
        "allowed_actions": sorted(ACTIONS),
        "closure_safe_evidence": sorted(CLOSURE_SAFE),
        "rules": {
            "explorer_cannot_produce_evidence": True,
            "return_requires_arbitration": True,
            "researcher_successor_is_advisory": True,
            "terminal_forbids_pending_work": True,
            "bounded_evidence_cannot_exhaust_general_route": True,
            "source_absence_is_scoped": True,
            "frontier_requires_target_paths": True,
            "barriers_require_frontier_expansion": True,
            "researcher_has_no_campaign_authority": True,
            "pause_preserves_open_frontier": True,
            "stop_requires_search_coverage": True,
        },
    })


def validate_contract(
    root: Path,
    value: Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, CONTRACT_SCHEMA, value)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    if packet["limits"] != FIXED_LIMITS:
        raise ExplorationError("Explorer contract limits are not canonical")
    if set(packet["allowed_actions"]) != ACTIONS:
        raise ExplorationError("Explorer contract actions are incomplete")
    if set(packet["closure_safe_evidence"]) != CLOSURE_SAFE:
        raise ExplorationError("Explorer closure-safe evidence classes are not canonical")
    if state is not None and packet != build_contract(state):
        raise ExplorationError("Explorer contract does not bind the current kernel state")
    return packet


def _terms(*values: Any) -> set[str]:
    text = " ".join(str(value) for value in values)
    text = unicodedata.normalize("NFKC", text).casefold()
    return {
        TERM_ALIASES.get(item, item)
        for item in re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)?", text)
        if item not in FILLER_TERMS
    }


def term_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return max(overlap / len(left | right), overlap / min(len(left), len(right)))


def _semantic_projection(proposal: Mapping[str, Any]) -> dict[str, Any]:
    route = proposal["route"]
    prerequisites = [item["statement"] for item in proposal["prerequisites"]]
    return {
        "operator_id": " ".join(proposal["operator_id"].casefold().split()),
        "method_family": " ".join(route["method_family"].casefold().split()),
        "mechanism": sorted(_terms(route["mechanism"])),
        "structural_object": sorted(_terms(route["structural_object"])),
        "invariant": sorted(_terms(proposal["invariant"])),
        "required_result": sorted(_terms(route["required_result"], proposal["failure_signature"])),
        "target_effect": sorted(_terms(route["target_effect"])),
        "assumptions": sorted(_terms(*route["assumptions"], *prerequisites)),
        "failure_domain": " ".join(proposal["failure_domain"].casefold().split()),
    }


def proposal_fingerprints(proposal: Mapping[str, Any]) -> tuple[str, str]:
    normalized = _semantic_projection(proposal)
    core = {
        key: normalized[key]
        for key in ("structural_object", "invariant", "required_result", "assumptions")
    }
    return digest_value(normalized), digest_value(core)


def proposal_terms(proposal: Mapping[str, Any], *, core: bool = False) -> set[str]:
    normalized = _semantic_projection(proposal)
    keys = (
        ("structural_object", "invariant", "required_result", "assumptions")
        if core else tuple(normalized)
    )
    result: set[str] = set()
    for key in keys:
        value = normalized[key]
        if isinstance(value, list):
            result.update(value)
        else:
            result.update(_terms(value))
    return result


def semantic_similarity(left: Mapping[str, Any], right: Mapping[str, Any], *, core: bool = False) -> float:
    left_projection = _semantic_projection(left)
    right_projection = _semantic_projection(right)
    keys = (
        ("structural_object", "invariant", "required_result", "assumptions")
        if core else tuple(left_projection)
    )
    scores = []
    for key in keys:
        left_value, right_value = left_projection[key], right_projection[key]
        left_terms = set(left_value) if isinstance(left_value, list) else _terms(left_value)
        right_terms = set(right_value) if isinstance(right_value, list) else _terms(right_value)
        scores.append(term_similarity(left_terms, right_terms))
    aggregate = term_similarity(
        proposal_terms(left, core=core), proposal_terms(right, core=core)
    )
    return round(0.65 * sum(scores) / len(scores) + 0.35 * aggregate, 6)


def _path_to(state: Mapping[str, Any], target_id: str) -> list[str]:
    by_id = {item["item_id"]: item for item in state["frontier"]["items"]}
    if target_id not in by_id:
        return ["ROOT", target_id]
    queue: list[tuple[str, list[str]]] = [("ROOT", ["ROOT"])]
    visited: set[str] = set()
    while queue:
        current, path = queue.pop(0)
        if current == target_id:
            return path
        if current in visited:
            continue
        visited.add(current)
        for dependency in by_id[current]["dependencies"]:
            queue.append((dependency, [*path, dependency]))
    return ["ROOT"] if target_id == "ROOT" else ["ROOT", target_id]


def migrate_legacy_proposal(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    required = {
        "proposal_id", "node_id", "lane", "route", "objective", "evaluator",
        "expected_delta", "changed_axis", "revival_evidence",
        "features",
    }
    condition_fields = {"return_condition", "stop_condition"} & set(value)
    if len(condition_fields) != 1:
        raise ExplorationError("legacy proposal requires exactly one return condition")
    _closed(value, required | condition_fields, "legacy discovery proposal")
    return_condition = value.get("return_condition", value.get("stop_condition"))
    route = copy.deepcopy(dict(value["route"]))
    if value["lane"] not in LANES:
        raise ExplorationError(f"unknown discovery lane {value['lane']!r}")
    success = {
        "RETRIEVE": "ADMITTED_PRODUCT",
        "REFUTE": "FALSIFICATION",
        "REDUCE": "STRICT_REDUCTION",
        "CONSTRUCT": "ADMITTED_PRODUCT",
        "TRANSFER": "STRICT_REDUCTION",
        "MEASURE": "STRICT_REDUCTION",
        "VERIFY": "ADMITTED_PRODUCT",
    }[value["lane"]]
    ceiling = {
        "RETRIEVE": "SOURCE_VERIFIED",
        "MEASURE": "COMPUTATIONAL_BOUNDED",
    }.get(value["lane"], "EXACT")
    raw_cost = (value.get("features") or {}).get("cost", 0.5)
    cost_class = "small" if raw_cost <= 0.25 else "medium" if raw_cost <= 0.6 else "large"
    packet = seal_packet({
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": value["proposal_id"],
        "target_sha256": state["target"]["canonical_sha256"],
        "base_state_sha256": state["state_sha256"],
        "node_id": value["node_id"],
        "lane": value["lane"],
        "route": route,
        "operator_id": f"legacy-{value['lane'].casefold()}",
        "invariant": route["structural_object"],
        "failure_signature": route["required_result"],
        "failure_domain": f"legacy:{value['lane'].casefold()}",
        "question": value["objective"],
        "objective": value["objective"],
        "evaluator": value["evaluator"],
        "expected_delta": value["expected_delta"],
        "return_condition": return_condition,
        "changed_axis": value["changed_axis"],
        "fixed_axes": sorted(set(route) - ({value["changed_axis"]} if value["changed_axis"] in route else set())),
        "revival_evidence": value["revival_evidence"],
        "revival_predicate": value["revival_evidence"],
        "branches": [
            {
                "outcome": success,
                "condition": f"the evaluator establishes: {value['expected_delta']}",
                "frontier_effect": "apply only the evidence-supported branch to the bound node",
            },
            {
                "outcome": "NO_PROGRESS",
                "condition": f"the episode return condition is reached without the required result: {return_condition}",
                "frontier_effect": "retain the node and record the first failing gate",
            },
        ],
        "evidence_ceiling": ceiling,
        "target_path": _path_to(state, value["node_id"]),
        "prerequisites": [
            {"statement": item, "status": "ASSUMED", "evidence_ref": None}
            for item in route["assumptions"]
        ],
        "cost_class": cost_class,
        "max_attempts": 3,
        "resource_keys": [f"legacy:{value['lane'].casefold()}"],
        "novelty_refs": [],
    })
    return validate_proposal(root, state, packet)


def proposal_draft(
    state_value: Mapping[str, Any],
    *,
    proposal_id: str,
    node_id: str,
    lane: str,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    item_ids = {item["item_id"] for item in state["frontier"]["items"]}
    if not proposal_id.strip() or node_id not in item_ids or lane not in LANES:
        raise ExplorationError("proposal draft needs an id, known node, and valid lane")
    success = {
        "RETRIEVE": "ADMITTED_PRODUCT",
        "REFUTE": "FALSIFICATION",
        "REDUCE": "STRICT_REDUCTION",
        "CONSTRUCT": "ADMITTED_PRODUCT",
        "TRANSFER": "STRICT_REDUCTION",
        "MEASURE": "STRICT_REDUCTION",
        "VERIFY": "ADMITTED_PRODUCT",
    }[lane]
    ceiling = {
        "RETRIEVE": "SOURCE_VERIFIED",
        "MEASURE": "COMPUTATIONAL_BOUNDED",
    }.get(lane, "EXACT")
    return {
        "schema": PROPOSAL_DRAFT_SCHEMA,
        "proposal_id": proposal_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "base_state_sha256": state["state_sha256"],
        "node_id": node_id,
        "lane": lane,
        "route": {
            "method_family": "",
            "mechanism": "",
            "structural_object": "",
            "required_result": "",
            "target_effect": "",
            "assumptions": [],
        },
        "operator_id": "",
        "invariant": "",
        "failure_signature": "",
        "failure_domain": "",
        "question": "",
        "objective": "",
        "evaluator": "",
        "expected_delta": "",
        "return_condition": "",
        "changed_axis": "",
        "fixed_axes": [],
        "revival_evidence": "",
        "revival_predicate": "",
        "branches": [
            {"outcome": success, "condition": "", "frontier_effect": ""},
            {"outcome": "NO_PROGRESS", "condition": "", "frontier_effect": ""},
        ],
        "evidence_ceiling": ceiling,
        "target_path": _path_to(state, node_id),
        "prerequisites": [],
        "cost_class": "small",
        "max_attempts": 2,
        "resource_keys": [],
        "novelty_refs": [],
    }


def build_proposal(
    root: Path,
    state_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        "schema", "proposal_id", "target_sha256", "base_state_sha256",
        "node_id", "lane", "route", "operator_id", "invariant",
        "failure_signature", "failure_domain", "question", "objective",
        "evaluator", "expected_delta", "return_condition", "changed_axis",
        "fixed_axes", "revival_evidence", "revival_predicate", "branches",
        "evidence_ceiling", "target_path", "prerequisites", "cost_class",
        "max_attempts", "resource_keys", "novelty_refs",
    }
    _closed(draft_value, expected, "discovery proposal draft")
    if draft_value.get("schema") != PROPOSAL_DRAFT_SCHEMA:
        raise ExplorationError("discovery proposal draft schema is invalid")
    body = copy.deepcopy(dict(draft_value))
    body["schema"] = PROPOSAL_SCHEMA
    return validate_proposal(root, state_value, seal_packet(body))


def validate_proposal(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    condition_fields = {"return_condition", "stop_condition"} & set(value)
    if len(condition_fields) != 1:
        raise ExplorationError("discovery proposal requires exactly one return condition")
    candidate = copy.deepcopy(dict(value))
    if "stop_condition" in candidate:
        candidate["return_condition"] = candidate.pop("stop_condition")
        candidate = seal_packet({
            key: item for key, item in candidate.items() if key != "payload_sha256"
        })
    try:
        packet = contracts.validate_packet(root, PROPOSAL_SCHEMA, candidate)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    if packet["target_sha256"] != state["target"]["canonical_sha256"]:
        raise ExplorationError("proposal target differs from the frozen target")
    if packet["base_state_sha256"] != state["state_sha256"]:
        raise ExplorationError("proposal was compiled against stale frontier state")
    item_ids = {item["item_id"] for item in state["frontier"]["items"]}
    if packet["node_id"] not in item_ids:
        raise ExplorationError("proposal names an unknown frontier node")
    if packet["lane"] not in LANES:
        raise ExplorationError("proposal lane is invalid")
    if packet["target_path"][0] != "ROOT" or packet["target_path"][-1] != packet["node_id"]:
        raise ExplorationError("proposal target path must run from ROOT to its bound node")
    if packet["target_path"] != _path_to(state, packet["node_id"]):
        raise ExplorationError("proposal target path does not follow the current frontier")
    outcomes = [item["outcome"] for item in packet["branches"]]
    if len(set(outcomes)) < 2 or "NO_PROGRESS" not in outcomes:
        raise ExplorationError("proposal needs distinct decisive and no-progress branches")
    if packet["evidence_ceiling"] in BOUNDED_EVIDENCE and "NEW_OBSTRUCTION" in outcomes:
        raise ExplorationError("bounded evidence cannot propose a general obstruction branch")
    if packet["changed_axis"]:
        if not packet["fixed_axes"]:
            raise ExplorationError("a changed proposal axis requires retained fixed axes")
        if packet["changed_axis"].casefold() in {item.casefold() for item in packet["fixed_axes"]}:
            raise ExplorationError("proposal changes an axis it also declares fixed")
    if bool(packet["revival_evidence"]) != bool(packet["revival_predicate"]):
        raise ExplorationError("proposal revival evidence and predicate must appear together")
    for prerequisite in packet["prerequisites"]:
        if prerequisite["status"] in {"VERIFIED", "SOURCE_VERIFIED"} and not prerequisite["evidence_ref"]:
            raise ExplorationError("verified proposal prerequisites require evidence references")
        if prerequisite["status"] == "UNAVAILABLE" and packet["lane"] not in {"RETRIEVE", "REDUCE"}:
            raise ExplorationError("an unavailable prerequisite must itself be retrieved or reduced")
    return packet


def prepare_proposal(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if value.get("schema") == PROPOSAL_SCHEMA:
        return validate_proposal(root, state_value, value)
    if value.get("schema") == PROPOSAL_DRAFT_SCHEMA:
        return build_proposal(root, state_value, value)
    return migrate_legacy_proposal(root, state_value, value)


def proposal_metrics(proposal: Mapping[str, Any], recoupling_risk: float) -> dict[str, float]:
    outcomes = {item["outcome"] for item in proposal["branches"]}
    decisive = len(outcomes - {"NO_PROGRESS", "WAITING_EXTERNAL"})
    target_leverage = 1.0 if len(proposal["target_path"]) > 1 else 0.7
    information = min(1.0, 0.35 + 0.2 * decisive + 0.08 * len(outcomes))
    checkability = EVIDENCE_RANK[proposal["evidence_ceiling"]] / 5
    reversibility = 1.0 - COST_RANK[proposal["cost_class"]] / 5
    novelty = 0.85 if proposal["novelty_refs"] else 0.45
    transfer = 0.8 if proposal["lane"] == "TRANSFER" and proposal["resource_keys"] else 0.35
    cost = COST_RANK[proposal["cost_class"]] / 4
    return {
        "target_leverage": round(target_leverage, 6),
        "expected_information_gain": round(information, 6),
        "checkability": round(checkability, 6),
        "reversibility": round(reversibility, 6),
        "novelty": round(novelty, 6),
        "transfer_value": round(transfer, 6),
        "cost": round(cost, 6),
        "recoupling_risk": round(recoupling_risk, 6),
    }


def proposal_score(metrics: Mapping[str, float]) -> float:
    value = (
        0.30 * metrics["target_leverage"]
        + 0.24 * metrics["expected_information_gain"]
        + 0.18 * metrics["checkability"]
        + 0.10 * metrics["reversibility"]
        + 0.08 * metrics["novelty"]
        + 0.05 * metrics["transfer_value"]
        - 0.10 * metrics["cost"]
        - 0.30 * metrics["recoupling_risk"]
    )
    return round(max(0.0, min(1.0, value)), 6)


RECOUPLING_THRESHOLD = 0.72


def _memory_risk(
    proposal: Mapping[str, Any], memory: Mapping[str, Any]
) -> float:
    route_fingerprint, core_fingerprint = proposal_fingerprints(proposal)
    if route_fingerprint == memory["route_fingerprint"]:
        return 1.0
    if core_fingerprint == memory["core_fingerprint"]:
        return 0.95
    projection = _semantic_projection(proposal)
    scores = {
        "operator": 1.0 if projection["operator_id"] == memory["operator_id"].casefold() else 0.0,
        "mechanism": term_similarity(set(projection["mechanism"]), _terms(memory["mechanism"])),
        "invariant": term_similarity(set(projection["invariant"]), _terms(memory["invariant"])),
        "result": term_similarity(
            set(projection["required_result"]),
            _terms(memory["required_result"], memory["failure_signature"]),
        ),
        "failure": term_similarity(
            _terms(projection["failure_domain"]), _terms(memory["failure_domain"])
        ),
    }
    return round(
        0.10 * scores["operator"]
        + 0.28 * scores["mechanism"]
        + 0.24 * scores["invariant"]
        + 0.25 * scores["result"]
        + 0.13 * scores["failure"],
        6,
    )


def proposal_portfolio(
    proposals: list[Mapping[str, Any]], route_memory: list[Mapping[str, Any]]
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for proposal in proposals:
        risks = [
            (item["route_fingerprint"], _memory_risk(proposal, item))
            for item in route_memory
        ]
        risk = max((item[1] for item in risks), default=0.0)
        recoupled = sorted(
            fingerprint for fingerprint, value in risks
            if value >= RECOUPLING_THRESHOLD
        )
        revived = bool(
            recoupled and proposal["revival_predicate"] and proposal["revival_evidence"]
        )
        disposition = "REVIVED" if revived else "RECOUPLED" if recoupled else "ELIGIBLE"
        metrics = proposal_metrics(proposal, risk)
        route_fingerprint, core_fingerprint = proposal_fingerprints(proposal)
        entries.append({
            "proposal_id": proposal["proposal_id"],
            "route_fingerprint": route_fingerprint,
            "core_fingerprint": core_fingerprint,
            "method_family": proposal["route"]["method_family"],
            "mechanism_fingerprint": digest_value(
                sorted(_terms(proposal["route"]["mechanism"]))
            ),
            "recouples_to": recoupled,
            "disposition": disposition,
            "metrics": metrics,
            "score": proposal_score(metrics),
        })
    eligible = [item for item in entries if item["disposition"] != "RECOUPLED"]
    ranked = sorted(eligible, key=lambda item: (-item["score"], item["proposal_id"]))
    method_families = sorted({
        " ".join(item["method_family"].casefold().split()) for item in eligible
    })
    mechanisms = sorted({item["mechanism_fingerprint"] for item in eligible})
    return {
        "entries": entries,
        "recommended_proposal_id": ranked[0]["proposal_id"] if ranked else None,
        "represented_method_families": method_families,
        "represented_mechanisms": mechanisms,
        "diversity_floor_met": (
            len(eligible) <= 1 or (len(method_families) >= 2 and len(mechanisms) >= 2)
        ),
        "recoupling_threshold": RECOUPLING_THRESHOLD,
    }


def proposal_set_sha256(proposals: list[Mapping[str, Any]]) -> str | None:
    return digest_value(sorted(item["payload_sha256"] for item in proposals)) if proposals else None


def _frontier_model(state: Mapping[str, Any]) -> dict[str, Any]:
    items = {
        item["item_id"]: copy.deepcopy(dict(item))
        for item in state["frontier"]["items"]
    }
    reachable: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in reachable:
            return
        reachable.add(identifier)
        for dependency in items[identifier]["dependencies"]:
            if dependency in items:
                visit(dependency)

    visit("ROOT")
    orphaned = set(items) - reachable
    if orphaned:
        nested = {
            dependency
            for identifier in orphaned
            for dependency in items[identifier]["dependencies"]
            if dependency in orphaned
        }
        component_roots = sorted(orphaned - nested)
        items["ROOT"]["dependencies"] = [
            *items["ROOT"]["dependencies"],
            *(component_roots or sorted(orphaned)),
        ]
    model_state = copy.deepcopy(dict(state))
    model_state["frontier"] = copy.deepcopy(dict(state["frontier"]))
    model_state["frontier"]["items"] = list(items.values())
    nodes = []
    edges = []
    for item in items.values():
        path = _path_to(model_state, item["item_id"])
        nodes.append({
            "node_id": item["item_id"],
            "kind": item["kind"] if item["kind"] in FRONTIER_KINDS else "OPEN_CORE",
            "statement": item["statement"],
            "status": item["status"],
            "dependencies": list(item["dependencies"]),
            "evidence_refs": list(item["evidence_refs"]),
            "target_path": path,
            "relation_to_parent": "ROOT" if item["item_id"] == "ROOT" else "REDUCES_TO",
        })
        for dependency in item["dependencies"]:
            edges.append({
                "from_id": item["item_id"],
                "to_id": dependency,
                "relation": "REDUCES_TO",
                "evidence_refs": [],
            })
    active = [
        identifier
        for identifier in state["frontier"]["active"]
        if items[identifier]["status"] == "OPEN"
        and not any(items[item]["status"] == "OPEN" for item in items[identifier]["dependencies"])
    ]
    if not active:
        active = [
            identifier for identifier, item in items.items()
            if item["status"] == "OPEN"
            and not any(items[dependency]["status"] == "OPEN" for dependency in item["dependencies"])
        ]
    return {
        "nodes": sorted(nodes, key=lambda item: item["node_id"]),
        "edges": sorted(edges, key=lambda item: (item["from_id"], item["to_id"])),
        "minimal_open_core_ids": sorted(set(active)),
        "frontier_measure": len(set(active)),
        "root_only_exception": "",
    }


def _domain_controls(state: Mapping[str, Any]) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    if "maths" in state["domains"]:
        controls["maths"] = {
            "quantifier_audit": "UNRECORDED",
            "implication_direction": "UNRECORDED",
            "finite_vs_general": "SEPARATE",
            "fixed_structure": "UNRECORDED",
        }
    if "bio" in state["domains"]:
        controls["bio"] = {
            "claim_class": "UNRECORDED",
            "causal_estimand": "UNRECORDED",
            "denominator": "UNRECORDED",
            "experimental_unit": "UNRECORDED",
            "intervention": "UNRECORDED",
            "generalization_population": "UNRECORDED",
        }
    return controls


def _scope_list(scope: Mapping[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = scope.get(key)
        if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
            return list(dict.fromkeys(item.strip() for item in value))
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _baseline_target_acceptance(
    state: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    statement = state["target"]["statement"]
    clauses = [{
        "clause_id": "ENDPOINT-EXACT",
        "kind": "ENDPOINT",
        "statement": statement,
        "polarity": "MUST_HOLD",
        "verification": "Match the complete frozen statement, not a nearby variant or local consequence.",
    }]
    if state["mode"] == "OPEN_DISCOVERY":
        clauses.append({
            "clause_id": "QUANTIFIERS-EXACT",
            "kind": "QUANTIFIER",
            "statement": "Every quantifier, range, and uniformity requirement in the frozen target is retained.",
            "polarity": "MUST_HOLD",
            "verification": "Audit witnesses, exceptional cases, ranges, and quantifier order against the frozen statement.",
        })
    if "maths" in state["domains"] and state["mode"] == "OPEN_DISCOVERY":
        clauses.extend([
            {
                "clause_id": "MATHS-STRUCTURE",
                "kind": "DEFINITION",
                "statement": "Every object, operation, relation, recurrence, and fixed parameter in the frozen target remains unchanged.",
                "polarity": "MUST_HOLD",
                "verification": "Compare the candidate structure symbol by symbol with the frozen target; a valid result for a broader or neighbouring class is not target closure.",
            },
            {
                "clause_id": "MATHS-BOUNDARY",
                "kind": "BOUNDARY",
                "statement": "Initial values, endpoints, degenerate cases, and exceptional parameters are part of the claim unless explicitly excluded.",
                "polarity": "MUST_HOLD",
                "verification": "Check every boundary case separately and cite exact derivation or verification evidence.",
            },
        ])
    if "bio" in state["domains"] and state["mode"] == "OPEN_DISCOVERY":
        clauses.extend([
            {
                "clause_id": "BIO-EVIDENCE-STANDARD",
                "kind": "EVIDENCE_STANDARD",
                "statement": "The claimed biological evidence class matches the design, controls, replication, and uncertainty actually available.",
                "polarity": "MUST_HOLD",
                "verification": "Audit experimental unit, denominator, controls, uncertainty, and causal-identification limits.",
            },
            {
                "clause_id": "BIO-GENERALIZATION",
                "kind": "GENERALIZATION",
                "statement": "The claimed population, context, organism, and intervention scope do not exceed the observed or justified scope.",
                "polarity": "MUST_HOLD",
                "verification": "State the transport boundary and test each generalization axis independently.",
            },
        ])
    distinctions: list[dict[str, str]] = []
    if target_semantics.NEGATION_PATTERN.search(statement):
        clauses.append({
            "clause_id": "EXCLUSION-EXACT",
            "kind": "EXCLUSION",
            "statement": "Every negated, forbidden, absent, or mechanism-excluding condition in the frozen target holds as stated.",
            "polarity": "MUST_HOLD",
            "verification": "Establish the exclusion itself; absence from one derivation, sample, or search is not evidence of nonexistence.",
        })
        distinctions.append({
            "distinction_id": "USE-VS-EXISTENCE",
            "left": "A presented derivation, construction, or search does not use the excluded mechanism.",
            "right": "No admissible explanation or instance using the excluded mechanism exists in the target scope.",
            "relation": "NOT_EQUIVALENT",
            "closure_rule": "The left statement cannot discharge the right statement without an independent nonexistence argument.",
        })
    return clauses, distinctions


def _last_return(state: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    last = _last_event(state)
    if last is None:
        return None
    if last["kind"] == "EPISODE_RETURNED":
        delta = last["payload"]["delta"]
        return delta["payload_sha256"], delta
    if last["kind"] == "ROUND_RETURNED":
        delta = last["payload"]["round_delta"]
        return delta["payload_sha256"], delta
    return None


def _issued_node_ids(state: Mapping[str, Any]) -> list[str]:
    """Return worker targets in replay order without trusting mutable summaries."""
    result: list[str] = []
    for event in state.get("events", []):
        if event["kind"] == "EPISODE_ISSUED":
            result.append(event["payload"]["episode"]["node_id"])
        elif event["kind"] == "ROUND_ISSUED":
            result.extend(
                item["episode"]["node_id"]
                for item in event["payload"]["round"]["episodes"]
            )
    return result


def _delta_evidence_ceiling(delta: Mapping[str, Any]) -> str:
    children = delta.get("deltas")
    if isinstance(children, list) and children:
        classes = [_delta_evidence_ceiling(item) for item in children]
        return min(classes, key=lambda item: EVIDENCE_RANK.get(item, 0))
    reasoning_state = delta.get("reasoning")
    if not isinstance(reasoning_state, Mapping):
        return "UNKNOWN"
    claims = {item["claim_id"]: item for item in reasoning_state.get("claims", [])}
    closure = [claims[item] for item in reasoning_state.get("closure_candidate_ids", []) if item in claims]
    if not closure:
        classes = [item.get("epistemic_class", "UNKNOWN") for item in claims.values()]
    else:
        classes = [item.get("epistemic_class", "UNKNOWN") for item in closure]
    if not classes:
        return "UNKNOWN"
    result = min(classes, key=lambda item: EVIDENCE_RANK.get(item, 0))
    return result if result in EVIDENCE_RANK else "UNKNOWN"


def _return_assessment(state: Mapping[str, Any]) -> dict[str, Any] | None:
    returned = _last_return(state)
    if returned is None:
        return None
    return_ref, delta = returned
    outcome = delta.get("outcome", delta.get("aggregate_outcome", "NO_PROGRESS"))
    impact = {
        "ADMITTED_PRODUCT": "LOCAL_PRODUCT",
        "CANDIDATE_PRODUCT": "LOCAL_PRODUCT",
        "STRICT_REDUCTION": "CORE_SHARPENED",
        "FALSIFICATION": "TARGET_PROGRESS",
        "TARGET_FALSIFIED": "TARGET_PROGRESS",
        "ROUTE_REFUTED": "ROUTE_REFUTED",
        "NEW_OBSTRUCTION": "CORE_SHARPENED",
        "METHOD_BARRIER": "CORE_SHARPENED",
        "CORE_SHARPENED": "CORE_SHARPENED",
        "POSITIVE_SIGNAL": "EMPIRICAL_SIGNAL",
        "WAITING_EXTERNAL": "EXTERNAL_WAIT",
        "CONFLICT": "CONFLICT",
    }.get(outcome, "NO_PROGRESS")
    reasoning_states = (
        [item.get("reasoning") or {} for item in delta.get("deltas", [])]
        if delta.get("deltas") else [delta.get("reasoning") or {}]
    )
    contradictions = sorted({
        item["contradiction_id"]
        for reasoning_state in reasoning_states
        for item in reasoning_state.get("contradictions", [])
        if item.get("status") == "OPEN"
    })
    affected = [delta["node_id"]] if delta.get("node_id") else []
    if not affected and state["route_attempts"]:
        episode_id = delta.get("episode_id")
        for event in reversed(state["events"]):
            if event["kind"] == "EPISODE_ISSUED":
                episode = event["payload"]["episode"]
                if episode.get("episode_id") == episode_id:
                    affected = [episode["node_id"]]
                    break
    if not affected and delta.get("round_id"):
        for event in reversed(state["events"]):
            if event["kind"] == "ROUND_ISSUED":
                round_packet = event["payload"]["round"]
                if round_packet.get("round_id") == delta["round_id"]:
                    affected = sorted({
                        item["episode"]["node_id"] for item in round_packet["episodes"]
                    })
                    break
    return {
        "return_ref": return_ref,
        "claimed_outcome": outcome,
        "impact": impact,
        "evidence_ceiling": _delta_evidence_ceiling(delta),
        "affected_node_ids": affected,
        "accepted_claim_ids": [],
        "rejected_claim_ids": [],
        "unresolved_contradiction_ids": contradictions,
        "route_disposition": (
            "WAITING" if outcome == "WAITING_EXTERNAL"
            else "REFRAME_REQUIRED" if outcome in {
                "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED"
            }
            else "LIVE"
        ),
        "obstruction_disposition": (
            "DEFER" if outcome in {"NEW_OBSTRUCTION", "METHOD_BARRIER"}
            else "NOT_APPLICABLE"
        ),
        "rationale": "Explorer review is required; the Researcher outcome is not self-admitting.",
    }


def _route_memory(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    disposition_by_return: dict[str, str] = {}
    for event in state["events"]:
        if event["kind"] != "ARBITRATION_RECORDED":
            continue
        arbitration = event["payload"]["arbitration"]
        route = arbitration.get("selected_route")
        if route is not None:
            selected[route["route_fingerprint"]] = route
        if arbitration.get("return_ref"):
            disposition_by_return[arbitration["return_ref"]] = arbitration["route_disposition"]
    obstructions = {
        item["route_fingerprint"]: item for item in state["frontier"]["obstructions"]
    }
    memory_by_route: dict[str, dict[str, Any]] = {}
    route_order: list[str] = []
    for attempt in state["route_attempts"][-FIXED_LIMITS["max_route_memory"]:]:
        route = selected.get(attempt["route_fingerprint"])
        obstruction = obstructions.get(attempt["route_fingerprint"], {})
        record = {
            "route_fingerprint": attempt["route_fingerprint"],
            "core_fingerprint": attempt["core_fingerprint"],
            "operator_id": route["operator_id"] if route else "legacy-unknown",
            "mechanism": route["mechanism"] if route else "legacy semantic route",
            "invariant": route["invariant"] if route else "legacy unknown invariant",
            "required_result": route["required_result"] if route else "legacy unknown result",
            "failure_signature": route["failure_signature"] if route else "legacy unknown failure",
            "failure_domain": route["failure_domain"] if route else "legacy:unknown",
            "outcome": attempt["outcome"],
            "disposition": attempt.get("route_disposition") or disposition_by_return.get(
                attempt["delta_sha256"],
                "EXHAUSTED" if attempt.get("exhausted") else "LIVE",
            ),
            "revival_predicate": (
                obstruction.get("revival_condition")
                or (route.get("revival_predicate", "") if route else "")
            ),
            "evidence_refs": list(obstruction.get("evidence_refs", [])),
        }
        fingerprint = attempt["route_fingerprint"]
        if fingerprint in memory_by_route:
            route_order.remove(fingerprint)
        route_order.append(fingerprint)
        memory_by_route[fingerprint] = record
    return [memory_by_route[item] for item in route_order]


def draft(
    root: Path,
    state_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]] | None = None,
    prior_explorer_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = kernel.validate_state(state_value)
    contract = build_contract(state)
    prepared = [prepare_proposal(root, state, value) for value in (proposals or [])]
    scope = state["target"].get("scope") or {}
    acceptance_clauses, semantic_distinctions = _baseline_target_acceptance(state)
    quantifiers = _scope_list(scope, "quantifiers")
    if state["mode"] == "OPEN_DISCOVERY" and not quantifiers:
        quantifiers = [
            "Retain every quantifier, range, and uniformity requirement in the frozen target."
        ]
    scope_boundaries = _scope_list(scope, "boundaries", "scope_boundaries")
    if "maths" in state["domains"] and state["mode"] == "OPEN_DISCOVERY" and not scope_boundaries:
        scope_boundaries = [
            "Initial values, endpoints, degenerate cases, and exceptional parameters remain in scope."
        ]
    target_model = {
        "frozen": True,
        "interpretation": state["target"]["statement"],
        "definitions": _scope_list(scope, "definitions"),
        "quantifiers": quantifiers,
        "assumptions": _scope_list(scope, "assumptions", "given"),
        "scope_boundaries": scope_boundaries,
        "ambiguities": [],
        "variant_refs": [],
        "acceptance_clauses": acceptance_clauses,
        "semantic_distinctions": semantic_distinctions,
        "domain_controls": _domain_controls(state),
    }
    source_coverage = {
        "status": "NOT_STARTED",
        "source_map_ref": None,
        "queries": [],
        "unavailable_refs": [],
        "correction_refs": [],
        "unresolved": [],
        "absence_claim_prohibited": True,
    }
    if prior_explorer_value is not None:
        try:
            prior = contracts.validate_packet(root, STATE_SCHEMA, prior_explorer_value)
        except contracts.ContractError as exc:
            raise ExplorationError(str(exc)) from exc
        if prior["target_sha256"] != state["target"]["canonical_sha256"]:
            raise ExplorationError("prior Explorer state belongs to another target")
        if prior["base_revision"] > state["revision"]:
            raise ExplorationError("prior Explorer state comes from a future revision")
        if prior["target_model"]["interpretation"] != state["target"]["statement"]:
            raise ExplorationError("prior Explorer interpretation differs from the frozen target")
        _validate_target_model(prior, state)
        _validate_source_coverage(prior)
        target_model = copy.deepcopy(prior["target_model"])
        source_coverage = copy.deepcopy(prior["source_coverage"])
    route_memory = _route_memory(state)
    return {
        "schema": DRAFT_SCHEMA,
        "explorer_id": f"explorer:{state['kernel_id']}:{state['revision']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "phase": contract["phase"],
        "target_model": target_model,
        "source_coverage": source_coverage,
        "frontier_model": _frontier_model(state),
        "route_memory": route_memory,
        "proposal_refs": [
            {"proposal_id": item["proposal_id"], "payload_sha256": item["payload_sha256"]}
            for item in prepared
        ],
        "portfolio": proposal_portfolio(prepared, route_memory),
        "return_assessment": _return_assessment(state),
        "decision": {
            "action": "UNDECIDED",
            "selected_proposal_id": None,
            "basis_refs": [],
            "alternatives": [],
            "changed_axis": "",
            "reason": "",
        },
        "open_contradictions": [],
        "stop_review_ref": None,
        "first_failing_gate": "",
    }, prepared


def _validate_target_model(packet: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    model = packet["target_model"]
    if model["interpretation"] != state["target"]["statement"]:
        raise ExplorationError("Explorer target interpretation differs from the frozen statement")
    ambiguities = _unique(model["ambiguities"], "ambiguity_id", "target ambiguity")
    if len(ambiguities) > FIXED_LIMITS["max_target_ambiguities"]:
        raise ExplorationError("Explorer target model exceeds the ambiguity limit")
    for ambiguity in ambiguities.values():
        if ambiguity["status"] == "BLOCKER" and ambiguity["resolution"]:
            raise ExplorationError("an unresolved target ambiguity cannot claim a resolution")
        if ambiguity["status"] != "BLOCKER" and not ambiguity["resolution"].strip():
            raise ExplorationError("a resolved target ambiguity requires its retained reading")
    try:
        target_semantics.build(
            Path(__file__).resolve().parents[2], state, model
        )
    except target_semantics.TargetSemanticsError as exc:
        raise ExplorationError(str(exc)) from exc


def _validate_source_coverage(packet: Mapping[str, Any]) -> None:
    coverage = packet["source_coverage"]
    queries = _unique(coverage["queries"], "query_id", "source query")
    if len(queries) > FIXED_LIMITS["max_source_queries"]:
        raise ExplorationError("Explorer source query ledger exceeds its limit")
    for query in queries.values():
        if not query["evidence_refs"]:
            raise ExplorationError("a source query requires a retrieval or failure receipt")
    if coverage["status"] == "NOT_STARTED" and queries:
        raise ExplorationError("source coverage cannot be NOT_STARTED after recorded queries")
    if coverage["status"] == "BOUNDED_COMPLETE" and not queries:
        raise ExplorationError("bounded-complete source coverage requires a query ledger")
    if coverage["status"] != "NOT_STARTED" and not coverage["source_map_ref"]:
        raise ExplorationError("started source coverage requires a source-map reference")


def _entry_refs(entry: Mapping[str, Any]) -> set[str]:
    digest = entry["retrieved_sha256"]
    return {entry["source_id"], digest, f"sha256:{digest}"}


def source_evidence_refs(
    source_map: Mapping[str, Any] | None,
    *,
    statuses: set[str] | None = None,
) -> list[str]:
    if source_map is None:
        return []
    return sorted({
        reference
        for entry in source_map["entries"]
        if statuses is None or entry["status"] in statuses
        for reference in {
            *_entry_refs(entry),
            f"{entry['source_id']}@sha256:{entry['retrieved_sha256']}",
        }
    })


def _validate_source_entry_provenance(entries: Mapping[str, Mapping[str, Any]]) -> None:
    for entry in entries.values():
        source_type = re.sub(r"[^A-Z0-9]+", "_", entry["source_type"].upper()).strip("_")
        locator = entry["locator"].replace("\\", "/").casefold()
        basename = locator.rsplit("/", 1)[-1]
        if source_type in PROHIBITED_SOURCE_TYPES or basename in PROHIBITED_SOURCE_BASENAMES:
            raise ExplorationError(
                f"source-map entry {entry['source_id']!r} is Explorer-authored output, not source evidence"
            )


def source_map_draft(
    state_value: Mapping[str, Any],
    *,
    source_map_id: str,
    checked_at: str,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if not source_map_id.strip() or not checked_at.strip():
        raise ExplorationError("source-map id and checked-at timestamp are required")
    return {
        "schema": SOURCE_MAP_DRAFT_SCHEMA,
        "source_map_id": source_map_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "entries": [],
        "contradictions": [],
        "unresolved": ["complete the scoped source review and add retrieval receipts"],
        "checked_at": checked_at,
    }


def build_source_map(
    root: Path,
    state_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "schema", "source_map_id", "target_sha256", "entries",
        "contradictions", "unresolved", "checked_at",
    }
    _closed(draft_value, required, "source-map draft")
    if draft_value.get("schema") != SOURCE_MAP_DRAFT_SCHEMA:
        raise ExplorationError("source-map draft schema is invalid")
    state = kernel.validate_state(state_value)
    body = copy.deepcopy(dict(draft_value))
    body["schema"] = SOURCE_MAP_SCHEMA
    try:
        packet = contracts.validate_packet(root, SOURCE_MAP_SCHEMA, seal_packet(body))
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    if packet["target_sha256"] != state["target"]["canonical_sha256"]:
        raise ExplorationError("source map belongs to another frozen target")
    entries = _unique(packet["entries"], "source_id", "source-map entry")
    if not entries:
        raise ExplorationError(
            "source map requires at least one retrieved source or scoped search receipt"
        )
    _validate_source_entry_provenance(entries)
    return packet


def _validate_source_binding(
    root: Path,
    packet: Mapping[str, Any],
    state: Mapping[str, Any],
    source_map_value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    coverage = packet["source_coverage"]
    if coverage["status"] == "NOT_STARTED":
        if source_map_value is not None:
            raise ExplorationError(
                "NOT_STARTED source coverage cannot carry an unreferenced source map"
            )
        return None
    if source_map_value is None:
        raise ExplorationError(
            "started source coverage requires the exact sealed source-map packet"
        )
    try:
        source_map = contracts.validate_packet(root, SOURCE_MAP_SCHEMA, source_map_value)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    if source_map["target_sha256"] != state["target"]["canonical_sha256"]:
        raise ExplorationError("Explorer source map belongs to another frozen target")
    if coverage["source_map_ref"] != source_map["payload_sha256"]:
        raise ExplorationError("Explorer source-map reference does not bind supplied bytes")

    entries = _unique(source_map["entries"], "source_id", "source-map entry")
    if not entries:
        raise ExplorationError("started source coverage requires at least one source receipt")
    _validate_source_entry_provenance(entries)

    unavailable = sorted(
        entry["source_id"] for entry in entries.values() if entry["status"] == "UNAVAILABLE"
    )
    corrected = sorted(
        entry["source_id"] for entry in entries.values() if entry["status"] == "CORRECTED"
    )
    if sorted(coverage["unavailable_refs"]) != unavailable:
        raise ExplorationError("Explorer unavailable refs differ from the sealed source map")
    if sorted(coverage["correction_refs"]) != corrected:
        raise ExplorationError("Explorer correction refs differ from the sealed source map")
    if sorted(coverage["unresolved"]) != sorted(source_map["unresolved"]):
        raise ExplorationError("Explorer source gaps differ from the sealed source map")

    recognized = {source_map["payload_sha256"]}
    refs_by_id: dict[str, set[str]] = {}
    for identifier, entry in entries.items():
        refs_by_id[identifier] = _entry_refs(entry)
        recognized.update(refs_by_id[identifier])
    covered_ids: set[str] = set()
    statuses_by_result = {
        "FOUND": {"ESTABLISHED", "CONDITIONAL", "BOUNDED", "DISPUTED", "CORRECTED", "OPEN"},
        "NOT_FOUND_WITHIN_SCOPE": {"OPEN", "UNAVAILABLE"},
        "CONTRADICTED": {"DISPUTED"},
        "CORRECTED": {"CORRECTED"},
        "UNAVAILABLE": {"UNAVAILABLE"},
    }
    for query in coverage["queries"]:
        unknown = set(query["evidence_refs"]) - recognized
        if unknown:
            raise ExplorationError(
                f"source query {query['query_id']!r} cites unbound evidence refs: {sorted(unknown)}"
            )
        matched = {
            identifier
            for identifier, references in refs_by_id.items()
            if references & set(query["evidence_refs"])
        }
        if not matched:
            raise ExplorationError(
                f"source query {query['query_id']!r} lacks an entry-level retrieval receipt"
            )
        allowed_statuses = statuses_by_result[query["result"]]
        if not any(entries[identifier]["status"] in allowed_statuses for identifier in matched):
            raise ExplorationError(
                f"source query {query['query_id']!r} result conflicts with its source-map entries"
            )
        covered_ids.update(matched)
    if coverage["status"] == "BOUNDED_COMPLETE":
        if source_map["unresolved"] or unavailable:
            raise ExplorationError(
                "bounded-complete source coverage cannot retain unavailable or unresolved source work"
            )
        if covered_ids != set(entries):
            raise ExplorationError(
                "bounded-complete source coverage must account for every source-map entry"
            )
    return source_map


def _validate_frontier(packet: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    model = packet["frontier_model"]
    nodes = _unique(model["nodes"], "node_id", "frontier node")
    if len(nodes) > FIXED_LIMITS["max_frontier_nodes"]:
        raise ExplorationError("Explorer frontier exceeds its node limit")
    if "ROOT" not in nodes or nodes["ROOT"]["kind"] != "TARGET":
        raise ExplorationError("Explorer frontier requires one ROOT target node")
    if nodes["ROOT"]["statement"] != state["target"]["statement"]:
        raise ExplorationError("Explorer ROOT differs from the frozen target")
    existing = {item["item_id"]: item for item in state["frontier"]["items"]}
    for identifier in set(nodes) & set(existing):
        node, item = nodes[identifier], existing[identifier]
        immutable = {
            "kind": item["kind"],
            "statement": item["statement"],
            "status": item["status"],
            "evidence_refs": item["evidence_refs"],
        }
        for field, expected in immutable.items():
            if node[field] != expected:
                raise ExplorationError(
                    f"Explorer cannot rewrite frontier {identifier!r} field {field!r}"
                )
    for node in nodes.values():
        if node["kind"] not in FRONTIER_KINDS or node["status"] not in kernel.STATUSES:
            raise ExplorationError(f"frontier node {node['node_id']!r} has an invalid kind or status")
        missing = set(node["dependencies"]) - set(nodes)
        if node["node_id"] in node["dependencies"] or missing:
            raise ExplorationError(f"frontier node {node['node_id']!r} has invalid dependencies")
        if node["node_id"] == "ROOT":
            if node["target_path"] != ["ROOT"] or node["relation_to_parent"] != "ROOT":
                raise ExplorationError("ROOT target path or relation is invalid")
        else:
            if node["target_path"][0] != "ROOT" or node["target_path"][-1] != node["node_id"]:
                raise ExplorationError(f"frontier node {node['node_id']!r} lacks a target path")
            if node["relation_to_parent"] == "ROOT":
                raise ExplorationError("only ROOT may use the ROOT relation")
        if node["kind"] == "EMPIRICAL_SIGNAL" and node["relation_to_parent"] != "EMPIRICAL_ONLY":
            raise ExplorationError("empirical frontier nodes must remain EMPIRICAL_ONLY")
    edges = _unique(
        [dict(item, edge_id=f"{item['from_id']}->{item['to_id']}") for item in model["edges"]],
        "edge_id",
        "frontier edge",
    )
    dependency_pairs = {
        (node["node_id"], dependency)
        for node in nodes.values()
        for dependency in node["dependencies"]
    }
    edge_pairs = {(item["from_id"], item["to_id"]) for item in edges.values()}
    if edge_pairs != dependency_pairs:
        raise ExplorationError("frontier typed edges and dependency links differ")
    for edge in edges.values():
        if edge["from_id"] not in nodes or edge["to_id"] not in nodes or edge["relation"] not in RELATIONS:
            raise ExplorationError("frontier edge names an unknown node or relation")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(identifier: str) -> None:
        if identifier in visiting:
            raise ExplorationError(f"frontier dependency cycle passes through {identifier!r}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in nodes[identifier]["dependencies"]:
            walk(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    walk("ROOT")
    if set(nodes) - visited:
        raise ExplorationError(f"frontier has nodes without a target path: {sorted(set(nodes) - visited)}")
    for node in nodes.values():
        path = node["target_path"]
        if any((left, right) not in dependency_pairs for left, right in zip(path, path[1:])):
            raise ExplorationError(f"frontier node {node['node_id']!r} has a stale target path")
    active = model["minimal_open_core_ids"]
    if len(active) != len(set(active)) or set(active) - set(nodes):
        raise ExplorationError("minimal open core names unknown or duplicate nodes")
    for identifier in active:
        node = nodes[identifier]
        if node["status"] != "OPEN":
            raise ExplorationError("minimal open core contains a non-open node")
        if any(nodes[item]["status"] == "OPEN" for item in node["dependencies"]):
            raise ExplorationError("minimal open core contains a node with a smaller open dependency")
    if model["frontier_measure"] != len(active):
        raise ExplorationError("frontier measure must equal the minimal open-core count")
    return nodes


def _collect_declared_evidence(value: Any, refs: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "evidence_refs" and isinstance(item, list):
                refs.update(reference for reference in item if isinstance(reference, str))
            elif key in {
                "payload_sha256", "evidence_sha256", "admission_ref",
                "independent_review", "invalidation_ref",
            } and isinstance(item, str):
                refs.add(item)
            _collect_declared_evidence(item, refs)
    elif isinstance(value, list):
        for item in value:
            _collect_declared_evidence(item, refs)


def _allowed_control_refs(
    state: Mapping[str, Any],
    source_map: Mapping[str, Any] | None,
    proposals: list[Mapping[str, Any]],
    stop_review: Mapping[str, Any] | None = None,
) -> set[str]:
    refs = {
        state["state_sha256"], state["target"]["canonical_sha256"],
        *(item["payload_sha256"] for item in proposals),
    }
    _collect_declared_evidence(state, refs)
    if source_map is not None:
        refs.add(source_map["payload_sha256"])
        for entry in source_map["entries"]:
            refs.update(_entry_refs(entry))
    if stop_review is not None:
        refs.add(stop_review["payload_sha256"])
    return refs


def _validate_role_evidence_refs(
    packet: Mapping[str, Any],
    state: Mapping[str, Any],
    source_map: Mapping[str, Any] | None,
    proposals: list[Mapping[str, Any]],
    stop_review: Mapping[str, Any] | None = None,
) -> None:
    allowed = _allowed_control_refs(state, source_map, proposals, stop_review)
    existing = {item["item_id"] for item in state["frontier"]["items"]}
    for node in packet["frontier_model"]["nodes"]:
        if node["node_id"] not in existing:
            unknown = set(node["evidence_refs"]) - allowed
            if unknown:
                raise ExplorationError(
                    f"new frontier node {node['node_id']!r} cites Explorer-local or unbound evidence"
                )
    for edge in packet["frontier_model"]["edges"]:
        unknown = set(edge["evidence_refs"]) - allowed
        if unknown:
            raise ExplorationError("frontier relation cites Explorer-local or unbound evidence")
    for proposal in proposals:
        proposal_refs = set(proposal["novelty_refs"])
        proposal_refs.update(
            item["evidence_ref"]
            for item in proposal["prerequisites"]
            if item["evidence_ref"] is not None
        )
        if proposal_refs - allowed:
            raise ExplorationError(
                f"proposal {proposal['proposal_id']!r} cites Explorer-local or unbound evidence"
            )
    if set(packet["decision"]["basis_refs"]) - allowed:
        raise ExplorationError(
            "Explorer decision basis must use sealed state, source, proposal, return, or review refs"
        )


def _validate_route_memory(packet: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    memory = packet["route_memory"]
    if len(memory) > FIXED_LIMITS["max_route_memory"]:
        raise ExplorationError("Explorer route memory exceeds its limit")
    fingerprints = [item["route_fingerprint"] for item in memory]
    if len(fingerprints) != len(set(fingerprints)):
        raise ExplorationError("Explorer route memory repeats a semantic route")
    for item in memory:
        if item["disposition"] == "EXHAUSTED" and not item["revival_predicate"].strip():
            raise ExplorationError("an exhausted route requires a checkable revival predicate")
    if memory != _route_memory(state):
        raise ExplorationError(
            "Explorer route memory is derived from kernel attempts and cannot be invented or edited"
        )


def _validate_return(packet: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    phase = packet["phase"]
    assessment = packet["return_assessment"]
    returned = _last_return(state)
    if phase == "RETURN_ARBITRATION":
        if returned is None or assessment is None:
            raise ExplorationError("return arbitration requires the exact returned delta")
        return_ref, delta = returned
        outcome = delta.get("outcome", delta.get("aggregate_outcome", "NO_PROGRESS"))
        if assessment["return_ref"] != return_ref or assessment["claimed_outcome"] != outcome:
            raise ExplorationError("Explorer return assessment is not bound to the latest return")
        if not assessment["affected_node_ids"]:
            raise ExplorationError("return assessment must identify its affected frontier node")
        if assessment["impact"] not in RETURN_IMPACTS.get(outcome, {"CONFLICT"}):
            raise ExplorationError("Explorer impact classification conflicts with the returned outcome")
        actual_ceiling = _delta_evidence_ceiling(delta)
        if assessment["evidence_ceiling"] != actual_ceiling:
            raise ExplorationError("Explorer evidence ceiling differs from the returned claim graph")
        if assessment["unresolved_contradiction_ids"] != sorted(set(assessment["unresolved_contradiction_ids"])):
            raise ExplorationError("return contradictions must be unique and sorted")
        frontier_ids = {item["item_id"] for item in state["frontier"]["items"]}
        if set(assessment["affected_node_ids"]) - frontier_ids:
            raise ExplorationError("return assessment names an unknown affected frontier node")
        reasoning_states = (
            [item.get("reasoning") or {} for item in delta.get("deltas", [])]
            if delta.get("deltas") else [delta.get("reasoning") or {}]
        )
        claims = {
            item["claim_id"]: item
            for reasoning_state in reasoning_states
            for item in reasoning_state.get("claims", [])
        }
        accepted = assessment["accepted_claim_ids"]
        rejected = assessment["rejected_claim_ids"]
        if len(accepted) != len(set(accepted)) or len(rejected) != len(set(rejected)):
            raise ExplorationError("return claim dispositions must be unique")
        if set(accepted) & set(rejected) or (set(accepted) | set(rejected)) - set(claims):
            raise ExplorationError("return claim dispositions conflict or name unknown claims")
        if any(claims[item]["status"] != "SUPPORTED" for item in accepted):
            raise ExplorationError("Explorer accepted a claim not marked SUPPORTED by its evidence graph")
        if any(claims[item]["status"] != "REFUTED" for item in rejected):
            raise ExplorationError("Explorer rejected a claim not marked REFUTED by its evidence graph")
        actual_open = sorted({
            item["contradiction_id"]
            for reasoning_state in reasoning_states
            for item in reasoning_state.get("contradictions", [])
            if item.get("status") == "OPEN"
        })
        if assessment["unresolved_contradiction_ids"] != actual_open:
            raise ExplorationError("Explorer suppressed or invented an open return contradiction")
        if actual_ceiling in BOUNDED_EVIDENCE:
            if assessment["route_disposition"] == "EXHAUSTED":
                raise ExplorationError("bounded evidence cannot exhaust a general route")
            if assessment["obstruction_disposition"] == "ACCEPT":
                raise ExplorationError("bounded evidence cannot admit a general obstruction")
        if assessment["route_disposition"] == "EXHAUSTED":
            if outcome != "ROUTE_REFUTED":
                raise ExplorationError(
                    "only an exact refutation of the assigned route may exhaust that route"
                )
            if actual_ceiling not in CLOSURE_SAFE:
                raise ExplorationError("route exhaustion lacks closure-safe evidence")
            if not rejected:
                raise ExplorationError("refutation-based route exhaustion requires a refuted claim")
        if assessment["obstruction_disposition"] == "ACCEPT":
            if outcome not in {"NEW_OBSTRUCTION", "METHOD_BARRIER"} or not delta.get("new_obstruction"):
                raise ExplorationError("only a typed barrier return may be accepted")
            if actual_ceiling not in CLOSURE_SAFE:
                raise ExplorationError("an accepted obstruction lacks closure-safe evidence")
        if outcome == "CANDIDATE_PRODUCT" and assessment["accepted_claim_ids"]:
            raise ExplorationError(
                "a candidate product cannot be accepted before independent verification"
            )
        if outcome in {"STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED"}:
            if assessment["route_disposition"] != "REFRAME_REQUIRED":
                raise ExplorationError(
                    "a reduction or method barrier must return to an expanded frontier"
                )
    elif assessment is not None:
        raise ExplorationError("return assessment is only valid immediately after a return")


def _validate_domain_controls(packet: Mapping[str, Any], state: Mapping[str, Any], action: str) -> None:
    if action not in DISPATCH_ACTIONS | TERMINAL_ACTIONS:
        return
    controls = packet["target_model"]["domain_controls"]
    for domain in set(state["domains"]) & {"maths", "bio"}:
        domain_values = controls.get(domain)
        if not isinstance(domain_values, Mapping) or not domain_values:
            raise ExplorationError(f"Explorer target model lacks {domain} domain controls")
        expected = (
            {
                "quantifier_audit", "implication_direction", "finite_vs_general",
                "fixed_structure",
            }
            if domain == "maths" else
            {
                "claim_class", "causal_estimand", "denominator",
                "experimental_unit", "intervention", "generalization_population",
            }
        )
        if set(domain_values) != expected:
            raise ExplorationError(
                f"Explorer {domain} controls differ from the required fields"
            )
        if any(str(value).strip().upper() == "UNRECORDED" for value in domain_values.values()):
            raise ExplorationError(f"Explorer {domain} controls are still unrecorded")
        if domain == "maths" and domain_values["finite_vs_general"] not in {
            "SEPARATE", "NOT_APPLICABLE"
        }:
            raise ExplorationError("Explorer maths finite/general control is invalid")


def _normalized_target_text(state: Mapping[str, Any]) -> str:
    text = " ".join((state["target"]["statement"], state["target"].get("intent", "")))
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _named_problem_identifier(state: Mapping[str, Any]) -> str:
    text = _normalized_target_text(state)
    match = re.search(r"\berdos\s*(?:problem\s*)?#?\s*(\d+)\b", text, re.IGNORECASE)
    if match:
        return f"erdos:{match.group(1)}"
    match = re.search(r"\bproblem\s*#\s*(\d+)\b", text, re.IGNORECASE)
    return f"problem:{match.group(1)}" if match else ""


def _is_named_open_maths_target(state: Mapping[str, Any]) -> bool:
    if state["mode"] != "OPEN_DISCOVERY" or "maths" not in state["domains"]:
        return False
    text = _normalized_target_text(state)
    return bool(re.search(
        r"\b(?:erdos|open\s+(?:math(?:ematical)?\s+)?problem|conjecture)\b|\bproblem\s*#?\s*\d+\b",
        text,
        re.IGNORECASE,
    ))


def _validate_canonical_open_target(
    state: Mapping[str, Any],
    source_map: Mapping[str, Any] | None,
    proposal: Mapping[str, Any] | None,
) -> None:
    if not _is_named_open_maths_target(state) or proposal is None or proposal["lane"] == "RETRIEVE":
        return
    if source_map is None:
        raise ExplorationError(
            "a named open maths target must be source-bound before non-retrieval work"
        )
    marker = f"target_sha256:{state['target']['canonical_sha256']}"
    problem_id = _named_problem_identifier(state)
    problem_marker = f"canonical_problem_id:{problem_id}" if problem_id else ""
    canonical = [
        entry for entry in source_map["entries"]
        if entry["status"] == "OPEN"
        and entry["reliability"] in {"PRIMARY", "CURATED"}
        and marker in entry["preconditions"]
        and (not problem_marker or problem_marker in entry["preconditions"])
    ]
    if not canonical:
        raise ExplorationError(
            "named open maths work requires a PRIMARY or CURATED OPEN source entry "
            "with exact target_sha256 and canonical problem-id preconditions"
        )


def _campaign_stop_scope(state: Mapping[str, Any]) -> str:
    prefix = "campaign-stop-scope:"
    for constraint in state["target"].get("constraints", []):
        if constraint.casefold().startswith(prefix):
            return constraint[len(prefix):].strip()
    return ""


def _search_coverage(state: Mapping[str, Any]) -> dict[str, Any]:
    attempts = [
        item for item in state["route_attempts"]
        if item.get("adjudicated_by") and item.get("route_disposition") != "PENDING"
    ]
    routes: dict[str, Mapping[str, Any]] = {}
    node_by_episode: dict[str, str] = {}
    for event in state["events"]:
        if event["kind"] == "ARBITRATION_RECORDED":
            route = event["payload"]["arbitration"].get("selected_route")
            if route is not None:
                routes[route["route_fingerprint"]] = route
        elif event["kind"] == "EPISODE_ISSUED":
            episode = event["payload"]["episode"]
            node_by_episode[episode["episode_id"]] = episode["node_id"]
        elif event["kind"] == "ROUND_ISSUED":
            for wrapped in event["payload"]["round"]["episodes"]:
                episode = wrapped["episode"]
                node_by_episode[episode["episode_id"]] = episode["node_id"]
    distinct_axes = {
        (
            route.get("operator_id", "legacy-unknown"),
            route.get("failure_domain", "legacy:unknown"),
            " ".join(route.get("mechanism", "legacy mechanism").casefold().split()),
        )
        for attempt in attempts
        for route in [routes.get(attempt["route_fingerprint"], {})]
    }
    node_counts: dict[str, int] = {}
    for attempt in attempts:
        node_id = node_by_episode.get(attempt["episode_id"])
        if node_id:
            node_counts[node_id] = node_counts.get(node_id, 0) + 1
    active = state["frontier"]["active"]
    under_attacked = [node_id for node_id in active if node_counts.get(node_id, 0) < 2]
    last_reduction = max(
        (
            index for index, attempt in enumerate(attempts)
            if attempt.get("outcome") in {
                "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED"
            }
        ),
        default=-1,
    )
    post_reduction_attempts = len(attempts) - last_reduction - 1 if last_reduction >= 0 else len(attempts)
    return {
        "adjudicated_attempts": len(attempts),
        "distinct_mechanism_axes": len(distinct_axes),
        "under_attacked_open_core_ids": under_attacked,
        "post_reduction_attempts": post_reduction_attempts,
        "complete": (
            len(attempts) >= 6
            and len(distinct_axes) >= 4
            and not under_attacked
            and post_reduction_attempts >= 2
        ),
    }


def _stop_case_projection(
    state: Mapping[str, Any],
    explorer_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "phase": phase_for(state),
        "source_map_ref": explorer_value["source_coverage"]["source_map_ref"],
        "source_coverage_sha256": digest_value(explorer_value["source_coverage"]),
        "frontier_sha256": digest_value(explorer_value["frontier_model"]),
        "route_memory_sha256": digest_value(explorer_value["route_memory"]),
        "proposal_set_sha256": proposal_set_sha256(proposals),
        "proposal_ids": [item["proposal_id"] for item in proposals],
        "alternatives": list(explorer_value["decision"]["alternatives"]),
        "decision_reason": explorer_value["decision"]["reason"],
        "minimal_open_core_ids": list(
            explorer_value["frontier_model"]["minimal_open_core_ids"]
        ),
        "campaign_stop_scope": _campaign_stop_scope(state),
        "search_coverage": _search_coverage(state),
    }


def _prepare_stop_case(
    root: Path,
    state_value: Mapping[str, Any],
    explorer_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    state = kernel.validate_state(state_value)
    prepared = [prepare_proposal(root, state, item) for item in proposals]
    if explorer_value.get("schema") not in {DRAFT_SCHEMA, STATE_SCHEMA}:
        raise ExplorationError("stop review requires an Explorer draft or state")
    expected_binding = {
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "phase": phase_for(state),
    }
    for field, expected in expected_binding.items():
        if explorer_value.get(field) != expected:
            raise ExplorationError(f"stop-review Explorer {field} is stale")
    decision = explorer_value.get("decision") or {}
    if decision.get("action") != "HONEST_STOP":
        raise ExplorationError("stop review is only valid for an HONEST_STOP candidate")
    if decision.get("selected_proposal_id") is not None:
        raise ExplorationError("HONEST_STOP cannot select a proposal")
    if decision.get("changed_axis", "").strip():
        raise ExplorationError("HONEST_STOP cannot claim a changed research axis")
    refs = {
        item["proposal_id"]: item["payload_sha256"] for item in prepared
    }
    declared = _unique(
        explorer_value["proposal_refs"], "proposal_id", "proposal reference"
    )
    if {key: item["payload_sha256"] for key, item in declared.items()} != refs:
        raise ExplorationError("stop-review proposal bytes differ from the Explorer candidate")
    if prepared:
        raise ExplorationError(
            "HONEST_STOP is premature while a validated live proposal remains"
        )
    if phase_for(state) == "TRIAGE":
        raise ExplorationError("HONEST_STOP is unavailable at initial triage")
    if not _campaign_stop_scope(state):
        raise ExplorationError(
            "HONEST_STOP requires an explicit campaign-stop-scope target constraint; "
            "use PAUSE_WITH_FRONTIER for a resumable handoff"
        )
    _validate_target_model(explorer_value, state)
    _validate_source_coverage(explorer_value)
    source_map = _validate_source_binding(
        root, explorer_value, state, source_map_value
    )
    assert source_map is not None
    _validate_frontier(explorer_value, state)
    _validate_route_memory(explorer_value, state)
    _validate_return(explorer_value, state)
    if explorer_value["frontier_model"] != _frontier_model(state):
        raise ExplorationError(
            "HONEST_STOP cannot publish, relink, or reframe a frontier claim"
        )
    if source_map["contradictions"] or explorer_value["open_contradictions"]:
        raise ExplorationError("HONEST_STOP cannot suppress an unresolved contradiction")
    if explorer_value["source_coverage"]["status"] != "BOUNDED_COMPLETE":
        raise ExplorationError("HONEST_STOP requires bounded-complete source coverage")
    if len(decision.get("alternatives") or []) < 2:
        raise ExplorationError("HONEST_STOP requires at least two retained alternatives")
    if not explorer_value["frontier_model"]["minimal_open_core_ids"]:
        raise ExplorationError("HONEST_STOP requires a retained minimal open core")
    coverage = _search_coverage(state)
    if not coverage["complete"]:
        raise ExplorationError(
            "HONEST_STOP lacks bounded search coverage: six adjudicated attempts, four "
            "mechanism axes, two attacks per open core, and two post-reduction attacks are required"
        )
    unclosed = [
        item for item in explorer_value["route_memory"]
        if item["disposition"] not in {"EXHAUSTED", "WAITING"}
    ]
    if unclosed:
        raise ExplorationError(
            "HONEST_STOP cannot leave a live or unadjudicated semantic route"
        )
    if phase_for(state) == "RETURN_ARBITRATION":
        raise ExplorationError(
            "adjudicate the latest return before requesting terminal stop review"
        )
    return state, prepared, source_map


def stop_review_draft(
    root: Path,
    state_value: Mapping[str, Any],
    explorer_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any],
    *,
    report_id: str,
) -> dict[str, Any]:
    state, prepared, source_map = _prepare_stop_case(
        root, state_value, explorer_value, proposals, source_map_value
    )
    stop_case = _stop_case_projection(state, explorer_value, prepared)
    return {
        "schema": CONTROL_REPORT_SCHEMA,
        "report_id": report_id,
        "kind": "STOP_REVIEW",
        "target_sha256": state["target"]["canonical_sha256"],
        "source_refs": sorted({
            state["state_sha256"], source_map["payload_sha256"], digest_value(stop_case),
        }),
        "body": {
            "base_revision": state["revision"],
            "base_state_sha256": state["state_sha256"],
            "stop_case_sha256": digest_value(stop_case),
            "reviewer_id": "",
            "reviewer_role": "INDEPENDENT_CONTROL_REVIEWER",
            "independent_of_explorer": False,
            "independent_of_researchers": False,
            "reviewed_proposal_ids": stop_case["proposal_ids"],
            "reviewed_route_fingerprints": [
                item["route_fingerprint"] for item in explorer_value["route_memory"]
            ],
            "reviewed_alternatives": stop_case["alternatives"],
            "reviewed_open_core_ids": stop_case["minimal_open_core_ids"],
            "conclusion": "UNDECIDED",
            "all_routes_accounted_for": False,
            "no_universal_impossibility_claim": True,
            "no_status_claim": True,
            "terminal_scope": "CURRENT_AUTHORIZED_SEARCH_ONLY",
            "scope": "",
            "limitations": [],
            "first_failing_gate": "",
        },
        "disposition": "BLOCKED",
        "status_authority": False,
    }


def validate_stop_review(
    root: Path,
    state_value: Mapping[str, Any],
    explorer_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any],
    review_value: Mapping[str, Any],
) -> dict[str, Any]:
    state, prepared, source_map = _prepare_stop_case(
        root, state_value, explorer_value, proposals, source_map_value
    )
    try:
        report = contracts.validate_packet(root, CONTROL_REPORT_SCHEMA, review_value)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    if report["kind"] != "STOP_REVIEW":
        raise ExplorationError("HONEST_STOP requires a STOP_REVIEW control report")
    stop_case = _stop_case_projection(state, explorer_value, prepared)
    expected_refs = sorted({
        state["state_sha256"], source_map["payload_sha256"], digest_value(stop_case),
    })
    if report["target_sha256"] != state["target"]["canonical_sha256"]:
        raise ExplorationError("stop review belongs to another frozen target")
    if report["source_refs"] != expected_refs:
        raise ExplorationError("stop review does not bind the exact state, sources, and stop case")
    required_body = {
        "base_revision", "base_state_sha256", "stop_case_sha256", "reviewer_id",
        "reviewer_role", "independent_of_explorer", "independent_of_researchers",
        "reviewed_proposal_ids",
        "reviewed_route_fingerprints", "reviewed_alternatives",
        "reviewed_open_core_ids", "conclusion", "all_routes_accounted_for",
        "no_universal_impossibility_claim", "no_status_claim", "terminal_scope",
        "scope", "limitations", "first_failing_gate",
    }
    _closed(report["body"], required_body, "stop-review body")
    body = report["body"]
    expected_fields = {
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "stop_case_sha256": digest_value(stop_case),
        "reviewer_role": "INDEPENDENT_CONTROL_REVIEWER",
        "independent_of_explorer": True,
        "independent_of_researchers": True,
        "reviewed_proposal_ids": stop_case["proposal_ids"],
        "reviewed_route_fingerprints": [
            item["route_fingerprint"] for item in explorer_value["route_memory"]
        ],
        "reviewed_alternatives": stop_case["alternatives"],
        "reviewed_open_core_ids": stop_case["minimal_open_core_ids"],
        "all_routes_accounted_for": True,
        "no_universal_impossibility_claim": True,
        "no_status_claim": True,
        "terminal_scope": "CURRENT_AUTHORIZED_SEARCH_ONLY",
    }
    for field, expected in expected_fields.items():
        if body[field] != expected:
            raise ExplorationError(f"stop review has stale or unsafe {field}")
    reviewer_id = body["reviewer_id"].strip()
    prohibited_roles = {"researcher", "worker", "attacker"}
    if (
        not reviewer_id
        or reviewer_id == explorer_value["explorer_id"]
        or any(role in reviewer_id.casefold() for role in prohibited_roles)
    ):
        raise ExplorationError("stop review requires a distinct named reviewer")
    if body["scope"].strip() != _campaign_stop_scope(state):
        raise ExplorationError("stop-review scope differs from the frozen campaign-stop scope")
    if not body["limitations"] or not body["first_failing_gate"].strip():
        raise ExplorationError(
            "stop review requires explicit scope, limitations, and first failing gate"
        )
    if any(not isinstance(item, str) or not item.strip() for item in body["limitations"]):
        raise ExplorationError("stop-review limitations must be non-empty strings")
    expected_conclusion = "ALL_RECORDED_ROUTES_ADJUDICATED"
    if body["conclusion"] != expected_conclusion or body["conclusion"] not in STOP_CONCLUSIONS:
        raise ExplorationError("stop-review conclusion conflicts with the recorded route history")
    if report["disposition"] != "READY" or report["status_authority"] is not False:
        raise ExplorationError("stop review is not independently ready and non-authoritative")
    return report


def build_stop_review(
    root: Path,
    state_value: Mapping[str, Any],
    explorer_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "schema", "report_id", "kind", "target_sha256", "source_refs", "body",
        "disposition", "status_authority",
    }
    _closed(draft_value, required, "stop-review draft")
    packet = seal_packet(copy.deepcopy(dict(draft_value)))
    return validate_stop_review(
        root,
        state_value,
        explorer_value,
        proposals,
        source_map_value,
        packet,
    )


def validate_state(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
    contract_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any] | None = None,
    stop_review_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    contract = validate_contract(root, contract_value, state=state)
    try:
        packet = contracts.validate_packet(root, STATE_SCHEMA, value)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    state_binding = {
        "target_sha256": contract["target_sha256"],
        "base_revision": contract["base_revision"],
        "base_state_sha256": contract["base_state_sha256"],
        "phase": contract["phase"],
    }
    for field, expected in state_binding.items():
        if packet[field] != expected:
            raise ExplorationError(f"Explorer state {field} is stale")
    prepared = proposals
    refs = {item["proposal_id"]: item["payload_sha256"] for item in prepared}
    declared = _unique(packet["proposal_refs"], "proposal_id", "proposal reference")
    if len(declared) > FIXED_LIMITS["max_live_proposals"]:
        raise ExplorationError("Explorer proposal set exceeds its live limit")
    if {key: item["payload_sha256"] for key, item in declared.items()} != refs:
        raise ExplorationError("Explorer proposal references differ from supplied proposal bytes")
    _validate_target_model(packet, state)
    _validate_source_coverage(packet)
    source_map = _validate_source_binding(root, packet, state, source_map_value)
    nodes = _validate_frontier(packet, state)
    _validate_route_memory(packet, state)
    if packet["portfolio"] != proposal_portfolio(prepared, packet["route_memory"]):
        raise ExplorationError("Explorer portfolio differs from its proposals or route memory")
    _validate_return(packet, state)
    if len(packet["open_contradictions"]) > FIXED_LIMITS["max_open_contradictions"]:
        raise ExplorationError("Explorer state exceeds the contradiction limit")
    decision = packet["decision"]
    action = decision["action"]
    if action == "UNDECIDED":
        raise ExplorationError("Explorer state has no decision")
    if action not in ACTIONS or not decision["basis_refs"] or not decision["reason"].strip():
        raise ExplorationError("Explorer decision lacks an allowed action, basis, or reason")
    selected = decision["selected_proposal_id"]
    if action in DISPATCH_ACTIONS:
        if selected not in refs:
            raise ExplorationError("Explorer dispatch does not select a supplied proposal")
        portfolio_entry = next(
            item for item in packet["portfolio"]["entries"]
            if item["proposal_id"] == selected
        )
        if portfolio_entry["disposition"] == "RECOUPLED":
            raise ExplorationError(
                "Explorer cannot dispatch a recoupled route without revival evidence"
            )
        recommended = packet["portfolio"]["recommended_proposal_id"]
        if selected != recommended and recommended not in decision["alternatives"]:
            raise ExplorationError(
                "a portfolio override must name the recommended proposal in alternatives"
            )
    elif selected is not None:
        raise ExplorationError("a non-dispatch Explorer decision cannot select a proposal")
    frontier_changed = packet["frontier_model"] != _frontier_model(state)
    if action in {"REFRAME_FRONTIER", "EXPAND_FRONTIER"} and not frontier_changed:
        raise ExplorationError(f"{action} must make one explicit frontier change")
    if action == "PAUSE_WITH_FRONTIER":
        if frontier_changed:
            raise ExplorationError("PAUSE_WITH_FRONTIER cannot hide an unapplied frontier mutation")
        if not packet["frontier_model"]["minimal_open_core_ids"]:
            raise ExplorationError("PAUSE_WITH_FRONTIER must retain a resumable open core")
    if action != "RETRY_WITH_MUTATION" and decision["changed_axis"].strip():
        raise ExplorationError("only RETRY_WITH_MUTATION may declare a changed axis")
    blocker_ambiguities = [
        item for item in packet["target_model"]["ambiguities"] if item["status"] == "BLOCKER"
    ]
    if blocker_ambiguities and action not in {"WAIT_EXTERNAL", "DEMOTE"}:
        raise ExplorationError("unresolved target ambiguity blocks dispatch and completion")
    if packet["open_contradictions"] and action not in {"WAIT_EXTERNAL", "DEMOTE"}:
        raise ExplorationError("open Explorer contradictions block dispatch and completion")
    if source_map is not None:
        missing_source_conflicts = (
            set(source_map["contradictions"]) - set(packet["open_contradictions"])
        )
        if missing_source_conflicts:
            raise ExplorationError(
                "Explorer suppressed source-map contradictions: "
                f"{sorted(missing_source_conflicts)}"
            )
    if packet["phase"] == "WAITING_RETURN":
        raise ExplorationError("Explorer cannot decide while bound work is pending")
    if packet["phase"] == "TERMINAL":
        raise ExplorationError("terminal Explorer state cannot issue or record another decision")
    issued_nodes = _issued_node_ids(state)
    if state["route_attempts"] and len(nodes) == 1 and action in DISPATCH_ACTIONS:
        if not packet["frontier_model"]["root_only_exception"].strip():
            raise ExplorationError("post-return dispatch requires a decomposed frontier or a retained ROOT-only exception")
    if issued_nodes.count("ROOT") >= 2 and action in DISPATCH_ACTIONS:
        selected_proposal = next(
            item for item in prepared if item["proposal_id"] == selected
        )
        if (
            selected_proposal["node_id"] == "ROOT"
            or "ROOT" in packet["frontier_model"]["minimal_open_core_ids"]
            or len(nodes) == 1
        ):
            raise ExplorationError(
                "two ROOT attacks require a real endpoint decomposition before another dispatch"
            )
    _validate_domain_controls(packet, state, action)
    review = None
    if action in DISPATCH_ACTIONS:
        proposal = next(item for item in prepared if item["proposal_id"] == selected)
        if proposal["node_id"] not in nodes:
            raise ExplorationError("selected proposal is absent from the Explorer frontier")
        if packet["source_coverage"]["status"] == "NOT_STARTED" and proposal["lane"] != "RETRIEVE":
            raise ExplorationError("non-retrieval work requires a started source-status map")
        _validate_canonical_open_target(state, source_map, proposal)
        if action == "RETRY_WITH_MUTATION":
            if not decision["changed_axis"].strip() or proposal["changed_axis"] != decision["changed_axis"]:
                raise ExplorationError("retry decision and proposal must bind one identical changed axis")
            if not proposal["revival_predicate"] or not proposal["revival_evidence"]:
                raise ExplorationError("retry requires evidence satisfying a retained revival predicate")
    assessment = packet["return_assessment"]
    if (
        packet["phase"] == "RETURN_ARBITRATION"
        and assessment is not None
        and assessment["claimed_outcome"] in {
            "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED"
        }
        and action not in {"REFRAME_FRONTIER", "EXPAND_FRONTIER"}
    ):
        raise ExplorationError(
            "a reduction or barrier must be installed as an attackable frontier before continuation"
        )
    if (
        packet["phase"] == "RETURN_ARBITRATION"
        and assessment is not None
        and assessment["claimed_outcome"] == "CANDIDATE_PRODUCT"
    ):
        if action in DISPATCH_ACTIONS:
            proposal = next(item for item in prepared if item["proposal_id"] == selected)
            if proposal["lane"] != "VERIFY":
                raise ExplorationError(
                    "CANDIDATE_PRODUCT may dispatch only an independent VERIFY route"
                )
        elif action not in {"REFRAME_FRONTIER", "EXPAND_FRONTIER", "PAUSE_WITH_FRONTIER", "WAIT_EXTERNAL", "DEMOTE"}:
            raise ExplorationError(
                "CANDIDATE_PRODUCT requires verification, explicit reframing, waiting, or demotion"
            )
    if action == "DIRECT_ANSWER" and state["status"] not in kernel.ACCEPTED:
        raise ExplorationError("DIRECT_ANSWER requires reducer-admitted target status")
    if action == "HONEST_STOP":
        if source_map_value is None or stop_review_value is None:
            raise ExplorationError(
                "HONEST_STOP requires the exact source map and independent stop-review packet"
            )
        review = validate_stop_review(
            root, state, packet, prepared, source_map_value, stop_review_value
        )
        if packet["stop_review_ref"] != review["payload_sha256"]:
            raise ExplorationError("Explorer stop-review reference does not bind supplied bytes")
        required_basis = {
            state["state_sha256"], source_map_value["payload_sha256"], review["payload_sha256"],
        }
        if not required_basis.issubset(set(decision["basis_refs"])):
            raise ExplorationError(
                "HONEST_STOP basis must bind state, source map, and independent review"
            )
    elif packet["stop_review_ref"] is not None or stop_review_value is not None:
        raise ExplorationError("stop review is valid only for HONEST_STOP")
    if action == "WAIT_EXTERNAL" and not packet["first_failing_gate"].strip():
        raise ExplorationError("WAIT_EXTERNAL requires the first unavailable gate")
    if action != "WAIT_EXTERNAL" and packet["first_failing_gate"].strip():
        raise ExplorationError("only WAIT_EXTERNAL may set the Explorer first failing gate")
    if action in TERMINAL_ACTIONS and frontier_changed:
        raise ExplorationError("a terminal decision cannot also mutate the frontier")
    _validate_role_evidence_refs(
        packet, state, source_map, prepared, review
    )
    return packet


def build_state(
    root: Path,
    state_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any] | None = None,
    stop_review_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = kernel.validate_state(state_value)
    contract = build_contract(state)
    prepared = [prepare_proposal(root, state, item) for item in proposals]
    required = {
        "schema", "explorer_id", "target_sha256", "base_revision",
        "base_state_sha256", "phase", "target_model", "source_coverage",
        "frontier_model", "route_memory", "proposal_refs", "portfolio", "return_assessment",
        "decision", "open_contradictions", "stop_review_ref", "first_failing_gate",
    }
    _closed(draft_value, required, "Explorer draft")
    if draft_value.get("schema") != DRAFT_SCHEMA:
        raise ExplorationError("Explorer draft schema is invalid")
    body = copy.deepcopy(dict(draft_value))
    body["schema"] = STATE_SCHEMA
    packet = seal_packet(body)
    return validate_state(
        root, state, packet, contract, prepared, source_map_value, stop_review_value
    ), prepared


def _topological_additions(
    nodes: Mapping[str, Mapping[str, Any]], existing: set[str]
) -> list[Mapping[str, Any]]:
    ordered: list[Mapping[str, Any]] = []
    visiting: set[str] = set()
    visited = set(existing)

    def add(identifier: str) -> None:
        if identifier in visited:
            return
        if identifier in visiting:
            raise ExplorationError("new frontier additions contain a cycle")
        visiting.add(identifier)
        for dependency in nodes[identifier]["dependencies"]:
            add(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
        ordered.append(nodes[identifier])

    for identifier in sorted(set(nodes) - existing):
        add(identifier)
    return ordered


def _frontier_delta(
    state: Mapping[str, Any], explorer_state: Mapping[str, Any]
) -> dict[str, Any]:
    current = {item["item_id"]: item for item in state["frontier"]["items"]}
    nodes = {item["node_id"]: item for item in explorer_state["frontier_model"]["nodes"]}
    edge_index = {
        (item["from_id"], item["to_id"]): item
        for item in explorer_state["frontier_model"]["edges"]
    }
    additions = []
    for node in _topological_additions(nodes, set(current)):
        if node["status"] != "OPEN":
            raise ExplorationError("new Explorer frontier nodes must enter OPEN")
        additions.append({
            "item_id": node["node_id"],
            "kind": node["kind"],
            "statement": node["statement"],
            "target_sha256": state["target"]["canonical_sha256"],
            "status": "OPEN",
            "dependencies": list(node["dependencies"]),
            "evidence_refs": list(node["evidence_refs"]),
            "route_fingerprint": None,
            "admission_ref": None,
        })
    relinks = []
    for identifier, node in nodes.items():
        if identifier in current and node["dependencies"] != current[identifier]["dependencies"]:
            relinks.append({
                "item_id": identifier,
                "dependencies": list(node["dependencies"]),
                "relations": [
                    {
                        "dependency_id": dependency,
                        "relation": edge_index[(identifier, dependency)]["relation"],
                        "evidence_refs": edge_index[(identifier, dependency)]["evidence_refs"],
                    }
                    for dependency in node["dependencies"]
                ],
            })
    accepted_obstructions: list[dict[str, Any]] = []
    assessment = explorer_state["return_assessment"]
    returned = _last_return(state)
    if assessment and assessment["obstruction_disposition"] == "ACCEPT" and returned:
        delta = returned[1]
        if delta.get("new_obstruction"):
            accepted_obstructions.append(copy.deepcopy(delta["new_obstruction"]))
        else:
            for child in delta.get("deltas", []):
                if child.get("new_obstruction"):
                    accepted_obstructions.append(copy.deepcopy(child["new_obstruction"]))
    return {
        "additions": additions,
        "relinks": sorted(relinks, key=lambda item: item["item_id"]),
        "edge_assertions": copy.deepcopy(explorer_state["frontier_model"]["edges"]),
        "active_ids": list(explorer_state["frontier_model"]["minimal_open_core_ids"]),
        "accepted_obstructions": accepted_obstructions,
    }


def build_arbitration(
    root: Path,
    state_value: Mapping[str, Any],
    explorer_state_value: Mapping[str, Any],
    proposals: list[Mapping[str, Any]],
    source_map_value: Mapping[str, Any] | None = None,
    stop_review_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = kernel.validate_state(state_value)
    prepared = [prepare_proposal(root, state, item) for item in proposals]
    contract = build_contract(state)
    explorer_state = validate_state(
        root, state, explorer_state_value, contract, prepared,
        source_map_value, stop_review_value,
    )
    source_map = (
        contracts.validate_packet(root, SOURCE_MAP_SCHEMA, source_map_value)
        if source_map_value is not None else None
    )
    decision = explorer_state["decision"]
    assessment = explorer_state["return_assessment"]
    selected = next(
        (item for item in prepared if item["proposal_id"] == decision["selected_proposal_id"]),
        None,
    )
    selected_route = None
    if selected is not None:
        route_fp, core_fp = proposal_fingerprints(selected)
        selected_route = {
            "proposal_id": selected["proposal_id"],
            "proposal_sha256": selected["payload_sha256"],
            "route_fingerprint": route_fp,
            "core_fingerprint": core_fp,
            "route_terms": sorted(proposal_terms(selected)),
            "core_terms": sorted(proposal_terms(selected, core=True)),
            "operator_id": selected["operator_id"],
            "mechanism": selected["route"]["mechanism"],
            "invariant": selected["invariant"],
            "required_result": selected["route"]["required_result"],
            "failure_signature": selected["failure_signature"],
            "failure_domain": selected["failure_domain"],
            "revival_predicate": selected["revival_predicate"],
            "evidence_refs": sorted({
                *selected["novelty_refs"],
                *(item["evidence_ref"] for item in selected["prerequisites"] if item["evidence_ref"]),
            }),
        }
    packet = seal_packet({
        "schema": ARBITRATION_SCHEMA,
        "arbitration_id": f"arbitration:{state['kernel_id']}:{state['revision']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "explorer_state_sha256": explorer_state["payload_sha256"],
        "phase": explorer_state["phase"],
        "return_ref": assessment["return_ref"] if assessment else None,
        "impact": assessment["impact"] if assessment else "INITIAL_TRIAGE",
        "evidence_ceiling": assessment["evidence_ceiling"] if assessment else "UNKNOWN",
        "route_disposition": assessment["route_disposition"] if assessment else "NOT_APPLICABLE",
        "obstruction_disposition": assessment["obstruction_disposition"] if assessment else "NOT_APPLICABLE",
        "action": decision["action"],
        "basis_refs": decision["basis_refs"],
        "alternatives": decision["alternatives"],
        "selected_proposal_id": decision["selected_proposal_id"],
        "selected_route": selected_route,
        "proposal_set_sha256": proposal_set_sha256(prepared),
        "changed_axis": decision["changed_axis"],
        "reason": decision["reason"],
        "frontier_delta": _frontier_delta(state, explorer_state),
        "source_coverage_status": explorer_state["source_coverage"]["status"],
        "source_map_ref": explorer_state["source_coverage"]["source_map_ref"],
        "source_refs": source_evidence_refs(source_map),
        "source_verified_refs": source_evidence_refs(
            source_map, statuses={"ESTABLISHED", "CORRECTED"}
        ),
        "target_contract": target_semantics.build(
            root, state, explorer_state["target_model"]
        ),
        "stop_review_ref": explorer_state["stop_review_ref"],
        "status_authority": False,
    })
    try:
        packet = contracts.validate_packet(root, ARBITRATION_SCHEMA, packet)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    delta = packet["frontier_delta"]
    if packet["action"] in {"REFRAME_FRONTIER", "EXPAND_FRONTIER"} and not (
        delta["additions"] or delta["relinks"]
        or delta["active_ids"] != state["frontier"]["active"]
    ):
        raise ExplorationError(f"{packet['action']} must make one explicit frontier change")
    return packet, prepared


def validate_arbitration(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    try:
        packet = contracts.validate_packet(root, ARBITRATION_SCHEMA, value)
    except contracts.ContractError as exc:
        raise ExplorationError(str(exc)) from exc
    expected = {
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "phase": phase_for(state),
    }
    for field, expected_value in expected.items():
        if packet[field] != expected_value:
            raise ExplorationError(f"Explorer arbitration {field} is stale")
    try:
        target_semantics.validate(root, packet["target_contract"], state=state)
    except target_semantics.TargetSemanticsError as exc:
        raise ExplorationError(str(exc)) from exc
    returned = _last_return(state)
    if returned is None:
        if packet["return_ref"] is not None:
            raise ExplorationError("Explorer arbitration invents a return reference")
    elif packet["return_ref"] != returned[0]:
        raise ExplorationError("Explorer arbitration does not bind the latest return")
    if packet["action"] in DISPATCH_ACTIONS:
        if packet["selected_route"] is None or packet["selected_proposal_id"] is None:
            raise ExplorationError("dispatch arbitration lacks its selected semantic route")
    elif packet["selected_route"] is not None or packet["selected_proposal_id"] is not None:
        raise ExplorationError("non-dispatch arbitration cannot select a semantic route")
    if packet["evidence_ceiling"] in BOUNDED_EVIDENCE:
        if (
            packet["route_disposition"] == "EXHAUSTED"
            or packet["frontier_delta"]["accepted_obstructions"]
        ):
            raise ExplorationError("bounded evidence cannot exhaust a route or admit an obstruction")
    source_ref = packet.get("source_map_ref")
    source_refs = packet.get("source_refs", [])
    source_verified_refs = packet.get("source_verified_refs", [])
    if packet["source_coverage_status"] == "NOT_STARTED" and source_ref is not None:
        raise ExplorationError("unstarted source coverage cannot bind a source map")
    if packet["source_coverage_status"] != "NOT_STARTED" and not (
        isinstance(source_ref, str) and re.fullmatch(r"[0-9a-f]{64}", source_ref)
    ):
        raise ExplorationError("started source coverage lacks a sealed source-map digest")
    if source_ref is None and source_refs:
        raise ExplorationError("source evidence refs cannot exist without a source map")
    if source_ref is not None and not source_refs:
        raise ExplorationError("started source coverage lacks entry-level source refs")
    if set(source_verified_refs) - set(source_refs):
        raise ExplorationError("source-verified refs are not part of the bound source map")
    if packet["action"] == "HONEST_STOP" and not (
        isinstance(packet["stop_review_ref"], str)
        and re.fullmatch(r"[0-9a-f]{64}", packet["stop_review_ref"])
    ):
        raise ExplorationError("HONEST_STOP lacks a sealed stop-review digest")
    return packet


def apply_arbitration(
    root: Path,
    state_value: Mapping[str, Any],
    arbitration_value: Mapping[str, Any],
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    arbitration = validate_arbitration(root, state, arbitration_value)
    event = kernel.build_event(
        state,
        "ARBITRATION_RECORDED",
        {"arbitration": arbitration},
        f"arbitrate:{arbitration['arbitration_id']}",
        _explorer_authority=True,
    )
    return kernel.apply_event(state, event)


def summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "explorer_id": value["explorer_id"],
        "phase": value["phase"],
        "frontier_nodes": len(value["frontier_model"]["nodes"]),
        "minimal_open_core": list(value["frontier_model"]["minimal_open_core_ids"]),
        "source_coverage": value["source_coverage"]["status"],
        "routes_retained": len(value["route_memory"]),
        "proposals": len(value["proposal_refs"]),
        "eligible_proposals": sum(
            item["disposition"] != "RECOUPLED" for item in value["portfolio"]["entries"]
        ),
        "recoupled_proposals": sum(
            item["disposition"] == "RECOUPLED" for item in value["portfolio"]["entries"]
        ),
        "portfolio_recommendation": value["portfolio"]["recommended_proposal_id"],
        "portfolio_diverse": value["portfolio"]["diversity_floor_met"],
        "action": value["decision"]["action"],
        "selected_proposal_id": value["decision"]["selected_proposal_id"],
        "payload_sha256": value["payload_sha256"],
    }
