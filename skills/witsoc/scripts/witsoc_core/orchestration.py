"""Mechanical boundary between Witsoc state and a host orchestrator."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from . import (
    assurance,
    capabilities,
    capsules,
    contracts,
    discovery,
    domain_packages,
    exploration,
    kernel,
    loop_messages,
    operators,
    reasoning,
    rounds,
)
from .canonical import canonical_json, seal_packet, verify_packet_seal


LEGACY_HANDOFF_SCHEMA = "witsoc.orchestrator-handoff.v1"
DOMAIN_HANDOFF_SCHEMA = "witsoc.orchestrator-handoff.v2"
REASONING_HANDOFF_SCHEMA = "witsoc.orchestrator-handoff.v3"
HANDOFF_SCHEMA = "witsoc.orchestrator-handoff.v4"
REASONING_HANDOFF_SCHEMAS = {REASONING_HANDOFF_SCHEMA, HANDOFF_SCHEMA}
DOMAIN_BINDING_SCHEMA = "witsoc.domain-binding.v1"
LEGACY_DRAFT_SCHEMA = "witsoc.research-delta-draft.v1"
DRAFT_SCHEMA = "witsoc.research-delta-draft.v2"
DECISION_ACTIONS = {"DIRECT_ANSWER", "DEMOTE", "WAIT_EXTERNAL", "HONEST_STOP"}
TERMINAL_ACTIONS = {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}
ROOT = Path(__file__).resolve().parents[2]


class OrchestrationError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise OrchestrationError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _within(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise OrchestrationError(f"{label} escapes the bound workspace: {resolved}") from exc
    return resolved


def _pending_binding(
    state: Mapping[str, Any], episode_id: str | None = None
) -> Mapping[str, Any]:
    pending = state.get("pending_episode")
    if pending is None:
        raise OrchestrationError("Explorer has not issued work; no role worker may launch")
    if pending.get("kind") == "ROUND":
        if not episode_id:
            raise OrchestrationError("an independent round requires one exact child episode id")
        for binding in pending["episodes"]:
            if binding["episode_id"] == episode_id:
                return binding
        raise OrchestrationError(f"round has no issued episode {episode_id!r}")
    if episode_id is not None and pending["episode_id"] != episode_id:
        raise OrchestrationError("episode does not match pending Witsoc work")
    return pending


def validate_episode_binding(
    state_value: Mapping[str, Any], episode_value: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = kernel.validate_state(state_value)
    episode = discovery.validate_episode(episode_value)
    pending = _pending_binding(state, episode["episode_id"])
    expected = {
        "episode_id": pending["episode_id"],
        "payload_sha256": pending["payload_sha256"],
        "target_sha256": state["target"]["canonical_sha256"],
        "route_fingerprint": pending["route_fingerprint"],
        "core_fingerprint": pending["core_fingerprint"],
        "node_id": pending["node_id"],
    }
    for field, value in expected.items():
        if episode.get(field) != value:
            raise OrchestrationError(f"episode {field} does not bind pending Witsoc work")
    return state, episode


def delta_draft(
    state_value: Mapping[str, Any],
    episode_value: Mapping[str, Any] | None = None,
    reasoning_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if episode_value is not None:
        state, episode = validate_episode_binding(state, episode_value)
        pending = _pending_binding(state, episode["episode_id"])
    else:
        pending = _pending_binding(state)
    measure = len(state["frontier"]["active"])
    result = {
        "schema": DRAFT_SCHEMA if reasoning_contract is not None else LEGACY_DRAFT_SCHEMA,
        "delta_id": f"delta:{pending['episode_id']}",
        "episode_id": pending["episode_id"],
        "outcome": "NO_PROGRESS",
        "evidence_refs": [],
        "frontier_measure_before": measure,
        "frontier_measure_after": measure,
        "new_frontier": [],
        "new_obstruction": None,
        "admission_ref": None,
        "independent_review": None,
        "remaining_obstruction": "",
        "revival_condition": "",
        "next_proposals": [],
        "changed_axis": "",
    }
    if reasoning_contract is not None:
        result["reasoning"] = reasoning.draft(reasoning_contract)
    return result


def build_delta(
    state_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
    handoff_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    base_required = {
        "schema", "delta_id", "episode_id", "outcome", "evidence_refs",
        "frontier_measure_before", "frontier_measure_after", "new_frontier",
        "new_obstruction", "admission_ref", "independent_review",
        "remaining_obstruction", "revival_condition", "next_proposals",
        "changed_axis",
    }
    draft_schema = draft_value.get("schema")
    required = base_required | ({"reasoning"} if draft_schema == DRAFT_SCHEMA else set())
    _closed(draft_value, required, "research delta draft")
    if draft_schema not in {LEGACY_DRAFT_SCHEMA, DRAFT_SCHEMA}:
        raise OrchestrationError("research delta draft schema is invalid")
    pending = _pending_binding(state, draft_value.get("episode_id"))
    if handoff_value is not None:
        handoff = validate_handoff(handoff_value, state)
        if handoff["episode"]["episode_id"] != pending["episode_id"]:
            raise OrchestrationError("research delta draft differs from its sealed handoff")
    else:
        handoff = None
    if draft_schema == DRAFT_SCHEMA:
        if handoff is None or handoff["schema"] not in REASONING_HANDOFF_SCHEMAS:
            raise OrchestrationError("reasoning-bound delta requires its sealed v3 or v4 handoff")
    elif handoff is not None and handoff["schema"] in REASONING_HANDOFF_SCHEMAS:
        raise OrchestrationError("v3/v4 handoff requires a reasoning-bound delta draft")
    controlled = copy.deepcopy(dict(draft_value))
    controlled.pop("schema")
    controlled.pop("episode_id")
    if draft_schema == DRAFT_SCHEMA:
        try:
            controlled["reasoning"] = reasoning.build_state(
                ROOT,
                controlled["reasoning"],
                handoff["reasoning_contract"],
                expected_outcome=controlled["outcome"],
            )
        except reasoning.ReasoningError as exc:
            raise OrchestrationError(str(exc)) from exc
        controlled["messages"] = [
            loop_messages.research_return(
                handoff["reasoning_contract"], controlled["reasoning"]
            )
        ]
    obstruction = controlled.get("new_obstruction")
    if obstruction is not None:
        if not isinstance(obstruction, dict):
            raise OrchestrationError("new_obstruction must be null or an object")
        allowed = {
            "obstruction_id", "statement", "evidence_refs", "revival_condition",
            "route_fingerprint", "core_fingerprint",
        }
        if set(obstruction) - allowed:
            raise OrchestrationError("new_obstruction has unknown fields")
        obstruction["route_fingerprint"] = pending["route_fingerprint"]
        obstruction["core_fingerprint"] = pending["core_fingerprint"]
    round_pending = state["pending_episode"].get("kind") == "ROUND"
    base_revision = (
        state["pending_episode"]["base_revision"] if round_pending else state["revision"]
    )
    base_state_sha256 = (
        state["pending_episode"]["base_state_sha256"]
        if round_pending
        else state["state_sha256"]
    )
    packet = seal_packet({
        "schema": (
            discovery.DELTA_SCHEMA
            if draft_schema == DRAFT_SCHEMA
            else discovery.LEGACY_DELTA_SCHEMA
        ),
        "episode_id": pending["episode_id"],
        "episode_sha256": pending["payload_sha256"],
        "target_sha256": state["target"]["canonical_sha256"],
        "base_revision": base_revision,
        "base_state_sha256": base_state_sha256,
        **controlled,
    })
    try:
        return discovery.validate_delta_binding(
            packet,
            state,
            pending,
            base_revision=base_revision,
            base_state_sha256=base_state_sha256,
        )
    except discovery.DiscoveryError as exc:
        raise OrchestrationError(str(exc)) from exc


def _episode_operator_bindings(
    root: Path,
    domains: list[str],
    episode: Mapping[str, Any],
) -> list[dict[str, Any]]:
    searchable = " ".join(
        str(value)
        for value in (
            episode.get("objective", ""),
            episode.get("evaluator", ""),
            episode.get("expected_delta", ""),
            episode.get("return_condition", episode.get("stop_condition", "")),
            *((episode.get("route") or {}).values()),
        )
    ).casefold()
    selected: list[dict[str, Any]] = []
    for domain in domains:
        manifest = operators.load_manifest(root, domain)
        catalog = {item["id"]: item for item in manifest["operators"]}
        candidates = [
            item for item in manifest["operators"]
            if "researcher" in item["roles"] and item["lane"] == episode["lane"]
        ]
        if not candidates:
            raise OrchestrationError(
                f"domain {domain!r} has no Researcher operator for lane {episode['lane']!r}"
            )
        specific = [item for item in candidates if not item["default"]]
        if specific:
            candidates = specific

        def trigger_count(item: Mapping[str, Any]) -> int:
            return sum(
                bool(re.search(
                    rf"(?<![\w-]){re.escape(trigger.casefold())}(?![\w-])",
                    searchable,
                ))
                for trigger in item["triggers"]
            )

        primary = min(
            candidates,
            key=lambda item: (
                -trigger_count(item), -item["priority"], item["cost_units"], item["id"]
            ),
        )
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(identifier: str, stack: tuple[str, ...] = ()) -> None:
            if identifier in stack:
                raise OrchestrationError("domain operator dependency cycle")
            item = catalog[identifier]
            if "researcher" not in item["roles"]:
                raise OrchestrationError(
                    f"domain operator dependency {identifier!r} excludes Researcher"
                )
            for dependency in item["requires_operators"]:
                add(dependency, (*stack, identifier))
            qualified = f"{domain}:{identifier}"
            if qualified not in seen:
                seen.add(qualified)
                ordered.append(item)

        add(primary["id"])
        for item in ordered:
            selected.append({
                "domain": domain,
                "id": item["id"],
                "lane": item["lane"],
                "summary": item["summary"],
                "requires_capabilities": list(item["requires_capabilities"]),
                "doctrine": list(item["doctrine"]),
                "commands": list(item["commands"]),
                "evidence_ceiling": item["evidence_ceiling"],
                "failure_domain": item["failure_domain"],
                "return_conditions": list(item["stop_conditions"]),
            })
    return selected


def _build_domain_binding(
    root: Path,
    state: Mapping[str, Any],
    capsule: Mapping[str, Any],
    episode_operators: list[dict[str, Any]],
    capability_mode: str,
    routing_text: str,
    required_capabilities: list[str],
) -> dict[str, Any]:
    plan = capabilities.build_load_plan(
        root,
        capability_mode,
        state["domains"],
        "researcher",
        routing_text,
        required_capabilities=required_capabilities,
    )
    if not plan["ok"]:
        raise OrchestrationError(
            "cannot bind Researcher to a domain capability path: "
            + "; ".join(plan["problems"])
        )
    capability_ids = [item["id"] for item in plan["capabilities"]]
    if capability_ids != capsule["capabilities"]:
        raise OrchestrationError("domain capability plan differs from the sealed capsule")

    package_status = domain_packages.status(root, verify=True)
    if not package_status["ok"]:
        raise OrchestrationError("cannot bind an invalid domain package activation")
    status_by_domain = {item["domain"]: item for item in package_status["packages"]}
    packages: list[dict[str, Any]] = []
    for domain in state["domains"]:
        item = status_by_domain.get(domain)
        if item is None or item["status"] not in {"ACTIVE", "DEVELOPMENT_SOURCE"}:
            raise OrchestrationError(f"domain package {domain!r} is not active")
        packages.append({
            key: item[key]
            for key in (
                "domain", "distribution", "version", "core_api",
                "domain_contract_version", "payload_sha256", "payload_files",
                "payload_bytes", "install_receipt_sha256", "activation_sha256",
                "status",
            )
        })

    resources = copy.deepcopy(plan["load_resources"])
    commands = list(plan["commands"])
    reasoning_resource = {
        "local_path": "references/researcher_reasoning.md",
        "skill_locator": "witsoc/references/researcher_reasoning.md",
    }
    if reasoning_resource not in resources:
        resources.append(reasoning_resource)
    for operator in episode_operators:
        for relative in operator["doctrine"]:
            resource = {
                "local_path": relative,
                "skill_locator": f"witsoc/{relative}",
            }
            if resource not in resources:
                resources.append(resource)
        for command in operator["commands"]:
            if command not in commands:
                commands.append(command)
    for domain in state["domains"]:
        prefix = f"domains/{domain}/"
        if not any(item["local_path"].startswith(prefix) for item in resources):
            raise OrchestrationError(
                f"domain capability path for {domain!r} has no bound instruction resource"
            )
    return seal_packet({
        "schema": DOMAIN_BINDING_SCHEMA,
        "mode": state["mode"],
        "capability_mode": capability_mode,
        "role": "researcher",
        "domains": list(state["domains"]),
        "packages": packages,
        "capabilities": capability_ids,
        "episode_operators": episode_operators,
        "load_resources": resources,
        "skill_view_argv": [
            ["$PLANE_TOOL_BIN", "skill-view", item["skill_locator"]]
            for item in resources
        ],
        "commands": commands,
        "pack_status_argv": ["bash", "$WITSOC", "pack-status", "--verify"],
        "load_required": True,
        "core_only_forbidden": True,
    })


def _episode_routing_text(
    state: Mapping[str, Any], episode: Mapping[str, Any]
) -> str:
    route = episode.get("route") or {}
    parts: list[str] = [
        state["target"]["statement"],
        episode.get("objective", ""),
        episode.get("claim", ""),
        episode.get("evaluator", ""),
        episode.get("expected_delta", ""),
        episode.get("return_condition", episode.get("stop_condition", "")),
    ]
    parts.extend(str(route.get(key, "")) for key in (
        "method_family", "mechanism", "structural_object", "required_result",
        "target_effect",
    ))
    parts.extend(str(item) for item in route.get("assumptions", []))
    return "\n".join(item for item in parts if item)


def _episode_capability_mode(
    state: Mapping[str, Any],
    episode: Mapping[str, Any],
) -> str:
    lane = episode["lane"]
    if lane == "RETRIEVE":
        return "SOURCE_SYNTHESIS"
    if lane == "TRANSFER" and (
        state["mode"] == "CROSS_DOMAIN" or len(state["domains"]) > 1
    ):
        return "CROSS_DOMAIN"
    if lane == "VERIFY" or (
        state["mode"] == "CLAIM_VERIFICATION" and lane in {"REFUTE", "MEASURE"}
    ):
        return "CLAIM_VERIFICATION"
    return "OPEN_DISCOVERY"


def _validate_domain_binding(
    value: Mapping[str, Any],
    state: Mapping[str, Any],
    capsule: Mapping[str, Any],
    episode: Mapping[str, Any],
) -> dict[str, Any]:
    required = {
        "schema", "mode", "capability_mode", "role", "domains", "packages",
        "capabilities", "episode_operators", "load_resources", "skill_view_argv", "commands",
        "pack_status_argv", "load_required", "core_only_forbidden",
        "payload_sha256",
    }
    _closed(value, required, "domain binding")
    binding = copy.deepcopy(dict(value))
    if binding["schema"] != DOMAIN_BINDING_SCHEMA or not verify_packet_seal(binding):
        raise OrchestrationError("domain binding schema or seal is invalid")
    if (
        binding["mode"] != state["mode"]
        or binding["capability_mode"] != _episode_capability_mode(state, episode)
        or binding["role"] != "researcher"
        or binding["domains"] != state["domains"]
        or binding["domains"] != capsule.get("domains")
        or binding["capabilities"] != capsule.get("capabilities")
        or binding["load_required"] is not True
        or binding["core_only_forbidden"] is not True
    ):
        raise OrchestrationError("domain binding differs from the Witsoc state or capsule")
    if not binding["domains"] or len(binding["domains"]) != len(set(binding["domains"])):
        raise OrchestrationError("domain binding has no unique selected domains")

    operator_fields = {
        "domain", "id", "lane", "summary", "requires_capabilities", "doctrine", "commands",
        "evidence_ceiling", "failure_domain", "return_conditions",
    }
    episode_operators = binding["episode_operators"]
    if not isinstance(episode_operators, list) or not episode_operators or any(
        not isinstance(item, dict) or set(item) != operator_fields
        for item in episode_operators
    ):
        raise OrchestrationError("domain binding episode operators are malformed")
    if {item["domain"] for item in episode_operators} != set(binding["domains"]):
        raise OrchestrationError("domain binding has no operator for every domain")
    lane_domains = {
        item["domain"] for item in episode_operators if item["lane"] == episode["lane"]
    }
    if lane_domains != set(binding["domains"]):
        raise OrchestrationError(
            "domain binding does not implement the episode lane in every domain"
        )
    operator_ids: set[str] = set()
    for item in episode_operators:
        qualified = f"{item['domain']}:{item['id']}"
        if (
            not isinstance(item["id"], str)
            or not item["id"]
            or qualified in operator_ids
            or not isinstance(item["requires_capabilities"], list)
            or any(
                not isinstance(capability_id, str) or not capability_id
                for capability_id in item["requires_capabilities"]
            )
            or not isinstance(item["doctrine"], list)
            or not isinstance(item["commands"], list)
            or any(not isinstance(path, str) or not path for path in item["doctrine"])
            or any(not isinstance(command, str) or not command for command in item["commands"])
        ):
            raise OrchestrationError("domain binding episode operator is invalid")
        if not {
            f"{item['domain']}:{capability_id}"
            for capability_id in item["requires_capabilities"]
        } <= set(binding["capabilities"]):
            raise OrchestrationError(
                "domain binding omits an operator-required capability"
            )
        operator_ids.add(qualified)

    package_fields = {
        "domain", "distribution", "version", "core_api",
        "domain_contract_version", "payload_sha256", "payload_files",
        "payload_bytes", "install_receipt_sha256", "activation_sha256", "status",
    }
    packages = binding["packages"]
    if not isinstance(packages, list) or any(
        not isinstance(item, dict) or set(item) != package_fields for item in packages
    ):
        raise OrchestrationError("domain binding package attestations are malformed")
    if [item["domain"] for item in packages] != binding["domains"]:
        raise OrchestrationError("domain binding package order or coverage is invalid")
    for item in packages:
        digest = item["payload_sha256"]
        if (
            item["status"] not in {"ACTIVE", "DEVELOPMENT_SOURCE"}
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(item["activation_sha256"], str)
            or len(item["activation_sha256"]) != 64
            or not isinstance(item["payload_files"], int)
            or item["payload_files"] < 1
            or not isinstance(item["payload_bytes"], int)
            or item["payload_bytes"] < 1
        ):
            raise OrchestrationError("domain binding package attestation is invalid")

    resources = binding["load_resources"]
    if not isinstance(resources, list) or not resources:
        raise OrchestrationError("domain binding has no instruction resources")
    expected_argv: list[list[str]] = []
    covered: set[str] = set()
    for resource in resources:
        if not isinstance(resource, dict) or set(resource) != {"local_path", "skill_locator"}:
            raise OrchestrationError("domain binding resource shape is invalid")
        local = resource["local_path"]
        locator = resource["skill_locator"]
        if not isinstance(local, str) or not isinstance(locator, str):
            raise OrchestrationError("domain binding resource path is invalid")
        relative = Path(local)
        if relative.is_absolute() or ".." in relative.parts or locator != f"witsoc/{local}":
            raise OrchestrationError("domain binding resource is not a canonical Witsoc locator")
        for domain in binding["domains"]:
            if local.startswith(f"domains/{domain}/"):
                covered.add(domain)
        expected_argv.append(["$PLANE_TOOL_BIN", "skill-view", locator])
    if covered != set(binding["domains"]):
        raise OrchestrationError("domain binding does not load every selected domain")
    if binding["skill_view_argv"] != expected_argv:
        raise OrchestrationError("domain binding skill-view commands are not canonical")
    if binding["pack_status_argv"] != ["bash", "$WITSOC", "pack-status", "--verify"]:
        raise OrchestrationError("domain binding package verification command is not canonical")
    if not isinstance(binding["commands"], list) or any(
        not isinstance(command, str) or not command for command in binding["commands"]
    ):
        raise OrchestrationError("domain binding capability commands are malformed")
    resource_paths = {item["local_path"] for item in resources}
    command_set = set(binding["commands"])
    if any(
        not set(item["doctrine"]) <= resource_paths
        or not set(item["commands"]) <= command_set
        for item in episode_operators
    ):
        raise OrchestrationError("domain binding omits an episode operator resource")
    return binding


def _worker_prompt(
    relative_handoff: str,
    relative_state: str,
    relative_draft: str,
    relative_delta: str,
    domain_binding: Mapping[str, Any] | None = None,
    reasoning_contract: Mapping[str, Any] | None = None,
    source_map: Mapping[str, Any] | None = None,
) -> str:
    if domain_binding is None:
        return "\n".join([
            "You are the Researcher role inside an already-active Witsoc lifecycle.",
            "This role is a contract for an osci-worker, not a skill or agent named witsoc-researcher.",
            'First run: "$PLANE_TOOL_BIN" skill-view witsoc/researcher/SKILL.md',
            f'Read exactly: "$KIMI_WORK_DIR/{relative_handoff}"',
            "The embedded sealed episode is the only authorized research target.",
            "You have no campaign-stop authority. The return condition ends only this episode and returns control to Explorer.",
            "Do not reinterpret the target, edit frontier state, dispatch a successor, recommend HONEST_STOP, or claim status.",
            "The same-named Witsoc plugin is optional tooling, not activation; do not use it unless the handoff selects it.",
            f'Complete the draft at "$KIMI_WORK_DIR/{relative_draft}" and seal it with:',
            'WITSOC_ROOT=$(dirname "$("$PLANE_TOOL_BIN" skill-which witsoc/SKILL.md)")',
            f'bash "$WITSOC_ROOT/scripts/witsoc.sh" delta-build --state "$KIMI_WORK_DIR/{relative_state}" --handoff "$KIMI_WORK_DIR/{relative_handoff}" --draft "$KIMI_WORK_DIR/{relative_draft}" --out "$KIMI_WORK_DIR/{relative_delta}"',
            f'Commit only assigned artifacts, then mail the orchestrator the commit and path {relative_delta}.',
            "A prose report, worker exit, plugin receipt, or commit without the sealed delta is not a return.",
        ])

    domains = ", ".join(domain_binding["domains"])
    capabilities_text = ", ".join(domain_binding["capabilities"])
    operators_text = ", ".join(
        f"{item['domain']}:{item['id']}" for item in domain_binding["episode_operators"]
    )
    resource_commands = [
        f'"$PLANE_TOOL_BIN" skill-view {item[2]}'
        for item in domain_binding["skill_view_argv"]
    ]
    lines = [
        "You are the Researcher role inside an already-active Witsoc lifecycle.",
        "This role is a contract for an osci-worker, not a skill or agent named witsoc-researcher.",
        'First run: "$PLANE_TOOL_BIN" skill-view witsoc/researcher/SKILL.md',
        f'Read exactly: "$KIMI_WORK_DIR/{relative_handoff}"',
        f"The sealed domain binding is REQUIRED: domains={domains}; capability mode={domain_binding['capability_mode']}; capabilities={capabilities_text}; episode operators={operators_text}.",
        "Do not infer a replacement domain and do not work from the architecture core alone.",
        'WITSOC_ROOT=$(dirname "$("$PLANE_TOOL_BIN" skill-which witsoc/SKILL.md)")',
        'WITSOC="$WITSOC_ROOT/scripts/witsoc.sh"',
        'bash "$WITSOC" pack-status --verify',
        "Require the selected package identity, version, digest, and ACTIVE or DEVELOPMENT_SOURCE status to match domain_binding.packages.",
        "Load every sealed domain instruction resource before the attack:",
        *resource_commands,
        "Use domain_binding.episode_operators, capabilities, and commands as this episode's domain interface.",
        "If package verification or a required skill-view fails, do not continue core-only; return NO_PROGRESS with the exact activation blocker.",
        "The embedded sealed episode is the only authorized research target.",
        "You have no campaign-stop authority. The return condition ends only this episode and returns control to Explorer.",
            "A failed route must preserve the strongest valid partial result and emit typed follow-up seeds; it is not a reason to stop the campaign.",
        "Do not reinterpret the target, edit frontier state, dispatch a successor, recommend HONEST_STOP, or claim status.",
        "The same-named Witsoc plugin is optional tooling, not activation; do not use it unless the handoff selects it.",
        f'Complete the draft at "$KIMI_WORK_DIR/{relative_draft}" and seal it with:',
        f'bash "$WITSOC_ROOT/scripts/witsoc.sh" delta-build --state "$KIMI_WORK_DIR/{relative_state}" --handoff "$KIMI_WORK_DIR/{relative_handoff}" --draft "$KIMI_WORK_DIR/{relative_draft}" --out "$KIMI_WORK_DIR/{relative_delta}"',
        f'Commit only assigned artifacts, then mail the orchestrator the commit and path {relative_delta}.',
        "A prose report, worker exit, plugin receipt, or commit without the sealed delta is not a return.",
    ]
    if reasoning_contract is not None:
        lines[2:2] = [
            "The handoff's sealed reasoning_contract is mandatory.",
            "Confirm campaign_authority=false and allowed_termination=EPISODE_RETURN_ONLY before working.",
            "Verify reasoning_contract.authorization is ATTACK_AUTHORIZATION for this exact episode and state.",
            "Treat reasoning_contract.target_contract as the endpoint specification; every required clause and semantic distinction remains binding.",
            "Keep TARGET and OBJECTIVE separate: refuting the assigned objective is ROUTE_REFUTED unless an atomic target clause is itself refuted.",
            "For every closure candidate, complete target_fidelity against every clause and distinction; exact local mathematics cannot erase a missed boundary, quantifier, exclusion, or generalization condition.",
            "Use CANDIDATE_PRODUCT for full endpoint coverage awaiting independent verification; it returns to Explorer and does not grant status.",
            "Move reasoning.phase SCREENING -> DEEP_ATTACK -> RETURN. Maintain the subgoal DAG, INV-ROUTE and any added invariants, claim graph, obligations, bounded hypotheses, pressure tests, attempts, and contradictions.",
            "Every promoted closure claim needs a discharged linked subgoal and all invariants PRESERVED.",
            "Record concise audit reasons only; never place unrestricted private deliberation in artifacts.",
            "Off-route value is a side result plus REFRAME_REQUIRED; it cannot replace the assigned evaluator or authorize a reframe.",
            "Distinguish TARGET_FALSIFIED, ROUTE_REFUTED, METHOD_BARRIER, CORE_SHARPENED, POSITIVE_SIGNAL, and NO_DELTA exactly; only TARGET_FALSIFIED concerns the endpoint.",
            "For every unresolved return, supply the strongest closure-safe partial result, exact residual obstruction, revival condition, and a mechanism-distinct next proposal.",
            "Delta build derives one typed Researcher-to-Explorer message; do not hand-author or bypass it.",
            "The builder rejects heuristic closure, open subgoals/contradictions, broken invariants, unsupported reductions, and under-scoped obstructions.",
        ]
    if source_map is not None:
        lines[2:2] = [
            "The handoff embeds the exact source map audited by Explorer; its digest, scopes, preconditions, contradictions, and evidence ceilings are binding.",
            "Use source entries only for the claims they explicitly support. Do not cite an Explorer output, widen a source claim, or convert source coverage into closure or open-status authority.",
        ]
    return "\n".join(lines)


def _plane_projection(
    state: Mapping[str, Any],
    episode: Mapping[str, Any],
    paths: Mapping[str, str],
    domain_binding: Mapping[str, Any] | None = None,
    reasoning_contract: Mapping[str, Any] | None = None,
    source_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = _worker_prompt(
        paths["handoff"], paths["state_snapshot"], paths["draft"], paths["delta"],
        domain_binding,
        reasoning_contract,
        source_map,
    )
    metadata = {
        "target_sha256": state["target"]["canonical_sha256"],
        "task_id": episode["episode_id"],
        "work_item_id": episode["episode_id"],
        "campaign_id": state["kernel_id"],
        "base_revision": state["revision"],
        "node_id": episode["node_id"],
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "witsoc_role": "researcher",
        "witsoc_handoff_path": paths["handoff"],
        "witsoc_delta_path": paths["delta"],
    }
    if domain_binding is not None:
        metadata.update({
            "witsoc_domain_required": True,
            "witsoc_domains": list(domain_binding["domains"]),
            "witsoc_capability_mode": domain_binding["capability_mode"],
            "witsoc_capabilities": list(domain_binding["capabilities"]),
            "witsoc_operators": [
                f"{item['domain']}:{item['id']}"
                for item in domain_binding["episode_operators"]
            ],
            "witsoc_domain_binding_sha256": domain_binding["payload_sha256"],
        })
    if reasoning_contract is not None:
        metadata.update({
            "witsoc_reasoning_required": True,
            "witsoc_reasoning_contract_sha256": reasoning_contract["payload_sha256"],
            "witsoc_attack_authorization_sha256": reasoning_contract["authorization"]["payload_sha256"],
            "witsoc_max_hypotheses": reasoning_contract["limits"]["max_hypotheses"],
            "witsoc_max_subgoals": reasoning_contract["limits"]["max_subgoals"],
            "witsoc_reasoning_phases": ["SCREENING", "DEEP_ATTACK", "RETURN"],
            "witsoc_raw_deliberation_forbidden": True,
        })
    if source_map is not None:
        metadata.update({
            "witsoc_source_context_required": True,
            "witsoc_source_map_sha256": source_map["payload_sha256"],
        })
    adjudication = episode.get("adjudication") or {}
    if adjudication.get("schema") == "witsoc.round-adjudication.v1":
        metadata.update({
            "witsoc_round_id": adjudication["round_id"],
            "witsoc_actor_id": adjudication["actor_id"],
            "witsoc_failure_domain": adjudication["failure_domain"],
        })
    title = f"witsoc-researcher:{episode['episode_id']}"
    return {
        "agent": "osci-worker",
        "title": title,
        "target": episode["objective"],
        "prompt": prompt,
        "metadata": metadata,
        "launch_argv": [
            "$PLANE_TOOL_BIN", "launch-worker",
            "--agent", "osci-worker",
            "--title", title,
            "--target", episode["objective"],
            "--prompt", prompt,
            "--require-isolated-worktree", "true",
            "--worktree-base", "$KIMI_WORK_DIR",
            "--metadata", canonical_json(metadata),
        ],
    }


def _bound_source_map(
    root: Path,
    state: Mapping[str, Any],
    episode: Mapping[str, Any],
    source_map_value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    expected_ref = (episode.get("adjudication") or {}).get("source_map_ref")
    if expected_ref is None:
        if source_map_value is not None:
            raise OrchestrationError(
                "episode did not authorize the supplied source-map packet"
            )
        return None
    if source_map_value is None:
        raise OrchestrationError(
            "source-bound episode requires the exact Explorer source-map packet"
        )
    try:
        source_map = contracts.validate_packet(
            root, exploration.SOURCE_MAP_SCHEMA, source_map_value
        )
    except contracts.ContractError as exc:
        raise OrchestrationError(str(exc)) from exc
    if source_map["target_sha256"] != state["target"]["canonical_sha256"]:
        raise OrchestrationError("Researcher source map belongs to another frozen target")
    if source_map["payload_sha256"] != expected_ref:
        raise OrchestrationError("Researcher source map differs from Explorer-audited bytes")
    expected_source_refs = exploration.source_evidence_refs(source_map)
    if (episode.get("adjudication") or {}).get("source_refs", []) != expected_source_refs:
        raise OrchestrationError("Researcher source refs differ from Explorer-audited entries")
    expected_verified_refs = exploration.source_evidence_refs(
        source_map, statuses={"ESTABLISHED", "CORRECTED"}
    )
    if (
        (episode.get("adjudication") or {}).get("source_verified_refs", [])
        != expected_verified_refs
    ):
        raise OrchestrationError(
            "Researcher source-verified refs exceed the Explorer-audited evidence ceiling"
        )
    return source_map


def build_handoff(
    root: Path,
    state_value: Mapping[str, Any],
    episode_value: Mapping[str, Any],
    *,
    workspace_root: Path,
    task_dir: Path,
    handoff_path: Path,
    state_snapshot_path: Path,
    draft_path: Path,
    delta_path: Path,
    context_budget: int = 2048,
    source_map_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workspace = workspace_root.expanduser().resolve()
    if not workspace.is_dir():
        raise OrchestrationError(f"workspace root is not a directory: {workspace}")
    task = _within(task_dir, workspace, "task directory")
    paths = {
        "handoff": _within(handoff_path, task, "handoff path"),
        "state_snapshot": _within(state_snapshot_path, task, "state snapshot path"),
        "draft": _within(draft_path, task, "draft path"),
        "delta": _within(delta_path, task, "delta path"),
    }
    if len(set(paths.values())) != len(paths):
        raise OrchestrationError("handoff, state snapshot, draft, and delta paths must be distinct")
    state, episode = validate_episode_binding(state_value, episode_value)
    source_map = _bound_source_map(root, state, episode, source_map_value)
    routing_text = _episode_routing_text(state, episode)
    episode_operators = _episode_operator_bindings(
        root, list(state["domains"]), episode
    )
    required_capabilities = sorted({
        f"{item['domain']}:{capability_id}"
        for item in episode_operators
        for capability_id in item["requires_capabilities"]
    })
    capability_mode = _episode_capability_mode(state, episode)
    capsule = capsules.build(
        root,
        state,
        role="researcher",
        statement=routing_text,
        capability_mode=capability_mode,
        context_budget=context_budget,
        capsule_id=f"capsule:{episode['episode_id']}",
        source_map=source_map,
        required_capabilities=required_capabilities,
    )
    relatives = {
        key: value.relative_to(workspace).as_posix() for key, value in paths.items()
    }
    domain_binding = _build_domain_binding(
        root,
        state,
        capsule,
        episode_operators,
        capability_mode,
        routing_text,
        required_capabilities,
    )
    reasoning_contract = reasoning.build_contract(state, episode)
    try:
        reasoning_contract = reasoning.validate_contract(
            root, reasoning_contract, state=state, episode=episode
        )
    except reasoning.ReasoningError as exc:
        raise OrchestrationError(str(exc)) from exc
    plane = _plane_projection(
        state, episode, relatives, domain_binding, reasoning_contract, source_map
    )
    packet = seal_packet({
        "schema": HANDOFF_SCHEMA,
        "handoff_id": f"handoff:{episode['episode_id']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "state_revision": state["revision"],
        "state_sha256": state["state_sha256"],
        "role": "researcher",
        "role_resource": "witsoc/researcher/SKILL.md",
        "episode": episode,
        "capsule": capsule,
        "domain_binding": domain_binding,
        "reasoning_contract": reasoning_contract,
        "source_map": source_map,
        "paths": relatives,
        "return_contract": {
            "schema": discovery.DELTA_SCHEMA,
            "draft_schema": DRAFT_SCHEMA,
            "required_path": relatives["delta"],
            "state_is_read_only": True,
            "successor_dispatch_forbidden": True,
            "return_to": "EXPLORER",
        },
        "plugin_boundary": {
            "witsoc_skill": "REQUIRED",
            "same_named_plugin": "OPTIONAL_BACKEND_ONLY",
            "plugin_use_is_activation": False,
        },
        "plane": plane,
    })
    validate_handoff(packet, state)
    draft = delta_draft(state, episode, reasoning_contract)
    return packet, draft, copy.deepcopy(state)


def build_round_handoffs(
    root: Path,
    state_value: Mapping[str, Any],
    round_value: Mapping[str, Any],
    *,
    workspace_root: Path,
    task_dir: Path,
    output_dir: Path,
    context_budget: int = 2048,
    source_map_value: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state, round_packet = rounds.validate_round_binding(root, state_value, round_value)
    workspace = workspace_root.expanduser().resolve()
    task = task_dir if task_dir.is_absolute() else workspace / task_dir
    base = output_dir if output_dir.is_absolute() else task / output_dir
    results: list[dict[str, Any]] = []
    for index, wrapped in enumerate(round_packet["episodes"], start=1):
        worker_dir = base / f"worker-{index:02d}"
        packet, draft, snapshot = build_handoff(
            root,
            state,
            wrapped["episode"],
            workspace_root=workspace,
            task_dir=task,
            handoff_path=worker_dir / "researcher-handoff.json",
            state_snapshot_path=worker_dir / "researcher-state.json",
            draft_path=worker_dir / "research-delta.draft.json",
            delta_path=worker_dir / "research-delta.json",
            context_budget=context_budget,
            source_map_value=source_map_value,
        )
        results.append({
            "episode_id": wrapped["episode"]["episode_id"],
            "actor_id": wrapped["actor_id"],
            "failure_domain": wrapped["failure_domain"],
            "handoff": packet,
            "draft": draft,
            "state_snapshot": snapshot,
            "worker_dir": worker_dir,
        })
    return results


def validate_handoff(
    value: Mapping[str, Any], state_value: Mapping[str, Any]
) -> dict[str, Any]:
    base_required = {
        "schema", "handoff_id", "target_sha256", "state_revision",
        "state_sha256", "role", "role_resource", "episode", "capsule",
        "paths", "return_contract", "plugin_boundary", "plane",
        "payload_sha256",
    }
    schema = value.get("schema")
    required = base_required
    if schema in {DOMAIN_HANDOFF_SCHEMA, REASONING_HANDOFF_SCHEMA, HANDOFF_SCHEMA}:
        required |= {"domain_binding"}
    if schema in REASONING_HANDOFF_SCHEMAS:
        required |= {"reasoning_contract"}
    if schema == HANDOFF_SCHEMA:
        required |= {"source_map"}
    _closed(value, required, "orchestrator handoff")
    packet = copy.deepcopy(dict(value))
    if packet["schema"] not in {
        LEGACY_HANDOFF_SCHEMA, DOMAIN_HANDOFF_SCHEMA,
        REASONING_HANDOFF_SCHEMA, HANDOFF_SCHEMA,
    } or packet["role"] != "researcher":
        raise OrchestrationError("orchestrator handoff schema or role is invalid")
    if packet["role_resource"] != "witsoc/researcher/SKILL.md":
        raise OrchestrationError("orchestrator handoff uses a noncanonical role locator")
    if not verify_packet_seal(packet):
        raise OrchestrationError("orchestrator handoff seal is broken")
    state, episode = validate_episode_binding(state_value, packet["episode"])
    expected = {
        "target_sha256": state["target"]["canonical_sha256"],
        "state_revision": state["revision"],
        "state_sha256": state["state_sha256"],
    }
    for field, value_expected in expected.items():
        if packet[field] != value_expected:
            raise OrchestrationError(f"orchestrator handoff {field} is stale")
    capsule = packet["capsule"]
    if (
        capsule.get("target_sha256") != packet["target_sha256"]
        or capsule.get("base_state_sha256") != packet["state_sha256"]
        or capsule.get("role") != "researcher"
        or not verify_packet_seal(capsule)
    ):
        raise OrchestrationError("orchestrator handoff capsule is stale or unsealed")
    expected_delta_schema = (
        discovery.DELTA_SCHEMA
        if packet["schema"] in REASONING_HANDOFF_SCHEMAS
        else discovery.LEGACY_DELTA_SCHEMA
    )
    if packet["return_contract"].get("schema") != expected_delta_schema:
        raise OrchestrationError("orchestrator handoff return schema is invalid")
    paths = packet["paths"]
    if not isinstance(paths, dict) or set(paths) != {
        "handoff", "state_snapshot", "draft", "delta"
    }:
        raise OrchestrationError("orchestrator handoff paths are incomplete")
    for label, relative in paths.items():
        if not isinstance(relative, str):
            raise OrchestrationError(f"orchestrator handoff {label} path is unsafe")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise OrchestrationError(f"orchestrator handoff {label} path is unsafe")
    if packet["return_contract"].get("required_path") != paths["delta"]:
        raise OrchestrationError("orchestrator handoff return path is inconsistent")
    domain_binding = None
    if packet["schema"] in {
        DOMAIN_HANDOFF_SCHEMA, REASONING_HANDOFF_SCHEMA, HANDOFF_SCHEMA,
    }:
        domain_binding = _validate_domain_binding(
            packet["domain_binding"], state, capsule, episode
        )
    reasoning_contract = None
    if packet["schema"] in REASONING_HANDOFF_SCHEMAS:
        try:
            reasoning_contract = reasoning.validate_contract(
                ROOT,
                packet["reasoning_contract"],
                state=state,
                episode=episode,
            )
        except reasoning.ReasoningError as exc:
            raise OrchestrationError(str(exc)) from exc
    source_map = None
    if packet["schema"] == HANDOFF_SCHEMA:
        source_map = _bound_source_map(
            ROOT, state, episode, packet["source_map"]
        )
    elif (episode.get("adjudication") or {}).get("source_map_ref") is not None:
        raise OrchestrationError(
            "a source-bound episode cannot be downgraded below handoff v4"
        )
    if packet["plane"] != _plane_projection(
        state, episode, paths, domain_binding, reasoning_contract, source_map
    ):
        raise OrchestrationError("orchestrator handoff Plane projection is not canonical")
    if episode["episode_id"] not in packet["handoff_id"]:
        raise OrchestrationError("orchestrator handoff id does not bind the episode")
    return packet


def _last_event(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    events = state.get("events") or []
    return events[-1] if events else None


def _terminal_gate(
    report: dict[str, Any],
    state: Mapping[str, Any],
    action: str,
    finalization_value: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if action == "DIRECT_ANSWER" and state["status"] not in kernel.ACCEPTED:
        raise OrchestrationError("DIRECT_ANSWER lacks an admitted frontier status")
    if finalization_value is None:
        report.update({
            "stage": "BUILD_FINALIZATION",
            "terminal_candidate": action,
            "required_action": (
                "Run campaign-audit, bind exact product bytes through review-draft and "
                "review-check when DIRECT_ANSWER is requested, then run finalize. "
                "Completion remains closed until the resulting packet is supplied here."
            ),
            "completion_allowed": False,
        })
        if action == "HONEST_STOP":
            report["terminal_scope"] = "CURRENT_AUTHORIZED_SEARCH_ONLY"
        return report
    try:
        finalization = assurance.validate_finalization(ROOT, state, finalization_value)
    except assurance.AssuranceError as exc:
        raise OrchestrationError(str(exc)) from exc
    if finalization["terminal_action"] != action:
        raise OrchestrationError("finalization action differs from Explorer arbitration")
    report.update({
        "stage": f"TERMINAL_{action}",
        "required_action": (
            "Report only the canonical result generated from this finalization packet; "
            "do not append stronger free-form conclusions."
        ),
        "completion_allowed": True,
        "finalization_sha256": finalization["payload_sha256"],
        "assurance_level": finalization["assurance_level"],
    })
    if action == "HONEST_STOP":
        report["terminal_scope"] = "CURRENT_AUTHORIZED_SEARCH_ONLY"
    return report


def next_action(
    state_value: Mapping[str, Any],
    *,
    handoff_value: Mapping[str, Any] | None = None,
    delta_value: Mapping[str, Any] | None = None,
    finalization_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    pending = state["pending_episode"]
    last = _last_event(state)
    report: dict[str, Any] = {
        "schema": "witsoc.orchestrator-next.v1",
        "ok": True,
        "target_sha256": state["target"]["canonical_sha256"],
        "revision": state["revision"],
        "state_sha256": state["state_sha256"],
        "initialization_only": state["revision"] == 0,
        "worker_launch_allowed": False,
        "completion_allowed": False,
        "launch_argv": None,
        "problems": [],
    }
    if state["genesis"].get("activation_binding") is not None:
        try:
            audit = assurance.campaign_audit(ROOT, state)
        except assurance.AssuranceError as exc:
            raise OrchestrationError(str(exc)) from exc
        report["campaign_audit"] = {
            "disposition": audit["disposition"],
            "payload_sha256": audit["payload_sha256"],
            "blockers": audit["body"]["blockers"],
            "warnings": audit["body"]["warnings"],
        }
        if audit["disposition"] == "BLOCKED":
            report.update({
                "ok": False,
                "stage": "CAMPAIGN_RECONCILIATION",
                "required_action": (
                    "Do not dispatch or finalize. Reconcile frontier.json with the sealed "
                    "episode/delta history, remove stale worktree paths, and regenerate stale "
                    "terminal reports; rerun campaign-audit before continuing."
                ),
                "problems": [item["detail"] for item in audit["body"]["blockers"]],
            })
            return report
    if pending is not None:
        if finalization_value is not None:
            raise OrchestrationError("pending work makes finalization stale")
        if delta_value is not None:
            if pending.get("kind") == "ROUND":
                binding = _pending_binding(state, delta_value.get("episode_id"))
                discovery.validate_delta_binding(
                    delta_value,
                    state,
                    binding,
                    base_revision=pending["base_revision"],
                    base_state_sha256=pending["base_state_sha256"],
                )
                report.update({
                    "stage": "COLLECT_BOUND_ROUND_DELTA",
                    "required_action": (
                        "Collect every distinct child delta, then run round-merge and "
                        "round-return before re-entering Explorer."
                    ),
                    "round_id": pending["round_id"],
                    "episode_id": binding["episode_id"],
                    "required_episode_ids": [
                        item["episode_id"] for item in pending["episodes"]
                    ],
                })
                if delta_value.get("schema") == discovery.DELTA_SCHEMA:
                    report["reasoning"] = reasoning.summary(delta_value["reasoning"])
                return report
            discovery.validate_delta(delta_value, state)
            report.update({
                "stage": "IMPORT_BOUND_DELTA",
                "required_action": "Run episode-return, then re-enter Explorer; do not launch another worker.",
            })
            if delta_value.get("schema") == discovery.DELTA_SCHEMA:
                report["reasoning"] = reasoning.summary(delta_value["reasoning"])
            return report
        if handoff_value is None:
            if pending.get("kind") == "ROUND":
                report.update({
                    "stage": "BUILD_ROUND_HANDOFFS",
                    "required_action": (
                        "Run orchestrator-round-handoffs with the exact issued round; "
                        "validate each generated handoff here before launch."
                    ),
                    "round_id": pending["round_id"],
                    "required_episode_ids": [
                        item["episode_id"] for item in pending["episodes"]
                    ],
                })
                return report
            report.update({
                "stage": "BUILD_RESEARCHER_HANDOFF",
                "required_action": (
                    "Run orchestrator-handoff with the exact issued episode and its "
                    "Explorer source map when source_map_ref is present; an issued episode "
                    "alone is not a launch packet."
                ),
            })
            return report
        handoff = validate_handoff(handoff_value, state)
        report.update({
            "stage": (
                "LAUNCH_BOUND_ROUND_RESEARCHER"
                if pending.get("kind") == "ROUND"
                else "LAUNCH_BOUND_RESEARCHER"
            ),
            "required_action": "Launch exactly this osci-worker and wait for its sealed delta.",
            "worker_launch_allowed": True,
            "launch_argv": handoff["plane"]["launch_argv"],
            "handoff_sha256": handoff["payload_sha256"],
            "episode_id": handoff["episode"]["episode_id"],
        })
        binding = handoff.get("domain_binding")
        report["domain_binding"] = (
            {
                "schema": binding["schema"],
                "domains": binding["domains"],
                "capability_mode": binding["capability_mode"],
                "capabilities": binding["capabilities"],
                "episode_operators": binding["episode_operators"],
                "packages": binding["packages"],
                "skill_view_argv": binding["skill_view_argv"],
                "payload_sha256": binding["payload_sha256"],
                "load_required": True,
            }
            if binding is not None
            else {
                "schema": "witsoc.domain-binding.legacy-v1",
                "domains": handoff["capsule"]["domains"],
                "capabilities": handoff["capsule"]["capabilities"],
                "load_required": False,
            }
        )
        reasoning_contract = handoff.get("reasoning_contract")
        report["reasoning_contract"] = (
            {
                "schema": reasoning_contract["schema"],
                "payload_sha256": reasoning_contract["payload_sha256"],
                "max_claims": reasoning_contract["limits"]["max_claims"],
                "max_hypotheses": reasoning_contract["limits"]["max_hypotheses"],
                "max_subgoals": reasoning_contract["limits"]["max_subgoals"],
                "authorization_sha256": reasoning_contract["authorization"]["payload_sha256"],
                "campaign_authority": reasoning_contract["campaign_authority"],
                "allowed_termination": reasoning_contract["allowed_termination"],
                "required": True,
            }
            if reasoning_contract is not None
            else {
                "schema": "witsoc.reasoning-contract.legacy",
                "required": False,
            }
        )
        source_map = handoff.get("source_map")
        report["source_context"] = {
            "required": source_map is not None,
            "payload_sha256": (
                source_map["payload_sha256"] if source_map is not None else None
            ),
            "status_authority": False,
        }
        if pending.get("kind") == "ROUND":
            report["round_id"] = pending["round_id"]
        return report

    if handoff_value is not None or delta_value is not None:
        raise OrchestrationError("no work is pending; handoff or delta would be stale")
    if last and last["kind"] == "ARBITRATION_RECORDED":
        arbitration = last["payload"]["arbitration"]
        action = arbitration["action"]
        report["explorer_arbitration"] = {
            "action": action,
            "impact": arbitration["impact"],
            "evidence_ceiling": arbitration["evidence_ceiling"],
            "route_disposition": arbitration["route_disposition"],
            "frontier_measure": len(arbitration["frontier_delta"]["active_ids"]),
            "payload_sha256": arbitration["payload_sha256"],
        }
        if action in TERMINAL_ACTIONS:
            return _terminal_gate(
                report, state, action, finalization_value
            )
        if finalization_value is not None:
            raise OrchestrationError("finalization supplied before terminal Explorer arbitration")
        report.update({
            "stage": (
                "EXPLORER_FRONTIER_EXPANDED"
                if action in {"REFRAME_FRONTIER", "EXPAND_FRONTIER"}
                else "CAMPAIGN_PAUSED_WITH_FRONTIER"
                if action == "PAUSE_WITH_FRONTIER"
                else "EXPLORER_DECISION"
            ),
            "required_action": (
                "The frontier change is recorded. Build proposals against this new state, "
                "then run explorer-draft and explorer-check before issuing work."
                if action in {"REFRAME_FRONTIER", "EXPAND_FRONTIER"}
                else
                "The campaign is resumably paused with its open frontier intact. Persist the "
                "state and re-enter Explorer when resources or a new route are available."
                if action == "PAUSE_WITH_FRONTIER"
                else
                "Re-enter Explorer on the current state; no worker launch is authorized."
            ),
            "explorer_command_sequence": [
                "explorer-proposal-draft --state STATE --proposal-id ID --node-id NODE --lane LANE --out PROPOSAL_DRAFT",
                "explorer-proposal-check --state STATE --input PROPOSAL_DRAFT --out PROPOSAL",
                "explorer-draft --state STATE --proposals PROPOSALS [--prior-explorer PRIOR] --out EXPLORER_DRAFT",
                "edit only EXPLORER_DRAFT decision, frontier, source, and domain-control fields",
                "explorer-check --state STATE --input EXPLORER_DRAFT --proposals PROPOSALS --source-map SOURCE_MAP --out EXPLORER_STATE",
                "episode-issue --state STATE --explorer-state EXPLORER_STATE --proposals PROPOSALS --source-map SOURCE_MAP ...",
            ],
        })
        return report
    if last and last["kind"] == "DECISION_RECORD":
        action = last["payload"]["decision"]["action"]
        if action in TERMINAL_ACTIONS:
            return _terminal_gate(
                report, state, action, finalization_value
            )
    if finalization_value is not None:
        raise OrchestrationError("finalization supplied before terminal Explorer arbitration")
    returned = last and last["kind"] in {"EPISODE_RETURNED", "ROUND_RETURNED"}
    report.update({
        "stage": "EXPLORER_RETURN_ARBITRATION" if returned else "EXPLORER_DECISION",
        "required_action": (
            "Load witsoc/explorer/SKILL.md; run explorer-draft, edit the bounded worksheet, "
            "and run explorer-check. Then atomically issue selected work or use "
            "explorer-arbitrate for a non-dispatch action."
            if returned else
            "Load witsoc/explorer/SKILL.md; build a typed frontier and proposals with "
            "explorer-draft plus explorer-check before issuing any work."
        ),
        "explorer_contract": exploration.build_contract(state),
        "explorer_command_sequence": [
            "explorer-proposal-draft --state STATE --proposal-id ID --node-id NODE --lane LANE --out PROPOSAL_DRAFT",
            "explorer-proposal-check --state STATE --input PROPOSAL_DRAFT --out PROPOSAL",
            "explorer-draft --state STATE --proposals PROPOSALS [--prior-explorer PRIOR] --out EXPLORER_DRAFT",
            "edit only EXPLORER_DRAFT decision, frontier, source, and domain-control fields",
            "explorer-check --state STATE --input EXPLORER_DRAFT --proposals PROPOSALS --source-map SOURCE_MAP --out EXPLORER_STATE",
            "episode-issue --state STATE --explorer-state EXPLORER_STATE --proposals PROPOSALS --source-map SOURCE_MAP ...",
        ],
    })
    if state["revision"] == 0:
        report["problems"].append(
            "frontier initialization is not Explorer arbitration and cannot complete a Witsoc task"
        )
    if last and last["kind"] == "EPISODE_RETURNED":
        delta = last["payload"]["delta"]
        if delta.get("schema") == discovery.DELTA_SCHEMA:
            report["reasoning"] = reasoning.summary(delta["reasoning"])
            report["reframe_request"] = delta["reasoning"]["route_compliance"]["reframe_request"] or None
            report["open_contradictions"] = [
                item["contradiction_id"]
                for item in delta["reasoning"]["contradictions"]
                if item["status"] == "OPEN"
            ]
    elif last and last["kind"] == "ROUND_RETURNED":
        report["reasoning_returns"] = [
            reasoning.summary(delta["reasoning"])
            for delta in last["payload"]["round_delta"]["deltas"]
            if delta.get("schema") == discovery.DELTA_SCHEMA
        ]
    return report


def record_decision(
    state_value: Mapping[str, Any],
    *,
    decision_id: str,
    action: str,
    basis_refs: list[str],
    alternatives: list[str],
    changed_axis: str,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    if state["mode"] == "OPEN_DISCOVERY":
        raise OrchestrationError(
            "OPEN_DISCOVERY decisions require a sealed Explorer state and typed arbitration"
        )
    if state["pending_episode"] is not None:
        raise OrchestrationError("Explorer cannot decide terminal state while work is pending")
    if action not in DECISION_ACTIONS:
        raise OrchestrationError(f"unsupported Explorer action {action!r}")
    if not decision_id.strip() or not basis_refs or any(not item.strip() for item in basis_refs):
        raise OrchestrationError("Explorer decision requires an id and non-empty basis references")
    if action == "HONEST_STOP" and not alternatives:
        raise OrchestrationError("HONEST_STOP must retain at least one attempted alternative")
    if action == "DIRECT_ANSWER" and state["status"] not in kernel.ACCEPTED:
        raise OrchestrationError("DIRECT_ANSWER requires reducer-admitted frontier status")
    decision = {
        "decision_id": decision_id,
        "action": action,
        "basis_refs": list(dict.fromkeys(basis_refs)),
        "alternatives": list(dict.fromkeys(alternatives)),
        "changed_axis": changed_axis,
    }
    event = kernel.build_event(
        state, "DECISION_RECORD", {"decision": decision}, f"decision:{decision_id}"
    )
    return kernel.apply_event(state, event)
