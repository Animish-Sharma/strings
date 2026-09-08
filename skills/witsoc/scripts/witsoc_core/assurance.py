"""Activation, review, campaign audit, and canonical finalization gates."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import contracts, domain_packages, kernel
from .canonical import digest_file, digest_value, load_json, seal_packet, verify_packet_seal


ACTIVATION_SCHEMA = "witsoc.activation-receipt.v1"
ACTIVATION_DRAFT_SCHEMA = "witsoc.activation-receipt-draft.v1"
REVIEW_SCHEMA = "witsoc.independent-review.v1"
REVIEW_DRAFT_SCHEMA = "witsoc.independent-review-draft.v1"
FINALIZATION_SCHEMA = "witsoc.finalization.v1"
CONTROL_REPORT_SCHEMA = "witsoc.control-report.v1"
TERMINAL_ACTIONS = {"DIRECT_ANSWER", "WAIT_EXTERNAL", "HONEST_STOP"}
REVIEW_CHECKS = {
    "target_fidelity", "dependencies", "preconditions", "circularity",
    "source_scope", "numeric_scope", "causal_scope", "artifact_completeness",
    "placeholder_scan",
}
REVIEW_VERDICTS = {"ACCEPT", "REJECT", "NEEDS_WORK", "INCONCLUSIVE"}
TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml",
    ".py", ".r", ".jl", ".csv", ".tsv",
}
PLACEHOLDER_PATTERNS = (
    ("PLACEHOLDER_TOKEN", re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER|XXX)\b", re.I)),
    ("UNKNOWN_EXPONENT", re.compile(r"\^\{[^}\n]{0,80}\?[^}\n]*\}")),
    (
        "UNVERIFIED_STEP",
        re.compile(
            r"\b(?:not independently (?:checked|verified|derived|rederived)|"
            r"(?:argument|derivation|bookkeeping) (?:omitted|deferred)|left as an exercise)\b",
            re.I,
        ),
    ),
)
LEGACY_SCHEMAS = {
    "witsoc.research-delta.v1",
    "witsoc.orchestrator-handoff.v1",
    "witsoc.orchestrator-handoff.v2",
    "witsoc.orchestrator-handoff.v3",
    "witsoc.route-state.v1",
    "frame-state-v1",
}


class AssuranceError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise AssuranceError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _safe_relative(value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise AssuranceError(f"{label} must be a relative non-escaping path")
    return path


def _inside(base: Path, path: Path, label: str) -> Path:
    base = base.expanduser().resolve()
    path = path.expanduser().resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise AssuranceError(f"{label} escapes {base}") from exc
    return path


def route_projection(route: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(route[key])
        for key in (
            "activation", "sticky", "decision", "mode", "domains",
            "mode_reference",
        )
    }


def package_records(root: Path, domains: Sequence[str]) -> list[dict[str, Any]]:
    status = domain_packages.status(root, verify=True)
    if not status["ok"]:
        raise AssuranceError("domain package verification failed")
    by_domain = {item["domain"]: item for item in status["packages"]}
    records: list[dict[str, Any]] = []
    for domain in sorted(set(domains)):
        item = by_domain.get(domain)
        if item is None or item["status"] not in {"ACTIVE", "DEVELOPMENT_SOURCE"}:
            raise AssuranceError(f"domain package {domain!r} is not active")
        records.append({
            key: item[key]
            for key in (
                "domain", "distribution", "version", "core_api",
                "domain_contract_version", "payload_sha256", "payload_files",
                "payload_bytes", "install_receipt_sha256", "activation_sha256",
                "status",
            )
        })
    return records


def resource_records(root: Path, resources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in resources:
        relative = _safe_relative(str(raw["local_path"]), "resource path")
        locator = str(raw["skill_locator"])
        if locator != f"witsoc/{relative.as_posix()}":
            raise AssuranceError(f"resource {relative} has a non-canonical Plane locator")
        if locator in seen:
            continue
        path = _inside(root, root / relative, "resource path")
        if not path.is_file() or path.is_symlink():
            raise AssuranceError(f"resource is missing or indirect: {relative}")
        records.append({
            "kind": str(raw["kind"]),
            "local_path": relative.as_posix(),
            "skill_locator": locator,
            "sha256": digest_file(path),
            "size": path.stat().st_size,
        })
        seen.add(locator)
    return records


def build_activation_receipt(
    root: Path,
    *,
    target: Mapping[str, Any],
    route: Mapping[str, Any],
    role: str,
    resources: Sequence[Mapping[str, Any]],
    load_plan: Mapping[str, Any],
    workspace: Mapping[str, Any],
    plane_resolution: Mapping[str, Any],
    coordination: Mapping[str, Any] | None,
    protocol_resource: Mapping[str, Any],
    side_effects: Sequence[str],
    dispatch_gate: Mapping[str, Any],
    problems: Sequence[str],
) -> dict[str, Any]:
    problem_list = list(problems)
    projection = route_projection(route) if route.get("mode_reference") else {}
    route_sha256 = digest_value(projection)
    package_values: list[dict[str, Any]] = []
    resource_values: list[dict[str, Any]] = []
    if not problem_list and route.get("decision") in {"SELECTED", "AMBIGUOUS"}:
        try:
            package_values = package_records(root, route.get("domains") or [])
            resource_values = resource_records(root, resources)
        except AssuranceError as exc:
            problem_list.append(str(exc))
    else:
        for item in resources:
            try:
                resource_values.extend(resource_records(root, [item]))
            except AssuranceError:
                continue
    ok = not problem_list and bool(load_plan.get("ok"))
    packet = seal_packet({
        "schema": ACTIVATION_SCHEMA,
        "receipt_id": f"activation:{target['canonical_sha256'][:16]}:{route_sha256[:12]}",
        "ok": ok,
        "status": "PREFLIGHT_READY" if ok else "ACTIVATION_FAILED",
        "target": copy.deepcopy(dict(target)),
        "route": {
            "activation": route.get("activation", "WITSOC"),
            "decision": route.get("decision", "UNRESOLVABLE"),
            "mode": route.get("mode"),
            "mode_basis": list(route.get("mode_basis") or []),
            "domains": list(route.get("domains") or []),
            "sticky": bool(route.get("sticky", True)),
            "role": role,
            "projection": projection,
            "route_sha256": route_sha256,
        },
        "packages": package_values,
        "resources": resource_values,
        "skill_view_argv": [
            ["$PLANE_TOOL_BIN", "skill-view", item["skill_locator"]]
            for item in resource_values
        ],
        "load_plan": copy.deepcopy(dict(load_plan)),
        "workspace": copy.deepcopy(dict(workspace)),
        "plane_resolution": copy.deepcopy(dict(plane_resolution)),
        "coordination": copy.deepcopy(coordination),
        "protocol_resource": copy.deepcopy(dict(protocol_resource)),
        "side_effects": list(side_effects),
        "dispatch_gate": copy.deepcopy(dict(dispatch_gate)),
        "may_create_run_artifacts": ok,
        "next_stage": "EXPLORER_DECISION" if ok else None,
        "problems": problem_list,
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, ACTIVATION_SCHEMA, packet)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc


def validate_activation(root: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, ACTIVATION_SCHEMA, value)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc
    if not packet["ok"] or packet["status"] != "PREFLIGHT_READY" or packet["problems"]:
        raise AssuranceError("activation receipt is not PREFLIGHT_READY")
    route = packet["route"]
    if route["decision"] not in {"SELECTED", "AMBIGUOUS"}:
        raise AssuranceError("activation receipt has no selected route")
    if route["route_sha256"] != digest_value(route["projection"]):
        raise AssuranceError("activation receipt route digest is broken")
    expected_target = kernel.target_record(
        packet["target"]["statement"],
        packet["target"]["intent"],
        packet["target"]["constraints"],
        canonical_sha256=packet["target"]["canonical_sha256"],
    )
    if expected_target != packet["target"]:
        raise AssuranceError("activation receipt target content is inconsistent")
    workspace = packet["workspace"]
    root_path = Path(workspace["root"]).expanduser().resolve()
    if not root_path.is_dir():
        raise AssuranceError("activation workspace no longer exists")
    relative = _safe_relative(workspace["task_dir_relative"], "activation task directory")
    expected_task = _inside(root_path, root_path / relative, "activation task directory")
    if expected_task != Path(workspace["task_dir"]).expanduser().resolve():
        raise AssuranceError("activation task directory does not match its workspace binding")
    if resource_records(root, packet["resources"]) != packet["resources"]:
        raise AssuranceError("an activated skill resource changed after preflight")
    if package_records(root, route["domains"]) != packet["packages"]:
        raise AssuranceError("an activated domain package changed after preflight")
    return packet


def activation_binding(packet_value: Mapping[str, Any]) -> dict[str, Any]:
    packet = copy.deepcopy(dict(packet_value))
    return {
        "schema": "witsoc.activation-binding.v1",
        "receipt_sha256": packet["payload_sha256"],
        "target_sha256": packet["target"]["canonical_sha256"],
        "route_sha256": packet["route"]["route_sha256"],
        "workspace_root": packet["workspace"]["root"],
        "task_dir_relative": packet["workspace"]["task_dir_relative"],
        "worker_mode": packet["workspace"]["worker_mode"],
        "domains": list(packet["route"]["domains"]),
        "packages": copy.deepcopy(packet["packages"]),
        "resources": copy.deepcopy(packet["resources"]),
    }


def task_directory(state_value: Mapping[str, Any]) -> Path:
    state = kernel.validate_state(state_value)
    binding = state["genesis"].get("activation_binding")
    if binding is None:
        raise AssuranceError("kernel state has no durable activation binding")
    root = Path(binding["workspace_root"]).expanduser().resolve()
    relative = _safe_relative(binding["task_dir_relative"], "bound task directory")
    return _inside(root, root / relative, "bound task directory")


def artifact_manifest(task_dir: Path, paths: Sequence[Path | str]) -> list[dict[str, Any]]:
    task_dir = task_dir.expanduser().resolve()
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        candidate = Path(raw).expanduser()
        candidate = candidate if candidate.is_absolute() else task_dir / candidate
        candidate = _inside(task_dir, candidate, "artifact")
        if not candidate.is_file() or candidate.is_symlink():
            raise AssuranceError(f"artifact is missing or indirect: {candidate}")
        relative = candidate.relative_to(task_dir).as_posix()
        if relative in seen:
            raise AssuranceError(f"artifact path is duplicated: {relative}")
        records.append({
            "path": relative,
            "sha256": digest_file(candidate),
            "size": candidate.stat().st_size,
        })
        seen.add(relative)
    return sorted(records, key=lambda item: item["path"])


def placeholder_findings(task_dir: Path, artifacts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in artifacts:
        path = _inside(task_dir, task_dir / _safe_relative(record["path"], "artifact path"), "artifact")
        if path.suffix.casefold() not in TEXT_SUFFIXES or path.stat().st_size > 4 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for code, pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                findings.append({
                    "severity": "BLOCKER",
                    "code": code,
                    "detail": f"unresolved marker at line {line}",
                    "artifact": record["path"],
                })
    return sorted(findings, key=lambda item: (item["artifact"] or "", item["code"]))


def review_draft(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    review_id: str,
    revision_id: str,
    producer_id: str,
    producer_method: str,
    producer_failure_domains: Sequence[str],
    reviewer_id: str,
    reviewer_method: str,
    reviewer_failure_domains: Sequence[str],
    artifacts: Sequence[Path | str],
    reviewed_item_ids: Sequence[str],
    source_map_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    task = task_directory(state)
    records = artifact_manifest(task, artifacts)
    automatic = placeholder_findings(task, records)
    checks = {name: "NOT_RUN" for name in REVIEW_CHECKS}
    checks["placeholder_scan"] = "FAIL" if automatic else "PASS"
    if "maths" not in state["domains"]:
        checks["numeric_scope"] = "NOT_APPLICABLE"
    if "bio" not in state["domains"]:
        checks["causal_scope"] = "NOT_APPLICABLE"
    source_sha = None
    if source_map_value is not None:
        try:
            source_map = contracts.validate_packet(root, "witsoc.source-map.v2", source_map_value)
        except contracts.ContractError as exc:
            raise AssuranceError(str(exc)) from exc
        if source_map["target_sha256"] != state["target"]["canonical_sha256"]:
            raise AssuranceError("review source map belongs to another target")
        source_sha = source_map["payload_sha256"]
    return {
        "schema": REVIEW_DRAFT_SCHEMA,
        "review_id": review_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "state_revision": state["revision"],
        "state_sha256": state["state_sha256"],
        "revision_id": revision_id,
        "producer": {
            "actor_id": producer_id,
            "method_family": producer_method,
            "failure_domains": sorted(set(producer_failure_domains)),
        },
        "reviewer": {
            "actor_id": reviewer_id,
            "method_family": reviewer_method,
            "failure_domains": sorted(set(reviewer_failure_domains)),
        },
        "artifacts": records,
        "source_map_sha256": source_sha,
        "reviewed_item_ids": sorted(set(reviewed_item_ids)),
        "checks": checks,
        "automated_findings": automatic,
        "findings": [],
        "open_obligations": [],
        "verdict": "NEEDS_WORK",
        "notes": "",
        "status_authority": False,
    }


def _review_required_checks(state: Mapping[str, Any]) -> set[str]:
    required = {
        "target_fidelity", "dependencies", "preconditions", "circularity",
        "source_scope", "artifact_completeness", "placeholder_scan",
    }
    if "maths" in state["domains"]:
        required.add("numeric_scope")
    if "bio" in state["domains"]:
        required.add("causal_scope")
    return required


def validate_review(
    root: Path,
    state_value: Mapping[str, Any],
    value: Mapping[str, Any],
    *,
    source_map_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    try:
        packet = contracts.validate_packet(root, REVIEW_SCHEMA, value)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc
    if (
        packet["target_sha256"] != state["target"]["canonical_sha256"]
        or packet["state_revision"] != state["revision"]
        or packet["state_sha256"] != state["state_sha256"]
    ):
        raise AssuranceError("independent review is stale or targets different state")
    producer, reviewer = packet["producer"], packet["reviewer"]
    if producer["actor_id"] == reviewer["actor_id"]:
        raise AssuranceError("independent reviewer is the producer")
    if producer["method_family"].casefold() == reviewer["method_family"].casefold():
        raise AssuranceError("independent review reuses the producer method family")
    shared_failures = {
        item.casefold() for item in producer["failure_domains"]
    } & {item.casefold() for item in reviewer["failure_domains"]}
    if shared_failures:
        raise AssuranceError(
            f"producer and reviewer share failure domains: {sorted(shared_failures)}"
        )
    known_items = {item["item_id"] for item in state["frontier"]["items"]}
    if not packet["reviewed_item_ids"] or set(packet["reviewed_item_ids"]) - known_items:
        raise AssuranceError("reviewed item ids are empty or unknown")
    task = task_directory(state)
    current = artifact_manifest(task, [item["path"] for item in packet["artifacts"]])
    if current != packet["artifacts"]:
        raise AssuranceError("reviewed artifact bytes changed after review")
    automatic = placeholder_findings(task, current)
    if automatic != packet["automated_findings"]:
        raise AssuranceError("automated review findings are stale")
    expected_placeholder = "FAIL" if automatic else "PASS"
    if packet["checks"]["placeholder_scan"] != expected_placeholder:
        raise AssuranceError("placeholder check differs from the artifact scan")
    source_sha = packet["source_map_sha256"]
    if source_map_value is not None:
        try:
            source_map = contracts.validate_packet(root, "witsoc.source-map.v2", source_map_value)
        except contracts.ContractError as exc:
            raise AssuranceError(str(exc)) from exc
        if source_map["target_sha256"] != packet["target_sha256"]:
            raise AssuranceError("review source map belongs to another target")
        if source_sha != source_map["payload_sha256"]:
            raise AssuranceError("review source map bytes differ from the checked map")
    if packet["verdict"] == "ACCEPT":
        failed = sorted(
            name for name in _review_required_checks(state)
            if packet["checks"][name] != "PASS"
        )
        if failed:
            raise AssuranceError(f"accepted review has incomplete checks: {failed}")
        if packet["open_obligations"]:
            raise AssuranceError("accepted review retains open obligations")
        if any(item["severity"] in {"BLOCKER", "MAJOR"} for item in packet["findings"]):
            raise AssuranceError("accepted review retains major findings")
    return packet


def build_review(
    root: Path,
    state_value: Mapping[str, Any],
    draft_value: Mapping[str, Any],
    *,
    source_map_value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    required = {
        "schema", "review_id", "target_sha256", "state_revision", "state_sha256",
        "revision_id", "producer", "reviewer", "artifacts", "source_map_sha256",
        "reviewed_item_ids", "checks", "automated_findings", "findings",
        "open_obligations", "verdict", "notes", "status_authority",
    }
    _closed(draft_value, required, "independent-review draft")
    if draft_value["schema"] != REVIEW_DRAFT_SCHEMA:
        raise AssuranceError("independent-review draft schema is invalid")
    if set(draft_value["checks"]) != REVIEW_CHECKS:
        raise AssuranceError("independent-review checks are incomplete")
    if draft_value["verdict"] not in REVIEW_VERDICTS:
        raise AssuranceError("independent-review verdict is invalid")
    body = copy.deepcopy(dict(draft_value))
    body["schema"] = REVIEW_SCHEMA
    return validate_review(
        root, state_value, seal_packet(body), source_map_value=source_map_value
    )


def _terminal_record(state: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    if state["pending_episode"] is not None:
        raise AssuranceError("pending work blocks finalization")
    if not state["events"]:
        raise AssuranceError("initialization is not a terminal decision")
    last = state["events"][-1]
    if last["kind"] == "ARBITRATION_RECORDED":
        record = last["payload"]["arbitration"]
    elif last["kind"] == "DECISION_RECORD":
        record = last["payload"]["decision"]
    else:
        raise AssuranceError("latest state event is not terminal Explorer arbitration")
    action = record.get("action")
    if action not in TERMINAL_ACTIONS:
        raise AssuranceError("Explorer has not selected a terminal action")
    return action, record


def _frontier_record(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(item[key])
        for key in (
            "item_id", "kind", "statement", "status", "evidence_refs", "admission_ref",
        )
    }


def _assurance_level(
    state: Mapping[str, Any], action: str, reviews: Sequence[Mapping[str, Any]]
) -> str:
    if action == "HONEST_STOP":
        return "SEARCH_STOPPED"
    if action == "WAIT_EXTERNAL":
        return "WAITING_EXTERNAL"
    levels = {
        "CHECKED_BOUNDED": "BOUNDED_VERIFIED",
        "SKETCH": "PROOF_SKETCH",
        "PARTIAL": "PARTIAL_RESULT",
        "CONDITIONAL": "CONDITIONAL_RESULT",
        "VERIFIED": "KERNEL_VERIFIED",
    }
    level = levels.get(state["status"], "SPECULATION")
    if level == "KERNEL_VERIFIED" and any(item["verdict"] == "ACCEPT" for item in reviews):
        return "INDEPENDENTLY_VERIFIED"
    return level


def _review_file(
    root: Path, state: Mapping[str, Any], task: Path, path_value: Path | str
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(path_value).expanduser()
    path = path if path.is_absolute() else task / path
    path = _inside(task, path, "review")
    if not path.is_file() or path.is_symlink():
        raise AssuranceError(f"review is missing or indirect: {path}")
    review = validate_review(root, state, load_json(path))
    reference = {
        "path": path.relative_to(task).as_posix(),
        "review_id": review["review_id"],
        "sha256": digest_file(path),
        "verdict": review["verdict"],
        "revision_id": review["revision_id"],
    }
    return review, reference


def build_finalization(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    finalization_id: str,
    artifacts: Sequence[Path | str],
    review_paths: Sequence[Path | str],
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    action, arbitration = _terminal_record(state)
    binding = state["genesis"].get("activation_binding")
    if binding is None:
        raise AssuranceError("finalization requires a durable activation binding")
    task = task_directory(state)
    artifact_values = artifact_manifest(task, artifacts)
    unresolved_markers = placeholder_findings(task, artifact_values)
    if unresolved_markers:
        first = unresolved_markers[0]
        raise AssuranceError(
            f"final artifact contains {first['code']} in {first['artifact']}"
        )
    reviews: list[dict[str, Any]] = []
    review_refs: list[dict[str, Any]] = []
    for path in review_paths:
        review, reference = _review_file(root, state, task, path)
        reviews.append(review)
        review_refs.append(reference)
    review_refs.sort(key=lambda item: item["path"])
    if action == "DIRECT_ANSWER":
        if state["status"] not in kernel.ACCEPTED:
            raise AssuranceError("DIRECT_ANSWER has no reducer-admitted target status")
        if not artifact_values:
            raise AssuranceError("DIRECT_ANSWER requires at least one final research artifact")
        accepted_artifacts = {
            (item["path"], item["sha256"])
            for review in reviews if review["verdict"] == "ACCEPT"
            for item in review["artifacts"]
        }
        uncovered = [
            item["path"] for item in artifact_values
            if (item["path"], item["sha256"]) not in accepted_artifacts
        ]
        if uncovered:
            raise AssuranceError(
                f"final artifacts lack an exact accepted independent review: {uncovered}"
            )
    items = state["frontier"]["items"]
    admitted = sorted(
        (_frontier_record(item) for item in items if item["status"] in kernel.ACCEPTED),
        key=lambda item: item["item_id"],
    )
    unresolved = sorted(
        (
            _frontier_record(item) for item in items
            if item["status"] not in {"VERIFIED", "REJECTED"}
        ),
        key=lambda item: item["item_id"],
    )
    source_limits = {
        "coverage_status": arbitration.get("source_coverage_status", "UNKNOWN"),
        "source_map_ref": arbitration.get("source_map_ref"),
        "evidence_ceiling": arbitration.get("evidence_ceiling", "UNKNOWN"),
        "terminal_scope": (
            "CURRENT_AUTHORIZED_SEARCH_ONLY" if action == "HONEST_STOP" else "FROZEN_TARGET"
        ),
    }
    prohibited = {
        "unadmitted claims as established results",
        "novelty beyond the sealed source scope",
        "generalization beyond the recorded evidence ceiling",
        "bounded computation as an unbounded conclusion",
        "causal biological claims without identified intervention evidence",
    }
    if action == "HONEST_STOP":
        prohibited.update({
            "universal impossibility from route exhaustion",
            "solved, disproved, or open-status claims about the target",
            "exhaustion beyond the current authorized search",
        })
    packet = seal_packet({
        "schema": FINALIZATION_SCHEMA,
        "finalization_id": finalization_id,
        "target_sha256": state["target"]["canonical_sha256"],
        "state_revision": state["revision"],
        "state_sha256": state["state_sha256"],
        "activation_receipt_sha256": binding["receipt_sha256"],
        "terminal_action": action,
        "kernel_status": state["status"],
        "outcome": state["outcome"],
        "assurance_level": _assurance_level(state, action, reviews),
        "workspace": {
            "root": binding["workspace_root"],
            "task_dir_relative": binding["task_dir_relative"],
        },
        "artifacts": artifact_values,
        "review_refs": review_refs,
        "admitted_products": admitted,
        "unresolved_items": unresolved,
        "obstructions": sorted(
            copy.deepcopy(state["frontier"]["obstructions"]),
            key=lambda item: item["obstruction_id"],
        ),
        "source_limits": source_limits,
        "prohibited_claims": sorted(prohibited),
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, FINALIZATION_SCHEMA, packet)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc


def validate_finalization(
    root: Path, state_value: Mapping[str, Any], value: Mapping[str, Any]
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    try:
        packet = contracts.validate_packet(root, FINALIZATION_SCHEMA, value)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc
    task_directory(state)
    rebuilt = build_finalization(
        root,
        state,
        finalization_id=packet["finalization_id"],
        artifacts=[item["path"] for item in packet["artifacts"]],
        review_paths=[item["path"] for item in packet["review_refs"]],
    )
    if rebuilt != packet:
        raise AssuranceError("finalization packet is stale or not derived from current state")
    return packet


def render_result(state_value: Mapping[str, Any], finalization: Mapping[str, Any]) -> str:
    state = kernel.validate_state(state_value)
    admitted = finalization["admitted_products"]
    unresolved = finalization["unresolved_items"]
    lines = [
        "# Witsoc Result",
        "",
        "## Target",
        "",
        state["target"]["statement"],
        "",
        "## Disposition",
        "",
        f"- Explorer action: `{finalization['terminal_action']}`",
        f"- Kernel status: `{finalization['kernel_status']}`",
        f"- Outcome: `{finalization['outcome']}`",
        f"- Assurance: `{finalization['assurance_level']}`",
        "",
        "## Admitted Products",
        "",
    ]
    lines.extend(
        f"- `{item['item_id']}` [{item['status']}]: {item['statement']}"
        for item in admitted
    )
    if not admitted:
        lines.append("- None.")
    lines.extend(["", "## Unresolved", ""])
    lines.extend(
        f"- `{item['item_id']}` [{item['status']}]: {item['statement']}"
        for item in unresolved
    )
    if not unresolved:
        lines.append("- None.")
    lines.extend(["", "## Provenance", ""])
    lines.extend([
        f"- State revision: `{finalization['state_revision']}`",
        f"- State SHA-256: `{finalization['state_sha256']}`",
        f"- Activation SHA-256: `{finalization['activation_receipt_sha256']}`",
        f"- Finalization SHA-256: `{finalization['payload_sha256']}`",
        "",
        "## Prohibited Conclusions",
        "",
    ])
    lines.extend(f"- {item}" for item in finalization["prohibited_claims"])
    return "\n".join(lines) + "\n"


def campaign_audit(
    root: Path,
    state_value: Mapping[str, Any],
    *,
    task_dir: Path | None = None,
    report_id: str = "campaign-audit",
) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    binding = state["genesis"].get("activation_binding")
    if binding is None:
        blockers.append({"code": "MISSING_ACTIVATION", "detail": "state has no durable preflight binding"})
        task = task_dir.expanduser().resolve() if task_dir else None
    else:
        task = task_directory(state)
        if task_dir is not None and task != task_dir.expanduser().resolve():
            blockers.append({"code": "TASK_DRIFT", "detail": "requested task directory differs from activation"})
    files: list[Path] = []
    if task is None or not task.is_dir():
        blockers.append({"code": "MISSING_TASK", "detail": "bound task directory does not exist"})
    else:
        files = sorted(
            path for path in task.rglob("*")
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
        )[:4096]
    issued_ids: set[str] = set()
    for event in state["events"]:
        if event["kind"] == "EPISODE_ISSUED":
            issued_ids.add(event["payload"]["episode"]["episode_id"])
        elif event["kind"] == "ROUND_ISSUED":
            issued_ids.update(
                item["episode_id"] for item in event["payload"]["round"]["episodes"]
            )
    returned_ids = {item["episode_id"] for item in state["route_attempts"]}
    pending_ids: set[str] = set()
    pending = state["pending_episode"]
    if pending:
        pending_ids = (
            {item["episode_id"] for item in pending["episodes"]}
            if pending.get("kind") == "ROUND" else {pending["episode_id"]}
        )
    disk_episodes: set[str] = set()
    disk_deltas: set[str] = set()
    content_hashes: dict[str, list[str]] = {}
    terminal_reports: list[Path] = []
    stale_refs: list[str] = []
    workspace = Path(binding["workspace_root"]).resolve() if binding else None
    for path in files:
        relative = path.relative_to(task).as_posix() if task else str(path)
        content_hashes.setdefault(digest_file(path), []).append(relative)
        if re.search(r"(?:^|/)(?:RESULT|FINAL|VERDICT|REPORT)[^/]*\.(?:md|txt|json)$", relative, re.I):
            terminal_reports.append(path)
        if path.suffix.casefold() in TEXT_SUFFIXES and path.stat().st_size <= 4 * 1024 * 1024:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = ""
            for match in re.findall(r"/[^\s\"'`]*\.openscientist/worktrees/[^\s\"'`/]+", text):
                if workspace is None or not str(workspace).startswith(match):
                    stale_refs.append(f"{relative}: {match}")
        if path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or not verify_packet_seal(value):
            continue
        schema = value.get("schema")
        if schema == "witsoc.research-episode.v1":
            disk_episodes.add(str(value.get("episode_id", "")))
        elif schema in {"witsoc.research-delta.v1", "witsoc.research-delta.v2"}:
            disk_deltas.add(str(value.get("episode_id", "")))
    untracked_episodes = sorted(disk_episodes - issued_ids)
    unimported_deltas = sorted(disk_deltas - returned_ids - pending_ids)
    if untracked_episodes:
        blockers.append({
            "code": "OUT_OF_BAND_EPISODE",
            "detail": f"sealed episode artifacts are absent from kernel history: {untracked_episodes}",
        })
    if unimported_deltas:
        blockers.append({
            "code": "UNIMPORTED_DELTA",
            "detail": f"sealed returns are absent from kernel history: {unimported_deltas}",
        })
    if pending_ids and (disk_episodes - issued_ids or disk_deltas - returned_ids - pending_ids):
        blockers.append({
            "code": "PENDING_STATE_DRIFT",
            "detail": f"state remains pending on {sorted(pending_ids)} while later work exists",
        })
    if pending_ids:
        warnings.append({"code": "WORK_PENDING", "detail": f"pending episode ids: {sorted(pending_ids)}"})
    for digest, names in sorted(content_hashes.items()):
        if len(names) > 1:
            warnings.append({
                "code": "DUPLICATE_BYTES",
                "detail": f"{digest[:12]} is stored at {names}",
            })
    if stale_refs:
        blockers.append({
            "code": "STALE_WORKTREE_REFERENCE",
            "detail": "; ".join(sorted(set(stale_refs))[:12]),
        })
    action = None
    try:
        action, _record = _terminal_record(state)
    except AssuranceError:
        pass
    if action:
        for path in terminal_reports:
            if path.suffix.casefold() in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                if state["state_sha256"] not in text:
                    blockers.append({
                        "code": "STALE_TERMINAL_REPORT",
                        "detail": f"{path.relative_to(task)} does not bind current state bytes",
                    })
    report = seal_packet({
        "schema": CONTROL_REPORT_SCHEMA,
        "report_id": report_id,
        "kind": "CAMPAIGN_AUDIT",
        "target_sha256": state["target"]["canonical_sha256"],
        "source_refs": [state["state_sha256"]],
        "body": {
            "state_revision": state["revision"],
            "state_sha256": state["state_sha256"],
            "files_scanned": len(files),
            "issued_episode_ids": sorted(issued_ids),
            "returned_episode_ids": sorted(returned_ids),
            "pending_episode_ids": sorted(pending_ids),
            "blockers": blockers,
            "warnings": warnings,
            "continuation_allowed": not blockers,
        },
        "disposition": "BLOCKED" if blockers else "READY",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, CONTROL_REPORT_SCHEMA, report)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc


def legacy_audit(
    root: Path,
    value: Mapping[str, Any],
    *,
    report_id: str,
    target_sha256: str | None = None,
) -> dict[str, Any]:
    schema = str(value.get("schema", "UNKNOWN"))
    detected = schema in LEGACY_SCHEMAS or schema.startswith("witsoc.orchestrator-handoff.v")
    target = target_sha256 or value.get("target_sha256")
    if target is not None and (
        not isinstance(target, str) or not re.fullmatch(r"[0-9a-f]{64}", target)
    ):
        raise AssuranceError("legacy audit target is not a SHA-256 digest")
    packet = seal_packet({
        "schema": CONTROL_REPORT_SCHEMA,
        "report_id": report_id,
        "kind": "LEGACY_AUDIT",
        "target_sha256": target,
        "source_refs": [digest_value(value)],
        "body": {
            "detected_schema": schema,
            "legacy_detected": detected,
            "continuation_allowed": False,
            "status_import_allowed": False,
            "disposition": (
                "MIGRATE_FRAME_STATE_ONLY"
                if schema == "frame-state-v1" else "ARCHIVE_AND_RESTART_FROM_PREFLIGHT"
            ),
            "required_active_contracts": [
                ACTIVATION_SCHEMA,
                "witsoc.orchestrator-handoff.v4",
                "witsoc.research-delta.v2",
                FINALIZATION_SCHEMA,
            ],
            "reason": (
                "legacy packets are evidence for audit, not authority for active continuation"
                if detected else "unknown packets cannot enter the active lifecycle"
            ),
        },
        "disposition": "BLOCKED",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, CONTROL_REPORT_SCHEMA, packet)
    except contracts.ContractError as exc:
        raise AssuranceError(str(exc)) from exc
