"""Command line interface for routing, state, discovery, bridges, and memory."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import (
    assurance,
    bridges,
    capabilities,
    capability_graph,
    capsules,
    contracts,
    discovery,
    domain_packages,
    evidence_memory,
    exploration,
    hint_memory,
    kernel,
    migrations,
    modes,
    operators,
    orchestration,
    projections,
    reasoning,
    research_ir,
    rounds,
    runtime_contracts,
)
from .canonical import atomic_write_json, atomic_write_text, digest_value, load_json, seal_packet


ROOT = Path(__file__).resolve().parents[2]


def emit(value: Any, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        print(value)


def write_state(path: Path, value: dict[str, Any], *, write: bool, out: Path | None) -> Path | None:
    destination = path if write else out
    if destination is not None:
        atomic_write_json(destination, value)
    return destination


def statement_input(args: argparse.Namespace) -> str:
    statement_file = getattr(args, "statement_file", None)
    statement = statement_file.read_text(encoding="utf-8") if statement_file else args.statement
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("statement must not be empty")
    return statement


def route_command(args: argparse.Namespace) -> int:
    statement = statement_input(args)
    result = modes.route(ROOT, statement, args.intent, args.domain, args.role)
    if result["decision"] in {"SELECTED", "AMBIGUOUS"}:
        result["load_plan"] = capabilities.build_load_plan(
            ROOT,
            result["mode"],
            result["domains"],
            args.role,
            statement,
            goal_type=args.goal_type,
            available_types=args.available_type,
            required_capabilities=args.capability,
        )
    emit(result)
    if result["decision"] == "SELECTED" and not result.get("load_plan", {}).get("ok", False):
        return 6
    return {"SELECTED": 0, "AMBIGUOUS": 3, "NO_MATCH": 4, "UNRESOLVABLE": 5}.get(
        result["decision"], 1
    )


def package_status_command(args: argparse.Namespace) -> int:
    result = domain_packages.status(ROOT, verify=args.verify)
    emit(result)
    return 0 if result["ok"] else 1


def package_ensure_command(args: argparse.Namespace) -> int:
    if args.domain:
        domains = args.domain
        resolution: dict[str, Any] = {
            "decision": "SELECTED",
            "domains": sorted(set(domains)),
            "by": "explicit",
        }
    else:
        import resolve_domain

        packs = domain_packages.routing_packs(ROOT)
        resolution = resolve_domain.decide(
            packs, resolve_domain.normalize(statement_input(args))
        )
        domains = resolution.get("candidates") or (
            [resolution["domain"]] if resolution.get("domain") else []
        )
        if not domains:
            result = {
                "schema": "witsoc.domain-package-ensure.v1",
                "ok": False,
                "resolution": resolution,
                "activation": None,
                "problems": ["request does not select an installable domain package"],
            }
            emit(result)
            return 4
    activation = domain_packages.ensure_domains(
        ROOT,
        domains,
        installer=args.installer,
        wheelhouse=args.wheelhouse,
        offline=args.offline,
        allow_install=False if args.no_install else None,
    )
    result = {
        "schema": "witsoc.domain-package-ensure.v1",
        "ok": activation["ok"],
        "resolution": resolution,
        "activation": activation,
        "problems": activation["problems"],
    }
    emit(result)
    return 0 if result["ok"] else 1


def _resource_list(route: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, str]]:
    activation = route.get("activation_resources") or {
        "root": modes.skill_resource("SKILL.md"),
        "mode": None,
        "roles": [{"role": plan["role"], **plan["role_contract"]}],
    }
    resources = [
        {"kind": "root", **activation["root"]},
        {"kind": "protocol", **modes.skill_resource("references/orchestrator_protocol.md")},
        *([{"kind": "mode", **activation["mode"]}] if activation["mode"] else []),
        *({"kind": "role", **item} for item in activation["roles"]),
        *({"kind": "capability", **item} for item in plan["load_resources"]),
    ]
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in resources:
        if item["skill_locator"] not in seen:
            unique.append(item)
            seen.add(item["skill_locator"])
    return unique


def _plane_prefix(raw: str) -> list[str]:
    expanded = Path(raw).expanduser()
    resolved = expanded if expanded.is_file() else Path(shutil.which(raw) or "")
    if not resolved.is_file():
        raise ValueError(f"Plane tool does not exist: {raw}")
    if resolved.suffix == ".cjs":
        node = shutil.which("node")
        if not node:
            raise ValueError("Plane tool is a .cjs file but node is unavailable")
        return [node, str(resolved.resolve())]
    return [str(resolved.resolve())]


def _plane_resource_check(raw: str | None, resources: list[dict[str, str]]) -> dict[str, Any]:
    if raw is None:
        return {
            "status": "NOT_REQUESTED",
            "checks": [],
            "problems": [],
            "reason": "pass --plane-tool to bind installed Plane resolution",
        }
    prefix = _plane_prefix(raw)
    checks: list[dict[str, Any]] = []
    problems: list[str] = []
    for resource in resources:
        completed = subprocess.run(
            [*prefix, "skill-which", resource["skill_locator"]],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        expected = (ROOT / resource["local_path"]).resolve()
        actual = Path(output).expanduser().resolve() if completed.returncode == 0 else None
        ok = completed.returncode == 0 and actual == expected
        checks.append({
            "skill_locator": resource["skill_locator"],
            "expected": str(expected),
            "actual": output,
            "exit_code": completed.returncode,
            "ok": ok,
        })
        if not ok:
            problems.append(
                f"Plane cannot resolve {resource['skill_locator']!r} to the active Witsoc bytes"
            )
    return {
        "status": "PASS" if not problems else "FAIL",
        "checks": checks,
        "problems": problems,
    }


def orchestrator_preflight_command(args: argparse.Namespace) -> int:
    statement = statement_input(args)
    route = modes.route(ROOT, statement, args.intent, args.domain, args.role)
    problems: list[str] = []
    if route["decision"] not in {"SELECTED", "AMBIGUOUS"}:
        problems.append(f"route decision is {route['decision']}; no role work may start")
        if route.get("mode"):
            plan = capabilities.build_load_plan(
                ROOT,
                route["mode"],
                [],
                args.role,
                statement,
                goal_type=args.goal_type,
                available_types=args.available_type,
                required_capabilities=args.capability,
            )
        else:
            plan = {
                "ok": False,
                "role": args.role,
                "role_contract": {
                    "role": args.role,
                    **modes.skill_resource(modes.ROLE_PATHS[args.role]),
                },
                "required_path": [],
                "requested_extensions": [],
                "triggered_extensions": [],
                "deferred_extensions": [],
                "load_resources": [],
                "commands": [],
                "contracts": [],
                "estimated_tokens": 0,
                "problems": [],
            }
    else:
        plan = capabilities.build_load_plan(
            ROOT,
            route["mode"],
            route["domains"],
            args.role,
            statement,
            goal_type=args.goal_type,
            available_types=args.available_type,
            required_capabilities=args.capability,
        )
        problems.extend(plan["problems"])

    canonical_target_sha256 = args.target_sha256
    if canonical_target_sha256 is None and route.get("mode"):
        request_packet = research_ir.request(
            ROOT,
            statement,
            intent=args.objective,
            constraints=args.constraint,
            requested_output="witsoc.decision.v2",
        )
        target_packet = research_ir.target(
            ROOT,
            request_packet,
            mode=route["mode"],
            domains=route.get("domains") or [],
            scope={},
        )
        canonical_target_sha256 = target_packet["content_sha256"]
    target = kernel.target_record(
        statement,
        args.objective,
        args.constraint,
        canonical_sha256=canonical_target_sha256,
    )

    workspace = args.workspace_root.expanduser().resolve()
    if not workspace.is_dir():
        problems.append(f"workspace root is not an existing directory: {workspace}")
    raw_task = args.task_dir.expanduser()
    task_dir = (raw_task if raw_task.is_absolute() else workspace / raw_task).resolve()
    try:
        task_relative = task_dir.relative_to(workspace).as_posix()
    except ValueError:
        task_relative = None
        problems.append("task directory escapes the bound workspace")
    if task_dir.exists() and not task_dir.is_dir():
        problems.append(f"task directory exists but is not a directory: {task_dir}")

    artifact_returns: list[str] = []
    for raw in args.artifact_return:
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            problems.append(f"artifact return must be a relative non-escaping path: {raw!r}")
        else:
            artifact_returns.append(path.as_posix())
    if args.worker_workspace == "isolated-return":
        if not args.base_revision:
            problems.append("isolated-return requires --base-revision")
        if not artifact_returns:
            problems.append("isolated-return requires at least one --artifact-return")
    elif args.base_revision or artifact_returns:
        problems.append("base revision and artifact returns apply only to isolated-return")

    resources = _resource_list(route, plan)
    for resource in resources:
        local = ROOT / resource["local_path"]
        if not local.is_file():
            problems.append(f"installed resource is missing: {resource['local_path']}")
        if not resource["skill_locator"].startswith("witsoc/"):
            problems.append(f"non-canonical Plane locator: {resource['skill_locator']}")
    try:
        plane = _plane_resource_check(args.plane_tool, resources)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        plane = {"status": "FAIL", "checks": [], "problems": [str(exc)]}
    problems.extend(plane["problems"])

    dispatch_gate = {
        "worker_launch_allowed": False,
        "opens_only_after": "SEALED_EPISODE_OR_STRONG_ROUND_AND_BOUND_HANDOFF",
        "open_discovery_issue_requires": "SEALED_EXPLORER_STATE_AND_ATOMIC_ARBITRATION",
        "host_missions_are": "EXPLORER_PROPOSALS_NOT_DISPATCH_AUTHORITY",
        "frontier_initialization_is_completion": False,
        "same_named_plugin_is_activation": False,
        "next_command": "orchestrator-next --state <task-dir>/frontier.json",
    }
    compact_plan = {
        "ok": plan["ok"],
        "role": plan["role"],
        "capabilities": (
            plan["required_path"]
            + plan["requested_extensions"]
            + plan["triggered_extensions"]
        ),
        "commands": plan["commands"],
        "contracts": plan["contracts"],
        "estimated_tokens": plan["estimated_tokens"],
        "deferred_extensions": plan["deferred_extensions"],
    }
    result = assurance.build_activation_receipt(
        ROOT,
        target=target,
        route=route,
        role=args.role,
        resources=resources,
        load_plan=compact_plan,
        workspace={
            "root": str(workspace),
            "task_dir": str(task_dir),
            "task_dir_relative": task_relative,
            "task_dir_existed_before_preflight": task_dir.exists(),
            "worker_mode": args.worker_workspace.upper().replace("-", "_"),
            "base_revision": args.base_revision,
            "artifact_returns": artifact_returns,
            "user_bound_paths_are_immutable": True,
        },
        plane_resolution=plane,
        coordination=route.get("coordination"),
        protocol_resource=modes.skill_resource("references/orchestrator_protocol.md"),
        side_effects=(
            (route.get("domain_packages") or {}).get("activation") or {}
        ).get("side_effects", []),
        dispatch_gate=dispatch_gate,
        problems=problems,
    )
    atomic_write_json(args.out, result)
    emit(result)
    return 0 if result["ok"] else 1


def start_command(args: argparse.Namespace) -> int:
    statement = statement_input(args)
    activation = assurance.validate_activation(ROOT, load_json(args.preflight))
    route = activation["route"]
    if route["role"] != args.role:
        raise assurance.AssuranceError("start role differs from preflight role")
    if args.intent and route["mode"] != args.intent:
        raise assurance.AssuranceError("start intent differs from preflight mode")
    if args.domain and route["domains"] != [args.domain]:
        raise assurance.AssuranceError("start domain differs from preflight domains")
    request_packet = research_ir.request(
        ROOT,
        statement,
        intent=args.objective,
        constraints=args.constraint,
        requested_output="witsoc.decision.v2",
    )
    target_packet = research_ir.target(
        ROOT,
        request_packet,
        mode=route["mode"],
        domains=route["domains"],
        scope={},
    )
    target = kernel.target_record(
        statement,
        args.objective,
        args.constraint,
        canonical_sha256=args.target_sha256 or target_packet["content_sha256"],
    )
    if target != activation["target"]:
        raise assurance.AssuranceError("start target differs from sealed preflight target")
    task_dir = Path(activation["workspace"]["task_dir"]).resolve()
    if args.out.expanduser().resolve().parent != task_dir:
        raise assurance.AssuranceError("frontier output must be directly inside the bound task directory")
    if args.target_out and args.target_out.expanduser().resolve().parent != task_dir:
        raise assurance.AssuranceError("target output must be directly inside the bound task directory")
    state = kernel.new_state(
        target,
        route["mode"],
        route["domains"],
        ceiling=args.ceiling,
        route_sha256=route["route_sha256"],
        activation_binding=assurance.activation_binding(activation),
    )
    atomic_write_json(args.out, state)
    if args.target_out:
        atomic_write_json(args.target_out, target_packet)
    emit({
        "ok": True,
        "state": str(args.out.expanduser().resolve()),
        "target_sha256": target["canonical_sha256"],
        "target_packet": str(args.target_out.expanduser().resolve()) if args.target_out else None,
        "mode": route["mode"],
        "domains": route["domains"],
        "activation_receipt_sha256": activation["payload_sha256"],
        "load_plan": activation["load_plan"],
        "state_sha256": state["state_sha256"],
    })
    return 0


def orchestrator_next_command(args: argparse.Namespace) -> int:
    handoff = load_json(args.handoff) if args.handoff else None
    delta = load_json(args.delta) if args.delta else None
    finalization = load_json(args.finalization) if args.finalization else None
    result = orchestration.next_action(
        load_json(args.state),
        handoff_value=handoff,
        delta_value=delta,
        finalization_value=finalization,
    )
    emit(result)
    return 0


def review_draft_command(args: argparse.Namespace) -> int:
    packet = assurance.review_draft(
        ROOT,
        load_json(args.state),
        review_id=args.review_id,
        revision_id=args.revision_id,
        producer_id=args.producer_id,
        producer_method=args.producer_method,
        producer_failure_domains=args.producer_failure_domain,
        reviewer_id=args.reviewer_id,
        reviewer_method=args.reviewer_method,
        reviewer_failure_domains=args.reviewer_failure_domain,
        artifacts=args.artifact,
        reviewed_item_ids=args.item_id,
        source_map_value=load_json(args.source_map) if args.source_map else None,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "review_draft": str(args.out.expanduser().resolve()),
        "artifacts": packet["artifacts"],
        "automated_findings": packet["automated_findings"],
        "required_action": "A distinct reviewer must complete every applicable check and set the verdict.",
    })
    return 0


def review_check_command(args: argparse.Namespace) -> int:
    packet = assurance.build_review(
        ROOT,
        load_json(args.state),
        load_json(args.input),
        source_map_value=load_json(args.source_map) if args.source_map else None,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "review": str(args.out.expanduser().resolve()),
        "review_id": packet["review_id"],
        "verdict": packet["verdict"],
        "payload_sha256": packet["payload_sha256"],
        "status_authority": False,
    })
    return 0


def campaign_audit_command(args: argparse.Namespace) -> int:
    packet = assurance.campaign_audit(
        ROOT,
        load_json(args.state),
        task_dir=args.task_dir,
        report_id=args.report_id,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet)
    return 0 if packet["disposition"] != "BLOCKED" else 1


def legacy_audit_command(args: argparse.Namespace) -> int:
    packet = assurance.legacy_audit(
        ROOT,
        load_json(args.input),
        report_id=args.report_id,
        target_sha256=args.target_sha256,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet)
    return 1


def finalize_command(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    task = assurance.task_directory(state)
    for destination in (args.out, args.result_out):
        resolved = destination.expanduser().resolve()
        try:
            resolved.relative_to(task)
        except ValueError as exc:
            raise assurance.AssuranceError(
                "finalization outputs must remain inside the bound task directory"
            ) from exc
    packet = assurance.build_finalization(
        ROOT,
        state,
        finalization_id=args.finalization_id,
        artifacts=args.artifact,
        review_paths=args.review,
    )
    atomic_write_json(args.out, packet)
    atomic_write_text(args.result_out, assurance.render_result(state, packet))
    emit({
        "ok": True,
        "finalization": str(args.out.expanduser().resolve()),
        "result": str(args.result_out.expanduser().resolve()),
        "terminal_action": packet["terminal_action"],
        "assurance_level": packet["assurance_level"],
        "payload_sha256": packet["payload_sha256"],
        "next_command": f"orchestrator-next --state {args.state} --finalization {args.out}",
    })
    return 0


def orchestrator_handoff_command(args: argparse.Namespace) -> int:
    workspace = args.workspace_root.expanduser().resolve()
    task = args.task_dir.expanduser()
    if not task.is_absolute():
        task = workspace / task

    def task_path(path: Path) -> Path:
        return path if path.is_absolute() else task / path

    packet, draft, state_snapshot = orchestration.build_handoff(
        ROOT,
        load_json(args.state),
        load_json(args.episode),
        workspace_root=workspace,
        task_dir=task,
        handoff_path=task_path(args.out),
        state_snapshot_path=task_path(args.state_out),
        draft_path=task_path(args.draft_out),
        delta_path=task_path(args.delta_out),
        context_budget=args.budget,
        source_map_value=load_json(args.source_map) if args.source_map else None,
    )
    handoff_path = task_path(args.out)
    state_path = task_path(args.state_out)
    draft_path = task_path(args.draft_out)
    atomic_write_json(handoff_path, packet)
    atomic_write_json(draft_path, draft)
    atomic_write_json(state_path, state_snapshot)
    binding = packet["domain_binding"]
    emit({
        "ok": True,
        "status": "BOUND_HANDOFF_READY",
        "handoff": str(handoff_path.expanduser().resolve()),
        "handoff_sha256": packet["payload_sha256"],
        "draft": str(draft_path.expanduser().resolve()),
        "state_snapshot": str(state_path),
        "delta": packet["return_contract"]["required_path"],
        "domain_binding": {
            "domains": binding["domains"],
            "capability_mode": binding["capability_mode"],
            "capabilities": binding["capabilities"],
            "episode_operators": binding["episode_operators"],
            "packages": binding["packages"],
            "skill_view_argv": binding["skill_view_argv"],
            "payload_sha256": binding["payload_sha256"],
            "load_required": True,
        },
            "reasoning_contract": {
                "schema": packet["reasoning_contract"]["schema"],
                "payload_sha256": packet["reasoning_contract"]["payload_sha256"],
                "max_claims": packet["reasoning_contract"]["limits"]["max_claims"],
                "max_hypotheses": packet["reasoning_contract"]["limits"]["max_hypotheses"],
                "max_subgoals": packet["reasoning_contract"]["limits"]["max_subgoals"],
                "authorization_sha256": packet["reasoning_contract"]["authorization"]["payload_sha256"],
                "required": True,
        },
        "source_map_sha256": (
            packet["source_map"]["payload_sha256"]
            if packet["source_map"] is not None else None
        ),
        "worker_launch_allowed": False,
        "next_command": f"orchestrator-next --state {args.state} --handoff {handoff_path}",
    })
    return 0


def orchestrator_round_handoffs_command(args: argparse.Namespace) -> int:
    results = orchestration.build_round_handoffs(
        ROOT,
        load_json(args.state),
        load_json(args.round),
        workspace_root=args.workspace_root,
        task_dir=args.task_dir,
        output_dir=args.out_dir,
        context_budget=args.budget,
        source_map_value=load_json(args.source_map) if args.source_map else None,
    )
    handoffs: list[dict[str, Any]] = []
    state_path_for_gate = str(args.state.expanduser().resolve())
    for item in results:
        worker_dir = item["worker_dir"]
        handoff_path = worker_dir / "researcher-handoff.json"
        draft_path = worker_dir / "research-delta.draft.json"
        state_path = worker_dir / "researcher-state.json"
        atomic_write_json(handoff_path, item["handoff"])
        atomic_write_json(draft_path, item["draft"])
        atomic_write_json(state_path, item["state_snapshot"])
        binding = item["handoff"]["domain_binding"]
        handoffs.append({
            "episode_id": item["episode_id"],
            "actor_id": item["actor_id"],
            "failure_domain": item["failure_domain"],
            "handoff": str(handoff_path),
            "draft": str(draft_path),
            "state_snapshot": str(state_path),
            "delta": item["handoff"]["return_contract"]["required_path"],
            "domain_binding": {
                "domains": binding["domains"],
                "capability_mode": binding["capability_mode"],
                "capabilities": binding["capabilities"],
                "episode_operators": binding["episode_operators"],
                "packages": binding["packages"],
                "skill_view_argv": binding["skill_view_argv"],
                "payload_sha256": binding["payload_sha256"],
                "load_required": True,
            },
            "reasoning_contract": {
                "schema": item["handoff"]["reasoning_contract"]["schema"],
                "payload_sha256": item["handoff"]["reasoning_contract"]["payload_sha256"],
                "max_claims": item["handoff"]["reasoning_contract"]["limits"]["max_claims"],
                "max_hypotheses": item["handoff"]["reasoning_contract"]["limits"]["max_hypotheses"],
                "max_subgoals": item["handoff"]["reasoning_contract"]["limits"]["max_subgoals"],
                "authorization_sha256": item["handoff"]["reasoning_contract"]["authorization"]["payload_sha256"],
                "required": True,
            },
            "source_map_sha256": (
                item["handoff"]["source_map"]["payload_sha256"]
                if item["handoff"]["source_map"] is not None else None
            ),
            "worker_launch_allowed": False,
            "gate_argv": [
                "bash", "$WITSOC", "orchestrator-next",
                "--state", state_path_for_gate, "--handoff", str(handoff_path),
            ],
        })
    emit({
        "ok": True,
        "status": "BOUND_ROUND_HANDOFFS_READY",
        "round": str(args.round),
        "handoffs": handoffs,
        "worker_launch_allowed": False,
        "required_action": "Run each gate_argv and launch only an argv it authorizes.",
    })
    return 0


def delta_build_command(args: argparse.Namespace) -> int:
    packet = orchestration.build_delta(
        load_json(args.state),
        load_json(args.draft),
        load_json(args.handoff) if args.handoff else None,
    )
    atomic_write_json(args.out, packet)
    result = {
        "ok": True,
        "status": "BOUND_DELTA_READY",
        "delta": str(args.out.expanduser().resolve()),
        "delta_sha256": packet["payload_sha256"],
        "episode_id": packet["episode_id"],
        "outcome": packet["outcome"],
        "successor_dispatch_allowed": False,
        "return_to": "EXPLORER",
    }
    if packet["schema"] == discovery.DELTA_SCHEMA:
        result["reasoning"] = reasoning.summary(packet["reasoning"])
        result["return_message"] = {
            "message_type": packet["messages"][0]["message_type"],
            "payload_sha256": packet["messages"][0]["payload_sha256"],
            "recipient": packet["messages"][0]["recipient"],
        }
    emit(result)
    return 0


def reasoning_check_command(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    handoff = orchestration.validate_handoff(load_json(args.handoff), state)
    contract = handoff.get("reasoning_contract")
    if contract is None:
        raise reasoning.ReasoningError("legacy handoff has no reasoning contract")
    value = load_json(args.input)
    if value.get("schema") == reasoning.DRAFT_SCHEMA:
        packet = reasoning.build_state(
            ROOT,
            value,
            contract,
            expected_outcome=value.get("requested_outcome", ""),
        )
    else:
        packet = reasoning.validate_state(
            ROOT,
            value,
            contract,
            expected_outcome=args.expected_outcome,
            final=True,
        )
    if args.out:
        atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "out": str(args.out.expanduser().resolve()) if args.out else None,
        "summary": reasoning.summary(packet),
    })
    return 0


def explorer_decide_command(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    if state.get("mode") == "OPEN_DISCOVERY":
        raise exploration.ExplorationError(
            "OPEN_DISCOVERY decisions require explorer-draft plus explorer-check; "
            "dispatch with episode-issue or record a non-dispatch decision with explorer-arbitrate"
        )
    updated = orchestration.record_decision(
        state,
        decision_id=args.decision_id,
        action=args.action,
        basis_refs=args.basis_ref,
        alternatives=args.alternative,
        changed_axis=args.changed_axis,
    )
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    stage = orchestration.next_action(updated)
    emit({
        "ok": True,
        "action": args.action,
        "revision": updated["revision"],
        "state_sha256": updated["state_sha256"],
        "written": str(destination) if destination else None,
        "completion_allowed": stage["completion_allowed"],
        "next_stage": stage["stage"],
    })
    return 0


def explorer_draft_command(args: argparse.Namespace) -> int:
    proposals = _array_file(args.proposals, "proposals") if args.proposals else []
    draft, prepared = exploration.draft(
        ROOT,
        load_json(args.state),
        proposals,
        load_json(args.prior_explorer) if args.prior_explorer else None,
    )
    atomic_write_json(args.out, draft)
    if args.proposals_out:
        atomic_write_json(args.proposals_out, prepared)
    emit({
        "ok": True,
        "draft": str(args.out.expanduser().resolve()),
        "prepared_proposals": (
            str(args.proposals_out.expanduser().resolve()) if args.proposals_out else None
        ),
        "phase": draft["phase"],
        "frontier_nodes": len(draft["frontier_model"]["nodes"]),
        "proposals": len(prepared),
    })
    return 0


def source_map_draft_command(args: argparse.Namespace) -> int:
    packet = exploration.source_map_draft(
        load_json(args.state),
        source_map_id=args.source_map_id,
        checked_at=args.checked_at,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "source_map_draft": str(args.out.expanduser().resolve()),
        "target_sha256": packet["target_sha256"],
    })
    return 0


def source_map_check_command(args: argparse.Namespace) -> int:
    packet = exploration.build_source_map(
        ROOT, load_json(args.state), load_json(args.input)
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "source_map": str(args.out.expanduser().resolve()),
        "entries": len(packet["entries"]),
        "unresolved": len(packet["unresolved"]),
        "payload_sha256": packet["payload_sha256"],
        "status_authority": False,
    })
    return 0


def explorer_proposal_draft_command(args: argparse.Namespace) -> int:
    draft = exploration.proposal_draft(
        load_json(args.state),
        proposal_id=args.proposal_id,
        node_id=args.node_id,
        lane=args.lane,
    )
    atomic_write_json(args.out, draft)
    emit({
        "ok": True,
        "proposal_draft": str(args.out.expanduser().resolve()),
        "proposal_id": draft["proposal_id"],
        "node_id": draft["node_id"],
        "lane": draft["lane"],
    })
    return 0


def explorer_proposal_check_command(args: argparse.Namespace) -> int:
    packet = exploration.build_proposal(
        ROOT, load_json(args.state), load_json(args.input)
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "proposal": str(args.out.expanduser().resolve()),
        "proposal_id": packet["proposal_id"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0


def explorer_check_command(args: argparse.Namespace) -> int:
    proposals = _array_file(args.proposals, "proposals") if args.proposals else []
    packet, prepared = exploration.build_state(
        ROOT,
        load_json(args.state),
        load_json(args.input),
        proposals,
        load_json(args.source_map) if args.source_map else None,
        load_json(args.stop_review) if args.stop_review else None,
    )
    atomic_write_json(args.out, packet)
    if args.proposals_out:
        atomic_write_json(args.proposals_out, prepared)
    emit({
        "ok": True,
        "explorer_state": str(args.out.expanduser().resolve()),
        "prepared_proposals": (
            str(args.proposals_out.expanduser().resolve()) if args.proposals_out else None
        ),
        "summary": exploration.summary(packet),
    })
    return 0


def explorer_stop_review_draft_command(args: argparse.Namespace) -> int:
    proposals = _array_file(args.proposals, "proposals") if args.proposals else []
    packet = exploration.stop_review_draft(
        ROOT,
        load_json(args.state),
        load_json(args.explorer_draft),
        proposals,
        load_json(args.source_map),
        report_id=args.report_id,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "stop_review_draft": str(args.out.expanduser().resolve()),
        "stop_case_sha256": packet["body"]["stop_case_sha256"],
        "independent_review_required": True,
    })
    return 0


def explorer_stop_review_check_command(args: argparse.Namespace) -> int:
    proposals = _array_file(args.proposals, "proposals") if args.proposals else []
    packet = exploration.build_stop_review(
        ROOT,
        load_json(args.state),
        load_json(args.explorer_draft),
        proposals,
        load_json(args.source_map),
        load_json(args.input),
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "stop_review": str(args.out.expanduser().resolve()),
        "conclusion": packet["body"]["conclusion"],
        "payload_sha256": packet["payload_sha256"],
        "status_authority": False,
    })
    return 0


def explorer_arbitrate_command(args: argparse.Namespace) -> int:
    state = load_json(args.state)
    proposals = _array_file(args.proposals, "proposals") if args.proposals else []
    packet, _prepared = exploration.build_arbitration(
        ROOT,
        state,
        load_json(args.explorer_state),
        proposals,
        load_json(args.source_map) if args.source_map else None,
        load_json(args.stop_review) if args.stop_review else None,
    )
    if packet["action"] in exploration.DISPATCH_ACTIONS:
        raise exploration.ExplorationError(
            "dispatch arbitration must be recorded atomically by episode-issue or round-issue"
        )
    updated = exploration.apply_arbitration(ROOT, state, packet)
    atomic_write_json(args.arbitration_out, packet)
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    stage = orchestration.next_action(updated)
    emit({
        "ok": True,
        "action": packet["action"],
        "arbitration": str(args.arbitration_out.expanduser().resolve()),
        "state": str(destination) if destination else None,
        "revision": updated["revision"],
        "state_sha256": updated["state_sha256"],
        "completion_allowed": stage["completion_allowed"],
        "next_stage": stage["stage"],
    })
    return 0


OPEN_EXPLORER_CONTROLLED_KINDS = {
    "ARBITRATION_RECORDED", "DECISION_RECORD", "EPISODE_ISSUED",
    "EPISODE_RETURNED", "ROUND_ISSUED", "ROUND_RETURNED",
    "FRONTIER_ADD", "FRONTIER_LINK", "OBSTRUCTION_RECORD",
}


def _refuse_raw_open_lifecycle(state: Mapping[str, Any], kind: str) -> None:
    if state.get("mode") == "OPEN_DISCOVERY" and kind in OPEN_EXPLORER_CONTROLLED_KINDS:
        raise kernel.KernelError(
            f"raw {kind} is refused in OPEN_DISCOVERY; use the typed Explorer/episode/round command"
        )


def event_command(args: argparse.Namespace) -> int:
    state = kernel.validate_state(load_json(args.state))
    _refuse_raw_open_lifecycle(state, args.kind)
    payload = load_json(args.payload)
    event = kernel.build_event(state, args.kind, payload, args.event_id)
    atomic_write_json(args.out, event)
    emit(event)
    return 0


def step_command(args: argparse.Namespace) -> int:
    state = kernel.validate_state(load_json(args.state))
    event = load_json(args.event)
    if event.get("kind") == "ADMISSION_IMPORTED":
        raise kernel.KernelError("raw admission events are refused; use import-admission")
    _refuse_raw_open_lifecycle(state, event.get("kind", ""))
    updated = kernel.apply_event(state, event)
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({"ok": True, "revision": updated["revision"], "state_sha256": updated["state_sha256"],
          "written": str(destination) if destination else None})
    return 0


def inspect_command(args: argparse.Namespace) -> int:
    emit(kernel.inspect_state(load_json(args.state)))
    return 0


def replay_command(args: argparse.Namespace) -> int:
    report = kernel.replay_report(load_json(args.state))
    emit(report)
    return 0 if report["ok"] else 1


def state_index_command(args: argparse.Namespace) -> int:
    packet = kernel.state_index(ROOT, load_json(args.state), report_id=args.report_id)
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {
        "ok": True,
        "out": str(args.out),
        "revision": packet["body"]["revision"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0


def state_compact_command(args: argparse.Namespace) -> int:
    packet = kernel.compact_checkpoint(
        ROOT,
        load_json(args.state),
        report_id=args.report_id,
        block_size=args.block_size,
        tail_events=args.tail_events,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "out": str(args.out),
        "revision": packet["body"]["revision"],
        "event_blocks": len(packet["body"]["event_blocks"]),
        "payload_sha256": packet["payload_sha256"],
    })
    return 0


def import_admission_command(args: argparse.Namespace) -> int:
    state = kernel.validate_state(load_json(args.state))
    updated, admission_packet = projections.apply_frame_admission(
        ROOT,
        state,
        load_json(args.frame_state),
        args.claim_id,
        args.item_id,
        args.event_id or f"admission:{args.claim_id}:{state['revision']}",
    )
    if args.admission_out:
        atomic_write_json(args.admission_out, admission_packet)
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({"ok": True, "status": updated["status"], "revision": updated["revision"],
          "admission": str(args.admission_out) if args.admission_out else admission_packet,
          "state_sha256": updated["state_sha256"], "written": str(destination) if destination else None})
    return 0


def migrate_frame_command(args: argparse.Namespace) -> int:
    state = migrations.from_frame_state(
        load_json(args.frame_state), domain=args.domain, mode=args.mode
    )
    atomic_write_json(args.out, state)
    emit({
        "ok": True,
        "out": str(args.out.expanduser().resolve()),
        "revision": state["revision"],
        "claims": len(state["frontier"]["items"]),
        "state_sha256": state["state_sha256"],
    })
    return 0


def episode_plan_command(args: argparse.Namespace) -> int:
    result = discovery.plan_portfolio(
        load_json(args.state), load_json(args.proposals), args.portfolio_exception
    )
    emit(result)
    return 0 if result["dispatchable"] else 1


def episode_issue_command(args: argparse.Namespace) -> int:
    updated, episode = discovery.issue_best(
        load_json(args.state),
        load_json(args.proposals),
        args.episode_id,
        args.portfolio_exception,
        load_json(args.explorer_state) if args.explorer_state else None,
        load_json(args.source_map) if args.source_map else None,
    )
    atomic_write_json(args.episode_out, episode)
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({"ok": True, "episode": str(args.episode_out), "state": str(destination) if destination else None,
          "revision": updated["revision"], "state_sha256": updated["state_sha256"]})
    return 0


def episode_return_command(args: argparse.Namespace) -> int:
    updated = discovery.apply_delta(load_json(args.state), load_json(args.delta))
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({"ok": True, "state": str(destination) if destination else None,
          "revision": updated["revision"], "outcome": updated["outcome"],
          "state_sha256": updated["state_sha256"]})
    return 0


def novelty_audit_command(args: argparse.Namespace) -> int:
    packet = discovery.novelty_audit(
        ROOT,
        load_json(args.candidate),
        load_json(args.source_map),
        _array_file(args.comparisons, "comparisons"),
        report_id=args.report_id,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {
        "ok": packet["disposition"] == "READY",
        "out": str(args.out),
        "novelty_status": packet["body"]["novelty_status"],
        "disposition": packet["disposition"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0 if packet["disposition"] == "READY" else 3


def _array_file(path: Path, key: str) -> list[dict[str, Any]]:
    value = load_json(path)
    if isinstance(value, dict):
        value = value.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{path} must contain an array of objects or an object with {key!r}")
    return value


def round_plan_command(args: argparse.Namespace) -> int:
    packet = rounds.build_round(
        ROOT,
        load_json(args.state),
        _array_file(args.specifications, "specifications"),
        round_id=args.round_id,
        rationale=args.rationale,
        merge_policy=args.merge_policy,
        max_parallel=args.max_parallel,
    )
    emit(packet)
    return 0


def round_independence_command(args: argparse.Namespace) -> int:
    state = kernel.validate_state(load_json(args.state))
    packet = rounds.independence_audit(
        ROOT,
        state,
        _array_file(args.specifications, "specifications"),
        report_id=args.report_id,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {
        "ok": packet["disposition"] == "READY",
        "out": str(args.out),
        "grade": packet["body"]["grade"],
        "admission_eligible": packet["body"]["admission_eligible"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0 if packet["disposition"] == "READY" else 3


def round_issue_command(args: argparse.Namespace) -> int:
    updated, packet = rounds.issue_round(
        ROOT,
        load_json(args.state),
        _array_file(args.specifications, "specifications"),
        round_id=args.round_id,
        rationale=args.rationale,
        merge_policy=args.merge_policy,
        max_parallel=args.max_parallel,
        explorer_state_value=(
            load_json(args.explorer_state) if args.explorer_state else None
        ),
        source_map_value=load_json(args.source_map) if args.source_map else None,
    )
    atomic_write_json(args.round_out, packet)
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({
        "ok": True,
        "round": str(args.round_out),
        "episodes": len(packet["episodes"]),
        "state": str(destination) if destination else None,
        "revision": updated["revision"],
        "state_sha256": updated["state_sha256"],
    })
    return 0


def round_merge_command(args: argparse.Namespace) -> int:
    packet = rounds.build_delta(
        ROOT,
        load_json(args.state),
        load_json(args.round),
        _array_file(args.deltas, "deltas"),
        round_delta_id=args.round_delta_id,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": packet["aggregate_outcome"] != "CONFLICT",
        "out": str(args.out),
        "aggregate_outcome": packet["aggregate_outcome"],
        "conflicts": packet["conflicts"],
    })
    return 0 if packet["aggregate_outcome"] != "CONFLICT" else 1


def round_return_command(args: argparse.Namespace) -> int:
    updated = rounds.apply_delta(ROOT, load_json(args.state), load_json(args.round_delta))
    destination = write_state(args.state, updated, write=args.write, out=args.out)
    emit({
        "ok": True,
        "state": str(destination) if destination else None,
        "revision": updated["revision"],
        "outcome": updated["outcome"],
        "state_sha256": updated["state_sha256"],
    })
    return 0


def capabilities_command(args: argparse.Namespace) -> int:
    if args.statement:
        routed = modes.route(ROOT, args.statement, args.intent, args.domain, args.role)
        result = capabilities.build_load_plan(
            ROOT,
            routed["mode"],
            routed["domains"],
            args.role,
            args.statement,
            goal_type=args.goal_type,
            available_types=args.available_type,
            required_capabilities=args.capability,
        )
    else:
        result = {
            "schema": "witsoc.capability-catalog.v1",
            "capabilities": [
                {key: item[key] for key in ("owner", "id", "summary", "modes", "roles", "cost_class")}
                for item in capabilities.all_capabilities(ROOT)
            ],
        }
    emit(result)
    return 0 if result.get("ok", True) else 1


def capability_graph_command(args: argparse.Namespace) -> int:
    graph = capability_graph.compile_graph(ROOT, [args.domain] if args.domain else None)
    if args.full:
        emit(graph)
    else:
        emit({
            "schema": graph["schema"],
            "version": graph["version"],
            "nodes": len(graph["nodes"]),
            "edges": graph["edge_count"],
            "packet_types": len(graph["packet_types"]),
            "admission_authority": graph["admission_authority"],
            "capabilities": [item["id"] for item in graph["nodes"]],
            "ok": graph["ok"],
        })
    return 0


def contracts_command(args: argparse.Namespace) -> int:
    if args.packet:
        if not args.type:
            raise contracts.ContractError("--packet requires --type")
        result = contracts.validate_packet(ROOT, args.type, load_json(args.packet))
        emit({"ok": True, "type": args.type, "payload_sha256": result.get("payload_sha256")})
    elif args.type:
        emit(contracts.resolve_type(ROOT, args.type))
    else:
        emit(contracts.registry_report(ROOT))
    return 0


def project_command(args: argparse.Namespace) -> int:
    packet = projections.state_view(ROOT, load_json(args.state), args.view)
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {"ok": True, "out": str(args.out), "payload_sha256": packet["payload_sha256"]})
    return 0


def capsule_command(args: argparse.Namespace) -> int:
    packet = capsules.build(
        ROOT,
        load_json(args.state),
        role=args.role,
        statement=args.statement,
        context_budget=args.budget,
        capsule_id=args.capsule_id,
        source_map=load_json(args.source_map) if args.source_map else None,
    )
    atomic_write_json(args.out, packet)
    emit({"ok": True, "out": str(args.out), **capsules.inspect(packet)})
    return 0


def bridge_negotiate_command(args: argparse.Namespace) -> int:
    result = bridges.negotiate(ROOT, args.source, args.destination)
    emit(result)
    return 0 if result["ok"] else 1


def bridge_build_command(args: argparse.Namespace) -> int:
    packet = bridges.build_envelope(
        ROOT, args.envelope_id, args.source, args.destination, args.message_type,
        args.target_sha256, args.correlation_id, load_json(args.payload), args.evidence_ref,
        args.causation_id,
    )
    atomic_write_json(args.out, packet)
    emit(packet)
    return 0


def bridge_negotiate_v2_command(args: argparse.Namespace) -> int:
    result = bridges.negotiate_v2(ROOT, args.source, args.destination)
    emit(result)
    return 0 if result["ok"] else 1


def bridge_plan_v2_command(args: argparse.Namespace) -> int:
    packet = bridges.plan_v2(
        ROOT,
        args.source,
        args.destination,
        max_hops=args.max_hops,
        max_loss_units=args.max_loss_units,
        limit=args.limit,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {
        "ok": packet["disposition"] == "READY",
        "out": str(args.out),
        "paths": len(packet["body"]["paths"]),
        "payload_sha256": packet["payload_sha256"],
    })
    return 0 if packet["disposition"] == "READY" else 3


def bridge_translate_v2_command(args: argparse.Namespace) -> int:
    packet = bridges.translate_v2(
        ROOT,
        args.source,
        args.destination,
        args.adapter_id,
        load_json(args.source_packet),
        transfer_id=args.transfer_id,
        scope=load_json(args.scope),
        evidence_refs=args.evidence_ref,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "out": str(args.out),
        "message_type": packet["schema"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0


def bridge_build_v2_command(args: argparse.Namespace) -> int:
    packet = bridges.build_envelope_v2(
        ROOT,
        args.envelope_id,
        args.source,
        args.destination,
        args.adapter_id,
        args.source_message_type,
        args.message_type,
        args.target_sha256,
        args.correlation_id,
        load_json(args.source_packet),
        load_json(args.payload),
        scope_owner=args.scope_owner,
        preserved_invariants=args.preserve,
        losses=args.loss,
        evidence_refs=args.evidence_ref,
        conflict_refs=args.conflict_ref,
        causation_id=args.causation_id,
    )
    atomic_write_json(args.out, packet)
    emit({
        "ok": True,
        "out": str(args.out),
        "adapter_id": packet["adapter_id"],
        "message_type": packet["message_type"],
        "losses": packet["losses"],
        "payload_sha256": packet["payload_sha256"],
    })
    return 0


def bridge_compose_v2_command(args: argparse.Namespace) -> int:
    result = bridges.compose_v2(
        ROOT,
        [load_json(path) for path in args.envelope],
        max_losses=args.max_losses,
    )
    if args.out:
        atomic_write_json(args.out, result)
    emit(result if not args.out else {"out": str(args.out), **result})
    return 0 if result["ok"] else 3


def bridge_graph_v2_command(args: argparse.Namespace) -> int:
    packet = bridges.compose_graph_v2(
        ROOT,
        [load_json(path) for path in args.envelope],
        max_loss_units=args.max_loss_units,
        report_id=args.report_id,
    )
    if args.out:
        atomic_write_json(args.out, packet)
    emit(packet if not args.out else {
        "ok": packet["disposition"] == "READY",
        "out": str(args.out),
        "branches": len(packet["body"]["branches"]),
        "joins": len(packet["body"]["join_requirements"]),
        "payload_sha256": packet["payload_sha256"],
    })
    return 0 if packet["disposition"] == "READY" else 3


def memory_put_command(args: argparse.Namespace) -> int:
    entry = evidence_memory.put(args.store, load_json(args.entry))
    emit(entry)
    return 0


def memory_query_command(args: argparse.Namespace) -> int:
    result = evidence_memory.query(
        args.store,
        target_sha256=args.target_sha256,
        domain=args.domain,
        scope=load_json(args.scope) if args.scope else None,
        tags=args.tag,
        reusable_only=not args.all,
        include_invalidated=args.include_invalidated,
    )
    emit({"entries": result, "count": len(result)})
    return 0


def memory_compact_command(args: argparse.Namespace) -> int:
    emit(evidence_memory.compact_query(
        args.store,
        target_sha256=args.target_sha256,
        domain=args.domain,
        scope=load_json(args.scope),
        tags=args.tag,
        max_bytes=args.max_bytes,
    ))
    return 0


def memory_invalidate_command(args: argparse.Namespace) -> int:
    emit(evidence_memory.invalidate(args.store, args.entry_id, args.reason, args.evidence_ref))
    return 0


def hint_build_command(args: argparse.Namespace) -> int:
    packet = hint_memory.make_hint(
        ROOT,
        domain=args.domain,
        features=load_json(args.features),
        content=load_json(args.content),
        scope=load_json(args.scope) if args.scope else {},
        provenance_refs=args.provenance_ref,
        created_at=args.created_at,
    )
    atomic_write_json(args.out, packet)
    emit({"ok": True, "out": str(args.out), "hint_id": packet["hint_id"]})
    return 0


def hint_put_command(args: argparse.Namespace) -> int:
    packet = hint_memory.put(
        ROOT,
        args.store,
        load_json(args.hint),
        depends_on=args.depends_on,
    )
    emit({"ok": True, "hint_id": packet["hint_id"], "non_evidentiary": True})
    return 0


def hint_query_command(args: argparse.Namespace) -> int:
    emit(hint_memory.query(
        ROOT,
        args.store,
        domain=args.domain,
        features=load_json(args.features),
        scope=load_json(args.scope) if args.scope else {},
        min_score=args.min_score,
        limit=args.limit,
        include_invalidated=args.include_invalidated,
    ))
    return 0


def hint_invalidate_command(args: argparse.Namespace) -> int:
    emit(hint_memory.invalidate(
        ROOT, args.store, args.hint_id, args.reason, args.provenance_ref
    ))
    return 0


def doctor(root: Path = ROOT, state_path: Path | None = None) -> dict[str, Any]:
    problems: list[str] = []
    facts: dict[str, Any] = {}
    architecture_path = root / "references" / "runtime_architecture.json"
    try:
        architecture = load_json(architecture_path)
        if architecture.get("schema") != "witsoc.runtime-architecture.v1":
            problems.append("runtime architecture schema is invalid")
        if architecture.get("version") != 11:
            problems.append("runtime architecture version is not 11")
        for layer in architecture.get("layers", []):
            for pattern in layer.get("paths", []):
                if "*" in pattern:
                    if not list(root.glob(pattern)) and not pattern.startswith("domains/"):
                        problems.append(f"architecture path pattern matches nothing: {pattern}")
                elif not (root / pattern).exists():
                    problems.append(f"architecture path is missing: {pattern}")
        facts["architecture_layers"] = len(architecture.get("layers", []))
        facts["architecture_version"] = architecture.get("version")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"cannot read runtime architecture: {exc}")
    try:
        graph = capability_graph.compile_graph(root)
        facts["capabilities"] = len(graph["nodes"])
        facts["capability_edges"] = graph["edge_count"]
        facts["capability_admission_authority"] = graph["admission_authority"]
    except (capabilities.CapabilityError, capability_graph.CapabilityGraphError) as exc:
        problems.append(str(exc))
    try:
        contract_report = contracts.registry_report(root)
        facts["packet_types"] = contract_report["type_count"]
        facts["status_authority"] = contract_report["status_authority"]
    except contracts.ContractError as exc:
        problems.append(str(exc))
    try:
        operator_counts: dict[str, int] = {}
        for manifest_path in sorted((root / "domains").glob("*/operators.json")):
            manifest = operators.load_manifest(root, manifest_path.parent.name)
            operator_counts[manifest["domain"]] = len(manifest["operators"])
        if not operator_counts:
            facts["operators_dormant"] = [
                item["domain"] for item in domain_packages.load_registry(root)["packages"]
            ]
        facts["operators"] = operator_counts
    except operators.OperatorError as exc:
        problems.append(str(exc))
    try:
        package_status = domain_packages.status(root, verify=False)
        facts["domain_packages"] = package_status["packages"]
        if not package_status["ok"]:
            problems.append("domain package cache or activation is invalid")
    except domain_packages.DomainPackageError as exc:
        problems.append(str(exc))
    try:
        generated = runtime_contracts.check(root)
        if not generated["ok"]:
            problems.extend(generated["problems"])
        facts["runtime_contract"] = {
            key: generated[key]
            for key in (
                "content_sha256", "architecture_version", "capabilities",
                "operators", "maximum_load_plan_tokens",
            )
        }
    except runtime_contracts.RuntimeContractError as exc:
        problems.append(str(exc))
    for relative in (
        "schemas/research-kernel-v1.schema.json",
        "schemas/research-discovery-proposal-v2.schema.json",
        "schemas/research-explorer-contract-v1.schema.json",
        "schemas/research-explorer-state-v1.schema.json",
        "schemas/research-explorer-arbitration-v1.schema.json",
        "schemas/research-episode-v1.schema.json",
        "schemas/research-delta-v1.schema.json",
        "schemas/research-round-v1.schema.json",
        "schemas/research-capsule-v1.schema.json",
        "schemas/bridge-envelope-v2.schema.json",
        "schemas/memory-entry-v1.schema.json",
        "schemas/memory-hint-v1.schema.json",
        "schemas/operator-plan-v1.schema.json",
    ):
        if not (root / relative).is_file():
            problems.append(f"missing runtime schema: {relative}")
    if state_path:
        try:
            report = kernel.replay_report(load_json(state_path))
            if not report["ok"]:
                problems.append(report["problem"])
            facts["state"] = report
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"cannot read kernel state: {exc}")
    return {"ok": not problems, "problems": problems, "facts": facts}


def doctor_command(args: argparse.Namespace) -> int:
    result = doctor(ROOT, args.state)
    emit(result)
    return 0 if result["ok"] else 1


def self_test(root: Path = ROOT) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    registry = domain_packages.load_registry(root)
    required_domains = {item["domain"] for item in registry["packages"]}
    installed_domains = {
        path.parent.name for path in (root / "domains").glob("*/capabilities.json")
    }
    full_profile = (
        required_domains <= installed_domains
        and (root / "scripts" / "witsoc_core" / "advanced_selftest.py").is_file()
    )

    def check(name: str, condition: bool) -> None:
        cases.append({"name": name, "ok": bool(condition)})

    def refuses(name: str, expected: type[Exception], action: Any, phrase: str = "") -> None:
        try:
            action()
        except expected as exc:
            check(name, not phrase or phrase in str(exc))
        else:
            check(name, False)

    def synthetic_source_map(current: Mapping[str, Any]) -> dict[str, Any]:
        receipt_sha = digest_value({
            "kind": "synthetic-retrieval-receipt",
            "state": current["state_sha256"],
        })
        return seal_packet({
            "schema": exploration.SOURCE_MAP_SCHEMA,
            "source_map_id": f"synthetic:{current['state_sha256'][:16]}",
            "target_sha256": current["target"]["canonical_sha256"],
            "entries": [{
                "source_id": "SYNTHETIC-SEARCH",
                "source_type": "SEARCH_RECEIPT",
                "locator": "synthetic:bounded-corpus",
                "retrieved_sha256": receipt_sha,
                "claim_supported": "The named synthetic corpus was checked within scope.",
                "status": "OPEN",
                "preconditions": ["synthetic fixture only"],
                "reliability": "UNKNOWN",
            }],
            "contradictions": [],
            "unresolved": ["external literature is outside this synthetic test"],
            "checked_at": "2026-01-01T00:00:00+00:00",
        })

    def explorer_authorization(
        current: Mapping[str, Any],
        candidate_proposals: list[Mapping[str, Any]],
        selected_id: str,
        *,
        action: str = "WORK_ITEM_TO_RESEARCHER",
    ) -> dict[str, Any]:
        worksheet, _prepared = exploration.draft(root, current, candidate_proposals)
        for domain, controls in worksheet["target_model"]["domain_controls"].items():
            worksheet["target_model"]["domain_controls"][domain] = {
                key: (
                    "SEPARATE" if key == "finite_vs_general"
                    else f"synthetic {key.replace('_', ' ')} recorded"
                )
                for key in controls
            }
        source_map = synthetic_source_map(current)
        source_ref = source_map["payload_sha256"]
        worksheet["source_coverage"] = {
            "status": "PARTIAL",
            "source_map_ref": source_ref,
            "queries": [{
                "query_id": "synthetic-query",
                "question": "exact synthetic target and nearest variants",
                "corpus": "sealed synthetic fixture",
                "checked_at": "2026-01-01T00:00:00+00:00",
                "result": "NOT_FOUND_WITHIN_SCOPE",
                "evidence_refs": ["SYNTHETIC-SEARCH"],
            }],
            "unavailable_refs": [],
            "correction_refs": [],
            "unresolved": ["external literature is outside this synthetic test"],
            "absence_claim_prohibited": True,
        }
        worksheet["decision"] = {
            "action": action,
            "selected_proposal_id": selected_id,
            "basis_refs": [current["state_sha256"], source_ref],
            "alternatives": ["retain the next Pareto-distinct route"],
            "changed_axis": "",
            "reason": "The selected route asks one bounded, decisive question.",
        }
        packet, _prepared = exploration.build_state(
            root, current, worksheet, candidate_proposals, source_map
        )
        return packet

    target = kernel.target_record("A frozen synthetic research target.", "exercise the runtime")
    state = kernel.new_state(target, "OPEN_DISCOVERY", ["maths"], created_at="2026-01-01T00:00:00+00:00")
    item = {
        "item_id": "CORE", "kind": "OPEN_CORE", "statement": "Resolve the exact synthetic core.",
        "target_sha256": target["canonical_sha256"],
        "status": "OPEN", "dependencies": [], "evidence_refs": [],
        "route_fingerprint": None, "admission_ref": None,
    }
    event = kernel.build_event(state, "FRONTIER_ADD", {"item": item, "activate": True}, "add:core")
    state = kernel.apply_event(state, event)
    check("kernel event changes one replayable revision", state["revision"] == 1 and kernel.replay_report(state)["ok"])
    foreign_item = {**item, "item_id": "FOREIGN", "target_sha256": "f" * 64}
    foreign_event = kernel.build_event(
        state, "FRONTIER_ADD", {"item": foreign_item, "activate": True}, "add:foreign"
    )
    refuses(
        "frontier additions cannot cross the frozen target",
        kernel.KernelError,
        lambda: kernel.apply_event(state, foreign_event),
        "frozen target",
    )

    base_route = {
        "mechanism": "separate the live alternatives", "structural_object": "synthetic core",
        "required_result": "strictly reduce the live set", "target_effect": "advance the target",
        "assumptions": [],
    }
    features = {
        "target_leverage": 0.9, "expected_information_gain": 0.8, "checkability": 0.8,
        "reversibility": 0.9, "novelty": 0.7, "transfer_value": 0.4,
        "cost": 0.2, "recoupling_risk": 0.1,
    }
    proposals = []
    route_axes = {
        "REFUTE": ("minimal counterexample family", "falsify one live alternative"),
        "REDUCE": ("synthetic open core", "derive a strictly smaller equivalent core"),
        "TRANSFER": ("isomorphic surrogate", "transport one exact discriminator"),
    }
    for index, lane in enumerate(("REFUTE", "REDUCE", "TRANSFER"), start=1):
        structural_object, required_result = route_axes[lane]
        proposals.append({
            "proposal_id": f"P{index}", "node_id": "CORE", "lane": lane,
            "route": {
                **base_route,
                "method_family": lane.casefold(),
                "structural_object": structural_object,
                "required_result": required_result,
            },
            "objective": f"exercise {lane.casefold()} lane", "evaluator": "one exact discriminator",
            "expected_delta": "a smaller synthetic frontier", "return_condition": "return after one decision",
            "changed_axis": "", "revival_evidence": "", "features": features,
        })
    one_lane = discovery.plan_portfolio(state, proposals[:1])
    check("one relabeled route cannot satisfy portfolio diversity", not one_lane["dispatchable"])
    plan = discovery.plan_portfolio(state, proposals)
    check(
        "portfolio requires distinct lanes, routes, and semantic cores",
        plan["dispatchable"]
        and len(plan["lane_coverage"]) == 3
        and plan["semantic_route_count"] == 3
        and plan["semantic_core_count"] == 3,
    )
    compiled_source = exploration.prepare_proposal(root, state, proposals[0])
    compiled_draft = copy.deepcopy(compiled_source)
    compiled_draft["schema"] = exploration.PROPOSAL_DRAFT_SCHEMA
    compiled_draft.pop("payload_sha256")
    recompiled = exploration.build_proposal(root, state, compiled_draft)
    check(
        "proposal worksheet compiles to stable proposal-v2 bytes",
        recompiled == compiled_source,
    )
    explorer_state = explorer_authorization(state, proposals, plan["selected_proposal_id"])
    state, episode = discovery.issue_best(
        state,
        proposals,
        "E1",
        explorer_state_value=explorer_state,
        source_map_value=synthetic_source_map(state),
    )
    check("bounded loop records one pending episode", state["pending_episode"]["episode_id"] == "E1")
    refuses(
        "bounded loop refuses a second pending episode",
        discovery.DiscoveryError,
        lambda: discovery.issue_best(state, proposals, "E2"),
        "pending episode",
    )
    delta = seal_packet({
        "schema": discovery.LEGACY_DELTA_SCHEMA, "delta_id": "D1", "episode_id": "E1",
        "episode_sha256": episode["payload_sha256"],
        "target_sha256": state["target"]["canonical_sha256"], "base_revision": state["revision"],
        "base_state_sha256": state["state_sha256"], "outcome": "NO_PROGRESS",
        "evidence_refs": [], "frontier_measure_before": 1, "frontier_measure_after": 1,
        "new_frontier": [],
        "new_obstruction": None,
        "admission_ref": None, "independent_review": None,
        "remaining_obstruction": "the alternatives remain coupled",
        "revival_condition": "a new exact discriminator becomes available",
        "next_proposals": [], "changed_axis": "",
    })
    tampered_delta = {**delta, "remaining_obstruction": "tampered after sealing"}
    refuses(
        "research delta rejects post-seal tampering",
        discovery.DiscoveryError,
        lambda: discovery.apply_delta(state, tampered_delta),
        "seal",
    )
    state = discovery.apply_delta(state, delta)
    check("return clears the episode without auto-dispatch", state["pending_episode"] is None and state["revision"] == 4)
    check("post-return state replays", kernel.replay_report(state)["ok"])
    attempted_proposal = next(
        item for item in proposals
        if item["proposal_id"] == episode["adjudication"]["selected_proposal_id"]
    )
    retained = discovery.plan_portfolio(state, [attempted_proposal], "single surviving lane")
    check(
        "NO_PROGRESS keeps the route unexhausted but forbids an unchanged retry",
        not retained["dispatchable"]
        and not state["route_attempts"][-1]["exhausted"]
        and any("stalled" in item["reason"] for item in retained["refused"]),
    )
    revived = {
        **attempted_proposal,
        "proposal_id": "P4",
        "changed_axis": "new exact discriminator",
        "revival_evidence": "sha256:" + "3" * 64,
    }
    check(
        "changed-axis evidence remains an explicit mutation record",
        discovery.plan_portfolio(state, [revived], "only one revived route is live")["dispatchable"],
    )

    frame = {
        "schema": "frame-state-v1", "target_sha256": target["canonical_sha256"],
        "revision": 0, "previous_state_sha256": None, "root_claim_id": "C0",
        "claims": {
            "C0": {
                "claim_id": "C0", "statement": target["statement"], "status": "OPEN",
                "target_sha256": target["canonical_sha256"], "dependency_mode": "LEAF",
                "dependencies": [], "evidence_refs": [],
            }
        },
        "active_obstruction": None, "open_gaps": [], "outcome": "OPEN", "history": [],
    }
    migrated = migrations.from_frame_state(
        frame, domain="maths", created_at="2026-01-01T00:00:00+00:00"
    )
    check("frame-state-v1 migrates into replayable kernel state", kernel.replay_report(migrated)["ok"])

    if full_profile:
        agreement = bridges.negotiate(root, "frame:target-control", "maths:source-status-map")
        check("bridge negotiation finds a declared type", "witsoc.target.v2" in agreement["compatible_types"])
        envelope = bridges.build_envelope(
            root, "B1", "frame:target-control", "maths:source-status-map", "witsoc.target.v2",
            target["canonical_sha256"], "C1", {"statement": target["statement"]},
        )
        check("bridge envelope binds content", bridges.validate_envelope(root, envelope) == envelope)
        tampered_envelope = {**envelope, "payload": {"statement": "changed after sealing"}}
        refuses(
            "bridge envelope rejects post-seal payload changes",
            bridges.BridgeError,
            lambda: bridges.validate_envelope(root, tampered_envelope),
            "seal",
        )
        disconnected = bridges.build_envelope(
            root, "B2", "frame:target-control", "maths:source-status-map", "witsoc.target.v2",
            target["canonical_sha256"], "C1", {"statement": target["statement"]},
            causation_id="B1",
        )
        refuses(
            "bridge composition rejects disconnected capability hops",
            bridges.BridgeError,
            lambda: bridges.compose(root, [envelope, disconnected]),
            "disconnected",
        )

    with tempfile.TemporaryDirectory(prefix="witsoc-memory-") as raw:
        store = Path(raw)
        exact_scope = {"variant": "exact"}
        entry = evidence_memory.make_entry(
            kind="ADMITTED_PRODUCT", target_sha256=target["canonical_sha256"], domain="maths",
            scope=exact_scope, status="PARTIAL", content={"result": "synthetic"},
            admission_ref="A1", evidence_refs=["sha256:" + "1" * 64], tags=["synthetic"],
            created_at="2026-01-01T00:00:00+00:00",
        )
        evidence_memory.put(store, entry)
        equivalent_entry = evidence_memory.make_entry(
            kind="ADMITTED_PRODUCT", target_sha256=target["canonical_sha256"], domain="maths",
            scope=exact_scope, status="PARTIAL",
            content={"mechanism_fingerprint": "synthetic-mechanism", "summary": "same structural result"},
            admission_ref="A2", evidence_refs=["sha256:" + "5" * 64], tags=["synthetic"],
            created_at="2026-01-02T00:00:00+00:00",
        )
        entry_with_mechanism = evidence_memory.make_entry(
            kind="ADMITTED_PRODUCT", target_sha256=target["canonical_sha256"], domain="maths",
            scope=exact_scope, status="PARTIAL",
            content={"mechanism_fingerprint": "synthetic-mechanism", "summary": "first structural result"},
            admission_ref="A3", evidence_refs=["sha256:" + "6" * 64], tags=["synthetic"],
            created_at="2026-01-03T00:00:00+00:00",
        )
        evidence_memory.put(store, equivalent_entry)
        evidence_memory.put(store, entry_with_mechanism)
        check(
            "admitted memory is reusable at exact scope",
            len(evidence_memory.query(
                store,
                target_sha256=target["canonical_sha256"],
                domain="maths",
                scope=exact_scope,
            )) == 3,
        )
        compact_memory = evidence_memory.compact_query(
            store,
            target_sha256=target["canonical_sha256"],
            domain="maths",
            scope=exact_scope,
            tags=["synthetic"],
            max_bytes=4096,
        )
        check(
            "memory context compaction deduplicates mechanisms without becoming evidence",
            compact_memory["source_entry_count"] == 3
            and len(compact_memory["records"]) == 2
            and compact_memory["non_authoritative_read_model"] is True
            and compact_memory["encoded_bytes"] <= 4096,
        )
        check(
            "near-scope memory does not enter default retrieval",
            not evidence_memory.query(
                store,
                target_sha256=target["canonical_sha256"],
                domain="maths",
                scope={"variant": "nearby"},
            ),
        )
        refuses(
            "reusable retrieval fails closed without a complete context",
            evidence_memory.MemoryError,
            lambda: evidence_memory.query(
                store, target_sha256=target["canonical_sha256"], domain="maths"
            ),
            "exact target, domain, and scope",
        )
        refuses(
            "unproven products cannot enter reusable memory",
            evidence_memory.MemoryError,
            lambda: evidence_memory.make_entry(
                kind="ADMITTED_PRODUCT",
                target_sha256=target["canonical_sha256"],
                domain="maths",
                scope=exact_scope,
                status="PARTIAL",
                content={"result": "unsupported"},
            ),
            "provenance evidence",
        )
        refuses(
            "held-out answer markers cannot enter memory",
            evidence_memory.MemoryError,
            lambda: evidence_memory.make_entry(
                kind="SOURCE",
                target_sha256=target["canonical_sha256"],
                domain="maths",
                scope=exact_scope,
                status="RECORDED",
                content={"note": "contains an evaluation answer key"},
                evidence_refs=["sha256:" + "4" * 64],
            ),
            "forbidden evaluation material",
        )
        evidence_memory.invalidate(store, entry["entry_id"], "superseded", "sha256:" + "2" * 64)
        remaining_memory = evidence_memory.query(
            store,
            target_sha256=target["canonical_sha256"],
            domain="maths",
            scope=exact_scope,
        )
        check(
            "invalidated memory leaves default retrieval",
            len(remaining_memory) == 2
            and all(item["entry_id"] != entry["entry_id"] for item in remaining_memory),
        )

    if full_profile:
        from . import advanced_selftest

        advanced = advanced_selftest.run(root)
        cases.extend(
            {
                "name": f"advanced: {item['name']}",
                "ok": item["ok"],
                **({"detail": item["detail"]} if item.get("detail") else {}),
            }
            for item in advanced["cases"]
        )
        health = doctor(root)
        check("runtime ownership and capability closure are valid", health["ok"])
    else:
        generated = runtime_contracts.check(root)
        package_status = domain_packages.status(root, verify=False)
        check("thin core contract is valid while domain packs are dormant", generated["ok"])
        check("dormant domain package registry is valid", package_status["ok"])
    return {
        "schema": "witsoc.runtime-selftest.v1",
        "profile": "FULL" if full_profile else "CORE_ONLY",
        "cases": cases,
        "ok": all(item["ok"] for item in cases),
    }


def add_state_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--out", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Witsoc research runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    route = sub.add_parser("route", help="select a sticky mode, domain, and minimal load plan")
    route_statement = route.add_mutually_exclusive_group(required=True)
    route_statement.add_argument("--statement")
    route_statement.add_argument("--statement-file", type=Path)
    route.add_argument("--intent", choices=modes.MODES)
    route.add_argument("--domain"); route.add_argument("--role", choices=("explorer", "generator", "researcher"), default="explorer")
    route.add_argument("--goal-type")
    route.add_argument("--available-type", action="append", default=[])
    route.add_argument("--capability", action="append", default=[])
    route.set_defaults(func=route_command)

    pack_status = sub.add_parser(
        "pack-status", help="show pinned, cached, and active domain distributions"
    )
    pack_status.add_argument("--verify", action="store_true")
    pack_status.set_defaults(func=package_status_command)

    pack_ensure = sub.add_parser(
        "pack-ensure", help="install and activate the pinned pack selected by a request"
    )
    pack_target = pack_ensure.add_mutually_exclusive_group(required=True)
    pack_target.add_argument("--domain", action="append")
    pack_target.add_argument("--statement")
    pack_target.add_argument("--statement-file", type=Path)
    pack_ensure.add_argument("--installer", choices=sorted(domain_packages.INSTALLERS))
    pack_ensure.add_argument("--wheelhouse", type=Path)
    pack_ensure.add_argument("--offline", action="store_true", default=None)
    pack_ensure.add_argument("--no-install", action="store_true")
    pack_ensure.set_defaults(func=package_ensure_command)

    preflight = sub.add_parser(
        "orchestrator-preflight",
        help="route and validate Plane resources, workspace binding, and lifecycle before task side effects",
    )
    preflight_statement = preflight.add_mutually_exclusive_group(required=True)
    preflight_statement.add_argument("--statement")
    preflight_statement.add_argument("--statement-file", type=Path)
    preflight.add_argument("--objective", default="")
    preflight.add_argument("--constraint", action="append", default=[])
    preflight.add_argument("--target-sha256")
    preflight.add_argument("--intent", choices=modes.MODES)
    preflight.add_argument("--domain")
    preflight.add_argument(
        "--role", choices=("explorer", "generator", "researcher"), default="explorer"
    )
    preflight.add_argument("--goal-type")
    preflight.add_argument("--available-type", action="append", default=[])
    preflight.add_argument("--capability", action="append", default=[])
    preflight.add_argument("--workspace-root", type=Path, required=True)
    preflight.add_argument("--task-dir", type=Path, required=True)
    preflight.add_argument("--plane-tool")
    preflight.add_argument(
        "--worker-workspace",
        choices=("inherit-bound", "isolated-return"),
        default="inherit-bound",
    )
    preflight.add_argument("--base-revision")
    preflight.add_argument("--artifact-return", action="append", default=[])
    preflight.add_argument("--out", type=Path, required=True)
    preflight.set_defaults(func=orchestrator_preflight_command)

    next_action = sub.add_parser(
        "orchestrator-next",
        help="derive the only legal next lifecycle action and worker-launch gate",
    )
    next_action.add_argument("--state", type=Path, required=True)
    next_action.add_argument("--handoff", type=Path)
    next_action.add_argument("--delta", type=Path)
    next_action.add_argument("--finalization", type=Path)
    next_action.set_defaults(func=orchestrator_next_command)

    review_draft = sub.add_parser(
        "review-draft",
        help="bind an independent review worksheet to exact state and artifact bytes",
    )
    review_draft.add_argument("--state", type=Path, required=True)
    review_draft.add_argument("--review-id", required=True)
    review_draft.add_argument("--revision-id", required=True)
    review_draft.add_argument("--producer-id", required=True)
    review_draft.add_argument("--producer-method", required=True)
    review_draft.add_argument("--producer-failure-domain", action="append", required=True)
    review_draft.add_argument("--reviewer-id", required=True)
    review_draft.add_argument("--reviewer-method", required=True)
    review_draft.add_argument("--reviewer-failure-domain", action="append", required=True)
    review_draft.add_argument("--artifact", type=Path, action="append", required=True)
    review_draft.add_argument("--item-id", action="append", required=True)
    review_draft.add_argument("--source-map", type=Path)
    review_draft.add_argument("--out", type=Path, required=True)
    review_draft.set_defaults(func=review_draft_command)

    review_check = sub.add_parser(
        "review-check",
        help="seal a completed independent review and reject stale or incomplete checks",
    )
    review_check.add_argument("--state", type=Path, required=True)
    review_check.add_argument("--input", type=Path, required=True)
    review_check.add_argument("--source-map", type=Path)
    review_check.add_argument("--out", type=Path, required=True)
    review_check.set_defaults(func=review_check_command)

    audit = sub.add_parser(
        "campaign-audit",
        help="detect pending-state drift, unimported returns, stale paths, and stale reports",
    )
    audit.add_argument("--state", type=Path, required=True)
    audit.add_argument("--task-dir", type=Path)
    audit.add_argument("--report-id", default="campaign-audit")
    audit.add_argument("--out", type=Path)
    audit.set_defaults(func=campaign_audit_command)

    legacy = sub.add_parser(
        "legacy-audit",
        help="classify old packets without importing them into the active lifecycle",
    )
    legacy.add_argument("--input", type=Path, required=True)
    legacy.add_argument("--report-id", default="legacy-audit")
    legacy.add_argument("--target-sha256")
    legacy.add_argument("--out", type=Path)
    legacy.set_defaults(func=legacy_audit_command)

    handoff = sub.add_parser(
        "orchestrator-handoff",
        help="bind one issued episode to an osci-worker prompt and sealed return contract",
    )
    handoff.add_argument("--state", type=Path, required=True)
    handoff.add_argument("--episode", type=Path, required=True)
    handoff.add_argument("--workspace-root", type=Path, required=True)
    handoff.add_argument("--task-dir", type=Path, required=True)
    handoff.add_argument("--out", type=Path, default=Path("researcher-handoff.json"))
    handoff.add_argument("--state-out", type=Path, default=Path("researcher-state.json"))
    handoff.add_argument("--draft-out", type=Path, default=Path("research-delta.draft.json"))
    handoff.add_argument("--delta-out", type=Path, default=Path("research-delta.json"))
    handoff.add_argument("--source-map", type=Path)
    handoff.add_argument("--budget", type=int, default=2048)
    handoff.set_defaults(func=orchestrator_handoff_command)

    round_handoffs = sub.add_parser(
        "orchestrator-round-handoffs",
        help="bind every child of one STRONG issued round to an ordinary worker",
    )
    round_handoffs.add_argument("--state", type=Path, required=True)
    round_handoffs.add_argument("--round", type=Path, required=True)
    round_handoffs.add_argument("--workspace-root", type=Path, required=True)
    round_handoffs.add_argument("--task-dir", type=Path, required=True)
    round_handoffs.add_argument("--out-dir", type=Path, default=Path("round-workers"))
    round_handoffs.add_argument("--source-map", type=Path)
    round_handoffs.add_argument("--budget", type=int, default=2048)
    round_handoffs.set_defaults(func=orchestrator_round_handoffs_command)

    start = sub.add_parser("start", help="freeze a target and initialize replayable kernel state")
    start_statement = start.add_mutually_exclusive_group(required=True)
    start_statement.add_argument("--statement")
    start_statement.add_argument("--statement-file", type=Path)
    start.add_argument("--objective", default="")
    start.add_argument("--constraint", action="append", default=[]); start.add_argument("--target-sha256")
    start.add_argument("--intent", choices=modes.MODES); start.add_argument("--domain")
    start.add_argument("--role", choices=("explorer", "generator", "researcher"), default="explorer")
    start.add_argument("--ceiling", choices=sorted(kernel.STATUSES), default="VERIFIED")
    start.add_argument("--preflight", type=Path, required=True)
    start.add_argument("--out", type=Path, required=True); start.add_argument("--target-out", type=Path)
    start.set_defaults(func=start_command)

    finalize = sub.add_parser(
        "finalize",
        help="derive one canonical terminal packet and result from current kernel state",
    )
    finalize.add_argument("--state", type=Path, required=True)
    finalize.add_argument("--finalization-id", default="final")
    finalize.add_argument("--artifact", type=Path, action="append", default=[])
    finalize.add_argument("--review", type=Path, action="append", default=[])
    finalize.add_argument("--out", type=Path, required=True)
    finalize.add_argument("--result-out", type=Path, required=True)
    finalize.set_defaults(func=finalize_command)

    decide = sub.add_parser(
        "explorer-decide",
        help="record a non-dispatch Explorer decision against current state",
    )
    add_state_output(decide)
    decide.add_argument("--decision-id", required=True)
    decide.add_argument("--action", choices=sorted(orchestration.DECISION_ACTIONS), required=True)
    decide.add_argument("--basis-ref", action="append", default=[], required=True)
    decide.add_argument("--alternative", action="append", default=[])
    decide.add_argument("--changed-axis", default="")
    decide.set_defaults(func=explorer_decide_command)

    source_draft = sub.add_parser(
        "source-map-draft",
        help="create a target-bound source-status worksheet",
    )
    source_draft.add_argument("--state", type=Path, required=True)
    source_draft.add_argument("--source-map-id", required=True)
    source_draft.add_argument("--checked-at", required=True)
    source_draft.add_argument("--out", type=Path, required=True)
    source_draft.set_defaults(func=source_map_draft_command)

    source_check = sub.add_parser(
        "source-map-check",
        help="validate and seal source receipts against the frozen target",
    )
    source_check.add_argument("--state", type=Path, required=True)
    source_check.add_argument("--input", type=Path, required=True)
    source_check.add_argument("--out", type=Path, required=True)
    source_check.set_defaults(func=source_map_check_command)

    explorer_draft = sub.add_parser(
        "explorer-draft",
        help="materialize the bounded Explorer worksheet for the current state",
    )
    explorer_draft.add_argument("--state", type=Path, required=True)
    explorer_draft.add_argument("--proposals", type=Path)
    explorer_draft.add_argument("--prior-explorer", type=Path)
    explorer_draft.add_argument("--out", type=Path, required=True)
    explorer_draft.add_argument("--proposals-out", type=Path)
    explorer_draft.set_defaults(func=explorer_draft_command)

    proposal_draft = sub.add_parser(
        "explorer-proposal-draft",
        help="create one state-bound proposal-v2 worksheet",
    )
    proposal_draft.add_argument("--state", type=Path, required=True)
    proposal_draft.add_argument("--proposal-id", required=True)
    proposal_draft.add_argument("--node-id", required=True)
    proposal_draft.add_argument("--lane", choices=sorted(exploration.LANES), required=True)
    proposal_draft.add_argument("--out", type=Path, required=True)
    proposal_draft.set_defaults(func=explorer_proposal_draft_command)

    proposal_check = sub.add_parser(
        "explorer-proposal-check",
        help="validate and seal one proposal-v2 worksheet",
    )
    proposal_check.add_argument("--state", type=Path, required=True)
    proposal_check.add_argument("--input", type=Path, required=True)
    proposal_check.add_argument("--out", type=Path, required=True)
    proposal_check.set_defaults(func=explorer_proposal_check_command)

    explorer_check = sub.add_parser(
        "explorer-check",
        help="validate and seal an edited Explorer worksheet",
    )
    explorer_check.add_argument("--state", type=Path, required=True)
    explorer_check.add_argument("--input", type=Path, required=True)
    explorer_check.add_argument("--proposals", type=Path)
    explorer_check.add_argument("--source-map", type=Path)
    explorer_check.add_argument("--stop-review", type=Path)
    explorer_check.add_argument("--out", type=Path, required=True)
    explorer_check.add_argument("--proposals-out", type=Path)
    explorer_check.set_defaults(func=explorer_check_command)

    stop_review_draft = sub.add_parser(
        "explorer-stop-review-draft",
        help="bind an HONEST_STOP candidate for a distinct independent reviewer",
    )
    stop_review_draft.add_argument("--state", type=Path, required=True)
    stop_review_draft.add_argument("--explorer-draft", type=Path, required=True)
    stop_review_draft.add_argument("--proposals", type=Path)
    stop_review_draft.add_argument("--source-map", type=Path, required=True)
    stop_review_draft.add_argument("--report-id", required=True)
    stop_review_draft.add_argument("--out", type=Path, required=True)
    stop_review_draft.set_defaults(func=explorer_stop_review_draft_command)

    stop_review_check = sub.add_parser(
        "explorer-stop-review-check",
        help="validate and seal a distinct review of an HONEST_STOP candidate",
    )
    stop_review_check.add_argument("--state", type=Path, required=True)
    stop_review_check.add_argument("--explorer-draft", type=Path, required=True)
    stop_review_check.add_argument("--proposals", type=Path)
    stop_review_check.add_argument("--source-map", type=Path, required=True)
    stop_review_check.add_argument("--input", type=Path, required=True)
    stop_review_check.add_argument("--out", type=Path, required=True)
    stop_review_check.set_defaults(func=explorer_stop_review_check_command)

    explorer_arbitrate = sub.add_parser(
        "explorer-arbitrate",
        help="record one sealed non-dispatch Explorer arbitration",
    )
    add_state_output(explorer_arbitrate)
    explorer_arbitrate.add_argument("--explorer-state", type=Path, required=True)
    explorer_arbitrate.add_argument("--proposals", type=Path)
    explorer_arbitrate.add_argument("--source-map", type=Path)
    explorer_arbitrate.add_argument("--stop-review", type=Path)
    explorer_arbitrate.add_argument("--arbitration-out", type=Path, required=True)
    explorer_arbitrate.set_defaults(func=explorer_arbitrate_command)

    event = sub.add_parser("event", help="seal an event against current state")
    event.add_argument("--state", type=Path, required=True); event.add_argument("--kind", choices=sorted(kernel.EVENT_KINDS), required=True)
    event.add_argument("--payload", type=Path, required=True); event.add_argument("--event-id", required=True)
    event.add_argument("--out", type=Path, required=True); event.set_defaults(func=event_command)

    step = sub.add_parser("step", help="apply one sealed non-admission event")
    add_state_output(step); step.add_argument("--event", type=Path, required=True); step.set_defaults(func=step_command)

    inspect = sub.add_parser("inspect", help="show compact kernel state")
    inspect.add_argument("--state", type=Path, required=True); inspect.set_defaults(func=inspect_command)
    replay = sub.add_parser("replay", help="rebuild kernel state from its event log")
    replay.add_argument("--state", type=Path, required=True); replay.set_defaults(func=replay_command)
    state_index_parser = sub.add_parser("state-index", help="derive a sealed read-only index from kernel state")
    state_index_parser.add_argument("--state", type=Path, required=True); state_index_parser.add_argument("--report-id", default="state-index")
    state_index_parser.add_argument("--out", type=Path); state_index_parser.set_defaults(func=state_index_command)
    compact = sub.add_parser("state-compact", help="write a bounded non-authoritative checkpoint and index")
    compact.add_argument("--state", type=Path, required=True); compact.add_argument("--report-id", default="state-checkpoint")
    compact.add_argument("--block-size", type=int, default=64); compact.add_argument("--tail-events", type=int, default=16)
    compact.add_argument("--out", type=Path, required=True); compact.set_defaults(func=state_compact_command)

    admission = sub.add_parser("import-admission", help="project an admitted frame claim into kernel state")
    add_state_output(admission); admission.add_argument("--frame-state", type=Path, required=True)
    admission.add_argument("--claim-id", required=True); admission.add_argument("--item-id", default="ROOT")
    admission.add_argument("--event-id"); admission.add_argument("--admission-out", type=Path)
    admission.set_defaults(func=import_admission_command)

    migrate = sub.add_parser("migrate-frame", help="migrate frame-state-v1 into replayable kernel state")
    migrate.add_argument("--frame-state", type=Path, required=True); migrate.add_argument("--domain", required=True)
    migrate.add_argument("--mode", choices=modes.MODES, default="OPEN_DISCOVERY")
    migrate.add_argument("--out", type=Path, required=True); migrate.set_defaults(func=migrate_frame_command)

    plan = sub.add_parser("episode-plan", help="rank a semantically diverse discovery portfolio")
    plan.add_argument("--state", type=Path, required=True); plan.add_argument("--proposals", type=Path, required=True)
    plan.add_argument("--portfolio-exception", default=""); plan.set_defaults(func=episode_plan_command)
    issue = sub.add_parser("episode-issue", help="select and issue exactly one bounded episode")
    add_state_output(issue); issue.add_argument("--proposals", type=Path, required=True)
    issue.add_argument("--explorer-state", type=Path)
    issue.add_argument("--source-map", type=Path)
    issue.add_argument("--episode-id", required=True); issue.add_argument("--episode-out", type=Path, required=True)
    issue.add_argument("--portfolio-exception", default=""); issue.set_defaults(func=episode_issue_command)
    returned = sub.add_parser("episode-return", help="validate and merge one research delta")
    add_state_output(returned); returned.add_argument("--delta", type=Path, required=True)
    returned.set_defaults(func=episode_return_command)
    delta_build = sub.add_parser(
        "delta-build", help="bind and seal a role-authored delta draft to pending work"
    )
    delta_build.add_argument("--state", type=Path, required=True)
    delta_build.add_argument("--handoff", type=Path)
    delta_build.add_argument("--draft", type=Path, required=True)
    delta_build.add_argument("--out", type=Path, required=True)
    delta_build.set_defaults(func=delta_build_command)
    reasoning_check = sub.add_parser(
        "reasoning-check", help="validate and seal one bounded Researcher reasoning state"
    )
    reasoning_check.add_argument("--state", type=Path, required=True)
    reasoning_check.add_argument("--handoff", type=Path, required=True)
    reasoning_check.add_argument("--input", type=Path, required=True)
    reasoning_check.add_argument("--expected-outcome", choices=sorted(discovery.OUTCOMES))
    reasoning_check.add_argument("--out", type=Path)
    reasoning_check.set_defaults(func=reasoning_check_command)
    novelty = sub.add_parser("novelty-audit", help="compare one exact candidate against a bound source map")
    novelty.add_argument("--candidate", type=Path, required=True); novelty.add_argument("--source-map", type=Path, required=True)
    novelty.add_argument("--comparisons", type=Path, required=True); novelty.add_argument("--report-id", required=True)
    novelty.add_argument("--out", type=Path); novelty.set_defaults(func=novelty_audit_command)

    round_plan = sub.add_parser("round-plan", help="plan independent attacks against one state snapshot")
    round_plan.add_argument("--state", type=Path, required=True)
    round_plan.add_argument("--specifications", type=Path, required=True)
    round_plan.add_argument("--round-id", required=True); round_plan.add_argument("--rationale", required=True)
    round_plan.add_argument("--merge-policy", choices=sorted(rounds.MERGE_POLICIES), default="CONFLICT_VISIBLE")
    round_plan.add_argument("--max-parallel", type=int, default=4); round_plan.set_defaults(func=round_plan_command)
    independence = sub.add_parser("round-independence", help="audit epistemic independence before issuing a round")
    independence.add_argument("--state", type=Path, required=True); independence.add_argument("--specifications", type=Path, required=True)
    independence.add_argument("--report-id", required=True); independence.add_argument("--out", type=Path)
    independence.set_defaults(func=round_independence_command)
    round_issue = sub.add_parser("round-issue", help="issue one sealed independent research round")
    add_state_output(round_issue); round_issue.add_argument("--specifications", type=Path, required=True)
    round_issue.add_argument("--explorer-state", type=Path)
    round_issue.add_argument("--source-map", type=Path)
    round_issue.add_argument("--round-id", required=True); round_issue.add_argument("--rationale", required=True)
    round_issue.add_argument("--merge-policy", choices=sorted(rounds.MERGE_POLICIES), default="CONFLICT_VISIBLE")
    round_issue.add_argument("--max-parallel", type=int, default=4)
    round_issue.add_argument("--round-out", type=Path, required=True); round_issue.set_defaults(func=round_issue_command)
    round_merge = sub.add_parser("round-merge", help="validate child deltas and build a conflict-visible aggregate")
    round_merge.add_argument("--state", type=Path, required=True); round_merge.add_argument("--round", type=Path, required=True)
    round_merge.add_argument("--deltas", type=Path, required=True); round_merge.add_argument("--round-delta-id", required=True)
    round_merge.add_argument("--out", type=Path, required=True); round_merge.set_defaults(func=round_merge_command)
    round_return = sub.add_parser("round-return", help="merge a nonconflicting round aggregate and return control")
    add_state_output(round_return); round_return.add_argument("--round-delta", type=Path, required=True)
    round_return.set_defaults(func=round_return_command)

    catalog = sub.add_parser("capabilities", help="list capabilities or produce a minimal load plan")
    catalog.add_argument("--statement"); catalog.add_argument("--intent", choices=modes.MODES)
    catalog.add_argument("--domain"); catalog.add_argument("--role", choices=("explorer", "generator", "researcher"), default="explorer")
    catalog.add_argument("--goal-type")
    catalog.add_argument("--available-type", action="append", default=[])
    catalog.add_argument("--capability", action="append", default=[])
    catalog.set_defaults(func=capabilities_command)

    graph = sub.add_parser("capability-graph", help="inspect the typed capability graph")
    graph.add_argument("--domain"); graph.add_argument("--full", action="store_true")
    graph.set_defaults(func=capability_graph_command)

    contract = sub.add_parser("contracts", help="inspect the packet registry or validate one sealed packet")
    contract.add_argument("--type"); contract.add_argument("--packet", type=Path)
    contract.set_defaults(func=contracts_command)

    project = sub.add_parser("project", help="derive a read-only compatibility view from kernel state")
    project.add_argument("--state", type=Path, required=True)
    project.add_argument("--view", choices=("frame", "campaign", "summary"), default="summary")
    project.add_argument("--out", type=Path); project.set_defaults(func=project_command)

    capsule = sub.add_parser("capsule", help="compile a sealed, token-bounded role handoff")
    capsule.add_argument("--state", type=Path, required=True)
    capsule.add_argument("--role", choices=("explorer", "generator", "researcher"), required=True)
    capsule.add_argument("--statement", default=""); capsule.add_argument("--budget", type=int, default=2048)
    capsule.add_argument("--capsule-id"); capsule.add_argument("--source-map", type=Path)
    capsule.add_argument("--out", type=Path, required=True); capsule.set_defaults(func=capsule_command)

    negotiate = sub.add_parser("bridge-negotiate", help="find compatible types between two capabilities")
    negotiate.add_argument("--source", required=True); negotiate.add_argument("--destination", required=True)
    negotiate.set_defaults(func=bridge_negotiate_command)
    bridge = sub.add_parser("bridge-build", help="build a content-bound bridge envelope")
    bridge.add_argument("--envelope-id", required=True); bridge.add_argument("--source", required=True)
    bridge.add_argument("--destination", required=True); bridge.add_argument("--message-type", required=True)
    bridge.add_argument("--target-sha256", required=True); bridge.add_argument("--correlation-id", required=True)
    bridge.add_argument("--causation-id"); bridge.add_argument("--payload", type=Path, required=True)
    bridge.add_argument("--evidence-ref", action="append", default=[]); bridge.add_argument("--out", type=Path, required=True)
    bridge.set_defaults(func=bridge_build_command)

    negotiate_v2 = sub.add_parser("bridge-negotiate-v2", help="negotiate canonical packet versions and declared adapters")
    negotiate_v2.add_argument("--source", required=True); negotiate_v2.add_argument("--destination", required=True)
    negotiate_v2.set_defaults(func=bridge_negotiate_v2_command)
    bridge_plan = sub.add_parser("bridge-plan-v2", help="find the lowest-loss typed capability paths")
    bridge_plan.add_argument("--source", required=True); bridge_plan.add_argument("--destination", required=True)
    bridge_plan.add_argument("--max-hops", type=int, default=4); bridge_plan.add_argument("--max-loss-units", type=int, default=4)
    bridge_plan.add_argument("--limit", type=int, default=8); bridge_plan.add_argument("--out", type=Path)
    bridge_plan.set_defaults(func=bridge_plan_v2_command)
    translate_v2 = sub.add_parser("bridge-translate-v2", help="apply and verify one declared packet transform")
    translate_v2.add_argument("--source", required=True); translate_v2.add_argument("--destination", required=True)
    translate_v2.add_argument("--adapter-id", required=True); translate_v2.add_argument("--source-packet", type=Path, required=True)
    translate_v2.add_argument("--transfer-id", required=True); translate_v2.add_argument("--scope", type=Path, required=True)
    translate_v2.add_argument("--evidence-ref", action="append", default=[]); translate_v2.add_argument("--out", type=Path, required=True)
    translate_v2.set_defaults(func=bridge_translate_v2_command)
    bridge_v2 = sub.add_parser("bridge-build-v2", help="build a typed, loss-aware bridge envelope")
    bridge_v2.add_argument("--envelope-id", required=True); bridge_v2.add_argument("--source", required=True)
    bridge_v2.add_argument("--destination", required=True); bridge_v2.add_argument("--adapter-id", required=True)
    bridge_v2.add_argument("--source-message-type", required=True); bridge_v2.add_argument("--message-type", required=True)
    bridge_v2.add_argument("--target-sha256", required=True); bridge_v2.add_argument("--correlation-id", required=True)
    bridge_v2.add_argument("--causation-id"); bridge_v2.add_argument("--scope-owner", required=True)
    bridge_v2.add_argument("--source-packet", type=Path, required=True); bridge_v2.add_argument("--payload", type=Path, required=True)
    bridge_v2.add_argument("--preserve", action="append", default=[]); bridge_v2.add_argument("--loss", action="append", default=[])
    bridge_v2.add_argument("--evidence-ref", action="append", default=[]); bridge_v2.add_argument("--conflict-ref", action="append", default=[])
    bridge_v2.add_argument("--out", type=Path, required=True); bridge_v2.set_defaults(func=bridge_build_v2_command)
    compose_v2 = sub.add_parser("bridge-compose-v2", help="validate a causal bridge chain and its loss budget")
    compose_v2.add_argument("--envelope", type=Path, action="append", required=True)
    compose_v2.add_argument("--max-losses", type=int, default=4); compose_v2.add_argument("--out", type=Path)
    compose_v2.set_defaults(func=bridge_compose_v2_command)
    graph_v2 = sub.add_parser("bridge-graph-v2", help="validate a branching message graph and explicit joins")
    graph_v2.add_argument("--envelope", type=Path, action="append", required=True)
    graph_v2.add_argument("--max-loss-units", type=int, default=8); graph_v2.add_argument("--report-id", default="bridge-graph")
    graph_v2.add_argument("--out", type=Path); graph_v2.set_defaults(func=bridge_graph_v2_command)

    memory_put = sub.add_parser("memory-put", help="admit one content-addressed memory entry")
    memory_put.add_argument("--store", type=Path, required=True); memory_put.add_argument("--entry", type=Path, required=True)
    memory_put.set_defaults(func=memory_put_command)
    memory_query = sub.add_parser("memory-query", help="retrieve exact-scope reusable memory")
    memory_query.add_argument("--store", type=Path, required=True); memory_query.add_argument("--target-sha256")
    memory_query.add_argument("--domain"); memory_query.add_argument("--scope", type=Path)
    memory_query.add_argument("--tag", action="append", default=[])
    memory_query.add_argument("--all", action="store_true"); memory_query.add_argument("--include-invalidated", action="store_true")
    memory_query.set_defaults(func=memory_query_command)
    memory_compact = sub.add_parser("memory-compact", help="compile exact-scope memory into a bounded deduplicated context pack")
    memory_compact.add_argument("--store", type=Path, required=True); memory_compact.add_argument("--target-sha256", required=True)
    memory_compact.add_argument("--domain", required=True); memory_compact.add_argument("--scope", type=Path, required=True)
    memory_compact.add_argument("--tag", action="append", default=[]); memory_compact.add_argument("--max-bytes", type=int, default=8192)
    memory_compact.set_defaults(func=memory_compact_command)
    memory_invalidate = sub.add_parser("memory-invalidate", help="append an evidence-bound invalidation")
    memory_invalidate.add_argument("--store", type=Path, required=True); memory_invalidate.add_argument("--entry-id", required=True)
    memory_invalidate.add_argument("--reason", required=True); memory_invalidate.add_argument("--evidence-ref", required=True)
    memory_invalidate.set_defaults(func=memory_invalidate_command)

    hint_build = sub.add_parser("hint-build", help="build a sealed non-evidentiary structural hint")
    hint_build.add_argument("--domain", choices=sorted(hint_memory.DOMAIN_FEATURES), required=True)
    hint_build.add_argument("--features", type=Path, required=True); hint_build.add_argument("--content", type=Path, required=True)
    hint_build.add_argument("--scope", type=Path); hint_build.add_argument("--provenance-ref", action="append", default=[])
    hint_build.add_argument("--created-at"); hint_build.add_argument("--out", type=Path, required=True)
    hint_build.set_defaults(func=hint_build_command)
    hint_put = sub.add_parser("hint-put", help="store an immutable structural hint separately from evidence")
    hint_put.add_argument("--store", type=Path, required=True); hint_put.add_argument("--hint", type=Path, required=True)
    hint_put.add_argument("--depends-on", action="append", default=[]); hint_put.set_defaults(func=hint_put_command)
    hint_query = sub.add_parser("hint-query", help="rank scope-compatible hints by structural overlap")
    hint_query.add_argument("--store", type=Path, required=True); hint_query.add_argument("--domain", choices=sorted(hint_memory.DOMAIN_FEATURES), required=True)
    hint_query.add_argument("--features", type=Path, required=True); hint_query.add_argument("--scope", type=Path)
    hint_query.add_argument("--min-score", type=float, default=0.5); hint_query.add_argument("--limit", type=int, default=8)
    hint_query.add_argument("--include-invalidated", action="store_true"); hint_query.set_defaults(func=hint_query_command)
    hint_invalidate = sub.add_parser("hint-invalidate", help="invalidate a hint and its dependent hints")
    hint_invalidate.add_argument("--store", type=Path, required=True); hint_invalidate.add_argument("--hint-id", required=True)
    hint_invalidate.add_argument("--reason", required=True); hint_invalidate.add_argument("--provenance-ref", required=True)
    hint_invalidate.set_defaults(func=hint_invalidate_command)

    verify = sub.add_parser("verify", help="compatibility bridge to artifact admission")
    verify.add_argument("args", nargs=argparse.REMAINDER)

    health = sub.add_parser("doctor", help="check architecture, capability, and optional state closure")
    health.add_argument("--state", type=Path)
    health.set_defaults(func=doctor_command)
    test = sub.add_parser("self-test", help="exercise the lightweight runtime with synthetic fixtures")
    test.set_defaults(func=lambda _args: (lambda result: (emit(result), 0 if result["ok"] else 1)[1])(self_test(ROOT)))
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "verify":
        completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "campaign.py"), *args.args], check=False)
        return completed.returncode
    try:
        return int(args.func(args))
    except (
        OSError, json.JSONDecodeError, ValueError, kernel.KernelError,
        discovery.DiscoveryError, capabilities.CapabilityError,
        bridges.BridgeError, evidence_memory.MemoryError, contracts.ContractError,
        projections.ProjectionError, research_ir.ResearchIRError,
        capsules.CapsuleError,
        rounds.RoundError,
        hint_memory.HintMemoryError,
        capability_graph.CapabilityGraphError,
        operators.OperatorError,
        orchestration.OrchestrationError,
        reasoning.ReasoningError,
        assurance.AssuranceError,
        runtime_contracts.RuntimeContractError,
        domain_packages.DomainPackageError,
    ) as exc:
        emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
