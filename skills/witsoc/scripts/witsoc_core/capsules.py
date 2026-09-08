"""Build sealed, budget-bounded context capsules from canonical kernel state."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from . import capabilities, contracts, kernel
from .canonical import canonical_json, load_json, seal_packet


SCHEMA = "witsoc.capsule.v1"


class CapsuleError(ValueError):
    pass


def _frontier_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(item[key])
        for key in (
            "item_id", "kind", "statement", "status", "dependencies",
            "evidence_refs", "route_fingerprint", "admission_ref",
        )
        if key in item
    }


def _obstruction_view(item: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "obstruction_id", "statement", "route_fingerprint", "core_fingerprint",
        "evidence_refs", "revival_condition",
    )
    return {key: copy.deepcopy(item[key]) for key in keys if key in item}


def _source_refs(root: Path, source_map: Mapping[str, Any] | None, target_sha256: str) -> list[str]:
    if source_map is None:
        return []
    packet = contracts.validate_packet(root, "witsoc.source-map.v2", source_map)
    if packet["target_sha256"] != target_sha256:
        raise CapsuleError("source map differs from the capsule target")
    return sorted(
        {
            f"{entry['source_id']}@sha256:{entry['retrieved_sha256']}"
            for entry in packet["entries"]
        }
    )


def _estimate(packet: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(packet)
    for _ in range(4):
        result["estimated_tokens"] = (len(canonical_json(seal_packet(result))) + 3) // 4
    return seal_packet(result)


def build(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    role: str,
    statement: str = "",
    capability_mode: str | None = None,
    context_budget: int = 2048,
    capsule_id: str | None = None,
    source_map: Mapping[str, Any] | None = None,
    required_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    try:
        maximum_budget = int(
            load_json(root / "references" / "runtime_budgets.json")["capsules"]["maximum_tokens"]
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise CapsuleError(f"cannot read capsule runtime limits: {exc}") from exc
    if not 256 <= context_budget <= maximum_budget:
        raise CapsuleError(
            f"capsule context budget must be between 256 and {maximum_budget} tokens"
        )
    state = kernel.validate_state(state_value)
    plan = capabilities.build_load_plan(
        root,
        capability_mode or state["mode"],
        state["domains"],
        role,
        statement or state["target"]["statement"],
        required_capabilities=required_capabilities,
    )
    if not plan["ok"]:
        raise CapsuleError("cannot build capsule without a valid capability path: " + "; ".join(plan["problems"]))
    active = set(state["frontier"]["active"])
    frontier = sorted(
        (_frontier_view(item) for item in state["frontier"]["items"]),
        key=lambda item: (item["item_id"] not in active, item["item_id"]),
    )
    obstructions = sorted(
        (_obstruction_view(item) for item in state["frontier"]["obstructions"]),
        key=lambda item: item["obstruction_id"],
    )
    packet = {
        "schema": SCHEMA,
        "capsule_id": capsule_id or f"capsule:{state['state_sha256'][:16]}:{role}",
        "target_sha256": state["target"]["canonical_sha256"],
        "base_state_sha256": state["state_sha256"],
        "mode": state["mode"],
        "role": role,
        "domains": list(state["domains"]),
        "target": copy.deepcopy(state["target"]),
        "frontier_slice": frontier,
        "source_refs": _source_refs(root, source_map, state["target"]["canonical_sha256"]),
        "obstructions": obstructions,
        "capabilities": [item["id"] for item in plan["capabilities"]],
        "contracts": list(plan["contracts"]),
        "context_budget": context_budget,
        "estimated_tokens": 0,
        "omissions": [],
    }

    # Preserve the frozen target and active frontier longest; trim peripheral context first.
    removable_frontier = [
        item["item_id"] for item in reversed(packet["frontier_slice"])
        if item["item_id"] not in active
    ]
    removable_sources = list(reversed(packet["source_refs"][1:]))
    removable_obstructions = [
        item["obstruction_id"] for item in reversed(packet["obstructions"][1:])
    ]
    removal_order = (
        [("frontier", item) for item in removable_frontier]
        + [("source", item) for item in removable_sources]
        + [("obstruction", item) for item in removable_obstructions]
    )
    result = _estimate(packet)
    for kind, identifier in removal_order:
        if result["estimated_tokens"] <= context_budget:
            break
        if kind == "frontier":
            packet["frontier_slice"] = [
                item for item in packet["frontier_slice"] if item["item_id"] != identifier
            ]
        elif kind == "source":
            packet["source_refs"].remove(identifier)
        else:
            packet["obstructions"] = [
                item for item in packet["obstructions"] if item["obstruction_id"] != identifier
            ]
        packet["omissions"].append(f"{kind}:{identifier}")
        result = _estimate(packet)
    if result["estimated_tokens"] > context_budget:
        raise CapsuleError(
            f"essential capsule requires {result['estimated_tokens']} tokens, exceeding budget {context_budget}"
        )
    try:
        return contracts.validate_packet(root, "witsoc.capsule.v1", result)
    except contracts.ContractError as exc:
        raise CapsuleError(str(exc)) from exc


def inspect(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": value.get("schema"),
        "capsule_id": value.get("capsule_id"),
        "mode": value.get("mode"),
        "role": value.get("role"),
        "frontier_items": len(value.get("frontier_slice", [])),
        "source_refs": len(value.get("source_refs", [])),
        "obstructions": len(value.get("obstructions", [])),
        "estimated_tokens": value.get("estimated_tokens"),
        "context_budget": value.get("context_budget"),
        "omissions": list(value.get("omissions", [])),
    }
