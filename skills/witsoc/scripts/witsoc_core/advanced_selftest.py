"""Synthetic checks for coordination, rounds, memory, bridges, and budgets."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import (
    assurance,
    bridges,
    capabilities,
    capability_graph,
    capsules,
    contracts,
    discovery,
    domain_packages,
    hint_memory,
    exploration,
    kernel,
    modes,
    orchestration,
    reasoning,
    rounds,
    runtime_contracts,
)
from .canonical import seal_packet


def _finish_no_progress(draft: dict[str, Any]) -> dict[str, Any]:
    """Fill a v2 draft with the smallest semantically complete failed attack."""
    graph = draft["reasoning"]
    graph["phase"] = "RETURN"
    graph["hypotheses"] = [{
        "hypothesis_id": "H1",
        "statement": "the assigned mechanism may control the target claim",
        "mechanism": "the assigned route supplies the missing control",
        "discriminator": "derive the required bound under the frozen assumptions",
        "predicted_failure": "the required control remains unavailable",
        "claim_ids": ["TARGET"],
        "status": "REJECTED",
    }]
    graph["attacks"] = [{
        "attack_id": "A1",
        "claim_id": "TARGET",
        "objection": "the assigned mechanism may not provide the required control",
        "test": "audit the decisive dependency under the frozen assumptions",
        "result": "FAILED",
        "repair": "retain the exact missing dependency",
        "evidence_refs": [],
    }]
    graph["attempts"] = [{
        "attempt_id": "T1",
        "hypothesis_id": "H1",
        "method_family": "assigned-route audit",
        "changed_axis": "decisive discriminator",
        "fixed_axes": ["target", "assumptions", "direction"],
        "result": "INCONCLUSIVE",
        "failure_class": "genuine_obstruction",
        "failure_domain": "synthetic-assigned-route",
        "diagnostic": "the required dependency was not derived",
        "obligation_delta": "SAME",
        "evidence_refs": [],
    }]
    graph["pivotal_claim_ids"] = ["TARGET"]
    graph["subgoals"][0]["status"] = "BLOCKED"
    graph["first_failing_gate"] = "the decisive dependency was not derived"
    draft["next_proposals"] = [{
        "proposal_id": f"followup:{draft['episode_id']}",
        "node_id": "CORE",
        "lane": "TRANSFER",
        "route": {
            "method_family": "representation pivot",
            "mechanism": "translate the residual dependency to an invariant-preserving dual model",
            "structural_object": "dual synthetic obstruction",
            "required_result": "separate the surviving alternatives by an exact invariant",
            "target_effect": "strictly sharpen the retained open core",
            "assumptions": [],
        },
        "objective": "test a representation-distinct residual route",
        "evaluator": "one bidirectional implication or a translation countermodel",
        "expected_delta": "a strict residual reduction or scoped method barrier",
        "return_condition": "return after the exact translation discriminator is decided",
        "changed_axis": "representation",
        "revival_evidence": "the assigned direct mechanism returned its exact failing dependency",
        "features": {
            "target_leverage": 0.8,
            "expected_information_gain": 0.9,
            "checkability": 0.8,
            "reversibility": 0.9,
            "novelty": 0.8,
            "transfer_value": 0.9,
            "cost": 0.3,
            "recoupling_risk": 0.1,
        },
    }]
    return draft


def _promotion_reasoning(
    graph: dict[str, Any], *, evidence_class: str = "EXACT", off_route: bool = False
) -> dict[str, Any]:
    """Build a minimal promotion-shaped graph for semantic negative controls."""
    inference = {
        "EXACT": "DEDUCTION",
        "SOURCE_VERIFIED": "SOURCE_IMPORT",
        "COMPUTATIONAL_BOUNDED": "BOUNDED_CHECK",
        "EMPIRICAL": "OBSERVATION",
        "HEURISTIC": "ANALOGY",
        "CONJECTURAL": "ANALOGY",
        "SEARCH_BOUNDED": "SEARCH_SCOPE",
        "UNKNOWN": "GIVEN",
    }[evidence_class]
    needs_ref = evidence_class in {
        "SOURCE_VERIFIED", "COMPUTATIONAL_BOUNDED", "EMPIRICAL", "SEARCH_BOUNDED",
    }
    graph["claims"].append({
        "claim_id": "C1",
        "statement": "the decisive route-local consequence holds",
        "kind": "SIDE_RESULT" if off_route else "CONCLUSION",
        "epistemic_class": evidence_class,
        "status": "SUPPORTED",
        "depends_on": [],
        "inference": inference,
        "warrant": "the recorded derivation or observation supports this exact scope",
        "evidence_refs": ["evidence:bounded-scope"] if needs_ref else [],
        "defeaters": [],
        "target_link": "SIDE" if off_route else "DIRECT",
        "route_scope": "OFF_ROUTE" if off_route else "ASSIGNED",
    })
    graph["hypotheses"] = [{
        "hypothesis_id": "H1",
        "statement": "the route-local consequence decides the assigned claim",
        "mechanism": "a direct dependency carries the consequence",
        "discriminator": "attack the dependency under the frozen assumptions",
        "predicted_failure": "an assumption or direction mismatch breaks the dependency",
        "claim_ids": ["C1"],
        "status": "SUPPORTED",
    }]
    graph["attacks"] = [{
        "attack_id": "A1",
        "claim_id": "C1",
        "objection": "the dependency may fail at a boundary or assumption",
        "test": "check direction, scope, assumptions, and boundary cases",
        "result": "SURVIVED",
        "repair": "",
        "evidence_refs": [],
    }]
    graph["attempts"] = [{
        "attempt_id": "T1",
        "hypothesis_id": "H1",
        "method_family": "direct dependency audit",
        "changed_axis": "decisive dependency",
        "fixed_axes": ["target", "scope", "assumptions"],
        "result": "SUPPORTED",
        "failure_class": "NONE",
        "failure_domain": "NONE",
        "diagnostic": "the exact scoped dependency survived the declared attack",
        "obligation_delta": "REDUCED",
        "evidence_refs": [],
    }]
    graph["pivotal_claim_ids"] = ["C1"]
    graph["closure_candidate_ids"] = ["C1"]
    graph["phase"] = "RETURN"
    graph["subgoals"][0]["claim_id"] = "C1"
    graph["subgoals"][0]["status"] = "DISCHARGED"
    graph["invariants"][0]["status"] = "PRESERVED"
    graph["requested_outcome"] = "FALSIFICATION"
    graph["claims"][0]["status"] = "REFUTED"
    graph["target_fidelity"]["claim_checks"] = [{
        "claim_id": "C1",
        "relation": "SIDE_RESULT" if off_route else "REFUTES_TARGET",
        "clause_results": [
            {
                "clause_id": clause_id,
                "status": (
                    "NOT_APPLICABLE" if off_route
                    else "VIOLATED" if clause_id == "ENDPOINT-EXACT"
                    else "OPEN"
                ),
                "rationale": (
                    "the off-route result does not decide this target clause"
                    if off_route else
                    "the exact counterexample violates the endpoint"
                    if clause_id == "ENDPOINT-EXACT" else
                    "the endpoint refutation does not need this positive clause"
                ),
                "evidence_refs": [],
            }
            for clause_id in (
                "ENDPOINT-EXACT", "QUANTIFIERS-EXACT", "MATHS-STRUCTURE",
                "MATHS-BOUNDARY",
            )
        ],
        "scope_limit": (
            "outside the assigned route" if off_route
            else "one exact witness in the full frozen target scope"
        ),
    }]
    if off_route:
        graph["route_compliance"] = {
            "status": "REFRAME_REQUIRED",
            "changed_axis": "",
            "preserved_route_fields": [],
            "reframe_request": "Explorer must decide whether to issue this side route",
            "side_result_claim_ids": ["C1"],
        }
    return graph


def _proposal(identifier: str, lane: str, mechanism: str, structural_object: str) -> dict[str, Any]:
    return {
        "proposal_id": identifier,
        "node_id": "CORE",
        "lane": lane,
        "route": {
            "method_family": lane.casefold(),
            "mechanism": mechanism,
            "structural_object": structural_object,
            "required_result": f"separate route {identifier}",
            "target_effect": "reduce the retained frontier",
            "assumptions": [],
        },
        "objective": f"exercise independent route {identifier}",
        "evaluator": "one exact discriminator",
        "expected_delta": "a typed frontier change",
        "return_condition": "return after one evaluator decision",
        "changed_axis": "",
        "revival_evidence": "",
        "features": {
            "target_leverage": 0.9,
            "expected_information_gain": 0.8,
            "checkability": 0.8,
            "reversibility": 0.9,
            "novelty": 0.7,
            "transfer_value": 0.4,
            "cost": 0.2,
            "recoupling_risk": 0.1,
        },
    }


def _explorer_authorization(
    root: Path,
    state: dict[str, Any],
    proposals: list[dict[str, Any]],
    selected_id: str | None,
    *,
    action: str = "WORK_ITEM_TO_RESEARCHER",
) -> dict[str, Any]:
    worksheet, _prepared = exploration.draft(root, state, proposals)
    for domain, controls in worksheet["target_model"]["domain_controls"].items():
        worksheet["target_model"]["domain_controls"][domain] = {
            key: (
                "SEPARATE" if key == "finite_vs_general"
                else f"synthetic {key.replace('_', ' ')} recorded"
            )
            for key in controls
        }
    source_map = _synthetic_source_map(state)
    source_ref = source_map["payload_sha256"]
    worksheet["source_coverage"] = {
        "status": "PARTIAL",
        "source_map_ref": source_ref,
        "queries": [{
            "query_id": "synthetic-source-query",
            "question": "What exact results govern the frozen synthetic target?",
            "corpus": "sealed synthetic source fixture",
            "checked_at": "2026-01-01T00:00:00+00:00",
            "result": "NOT_FOUND_WITHIN_SCOPE",
            "evidence_refs": ["SYNTHETIC-SEARCH"],
        }],
        "unavailable_refs": [],
        "correction_refs": [],
        "unresolved": ["external literature lies outside the synthetic fixture"],
        "absence_claim_prohibited": True,
    }
    worksheet["decision"] = {
        "action": action,
        "selected_proposal_id": selected_id,
        "basis_refs": [state["state_sha256"], source_ref],
        "alternatives": ["retain one mechanism-distinct route"],
        "changed_axis": "",
        "reason": "The decision isolates one bounded and falsifiable information gain.",
    }
    if action == "WAIT_EXTERNAL":
        worksheet["first_failing_gate"] = "the declared external evidence is unavailable"
    packet, _prepared = exploration.build_state(
        root, state, worksheet, proposals, source_map
    )
    return packet


def _synthetic_source_map(state: Mapping[str, Any]) -> dict[str, Any]:
    receipt_sha = hashlib.sha256(
        f"synthetic-retrieval:{state['state_sha256']}".encode("utf-8")
    ).hexdigest()
    problem_id = exploration._named_problem_identifier(state)
    preconditions = [
        "synthetic fixture only",
        f"target_sha256:{state['target']['canonical_sha256']}",
    ]
    if problem_id:
        preconditions.append(f"canonical_problem_id:{problem_id}")
    return seal_packet({
        "schema": exploration.SOURCE_MAP_SCHEMA,
        "source_map_id": f"synthetic:{state['state_sha256'][:16]}",
        "target_sha256": state["target"]["canonical_sha256"],
        "entries": [{
            "source_id": "SYNTHETIC-SEARCH",
            "source_type": "SEARCH_RECEIPT",
            "locator": "synthetic:bounded-corpus",
            "retrieved_sha256": receipt_sha,
            "claim_supported": "The synthetic fixture was searched within scope.",
            "status": "OPEN",
            "preconditions": preconditions,
            "reliability": "CURATED",
        }],
        "contradictions": [],
        "unresolved": ["external literature lies outside the synthetic fixture"],
        "checked_at": "2026-01-01T00:00:00+00:00",
    })


def _complete_source_map(state: Mapping[str, Any]) -> dict[str, Any]:
    receipt_sha = hashlib.sha256(
        f"synthetic-complete-retrieval:{state['state_sha256']}".encode("utf-8")
    ).hexdigest()
    return seal_packet({
        "schema": exploration.SOURCE_MAP_SCHEMA,
        "source_map_id": f"synthetic-complete:{state['state_sha256'][:16]}",
        "target_sha256": state["target"]["canonical_sha256"],
        "entries": [{
            "source_id": "SYNTHETIC-PRIMARY",
            "source_type": "PRIMARY_RECORD",
            "locator": "synthetic:primary-record",
            "retrieved_sha256": receipt_sha,
            "claim_supported": "The declared synthetic source scope was checked.",
            "status": "ESTABLISHED",
            "preconditions": ["declared synthetic source scope only"],
            "reliability": "PRIMARY",
        }],
        "contradictions": [],
        "unresolved": [],
        "checked_at": "2026-01-01T00:00:00+00:00",
    })


def _explorer_draft_from_state(packet: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(packet)
    draft["schema"] = exploration.DRAFT_SCHEMA
    draft.pop("payload_sha256", None)
    return draft


def _candidate(root: Path, target_sha256: str) -> dict[str, Any]:
    return contracts.validate_packet(root, "witsoc.candidate.v2", seal_packet({
        "schema": "witsoc.candidate.v2",
        "candidate_id": "synthetic-transfer-candidate",
        "target_sha256": target_sha256,
        "domain": "maths",
        "claim": "the retained structure may transfer under the named invariant",
        "claim_class": "STRUCTURAL_CANDIDATE",
        "scope": {"synthetic": True},
        "dependencies": [],
        "evidence_refs": [],
        "limitations": ["destination interpretation remains unverified"],
        "ceiling": "CONJECTURE",
        "artifact_ref": None,
        "producer": "synthetic-selftest",
    }))


def run(root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        cases.append({"name": name, "ok": bool(condition), "detail": detail})

    def failed(name: str, exc: Exception) -> None:
        check(name, False, str(exc))

    try:
        coordination = modes.coordination_contract("OPEN_DISCOVERY")
        check(
            "explicit discovery stays in the current invocation and rejoins Explorer",
            coordination["owner"] == "CURRENT_INVOCATION"
            and coordination["child_role_scope"] == "CURRENT_SESSION_TREE"
            and coordination["nested_root_orchestrator"]
            == "FORBIDDEN_UNLESS_USER_EXPLICITLY_REQUESTS"
            and coordination["workspace_binding"] == "PRESERVE_USER_SPECIFIED_PATHS"
            and coordination["worker_workspace"]
            == {
                "default": "INHERIT_BOUND",
                "isolated": "REQUIRES_BASE_REVISION_AND_DECLARED_ARTIFACT_RETURN",
            }
            and coordination["activation_gate"]
            == "PREFLIGHT_READY_BEFORE_RUN_ARTIFACTS"
            and coordination["dispatch_is_completion"] is False
            and coordination["pending_worker_action"]
            == "YIELD_AND_RESUME_ON_BOUND_RETURN"
            and coordination["stage_order"]
            == [
                "EXPLORER_DECISION",
                "RESEARCHER_DELTA_IF_AUTHORIZED",
                "EXPLORER_RETURN_ARBITRATION",
                "FRONTIER_EXPANSION_OR_RESUMABLE_PAUSE",
            ]
            and coordination["completion_requires"]
            == ["BOUND_DELTA_IMPORTED", "EXPLORER_ARBITRATED"],
        )
    except Exception as exc:
        failed("explicit discovery stays in the current invocation and rejoins Explorer", exc)

    try:
        routed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "route.py"),
                "--statement",
                "Attack this open problem in mathematics without claiming a solve.",
                "--domain",
                "maths",
                "--role",
                "explorer",
            ],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        route_payload = json.loads(routed.stdout)
        check(
            "route.py exposes the same-run coordination contract from any cwd",
            routed.returncode == 0
            and route_payload["mode"] == "OPEN_DISCOVERY"
            and route_payload["coordination"]
            == modes.coordination_contract("OPEN_DISCOVERY")
            and route_payload["activation_resources"]["roles"]
            == [
                {
                    "role": "explorer",
                    "local_path": "explorer/SKILL.md",
                    "skill_locator": "witsoc/explorer/SKILL.md",
                },
                {
                    "role": "researcher",
                    "local_path": "researcher/SKILL.md",
                    "skill_locator": "witsoc/researcher/SKILL.md",
                },
            ]
            and route_payload["load_plan"]["role_contract"]["skill_locator"]
            == "witsoc/explorer/SKILL.md"
            and all(
                item["skill_locator"].startswith("witsoc/")
                for item in route_payload["load_plan"]["load_resources"]
            )
            and modes.choose_mode("Run the Explorer\u2192Researcher loop.")["mode"]
            == "OPEN_DISCOVERY",
            routed.stderr.strip(),
        )
        check(
            "open conjecture language cannot fall through to claim verification",
            modes.choose_mode(
                "Investigate an open asymptotic number theory conjecture and isolate its minimal obstruction."
            )["mode"] == "OPEN_DISCOVERY"
            and modes.choose_mode(
                "Investigate an open Erd\u0151s conjecture and isolate one obstruction."
            )["mode"] == "OPEN_DISCOVERY",
            routed.stderr.strip(),
        )
    except Exception as exc:
        failed("route.py exposes the same-run coordination contract from any cwd", exc)

    try:
        with tempfile.TemporaryDirectory(prefix="witsoc-orchestrator-") as raw:
            workspace = Path(raw) / "workspace"
            workspace.mkdir()
            task_dir = workspace / "runs" / "trace-derived"
            activation_path = Path(raw) / "activation.json"
            statement_file = Path(raw) / "request.txt"
            statement_file.write_text(
                "Run the Witsoc Explorer->Researcher loop on obstruction `b_3`; "
                "preserve $KIMI_WORK_DIR and runs/example.\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(root / "scripts" / "witsoc.py"),
                "orchestrator-preflight",
                "--statement-file",
                str(statement_file),
                "--domain",
                "maths",
                "--workspace-root",
                str(workspace),
                "--task-dir",
                "runs/trace-derived",
                "--out",
                str(activation_path),
            ]
            completed = subprocess.run(
                command,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            payload = json.loads(completed.stdout)
            locators = {item["skill_locator"] for item in payload["resources"]}
            check(
                "orchestrator preflight writes only a sealed receipt with canonical Plane locators",
                completed.returncode == 0
                and payload["status"] == "PREFLIGHT_READY"
                and payload["schema"] == "witsoc.activation-receipt.v1"
                and payload["may_create_run_artifacts"] is True
                and payload["route"]["mode"] == "OPEN_DISCOVERY"
                and payload["side_effects"] == []
                and not task_dir.exists()
                and activation_path.is_file()
                and {
                    "witsoc/SKILL.md",
                    "witsoc/references/orchestrator_protocol.md",
                    "witsoc/explorer/SKILL.md",
                    "witsoc/researcher/SKILL.md",
                }.issubset(locators)
                and payload["dispatch_gate"] == {
                    "worker_launch_allowed": False,
                    "opens_only_after": "SEALED_EPISODE_OR_STRONG_ROUND_AND_BOUND_HANDOFF",
                    "open_discovery_issue_requires": "SEALED_EXPLORER_STATE_AND_ATOMIC_ARBITRATION",
                    "host_missions_are": "EXPLORER_PROPOSALS_NOT_DISPATCH_AUTHORITY",
                    "frontier_initialization_is_completion": False,
                    "same_named_plugin_is_activation": False,
                    "next_command": "orchestrator-next --state <task-dir>/frontier.json",
                }
                and all(locator.startswith("witsoc/") for locator in locators),
                completed.stderr.strip(),
            )
            isolated = subprocess.run(
                [*command, "--worker-workspace", "isolated-return"],
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            isolated_payload = json.loads(isolated.stdout)
            check(
                "isolated worker preflight requires an explicit return contract",
                isolated.returncode == 1
                and isolated_payload["status"] == "ACTIVATION_FAILED"
                and isolated_payload["may_create_run_artifacts"] is False
                and not task_dir.exists()
                and any("--base-revision" in item for item in isolated_payload["problems"])
                and any("--artifact-return" in item for item in isolated_payload["problems"]),
                isolated.stderr.strip(),
            )
            isolated_bound = subprocess.run(
                [
                    *command,
                    "--worker-workspace",
                    "isolated-return",
                    "--base-revision",
                    "0123456789abcdef",
                    "--artifact-return",
                    "runs/trace-derived/RESULT.md",
                ],
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            isolated_bound_payload = json.loads(isolated_bound.stdout)
            check(
                "isolated worker preflight binds its revision and returned bytes",
                isolated_bound.returncode == 0
                and isolated_bound_payload["status"] == "PREFLIGHT_READY"
                and isolated_bound_payload["workspace"]["worker_mode"]
                == "ISOLATED_RETURN"
                and isolated_bound_payload["workspace"]["base_revision"]
                == "0123456789abcdef"
                and isolated_bound_payload["workspace"]["artifact_returns"]
                == ["runs/trace-derived/RESULT.md"]
                and not task_dir.exists(),
                isolated_bound.stderr.strip(),
            )
    except Exception as exc:
        failed("orchestrator preflight contract", exc)

    try:
        packaged_domains = [
            item["domain"] for item in domain_packages.load_registry(root)["packages"]
        ]
        graph = capability_graph.compile_graph(root, packaged_domains)
        declared_nodes = json.loads(
            (root / runtime_contracts.CONTRACT_PATH).read_text(encoding="utf-8")
        )["capabilities"]["nodes"]
        check(
            "typed capability graph has one admission authority",
            graph["admission_authority"] == "frame:evidence-admission"
            and len(graph["nodes"]) == declared_nodes,
        )
    except Exception as exc:  # Synthetic report should retain all independent failures.
        failed("typed capability graph has one admission authority", exc)

    try:
        explicit = capabilities.build_load_plan(
            root,
            "OPEN_DISCOVERY",
            ["maths", "bio"],
            "researcher",
            "exact finite computation",
            required_capabilities=["maths:exact-computation"],
        )
        bounded_bio = capabilities.build_load_plan(
            root,
            "OPEN_DISCOVERY",
            ["bio"],
            "researcher",
            "causal mechanism perturbation rescue replication",
            required_capabilities=["bio:causal-perturbation"],
        )
        check(
            "explicit capability paths preserve domain ownership and context bounds",
            explicit["ok"]
            and "maths:exact-computation" in (
                explicit["required_path"] + explicit["requested_extensions"]
            )
            and all(
                item.startswith(("maths:", "frame:"))
                for item in explicit["required_path"]
            )
            and explicit["estimated_tokens"] <= 4096
            and bounded_bio["ok"]
            and "bio:causal-perturbation" in (
                bounded_bio["required_path"] + bounded_bio["requested_extensions"]
            )
            and "bio:discriminating-design" not in bounded_bio["triggered_extensions"]
            and any(
                item["trigger"] == "bio:discriminating-design"
                for item in bounded_bio["deferred_extensions"]
            )
            and bounded_bio["estimated_tokens"] <= 4096,
            "; ".join(explicit["problems"] + bounded_bio["problems"]),
        )
        allowed_explorer_capabilities = {
            "maths": {
                "source-status-map", "normalized-problem-ir", "claim-novelty-ledger",
                "open-frontier", "cross-domain-routing",
            },
            "bio": {"source-status-map", "open-frontier", "cross-domain-routing"},
        }
        allowed_explorer_operators = {
            "maths": {"normalize-target", "source-anchoring", "claim-novelty-ledger"},
            "bio": {"freeze-context", "source-triangulation"},
        }
        role_leaks: list[str] = []
        for domain in ("maths", "bio"):
            capability_manifest = json.loads(
                (root / "domains" / domain / "capabilities.json").read_text(encoding="utf-8")
            )
            operator_manifest = json.loads(
                (root / "domains" / domain / "operators.json").read_text(encoding="utf-8")
            )
            role_leaks.extend(
                f"{domain}:capability:{item['id']}"
                for item in capability_manifest["capabilities"]
                if "explorer" in item["roles"]
                and item["id"] not in allowed_explorer_capabilities[domain]
            )
            role_leaks.extend(
                f"{domain}:operator:{item['id']}"
                for item in operator_manifest["operators"]
                if "explorer" in item["roles"]
                and item["id"] not in allowed_explorer_operators[domain]
            )
        check(
            "Explorer domain access is limited to framing, source triage, and route control",
            not role_leaks,
            ", ".join(role_leaks),
        )
    except Exception as exc:
        failed("explicit capability paths preserve domain ownership and context bounds", exc)

    target = kernel.target_record("A frozen synthetic discovery target.", "exercise typed controls")
    state = kernel.new_state(
        target, "OPEN_DISCOVERY", ["maths"], created_at="2026-01-01T00:00:00+00:00"
    )
    item = {
        "item_id": "CORE",
        "kind": "OPEN_CORE",
        "statement": "Resolve the retained synthetic core.",
        "target_sha256": target["canonical_sha256"],
        "status": "OPEN",
        "dependencies": [],
        "evidence_refs": [],
        "route_fingerprint": None,
        "admission_ref": None,
    }
    state = kernel.apply_event(
        state,
        kernel.build_event(state, "FRONTIER_ADD", {"item": item, "activate": True}, "advanced:add-core"),
    )
    try:
        root_state = kernel.new_state(
            target, "OPEN_DISCOVERY", ["maths"],
            created_at="2026-01-01T00:00:00+00:00",
        )
        root_proposal = _proposal(
            "X1", "REDUCE", "isolate the exact root obstruction", "frozen root target"
        )
        root_proposal["node_id"] = "ROOT"
        root_explorer = _explorer_authorization(
            root, root_state, [root_proposal], "X1"
        )
        root_source_map = _synthetic_source_map(root_state)
        root_arbitration, _prepared = exploration.build_arbitration(
            root, root_state, root_explorer, [root_proposal], root_source_map
        )
        try:
            kernel.build_event(
                root_state,
                "ARBITRATION_RECORDED",
                {"arbitration": root_arbitration},
                "advanced:unauthorized-arbitration",
            )
            unauthorized_arbitration = False
        except kernel.KernelError as exc:
            unauthorized_arbitration = "validated Explorer state" in str(exc)
        issued_root, root_episode = discovery.issue_best(
            root_state,
            [root_proposal],
            "explorer-negative-control",
            "one synthetic route",
            root_explorer,
            root_source_map,
        )
        staged_item = {
            "item_id": "RETURNED-SUGGESTION",
            "kind": "OPEN_CORE",
            "statement": "A returned suggestion that still needs Explorer arbitration.",
            "target_sha256": target["canonical_sha256"],
            "status": "OPEN",
            "dependencies": [],
            "evidence_refs": [],
            "route_fingerprint": None,
            "admission_ref": None,
        }
        staged_obstruction = {
            "obstruction_id": "RETURNED-OBSTRUCTION",
            "statement": "The attempted synthetic mechanism made no progress.",
            "route_fingerprint": root_episode["route_fingerprint"],
            "core_fingerprint": root_episode["core_fingerprint"],
            "evidence_refs": [],
            "revival_condition": "a new exact discriminator is supplied",
        }
        root_delta = seal_packet({
            "schema": discovery.LEGACY_DELTA_SCHEMA,
            "delta_id": "explorer-negative-delta",
            "episode_id": root_episode["episode_id"],
            "episode_sha256": root_episode["payload_sha256"],
            "target_sha256": target["canonical_sha256"],
            "base_revision": issued_root["revision"],
            "base_state_sha256": issued_root["state_sha256"],
            "outcome": "NO_PROGRESS",
            "evidence_refs": [],
            "frontier_measure_before": 1,
            "frontier_measure_after": 1,
            "new_frontier": [staged_item],
            "new_obstruction": None,
            "admission_ref": None,
            "independent_review": None,
            "remaining_obstruction": "the root remains undecomposed",
            "revival_condition": "a mechanism-distinct discriminator is supplied",
            "next_proposals": [],
            "changed_axis": "",
        })
        returned_root = discovery.apply_delta(issued_root, root_delta)
        post_return_event = kernel.build_event(
            returned_root,
            "DECISION_RECORD",
            {"decision": {
                "decision_id": "advanced:return-bypass",
                "action": "DEMOTE",
                "basis_refs": [returned_root["state_sha256"]],
                "alternatives": [],
                "changed_axis": "",
            }},
            "advanced:return-bypass",
        )
        try:
            kernel.apply_event(returned_root, post_return_event)
            return_bypass = False
        except kernel.KernelError as exc:
            return_bypass = "immediate Explorer arbitration" in str(exc)
        carried_draft, _prepared = exploration.draft(
            root, returned_root, [], root_explorer
        )

        def explorer_rejects(action: Any, phrase: str) -> bool:
            try:
                action()
            except (discovery.DiscoveryError, exploration.ExplorationError) as exc:
                return phrase in str(exc)
            return False

        missing_arbitration = explorer_rejects(
            lambda: discovery.issue_best(
                root_state, [root_proposal], "missing-arbitration", "one route"
            ),
            "sealed Explorer state",
        )
        pending_decision = explorer_rejects(
            lambda: _explorer_authorization(
                root, issued_root, [], None, action="WAIT_EXTERNAL"
            ),
            "pending",
        )
        terminal_packet = _explorer_authorization(
            root, returned_root, [], None, action="WAIT_EXTERNAL"
        )
        bounded_draft = _explorer_draft_from_state(terminal_packet)
        bounded_draft["return_assessment"]["route_disposition"] = "EXHAUSTED"
        bounded_exhaustion = explorer_rejects(
            lambda: exploration.build_state(
                root, returned_root, bounded_draft, [],
                _synthetic_source_map(returned_root),
            ),
            "bounded evidence",
        )

        initial_terminal = _explorer_authorization(
            root, root_state, [], None, action="WAIT_EXTERNAL"
        )
        absence_draft = _explorer_draft_from_state(initial_terminal)
        absence_draft["source_coverage"]["queries"][0]["result"] = "ABSENT"
        scoped_absence = explorer_rejects(
            lambda: exploration.build_state(
                root, root_state, absence_draft, [], root_source_map
            ),
            "must be one of",
        )

        status_draft = _explorer_draft_from_state(initial_terminal)
        status_draft["frontier_model"]["nodes"][0]["status"] = "VERIFIED"
        status_rewrite = explorer_rejects(
            lambda: exploration.build_state(
                root, root_state, status_draft, [], root_source_map
            ),
            "cannot rewrite",
        )

        cycle_draft = _explorer_draft_from_state(initial_terminal)
        cycle_draft["frontier_model"]["nodes"][0]["dependencies"] = ["CYCLE"]
        cycle_draft["frontier_model"]["nodes"].append({
            "node_id": "CYCLE",
            "kind": "OPEN_CORE",
            "statement": "A deliberately cyclic synthetic core.",
            "status": "OPEN",
            "dependencies": ["ROOT"],
            "evidence_refs": [],
            "target_path": ["ROOT", "CYCLE"],
            "relation_to_parent": "REDUCES_TO",
        })
        cycle_draft["frontier_model"]["edges"] = [
            {"from_id": "ROOT", "to_id": "CYCLE", "relation": "REDUCES_TO", "evidence_refs": []},
            {"from_id": "CYCLE", "to_id": "ROOT", "relation": "REDUCES_TO", "evidence_refs": []},
        ]
        cycle_draft["frontier_model"]["minimal_open_core_ids"] = ["CYCLE"]
        cycle_draft["frontier_model"]["frontier_measure"] = 1
        cyclic_frontier = explorer_rejects(
            lambda: exploration.build_state(
                root, root_state, cycle_draft, [], root_source_map
            ),
            "cycle",
        )

        next_proposal = _proposal(
            "X2", "REFUTE", "construct a minimal countermodel", "root boundary model"
        )
        next_proposal["node_id"] = "ROOT"
        root_dispatch, _prepared = exploration.draft(
            root, returned_root, [next_proposal]
        )
        root_dispatch["target_model"] = copy.deepcopy(terminal_packet["target_model"])
        root_dispatch["source_coverage"] = copy.deepcopy(terminal_packet["source_coverage"])
        root_dispatch["decision"] = {
            "action": "WORK_ITEM_TO_RESEARCHER",
            "selected_proposal_id": "X2",
            "basis_refs": [returned_root["state_sha256"]],
            "alternatives": ["retain the undecomposed root"],
            "changed_axis": "",
            "reason": "The candidate asks a distinct bounded question.",
        }
        root_only_dispatch = explorer_rejects(
            lambda: exploration.build_state(
                root, returned_root, root_dispatch, [next_proposal],
                _synthetic_source_map(returned_root),
            ),
            "decomposed frontier",
        )

        second_root_draft = copy.deepcopy(root_dispatch)
        second_root_draft["frontier_model"]["root_only_exception"] = (
            "one final ROOT-level discriminator is retained before decomposition"
        )
        returned_root_source_map = _synthetic_source_map(returned_root)
        second_root_explorer, _prepared = exploration.build_state(
            root,
            returned_root,
            second_root_draft,
            [next_proposal],
            returned_root_source_map,
        )
        second_root_issued, second_root_episode = discovery.issue_best(
            returned_root,
            [next_proposal],
            "explorer-second-root",
            "one final root-level discriminator",
            second_root_explorer,
            returned_root_source_map,
        )
        second_root_delta = seal_packet({
            "schema": discovery.LEGACY_DELTA_SCHEMA,
            "delta_id": "explorer-second-root-delta",
            "episode_id": second_root_episode["episode_id"],
            "episode_sha256": second_root_episode["payload_sha256"],
            "target_sha256": target["canonical_sha256"],
            "base_revision": second_root_issued["revision"],
            "base_state_sha256": second_root_issued["state_sha256"],
            "outcome": "NO_PROGRESS",
            "evidence_refs": [],
            "frontier_measure_before": 1,
            "frontier_measure_after": 1,
            "new_frontier": [],
            "new_obstruction": None,
            "admission_ref": None,
            "independent_review": None,
            "remaining_obstruction": "the ROOT target is still undecomposed",
            "revival_condition": "a new endpoint-level discriminator is supplied",
            "next_proposals": [],
            "changed_axis": "",
        })
        twice_returned_root = discovery.apply_delta(
            second_root_issued, second_root_delta
        )
        third_root_proposal = _proposal(
            "X3", "MEASURE", "derive a third root discriminator", "global root boundary"
        )
        third_root_proposal["node_id"] = "ROOT"
        third_root_draft, _prepared = exploration.draft(
            root, twice_returned_root, [third_root_proposal], second_root_explorer
        )
        third_root_draft["frontier_model"]["root_only_exception"] = (
            "attempt to retain ROOT despite two completed attacks"
        )
        third_root_draft["decision"] = {
            "action": "WORK_ITEM_TO_RESEARCHER",
            "selected_proposal_id": "X3",
            "basis_refs": [
                twice_returned_root["state_sha256"],
                returned_root_source_map["payload_sha256"],
            ],
            "alternatives": ["decompose the endpoint"],
            "changed_axis": "",
            "reason": "A third ROOT attack is proposed without decomposition.",
        }
        repeated_root_dispatch = explorer_rejects(
            lambda: exploration.build_state(
                root,
                twice_returned_root,
                third_root_draft,
                [third_root_proposal],
                returned_root_source_map,
            ),
            "two ROOT attacks require",
        )

        fabricated_memory_draft = _explorer_draft_from_state(root_explorer)
        fabricated_memory_draft["route_memory"].append({
            "route_fingerprint": "1" * 64,
            "core_fingerprint": "2" * 64,
            "operator_id": "invented-closure",
            "mechanism": "Explorer-local bounded calculation",
            "invariant": "synthetic invariant",
            "required_result": "universal closure",
            "failure_signature": "bounded samples agree",
            "failure_domain": "invented:route",
            "outcome": "NEW_OBSTRUCTION",
            "disposition": "EXHAUSTED",
            "revival_predicate": "an external exact derivation is supplied",
            "evidence_refs": [],
        })
        fabricated_route_memory = explorer_rejects(
            lambda: exploration.build_state(
                root,
                root_state,
                fabricated_memory_draft,
                [root_proposal],
                root_source_map,
            ),
            "cannot be invented or edited",
        )

        self_source_map = copy.deepcopy(root_source_map)
        self_source_map["entries"][0]["locator"] = "RESULT.md"
        self_source_map = seal_packet(self_source_map)
        self_source_draft = _explorer_draft_from_state(root_explorer)
        old_source_ref = self_source_draft["source_coverage"]["source_map_ref"]
        self_source_draft["source_coverage"]["source_map_ref"] = self_source_map["payload_sha256"]
        self_source_draft["decision"]["basis_refs"] = [
            self_source_map["payload_sha256"]
            if item == old_source_ref else item
            for item in self_source_draft["decision"]["basis_refs"]
        ]
        self_authored_source = explorer_rejects(
            lambda: exploration.build_state(
                root,
                root_state,
                self_source_draft,
                [root_proposal],
                self_source_map,
            ),
            "Explorer-authored output",
        )

        complete_source_map = _complete_source_map(root_state)
        stop_draft, _prepared = exploration.draft(root, root_state, [])
        for domain, controls in stop_draft["target_model"]["domain_controls"].items():
            stop_draft["target_model"]["domain_controls"][domain] = {
                key: (
                    "SEPARATE" if key == "finite_vs_general"
                    else f"synthetic {key.replace('_', ' ')} recorded"
                )
                for key in controls
            }
        stop_draft["source_coverage"] = {
            "status": "BOUNDED_COMPLETE",
            "source_map_ref": complete_source_map["payload_sha256"],
            "queries": [{
                "query_id": "synthetic-complete-query",
                "question": "Which exact sources cover the declared synthetic scope?",
                "corpus": "sealed synthetic primary fixture",
                "checked_at": "2026-01-01T00:00:00+00:00",
                "result": "FOUND",
                "evidence_refs": ["SYNTHETIC-PRIMARY"],
            }],
            "unavailable_refs": [],
            "correction_refs": [],
            "unresolved": [],
            "absence_claim_prohibited": True,
        }
        stop_draft["decision"] = {
            "action": "HONEST_STOP",
            "selected_proposal_id": None,
            "basis_refs": [root_state["state_sha256"], complete_source_map["payload_sha256"]],
            "alternatives": [
                "retain the unresolved core for a new mechanism",
                "resume when an external discriminator becomes available",
            ],
            "changed_axis": "",
            "reason": "No dispatchable route remains in the current authorized search only.",
        }
        unreviewed_stop = explorer_rejects(
            lambda: exploration.build_state(
                root, root_state, stop_draft, [], complete_source_map
            ),
            "independent stop-review",
        )
        triage_stop_review_rejected = explorer_rejects(
            lambda: exploration.stop_review_draft(
                root,
                root_state,
                stop_draft,
                [],
                complete_source_map,
                report_id="independent-synthetic-stop",
            ),
            "unavailable at initial triage",
        )
        pause_draft = copy.deepcopy(stop_draft)
        pause_draft["decision"] = {
            "action": "PAUSE_WITH_FRONTIER",
            "selected_proposal_id": None,
            "basis_refs": [root_state["state_sha256"], complete_source_map["payload_sha256"]],
            "alternatives": ["resume with a mechanism-distinct route"],
            "changed_axis": "",
            "reason": "Preserve the unresolved target and frontier for later resumption.",
        }
        paused_explorer, _prepared = exploration.build_state(
            root, root_state, pause_draft, [], complete_source_map
        )
        pause_arbitration, _prepared = exploration.build_arbitration(
            root, root_state, paused_explorer, [], complete_source_map
        )
        paused_state = exploration.apply_arbitration(
            root, root_state, pause_arbitration
        )
        pause_gate = orchestration.next_action(paused_state)

        paraphrase = copy.deepcopy(root_proposal)
        paraphrase["proposal_id"] = "X1-renamed"
        paraphrased_plan = discovery.plan_portfolio(
            returned_root, [paraphrase], "one route"
        )
        recoupled_draft, _prepared = exploration.draft(
            root, returned_root, [paraphrase]
        )
        revived = copy.deepcopy(paraphrase)
        revived["proposal_id"] = "X1-revived"
        revived["revival_evidence"] = "an exact discriminator now satisfies the retained predicate"
        revived_draft, _prepared = exploration.draft(
            root, returned_root, [revived]
        )
        staged_ids = {item["item_id"] for item in returned_root["frontier"]["items"]}
        staged_obstruction_ids = {
            item["obstruction_id"] for item in returned_root["frontier"]["obstructions"]
        }
        check(
            "Explorer control rejects trace-derived lifecycle shortcuts",
            unauthorized_arbitration
            and return_bypass
            and missing_arbitration
            and pending_decision
            and bounded_exhaustion
            and scoped_absence
            and status_rewrite
            and cyclic_frontier
            and root_only_dispatch
            and repeated_root_dispatch
            and fabricated_route_memory
            and self_authored_source
            and unreviewed_stop
            and triage_stop_review_rejected
            and pause_arbitration["frontier_delta"]["additions"] == []
            and pause_gate["stage"] == "CAMPAIGN_PAUSED_WITH_FRONTIER"
            and paused_state["status"] == "OPEN"
            and not paraphrased_plan["dispatchable"]
            and recoupled_draft["portfolio"]["entries"][0]["disposition"] == "RECOUPLED"
            and revived_draft["portfolio"]["entries"][0]["disposition"] == "REVIVED"
            and "RETURNED-SUGGESTION" not in staged_ids
            and "RETURNED-OBSTRUCTION" not in staged_obstruction_ids
            and returned_root["route_attempts"][-1]["route_disposition"] == "PENDING"
            and carried_draft["source_coverage"] == root_explorer["source_coverage"]
            and carried_draft["target_model"] == root_explorer["target_model"]
            and orchestration.next_action(returned_root)["stage"]
            == "EXPLORER_RETURN_ARBITRATION",
        )
    except Exception as exc:
        failed("Explorer control rejects trace-derived lifecycle shortcuts", exc)
    try:
        first_route = _proposal("S1", "REDUCE", "translate the boundary object", "the quotient object")["route"]
        equivalent_route = {
            **first_route,
            "method_family": "reduce strategy",
            "mechanism": "mapping boundary object",
            "structural_object": "quotient object",
            "required_result": "establish invariant",
        }
        first_route["method_family"] = "reduction approach"
        first_route["required_result"] = "show the invariant"
        reversed_route = {**first_route, "target_effect": "map target to source"}
        directed_route = {**first_route, "target_effect": "map source to target"}
        stagnant = discovery.adaptive_policy({
            "route_attempts": [
                {"outcome": "NO_PROGRESS"},
                {"outcome": "NEW_OBSTRUCTION"},
                {"outcome": "FALSIFICATION"},
            ]
        })
        check(
            "semantic route identity ignores relabeling but preserves direction",
            discovery.route_fingerprints(first_route)[0]
            == discovery.route_fingerprints(equivalent_route)[0]
            and discovery.route_fingerprints(directed_route)[0]
            != discovery.route_fingerprints(reversed_route)[0]
            and stagnant["effective_weights"]["novelty"]
            > discovery.FEATURE_WEIGHTS["novelty"],
        )
    except Exception as exc:
        failed("semantic route identity ignores relabeling but preserves direction", exc)

    try:
        state_read_index = kernel.state_index(root, state, report_id="synthetic-index")
        checkpoint = kernel.compact_checkpoint(
            root, state, report_id="synthetic-checkpoint", block_size=2, tail_events=1
        )
        check(
            "state indexes and checkpoints are sealed non-authoritative read models",
            state_read_index["status_authority"] is False
            and state_read_index["body"]["source_state_sha256"] == state["state_sha256"]
            and checkpoint["status_authority"] is False
            and checkpoint["body"]["replay_required_for_authority"] is True
            and checkpoint["body"]["may_replace_kernel_state"] is False,
        )
    except Exception as exc:
        failed("state indexes and checkpoints are sealed non-authoritative read models", exc)
    try:
        capsule = capsules.build(root, state, role="researcher", context_budget=2048)
        check(
            "role capsule is sealed and within budget",
            capsule["estimated_tokens"] <= capsule["context_budget"] == 2048,
        )
        try:
            capsules.build(root, state, role="researcher", context_budget=4097)
        except capsules.CapsuleError:
            check("capsule refuses context above the hard limit", True)
        else:
            check("capsule refuses context above the hard limit", False)
    except Exception as exc:
        failed("role capsule is sealed and within budget", exc)

    try:
        initial_state = kernel.new_state(
            target, "OPEN_DISCOVERY", ["maths"], created_at="2026-01-01T00:00:00+00:00"
        )
        initial_gate = orchestration.next_action(initial_state)
        domain_proposal = _proposal(
            "G1", "MEASURE", "run exact finite computation", "quotient boundary"
        )
        domain_proposal["objective"] = (
            "run an exact computation over the finite quotient boundary"
            + " Preserve the complete assigned context through the sealed handoff."
            * 96
        )
        domain_proposal["evaluator"] = "replay the exact finite certificate"
        explorer_state = _explorer_authorization(
            root, state, [domain_proposal], "G1"
        )
        domain_source_map = _synthetic_source_map(state)
        issued, episode = discovery.issue_best(
            state,
            [domain_proposal],
            "episode-gated",
            "single trace-derived obstruction already fixes the admissible route",
            explorer_state,
            domain_source_map,
        )
        issued_gate = orchestration.next_action(issued)
        with tempfile.TemporaryDirectory(prefix="witsoc-handoff-") as raw:
            workspace = Path(raw)
            task = workspace / "runs" / "gated"
            handoff, draft, _snapshot = orchestration.build_handoff(
                root,
                issued,
                episode,
                workspace_root=workspace,
                task_dir=task,
                handoff_path=task / "researcher-handoff.json",
                state_snapshot_path=task / "researcher-state.json",
                draft_path=task / "research-delta.draft.json",
                delta_path=task / "research-delta.json",
                source_map_value=domain_source_map,
            )
            launch_gate = orchestration.next_action(issued, handoff_value=handoff)
            tampered = json.loads(json.dumps(handoff))
            tampered["plane"]["agent"] = "witsoc-researcher"
            tampered = seal_packet(tampered)
            try:
                orchestration.next_action(issued, handoff_value=tampered)
            except orchestration.OrchestrationError:
                invented_agent_rejected = True
            else:
                invented_agent_rejected = False
            tampered_domain = json.loads(json.dumps(handoff))
            tampered_domain["domain_binding"]["domains"] = ["bio"]
            tampered_domain["domain_binding"] = seal_packet(
                tampered_domain["domain_binding"]
            )
            tampered_domain = seal_packet(tampered_domain)
            try:
                orchestration.next_action(issued, handoff_value=tampered_domain)
            except orchestration.OrchestrationError:
                mismatched_domain_rejected = True
            else:
                mismatched_domain_rejected = False
            legacy = json.loads(json.dumps(handoff))
            legacy["schema"] = orchestration.LEGACY_HANDOFF_SCHEMA
            legacy.pop("domain_binding")
            legacy.pop("reasoning_contract")
            legacy.pop("source_map")
            legacy["return_contract"]["schema"] = discovery.LEGACY_DELTA_SCHEMA
            legacy["return_contract"]["draft_schema"] = orchestration.LEGACY_DRAFT_SCHEMA
            legacy["plane"] = orchestration._plane_projection(
                issued, episode, legacy["paths"]
            )
            legacy = seal_packet(legacy)
            try:
                orchestration.next_action(issued, handoff_value=legacy)
            except orchestration.OrchestrationError:
                legacy_source_downgrade_rejected = True
            else:
                legacy_source_downgrade_rejected = False
            domain_legacy = json.loads(json.dumps(handoff))
            domain_legacy["schema"] = orchestration.DOMAIN_HANDOFF_SCHEMA
            domain_legacy.pop("reasoning_contract")
            domain_legacy.pop("source_map")
            domain_legacy["return_contract"]["schema"] = discovery.LEGACY_DELTA_SCHEMA
            domain_legacy["return_contract"]["draft_schema"] = orchestration.LEGACY_DRAFT_SCHEMA
            domain_legacy["plane"] = orchestration._plane_projection(
                issued,
                episode,
                domain_legacy["paths"],
                domain_legacy["domain_binding"],
            )
            domain_legacy = seal_packet(domain_legacy)
            try:
                orchestration.next_action(issued, handoff_value=domain_legacy)
            except orchestration.OrchestrationError:
                domain_source_downgrade_rejected = True
            else:
                domain_source_downgrade_rejected = False
            reasoning_legacy = json.loads(json.dumps(handoff))
            reasoning_legacy["schema"] = orchestration.REASONING_HANDOFF_SCHEMA
            reasoning_legacy.pop("source_map")
            reasoning_legacy["plane"] = orchestration._plane_projection(
                issued,
                episode,
                reasoning_legacy["paths"],
                reasoning_legacy["domain_binding"],
                reasoning_legacy["reasoning_contract"],
            )
            reasoning_legacy = seal_packet(reasoning_legacy)
            try:
                orchestration.next_action(issued, handoff_value=reasoning_legacy)
            except orchestration.OrchestrationError:
                reasoning_source_downgrade_rejected = True
            else:
                reasoning_source_downgrade_rejected = False
            retrieval_state = kernel.new_state(
                target,
                "CLAIM_VERIFICATION",
                ["maths"],
                created_at="2026-01-01T00:00:00+00:00",
            )
            retrieval_proposal = _proposal(
                "G2", "RETRIEVE", "search the primary literature", "known bound"
            )
            retrieval_proposal["node_id"] = "ROOT"
            retrieval_proposal["objective"] = (
                "find a published mathematical bound in primary sources"
            )
            retrieval_issued, retrieval_episode = discovery.issue_best(
                retrieval_state,
                [retrieval_proposal],
                "episode-domain-retrieval",
                "one source question is the only authorized route",
            )
            retrieval_task = workspace / "runs" / "retrieval"
            retrieval_handoff, _, _ = orchestration.build_handoff(
                root,
                retrieval_issued,
                retrieval_episode,
                workspace_root=workspace,
                task_dir=retrieval_task,
                handoff_path=retrieval_task / "researcher-handoff.json",
                state_snapshot_path=retrieval_task / "researcher-state.json",
                draft_path=retrieval_task / "research-delta.draft.json",
                delta_path=retrieval_task / "research-delta.json",
            )
            legacy = json.loads(json.dumps(retrieval_handoff))
            legacy["schema"] = orchestration.LEGACY_HANDOFF_SCHEMA
            legacy.pop("domain_binding")
            legacy.pop("reasoning_contract")
            legacy.pop("source_map")
            legacy["return_contract"]["schema"] = discovery.LEGACY_DELTA_SCHEMA
            legacy["return_contract"]["draft_schema"] = orchestration.LEGACY_DRAFT_SCHEMA
            legacy["plane"] = orchestration._plane_projection(
                retrieval_issued, retrieval_episode, legacy["paths"]
            )
            legacy = seal_packet(legacy)
            legacy_gate = orchestration.next_action(
                retrieval_issued, handoff_value=legacy
            )
            domain_legacy = json.loads(json.dumps(retrieval_handoff))
            domain_legacy["schema"] = orchestration.DOMAIN_HANDOFF_SCHEMA
            domain_legacy.pop("reasoning_contract")
            domain_legacy.pop("source_map")
            domain_legacy["return_contract"]["schema"] = discovery.LEGACY_DELTA_SCHEMA
            domain_legacy["return_contract"]["draft_schema"] = orchestration.LEGACY_DRAFT_SCHEMA
            domain_legacy["plane"] = orchestration._plane_projection(
                retrieval_issued,
                retrieval_episode,
                domain_legacy["paths"],
                domain_legacy["domain_binding"],
            )
            domain_legacy = seal_packet(domain_legacy)
            domain_legacy_gate = orchestration.next_action(
                retrieval_issued, handoff_value=domain_legacy
            )
            reasoning_legacy = json.loads(json.dumps(retrieval_handoff))
            reasoning_legacy["schema"] = orchestration.REASONING_HANDOFF_SCHEMA
            reasoning_legacy.pop("source_map")
            reasoning_legacy["plane"] = orchestration._plane_projection(
                retrieval_issued,
                retrieval_episode,
                reasoning_legacy["paths"],
                reasoning_legacy["domain_binding"],
                reasoning_legacy["reasoning_contract"],
            )
            reasoning_legacy = seal_packet(reasoning_legacy)
            reasoning_legacy_gate = orchestration.next_action(
                retrieval_issued, handoff_value=reasoning_legacy
            )
            _finish_no_progress(draft).update({
                "remaining_obstruction": "the exact quotient boundary remains uncontrolled",
                "revival_condition": "a bound separating the quotient boundary",
            })
            delta = orchestration.build_delta(issued, draft, handoff)
            import_gate = orchestration.next_action(issued, delta_value=delta)
            returned = discovery.apply_delta(issued, delta)
            return_gate = orchestration.next_action(returned)
            return_explorer = _explorer_authorization(
                root, returned, [], None, action="WAIT_EXTERNAL"
            )
            terminal_arbitration, _prepared = exploration.build_arbitration(
                root, returned, return_explorer, [], _synthetic_source_map(returned)
            )
            stopped = exploration.apply_arbitration(
                root, returned, terminal_arbitration
            )
            terminal_gate = orchestration.next_action(stopped)
        check(
            "orchestrator gate forbids initialization-only and generic dispatch",
            initial_gate["initialization_only"] is True
            and initial_gate["stage"] == "EXPLORER_DECISION"
            and initial_gate["worker_launch_allowed"] is False
            and initial_gate["completion_allowed"] is False
            and issued_gate["stage"] == "BUILD_RESEARCHER_HANDOFF"
            and issued_gate["worker_launch_allowed"] is False,
        )
        check(
            "sealed handoff projects a Witsoc role onto one ordinary worker",
            launch_gate["stage"] == "LAUNCH_BOUND_RESEARCHER"
            and launch_gate["worker_launch_allowed"] is True
            and handoff["role_resource"] == "witsoc/researcher/SKILL.md"
            and handoff["schema"] == "witsoc.orchestrator-handoff.v4"
            and handoff["return_contract"]["schema"] == "witsoc.research-delta.v2"
            and handoff["return_contract"]["draft_schema"]
            == "witsoc.research-delta-draft.v2"
            and handoff["plane"]["agent"] == "osci-worker"
            and handoff["plane"]["metadata"]["witsoc_reasoning_required"] is True
            and handoff["plane"]["metadata"]["witsoc_raw_deliberation_forbidden"] is True
            and handoff["plane"]["metadata"]["witsoc_source_context_required"] is True
            and handoff["plane"]["metadata"]["witsoc_source_map_sha256"]
            == domain_source_map["payload_sha256"]
            and handoff["source_map"] == domain_source_map
            and launch_gate["reasoning_contract"]["required"] is True
            and handoff["plugin_boundary"]["plugin_use_is_activation"] is False
            and invented_agent_rejected
            and handoff["plane"]["metadata"]["target_sha256"]
            == issued["target"]["canonical_sha256"]
            and handoff["plane"]["metadata"]["prompt_sha256"]
            == hashlib.sha256(handoff["plane"]["prompt"].encode("utf-8")).hexdigest()
            and len(handoff["reasoning_contract"]["objective"]) > 4096
            and len(
                handoff["reasoning_contract"]["authorization"]["content"]["summary"]
            ) > 4096,
        )
        binding = handoff["domain_binding"]
        domain_locator_prefix = f"witsoc/domains/{binding['domains'][0]}/"
        check(
            "Researcher handoff seals and loads the episode-specific domain",
            binding["domains"] == ["maths"]
            and binding["packages"][0]["distribution"] == "witsoc"
            and binding["packages"][0]["status"] in {"ACTIVE", "DEVELOPMENT_SOURCE"}
            and "maths:exact-computation" in binding["capabilities"]
            and any(
                item["domain"] == "maths" and item["id"] == "exact-computation"
                for item in binding["episode_operators"]
            )
            and binding["load_required"] is True
            and binding["core_only_forbidden"] is True
            and any(
                item["skill_locator"].startswith(domain_locator_prefix)
                for item in binding["load_resources"]
            )
            and any(
                item["local_path"] == "references/researcher_reasoning.md"
                for item in binding["load_resources"]
            )
            and "frame:reasoning-control" in binding["capabilities"]
            and any(
                item["domain"] == "maths" and item["id"] == "claim-pressure"
                for item in binding["episode_operators"]
            )
            and handoff["plane"]["metadata"]["witsoc_domains"] == ["maths"]
            and launch_gate["domain_binding"]["payload_sha256"]
            == binding["payload_sha256"]
            and mismatched_domain_rejected,
        )
        check(
            "source-free v1-v3 handoffs remain compatible; source-bound downgrades fail",
            legacy_gate["worker_launch_allowed"] is True
            and legacy_gate["domain_binding"]["load_required"] is False
            and legacy_gate["reasoning_contract"]["required"] is False
            and domain_legacy_gate["worker_launch_allowed"] is True
            and domain_legacy_gate["domain_binding"]["load_required"] is True
            and domain_legacy_gate["reasoning_contract"]["required"] is False
            and reasoning_legacy_gate["worker_launch_allowed"] is True
            and reasoning_legacy_gate["reasoning_contract"]["required"] is True
            and legacy_source_downgrade_rejected
            and domain_source_downgrade_rejected
            and reasoning_source_downgrade_rejected,
        )
        retrieval_binding = retrieval_handoff["domain_binding"]
        check(
            "episode lane overrides an unrelated campaign-level domain load",
            retrieval_binding["mode"] == "CLAIM_VERIFICATION"
            and retrieval_binding["capability_mode"] == "SOURCE_SYNTHESIS"
            and "maths:source-status-map" in retrieval_binding["capabilities"]
            and "maths:exact-computation" not in retrieval_binding["capabilities"]
            and any(
                item["id"] == "source-anchoring"
                for item in retrieval_binding["episode_operators"]
            )
            and all(
                "kernel_economics.md" not in item["local_path"]
                for item in retrieval_binding["load_resources"]
            ),
        )
        check(
            "bound delta always returns through Explorer before completion",
            delta["schema"] == "witsoc.research-delta.v2"
            and delta["reasoning"]["schema"] == "witsoc.reasoning-state.v1"
            and handoff["reasoning_contract"]["authorization"]["message_type"]
            == "ATTACK_AUTHORIZATION"
            and delta["messages"][0]["message_type"] == "PROGRESS_REPORT"
            and delta["messages"][0]["recipient"] == "EXPLORER"
            and import_gate["stage"] == "IMPORT_BOUND_DELTA"
            and import_gate["reasoning"]["requested_outcome"] == "NO_PROGRESS"
            and import_gate["worker_launch_allowed"] is False
            and return_gate["stage"] == "EXPLORER_RETURN_ARBITRATION"
            and return_gate["completion_allowed"] is False
            and terminal_gate["stage"] == "BUILD_FINALIZATION"
            and terminal_gate["terminal_candidate"] == "WAIT_EXTERNAL"
            and terminal_gate["completion_allowed"] is False
            and stopped["outcome"] == "WAITING_EXTERNAL",
        )
    except Exception as exc:
        failed("orchestrator lifecycle gate", exc)

    try:
        reasoning_proposal = _proposal(
            "RG1", "REFUTE", "audit the decisive dependency", "frozen core"
        )
        reasoning_explorer = _explorer_authorization(
            root, state, [reasoning_proposal], "RG1"
        )
        reasoning_source_map = _synthetic_source_map(state)
        reasoning_issued, reasoning_episode = discovery.issue_best(
            state,
            [reasoning_proposal],
            "episode-reasoning-gates",
            "one synthetic route isolates the reasoning contract",
            reasoning_explorer,
            reasoning_source_map,
        )
        reasoning_contract = reasoning.build_contract(reasoning_issued, reasoning_episode)

        valid_exact = reasoning.build_state(
            root,
            _promotion_reasoning(reasoning.draft(reasoning_contract)),
            reasoning_contract,
            expected_outcome="FALSIFICATION",
        )

        def rejected(
            graph: dict[str, Any], outcome: str, message_fragment: str
        ) -> bool:
            try:
                reasoning.build_state(
                    root, graph, reasoning_contract, expected_outcome=outcome
                )
            except reasoning.ReasoningError as exc:
                return message_fragment in str(exc)
            return False

        search_bounded_rejected = rejected(
            _promotion_reasoning(
                reasoning.draft(reasoning_contract),
                evidence_class="SEARCH_BOUNDED",
            ),
            "FALSIFICATION",
            "not supported by closure-safe evidence",
        )
        empirical_rejected = rejected(
            _promotion_reasoning(
                reasoning.draft(reasoning_contract), evidence_class="EMPIRICAL"
            ),
            "FALSIFICATION",
            "not supported by closure-safe evidence",
        )
        unbound_source_rejected = rejected(
            _promotion_reasoning(
                reasoning.draft(reasoning_contract),
                evidence_class="SOURCE_VERIFIED",
            ),
            "FALSIFICATION",
            "outside the Explorer-bound map",
        )
        off_route_rejected = rejected(
            _promotion_reasoning(
                reasoning.draft(reasoning_contract), off_route=True
            ),
            "FALSIFICATION",
            "not supported by closure-safe evidence",
        )

        unresolved = _promotion_reasoning(reasoning.draft(reasoning_contract))
        unresolved["claims"].extend([
            {
                "claim_id": "LEFT",
                "statement": "the auxiliary condition holds",
                "kind": "PREMISE",
                "epistemic_class": "EXACT",
                "status": "CONFLICTED",
                "depends_on": [],
                "inference": "GIVEN",
                "warrant": "",
                "evidence_refs": [],
                "defeaters": ["RIGHT"],
                "target_link": "SUPPORTING",
                "route_scope": "ASSIGNED",
            },
            {
                "claim_id": "RIGHT",
                "statement": "the auxiliary condition does not hold",
                "kind": "PREMISE",
                "epistemic_class": "EXACT",
                "status": "CONFLICTED",
                "depends_on": [],
                "inference": "GIVEN",
                "warrant": "",
                "evidence_refs": [],
                "defeaters": ["LEFT"],
                "target_link": "SUPPORTING",
                "route_scope": "ASSIGNED",
            },
        ])
        unresolved["contradictions"] = [{
            "contradiction_id": "K1",
            "left_claim_id": "LEFT",
            "right_claim_id": "RIGHT",
            "incompatible_assumptions": ["same frozen scope"],
            "status": "OPEN",
            "resolution": "",
            "evidence_refs": [],
        }]
        contradiction_rejected = rejected(
            unresolved,
            "FALSIFICATION",
            "open contradictions block promotion",
        )

        fake_reduction = _promotion_reasoning(reasoning.draft(reasoning_contract))
        fake_reduction["claims"][0]["status"] = "OPEN"
        fake_reduction["claims"].extend([
            {
                "claim_id": "RESIDUAL",
                "statement": "the residual condition holds",
                "kind": "INTERMEDIATE",
                "epistemic_class": "EXACT",
                "status": "SUPPORTED",
                "depends_on": [],
                "inference": "DEDUCTION",
                "warrant": "derived under the frozen assumptions",
                "evidence_refs": [],
                "defeaters": [],
                "target_link": "REQUIRED",
                "route_scope": "ASSIGNED",
            },
            {
                "claim_id": "IMPLICATION",
                "statement": "the residual condition implies the assigned claim",
                "kind": "CONCLUSION",
                "epistemic_class": "EXACT",
                "status": "SUPPORTED",
                "depends_on": ["RESIDUAL"],
                "inference": "REDUCTION",
                "warrant": "the recorded implication preserves the target",
                "evidence_refs": [],
                "defeaters": [],
                "target_link": "DIRECT",
                "route_scope": "ASSIGNED",
            },
        ])
        fake_reduction["hypotheses"][0]["claim_ids"] = ["IMPLICATION"]
        fake_reduction["attacks"][0]["claim_id"] = "IMPLICATION"
        fake_reduction["pivotal_claim_ids"] = ["IMPLICATION"]
        fake_reduction["closure_candidate_ids"] = ["IMPLICATION"]
        fake_reduction["subgoals"][0]["claim_id"] = "IMPLICATION"
        fake_reduction["requested_outcome"] = "STRICT_REDUCTION"
        fake_reduction["target_fidelity"]["claim_checks"] = [{
            "claim_id": "IMPLICATION",
            "relation": "ROUTE_LOCAL",
            "clause_results": [{
                "clause_id": clause_id,
                "status": "OPEN",
                "rationale": "the reduction preserves but does not discharge this clause",
                "evidence_refs": [],
            } for clause_id in (
                "ENDPOINT-EXACT", "QUANTIFIERS-EXACT", "MATHS-STRUCTURE",
                "MATHS-BOUNDARY",
            )],
            "scope_limit": "only the conditional reduction, not its residual",
        }]
        fake_reduction["claims"][-1]["target_link"] = "REQUIRED"
        fake_reduction["reduction_certificate"] = {
            "source_claim_id": "TARGET",
            "residual_claim_ids": ["RESIDUAL"],
            "implication_claim_id": "IMPLICATION",
            "direction": "RESIDUAL_IMPLIES_SOURCE",
            "coverage": "COMPLETE",
            "burden_changes": [{
                "axis": "OPEN_CORE",
                "before": "the original open core",
                "after": "the renamed original open core",
                "strict": False,
                "reason": "no actual burden changed",
            }],
        }
        fake_reduction_rejected = rejected(
            fake_reduction,
            "STRICT_REDUCTION",
            "no strict burden decrease",
        )

        weak_obstruction = _promotion_reasoning(reasoning.draft(reasoning_contract))
        weak_obstruction["claims"][0]["status"] = "OPEN"
        weak_obstruction["requested_outcome"] = "NEW_OBSTRUCTION"
        weak_obstruction["claims"][-1]["target_link"] = "REQUIRED"
        weak_obstruction["target_fidelity"]["claim_checks"][0].update({
            "relation": "ROUTE_LOCAL",
            "scope_limit": "only the assigned method family under its frozen assumptions",
        })
        for clause_result in weak_obstruction["target_fidelity"]["claim_checks"][0]["clause_results"]:
            clause_result["status"] = "OPEN"
            clause_result["rationale"] = "the method barrier does not decide this target clause"
        weak_obstruction["first_failing_gate"] = "the assigned method did not decide the claim"
        weak_obstruction["hypotheses"].append({
            **copy.deepcopy(weak_obstruction["hypotheses"][0]),
            "hypothesis_id": "H2",
            "discriminator": "a second wording of the same dependency audit",
            "status": "REJECTED",
        })
        weak_obstruction["obstruction_certificate"] = {
            "scope_statement": "the named method family fails in the frozen scope",
            "blocked_claim_ids": ["TARGET"],
            "covered_method_families": ["direct dependency audit"],
            "no_go_basis": "DEDUCTIVE",
            "decisive_claim_ids": ["C1"],
            "failure_domains": [],
            "surviving_alternatives": ["a mechanism-distinct route"],
            "limits": "only the named method and frozen assumptions",
            "revival_condition": "a genuinely different mechanism or discriminator",
        }
        weak_obstruction_rejected = rejected(
            weak_obstruction,
            "NEW_OBSTRUCTION",
            "mechanism-distinct hypotheses and discriminators",
        )

        unmarked_falsification = _promotion_reasoning(
            reasoning.draft(reasoning_contract)
        )
        unmarked_falsification["claims"][0]["status"] = "OPEN"
        unmarked_target_rejected = rejected(
            unmarked_falsification,
            "FALSIFICATION",
            "must mark the assigned TARGET refuted",
        )
        open_obligation = _promotion_reasoning(
            reasoning.draft(reasoning_contract)
        )
        open_obligation["obligations"] = [{
            "obligation_id": "O1",
            "claim_id": "C1",
            "kind": "DERIVATION",
            "statement": "supply the missing exponent bookkeeping",
            "status": "OPEN",
            "discharge": "",
            "evidence_refs": [],
        }]
        open_obligation_rejected = rejected(
            open_obligation,
            "FALSIFICATION",
            "unresolved obligations",
        )
        open_subgoal = _promotion_reasoning(reasoning.draft(reasoning_contract))
        open_subgoal["subgoals"][0]["status"] = "OPEN"
        open_subgoal_rejected = rejected(
            open_subgoal,
            "FALSIFICATION",
            "discharged subgoal",
        )
        broken_invariant = _promotion_reasoning(reasoning.draft(reasoning_contract))
        broken_invariant["invariants"][0]["status"] = "BROKEN"
        broken_invariant_rejected = rejected(
            broken_invariant,
            "FALSIFICATION",
            "invariant",
        )
        check(
            "reasoning gates accept exact closure and reject trace-derived overclaims",
            valid_exact["schema"] == "witsoc.reasoning-state.v1"
            and search_bounded_rejected
            and empirical_rejected
            and unbound_source_rejected
            and off_route_rejected
            and contradiction_rejected
            and fake_reduction_rejected
            and weak_obstruction_rejected
            and unmarked_target_rejected
            and open_obligation_rejected
            and open_subgoal_rejected
            and broken_invariant_rejected,
        )
    except Exception as exc:
        failed(
            "reasoning gates accept exact closure and reject trace-derived overclaims",
            exc,
        )

    try:
        lucas_target = kernel.target_record(
            "Does there exist an infinite sequence a_0, a_1, ... of positive integers "
            "satisfying a_(n+2) = a_(n+1) + a_n for every n >= 0, such that every "
            "a_k is composite and no integer d > 1 has a common factor with every "
            "term (equivalently, for every d > 1 there is k with gcd(d, a_k) = 1)?",
            "Erdos 276 endpoint-fidelity regression",
        )
        lucas_state = kernel.new_state(
            lucas_target,
            "OPEN_DISCOVERY",
            ["maths"],
            created_at="2026-01-01T00:00:00+00:00",
        )
        lucas_proposal = _proposal(
            "E276",
            "REFUTE",
            "audit the proposed U_n(7,9) witness clause by clause",
            "the complete all-index and no-finite-covering endpoint",
        )
        lucas_proposal["node_id"] = "ROOT"
        lucas_proposal["objective"] = (
            "Certify U_n(7,9) as an all-index composite witness with no finite "
            "prime-covering explanation."
        )
        lucas_explorer = _explorer_authorization(
            root, lucas_state, [lucas_proposal], "E276"
        )
        lucas_source_map = _synthetic_source_map(lucas_state)
        unanchored_source_map = copy.deepcopy(lucas_source_map)
        unanchored_source_map["entries"][0]["preconditions"] = [
            item for item in unanchored_source_map["entries"][0]["preconditions"]
            if not item.startswith("canonical_problem_id:")
        ]
        unanchored_source_map = seal_packet(unanchored_source_map)
        missing_catalog_anchor_rejected = False
        try:
            exploration._validate_canonical_open_target(
                lucas_state, unanchored_source_map, lucas_proposal
            )
        except exploration.ExplorationError as exc:
            missing_catalog_anchor_rejected = "problem-id preconditions" in str(exc)
        lucas_issued, lucas_episode = discovery.issue_best(
            lucas_state,
            [lucas_proposal],
            "episode-erdos-276-regression",
            "one exact witness audit is the bounded route",
            lucas_explorer,
            lucas_source_map,
        )
        lucas_contract = reasoning.build_contract(lucas_issued, lucas_episode)
        clause_ids = [
            item["clause_id"] for item in lucas_contract["target_contract"]["clauses"]
        ]
        distinction_ids = [
            item["distinction_id"]
            for item in lucas_contract["target_contract"]["semantic_distinctions"]
        ]

        route_refuted = _promotion_reasoning(reasoning.draft(lucas_contract))
        route_refuted["claims"][0]["status"] = "OPEN"
        route_refuted["claims"][1]["status"] = "REFUTED"
        route_refuted["claims"][2].update({
            "statement": (
                "U_n(7,9) changes the fixed Fibonacci recurrence, U_1=1 also "
                "violates all-index compositeness, and not using a covering does "
                "not prove the target's common-divisor exclusion."
            ),
            "target_link": "REQUIRED",
        })
        route_refuted["requested_outcome"] = "ROUTE_REFUTED"
        route_refuted["first_failing_gate"] = (
            "the proposed witness fails the initial-value and covering-nonexistence clauses"
        )
        route_refuted["target_fidelity"] = {
            "target_contract_sha256": lucas_contract["target_contract"]["payload_sha256"],
            "claim_checks": [{
                "claim_id": "C1",
                "relation": "ROUTE_LOCAL",
                "clause_results": [{
                    "clause_id": clause_id,
                    "status": (
                        "VIOLATED"
                        if clause_id in {"MATHS-STRUCTURE", "MATHS-BOUNDARY"}
                        else "OPEN"
                    ),
                    "rationale": (
                        "U_n(7,9) is a different recurrence from the frozen target"
                        if clause_id == "MATHS-STRUCTURE" else
                        "U_1 and U_2 violate the proposed witness boundary"
                        if clause_id == "MATHS-BOUNDARY" else
                        "refuting this witness does not decide the existential target"
                    ),
                    "evidence_refs": (
                        ["C1"]
                        if clause_id in {"MATHS-STRUCTURE", "MATHS-BOUNDARY"}
                        else []
                    ),
                } for clause_id in clause_ids],
                "scope_limit": "only the proposed U_n(7,9) witness and its derivation mechanism",
            }],
            "distinction_checks": [{
                "distinction_id": distinction_id,
                "status": "PRESERVED",
                "rationale": "derivation non-use and global nonexistence remain distinct",
                "evidence_refs": ["C1"],
            } for distinction_id in distinction_ids],
        }
        valid_route_refutation = reasoning.build_state(
            root, route_refuted, lucas_contract, expected_outcome="ROUTE_REFUTED"
        )

        bad_target_drift = copy.deepcopy(route_refuted)
        bad_target_drift["claims"][1]["status"] = "SUPPORTED"
        bad_target_drift["claims"][1]["warrant"] = (
            "the proposed route produced a candidate requiring endpoint audit"
        )
        bad_target_drift["claims"][2]["target_link"] = "DIRECT"
        bad_target_drift["requested_outcome"] = "CANDIDATE_PRODUCT"
        bad_target_drift["first_failing_gate"] = ""
        check_record = bad_target_drift["target_fidelity"]["claim_checks"][0]
        check_record["relation"] = "EXACT_TARGET"
        check_record["scope_limit"] = ""
        for item in check_record["clause_results"]:
            item["status"] = (
                "VIOLATED" if item["clause_id"] == "MATHS-STRUCTURE" else "SATISFIED"
            )
            item["evidence_refs"] = ["C1"]
        target_drift_rejected = False
        try:
            reasoning.build_state(
                root, bad_target_drift, lucas_contract,
                expected_outcome="CANDIDATE_PRODUCT",
            )
        except reasoning.ReasoningError as exc:
            target_drift_rejected = "does not satisfy every target clause" in str(exc)

        bad_exclusion = copy.deepcopy(bad_target_drift)
        for item in bad_exclusion["target_fidelity"]["claim_checks"][0]["clause_results"]:
            item["status"] = "SATISFIED"
        for item in bad_exclusion["target_fidelity"]["distinction_checks"]:
            item["status"] = "VIOLATED"
            item["rationale"] = "derivation non-use was substituted for nonexistence"
        exclusion_overclaim_rejected = False
        try:
            reasoning.build_state(
                root, bad_exclusion, lucas_contract,
                expected_outcome="CANDIDATE_PRODUCT",
            )
        except reasoning.ReasoningError as exc:
            exclusion_overclaim_rejected = "semantic distinctions" in str(exc)

        unsupported_distinction = copy.deepcopy(bad_exclusion)
        for item in unsupported_distinction["target_fidelity"]["distinction_checks"]:
            item["status"] = "PRESERVED"
            item["evidence_refs"] = []
        unsupported_distinction_rejected = False
        try:
            reasoning.build_state(
                root, unsupported_distinction, lucas_contract,
                expected_outcome="CANDIDATE_PRODUCT",
            )
        except reasoning.ReasoningError as exc:
            unsupported_distinction_rejected = (
                "lacks evidence for preserved semantic distinctions" in str(exc)
            )

        misclassified_obstruction = copy.deepcopy(bad_exclusion)
        for item in misclassified_obstruction["target_fidelity"]["distinction_checks"]:
            item["status"] = "PRESERVED"
        misclassified_obstruction["requested_outcome"] = "NEW_OBSTRUCTION"
        misclassified_obstruction["first_failing_gate"] = "the assigned route was refuted"
        obstruction_overclaim_rejected = False
        try:
            reasoning.build_state(
                root, misclassified_obstruction, lucas_contract,
                expected_outcome="NEW_OBSTRUCTION",
            )
        except reasoning.ReasoningError as exc:
            obstruction_overclaim_rejected = "incompatible target-fidelity relation" in str(exc)

        erdos_checks = {
            "route_refutation_is_local": (
                valid_route_refutation["requested_outcome"] == "ROUTE_REFUTED"
                and valid_route_refutation["claims"][0]["status"] == "OPEN"
            ),
            "catalog_anchor_required": missing_catalog_anchor_rejected,
            "recurrence_drift_rejected": target_drift_rejected,
            "exclusion_overclaim_rejected": exclusion_overclaim_rejected,
            "unsupported_distinction_rejected": unsupported_distinction_rejected,
            "obstruction_overclaim_rejected": obstruction_overclaim_rejected,
        }
        check(
            "Erdos 276 rejects recurrence drift, exclusion, and outcome overclaims",
            all(erdos_checks.values()),
            (
                "failed: " + ", ".join(
                    name for name, passed in erdos_checks.items() if not passed
                )
                if not all(erdos_checks.values()) else ""
            ),
        )
    except Exception as exc:
        failed(
            "Erdos 276 rejects recurrence drift, exclusion, and outcome overclaims",
            exc,
        )

    try:
        specifications = [
            {
                "actor_id": "independent-a",
                "failure_domain": "route-family-a",
                "resource_keys": ["ledger:a"],
                "independence": {
                    "method_lineage": "method:a",
                    "evidence_lineage": "evidence:a",
                    "data_lineage": "data:a",
                    "evaluation_lineage": "evaluation:a",
                },
                "proposal": _proposal("P1", "REFUTE", "separate by failure", "boundary object"),
            },
            {
                "actor_id": "independent-b",
                "failure_domain": "route-family-b",
                "resource_keys": ["ledger:b"],
                "independence": {
                    "method_lineage": "method:b",
                    "evidence_lineage": "evidence:b",
                    "data_lineage": "data:b",
                    "evaluation_lineage": "evaluation:b",
                },
                "proposal": _proposal("P2", "REDUCE", "separate by reduction", "quotient object"),
            },
        ]
        round_explorer = _explorer_authorization(
            root,
            state,
            [item["proposal"] for item in specifications],
            "P1",
        )
        round_source_map = _synthetic_source_map(state)
        issued, round_packet = rounds.issue_round(
            root,
            state,
            specifications,
            round_explorer,
            round_source_map,
            round_id="R1",
            rationale="two distinct mechanisms and failure domains",
            max_parallel=4,
        )
        round_gate = orchestration.next_action(issued)
        with tempfile.TemporaryDirectory(prefix="witsoc-round-handoffs-") as raw:
            workspace = Path(raw)
            task = workspace / "runs" / "round"
            handoffs = orchestration.build_round_handoffs(
                root,
                issued,
                round_packet,
                workspace_root=workspace,
                task_dir=task,
                output_dir=Path("workers"),
                source_map_value=round_source_map,
            )
            launch_gates = [
                orchestration.next_action(issued, handoff_value=item["handoff"])
                for item in handoffs
            ]
            children = []
            collect_gates = []
            for item in handoffs:
                draft = _finish_no_progress(item["draft"])
                draft.update({
                    "remaining_obstruction": "the independent route remains unresolved",
                    "revival_condition": "a new route-specific discriminator",
                })
                child = orchestration.build_delta(issued, draft, item["handoff"])
                children.append(child)
                collect_gates.append(
                    orchestration.next_action(issued, delta_value=child)
                )
        aggregate = rounds.build_delta(
            root, issued, round_packet, children, round_delta_id="R1-return"
        )
        returned = rounds.apply_delta(root, issued, aggregate)
        check(
            "independent round returns through conflict-visible merge",
            aggregate["aggregate_outcome"] == "MERGEABLE"
            and round_gate["stage"] == "BUILD_ROUND_HANDOFFS"
            and len(handoffs) == len(round_packet["episodes"])
            and all(
                gate["stage"] == "LAUNCH_BOUND_ROUND_RESEARCHER"
                and gate["worker_launch_allowed"]
                for gate in launch_gates
            )
            and all(
                gate["stage"] == "COLLECT_BOUND_ROUND_DELTA"
                and not gate["worker_launch_allowed"]
                for gate in collect_gates
            )
            and round_packet["independence_certificate"]["grade"] == "STRONG"
            and round_packet["independence_certificate"]["admission_eligible"] is True
            and any(item["kind"] == "SHARED_NODE" for item in aggregate["conflicts"])
            and returned["pending_episode"] is None
            and kernel.replay_report(returned)["ok"],
        )
    except Exception as exc:
        failed("independent round returns through conflict-visible merge", exc)

    try:
        with tempfile.TemporaryDirectory(prefix="witsoc-hints-") as raw:
            store = Path(raw)
            content = {
                "kind": "OBSTRUCTION",
                "summary": "a repeated structural obstruction",
                "rationale": "two exact feature axes coincide",
                "revival_condition": "a new discriminator changes one axis",
                "operator_ids": ["normalize-target"],
            }
            first = hint_memory.make_hint(
                root,
                domain="maths",
                features={"task_kind": "open", "obstruction_family": "coupling"},
                content=content,
                created_at="2026-01-01T00:00:00+00:00",
            )
            hint_memory.put(root, store, first)
            second = hint_memory.make_hint(
                root,
                domain="maths",
                features={
                    "task_kind": "open",
                    "obstruction_family": "coupling",
                    "method_family": "reduction",
                },
                content={**content, "summary": "a dependent structural hint"},
                created_at="2026-01-02T00:00:00+00:00",
            )
            hint_memory.put(root, store, second, depends_on=[first["hint_id"]])
            before = hint_memory.query(
                root,
                store,
                domain="maths",
                features={"task_kind": "open", "obstruction_family": "coupling"},
            )
            invalidated = hint_memory.invalidate(
                root, store, first["hint_id"], "synthetic invalidation", "sha256:" + "4" * 64
            )
            after = hint_memory.query(
                root,
                store,
                domain="maths",
                features={"task_kind": "open", "obstruction_family": "coupling"},
            )
            check(
                "hint memory is non-evidentiary and invalidates dependents",
                before["count"] == 2
                and len(invalidated["invalidated"]) == 2
                and after["count"] == 0,
            )
            receipt = seal_packet({
                "schema": "witsoc.receipt.v2",
                "receipt_id": "hint-contamination",
                "target_sha256": target["canonical_sha256"],
                "candidate_sha256": "1" * 64,
                "domain": "maths",
                "adapter": "synthetic",
                "tier": "bounded",
                "verdict": "PASS",
                "max_status": "CHECKED_BOUNDED",
                "artifact_sha256": "2" * 64,
                "input_refs": ["sha256:" + "3" * 64],
                "checks": {"synthetic": "PASS"},
                "evidence_refs": [first["hint_id"]],
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            try:
                contracts.validate_packet(root, "witsoc.receipt.v2", receipt)
            except contracts.ContractError:
                check("hint references cannot contaminate receipts", True)
            else:
                check("hint references cannot contaminate receipts", False)
    except Exception as exc:
        failed("hint memory is non-evidentiary and invalidates dependents", exc)

    try:
        candidate = _candidate(root, target["canonical_sha256"])
        transfer = bridges.translate_v2(
            root,
            "maths:conjecture-discovery",
            "bio:genetics-to-function",
            "candidate-to-transfer-v1",
            candidate,
            transfer_id="T1",
            scope={"synthetic": True},
        )
        first = bridges.build_envelope_v2(
            root,
            "B21",
            "maths:conjecture-discovery",
            "bio:genetics-to-function",
            "candidate-to-transfer-v1",
            "witsoc.candidate.v2",
            "witsoc.transfer.v2",
            target["canonical_sha256"],
            "C2",
            candidate,
            transfer,
            scope_owner="bio:genetics-to-function",
        )
        second = bridges.build_envelope_v2(
            root,
            "B22",
            "bio:genetics-to-function",
            "maths:structural-transfer",
            "identity:witsoc.transfer.v2",
            "witsoc.transfer.v2",
            "witsoc.transfer.v2",
            target["canonical_sha256"],
            "C2",
            transfer,
            transfer,
            scope_owner="bio:genetics-to-function",
            causation_id="B21",
        )
        branch = bridges.build_envelope_v2(
            root,
            "B23",
            "bio:genetics-to-function",
            "bio:cross-domain-transfer",
            "identity:witsoc.transfer.v2",
            "witsoc.transfer.v2",
            "witsoc.transfer.v2",
            target["canonical_sha256"],
            "C2",
            transfer,
            transfer,
            scope_owner="bio:genetics-to-function",
            causation_id="B21",
        )
        composition = bridges.compose_v2(root, [first, second], max_losses=1)
        path_plan = bridges.plan_v2(
            root, "maths:conjecture-discovery", "bio:genetics-to-function"
        )
        bridge_graph = bridges.compose_graph_v2(root, [branch, second, first])
        check(
            "bridge v2 plans and executes typed transforms and causal branches",
            composition["ok"]
            and len(composition["path"]) == 3
            and composition["losses"] == transfer["losses"]
            and transfer["candidate"] == candidate
            and path_plan["disposition"] == "READY"
            and bridge_graph["disposition"] == "READY"
            and bridge_graph["body"]["branches"]
        )
        try:
            bridges.compose_v2(root, [first, second], max_losses=0)
        except bridges.BridgeError:
            check("bridge v2 enforces its loss budget", True)
        else:
            check("bridge v2 enforces its loss budget", False)
    except Exception as exc:
        failed("bridge v2 plans and executes typed transforms and causal branches", exc)

    try:
        candidate = _candidate(root, target["canonical_sha256"])
        source_map = seal_packet({
            "schema": "witsoc.source-map.v2",
            "source_map_id": "synthetic-sources",
            "target_sha256": target["canonical_sha256"],
            "entries": [{
                "source_id": "S1",
                "source_type": "PRIMARY_RECORD",
                "locator": "synthetic:S1",
                "retrieved_sha256": "5" * 64,
                "claim_supported": candidate["claim"],
                "status": "ESTABLISHED",
                "preconditions": [],
                "reliability": "PRIMARY",
            }],
            "contradictions": [],
            "unresolved": [],
            "checked_at": "2026-01-01T00:00:00+00:00",
        })
        novelty = discovery.novelty_audit(
            root,
            candidate,
            source_map,
            [{
                "source_id": "S1",
                "relation": "SAME",
                "scope_match": True,
                "assumptions_match": True,
                "conclusion_match": True,
                "evidence_ref": "sha256:" + "5" * 64,
                "rationale": "same synthetic scoped statement",
            }],
            report_id="synthetic-novelty",
        )
        check(
            "novelty audit blocks a known claim without inferring correctness",
            novelty["body"]["novelty_status"] == "KNOWN"
            and novelty["body"]["correctness_inference"] == "NONE"
            and novelty["status_authority"] is False,
        )
    except Exception as exc:
        failed("novelty audit blocks a known claim without inferring correctness", exc)

    try:
        with tempfile.TemporaryDirectory(prefix="witsoc-assurance-") as raw:
            workspace = Path(raw) / "workspace"
            workspace.mkdir()

            def activated_state(task_name: str) -> tuple[dict[str, Any], Path, dict[str, Any]]:
                task = workspace / "runs" / task_name
                task.mkdir(parents=True)
                local_target = kernel.target_record(
                    f"Synthetic assurance target {task_name}.",
                    "exercise lifecycle assurance",
                )
                route = {
                    "activation": "WITSOC",
                    "sticky": True,
                    "decision": "SELECTED",
                    "mode": "CLAIM_VERIFICATION",
                    "mode_basis": ["explicit synthetic fixture"],
                    "mode_reference": "references/modes/claim_verification.md",
                    "domains": ["maths"],
                }
                receipt = assurance.build_activation_receipt(
                    root,
                    target=local_target,
                    route=route,
                    role="explorer",
                    resources=[{"kind": "root", **modes.skill_resource("SKILL.md")}],
                    load_plan={
                        "ok": True,
                        "role": "explorer",
                        "capabilities": ["frame:target-control"],
                        "commands": [],
                        "contracts": [],
                        "estimated_tokens": 0,
                        "deferred_extensions": [],
                    },
                    workspace={
                        "root": str(workspace),
                        "task_dir": str(task),
                        "task_dir_relative": task.relative_to(workspace).as_posix(),
                        "task_dir_existed_before_preflight": True,
                        "worker_mode": "INHERIT_BOUND",
                        "base_revision": None,
                        "artifact_returns": [],
                        "user_bound_paths_are_immutable": True,
                    },
                    plane_resolution={
                        "status": "NOT_REQUESTED",
                        "checks": [],
                        "problems": [],
                        "reason": "synthetic fixture",
                    },
                    coordination=modes.coordination_contract("CLAIM_VERIFICATION"),
                    protocol_resource=modes.skill_resource("references/orchestrator_protocol.md"),
                    side_effects=[],
                    dispatch_gate={"worker_launch_allowed": False},
                    problems=[],
                )
                local_state = kernel.new_state(
                    local_target,
                    "CLAIM_VERIFICATION",
                    ["maths"],
                    route_sha256=receipt["route"]["route_sha256"],
                    activation_binding=assurance.activation_binding(receipt),
                    created_at="2026-01-01T00:00:00+00:00",
                )
                return local_state, task, receipt

            assurance_state, assurance_task, activation = activated_state("review")
            tampered_activation = copy.deepcopy(activation)
            tampered_activation["resources"][0]["sha256"] = "0" * 64
            tampered_activation = seal_packet(tampered_activation)
            try:
                assurance.validate_activation(root, tampered_activation)
                activation_tamper_rejected = False
            except assurance.AssuranceError as exc:
                activation_tamper_rejected = "resource" in str(exc)

            product = assurance_task / "candidate.md"
            product.write_text("Candidate with unresolved exponent e^{?}.\n", encoding="utf-8")
            marker_draft = assurance.review_draft(
                root,
                assurance_state,
                review_id="marker-review",
                revision_id="snapshot-1",
                producer_id="producer",
                producer_method="construction",
                producer_failure_domains=["construction-error"],
                reviewer_id="reviewer",
                reviewer_method="independent-rederivation",
                reviewer_failure_domains=["review-derivation-error"],
                artifacts=[product],
                reviewed_item_ids=["ROOT"],
            )
            marker_detected = (
                marker_draft["checks"]["placeholder_scan"] == "FAIL"
                and marker_draft["automated_findings"][0]["code"] == "UNKNOWN_EXPONENT"
            )
            product.write_text("Candidate with every declared exponent fixed.\n", encoding="utf-8")
            review_draft = assurance.review_draft(
                root,
                assurance_state,
                review_id="accepted-review",
                revision_id="snapshot-2",
                producer_id="producer",
                producer_method="construction",
                producer_failure_domains=["construction-error"],
                reviewer_id="reviewer",
                reviewer_method="independent-rederivation",
                reviewer_failure_domains=["review-derivation-error"],
                artifacts=[product],
                reviewed_item_ids=["ROOT"],
            )
            for name, result in list(review_draft["checks"].items()):
                if result != "NOT_APPLICABLE":
                    review_draft["checks"][name] = "PASS"
            review_draft["verdict"] = "ACCEPT"
            review = assurance.build_review(root, assurance_state, review_draft)
            product.write_text("Candidate changed after accepted review.\n", encoding="utf-8")
            try:
                assurance.validate_review(root, assurance_state, review)
                stale_review_rejected = False
            except assurance.AssuranceError as exc:
                stale_review_rejected = "artifact bytes changed" in str(exc)

            terminal = orchestration.record_decision(
                assurance_state,
                decision_id="wait-for-external",
                action="WAIT_EXTERNAL",
                basis_refs=[assurance_state["state_sha256"]],
                alternatives=[],
                changed_axis="",
            )
            before_finalization = orchestration.next_action(terminal)
            finalization = assurance.build_finalization(
                root,
                terminal,
                finalization_id="synthetic-final",
                artifacts=[],
                review_paths=[],
            )
            (assurance_task / "finalization.json").write_text(
                json.dumps(finalization, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (assurance_task / "RESULT.md").write_text(
                assurance.render_result(terminal, finalization), encoding="utf-8"
            )
            after_finalization = orchestration.next_action(
                terminal, finalization_value=finalization
            )

            drift_state, drift_task, _receipt = activated_state("drift")
            episode = seal_packet({
                "schema": "witsoc.research-episode.v1",
                "episode_id": "E008",
                "route_fingerprint": "1" * 64,
                "core_fingerprint": "2" * 64,
                "node_id": "ROOT",
            })
            drift_state = kernel.apply_event(
                drift_state,
                kernel.build_event(
                    drift_state,
                    "EPISODE_ISSUED",
                    {"episode": episode},
                    "trace:issue-E008",
                ),
            )
            later_episode = seal_packet({
                "schema": "witsoc.research-episode.v1",
                "episode_id": "E009",
            })
            (drift_task / "episode-E009.json").write_text(
                json.dumps(later_episode, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            drift_audit = assurance.campaign_audit(root, drift_state)
            drift_codes = {item["code"] for item in drift_audit["body"]["blockers"]}
            legacy = assurance.legacy_audit(
                root,
                {"schema": "witsoc.orchestrator-handoff.v3", "target_sha256": "3" * 64},
                report_id="legacy-fixture",
            )

            check(
                "lifecycle assurance rejects trace-derived activation, review, state, and exit drift",
                activation_tamper_rejected
                and marker_detected
                and stale_review_rejected
                and before_finalization["stage"] == "BUILD_FINALIZATION"
                and before_finalization["completion_allowed"] is False
                and after_finalization["stage"] == "TERMINAL_WAIT_EXTERNAL"
                and after_finalization["completion_allowed"] is True
                and {"OUT_OF_BAND_EPISODE", "PENDING_STATE_DRIFT"} <= drift_codes
                and legacy["body"]["continuation_allowed"] is False
                and legacy["disposition"] == "BLOCKED",
            )
    except Exception as exc:
        failed(
            "lifecycle assurance rejects trace-derived activation, review, state, and exit drift",
            exc,
        )

    try:
        operator_results = []
        for manifest in sorted((root / "domains").glob("*/operators.json")):
            script = manifest.parent / "scripts" / "discovery_ops.py"
            completed = subprocess.run(
                [sys.executable, str(script), "self-test"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            payload = json.loads(completed.stdout)
            operator_results.append(completed.returncode == 0 and payload.get("ok") is True)
        check(
            "domain operator microkernels pass synthetic contract checks",
            len(operator_results) >= 2 and all(operator_results),
        )
    except Exception as exc:
        failed("domain operator microkernels pass synthetic contract checks", exc)

    try:
        generated = runtime_contracts.check(root)
        check("generated runtime contract is current", generated["ok"], "; ".join(generated["problems"]))
    except Exception as exc:
        failed("generated runtime contract is current", exc)

    return {
        "schema": "witsoc.advanced-selftest.v1",
        "cases": cases,
        "ok": all(item["ok"] for item in cases),
    }
