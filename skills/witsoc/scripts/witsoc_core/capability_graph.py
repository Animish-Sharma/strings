"""Compile manifest metadata into a typed, costed capability graph."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    import jsonschema_lite
except ModuleNotFoundError:
    from scripts import jsonschema_lite

from . import contracts
from .canonical import load_json


GRAPH_SCHEMA = "witsoc.capability-graph.v1"
POLICY_SCHEMA = "witsoc.capability-policy.v1"
COST_UNITS = {"tiny": 1, "small": 2, "medium": 4, "large": 8}
EVIDENCE_RANK = {"HINT": 0, "CONTROL": 1, "CANDIDATE": 2, "EVIDENCE": 3, "ADMISSION": 4}


class CapabilityGraphError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise CapabilityGraphError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _canonical(index: Mapping[str, Mapping[str, Any]], values: Iterable[str]) -> list[str]:
    result: set[str] = set()
    for value in values:
        if value not in index:
            raise CapabilityGraphError(f"unknown packet type {value!r}")
        result.add(str(index[value]["canonical_id"]))
    return sorted(result)


def _load_policy(
    root: Path,
    catalog: list[dict[str, Any]],
    index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        policy = load_json(root / "contracts" / "capability-policy.json")
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityGraphError(f"cannot read capability policy: {exc}") from exc
    _closed(
        policy,
        {"schema", "version", "routes", "optional_inputs", "evidence_ceiling_overrides", "failure_domains"},
        "capability policy",
    )
    if policy["schema"] != POLICY_SCHEMA or policy["version"] != 1:
        raise CapabilityGraphError("unsupported capability policy")
    qualified = {f"{item['owner']}:{item['id']}": item for item in catalog}
    owners = {item["owner"] for item in catalog}

    def installed_capability(identifier: str) -> bool:
        owner = identifier.split(":", 1)[0]
        return identifier in qualified or owner not in owners

    for capability_id, optional in policy["optional_inputs"].items():
        if capability_id not in qualified:
            if installed_capability(capability_id):
                continue
            raise CapabilityGraphError(f"policy references unknown capability {capability_id!r}")
        unknown = set(optional) - set(qualified[capability_id]["inputs"])
        if unknown:
            raise CapabilityGraphError(
                f"{capability_id} declares non-input optional packets: {sorted(unknown)}"
            )
        _canonical(index, optional)
    for capability_id, ceiling in policy["evidence_ceiling_overrides"].items():
        if capability_id not in qualified and installed_capability(capability_id):
            continue
        if capability_id not in qualified or ceiling not in EVIDENCE_RANK:
            raise CapabilityGraphError(f"invalid evidence ceiling override for {capability_id!r}")
    if not owners <= set(policy["failure_domains"]):
        raise CapabilityGraphError("failure domain policy must cover every capability owner")
    route_keys: set[tuple[str, str]] = set()
    for route_index, route in enumerate(policy["routes"]):
        _closed(route, {"mode", "role", "available", "goals"}, f"policy route[{route_index}]")
        key = (route["mode"], route["role"])
        if key in route_keys:
            raise CapabilityGraphError(f"duplicate capability route policy for {key}")
        route_keys.add(key)
        if not route["available"] or not route["goals"]:
            raise CapabilityGraphError(f"capability route policy {key} is empty")
        _canonical(index, route["available"] + route["goals"])
    projected = copy.deepcopy(policy)
    projected["optional_inputs"] = {
        key: value for key, value in policy["optional_inputs"].items() if key in qualified
    }
    projected["evidence_ceiling_overrides"] = {
        key: value
        for key, value in policy["evidence_ceiling_overrides"].items()
        if key in qualified
    }
    projected["failure_domains"] = {
        key: value for key, value in policy["failure_domains"].items() if key in owners
    }
    return projected


def _evidence_ceiling(index: Mapping[str, Mapping[str, Any]], outputs: list[str]) -> str:
    classes = [str(index[packet]["evidence_class"]) for packet in outputs]
    return max(classes, key=lambda item: EVIDENCE_RANK[item], default="CONTROL")


def _context_tokens(root: Path, paths: list[str]) -> int:
    return sum((root / relative).stat().st_size for relative in paths) // 4


def compile_graph(root: Path, domains: Iterable[str] | None = None) -> dict[str, Any]:
    from .capabilities import all_capabilities

    root = root.expanduser().resolve()
    catalog = all_capabilities(root)
    type_index = contracts.type_index(root)
    policy = _load_policy(root, catalog, type_index)
    selected_owners = None if domains is None else {"frame", *set(domains)}
    nodes: list[dict[str, Any]] = []
    for capability in catalog:
        if selected_owners is not None and capability["owner"] not in selected_owners:
            continue
        qualified = f"{capability['owner']}:{capability['id']}"
        inputs = _canonical(type_index, capability["inputs"])
        optional = _canonical(type_index, policy["optional_inputs"].get(qualified, []))
        outputs = _canonical(type_index, capability["outputs"])
        admission_authority = any(
            type_index[packet]["status_authority"] for packet in outputs
        )
        node = {
            "id": qualified,
            "owner": capability["owner"],
            "capability_id": capability["id"],
            "summary": capability["summary"],
            "modes": sorted(set(capability["modes"])),
            "roles": sorted(set(capability["roles"])),
            "default": capability["default"],
            "triggers": sorted(set(capability["triggers"])),
            "inputs": inputs,
            "required_inputs": sorted(set(inputs) - set(optional)),
            "optional_inputs": optional,
            "outputs": outputs,
            "load": list(capability["load"]),
            "commands": list(capability["commands"]),
            "cost_class": capability["cost_class"],
            "cost_units": COST_UNITS[capability["cost_class"]],
            "context_tokens": _context_tokens(root, capability["load"]),
            "priority": int(capability["priority"]),
            "evidence_ceiling": policy["evidence_ceiling_overrides"].get(
                qualified, _evidence_ceiling(type_index, outputs)
            ),
            "failure_domains": sorted({policy["failure_domains"][capability["owner"]], qualified}),
            "resource_keys": sorted(
                {f"read:{item}" for item in inputs} | {f"write:{item}" for item in outputs}
            ),
            "admission_authority": admission_authority,
        }
        nodes.append(node)
    authorities = [item["id"] for item in nodes if item["admission_authority"]]
    if authorities != ["frame:evidence-admission"]:
        raise CapabilityGraphError(
            "compiled graph must expose frame:evidence-admission as its sole admission authority"
        )
    packet_types = sorted({item for node in nodes for item in node["inputs"] + node["outputs"]})
    producers = {packet: [] for packet in packet_types}
    consumers = {packet: [] for packet in packet_types}
    for node in nodes:
        for packet in node["outputs"]:
            producers[packet].append(node["id"])
        for packet in node["required_inputs"]:
            consumers[packet].append(node["id"])
    edge_count = sum(len(producers[packet]) * len(consumers[packet]) for packet in packet_types)
    graph = {
        "schema": GRAPH_SCHEMA,
        "version": 1,
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "packet_types": packet_types,
        "admission_authority": authorities[0],
        "edge_count": edge_count,
        "ok": True,
    }
    schema = load_json(root / "schemas" / "capability-graph-v1.schema.json")
    errors: list[str] = []
    jsonschema_lite.validate(graph, schema, "capability graph", errors)
    if errors:
        raise CapabilityGraphError("; ".join(errors[:8]))
    return graph


def _triggered(node: Mapping[str, Any], statement: str) -> bool:
    normalized = " ".join(statement.casefold().split())
    return any(
        re.search(rf"(?<![\w-]){re.escape(trigger.casefold())}(?![\w-])", normalized)
        for trigger in node["triggers"]
    )


def _route(policy: Mapping[str, Any], mode: str, role: str) -> dict[str, Any]:
    matches = [item for item in policy["routes"] if item["mode"] == mode and item["role"] == role]
    if len(matches) != 1:
        raise CapabilityGraphError(f"no unique capability route policy for {mode}/{role}")
    return matches[0]


def minimal_path(
    root: Path,
    mode: str,
    domains: Iterable[str],
    role: str,
    statement: str = "",
    *,
    goal_type: str | None = None,
    available_types: Iterable[str] | None = None,
    required_capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    graph = compile_graph(root, domains)
    from .capabilities import all_capabilities

    type_index = contracts.type_index(root)
    policy = _load_policy(root, all_capabilities(root), type_index)
    route = _route(policy, mode, role)
    available = set(_canonical(type_index, available_types or route["available"]))
    goals = _canonical(type_index, [goal_type] if goal_type else route["goals"])
    candidates = [
        node for node in graph["nodes"]
        if (mode in node["modes"] or "*" in node["modes"])
        and (role in node["roles"] or "*" in node["roles"])
    ]
    by_output: dict[str, list[dict[str, Any]]] = {}
    for node in candidates:
        for packet in node["outputs"]:
            by_output.setdefault(packet, []).append(node)

    selected_domains = set(domains)
    requested_owner_hints = {
        identifier.split(":", 1)[0]
        for identifier in (required_capabilities or [])
        if ":" in identifier and identifier.split(":", 1)[0] in selected_domains
    }
    goal_owner = (
        next(iter(requested_owner_hints))
        if len(requested_owner_hints) == 1
        else next(iter(selected_domains)) if len(selected_domains) == 1
        else None
    )

    def node_cost(node: Mapping[str, Any]) -> int:
        owner_penalty = 0 if node["owner"] in selected_domains else 700 if node["owner"] == "frame" else 1400
        activation_penalty = 0 if node["default"] or _triggered(node, statement) else 1800
        return max(1, node["context_tokens"] + 64 * node["cost_units"] - 4 * node["priority"] + owner_penalty + activation_penalty)

    def merge_paths(parts: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for part in parts:
            for node in part:
                if node["id"] not in seen:
                    seen.add(node["id"])
                    result.append(node)
        return result

    def solve(
        packet: str,
        stack: frozenset[str],
        preferred_owner: str | None = None,
    ) -> tuple[list[dict[str, Any]], int] | None:
        if packet in available:
            return [], 0
        if packet in stack:
            return None
        choices: list[tuple[list[dict[str, Any]], int]] = []
        providers = by_output.get(packet, [])
        if preferred_owner:
            same_owner = [node for node in providers if node["owner"] == preferred_owner]
            frame_owned = [node for node in providers if node["owner"] == "frame"]
            if same_owner:
                providers = same_owner
            elif frame_owned:
                providers = frame_owned
        else:
            domain_providers = [node for node in providers if node["owner"] in selected_domains]
            if domain_providers:
                providers = domain_providers
        for node in providers:
            pieces: list[list[dict[str, Any]]] = []
            total = node_cost(node)
            feasible = True
            dependency_owner = (
                node["owner"] if node["owner"] != "frame" else preferred_owner
            )
            for required in node["required_inputs"]:
                solved = solve(required, stack | {packet}, dependency_owner)
                if solved is None:
                    feasible = False
                    break
                pieces.append(solved[0])
                total += solved[1]
            if feasible:
                path = merge_paths(pieces + [[node]])
                choices.append((path, total))
        if not choices:
            return None
        return min(choices, key=lambda item: (item[1], len(item[0]), [node["id"] for node in item[0]]))

    solved_goals = [(goal, solve(goal, frozenset(), goal_owner)) for goal in goals]
    feasible_goals = [(goal, value) for goal, value in solved_goals if value is not None]
    if not feasible_goals:
        return {
            "graph": graph,
            "available_packets": sorted(available),
            "goal_packets": goals,
            "required_path": [],
            "requested_extensions": [],
            "triggered_extensions": [],
            "triggered_extension_groups": [],
            "problems": [f"no typed capability path reaches any goal for {mode}/{role}"],
            "ok": False,
        }
    chosen_goal, solved = min(
        feasible_goals,
        key=lambda item: (item[1][1], len(item[1][0]), item[0]),
    )
    assert solved is not None
    required_path = solved[0]
    selected_ids = {node["id"] for node in required_path}
    candidate_index = {node["id"]: node for node in candidates}
    by_short_id: dict[str, list[dict[str, Any]]] = {}
    for node in candidates:
        by_short_id.setdefault(node["capability_id"], []).append(node)

    def requested_node(identifier: str) -> dict[str, Any]:
        if identifier in candidate_index:
            return candidate_index[identifier]
        matches = by_short_id.get(identifier, [])
        if len(matches) != 1:
            raise CapabilityGraphError(
                f"explicit capability {identifier!r} is unavailable or ambiguous for {mode}/{role}"
            )
        return matches[0]

    requested_extensions: list[dict[str, Any]] = []
    for identifier in sorted(set(required_capabilities or [])):
        node = requested_node(identifier)
        dependencies: list[list[dict[str, Any]]] = []
        for required in node["required_inputs"]:
            solved_required = solve(required, frozenset(), node["owner"])
            if solved_required is None:
                raise CapabilityGraphError(
                    f"explicit capability {node['id']!r} has no typed input path"
                )
            dependencies.append(solved_required[0])
        for item in merge_paths(dependencies + [[node]]):
            if item["id"] not in selected_ids:
                selected_ids.add(item["id"])
                requested_extensions.append(item)
    mandatory_ids = set(selected_ids)
    extensions: list[dict[str, Any]] = []
    extension_ids: set[str] = set()
    extension_groups: list[dict[str, Any]] = []
    for node in candidates:
        if node["id"] in mandatory_ids or node["default"] or not _triggered(node, statement):
            continue
        dependencies: list[list[dict[str, Any]]] = []
        feasible = True
        for required in node["required_inputs"]:
            solved_required = solve(required, frozenset(), node["owner"])
            if solved_required is None:
                feasible = False
                break
            dependencies.append(solved_required[0])
        if feasible:
            additions = [
                item for item in merge_paths(dependencies + [[node]])
                if item["id"] not in mandatory_ids
            ]
            if additions:
                extension_groups.append({"trigger": node["id"], "items": additions})
            for item in additions:
                if item["id"] not in extension_ids:
                    extension_ids.add(item["id"])
                    extensions.append(item)
    return {
        "graph": graph,
        "available_packets": sorted(available),
        "goal_packets": goals,
        "selected_goal": chosen_goal,
        "required_path": required_path,
        "requested_extensions": requested_extensions,
        "triggered_extensions": extensions,
        "triggered_extension_groups": extension_groups,
        "problems": [],
        "ok": True,
    }
