"""Validate capability manifests and build minimal, trigger-based load plans."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


class CapabilityError(ValueError):
    pass


COMMAND_PATH = re.compile(r"\$WITSOC_ROOT/([A-Za-z0-9_./-]+)")


def manifest_paths(root: Path, domains: Iterable[str]) -> list[Path]:
    paths = [root / "capabilities" / "frame.json"]
    paths.extend(root / "domains" / name / "capabilities.json" for name in sorted(set(domains)))
    return paths


def _validate_manifest(root: Path, path: Path, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != "witsoc.capability-manifest.v1":
        raise CapabilityError(f"{path}: unsupported capability manifest")
    if set(value) != {"schema", "owner", "version", "capabilities"}:
        raise CapabilityError(f"{path}: manifest keys are not closed")
    if not isinstance(value["capabilities"], list):
        raise CapabilityError(f"{path}: capabilities must be an array")
    seen: set[str] = set()
    required = {
        "id", "summary", "modes", "roles", "default", "triggers", "inputs",
        "outputs", "requires", "load", "commands", "cost_class", "priority",
    }
    for index, item in enumerate(value["capabilities"]):
        label = f"{path}: capabilities[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            raise CapabilityError(f"{label}: capability keys are not closed")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise CapabilityError(f"{label}: id is empty or duplicated")
        seen.add(identifier)
        if item["cost_class"] not in {"tiny", "small", "medium", "large"}:
            raise CapabilityError(f"{label}: invalid cost_class")
        for relative in item["load"]:
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError as exc:
                raise CapabilityError(f"{label}: load path escapes skill root") from exc
            if not candidate.is_file():
                raise CapabilityError(f"{label}: load path does not exist: {relative}")
        for command in item["commands"]:
            paths = COMMAND_PATH.findall(command)
            if not paths:
                raise CapabilityError(
                    f"{label}: command is not rooted at $WITSOC_ROOT: {command!r}"
                )
            for relative in paths:
                if not (root / relative).is_file():
                    raise CapabilityError(f"{label}: command path does not exist: {relative}")
    return value


def load_manifest(root: Path, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f"cannot read {path}: {exc}") from exc
    return _validate_manifest(root, path, value)


def _triggered(capability: dict[str, Any], text: str) -> bool:
    if capability["default"]:
        return True
    normalized = " ".join(text.casefold().split())
    return any(
        re.search(rf"(?<![\w-]){re.escape(trigger.casefold())}(?![\w-])", normalized)
        for trigger in capability["triggers"]
    )


def build_load_plan(
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
    from . import capability_graph, modes

    role_contract = {"role": role, **modes.skill_resource(modes.ROLE_PATHS[role])}

    try:
        path_plan = capability_graph.minimal_path(
            root,
            mode,
            domains,
            role,
            statement,
            goal_type=goal_type,
            available_types=available_types,
            required_capabilities=required_capabilities,
        )
    except capability_graph.CapabilityGraphError as exc:
        return {
            "schema": "witsoc.load-plan.v2",
            "mode": mode,
            "domains": sorted(set(domains)),
            "role": role,
            "capabilities": [],
            "required_path": [],
            "requested_extensions": [],
            "triggered_extensions": [],
            "deferred_extensions": [],
            "load_now": [],
            "load_resources": [],
            "role_contract": role_contract,
            "commands": [],
            "contracts": [],
            "estimated_tokens": 0,
            "problems": [str(exc)],
            "ok": False,
        }
    try:
        context_limit = int(
            json.loads((root / "references" / "runtime_budgets.json").read_text(encoding="utf-8"))
            ["capabilities"]["maximum_load_plan_tokens"]
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CapabilityError(f"cannot read capability runtime limits: {exc}") from exc

    selected = path_plan["required_path"] + path_plan["requested_extensions"]
    selected_ids = {item["id"] for item in selected}

    def selection_tokens(items: Iterable[dict[str, Any]]) -> int:
        unique_paths = {
            relative for item in items for relative in item["load"]
        }
        return sum(
            (root / relative).stat().st_size
            for relative in unique_paths if (root / relative).is_file()
        ) // 4

    accepted_triggered: list[dict[str, Any]] = []
    deferred_extensions: list[dict[str, Any]] = []
    groups = path_plan.get("triggered_extension_groups") or [
        {"trigger": "legacy-trigger-group", "items": path_plan["triggered_extensions"]}
    ]
    for group in groups:
        additions = [item for item in group["items"] if item["id"] not in selected_ids]
        if not additions:
            continue
        proposed = selected + accepted_triggered + additions
        needed = selection_tokens(proposed)
        if needed > context_limit:
            deferred_extensions.append({
                "trigger": group["trigger"],
                "reason": f"context limit {needed} > {context_limit}",
            })
            continue
        for item in additions:
            if item["id"] not in selected_ids:
                selected_ids.add(item["id"])
                accepted_triggered.append(item)
    selected += accepted_triggered
    paths: list[str] = []
    commands: list[str] = []
    for item in selected:
        for relative in item["load"]:
            if relative not in paths:
                paths.append(relative)
        for command in item["commands"]:
            if command not in commands:
                commands.append(command)
    byte_count = sum((root / relative).stat().st_size for relative in paths if (root / relative).is_file())
    estimated_tokens = byte_count // 4
    plan_problems = list(path_plan["problems"])
    if estimated_tokens > context_limit:
        plan_problems.append(
            f"load plan needs {estimated_tokens} context tokens; limit is {context_limit}"
        )
    contracts_used = sorted({
        packet for item in selected for packet in item["required_inputs"] + item["outputs"]
    })
    return {
        "schema": "witsoc.load-plan.v2",
        "mode": mode,
        "domains": sorted(set(domains)),
        "role": role,
        "capabilities": [
            {
                key: item[key]
                for key in (
                    "id", "summary", "cost_class", "cost_units", "context_tokens",
                    "required_inputs", "optional_inputs", "outputs", "evidence_ceiling",
                    "failure_domains", "resource_keys", "admission_authority",
                )
            }
            for item in selected
        ],
        "required_path": [item["id"] for item in path_plan["required_path"]],
        "requested_extensions": [item["id"] for item in path_plan["requested_extensions"]],
        "triggered_extensions": [item["id"] for item in accepted_triggered],
        "deferred_extensions": deferred_extensions,
        "available_packets": path_plan["available_packets"],
        "goal_packets": path_plan["goal_packets"],
        "selected_goal": path_plan.get("selected_goal"),
        "load_now": paths,
        "load_resources": [modes.skill_resource(relative) for relative in paths],
        "role_contract": role_contract,
        "commands": commands,
        "contracts": contracts_used,
        "estimated_tokens": estimated_tokens,
        "graph": {
            "nodes": len(path_plan["graph"]["nodes"]),
            "edges": path_plan["graph"]["edge_count"],
            "admission_authority": path_plan["graph"]["admission_authority"],
        },
        "problems": plan_problems,
        "ok": path_plan["ok"] and not plan_problems,
    }


def all_capabilities(root: Path) -> list[dict[str, Any]]:
    domains = [path.parent.name for path in (root / "domains").glob("*/capabilities.json")]
    result: list[dict[str, Any]] = []
    for path in manifest_paths(root, domains):
        manifest = load_manifest(root, path)
        result.extend({"owner": manifest["owner"], **item} for item in manifest["capabilities"])
    return sorted(result, key=lambda item: (item["owner"], item["id"]))
