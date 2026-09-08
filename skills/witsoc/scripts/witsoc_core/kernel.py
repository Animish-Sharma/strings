"""Replayable operational state around the existing evidence reducer."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from . import contracts
from .canonical import digest_value, seal_packet, utc_now, verify_packet_seal


STATE_SCHEMA = "witsoc.kernel-state.v1"
EVENT_SCHEMA = "witsoc.kernel-event.v1"
EVENT_KINDS = {
    "FRONTIER_ADD",
    "EVIDENCE_RECORD",
    "OBSTRUCTION_RECORD",
    "DECISION_RECORD",
    "EPISODE_ISSUED",
    "EPISODE_RETURNED",
    "ROUND_ISSUED",
    "ROUND_RETURNED",
    "FRONTIER_LINK",
    "ADMISSION_IMPORTED",
    "INVALIDATION_RECORDED",
    "ARBITRATION_RECORDED",
}
EVENT_PAYLOAD_SHAPES = {
    "FRONTIER_ADD": ({"item"}, {"activate"}),
    "FRONTIER_LINK": ({"item_id", "dependencies"}, set()),
    "EVIDENCE_RECORD": ({"record"}, set()),
    "OBSTRUCTION_RECORD": ({"obstruction"}, set()),
    "DECISION_RECORD": ({"decision"}, set()),
    "EPISODE_ISSUED": ({"episode"}, set()),
    "EPISODE_RETURNED": ({"delta"}, set()),
    "ROUND_ISSUED": ({"round"}, set()),
    "ROUND_RETURNED": ({"round_delta"}, set()),
    "ADMISSION_IMPORTED": ({
        "item_id", "claim_id", "status", "admission_id", "evidence_refs",
        "frame_revision", "frame_state_sha256",
    }, set()),
    "INVALIDATION_RECORDED": ({"evidence_sha256", "invalidation_ref"}, set()),
    "ARBITRATION_RECORDED": ({"arbitration"}, set()),
}
ITEM_KINDS = {
    "TARGET", "ENDPOINT", "OPEN_CORE", "REDUCTION", "HYPOTHESIS",
    "COMPUTATION", "RETRIEVAL", "VERIFICATION_OBLIGATION", "PRODUCT",
    "EQUIVALENT_CORE", "NECESSARY_CONDITION", "SUFFICIENT_CONDITION", "INTERMEDIATE_CLAIM",
    "DISCRIMINATOR", "EXTERNAL_DEPENDENCY", "EMPIRICAL_SIGNAL",
}
STATUSES = {
    "OPEN", "CONJECTURE", "GAP", "FAILED_ATTEMPT", "REJECTED",
    "CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED",
}
ACCEPTED = {"CHECKED_BOUNDED", "SKETCH", "PARTIAL", "CONDITIONAL", "VERIFIED"}
_EVIDENCE_RANK = {
    "UNKNOWN": 0,
    "SEARCH_BOUNDED": 1,
    "EMPIRICAL": 2,
    "COMPUTATIONAL_BOUNDED": 3,
    "SOURCE_VERIFIED": 4,
    "EXACT": 5,
}
_BOUNDED_EVIDENCE = {
    "UNKNOWN", "SEARCH_BOUNDED", "EMPIRICAL", "COMPUTATIONAL_BOUNDED",
}
_DISPATCH_ACTIONS = {
    "WORK_ITEM_TO_GENERATOR", "WORK_ITEM_TO_RESEARCHER", "RETRY_WITH_MUTATION",
}
_TERMINAL_ACTIONS = {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}


class KernelError(ValueError):
    pass


def state_digest(state: Mapping[str, Any]) -> str:
    return digest_value({key: value for key, value in state.items() if key != "state_sha256"})


def target_record(
    statement: str,
    intent: str = "",
    constraints: list[str] | None = None,
    canonical_sha256: str | None = None,
) -> dict[str, Any]:
    statement = statement.strip()
    if not statement:
        raise KernelError("target statement is empty")
    body = {
        "statement": statement,
        "intent": intent.strip(),
        "constraints": list(constraints or []),
    }
    content_sha256 = digest_value(body)
    external = canonical_sha256 or content_sha256
    if len(external) != 64 or any(char not in "0123456789abcdef" for char in external):
        raise KernelError("canonical target hash must be 64 lowercase hexadecimal characters")
    return {**body, "content_sha256": content_sha256, "canonical_sha256": external}


def _blank(genesis: Mapping[str, Any]) -> dict[str, Any]:
    target = copy.deepcopy(genesis["target"])
    root = {
        "item_id": "ROOT",
        "kind": "TARGET",
        "statement": target["statement"],
        "target_sha256": target["canonical_sha256"],
        "status": "OPEN",
        "dependencies": [],
        "evidence_refs": [],
        "route_fingerprint": None,
        "admission_ref": None,
    }
    state = {
        "schema": STATE_SCHEMA,
        "kernel_id": genesis["kernel_id"],
        "genesis": copy.deepcopy(dict(genesis)),
        "target": target,
        "mode": genesis["mode"],
        "domains": list(genesis["domains"]),
        "ceiling": genesis["ceiling"],
        "revision": 0,
        "previous_state_sha256": None,
        "status": "OPEN",
        "outcome": "OPEN",
        "frontier": {"items": [root], "active": ["ROOT"], "obstructions": []},
        "evidence": [],
        "decisions": [],
        "route_attempts": [],
        "pending_episode": None,
        "frame_projection": None,
        "events": [],
    }
    state["state_sha256"] = state_digest(state)
    return state


def new_state(
    target: Mapping[str, Any],
    mode: str,
    domains: list[str],
    ceiling: str = "VERIFIED",
    route_sha256: str | None = None,
    activation_binding: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if ceiling not in STATUSES:
        raise KernelError(f"unknown ceiling {ceiling!r}")
    canonical_sha256 = str(target.get("canonical_sha256", ""))
    genesis = {
        "kernel_id": f"WK-{canonical_sha256[:16]}",
        "created_at": created_at or utc_now(),
        "target": copy.deepcopy(dict(target)),
        "mode": mode,
        "domains": sorted(set(domains)),
        "ceiling": ceiling,
        "route_sha256": route_sha256,
        "activation_binding": (
            copy.deepcopy(dict(activation_binding))
            if activation_binding is not None else None
        ),
    }
    state = _blank(genesis)
    validate_state(state)
    return state


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = required - set(value)
    extra = set(value) - required
    if missing or extra:
        raise KernelError(f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")


def validate_event(event: Mapping[str, Any], state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    required = {
        "schema", "event_id", "target_sha256", "base_revision",
        "base_state_sha256", "kind", "payload", "payload_sha256",
    }
    _closed(event, required, "kernel event")
    if event["schema"] != EVENT_SCHEMA or event["kind"] not in EVENT_KINDS:
        raise KernelError("kernel event schema or kind is invalid")
    if not isinstance(event["event_id"], str) or not event["event_id"].strip():
        raise KernelError("kernel event_id is empty")
    if not isinstance(event["payload"], dict):
        raise KernelError("kernel event payload must be an object")
    required_payload, optional_payload = EVENT_PAYLOAD_SHAPES[event["kind"]]
    payload_keys = set(event["payload"])
    missing = required_payload - payload_keys
    extra = payload_keys - required_payload - optional_payload
    if missing or extra:
        raise KernelError(
            f"kernel event payload shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if not verify_packet_seal(event):
        raise KernelError("kernel event seal is broken")
    if state is not None:
        if event["target_sha256"] != state["target"]["canonical_sha256"]:
            raise KernelError("kernel event target differs from the frozen target")
        if event["base_revision"] != state["revision"]:
            raise KernelError("kernel event was produced against a stale revision")
        if event["base_state_sha256"] != state["state_sha256"]:
            raise KernelError("kernel event was produced against different state bytes")
    return copy.deepcopy(dict(event))


def build_event(
    state: Mapping[str, Any],
    kind: str,
    payload: Mapping[str, Any],
    event_id: str,
    *,
    _admission_authority: bool = False,
    _explorer_authority: bool = False,
) -> dict[str, Any]:
    if kind not in EVENT_KINDS:
        raise KernelError(f"unknown event kind {kind!r}")
    if kind == "ADMISSION_IMPORTED" and not _admission_authority:
        raise KernelError("admission events can only be built from reducer-owned frame state")
    if kind == "ARBITRATION_RECORDED" and not _explorer_authority:
        raise KernelError("arbitration events can only be built from validated Explorer state")
    event = seal_packet({
        "schema": EVENT_SCHEMA,
        "event_id": event_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"],
        "kind": kind,
        "payload": copy.deepcopy(dict(payload)),
    })
    return validate_event(event, state)


def _items(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["item_id"]: item for item in state["frontier"]["items"]}


def _frontier_item(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "item_id", "kind", "statement", "target_sha256", "status", "dependencies",
        "evidence_refs", "route_fingerprint", "admission_ref",
    }
    _closed(value, required, "frontier item")
    item = copy.deepcopy(dict(value))
    if item["kind"] not in ITEM_KINDS or item["status"] not in STATUSES:
        raise KernelError("frontier item kind or status is invalid")
    if item["status"] != "OPEN":
        raise KernelError("new frontier items enter OPEN; status comes from admission")
    if not item["item_id"] or not item["statement"].strip():
        raise KernelError("frontier item id and statement are required")
    if (
        not isinstance(item["target_sha256"], str)
        or len(item["target_sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in item["target_sha256"])
    ):
        raise KernelError("frontier item target hash is malformed")
    if not isinstance(item["dependencies"], list) or not isinstance(item["evidence_refs"], list):
        raise KernelError("frontier item dependencies and evidence_refs must be arrays")
    return item


def _return_evidence_ceiling(delta: Mapping[str, Any]) -> str:
    children = delta.get("deltas")
    if isinstance(children, list) and children:
        classes = [_return_evidence_ceiling(item) for item in children]
        return min(classes, key=lambda item: _EVIDENCE_RANK.get(item, 0))
    reasoning_state = delta.get("reasoning")
    if not isinstance(reasoning_state, Mapping):
        return "UNKNOWN"
    claims = {item["claim_id"]: item for item in reasoning_state.get("claims", [])}
    closure = [
        claims[item]
        for item in reasoning_state.get("closure_candidate_ids", [])
        if item in claims
    ]
    classes = [
        item.get("epistemic_class", "UNKNOWN")
        for item in (closure or list(claims.values()))
    ]
    if not classes:
        return "UNKNOWN"
    result = min(classes, key=lambda item: _EVIDENCE_RANK.get(item, 0))
    return result if result in _EVIDENCE_RANK else "UNKNOWN"


def _assert_frontier_graph(state: Mapping[str, Any]) -> None:
    items = _items(state)
    if "ROOT" not in items:
        raise KernelError("frontier graph lacks ROOT")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(identifier: str) -> None:
        if identifier in visiting:
            raise KernelError(f"frontier dependency cycle passes through {identifier!r}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in items[identifier]["dependencies"]:
            if dependency not in items:
                raise KernelError("frontier graph contains an unknown dependency")
            walk(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    walk("ROOT")
    if set(items) != visited:
        raise KernelError("frontier graph contains nodes without a ROOT path")


def _apply_payload(state: dict[str, Any], event: Mapping[str, Any]) -> None:
    kind, payload = event["kind"], event["payload"]
    existing = _items(state)
    last_event = state["events"][-1] if state["events"] else None
    if (
        last_event
        and last_event["kind"] in {"EPISODE_RETURNED", "ROUND_RETURNED"}
        and any(item.get("adjudicated_by") is None for item in state["route_attempts"])
        and kind != "ARBITRATION_RECORDED"
    ):
        raise KernelError("a strict Researcher return requires immediate Explorer arbitration")
    if kind == "FRONTIER_ADD":
        item = _frontier_item(payload["item"])
        if item["target_sha256"] != state["target"]["canonical_sha256"]:
            raise KernelError("frontier item differs from the frozen target")
        if item["item_id"] in existing:
            raise KernelError(f"frontier item {item['item_id']!r} already exists")
        missing = sorted(set(item["dependencies"]) - set(existing))
        if missing:
            raise KernelError(f"frontier item has unknown dependencies: {missing}")
        state["frontier"]["items"].append(item)
        if payload.get("activate", True):
            state["frontier"]["active"].append(item["item_id"])
    elif kind == "FRONTIER_LINK":
        item_id = payload["item_id"]
        dependencies = payload["dependencies"]
        if item_id not in existing or not isinstance(dependencies, list):
            raise KernelError("frontier link names an unknown item or malformed dependencies")
        missing = sorted(set(dependencies) - set(existing))
        if missing or item_id in dependencies:
            raise KernelError(f"frontier link has invalid dependencies: {missing or [item_id]}")
        existing[item_id]["dependencies"] = list(dict.fromkeys(dependencies))
    elif kind == "EVIDENCE_RECORD":
        record = copy.deepcopy(payload["record"])
        expected = digest_value({key: value for key, value in record.items() if key != "evidence_sha256"})
        if record.get("evidence_sha256") != expected:
            raise KernelError("evidence record is not content-addressed")
        if any(item["evidence_sha256"] == expected for item in state["evidence"]):
            raise KernelError("evidence record already exists")
        state["evidence"].append(record)
    elif kind == "OBSTRUCTION_RECORD":
        obstruction = copy.deepcopy(payload["obstruction"])
        required = {
            "obstruction_id", "statement", "route_fingerprint", "core_fingerprint",
            "evidence_refs", "revival_condition",
        }
        _closed(obstruction, required, "obstruction")
        if any(item["obstruction_id"] == obstruction["obstruction_id"] for item in state["frontier"]["obstructions"]):
            raise KernelError("obstruction id already exists")
        state["frontier"]["obstructions"].append(obstruction)
    elif kind == "DECISION_RECORD":
        decision = copy.deepcopy(payload["decision"])
        required = {"decision_id", "action", "basis_refs", "alternatives", "changed_axis"}
        _closed(decision, required, "decision")
        if not decision["basis_refs"]:
            raise KernelError("a decision requires a non-empty basis")
        state["decisions"].append(decision)
        if decision["action"] == "HONEST_STOP":
            state["outcome"] = "STOPPED"
        elif decision["action"] == "WAIT_EXTERNAL":
            state["outcome"] = "WAITING_EXTERNAL"
    elif kind == "ARBITRATION_RECORDED":
        arbitration = contracts.validate_packet(
            Path(__file__).resolve().parents[2],
            "witsoc.explorer-arbitration.v1",
            payload["arbitration"],
        )
        if state["pending_episode"] is not None:
            raise KernelError("Explorer arbitration cannot run while work is pending")
        if (
            arbitration["target_sha256"] != state["target"]["canonical_sha256"]
            or arbitration["base_revision"] != state["revision"]
            or arbitration["base_state_sha256"] != state["state_sha256"]
        ):
            raise KernelError("Explorer arbitration does not bind current state")
        prior = state["events"][-1] if state["events"] else None
        if prior and prior["kind"] in {"ARBITRATION_RECORDED", "DECISION_RECORD"}:
            prior_decision = prior["payload"].get(
                "arbitration", prior["payload"].get("decision", {})
            )
            if prior_decision.get("action") in _TERMINAL_ACTIONS:
                raise KernelError("terminal Explorer state cannot be arbitrated again")
            if (
                prior["kind"] == "ARBITRATION_RECORDED"
                and prior_decision.get("action") in _DISPATCH_ACTIONS
            ):
                raise KernelError("a dispatch arbitration must be consumed by its bound issue")
        expected_phase = (
            "RETURN_ARBITRATION"
            if prior and prior["kind"] in {"EPISODE_RETURNED", "ROUND_RETURNED"}
            else "POST_ARBITRATION"
            if prior and prior["kind"] in {"ARBITRATION_RECORDED", "DECISION_RECORD"}
            else "TRIAGE"
        )
        if arbitration["phase"] != expected_phase:
            raise KernelError("Explorer arbitration is out of lifecycle phase")
        returned_delta = None
        expected_return_ref = None
        if prior and prior["kind"] == "EPISODE_RETURNED":
            returned_delta = prior["payload"]["delta"]
            expected_return_ref = returned_delta["payload_sha256"]
        elif prior and prior["kind"] == "ROUND_RETURNED":
            returned_delta = prior["payload"]["round_delta"]
            expected_return_ref = returned_delta["payload_sha256"]
        if arbitration["return_ref"] != expected_return_ref:
            raise KernelError("Explorer arbitration does not bind the latest return")
        expected_ceiling = (
            _return_evidence_ceiling(returned_delta)
            if returned_delta is not None else "UNKNOWN"
        )
        if arbitration["evidence_ceiling"] != expected_ceiling:
            raise KernelError("Explorer arbitration misstates the return evidence ceiling")
        action = arbitration["action"]
        selected_route = arbitration["selected_route"]
        if action in _DISPATCH_ACTIONS:
            if (
                selected_route is None
                or arbitration["selected_proposal_id"] is None
                or arbitration["proposal_set_sha256"] is None
                or selected_route["proposal_id"] != arbitration["selected_proposal_id"]
            ):
                raise KernelError("dispatch arbitration lacks one bound semantic route")
            if action == "RETRY_WITH_MUTATION" and not arbitration["changed_axis"].strip():
                raise KernelError("retry arbitration lacks its changed axis")
        elif selected_route is not None or arbitration["selected_proposal_id"] is not None:
            raise KernelError("non-dispatch arbitration cannot select a semantic route")
        if arbitration["evidence_ceiling"] in _BOUNDED_EVIDENCE and (
            arbitration["route_disposition"] == "EXHAUSTED"
            or arbitration["frontier_delta"]["accepted_obstructions"]
        ):
            raise KernelError("bounded evidence cannot close a route or admit an obstruction")
        returned_outcome = (
            returned_delta.get("outcome", returned_delta.get("aggregate_outcome"))
            if returned_delta is not None else None
        )
        if arbitration["route_disposition"] == "EXHAUSTED" and returned_outcome not in {
            "ROUTE_REFUTED",
        }:
            raise KernelError("route exhaustion lacks a closure-capable return")
        if arbitration["frontier_delta"]["accepted_obstructions"] and returned_outcome not in {
            "NEW_OBSTRUCTION", "METHOD_BARRIER",
        }:
            raise KernelError("accepted obstruction lacks a typed barrier return")
        if action == "DIRECT_ANSWER" and state["status"] not in ACCEPTED:
            raise KernelError("DIRECT_ANSWER requires reducer-admitted frontier status")
        if action == "HONEST_STOP" and (
            arbitration["source_coverage_status"] != "BOUNDED_COMPLETE"
            or arbitration["stop_review_ref"] is None
            or not arbitration["alternatives"]
            or not arbitration["frontier_delta"]["active_ids"]
        ):
            raise KernelError("HONEST_STOP lacks bounded coverage, review, alternatives, or open core")
        delta = arbitration["frontier_delta"]
        for raw in delta["additions"]:
            item = _frontier_item(raw)
            if item["target_sha256"] != state["target"]["canonical_sha256"]:
                raise KernelError("arbitrated frontier addition differs from the target")
            if item["item_id"] in _items(state):
                raise KernelError("arbitrated frontier addition already exists")
            missing = sorted(set(item["dependencies"]) - set(_items(state)))
            if missing:
                raise KernelError(f"arbitrated frontier addition has unknown dependencies: {missing}")
            state["frontier"]["items"].append(item)
        for relink in delta["relinks"]:
            existing = _items(state)
            item_id = relink["item_id"]
            dependencies = relink["dependencies"]
            if item_id not in existing:
                raise KernelError("arbitrated frontier relink names an unknown item")
            missing = sorted(set(dependencies) - set(existing))
            if missing or item_id in dependencies:
                raise KernelError(f"arbitrated frontier relink is invalid: {missing or [item_id]}")
            if {item["dependency_id"] for item in relink["relations"]} != set(dependencies):
                raise KernelError("arbitrated frontier relations differ from dependencies")
            existing[item_id]["dependencies"] = list(dependencies)
        active = delta["active_ids"]
        if set(active) - set(_items(state)):
            raise KernelError("arbitrated active frontier names unknown items")
        state["frontier"]["active"] = list(active)
        asserted_pairs = [
            (item["from_id"], item["to_id"])
            for item in delta["edge_assertions"]
        ]
        expected_pairs = {
            (item["item_id"], dependency)
            for item in state["frontier"]["items"]
            for dependency in item["dependencies"]
        }
        if len(asserted_pairs) != len(set(asserted_pairs)) or set(asserted_pairs) != expected_pairs:
            raise KernelError("arbitrated edge assertions differ from the resulting frontier")
        _assert_frontier_graph(state)
        for obstruction in delta["accepted_obstructions"]:
            required = {
                "obstruction_id", "statement", "route_fingerprint", "core_fingerprint",
                "evidence_refs", "revival_condition",
            }
            _closed(obstruction, required, "arbitrated obstruction")
            if any(
                item["obstruction_id"] == obstruction["obstruction_id"]
                for item in state["frontier"]["obstructions"]
            ):
                raise KernelError("arbitrated obstruction id already exists")
            state["frontier"]["obstructions"].append(copy.deepcopy(obstruction))
        return_ref = arbitration.get("return_ref")
        if return_ref:
            attempts = [
                item for item in state["route_attempts"]
                if item.get("delta_sha256") == return_ref
            ]
            last = state["events"][-1] if state["events"] else None
            if not attempts and last and last["kind"] == "ROUND_RETURNED":
                aggregate = last["payload"]["round_delta"]
                if aggregate.get("payload_sha256") == return_ref:
                    child_refs = {item["payload_sha256"] for item in aggregate["deltas"]}
                    attempts = [
                        item for item in state["route_attempts"]
                        if item.get("delta_sha256") in child_refs
                    ]
            if not attempts:
                raise KernelError("Explorer arbitration does not identify a returned route")
            for attempt in attempts:
                attempt["adjudicated_by"] = arbitration["payload_sha256"]
                attempt["route_disposition"] = arbitration["route_disposition"]
                attempt["exhausted"] = arbitration["route_disposition"] == "EXHAUSTED"
        state["decisions"].append(copy.deepcopy(arbitration))
        if action == "HONEST_STOP":
            state["outcome"] = "STOPPED"
        elif action == "WAIT_EXTERNAL":
            state["outcome"] = "WAITING_EXTERNAL"
        elif action == "DIRECT_ANSWER":
            state["outcome"] = "ANSWERED"
        elif action in {
            "REFRAME_FRONTIER", "EXPAND_FRONTIER", "PAUSE_WITH_FRONTIER",
            "WORK_ITEM_TO_GENERATOR", "WORK_ITEM_TO_RESEARCHER",
            "RETRY_WITH_MUTATION", "DEMOTE",
        }:
            state["outcome"] = "OPEN"
    elif kind == "EPISODE_ISSUED":
        episode = copy.deepcopy(payload["episode"])
        if state["events"]:
            prior = state["events"][-1]
            prior_action = (
                prior["payload"].get("arbitration", prior["payload"].get("decision", {})).get("action")
                if prior["kind"] in {"ARBITRATION_RECORDED", "DECISION_RECORD"}
                else None
            )
            if prior_action in {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}:
                raise KernelError("terminal Explorer decision forbids new work")
        if state["mode"] == "OPEN_DISCOVERY":
            if not state["events"] or state["events"][-1]["kind"] != "ARBITRATION_RECORDED":
                raise KernelError("open discovery issue lacks immediate Explorer arbitration")
            arbitration = state["events"][-1]["payload"]["arbitration"]
            route = arbitration.get("selected_route") or {}
            if arbitration["action"] not in _DISPATCH_ACTIONS:
                raise KernelError("Explorer arbitration does not authorize an episode")
            if (
                episode.get("adjudication", {}).get("arbitration_ref")
                != arbitration["payload_sha256"]
                or episode.get("adjudication", {}).get("source_map_ref")
                != arbitration.get("source_map_ref")
                or episode.get("adjudication", {}).get("source_refs", [])
                != arbitration.get("source_refs", [])
                or episode.get("adjudication", {}).get("source_verified_refs", [])
                != arbitration.get("source_verified_refs", [])
                or episode.get("adjudication", {}).get("target_contract")
                != arbitration.get("target_contract")
                or episode.get("route_fingerprint") != route.get("route_fingerprint")
                or episode.get("core_fingerprint") != route.get("core_fingerprint")
                or episode.get("adjudication", {}).get("selected_proposal_id")
                != arbitration["selected_proposal_id"]
            ):
                raise KernelError("issued episode differs from its Explorer-selected route")
        if state["pending_episode"] is not None:
            raise KernelError("the bounded loop already has a pending episode")
        state["pending_episode"] = {
            "episode_id": episode["episode_id"],
            "payload_sha256": episode["payload_sha256"],
            "route_fingerprint": episode["route_fingerprint"],
            "core_fingerprint": episode["core_fingerprint"],
            "node_id": episode["node_id"],
        }
    elif kind == "EPISODE_RETURNED":
        pending = state["pending_episode"]
        delta = copy.deepcopy(payload["delta"])
        if pending is None or delta.get("episode_id") != pending["episode_id"]:
            raise KernelError("research delta does not answer the pending episode")
        issued_index = next(
            (
                index for index in range(len(state["events"]) - 1, -1, -1)
                if state["events"][index]["kind"] == "EPISODE_ISSUED"
                and state["events"][index]["payload"]["episode"]["episode_id"] == delta["episode_id"]
            ),
            None,
        )
        strict_episode = bool(
            issued_index is not None
            and issued_index > 0
            and state["events"][issued_index - 1]["kind"] == "ARBITRATION_RECORDED"
        )
        attempt = {
            "episode_id": delta["episode_id"],
            "route_fingerprint": pending["route_fingerprint"],
            "core_fingerprint": pending["core_fingerprint"],
            "outcome": delta["outcome"],
            "delta_sha256": delta["payload_sha256"],
            "changed_axis": delta.get("changed_axis", ""),
        }
        if strict_episode:
            attempt.update({
                "adjudicated_by": None,
                "route_disposition": "PENDING",
                "exhausted": False,
            })
        state["route_attempts"].append(attempt)
        state["pending_episode"] = None
        if not strict_episode:
            for item in delta.get("new_frontier", []):
                candidate = _frontier_item(item)
                if candidate["target_sha256"] != state["target"]["canonical_sha256"]:
                    raise KernelError("returned frontier item differs from the frozen target")
                if candidate["item_id"] in _items(state):
                    raise KernelError(f"returned frontier item {candidate['item_id']!r} already exists")
                state["frontier"]["items"].append(candidate)
                state["frontier"]["active"].append(candidate["item_id"])
            if delta.get("new_obstruction"):
                obstruction = delta["new_obstruction"]
                if any(item["obstruction_id"] == obstruction["obstruction_id"] for item in state["frontier"]["obstructions"]):
                    raise KernelError("returned obstruction id already exists")
                state["frontier"]["obstructions"].append(obstruction)
        if delta["outcome"] == "WAITING_EXTERNAL":
            state["outcome"] = "WAITING_EXTERNAL"
        elif delta["outcome"] == "NO_PROGRESS":
            state["outcome"] = "OPEN"
    elif kind == "ROUND_ISSUED":
        round_packet = copy.deepcopy(payload["round"])
        if state["events"]:
            prior = state["events"][-1]
            prior_action = (
                prior["payload"].get("arbitration", prior["payload"].get("decision", {})).get("action")
                if prior["kind"] in {"ARBITRATION_RECORDED", "DECISION_RECORD"}
                else None
            )
            if prior_action in {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}:
                raise KernelError("terminal Explorer decision forbids new work")
        if state["mode"] == "OPEN_DISCOVERY":
            if not state["events"] or state["events"][-1]["kind"] != "ARBITRATION_RECORDED":
                raise KernelError("open discovery round lacks immediate Explorer arbitration")
            arbitration = state["events"][-1]["payload"]["arbitration"]
            route = arbitration.get("selected_route") or {}
            matching = [
                wrapped["episode"]
                for wrapped in round_packet.get("episodes", [])
                if wrapped.get("episode", {}).get("adjudication", {}).get("selected_proposal_id")
                == arbitration["selected_proposal_id"]
            ]
            if arbitration["action"] != "WORK_ITEM_TO_RESEARCHER" or len(matching) != 1:
                raise KernelError("Explorer arbitration does not authorize this Researcher round")
            selected = matching[0]
            if (
                selected.get("adjudication", {}).get("arbitration_ref")
                != arbitration["payload_sha256"]
                or any(
                    wrapped.get("episode", {}).get("adjudication", {}).get("source_map_ref")
                    != arbitration.get("source_map_ref")
                    for wrapped in round_packet.get("episodes", [])
                )
                or any(
                    wrapped.get("episode", {}).get("adjudication", {}).get("source_refs", [])
                    != arbitration.get("source_refs", [])
                    for wrapped in round_packet.get("episodes", [])
                )
                or any(
                    wrapped.get("episode", {}).get("adjudication", {}).get("source_verified_refs", [])
                    != arbitration.get("source_verified_refs", [])
                    for wrapped in round_packet.get("episodes", [])
                )
                or selected.get("route_fingerprint") != route.get("route_fingerprint")
                or selected.get("core_fingerprint") != route.get("core_fingerprint")
                or any(
                    wrapped.get("episode", {}).get("adjudication", {}).get("arbitration_ref")
                    != arbitration["payload_sha256"]
                    for wrapped in round_packet.get("episodes", [])
                )
            ):
                raise KernelError("issued round differs from its Explorer-selected portfolio")
        if state["pending_episode"] is not None:
            raise KernelError("the bounded loop already has pending work")
        state["pending_episode"] = {
            "kind": "ROUND",
            "round_id": round_packet["round_id"],
            "payload_sha256": round_packet["payload_sha256"],
            "base_revision": round_packet["base_revision"],
            "base_state_sha256": round_packet["base_state_sha256"],
            "merge_policy": round_packet["merge_policy"],
            "episodes": [
                {
                    "episode_id": item["episode"]["episode_id"],
                    "payload_sha256": item["episode"]["payload_sha256"],
                    "route_fingerprint": item["episode"]["route_fingerprint"],
                    "core_fingerprint": item["episode"]["core_fingerprint"],
                    "node_id": item["episode"]["node_id"],
                    "actor_id": item["actor_id"],
                    "failure_domain": item["failure_domain"],
                    "resource_keys": list(item["resource_keys"]),
                }
                for item in round_packet["episodes"]
            ],
        }
    elif kind == "ROUND_RETURNED":
        pending = state["pending_episode"]
        aggregate = copy.deepcopy(payload["round_delta"])
        if pending is None or pending.get("kind") != "ROUND":
            raise KernelError("round delta does not answer pending work")
        if (
            aggregate.get("round_id") != pending["round_id"]
            or aggregate.get("round_sha256") != pending["payload_sha256"]
            or aggregate.get("aggregate_outcome") == "CONFLICT"
        ):
            raise KernelError("round delta does not bind the issued round or still conflicts")
        episode_index = {item["episode_id"]: item for item in pending["episodes"]}
        returned_ids = [item["episode_id"] for item in aggregate["deltas"]]
        if set(returned_ids) != set(episode_index) or len(returned_ids) != len(set(returned_ids)):
            raise KernelError("round delta does not return every issued episode exactly once")
        new_frontier = sorted(
            (copy.deepcopy(item) for delta in aggregate["deltas"] for item in delta["new_frontier"]),
            key=lambda item: item["item_id"],
        )
        new_obstructions = sorted(
            (copy.deepcopy(delta["new_obstruction"]) for delta in aggregate["deltas"] if delta["new_obstruction"] is not None),
            key=lambda item: item["obstruction_id"],
        )
        issued_index = next(
            (
                index for index in range(len(state["events"]) - 1, -1, -1)
                if state["events"][index]["kind"] == "ROUND_ISSUED"
                and state["events"][index]["payload"]["round"]["round_id"] == aggregate["round_id"]
            ),
            None,
        )
        strict_round = bool(
            issued_index is not None
            and issued_index > 0
            and state["events"][issued_index - 1]["kind"] == "ARBITRATION_RECORDED"
        )
        for delta in sorted(aggregate["deltas"], key=lambda item: item["episode_id"]):
            episode = episode_index[delta["episode_id"]]
            attempt = {
                "episode_id": delta["episode_id"],
                "route_fingerprint": episode["route_fingerprint"],
                "core_fingerprint": episode["core_fingerprint"],
                "outcome": delta["outcome"],
                "delta_sha256": delta["payload_sha256"],
                "changed_axis": delta.get("changed_axis", ""),
            }
            if strict_round:
                attempt.update({
                    "adjudicated_by": None,
                    "route_disposition": "PENDING",
                    "exhausted": False,
                })
            state["route_attempts"].append(attempt)
        if not strict_round:
            for item in new_frontier:
                candidate = _frontier_item(item)
                if candidate["target_sha256"] != state["target"]["canonical_sha256"]:
                    raise KernelError("round frontier item differs from the frozen target")
                if candidate["item_id"] in _items(state):
                    raise KernelError("round frontier item id already exists")
                state["frontier"]["items"].append(candidate)
                state["frontier"]["active"].append(candidate["item_id"])
            for obstruction in new_obstructions:
                if any(
                    item["obstruction_id"] == obstruction["obstruction_id"]
                    for item in state["frontier"]["obstructions"]
                ):
                    raise KernelError("round obstruction id already exists")
                state["frontier"]["obstructions"].append(obstruction)
        state["pending_episode"] = None
        state["outcome"] = (
            "WAITING_EXTERNAL"
            if aggregate["aggregate_outcome"] == "WAITING_EXTERNAL"
            else "OPEN"
        )
    elif kind == "ADMISSION_IMPORTED":
        item_id = payload["item_id"]
        if item_id not in existing:
            raise KernelError(f"admission references unknown frontier item {item_id!r}")
        status = payload["status"]
        if status not in STATUSES:
            raise KernelError("imported frame status is invalid")
        item = existing[item_id]
        item["status"] = status
        item["admission_ref"] = payload["admission_id"]
        item["evidence_refs"] = list(payload["evidence_refs"])
        state["frame_projection"] = {
            "frame_state_sha256": payload["frame_state_sha256"],
            "frame_revision": payload["frame_revision"],
            "claim_id": payload["claim_id"],
            "import_event_id": event["event_id"],
        }
        if item_id == "ROOT":
            state["status"] = status
            state["outcome"] = (
                "SOLVED" if status == "VERIFIED"
                else "DISPROVED" if status == "REJECTED"
                else "PARTIAL" if status in ACCEPTED
                else "OPEN"
            )
    elif kind == "INVALIDATION_RECORDED":
        reference = payload["evidence_sha256"]
        records = [item for item in state["evidence"] if item["evidence_sha256"] == reference]
        if not records:
            raise KernelError("invalidation references unknown evidence")
        records[0]["invalidated_by"] = payload["invalidation_ref"]


def apply_event(
    state_value: Mapping[str, Any],
    event_value: Mapping[str, Any],
    *,
    _replaying: bool = False,
) -> dict[str, Any]:
    state = validate_state(state_value, replay=not _replaying)
    event = validate_event(event_value, state)
    updated = copy.deepcopy(state)
    _apply_payload(updated, event)
    updated["previous_state_sha256"] = state["state_sha256"]
    updated["revision"] += 1
    updated["events"].append(event)
    updated["state_sha256"] = state_digest(updated)
    validate_state(updated, replay=False)
    return updated


def validate_state(state_value: Mapping[str, Any], *, replay: bool = True) -> dict[str, Any]:
    state = copy.deepcopy(dict(state_value))
    required = {
        "schema", "kernel_id", "genesis", "target", "mode", "domains", "ceiling",
        "revision", "previous_state_sha256", "status", "outcome", "frontier",
        "evidence", "decisions", "route_attempts", "pending_episode",
        "frame_projection", "events", "state_sha256",
    }
    _closed(state, required, "kernel state")
    if state["schema"] != STATE_SCHEMA or state["state_sha256"] != state_digest(state):
        raise KernelError("kernel state schema or content hash is invalid")
    if state["revision"] != len(state["events"]):
        raise KernelError("kernel revision does not equal the event count")
    if state["target"] != state["genesis"]["target"]:
        raise KernelError("frozen target differs from genesis")
    activation = state["genesis"].get("activation_binding")
    if activation is not None:
        required_activation = {
            "schema", "receipt_sha256", "target_sha256", "route_sha256",
            "workspace_root", "task_dir_relative", "worker_mode", "domains",
            "packages", "resources",
        }
        _closed(activation, required_activation, "activation binding")
        if activation["schema"] != "witsoc.activation-binding.v1":
            raise KernelError("activation binding schema is invalid")
        if activation["target_sha256"] != state["target"]["canonical_sha256"]:
            raise KernelError("activation binding targets different research bytes")
        if activation["route_sha256"] != state["genesis"].get("route_sha256"):
            raise KernelError("activation binding route differs from genesis")
        if activation["domains"] != state["domains"]:
            raise KernelError("activation binding domains differ from kernel domains")
        for field in ("receipt_sha256", "target_sha256", "route_sha256"):
            value = activation[field]
            if (
                not isinstance(value, str) or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise KernelError(f"activation binding {field} is not a SHA-256 digest")
        if not isinstance(activation["workspace_root"], str) or not activation["workspace_root"]:
            raise KernelError("activation binding workspace is empty")
        task_relative = Path(str(activation["task_dir_relative"]))
        if task_relative.is_absolute() or ".." in task_relative.parts or not task_relative.parts:
            raise KernelError("activation binding task directory is not safely relative")
        if activation["worker_mode"] not in {"INHERIT_BOUND", "ISOLATED_RETURN"}:
            raise KernelError("activation binding worker mode is invalid")
        if not isinstance(activation["packages"], list) or not isinstance(activation["resources"], list):
            raise KernelError("activation binding package or resource records are invalid")
    if state["status"] not in STATUSES or state["ceiling"] not in STATUSES:
        raise KernelError("kernel state status or ceiling is invalid")
    ids = [item["item_id"] for item in state["frontier"]["items"]]
    if len(ids) != len(set(ids)) or "ROOT" not in ids:
        raise KernelError("frontier item ids are duplicated or ROOT is absent")
    if set(state["frontier"]["active"]) - set(ids):
        raise KernelError("active frontier names unknown items")
    by_id = _items(state)
    for item in state["frontier"]["items"]:
        missing = sorted(set(item["dependencies"]) - set(by_id))
        if missing:
            raise KernelError(f"frontier item {item['item_id']!r} has unknown dependencies: {missing}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(item_id: str) -> None:
        if item_id in visiting:
            raise KernelError(f"frontier dependency cycle passes through {item_id!r}")
        if item_id in visited:
            return
        visiting.add(item_id)
        for dependency in by_id[item_id]["dependencies"]:
            walk(dependency)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in by_id:
        walk(item_id)
    pending = state["pending_episode"]
    if pending is not None:
        if not isinstance(pending, dict):
            raise KernelError("pending work must be an object or null")
        if pending.get("kind") == "ROUND":
            required_round = {
                "kind", "round_id", "payload_sha256", "base_revision",
                "base_state_sha256", "merge_policy", "episodes",
            }
            _closed(pending, required_round, "pending round")
            episode_ids = [item.get("episode_id") for item in pending["episodes"]]
            if len(episode_ids) < 2 or len(episode_ids) != len(set(episode_ids)):
                raise KernelError("pending round episode ids are missing or duplicated")
        else:
            required_episode = {
                "episode_id", "payload_sha256", "route_fingerprint",
                "core_fingerprint", "node_id",
            }
            _closed(pending, required_episode, "pending episode")
    for event in state["events"]:
        validate_event(event)
    if replay and state["events"]:
        rebuilt = _blank(state["genesis"])
        for event in state["events"]:
            rebuilt = apply_event(rebuilt, event, _replaying=True)
        if rebuilt != state:
            raise KernelError("kernel state is not the deterministic replay of its events")
    return state


def replay_report(state_value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        state = validate_state(state_value, replay=True)
    except KernelError as exc:
        return {"ok": False, "problem": str(exc)}
    return {
        "ok": True,
        "kernel_id": state["kernel_id"],
        "revision": state["revision"],
        "events": len(state["events"]),
        "state_sha256": state["state_sha256"],
    }


def import_frame_admission(
    kernel_state: Mapping[str, Any],
    frame_state: Mapping[str, Any],
    claim_id: str,
    item_id: str,
    event_id: str,
) -> dict[str, Any]:
    # Import the established reducer implementation rather than duplicating its
    # evidence rules here. The kernel only projects an already admitted status.
    import reducer

    state = validate_state(kernel_state)
    claims = frame_state.get("claims") or {}
    claim = claims.get(claim_id)
    if not isinstance(claim, dict):
        raise KernelError(f"frame state has no claim {claim_id!r}")
    item = _items(state).get(item_id)
    if item is None:
        raise KernelError(f"kernel frontier has no item {item_id!r}")
    if claim.get("target_sha256") != item.get("target_sha256"):
        raise KernelError("frame claim target does not match the frontier item target")
    status = claim.get("status")
    if status in ACCEPTED and not claim.get("admitted_by"):
        raise KernelError("accepted frame claim has no admission reference")
    payload = {
        "item_id": item_id,
        "claim_id": claim_id,
        "status": status,
        "admission_id": claim.get("admitted_by") or f"rejection:{claim_id}",
        "evidence_refs": list(claim.get("evidence_refs") or []),
        "frame_revision": frame_state.get("revision"),
        "frame_state_sha256": reducer.state_hash(dict(frame_state)),
    }
    return apply_event(
        state,
        build_event(
            state,
            "ADMISSION_IMPORTED",
            payload,
            event_id,
            _admission_authority=True,
        ),
    )


def inspect_state(state_value: Mapping[str, Any]) -> dict[str, Any]:
    state = validate_state(state_value)
    items = state["frontier"]["items"]
    return {
        "kernel_id": state["kernel_id"],
        "target_sha256": state["target"]["canonical_sha256"],
        "mode": state["mode"],
        "domains": state["domains"],
        "revision": state["revision"],
        "status": state["status"],
        "outcome": state["outcome"],
        "frontier": {item["item_id"]: item["status"] for item in items},
        "active": state["frontier"]["active"],
        "obstructions": len(state["frontier"]["obstructions"]),
        "evidence": len(state["evidence"]),
        "pending_episode": state["pending_episode"],
        "state_sha256": state["state_sha256"],
    }


def state_index(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    report_id: str = "state-index",
    _validated: bool = False,
) -> dict[str, Any]:
    state = copy.deepcopy(dict(state_value)) if _validated else validate_state(state_value)
    items = state["frontier"]["items"]
    by_status: dict[str, list[str]] = {}
    by_kind: dict[str, list[str]] = {}
    reverse_dependencies: dict[str, list[str]] = {item["item_id"]: [] for item in items}
    for item in items:
        by_status.setdefault(item["status"], []).append(item["item_id"])
        by_kind.setdefault(item["kind"], []).append(item["item_id"])
        for dependency in item["dependencies"]:
            reverse_dependencies[dependency].append(item["item_id"])
    route_outcomes: dict[str, int] = {}
    core_attempts: dict[str, int] = {}
    for attempt in state["route_attempts"]:
        outcome = str(attempt.get("outcome", "UNKNOWN"))
        route_outcomes[outcome] = route_outcomes.get(outcome, 0) + 1
        core = str(attempt.get("core_fingerprint", ""))
        if core:
            core_attempts[core] = core_attempts.get(core, 0) + 1
    event_kinds: dict[str, int] = {}
    for event in state["events"]:
        event_kinds[event["kind"]] = event_kinds.get(event["kind"], 0) + 1
    open_leaves = sorted(
        item["item_id"]
        for item in items
        if item["status"] == "OPEN" and not reverse_dependencies[item["item_id"]]
    )
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": report_id,
        "kind": "STATE_INDEX",
        "target_sha256": state["target"]["canonical_sha256"],
        "source_refs": [state["state_sha256"]],
        "body": {
            "kernel_id": state["kernel_id"],
            "source_state_sha256": state["state_sha256"],
            "revision": state["revision"],
            "status": state["status"],
            "outcome": state["outcome"],
            "active": sorted(set(state["frontier"]["active"])),
            "open_leaves": open_leaves,
            "items_by_status": {key: sorted(value) for key, value in sorted(by_status.items())},
            "items_by_kind": {key: sorted(value) for key, value in sorted(by_kind.items())},
            "reverse_dependencies": {
                key: sorted(value) for key, value in sorted(reverse_dependencies.items())
            },
            "route_outcomes": dict(sorted(route_outcomes.items())),
            "core_attempts": dict(sorted(core_attempts.items())),
            "event_kinds": dict(sorted(event_kinds.items())),
            "obstruction_ids": sorted(
                item["obstruction_id"] for item in state["frontier"]["obstructions"]
            ),
            "evidence": {
                "total": len(state["evidence"]),
                "invalidated": sum(bool(item.get("invalidated_by")) for item in state["evidence"]),
            },
            "pending": state["pending_episode"] is not None,
            "authoritative": False,
        },
        "disposition": "ADVISORY",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise KernelError(str(exc)) from exc


def compact_checkpoint(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    report_id: str = "state-checkpoint",
    block_size: int = 64,
    tail_events: int = 16,
) -> dict[str, Any]:
    if not 1 <= block_size <= 1024 or not 0 <= tail_events <= 128:
        raise KernelError("state checkpoint block or tail bound is invalid")
    state = validate_state(state_value)
    event_hashes = [event["payload_sha256"] for event in state["events"]]
    blocks = [
        {
            "first_revision": start + 1,
            "last_revision": min(start + block_size, len(event_hashes)),
            "events": len(event_hashes[start:start + block_size]),
            "content_sha256": digest_value(event_hashes[start:start + block_size]),
        }
        for start in range(0, len(event_hashes), block_size)
    ]
    index = state_index(root, state, report_id=f"{report_id}:index", _validated=True)
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": report_id,
        "kind": "STATE_CHECKPOINT",
        "target_sha256": state["target"]["canonical_sha256"],
        "source_refs": [state["state_sha256"], index["payload_sha256"]],
        "body": {
            "kernel_id": state["kernel_id"],
            "source_state_sha256": state["state_sha256"],
            "revision": state["revision"],
            "event_count": len(event_hashes),
            "event_chain_sha256": digest_value(event_hashes),
            "event_blocks": blocks,
            "tail_event_refs": event_hashes[-tail_events:] if tail_events else [],
            "index": index["body"],
            "replay_required_for_authority": True,
            "may_replace_kernel_state": False,
        },
        "disposition": "ADVISORY",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise KernelError(str(exc)) from exc
