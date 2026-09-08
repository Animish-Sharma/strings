"""Independent discovery rounds with conflict-visible deterministic merge."""

from __future__ import annotations

import copy
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from . import contracts, discovery, exploration, kernel
from .canonical import seal_packet


ROUND_SCHEMA = "witsoc.round.v1"
DELTA_SCHEMA = "witsoc.round-delta.v1"
MERGE_POLICIES = {"DISJOINT_ONLY", "CONFLICT_VISIBLE"}


class RoundError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise RoundError(f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")


def _round_spec(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    required = {"actor_id", "failure_domain", "resource_keys", "proposal"}
    optional = {"independence"}
    missing, extra = required - set(value), set(value) - required - optional
    if missing or extra:
        raise RoundError(
            f"round specification shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    result = copy.deepcopy(dict(value))
    for field in ("actor_id", "failure_domain"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise RoundError(f"round specification {field} is empty")
    resources = result["resource_keys"]
    if not isinstance(resources, list) or any(
        not isinstance(item, str) or not item.strip() for item in resources
    ):
        raise RoundError("round resource_keys must be an array of non-empty strings")
    if len(resources) != len(set(resources)):
        raise RoundError("round resource_keys are duplicated")
    result["resource_keys"] = sorted(resources)
    profile = result.get("independence")
    if profile is not None:
        if not isinstance(profile, Mapping):
            raise RoundError("round independence profile must be an object")
        fields = {
            "method_lineage", "evidence_lineage", "data_lineage", "evaluation_lineage",
        }
        _closed(profile, fields, "round independence profile")
        if any(not isinstance(profile[field], str) or not profile[field].strip() for field in fields):
            raise RoundError("round independence lineage fields must be non-empty strings")
        result["independence"] = {field: profile[field].strip() for field in sorted(fields)}
    else:
        result["independence"] = None
    try:
        result["proposal"] = exploration.prepare_proposal(
            root, state_value, result["proposal"]
        )
    except exploration.ExplorationError as exc:
        raise RoundError(str(exc)) from exc
    return result


def independence_audit(
    root: Path,
    state_value: Mapping[str, Any],
    specifications: list[Mapping[str, Any]],
    *,
    report_id: str,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if len(specifications) < 2:
        raise RoundError("independence audit requires at least two attacks")
    specs = [_round_spec(root, state, value) for value in specifications]
    shared: list[str] = []
    pairwise: list[dict[str, Any]] = []
    lineages = (
        "method_lineage", "evidence_lineage", "data_lineage", "evaluation_lineage",
    )
    complete = all(item["independence"] is not None for item in specs)
    for left, right in combinations(specs, 2):
        dimensions = {
            "actor": left["actor_id"] != right["actor_id"],
            "failure_domain": left["failure_domain"] != right["failure_domain"],
            "semantic_route": (
                exploration.proposal_fingerprints(left["proposal"])[0]
                != exploration.proposal_fingerprints(right["proposal"])[0]
            ),
            "resources": set(left["resource_keys"]).isdisjoint(right["resource_keys"]),
        }
        if complete:
            assert left["independence"] is not None and right["independence"] is not None
            for field in lineages:
                dimensions[field] = (
                    left["independence"][field] != right["independence"][field]
                )
                if not dimensions[field]:
                    shared.append(f"{left['actor_id']}:{right['actor_id']}:{field}")
        pairwise.append({
            "left": left["actor_id"],
            "right": right["actor_id"],
            "independent_dimensions": sorted(
                field for field, independent in dimensions.items() if independent
            ),
            "shared_dimensions": sorted(
                field for field, independent in dimensions.items() if not independent
            ),
        })
    structural = all(
        {"actor", "failure_domain", "semantic_route"}.issubset(
            set(item["independent_dimensions"])
        )
        for item in pairwise
    )
    lineage_distances = [
        sum(field in item["independent_dimensions"] for field in lineages)
        for item in pairwise
    ] if complete else []
    minimum_distance = min(lineage_distances, default=0)
    if not structural:
        grade = "WEAK"
    elif complete and minimum_distance >= 3:
        grade = "STRONG"
    elif complete and minimum_distance >= 2:
        grade = "MODERATE"
    else:
        grade = "STRUCTURAL"
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": report_id,
        "kind": "INDEPENDENCE_AUDIT",
        "target_sha256": state["target"]["canonical_sha256"],
        "source_refs": sorted({
            exploration.proposal_fingerprints(item["proposal"])[0] for item in specs
        }),
        "body": {
            "grade": grade,
            "admission_eligible": grade == "STRONG",
            "profiles_complete": complete,
            "minimum_lineage_distance": minimum_distance,
            "pairwise": pairwise,
            "shared_risks": sorted(set(shared)),
            "dimensions": [
                "actor", "failure_domain", "semantic_route", "resources", *lineages,
            ],
            "runtime_identity_inference": "NONE",
        },
        "disposition": (
            "BLOCKED" if grade == "WEAK" else "READY" if grade in {"MODERATE", "STRONG"}
            else "ADVISORY"
        ),
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise RoundError(str(exc)) from exc


def _episode(
    state: Mapping[str, Any],
    spec: Mapping[str, Any],
    ranking: Mapping[str, Any],
    round_id: str,
    index: int,
    source_map_ref: str | None = None,
    source_refs: list[str] | None = None,
    source_verified_refs: list[str] | None = None,
    target_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    proposal = spec["proposal"]
    items = {item["item_id"]: item for item in state["frontier"]["items"]}
    if proposal["node_id"] not in items:
        raise RoundError(f"round proposal names unknown frontier item {proposal['node_id']!r}")
    last = state["events"][-1] if state["events"] else None
    arbitration_ref = (
        last["payload"]["arbitration"]["payload_sha256"]
        if state["mode"] == "OPEN_DISCOVERY"
        and last is not None
        and last["kind"] == "ARBITRATION_RECORDED"
        else None
    )
    packet = seal_packet({
        "schema": discovery.EPISODE_SCHEMA,
        "episode_id": f"{round_id}:{index:02d}:{proposal['proposal_id']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "node_id": proposal["node_id"],
        "claim": items[proposal["node_id"]]["statement"],
        "lane": proposal["lane"],
        "route": proposal["route"],
        "route_fingerprint": ranking["route_fingerprint"],
        "core_fingerprint": ranking["core_fingerprint"],
        "objective": proposal["objective"],
        "evaluator": proposal["evaluator"],
        "expected_delta": proposal["expected_delta"],
        "return_condition": proposal["return_condition"],
        "campaign_authority": False,
        "changed_axis": proposal["changed_axis"],
        "revival_evidence": proposal["revival_evidence"],
        "adjudication": {
            "schema": "witsoc.round-adjudication.v1",
            "round_id": round_id,
            "actor_id": spec["actor_id"],
            "failure_domain": spec["failure_domain"],
            "resource_keys": spec["resource_keys"],
            "score": ranking["score"],
            "ranked": [copy.deepcopy(dict(ranking))],
            "selected_proposal_id": proposal["proposal_id"],
            "arbitration_ref": arbitration_ref,
            "source_map_ref": source_map_ref,
            "source_refs": list(source_refs or []),
            "source_verified_refs": list(source_verified_refs or []),
            "target_contract": copy.deepcopy(
                dict(target_contract) if target_contract is not None else None
            ),
            "advisory": True,
        },
    })
    return discovery.validate_episode(packet, state)


def build_round(
    root: Path,
    state_value: Mapping[str, Any],
    specifications: list[Mapping[str, Any]],
    *,
    round_id: str,
    rationale: str,
    merge_policy: str = "CONFLICT_VISIBLE",
    max_parallel: int = 4,
    _prepared_specs: list[Mapping[str, Any]] | None = None,
    _proposal_state_value: Mapping[str, Any] | None = None,
    _selected_proposal_id: str | None = None,
    _source_map_ref: str | None = None,
    _source_refs: list[str] | None = None,
    _source_verified_refs: list[str] | None = None,
    _target_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    proposal_state = kernel.validate_state(_proposal_state_value or state_value)
    if state["pending_episode"] is not None:
        raise RoundError("the bounded loop already has pending work")
    if not round_id.strip() or not rationale.strip():
        raise RoundError("round id and independence rationale are required")
    if merge_policy not in MERGE_POLICIES or not 2 <= max_parallel <= 8:
        raise RoundError("round merge policy or max_parallel is invalid")
    specs = (
        [copy.deepcopy(dict(value)) for value in _prepared_specs]
        if _prepared_specs is not None
        else [_round_spec(root, proposal_state, value) for value in specifications]
    )
    if len(specs) < 2:
        raise RoundError("an independent round requires at least two specifications")
    actors = [item["actor_id"] for item in specs]
    failures = [item["failure_domain"] for item in specs]
    routes = [exploration.proposal_fingerprints(item["proposal"])[0] for item in specs]
    if len(actors) != len(set(actors)):
        raise RoundError("round actors must be distinct")
    if len(failures) != len(set(failures)):
        raise RoundError("round failure domains must be distinct")
    if len(routes) != len(set(routes)):
        raise RoundError("round semantic routes must be distinct")
    audit = independence_audit(
        root,
        proposal_state,
        [copy.deepcopy(dict(value)) for value in specs],
        report_id=f"independence:{round_id}",
    )
    if not audit["body"]["admission_eligible"]:
        raise RoundError(
            "parallel dispatch requires a STRONG independence audit across actor, "
            "failure, semantic route, and at least three lineage dimensions"
        )
    portfolio = discovery.plan_portfolio(
        proposal_state,
        [item["proposal"] for item in specs],
        portfolio_exception=rationale,
    )
    eligible_ids = {item["proposal_id"] for item in portfolio["ranked"]}
    if len(eligible_ids) < 2:
        reasons = "; ".join(item["reason"] for item in portfolio["refused"][:4])
        raise RoundError("fewer than two round routes survive frontier policy" + (f": {reasons}" if reasons else ""))
    specs = [item for item in specs if item["proposal"]["proposal_id"] in eligible_ids]
    resources_disjoint = all(
        set(left["resource_keys"]).isdisjoint(right["resource_keys"])
        for left, right in combinations(specs, 2)
    )
    if merge_policy == "DISJOINT_ONLY" and not resources_disjoint:
        raise RoundError("DISJOINT_ONLY round specifications share a resource key")
    ranking_by_id = {item["proposal_id"]: item for item in portfolio["ranked"]}
    ranked_ids = [item["proposal_id"] for item in portfolio["ranked"] if item["proposal_id"] in eligible_ids]
    if _selected_proposal_id is not None:
        if _selected_proposal_id not in eligible_ids:
            raise RoundError("Explorer selected a route excluded by round policy")
        ranked_ids.remove(_selected_proposal_id)
        ranked_ids.insert(0, _selected_proposal_id)
    spec_by_id = {item["proposal"]["proposal_id"]: item for item in specs}
    ranked = [spec_by_id[item] for item in ranked_ids[:max_parallel]]
    nodes = [item["proposal"]["node_id"] for item in ranked]
    wrapped = [
        {
            "actor_id": spec["actor_id"],
            "failure_domain": spec["failure_domain"],
            "resource_keys": spec["resource_keys"],
            "independence": spec["independence"],
            "episode": _episode(
                state,
                spec,
                ranking_by_id[spec["proposal"]["proposal_id"]],
                round_id,
                index,
                _source_map_ref,
                _source_refs,
                _source_verified_refs,
                _target_contract,
            ),
        }
        for index, spec in enumerate(ranked, start=1)
    ]
    packet = seal_packet({
        "schema": ROUND_SCHEMA,
        "round_id": round_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "episodes": wrapped,
        "independence_certificate": {
            "disjoint_nodes": len(nodes) == len(set(nodes)),
            "disjoint_resources": resources_disjoint,
            "independent_failure_domains": True,
            "rationale": rationale,
            "grade": audit["body"]["grade"],
            "admission_eligible": audit["body"]["admission_eligible"],
            "dimensions": audit["body"]["dimensions"],
            "shared_risks": audit["body"]["shared_risks"],
            "audit_sha256": audit["payload_sha256"],
        },
        "merge_policy": merge_policy,
        "max_parallel": max_parallel,
    })
    try:
        return contracts.validate_packet(root, "witsoc.round.v1", packet)
    except contracts.ContractError as exc:
        raise RoundError(str(exc)) from exc


def issue_round(
    root: Path,
    state_value: Mapping[str, Any],
    specifications: list[Mapping[str, Any]],
    explorer_state_value: Mapping[str, Any] | None = None,
    source_map_value: Mapping[str, Any] | None = None,
    stop_review_value: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = kernel.validate_state(state_value)
    prepared_specs = [_round_spec(root, state, value) for value in specifications]
    proposal_state = state
    selected_proposal_id = None
    source_map_ref = None
    source_refs: list[str] = []
    source_verified_refs: list[str] = []
    target_contract: Mapping[str, Any] | None = None
    if state["mode"] == "OPEN_DISCOVERY":
        if explorer_state_value is None:
            raise RoundError(
                "OPEN_DISCOVERY round issuance requires a sealed Explorer state and arbitration"
            )
        proposals = [item["proposal"] for item in prepared_specs]
        try:
            arbitration, _prepared = exploration.build_arbitration(
                root, state, explorer_state_value, proposals,
                source_map_value, stop_review_value,
            )
        except exploration.ExplorationError as exc:
            raise RoundError(str(exc)) from exc
        if arbitration["action"] != "WORK_ITEM_TO_RESEARCHER":
            raise RoundError("independent Researcher rounds require WORK_ITEM_TO_RESEARCHER")
        selected_proposal_id = arbitration["selected_proposal_id"]
        source_map_ref = explorer_state_value["source_coverage"]["source_map_ref"]
        source_refs = list(arbitration.get("source_refs", []))
        source_verified_refs = list(arbitration.get("source_verified_refs", []))
        target_contract = arbitration["target_contract"]
        try:
            state = exploration.apply_arbitration(root, state, arbitration)
        except exploration.ExplorationError as exc:
            raise RoundError(str(exc)) from exc
    packet = build_round(
        root,
        state,
        specifications,
        _prepared_specs=prepared_specs,
        _proposal_state_value=proposal_state,
        _selected_proposal_id=selected_proposal_id,
        _source_map_ref=source_map_ref,
        _source_refs=source_refs,
        _source_verified_refs=source_verified_refs,
        _target_contract=target_contract,
        **kwargs,
    )
    event = kernel.build_event(
        state,
        "ROUND_ISSUED",
        {"round": packet},
        f"round-issue:{packet['round_id']}",
    )
    return kernel.apply_event(state, event), packet


def validate_round_binding(
    root: Path,
    state_value: Mapping[str, Any],
    round_value: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = kernel.validate_state(state_value)
    round_packet = contracts.validate_packet(root, "witsoc.round.v1", round_value)
    pending = state["pending_episode"] or {}
    if pending.get("kind") != "ROUND":
        raise RoundError("there is no pending independent round")
    expected = {
        "round_id": pending["round_id"],
        "payload_sha256": pending["payload_sha256"],
        "target_sha256": round_packet["target_sha256"],
        "base_revision": pending["base_revision"],
        "base_state_sha256": pending["base_state_sha256"],
        "merge_policy": pending["merge_policy"],
    }
    expected["target_sha256"] = state["target"]["canonical_sha256"]
    for field, expected_value in expected.items():
        if round_packet.get(field) != expected_value:
            raise RoundError(f"round packet {field} does not bind pending Witsoc work")
    certificate = round_packet["independence_certificate"]
    if certificate.get("grade") != "STRONG" or not certificate.get("admission_eligible"):
        raise RoundError("pending round lacks a STRONG independence certificate")
    pending_episodes = {item["episode_id"]: item for item in pending["episodes"]}
    packet_episodes: dict[str, dict[str, Any]] = {}
    for wrapped in round_packet["episodes"]:
        required = {
            "actor_id", "failure_domain", "resource_keys", "independence", "episode",
        }
        _closed(wrapped, required, "wrapped round episode")
        episode = discovery.validate_episode(wrapped["episode"])
        episode_id = episode["episode_id"]
        if episode_id in packet_episodes or episode_id not in pending_episodes:
            raise RoundError("round packet has an unknown or duplicated episode")
        descriptor = pending_episodes[episode_id]
        bindings = {
            "payload_sha256": episode["payload_sha256"],
            "route_fingerprint": episode["route_fingerprint"],
            "core_fingerprint": episode["core_fingerprint"],
            "node_id": episode["node_id"],
            "actor_id": wrapped["actor_id"],
            "failure_domain": wrapped["failure_domain"],
            "resource_keys": wrapped["resource_keys"],
        }
        for field, value in bindings.items():
            if descriptor.get(field) != value:
                raise RoundError(f"round episode {episode_id!r} has stale {field}")
        episode_expected = {
            "target_sha256": round_packet["target_sha256"],
            "base_revision": round_packet["base_revision"],
            "base_state_sha256": round_packet["base_state_sha256"],
        }
        for field, value in episode_expected.items():
            if episode.get(field) != value:
                raise RoundError(f"round episode {episode_id!r} has stale {field}")
        adjudication = episode.get("adjudication") or {}
        if (
            adjudication.get("schema") != "witsoc.round-adjudication.v1"
            or adjudication.get("round_id") != round_packet["round_id"]
            or adjudication.get("actor_id") != wrapped["actor_id"]
            or adjudication.get("failure_domain") != wrapped["failure_domain"]
            or adjudication.get("resource_keys") != wrapped["resource_keys"]
        ):
            raise RoundError(f"round episode {episode_id!r} has stale adjudication")
        if state["mode"] == "OPEN_DISCOVERY":
            issued = next(
                (
                    event["payload"]["arbitration"]["payload_sha256"]
                    for event in reversed(state["events"])
                    if event["kind"] == "ARBITRATION_RECORDED"
                ),
                None,
            )
            if adjudication.get("arbitration_ref") != issued:
                raise RoundError(f"round episode {episode_id!r} lacks its Explorer arbitration")
        packet_episodes[episode_id] = wrapped
    if set(packet_episodes) != set(pending_episodes):
        raise RoundError("round packet does not contain every pending episode")
    return state, round_packet


def validate_child_delta(
    root: Path,
    state_value: Mapping[str, Any],
    round_value: Mapping[str, Any],
    child_value: Mapping[str, Any],
) -> dict[str, Any]:
    state, round_packet = validate_round_binding(root, state_value, round_value)
    child_schema = child_value.get("schema")
    if child_schema not in discovery.DELTA_SCHEMAS:
        raise RoundError("round child uses an unsupported research delta schema")
    child = contracts.validate_packet(root, child_schema, child_value)
    bindings = {
        item["episode_id"]: item
        for item in state["pending_episode"]["episodes"]
    }
    binding = bindings.get(child["episode_id"])
    if binding is None:
        raise RoundError(f"delta answers unknown round episode {child['episode_id']!r}")
    try:
        child = discovery.validate_delta_binding(
            child,
            state,
            binding,
            base_revision=round_packet["base_revision"],
            base_state_sha256=round_packet["base_state_sha256"],
        )
    except discovery.DiscoveryError as exc:
        raise RoundError(str(exc)) from exc
    existing = {item["item_id"] for item in state["frontier"]["items"]}
    for item in child["new_frontier"]:
        frontier = kernel._frontier_item(item)
        if frontier["target_sha256"] != state["target"]["canonical_sha256"]:
            raise RoundError("round child frontier crosses the frozen target")
        if set(frontier["dependencies"]) - existing:
            raise RoundError("round child frontier must depend only on the common snapshot")
    return child


def build_delta(
    root: Path,
    state_value: Mapping[str, Any],
    round_value: Mapping[str, Any],
    child_values: list[Mapping[str, Any]],
    *,
    round_delta_id: str,
) -> dict[str, Any]:
    state, round_packet = validate_round_binding(root, state_value, round_value)
    episodes = {item["episode"]["episode_id"]: item for item in round_packet["episodes"]}
    children = [
        validate_child_delta(root, state, round_packet, child) for child in child_values
    ]
    answered = [item["episode_id"] for item in children]
    if len(answered) != len(set(answered)):
        raise RoundError("round contains duplicate child returns")
    if set(answered) != set(episodes):
        missing = sorted(set(episodes) - set(answered))
        raise RoundError(f"round return is incomplete; missing={missing}")

    conflicts: list[dict[str, Any]] = []
    for left, right in combinations(round_packet["episodes"], 2):
        left_episode, right_episode = left["episode"], right["episode"]
        if left_episode["node_id"] == right_episode["node_id"]:
            conflicts.append({
                "kind": "SHARED_NODE", "severity": "NOTICE",
                "left": left_episode["episode_id"], "right": right_episode["episode_id"],
                "key": left_episode["node_id"],
            })
        for key in sorted(set(left["resource_keys"]) & set(right["resource_keys"])):
            conflicts.append({
                "kind": "SHARED_RESOURCE", "severity": "NOTICE",
                "left": left_episode["episode_id"], "right": right_episode["episode_id"],
                "key": key,
            })
    existing_frontier = {item["item_id"] for item in state["frontier"]["items"]}
    existing_obstructions = {
        item["obstruction_id"] for item in state["frontier"]["obstructions"]
    }
    frontier_owner: dict[str, str] = {}
    obstruction_owner: dict[str, str] = {}
    for child in children:
        for item in child["new_frontier"]:
            identifier = item["item_id"]
            if identifier in existing_frontier or identifier in frontier_owner:
                conflicts.append({
                    "kind": "FRONTIER_ID", "severity": "BLOCKING",
                    "left": frontier_owner.get(identifier, "kernel"),
                    "right": child["episode_id"], "key": identifier,
                })
            frontier_owner[identifier] = child["episode_id"]
        if child["new_obstruction"] is not None:
            identifier = child["new_obstruction"]["obstruction_id"]
            if identifier in existing_obstructions or identifier in obstruction_owner:
                conflicts.append({
                    "kind": "OBSTRUCTION_ID", "severity": "BLOCKING",
                    "left": obstruction_owner.get(identifier, "kernel"),
                    "right": child["episode_id"], "key": identifier,
                })
            obstruction_owner[identifier] = child["episode_id"]
    blocking = any(item["severity"] == "BLOCKING" for item in conflicts)
    outcome = (
        "CONFLICT" if blocking
        else "WAITING_EXTERNAL" if any(item["outcome"] == "WAITING_EXTERNAL" for item in children)
        else "MERGEABLE"
    )
    packet = seal_packet({
        "schema": DELTA_SCHEMA,
        "round_delta_id": round_delta_id,
        "round_id": round_packet["round_id"],
        "round_sha256": round_packet["payload_sha256"],
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "deltas": sorted(children, key=lambda item: item["episode_id"]),
        "conflicts": sorted(
            conflicts, key=lambda item: (item["severity"], item["kind"], item["left"], item["right"], item["key"])
        ),
        "aggregate_outcome": outcome,
    })
    try:
        return contracts.validate_packet(root, "witsoc.round-delta.v1", packet)
    except contracts.ContractError as exc:
        raise RoundError(str(exc)) from exc


def apply_delta(root: Path, state_value: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    packet = contracts.validate_packet(root, "witsoc.round-delta.v1", value)
    pending = state["pending_episode"] or {}
    expected = {
        "round_id": pending.get("round_id"),
        "round_sha256": pending.get("payload_sha256"),
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
    }
    if pending.get("kind") != "ROUND":
        raise RoundError("there is no pending independent round")
    for field, expected_value in expected.items():
        if packet[field] != expected_value:
            raise RoundError(f"round aggregate {field} does not bind current state")
    if packet["aggregate_outcome"] == "CONFLICT":
        raise RoundError("blocking round conflicts require Explorer adjudication before merge")
    event = kernel.build_event(
        state,
        "ROUND_RETURNED",
        {"round_delta": packet},
        f"round-return:{packet['round_delta_id']}",
    )
    return kernel.apply_event(state, event)
