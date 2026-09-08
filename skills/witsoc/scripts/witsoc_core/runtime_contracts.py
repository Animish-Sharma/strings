"""Compile and check deterministic runtime architecture and context contracts."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from . import (
    capabilities,
    capability_graph,
    contracts,
    domain_packages,
    modes,
    operators,
    reasoning,
)
from .canonical import canonical_json, digest_file, digest_value, load_json


BUDGET_SCHEMA = "witsoc.runtime-budgets.v1"
CONTRACT_SCHEMA = "witsoc.runtime-contract.v1"
ARCHITECTURE_SCHEMA = "witsoc.runtime-architecture.v1"
CONTRACT_PATH = Path("references/runtime_contracts.json")
CONTRACT_DOC_PATH = Path("references/runtime_contracts.md")
FRONTMATTER = re.compile(r"^---\n([\s\S]*?)\n---")


class RuntimeContractError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise RuntimeContractError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RuntimeContractError(f"{label} must be a positive integer")
    return value


def load_budgets(root: Path) -> dict[str, Any]:
    try:
        value = load_json(root / "references" / "runtime_budgets.json")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"cannot read runtime budgets: {exc}") from exc
    _closed(
        value,
        {
            "schema", "version", "documents", "capsules", "capabilities",
            "operators", "rounds", "release", "activation",
        },
        "runtime budgets",
    )
    if value["schema"] != BUDGET_SCHEMA or value["version"] != 1:
        raise RuntimeContractError("unsupported runtime budget contract")
    expected_sections = {
        "capsules": {"default_tokens", "maximum_tokens"},
        "capabilities": {"maximum_node_context_tokens", "maximum_load_plan_tokens"},
        "operators": {"default_selected", "maximum_selected", "maximum_plan_context_tokens"},
        "rounds": {"default_parallel", "maximum_parallel"},
        "release": {"maximum_files", "maximum_bytes"},
        "activation": {"name", "description_terms", "body_terms", "forbidden_body_terms"},
    }
    for section, keys in expected_sections.items():
        if not isinstance(value[section], dict):
            raise RuntimeContractError(f"runtime budget section {section!r} must be an object")
        _closed(value[section], keys, f"runtime budget {section}")
    if not isinstance(value["documents"], dict) or not value["documents"]:
        raise RuntimeContractError("runtime document budgets must be a non-empty object")
    for path, maximum in value["documents"].items():
        if not isinstance(path, str) or not path or not (root / path).is_file():
            raise RuntimeContractError(f"budgeted runtime document is missing: {path!r}")
        _positive_int(maximum, f"document budget {path}")
    for section in ("capsules", "capabilities", "operators", "rounds", "release"):
        for key, raw in value[section].items():
            _positive_int(raw, f"{section}.{key}")
    if value["capsules"]["default_tokens"] > value["capsules"]["maximum_tokens"]:
        raise RuntimeContractError("default capsule budget exceeds its maximum")
    if value["operators"]["default_selected"] > value["operators"]["maximum_selected"]:
        raise RuntimeContractError("default operator count exceeds its maximum")
    if value["rounds"]["default_parallel"] > value["rounds"]["maximum_parallel"]:
        raise RuntimeContractError("default round width exceeds its maximum")
    activation = value["activation"]
    if not isinstance(activation["name"], str) or not activation["name"]:
        raise RuntimeContractError("activation name is empty")
    for key in ("description_terms", "body_terms", "forbidden_body_terms"):
        terms = activation[key]
        if not isinstance(terms, list) or any(
            not isinstance(term, str) or not term.strip() for term in terms
        ):
            raise RuntimeContractError(f"activation.{key} must contain non-empty strings")
    return copy.deepcopy(value)


def operator_limits(root: Path) -> dict[str, int]:
    return copy.deepcopy(load_budgets(root)["operators"])


def capsule_limits(root: Path) -> dict[str, int]:
    return copy.deepcopy(load_budgets(root)["capsules"])


def _frontmatter_scalar(content: str, key: str) -> str | None:
    match = FRONTMATTER.match(content)
    if not match:
        return None
    field = re.search(rf"^{re.escape(key)}:\s*(.+)$", match.group(1), re.MULTILINE)
    if not field:
        return None
    return re.sub(r"^[\"']|[\"']$", "", field.group(1).strip())


def _activation_report(root: Path, budgets: Mapping[str, Any]) -> dict[str, Any]:
    content = (root / "SKILL.md").read_text(encoding="utf-8")
    description = _frontmatter_scalar(content, "description") or ""
    activation = budgets["activation"]
    problems: list[str] = []
    if _frontmatter_scalar(content, "name") != activation["name"]:
        problems.append("SKILL.md activation name differs from the runtime contract")
    normalized_description = " ".join(description.casefold().split())
    normalized_body = " ".join(content.casefold().split())
    for term in activation["description_terms"]:
        if term.casefold() not in normalized_description:
            problems.append(f"SKILL.md description omits activation term {term!r}")
    for term in activation["body_terms"]:
        if term.casefold() not in normalized_body:
            problems.append(f"SKILL.md body omits retention term {term!r}")
    for term in activation["forbidden_body_terms"]:
        if term.casefold() in normalized_body:
            problems.append(f"SKILL.md contains forbidden routing phrase {term!r}")
    return {
        "name": _frontmatter_scalar(content, "name"),
        "description_characters": len(description),
        "description_terms": len(activation["description_terms"]),
        "body_terms": len(activation["body_terms"]),
        "problems": problems,
    }


def _operator_report(root: Path, allowed_domains: set[str]) -> tuple[dict[str, Any], list[str]]:
    manifests = sorted(
        root / "domains" / domain / "operators.json"
        for domain in allowed_domains
        if (root / "domains" / domain / "operators.json").is_file()
    )
    domains: list[dict[str, Any]] = []
    problems: list[str] = []
    maximum_single = 0
    total = 0
    for path in manifests:
        manifest = operators.load_manifest(root, path.parent.name)
        total += len(manifest["operators"])
        doctrine_sizes = []
        for item in manifest["operators"]:
            size = sum((root / relative).stat().st_size for relative in item["doctrine"]) // 4
            doctrine_sizes.append(size)
            maximum_single = max(maximum_single, size)
        domains.append({
            "id": manifest["domain"],
            "operators": len(manifest["operators"]),
            "maximum_single_context_tokens": max(doctrine_sizes, default=0),
        })
    if not domains:
        problems.append("no domain operator registries are installed")
    return {
        "domains": domains,
        "domain_count": len(domains),
        "operator_count": total,
        "maximum_single_context_tokens": maximum_single,
    }, problems


def _load_profiles(root: Path, operator_domains: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    profiles: list[dict[str, Any]] = []
    problems: list[str] = []
    cases = (
        ("source-explorer", "SOURCE_SYNTHESIS", "explorer"),
        ("open-explorer", "OPEN_DISCOVERY", "explorer"),
        ("open-researcher", "OPEN_DISCOVERY", "researcher"),
    )
    for domain in operator_domains:
        for profile_id, mode, role in cases:
            plan = capabilities.build_load_plan(root, mode, [domain], role, "")
            if not plan["ok"]:
                problems.append(f"load profile {domain}/{profile_id} is unreachable")
                continue
            profiles.append({
                "id": f"{domain}:{profile_id}",
                "mode": mode,
                "role": role,
                "capabilities": len(plan["capabilities"]),
                "context_tokens": plan["estimated_tokens"],
            })
    if len(operator_domains) > 1:
        plan = capabilities.build_load_plan(
            root, "CROSS_DOMAIN", operator_domains, "explorer", "cross-domain transfer"
        )
        if not plan["ok"]:
            problems.append("combined cross-domain Explorer load profile is unreachable")
        else:
            profiles.append({
                "id": "combined:cross-domain-explorer",
                "mode": "CROSS_DOMAIN",
                "role": "explorer",
                "capabilities": len(plan["capabilities"]),
                "context_tokens": plan["estimated_tokens"],
            })
    return profiles, problems


def _fixed_inputs(root: Path) -> list[Path]:
    runtime_modules = sorted(
        path for path in (root / "scripts" / "witsoc_core").glob("*.py")
        if path.name != "advanced_selftest.py"
    )
    return [
        root / "SKILL.md",
        root / "explorer" / "SKILL.md",
        root / "generator" / "SKILL.md",
        root / "researcher" / "SKILL.md",
        root / "scripts" / "route.py",
        root / "references" / "runtime_architecture.json",
        root / "references" / "runtime_architecture.md",
        root / "references" / "runtime_budgets.json",
        root / "references" / "domain_packages.md",
        root / "references" / "orchestrator_protocol.md",
        root / "references" / "researcher_reasoning.md",
        root / "references" / "runtime_release.json",
        root / "references" / "runtime_sync.json",
        root / "contracts" / "type-registry.json",
        root / "contracts" / "capability-policy.json",
        root / "contracts" / "bridge-adapters.json",
        root / "contracts" / "domain-packages.json",
        *runtime_modules,
    ]


def _core_input_digest(root: Path) -> str:
    discovered = sorted((root / "capabilities").glob("*.json"))
    inputs = sorted(set(_fixed_inputs(root) + discovered), key=lambda path: path.as_posix())
    return digest_value([digest_file(path) for path in inputs])


def _input_digest(root: Path, allowed_domains: set[str]) -> str:
    fixed = _fixed_inputs(root)
    discovered = [
        root / "domains" / domain / name
        for domain in sorted(allowed_domains)
        for name in ("capabilities.json", "operators.json", "packet-types.json")
        if (root / "domains" / domain / name).is_file()
    ]
    discovered += sorted((root / "capabilities").glob("*.json"))
    for record in contracts.load_registry(root)["types"]:
        discovered.append(root / record["schema_path"])
    for item in capabilities.all_capabilities(root):
        if item["owner"] not in {"frame", *allowed_domains}:
            continue
        discovered.extend(root / relative for relative in item["load"])
    for manifest_path in sorted(
        root / "domains" / domain / "operators.json"
        for domain in allowed_domains
        if (root / "domains" / domain / "operators.json").is_file()
    ):
        manifest = operators.load_manifest(root, manifest_path.parent.name)
        for item in manifest["operators"]:
            discovered.extend(root / relative for relative in item["doctrine"])
    inputs = sorted(set(fixed + discovered), key=lambda path: path.as_posix())
    return digest_value([digest_file(path) for path in inputs])


def _internal_alias_uses(root: Path, allowed_domains: set[str]) -> list[dict[str, str]]:
    registry = contracts.load_registry(root)
    aliases = {
        alias
        for record in registry["types"]
        for alias in record["compatible_from"]
    }
    uses: list[dict[str, str]] = []
    for item in capabilities.all_capabilities(root):
        if item["owner"] not in {"frame", *allowed_domains}:
            continue
        for field in ("inputs", "outputs"):
            for packet in item[field]:
                if packet in aliases:
                    uses.append({"owner": item["owner"], "capability": item["id"], "packet": packet})
    policy = load_json(root / "contracts" / "capability-policy.json")
    for capability_id, packets in policy["optional_inputs"].items():
        for packet in packets:
            if packet in aliases:
                uses.append({"owner": "policy", "capability": capability_id, "packet": packet})
    for index, route in enumerate(policy["routes"]):
        for field in ("available", "goals"):
            for packet in route[field]:
                if packet in aliases:
                    uses.append({
                        "owner": "policy",
                        "capability": f"route:{index}:{field}",
                        "packet": packet,
                    })
    return sorted(uses, key=lambda item: (item["owner"], item["capability"], item["packet"]))


def build(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    budgets = load_budgets(root)
    try:
        architecture = load_json(root / "references" / "runtime_architecture.json")
        release = load_json(root / "references" / "runtime_release.json")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"cannot read runtime policy: {exc}") from exc
    if architecture.get("schema") != ARCHITECTURE_SCHEMA:
        raise RuntimeContractError("runtime architecture schema is invalid")
    package_registry = domain_packages.load_registry(root)
    packaged_domains = {item["domain"] for item in package_registry["packages"]}
    missing_packages = sorted(
        domain for domain in packaged_domains
        if not (root / "domains" / domain / "capabilities.json").is_file()
    )
    if missing_packages:
        raise RuntimeContractError(
            "cannot compile the complete runtime contract without installed packs: "
            + ", ".join(missing_packages)
        )
    graph = capability_graph.compile_graph(root, packaged_domains)
    operator_report, operator_problems = _operator_report(root, packaged_domains)
    operator_domains = [item["id"] for item in operator_report["domains"]]
    profiles, profile_problems = _load_profiles(root, operator_domains)
    registry = contracts.registry_report(root)
    internal_aliases = _internal_alias_uses(root, packaged_domains)
    activation = _activation_report(root, budgets)
    documents = [
        {
            "path": path,
            "bytes": (root / path).stat().st_size,
            "maximum_bytes": maximum,
        }
        for path, maximum in sorted(budgets["documents"].items())
    ]
    maximum_node = max(graph["nodes"], key=lambda item: item["context_tokens"])
    base = {
        "schema": CONTRACT_SCHEMA,
        "version": int(architecture.get("version", 0)),
        "inputs_sha256": _input_digest(root, packaged_domains),
        "domain_packages": {
            "core_api": package_registry["core_api"],
            "registry_sha256": digest_file(root / domain_packages.REGISTRY_PATH),
            "core_inputs_sha256": _core_input_digest(root),
            "count": len(package_registry["packages"]),
            "packages": [
                {
                    key: item[key]
                    for key in (
                        "domain", "distribution", "version", "payload_sha256",
                        "payload_files", "payload_bytes",
                    )
                }
                for item in package_registry["packages"]
            ],
        },
        "architecture": {
            "layers": len(architecture.get("layers", [])),
            "invariants": len(architecture.get("invariants", [])),
        },
        "activation": {key: value for key, value in activation.items() if key != "problems"},
        "contracts": {
            "registry_version": registry["version"],
            "packet_types": registry["type_count"],
            "aliases": registry["aliases"],
            "internal_alias_uses": len(internal_aliases),
            "status_authority": registry["status_authority"],
        },
        "capabilities": {
            "nodes": len(graph["nodes"]),
            "edges": graph["edge_count"],
            "admission_authority": graph["admission_authority"],
            "maximum_node": maximum_node["id"],
            "maximum_node_context_tokens": maximum_node["context_tokens"],
            "load_profiles": profiles,
            "maximum_load_plan_tokens": max(
                (item["context_tokens"] for item in profiles), default=0
            ),
        },
        "operators": operator_report,
        "documents": documents,
        "limits": {
            "capsules": copy.deepcopy(budgets["capsules"]),
            "capabilities": copy.deepcopy(budgets["capabilities"]),
            "operators": copy.deepcopy(budgets["operators"]),
            "rounds": copy.deepcopy(budgets["rounds"]),
            "release": copy.deepcopy(budgets["release"]),
        },
        "controls": {
            "pending_work_kinds": ["EPISODE", "ROUND"],
            "hints_are_evidence": False,
            "bridge_loss_is_explicit": True,
            "bridge_transforms_are_executable": True,
            "operator_contracts_are_bound": True,
            "reasoning_state_required_for_new_handoff": True,
            "typed_loop_messages_required": True,
            "portfolio_recoupling_is_derived": True,
            "reasoning_limits": copy.deepcopy(reasoning.FIXED_LIMITS),
            "closure_safe_evidence": ["EXACT", "SOURCE_VERIFIED"],
            "raw_deliberation_retained": False,
            "novelty_implies_correctness": False,
            "state_checkpoint_is_authority": False,
            "successor_selected_by_return": False,
            "coordination": modes.coordination_contract("OPEN_DISCOVERY"),
        },
    }
    problems = operator_problems + profile_problems + activation["problems"]
    if internal_aliases:
        problems.append(f"runtime capability contracts use legacy aliases: {internal_aliases[:8]}")
    problems.extend(
        f"{item['path']} exceeds its document budget"
        for item in documents if item["bytes"] > item["maximum_bytes"]
    )
    limits = budgets["capabilities"]
    if maximum_node["context_tokens"] > limits["maximum_node_context_tokens"]:
        problems.append(
            f"capability {maximum_node['id']} exceeds the node context budget"
        )
    oversized_profiles = [
        item["id"] for item in profiles
        if item["context_tokens"] > limits["maximum_load_plan_tokens"]
    ]
    if oversized_profiles:
        problems.append(f"load profiles exceed the context budget: {oversized_profiles}")
    if release.get("max_files") != budgets["release"]["maximum_files"]:
        problems.append("release file limit differs from runtime budgets")
    if release.get("max_bytes") != budgets["release"]["maximum_bytes"]:
        problems.append("release byte limit differs from runtime budgets")
    if architecture.get("version") != 11:
        problems.append("runtime architecture is not version 11")
    if problems:
        raise RuntimeContractError("; ".join(problems))
    base["content_sha256"] = digest_value(base)
    return base


def render_markdown(contract: Mapping[str, Any]) -> str:
    capability = contract["capabilities"]
    limits = contract["limits"]
    coordination = contract["controls"]["coordination"]
    return (
        "# Runtime contract\n\n"
        "This file is generated deterministically by `scripts/generate_contracts.py`. "
        "Edit the source policies, then regenerate it.\n\n"
        f"- Architecture: v{contract['version']}, {contract['architecture']['layers']} layers\n"
        f"- Packet types: {contract['contracts']['packet_types']}; status authority: "
        f"`{contract['contracts']['status_authority']}`\n"
        f"- Capability graph: {capability['nodes']} nodes, {capability['edges']} edges\n"
        f"- Largest capability context: {capability['maximum_node_context_tokens']} / "
        f"{limits['capabilities']['maximum_node_context_tokens']} tokens\n"
        f"- Largest required load profile: {capability['maximum_load_plan_tokens']} / "
        f"{limits['capabilities']['maximum_load_plan_tokens']} tokens\n"
        f"- Operators: {contract['operators']['operator_count']} across "
        f"{contract['operators']['domain_count']} domain registries; default selection "
        f"{limits['operators']['default_selected']}\n"
        f"- Domain distributions: {contract['domain_packages']['count']} pinned packs; "
        f"core API {contract['domain_packages']['core_api']}\n"
        f"- Capsule budget: {limits['capsules']['default_tokens']} default, "
        f"{limits['capsules']['maximum_tokens']} maximum tokens\n"
        f"- Independent round width: {limits['rounds']['default_parallel']} default, "
        f"{limits['rounds']['maximum_parallel']} maximum\n"
        f"- Coordination owner: `{coordination['owner']}`; nested root: "
        f"`{coordination['nested_root_orchestrator']}`; dispatch completes loop: "
        f"`{str(coordination['dispatch_is_completion']).lower()}`; activation gate: "
        f"`{coordination['activation_gate']}`\n"
        f"- Contract digest: `{contract['content_sha256']}`\n"
    )


def _thin_contract_problems(root: Path, actual: Mapping[str, Any]) -> list[str]:
    """Validate a generated full contract when one or more packs are dormant."""
    problems: list[str] = []
    if actual.get("schema") != CONTRACT_SCHEMA or actual.get("version") != 11:
        return ["generated runtime contract has an unsupported schema or version"]
    sealed = dict(actual)
    declared_digest = sealed.pop("content_sha256", None)
    if declared_digest != digest_value(sealed):
        problems.append("generated runtime contract content digest is invalid")
    try:
        registry = domain_packages.load_registry(root)
        package_contract = actual["domain_packages"]
        expected_packages = [
            {
                key: item[key]
                for key in (
                    "domain", "distribution", "version", "payload_sha256",
                    "payload_files", "payload_bytes",
                )
            }
            for item in registry["packages"]
        ]
        if package_contract.get("core_api") != registry["core_api"]:
            problems.append("generated runtime contract has a stale domain core API")
        if package_contract.get("registry_sha256") != digest_file(
            root / domain_packages.REGISTRY_PATH
        ):
            problems.append("generated runtime contract has a stale package registry digest")
        if package_contract.get("core_inputs_sha256") != _core_input_digest(root):
            problems.append("generated runtime contract has stale core input bytes")
        if package_contract.get("packages") != expected_packages:
            problems.append("generated runtime contract has stale package identities")
    except (KeyError, TypeError, domain_packages.DomainPackageError) as exc:
        problems.append(f"generated runtime package contract is invalid: {exc}")
    try:
        budgets = load_budgets(root)
        expected_limits = {
            "capsules": copy.deepcopy(budgets["capsules"]),
            "capabilities": copy.deepcopy(budgets["capabilities"]),
            "operators": copy.deepcopy(budgets["operators"]),
            "rounds": copy.deepcopy(budgets["rounds"]),
            "release": copy.deepcopy(budgets["release"]),
        }
        if actual.get("limits") != expected_limits:
            problems.append("generated runtime contract has stale budget limits")
        activation = _activation_report(root, budgets)
        if activation["problems"] or actual.get("activation") != {
            key: value for key, value in activation.items() if key != "problems"
        }:
            problems.append("generated runtime contract has stale activation metadata")
        documents = [
            {
                "path": path,
                "bytes": (root / path).stat().st_size,
                "maximum_bytes": maximum,
            }
            for path, maximum in sorted(budgets["documents"].items())
        ]
        if actual.get("documents") != documents:
            problems.append("generated runtime contract has stale document measurements")
        architecture = load_json(root / "references" / "runtime_architecture.json")
        expected_architecture = {
            "layers": len(architecture.get("layers", [])),
            "invariants": len(architecture.get("invariants", [])),
        }
        if actual.get("architecture") != expected_architecture:
            problems.append("generated runtime contract has stale architecture metadata")
    except (OSError, KeyError, TypeError, json.JSONDecodeError, RuntimeContractError) as exc:
        problems.append(f"cannot verify the thin runtime contract: {exc}")
    return problems


def check(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    problems: list[str] = []
    try:
        actual = load_json(root / CONTRACT_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        actual = None
        problems.append(f"cannot read generated runtime contract: {exc}")
    registry = domain_packages.load_registry(root)
    installed = {
        path.parent.name for path in (root / "domains").glob("*/capabilities.json")
    }
    required = {item["domain"] for item in registry["packages"]}
    expected: Mapping[str, Any] | None = None
    if actual is not None:
        if required <= installed:
            expected = build(root)
            if actual != expected:
                problems.append("generated runtime contract is stale")
        else:
            expected = actual
            problems.extend(_thin_contract_problems(root, actual))
    expected_doc = render_markdown(expected) if expected is not None else ""
    try:
        actual_doc = (root / CONTRACT_DOC_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        actual_doc = ""
        problems.append(f"cannot read generated runtime contract documentation: {exc}")
    if actual_doc != expected_doc:
        problems.append("generated runtime contract documentation is stale")
    return {
        "ok": not problems,
        "problems": problems,
        "content_sha256": expected["content_sha256"] if expected is not None else None,
        "architecture_version": expected["version"] if expected is not None else None,
        "capabilities": expected["capabilities"]["nodes"] if expected is not None else None,
        "operators": expected["operators"]["operator_count"] if expected is not None else None,
        "maximum_load_plan_tokens": (
            expected["capabilities"]["maximum_load_plan_tokens"]
            if expected is not None else None
        ),
    }


def canonical_output(contract: Mapping[str, Any]) -> str:
    """Expose stable compact bytes for callers that need a content comparison."""
    return canonical_json(contract)
