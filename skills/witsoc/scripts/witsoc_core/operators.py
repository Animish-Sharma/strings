"""Declarative domain operator registry and bounded advisory planner."""

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
from .canonical import load_json, seal_packet


MANIFEST_SCHEMA = "witsoc.operator-manifest.v1"
PLAN_SCHEMA = "witsoc.operator-plan.v1"
EVIDENCE_RANK = {"HINT": 0, "CONTROL": 1, "CANDIDATE": 2, "EVIDENCE": 3}
COMMAND_PATH = re.compile(r"\$WITSOC_ROOT/([A-Za-z0-9_./-]+)")
TEMPLATE_FIELD = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class OperatorError(ValueError):
    pass


def load_manifest(root: Path, domain: str) -> dict[str, Any]:
    path = root / "domains" / domain / "operators.json"
    schema_path = root / "schemas" / "operator-manifest-v1.schema.json"
    try:
        manifest = load_json(path)
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatorError(f"cannot read {domain} operator registry: {exc}") from exc
    errors: list[str] = []
    jsonschema_lite.validate(manifest, schema, f"{domain} operators", errors)
    if errors:
        raise OperatorError("; ".join(errors[:8]))
    if manifest["domain"] != domain:
        raise OperatorError("operator registry domain does not match its path")
    identifiers = [item["id"] for item in manifest["operators"]]
    if len(identifiers) != len(set(identifiers)):
        raise OperatorError("operator ids are duplicated")
    known = set(identifiers)
    capability_manifest = load_json(root / "domains" / domain / "capabilities.json")
    known_capabilities = {
        item["id"] for item in capability_manifest.get("capabilities", [])
    }
    type_index = contracts.type_index(root)
    for item in manifest["operators"]:
        missing_dependencies = set(item["requires_operators"]) - known
        if missing_dependencies or item["id"] in item["requires_operators"]:
            raise OperatorError(
                f"operator {item['id']!r} has invalid dependencies: {sorted(missing_dependencies)}"
            )
        missing_capabilities = set(item["requires_capabilities"]) - known_capabilities
        if missing_capabilities:
            raise OperatorError(
                f"operator {item['id']!r} requires unknown capabilities: "
                f"{sorted(missing_capabilities)}"
            )
        for packet in item["inputs"] + item["outputs"]:
            if packet not in type_index:
                raise OperatorError(f"operator {item['id']!r} uses unknown packet {packet!r}")
        if any(type_index[packet]["status_authority"] for packet in item["outputs"]):
            raise OperatorError(f"operator {item['id']!r} may not emit status-authoritative packets")
        for relative in item["doctrine"]:
            if not (root / relative).is_file():
                raise OperatorError(f"operator {item['id']!r} doctrine is missing: {relative}")
        for command in item["commands"]:
            paths = COMMAND_PATH.findall(command)
            if not paths or any(not (root / relative).is_file() for relative in paths):
                raise OperatorError(f"operator {item['id']!r} command path is invalid: {command}")
        execution = item["execution"]
        command_template = execution["command_template"]
        paths = COMMAND_PATH.findall(command_template)
        if command_template and (
            not paths or any(not (root / relative).is_file() for relative in paths)
        ):
            raise OperatorError(
                f"operator {item['id']!r} execution command path is invalid: {command_template}"
            )
        unknown_fields = set(TEMPLATE_FIELD.findall(command_template)) - set(
            execution["binding_fields"]
        )
        if unknown_fields:
            raise OperatorError(
                f"operator {item['id']!r} command uses undeclared bindings: {sorted(unknown_fields)}"
            )
        if execution["mode"] == "LOCAL_TOOL" and not command_template:
            raise OperatorError(f"local operator {item['id']!r} has no command template")
    return copy.deepcopy(manifest)


def _matches(item: Mapping[str, Any], text: str) -> list[str]:
    normalized = " ".join(text.casefold().split())
    return [
        f"trigger:{trigger}"
        for trigger in item["triggers"]
        if re.search(rf"(?<![\w-]){re.escape(trigger.casefold())}(?![\w-])", normalized)
    ]


def _parallel_groups(selected: list[dict[str, Any]]) -> list[list[str]]:
    groups: list[list[dict[str, Any]]] = []
    for item in selected:
        placed = False
        for group in groups:
            if all(
                item["failure_domain"] != other["failure_domain"]
                and set(item["resource_keys"]).isdisjoint(other["resource_keys"])
                and other["id"] not in item["requires_operators"]
                and item["id"] not in other["requires_operators"]
                for other in group
            ):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return [[item["id"] for item in group] for group in groups]


