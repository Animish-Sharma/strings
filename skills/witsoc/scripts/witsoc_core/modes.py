"""Deterministic, sticky routing between Witsoc operating modes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import domain_packages


MODES = (
    "SOURCE_SYNTHESIS",
    "OPEN_DISCOVERY",
    "CLAIM_VERIFICATION",
    "ARTIFACT_PRODUCTION",
    "REPAIR",
    "CROSS_DOMAIN",
)

MODE_REFERENCES = {
    "SOURCE_SYNTHESIS": "references/modes/source_synthesis.md",
    "OPEN_DISCOVERY": "references/modes/open_discovery.md",
    "CLAIM_VERIFICATION": "references/modes/claim_verification.md",
    "ARTIFACT_PRODUCTION": "references/modes/artifact_production.md",
    "REPAIR": "references/modes/repair.md",
    "CROSS_DOMAIN": "references/modes/cross_domain.md",
}

COORDINATION_SCHEMA = "witsoc.coordination.v1"

ROLE_PATHS = {
    "explorer": "explorer/SKILL.md",
    "generator": "generator/SKILL.md",
    "researcher": "researcher/SKILL.md",
}


def skill_resource(relative: str) -> dict[str, str]:
    """Return both local and Plane-safe names for one installed resource."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"invalid skill resource path {relative!r}")
    local_path = path.as_posix()
    return {
        "local_path": local_path,
        "skill_locator": f"witsoc/{local_path}",
    }


def required_roles(mode: str, acting_role: str) -> list[str]:
    roles = ["explorer"]
    if mode in {"OPEN_DISCOVERY", "CROSS_DOMAIN"}:
        roles.append("researcher")
    elif mode in {"ARTIFACT_PRODUCTION", "REPAIR"}:
        roles.append("generator")
    if acting_role not in roles:
        roles.append(acting_role)
    return roles


def activation_resources(mode: str, acting_role: str) -> dict[str, Any]:
    return {
        "root": skill_resource("SKILL.md"),
        "mode": skill_resource(MODE_REFERENCES[mode]),
        "roles": [
            {"role": role, **skill_resource(ROLE_PATHS[role])}
            for role in required_roles(mode, acting_role)
        ],
        "locator_rule": "PLANE_USES_WITSOC_PREFIX_LOCAL_READS_USE_WITSOC_ROOT",
    }