def plan(
    root: Path,
    domain: str,
    problem_type: str,
    problem_value: Mapping[str, Any],
    *,
    role: str,
    objective: str = "",
    structured_reasons: Mapping[str, Iterable[str]] | None = None,
    allowed_operators: Iterable[str] | None = None,
    max_operators: int = 5,
) -> dict[str, Any]:
    if role not in {"explorer", "generator", "researcher"}:
        raise OperatorError(f"unknown operator role {role!r}")
    try:
        limits = load_json(root / "references" / "runtime_budgets.json")["operators"]
        hard_max = int(limits["maximum_selected"])
        context_limit = int(limits["maximum_plan_context_tokens"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise OperatorError(f"cannot read operator runtime limits: {exc}") from exc
    if not 1 <= max_operators <= hard_max:
        raise OperatorError(f"max_operators must be between 1 and {hard_max}")
    problem = contracts.validate_packet(root, problem_type, problem_value)
    manifest = load_manifest(root, domain)
    catalog = {item["id"]: item for item in manifest["operators"]}
    allowed = set(allowed_operators or catalog)
    unknown_allowed = allowed - set(catalog)
    if unknown_allowed:
        raise OperatorError(f"unknown admissible operators: {sorted(unknown_allowed)}")
    reasons = {key: sorted(set(value)) for key, value in (structured_reasons or {}).items()}
    unknown_reasons = set(reasons) - set(catalog)
    if unknown_reasons:
        raise OperatorError(f"activation reasons name unknown operators: {sorted(unknown_reasons)}")
    searchable = " ".join(
        str(value) for key, value in problem.items()
        if key not in {"payload_sha256", "target_sha256"}
    ) + " " + objective
    activation: dict[str, list[str]] = {}
    for identifier, item in catalog.items():
        if (
            role not in item["roles"]
            or identifier not in allowed
            or problem_type not in item["inputs"]
        ):
            continue
        why = list(reasons.get(identifier, [])) + _matches(item, searchable)
        if item["default"]:
            why.append("domain-default")
        if why:
            activation[identifier] = sorted(set(why))
    roots = sorted(
        activation,
        key=lambda identifier: (-catalog[identifier]["priority"], catalog[identifier]["cost_units"], identifier),
    )
    selected_ids: set[str] = set()
    ordered: list[str] = []

    def dependency_closure(identifier: str, stack: tuple[str, ...] = ()) -> list[str]:
        if identifier in stack:
            raise OperatorError(
                "operator dependency cycle: " + " -> ".join((*stack, identifier))
            )
        result: list[str] = []
        for dependency in catalog[identifier]["requires_operators"]:
            for item in dependency_closure(dependency, (*stack, identifier)):
                if item not in result:
                    result.append(item)
        if identifier not in result:
            result.append(identifier)
        return result

    def context_tokens(identifiers: Iterable[str]) -> int:
        paths = {
            relative
            for identifier in identifiers
            for relative in catalog[identifier]["doctrine"]
        }
        return sum((root / path).stat().st_size for path in paths) // 4

    def add(identifier: str, reason: str) -> bool:
        closure = dependency_closure(identifier)
        if any(
            item not in allowed or role not in catalog[item]["roles"] for item in closure
        ):
            return False
        proposed = ordered + [item for item in closure if item not in selected_ids]
        if len(proposed) > max_operators or context_tokens(proposed) > context_limit:
            return False
        for item in closure:
            if item in selected_ids:
                continue
            selected_ids.add(item)
            ordered.append(item)
            activation.setdefault(item, []).append(
                reason if item == identifier else f"dependency:{identifier}"
            )
        return True

    uncovered: list[str] = []
    for identifier in roots:
        if not add(identifier, "activated"):
            uncovered.append(identifier)
    if not ordered:
        fallback = min(
            (item for item in catalog.values() if role in item["roles"] and item["id"] in allowed),
            key=lambda item: (-item["priority"], item["cost_units"], item["id"]),
            default=None,
        )
        if fallback is None or not add(fallback["id"], "fallback"):
            raise OperatorError("no operator is available for this role and admissible set")
    selected: list[dict[str, Any]] = []
    doctrine_paths: set[str] = set()
    for identifier in ordered:
        item = catalog[identifier]
        doctrine_paths.update(item["doctrine"])
        selected.append({
            "id": identifier,
            "lane": item["lane"],
            "summary": item["summary"],
            "activation": sorted(set(activation.get(identifier, []))),
            "requires_operators": list(item["requires_operators"]),
            "inputs": list(item["inputs"]),
            "outputs": list(item["outputs"]),
            "preconditions": list(item["preconditions"]),
            "doctrine": list(item["doctrine"]),
            "commands": list(item["commands"]),
            "execution": copy.deepcopy(item["execution"]),
            "cost_units": item["cost_units"],
            "context_tokens": sum((root / path).stat().st_size for path in item["doctrine"]) // 4,
            "evidence_ceiling": item["evidence_ceiling"],
            "failure_domain": item["failure_domain"],
            "resource_keys": list(item["resource_keys"]),
            "stop_conditions": list(item["stop_conditions"]),
        })
    packet = seal_packet({
        "schema": PLAN_SCHEMA,
        "plan_id": f"operators:{domain}:{problem.get('problem_id', problem['payload_sha256'][:12])}",
        "domain": domain,
        "target_sha256": problem["target_sha256"],
        "problem_type": contracts.resolve_type(root, problem_type)["canonical_id"],
        "problem_sha256": problem["payload_sha256"],
        "role": role,
        "objective": objective,
        "selected": selected,
        "parallel_groups": _parallel_groups(selected),
        "total_cost_units": sum(item["cost_units"] for item in selected),
        "estimated_context_tokens": sum((root / path).stat().st_size for path in doctrine_paths) // 4,
        "evidence_ceiling": max(
            (item["evidence_ceiling"] for item in selected),
            key=lambda value: EVIDENCE_RANK[value],
        ),
        "uncovered": sorted(set(uncovered)),
        "advisory": True,
    })
    try:
        return contracts.validate_packet(root, "witsoc.operator-plan.v1", packet)
    except contracts.ContractError as exc:
        raise OperatorError(str(exc)) from exc


def build_contract(
    root: Path,
    plan_value: Mapping[str, Any],
    operator_id: str,
    bindings: Mapping[str, Any],
    *,
    invocation_id: str,
    blockers: Iterable[str] | None = None,
    external_ready: bool = False,
) -> dict[str, Any]:
    try:
        plan_value = contracts.validate_packet(root, PLAN_SCHEMA, plan_value)
    except contracts.ContractError as exc:
        raise OperatorError(str(exc)) from exc
    plan_packet = copy.deepcopy(dict(plan_value))
    selected = [item for item in plan_packet["selected"] if item["id"] == operator_id]
    if len(selected) != 1:
        raise OperatorError(f"operator {operator_id!r} is not selected exactly once")
    if not isinstance(bindings, Mapping):
        raise OperatorError("operator bindings must be an object")
    operator = selected[0]
    execution = operator["execution"]
    required = set(execution["binding_fields"])
    missing, extra = required - set(bindings), set(bindings) - required
    if missing or extra:
        raise OperatorError(
            f"operator binding shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if any(value in (None, "", [], {}) for value in bindings.values()):
        raise OperatorError("operator bindings cannot contain empty top-level values")
    blocker_list = sorted(set(blockers or []))
    if any(not isinstance(item, str) or not item.strip() for item in blocker_list):
        raise OperatorError("operator blockers must be non-empty strings")
    if blocker_list:
        disposition = "BLOCKED"
    elif execution["mode"] == "EXTERNAL_PROTOCOL" and not external_ready:
        disposition = "WAITING_EXTERNAL"
    else:
        disposition = "READY"
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": invocation_id,
        "kind": "OPERATOR_CONTRACT",
        "target_sha256": plan_packet["target_sha256"],
        "source_refs": sorted({
            plan_packet["payload_sha256"], plan_packet["problem_sha256"],
        }),
        "body": {
            "plan_id": plan_packet["plan_id"],
            "operator_id": operator_id,
            "domain": plan_packet["domain"],
            "role": plan_packet["role"],
            "lane": operator["lane"],
            "problem_type": plan_packet["problem_type"],
            "execution_mode": execution["mode"],
            "backend_classes": list(execution["backend_classes"]),
            "command_template": execution["command_template"],
            "bindings": copy.deepcopy(dict(bindings)),
            "preconditions": list(operator["preconditions"]),
            "acceptance_checks": list(execution["acceptance_checks"]),
            "falsifier": execution["falsifier"],
            "stop_conditions": list(operator["stop_conditions"]),
            "output_types": list(operator["outputs"]),
            "evidence_ceiling": operator["evidence_ceiling"],
            "failure_domain": operator["failure_domain"],
            "resource_keys": list(operator["resource_keys"]),
            "blockers": blocker_list,
            "may_wait_external": execution["may_wait_external"],
            "result_contract": "Return declared packet types or a typed obstruction; never status.",
        },
        "disposition": disposition,
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise OperatorError(str(exc)) from exc