SOURCE_TERMS = (
    "status lookup", "known result", "what is known", "literature", "survey",
    "state of the art", "source synthesis", "prior work", "current status",
)
DISCOVERY_TERMS = (
    "open problem", "unsolved", "new discovery", "discover", "solve", "attack",
    "deep-attack", "deep attack", "remaining obstruction", "is open",
    "genuinely-new mathematics", "genuinely new mathematics", "improve the bound",
    "new mechanism", "new result", "research frontier",
    "explorer to researcher loop", "investigate the growth rate", "growth rate",
    "order of magnitude", "asymptotic behavior", "asymptotic growth",
)
OPEN_QUESTION = re.compile(
    r"(?<![\w-])open(?:[ -]+[\w-]+){0,6}[ -]+(?:problem|question|conjecture|obstruction)(?![\w-])",
    re.IGNORECASE,
)
VERIFY_TERMS = (
    "verify", "audit", "check this claim", "replicate", "reproduce", "validate",
    "establish or refute", "prove or disprove", "is this claim true",
)
PRODUCTION_TERMS = (
    "produce an artifact", "formalize", "render", "compile the argument",
    "make checkable", "build the candidate",
)
REPAIR_TERMS = (
    "repair", "failed check", "diagnostic", "stale receipt", "fix the artifact",
    "verification failure", "admission refused",
)


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    normalized = " ".join(text.casefold().split())
    normalized = normalized.replace("->", " to ").replace("\u2192", " to ")
    normalized = " ".join(normalized.split())
    return [term for term in terms if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", normalized)]


def coordination_contract(mode: str) -> dict[str, Any]:
    """Expose host obligations that must survive orchestration projection."""
    discovery = mode in {"OPEN_DISCOVERY", "CROSS_DOMAIN"}
    return {
        "schema": COORDINATION_SCHEMA,
        "owner": "CURRENT_INVOCATION",
        "child_role_scope": "CURRENT_SESSION_TREE",
        "nested_root_orchestrator": "FORBIDDEN_UNLESS_USER_EXPLICITLY_REQUESTS",
        "workspace_binding": "PRESERVE_USER_SPECIFIED_PATHS",
        "worker_workspace": {
            "default": "INHERIT_BOUND",
            "isolated": "REQUIRES_BASE_REVISION_AND_DECLARED_ARTIFACT_RETURN",
        },
        "activation_gate": "PREFLIGHT_READY_BEFORE_RUN_ARTIFACTS",
        "dispatch_is_completion": False,
        "pending_worker_action": "YIELD_AND_RESUME_ON_BOUND_RETURN",
        "stage_order": (
            [
                "EXPLORER_DECISION",
                "RESEARCHER_DELTA_IF_AUTHORIZED",
                "EXPLORER_RETURN_ARBITRATION",
                "FRONTIER_EXPANSION_OR_RESUMABLE_PAUSE",
            ]
            if discovery
            else ["MODE_WORK", "EXPLORER_RETURN_ARBITRATION"]
        ),
        "terminal_stage_results": (
            ["PAUSE_WITH_FRONTIER", "HONEST_STOP", "EXPLORER_ARBITRATED_DELTA"]
            if discovery
            else ["EXPLORER_ARBITRATED_RESULT"]
        ),
        "completion_requires": (
            ["BOUND_DELTA_IMPORTED", "EXPLORER_ARBITRATED"]
            if discovery
            else ["BOUND_RESULT_IMPORTED", "EXPLORER_ARBITRATED"]
        ),
    }


def choose_mode(statement: str, intent: str | None = None, *, ambiguous_domain: bool = False) -> dict[str, Any]:
    if intent:
        requested = intent.strip().upper().replace("-", "_")
        if requested not in MODES:
            raise ValueError(f"unsupported mode {intent!r}; choose one of {', '.join(MODES)}")
        return {"mode": requested, "basis": ["explicit intent"], "sticky": True}

    discovery_hits = _hits(statement, DISCOVERY_TERMS)
    if OPEN_QUESTION.search(" ".join(statement.split())):
        discovery_hits.append("open <field> problem/question/conjecture/obstruction")
    groups = {
        "source": _hits(statement, SOURCE_TERMS),
        "discovery": list(dict.fromkeys(discovery_hits)),
        "verification": _hits(statement, VERIFY_TERMS),
        "production": _hits(statement, PRODUCTION_TERMS),
        "repair": _hits(statement, REPAIR_TERMS),
    }
    if ambiguous_domain:
        mode, basis = "CROSS_DOMAIN", ["multiple domain packs qualify"]
    elif groups["repair"]:
        mode, basis = "REPAIR", groups["repair"]
    elif groups["source"] and not groups["discovery"]:
        mode, basis = "SOURCE_SYNTHESIS", groups["source"]
    elif groups["discovery"]:
        mode, basis = "OPEN_DISCOVERY", groups["discovery"]
    elif groups["verification"]:
        mode, basis = "CLAIM_VERIFICATION", groups["verification"]
    elif groups["production"]:
        mode, basis = "ARTIFACT_PRODUCTION", groups["production"]
    elif groups["source"]:
        mode, basis = "SOURCE_SYNTHESIS", groups["source"]
    else:
        mode, basis = "CLAIM_VERIFICATION", ["default for a precise research claim"]
    return {"mode": mode, "basis": basis, "sticky": True, "signals": groups}


def route(
    root: Path,
    statement: str,
    intent: str | None = None,
    domain: str | None = None,
    role: str = "explorer",
) -> dict[str, Any]:
    # Reuse the established pack scorer so the new shell cannot drift from the
    # compatibility entry point.
    import resolve_domain

    mode = choose_mode(statement, intent)
    try:
        installable = domain_packages.routing_packs(root)
        if domain:
            selected_packages = [
                pack for pack in installable if pack["domain"] == domain
            ]
            package_resolution: dict[str, Any] = {
                "decision": "SELECTED" if selected_packages else "NOT_APPLICABLE",
                "domain": domain if selected_packages else None,
                "by": "explicit" if selected_packages else None,
                "scores": [],
            }
        else:
            package_resolution = resolve_domain.decide(
                installable, resolve_domain.normalize(statement)
            )
            names = package_resolution.get("candidates") or (
                [package_resolution["domain"]] if package_resolution.get("domain") else []
            )
            selected_packages = [pack for pack in installable if pack["domain"] in names]
        requested_packages = [pack["domain"] for pack in selected_packages]
        if requested_packages:
            package_activation = domain_packages.ensure_domains(root, requested_packages)
        else:
            package_activation = {
                "schema": "witsoc.domain-package-activation.v1",
                "ok": True,
                "requested": [],
                "actions": [],
                "side_effects": [],
                "problems": [],
            }
    except domain_packages.DomainPackageError as exc:
        package_resolution = {"decision": "UNRESOLVABLE", "scores": []}
        package_activation = {
            "schema": "witsoc.domain-package-activation.v1",
            "ok": False,
            "requested": [],
            "actions": [],
            "side_effects": [],
            "problems": [str(exc)],
        }
    if not package_activation["ok"]:
        return {
            "schema": "witsoc.route.v1",
            "activation": "WITSOC",
            "sticky": True,
            "decision": "UNRESOLVABLE",
            "mode": mode["mode"],
            "mode_basis": mode["basis"],
            "domains": package_activation.get("requested", []),
            "domain_packages": {
                "resolution": package_resolution,
                "activation": package_activation,
            },
            "problems": package_activation["problems"],
        }

    packs, load_problems = resolve_domain.load_packs()
    if load_problems:
        return {
            "schema": "witsoc.route.v1",
            "activation": "WITSOC",
            "decision": "UNRESOLVABLE",
            "mode": None,
            "domains": [],
            "domain_packages": {
                "resolution": package_resolution,
                "activation": package_activation,
            },
            "problems": load_problems,
        }
    if domain:
        selected = [pack for pack in packs if pack.get("domain", pack["_dir"].name) == domain]
        if not selected:
            decision: dict[str, Any] = {"decision": "NO_MATCH", "domain": None, "scores": []}
        else:
            decision = {"decision": "SELECTED", "domain": domain, "by": "explicit", "scores": []}
    else:
        decision = resolve_domain.decide(packs, resolve_domain.normalize(statement))
    decision = resolve_domain.attach_plan(decision, packs)
    ambiguous = decision.get("decision") == "AMBIGUOUS"
    mode = choose_mode(statement, intent, ambiguous_domain=ambiguous)
    domains = decision.get("candidates") or ([decision["domain"]] if decision.get("domain") else [])
    return {
        "schema": "witsoc.route.v1",
        "activation": "WITSOC",
        "sticky": True,
        "decision": decision.get("decision"),
        "mode": mode["mode"],
        "mode_basis": mode["basis"],
        "mode_reference": MODE_REFERENCES[mode["mode"]],
        "domains": domains,
        "domain_resolution": decision,
        "domain_packages": {
            "resolution": package_resolution,
            "activation": package_activation,
        },
        "must_not_delegate_evidence_contract": True,
        "coordination": coordination_contract(mode["mode"]),
        "activation_resources": activation_resources(mode["mode"], role),
    }
