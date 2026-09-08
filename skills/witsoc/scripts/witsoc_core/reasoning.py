"""Compact, evidence-typed Researcher reasoning state and semantic gates."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from . import contracts, loop_messages, target_semantics
from .canonical import seal_packet


CONTRACT_SCHEMA = "witsoc.reasoning-contract.v1"
STATE_SCHEMA = "witsoc.reasoning-state.v1"
DRAFT_SCHEMA = "witsoc.reasoning-state-draft.v1"
PROMOTING_OUTCOMES = {
    "ADMITTED_PRODUCT", "CANDIDATE_PRODUCT", "STRICT_REDUCTION", "FALSIFICATION",
    "TARGET_FALSIFIED", "ROUTE_REFUTED", "NEW_OBSTRUCTION", "METHOD_BARRIER",
    "CORE_SHARPENED",
}
ROUTE_FIELDS = {
    "method_family", "mechanism", "structural_object", "required_result",
    "target_effect", "assumptions",
}
EVIDENCE_REQUIRES_REFS = {
    "SOURCE_VERIFIED", "COMPUTATIONAL_BOUNDED", "EMPIRICAL", "SEARCH_BOUNDED",
}
EVIDENCE_INFERENCE = {
    "SOURCE_VERIFIED": "SOURCE_IMPORT",
    "COMPUTATIONAL_BOUNDED": "BOUNDED_CHECK",
    "EMPIRICAL": "OBSERVATION",
    "SEARCH_BOUNDED": "SEARCH_SCOPE",
}
FIXED_LIMITS = {
    "max_claims": 24,
    "max_hypotheses": 4,
    "max_active_hypotheses": 1,
    "max_attempts": 16,
    "max_attacks": 20,
    "max_contradictions": 8,
    "max_obligations": 24,
    "max_subgoals": 20,
    "max_invariants": 12,
}


class ReasoningError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise ReasoningError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _unique(items: list[Mapping[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in items:
        identifier = raw[field]
        if identifier in result:
            raise ReasoningError(f"{label} identifier {identifier!r} is duplicated")
        result[identifier] = copy.deepcopy(dict(raw))
    return result


def build_contract(
    state: Mapping[str, Any], episode: Mapping[str, Any]
) -> dict[str, Any]:
    body = {
        "schema": CONTRACT_SCHEMA,
        "contract_id": f"reasoning-contract:{episode['episode_id']}",
        "target_sha256": state["target"]["canonical_sha256"],
        "episode_id": episode["episode_id"],
        "episode_sha256": episode["payload_sha256"],
        "base_state_sha256": episode["base_state_sha256"],
        "route_fingerprint": episode["route_fingerprint"],
        "lane": episode["lane"],
        "assigned_route": copy.deepcopy(episode["route"]),
        "assigned_claim": episode["claim"],
        "objective": episode["objective"],
        "episode_return_condition": episode.get(
            "return_condition", episode.get("stop_condition", "")
        ),
        "campaign_authority": False,
        "allowed_termination": "EPISODE_RETURN_ONLY",
        "limits": copy.deepcopy(FIXED_LIMITS),
        "allowed_route_scopes": ["ASSIGNED", "LOCAL_MUTATION"],
        "required_route_fields": sorted(ROUTE_FIELDS),
        "closure_safe_evidence": ["EXACT", "SOURCE_VERIFIED"],
        "target_contract": copy.deepcopy(
            (episode.get("adjudication") or {}).get("target_contract")
        ),
        "rules": {
            "raw_deliberation_forbidden": True,
            "closure_requires_acyclic_claims": True,
            "open_contradictions_block_promotion": True,
            "off_route_requires_reframe": True,
            "pivotal_claims_require_pressure": True,
            "open_obligations_block_promotion": True,
            "researcher_cannot_reframe": True,
            "subgoals_required_for_promotion": True,
            "invariants_preserved_for_promotion": True,
            "target_fidelity_required": True,
            "campaign_stop_forbidden": True,
            "unresolved_return_requires_followup": True,
            "barrier_is_nonterminal": True,
        },
    }
    adjudication = episode.get("adjudication") or {}
    if "source_refs" in adjudication:
        body["source_map_ref"] = adjudication.get("source_map_ref")
        body["allowed_source_refs"] = list(
            adjudication.get("source_verified_refs", [])
        )
    body["authorization"] = loop_messages.authorization(body)
    return seal_packet(body)


def validate_contract(
    root: Path,
    value: Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None = None,
    episode: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, CONTRACT_SCHEMA, value)
    except contracts.ContractError as exc:
        raise ReasoningError(str(exc)) from exc
    if packet["limits"] != FIXED_LIMITS:
        raise ReasoningError("reasoning contract limits are not canonical")
    if packet["campaign_authority"] is not False:
        raise ReasoningError("Researcher reasoning cannot carry campaign authority")
    if packet["allowed_termination"] != "EPISODE_RETURN_ONLY":
        raise ReasoningError("Researcher may terminate only its assigned episode")
    if set(packet["required_route_fields"]) != ROUTE_FIELDS:
        raise ReasoningError("reasoning contract route fields are incomplete")
    if packet["allowed_route_scopes"] != ["ASSIGNED", "LOCAL_MUTATION"]:
        raise ReasoningError("reasoning contract route scopes are not canonical")
    if packet["closure_safe_evidence"] != ["EXACT", "SOURCE_VERIFIED"]:
        raise ReasoningError("reasoning contract closure evidence is not canonical")
    target_contract = packet["target_contract"]
    if target_contract is not None:
        try:
            target_semantics.validate(root, target_contract)
        except target_semantics.TargetSemanticsError as exc:
            raise ReasoningError(str(exc)) from exc
        if target_contract["target_sha256"] != packet["target_sha256"]:
            raise ReasoningError("reasoning target contract belongs to another target")
    try:
        authorization = loop_messages.validate(root, packet["authorization"], packet)
    except loop_messages.LoopMessageError as exc:
        raise ReasoningError(str(exc)) from exc
    if authorization["message_type"] != "ATTACK_AUTHORIZATION":
        raise ReasoningError("reasoning contract lacks Explorer attack authorization")
    has_source_map = "source_map_ref" in packet
    has_source_refs = "allowed_source_refs" in packet
    if has_source_map != has_source_refs:
        raise ReasoningError("reasoning source binding is incomplete")
    if has_source_map:
        if packet["source_map_ref"] is None and packet["allowed_source_refs"]:
            raise ReasoningError("reasoning contract has source refs without a source map")
    if (state is None) != (episode is None):
        raise ReasoningError("state and episode must be supplied together")
    if state is not None and episode is not None:
        if state["mode"] == "OPEN_DISCOVERY" and target_contract is None:
            raise ReasoningError("open discovery reasoning lacks a target acceptance contract")
        if packet != build_contract(state, episode):
            raise ReasoningError("reasoning contract does not bind the issued episode")
    return packet


def draft(contract_value: Mapping[str, Any]) -> dict[str, Any]:
    contract = copy.deepcopy(dict(contract_value))
    return {
        "schema": DRAFT_SCHEMA,
        "reasoning_id": f"reasoning:{contract['episode_id']}",
        "target_sha256": contract["target_sha256"],
        "episode_id": contract["episode_id"],
        "episode_sha256": contract["episode_sha256"],
        "route_fingerprint": contract["route_fingerprint"],
        "phase": "SCREENING",
        "route_compliance": {
            "status": "ASSIGNED",
            "changed_axis": "",
            "preserved_route_fields": list(contract["required_route_fields"]),
            "reframe_request": "",
            "side_result_claim_ids": [],
        },
        "claims": [
            {
                "claim_id": "TARGET",
                "statement": contract["assigned_claim"],
                "kind": "TARGET",
                "epistemic_class": "UNKNOWN",
                "status": "OPEN",
                "depends_on": [],
                "inference": "GIVEN",
                "warrant": "",
                "evidence_refs": [],
                "defeaters": [],
                "target_link": "DIRECT",
                "route_scope": "ASSIGNED",
            },
            {
                "claim_id": "OBJECTIVE",
                "statement": contract["objective"],
                "kind": "ROUTE_OBJECTIVE",
                "epistemic_class": "UNKNOWN",
                "status": "OPEN",
                "depends_on": [],
                "inference": "GIVEN",
                "warrant": "",
                "evidence_refs": [],
                "defeaters": [],
                "target_link": "REQUIRED",
                "route_scope": "ASSIGNED",
            },
        ],
        "hypotheses": [],
        "attacks": [],
        "attempts": [],
        "contradictions": [],
        "obligations": [],
        "subgoals": [{
            "subgoal_id": "SG-TARGET",
            "claim_id": "OBJECTIVE",
            "statement": contract["objective"],
            "status": "OPEN",
            "dependencies": [],
            "method": contract["assigned_route"]["mechanism"],
            "failure_condition": contract["episode_return_condition"],
            "evidence_refs": [],
        }],
        "invariants": [{
            "invariant_id": "INV-ROUTE",
            "statement": contract["assigned_route"]["structural_object"],
            "scope": "ASSIGNED_ROUTE",
            "status": "ASSUMED",
            "evidence_refs": [],
        }],
        "pivotal_claim_ids": [],
        "closure_candidate_ids": [],
        "target_fidelity": {
            "target_contract_sha256": (
                contract["target_contract"]["payload_sha256"]
                if contract["target_contract"] is not None else None
            ),
            "claim_checks": [],
            "distinction_checks": [],
        },
        "requested_outcome": "NO_PROGRESS",
        "reduction_certificate": None,
        "obstruction_certificate": None,
        "first_failing_gate": "",
    }


def build_state(
    root: Path,
    draft_value: Mapping[str, Any],
    contract_value: Mapping[str, Any],
    *,
    expected_outcome: str,
) -> dict[str, Any]:
    contract = validate_contract(root, contract_value)
    required = {
        "schema", "reasoning_id", "target_sha256", "episode_id", "episode_sha256",
        "route_fingerprint", "phase", "route_compliance", "claims", "hypotheses", "attacks",
        "attempts", "contradictions", "obligations", "subgoals", "invariants",
        "pivotal_claim_ids", "closure_candidate_ids",
        "target_fidelity",
        "requested_outcome", "reduction_certificate", "obstruction_certificate",
        "first_failing_gate",
    }
    _closed(draft_value, required, "reasoning draft")
    if draft_value.get("schema") != DRAFT_SCHEMA:
        raise ReasoningError("reasoning draft schema is invalid")
    body = copy.deepcopy(dict(draft_value))
    body["schema"] = STATE_SCHEMA
    packet = seal_packet(body)
    return validate_state(
        root, packet, contract, expected_outcome=expected_outcome, final=True
    )


def _claim_ancestors(claim_id: str, claims: Mapping[str, Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    stack = list(claims[claim_id]["depends_on"])
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(claims[current]["depends_on"])
    return result


def _validate_claims(
    packet: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    claims = _unique(packet["claims"], "claim_id", "claim")
    if len(claims) > contract["limits"]["max_claims"]:
        raise ReasoningError("reasoning state exceeds the claim limit")
    targets = [item for item in claims.values() if item["kind"] == "TARGET"]
    if len(targets) != 1 or targets[0]["claim_id"] != "TARGET":
        raise ReasoningError("reasoning state requires exactly one TARGET claim")
    target = targets[0]
    if (
        target["statement"] != contract["assigned_claim"]
        or target["target_link"] != "DIRECT"
        or target["route_scope"] != "ASSIGNED"
    ):
        raise ReasoningError("TARGET claim differs from the assigned claim")
    objectives = [
        item for item in claims.values() if item["kind"] == "ROUTE_OBJECTIVE"
    ]
    if len(objectives) != 1 or objectives[0]["claim_id"] != "OBJECTIVE":
        raise ReasoningError("reasoning state requires exactly one OBJECTIVE claim")
    objective = objectives[0]
    if (
        objective["statement"] != contract["objective"]
        or objective["target_link"] != "REQUIRED"
        or objective["route_scope"] != "ASSIGNED"
    ):
        raise ReasoningError("OBJECTIVE claim differs from the assigned route objective")
    for claim in claims.values():
        dependencies = claim["depends_on"]
        if claim["claim_id"] in dependencies or set(dependencies) - set(claims):
            raise ReasoningError(f"claim {claim['claim_id']!r} has invalid dependencies")
        if claim["kind"] == "SIDE_RESULT" and (
            claim["target_link"] != "SIDE" or claim["route_scope"] != "OFF_ROUTE"
        ):
            raise ReasoningError("side-result claims must remain off-route and non-closing")
        evidence_class = claim["epistemic_class"]
        expected_inference = EVIDENCE_INFERENCE.get(evidence_class)
        if expected_inference and claim["inference"] != expected_inference:
            raise ReasoningError(
                f"claim {claim['claim_id']!r} evidence class requires {expected_inference}"
            )
        if evidence_class in EVIDENCE_REQUIRES_REFS and not claim["evidence_refs"]:
            raise ReasoningError(
                f"claim {claim['claim_id']!r} evidence class requires evidence references"
            )
        if evidence_class == "SOURCE_VERIFIED":
            allowed = set(contract.get("allowed_source_refs", []))
            if contract.get("source_map_ref") is None or not set(claim["evidence_refs"]) <= allowed:
                raise ReasoningError(
                    f"claim {claim['claim_id']!r} cites a source outside the Explorer-bound map"
                )
        if claim["status"] == "SUPPORTED" and claim["kind"] != "TARGET" and not claim["warrant"].strip():
            raise ReasoningError(f"supported claim {claim['claim_id']!r} has no warrant")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(identifier: str) -> None:
        if identifier in visiting:
            raise ReasoningError(f"claim dependency cycle passes through {identifier!r}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in claims[identifier]["depends_on"]:
            walk(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in claims:
        walk(identifier)
    for claim in claims.values():
        if claim["status"] != "SUPPORTED":
            continue
        unresolved = [
            dependency for dependency in claim["depends_on"]
            if claims[dependency]["status"] != "SUPPORTED"
        ]
        if unresolved:
            raise ReasoningError(
                f"supported claim {claim['claim_id']!r} consumes unresolved dependencies {unresolved}"
            )
    return claims


def _validate_route(
    packet: Mapping[str, Any], contract: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    route = packet["route_compliance"]
    preserved = set(route["preserved_route_fields"])
    if not preserved <= ROUTE_FIELDS:
        raise ReasoningError("route compliance names an unknown route field")
    off_route = {
        identifier for identifier, claim in claims.items()
        if claim["route_scope"] == "OFF_ROUTE"
    }
    side_results = set(route["side_result_claim_ids"])
    if off_route != side_results:
        raise ReasoningError("off-route claims and declared side results differ")
    status = route["status"]
    if status == "ASSIGNED":
        if route["changed_axis"] or route["reframe_request"] or side_results:
            raise ReasoningError("assigned route cannot carry mutation or reframe fields")
        if preserved != ROUTE_FIELDS:
            raise ReasoningError("assigned route must preserve every semantic field")
    elif status == "LOCAL_MUTATION":
        if not route["changed_axis"].strip() or route["reframe_request"] or side_results:
            raise ReasoningError("local mutation requires one changed axis and no reframe")
        if len(preserved) < len(ROUTE_FIELDS) - 1:
            raise ReasoningError("local mutation fails to preserve the rest of the route")
    else:
        if not route["reframe_request"].strip() or not side_results:
            raise ReasoningError("off-route work requires a typed reframe request and side result")


def _validate_closure(
    packet: Mapping[str, Any], contract: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    closure_ids = packet["closure_candidate_ids"]
    if len(closure_ids) != len(set(closure_ids)) or set(closure_ids) - set(claims):
        raise ReasoningError("closure candidates are unknown or duplicated")
    safe = set(contract["closure_safe_evidence"])
    for identifier in closure_ids:
        claim = claims[identifier]
        if (
            claim["status"] != "SUPPORTED"
            or claim["epistemic_class"] not in safe
            or claim["route_scope"] == "OFF_ROUTE"
            or claim["target_link"] not in {"DIRECT", "REQUIRED"}
        ):
            raise ReasoningError(
                f"closure candidate {identifier!r} is not supported by closure-safe evidence"
            )
        for ancestor_id in _claim_ancestors(identifier, claims):
            ancestor = claims[ancestor_id]
            if ancestor["status"] != "SUPPORTED" or ancestor["epistemic_class"] not in safe:
                raise ReasoningError(
                    f"closure candidate {identifier!r} depends on non-closing claim {ancestor_id!r}"
                )


def _validate_target_fidelity(
    packet: Mapping[str, Any],
    contract: Mapping[str, Any],
    claims: Mapping[str, Mapping[str, Any]],
) -> None:
    fidelity = packet["target_fidelity"]
    target_contract = contract["target_contract"]
    expected_sha = target_contract["payload_sha256"] if target_contract is not None else None
    if fidelity["target_contract_sha256"] != expected_sha:
        raise ReasoningError("target fidelity matrix is bound to a different contract")
    checks = _unique(fidelity["claim_checks"], "claim_id", "target fidelity claim")
    distinctions = _unique(
        fidelity["distinction_checks"], "distinction_id", "semantic distinction check"
    )
    if target_contract is None:
        if checks or distinctions:
            raise ReasoningError("source-free legacy reasoning cannot invent target fidelity")
        return
    closure_ids = set(packet["closure_candidate_ids"])
    if set(checks) != closure_ids:
        raise ReasoningError("target fidelity checks must cover exactly every closure candidate")
    clauses = {item["clause_id"]: item for item in target_contract["clauses"]}
    expected_distinctions = {
        item["distinction_id"] for item in target_contract["semantic_distinctions"]
    }
    if set(distinctions) != expected_distinctions:
        raise ReasoningError("target fidelity omits or invents a semantic distinction")
    if packet["requested_outcome"] in PROMOTING_OUTCOMES:
        failed = [
            identifier for identifier, item in distinctions.items()
            if item["status"] != "PRESERVED"
        ]
        if failed:
            raise ReasoningError(
                f"promotion violates or leaves open semantic distinctions: {failed}"
            )
        unsupported = [
            identifier for identifier, item in distinctions.items()
            if not item["evidence_refs"]
        ]
        if unsupported:
            raise ReasoningError(
                f"promotion lacks evidence for preserved semantic distinctions: {unsupported}"
            )
    for claim_id, check in checks.items():
        claim = claims[claim_id]
        results = _unique(check["clause_results"], "clause_id", "target clause result")
        if set(results) != set(clauses):
            raise ReasoningError(
                f"target fidelity for {claim_id!r} omits or invents acceptance clauses"
            )
        relation = check["relation"]
        statuses = {item["status"] for item in results.values()}
        if relation in {"EXACT_TARGET", "SUFFICIENT_FOR_TARGET"}:
            if statuses != {"SATISFIED"} or check["scope_limit"].strip():
                raise ReasoningError(
                    f"{relation} claim {claim_id!r} does not satisfy every target clause"
                )
            missing_boundary_evidence = [
                clause_id for clause_id, clause in clauses.items()
                if clause["kind"] in {"BOUNDARY", "EXCLUSION"}
                and not results[clause_id]["evidence_refs"]
            ]
            if missing_boundary_evidence:
                raise ReasoningError(
                    "endpoint closure lacks boundary/exclusion evidence for "
                    f"{missing_boundary_evidence}"
                )
        elif relation == "REFUTES_TARGET":
            if "VIOLATED" not in statuses or not check["scope_limit"].strip():
                raise ReasoningError("target refutation lacks a violated clause and witness scope")
        else:
            if not check["scope_limit"].strip():
                raise ReasoningError(
                    f"non-endpoint claim {claim_id!r} lacks an explicit scope limit"
                )
            if relation != "SIDE_RESULT" and statuses <= {"SATISFIED"}:
                raise ReasoningError(
                    f"non-endpoint claim {claim_id!r} is falsely marked as full target coverage"
                )
        if claim["target_link"] == "DIRECT" and relation not in {
            "EXACT_TARGET", "SUFFICIENT_FOR_TARGET", "REFUTES_TARGET",
        }:
            raise ReasoningError("a direct target claim has only route-local fidelity")
        if relation == "SIDE_RESULT" and claim["route_scope"] != "OFF_ROUTE":
            raise ReasoningError("a fidelity side result is not marked off route")
        if relation != "SIDE_RESULT" and claim["route_scope"] == "OFF_ROUTE":
            raise ReasoningError("an off-route claim is not classified as a fidelity side result")
    relations = {item["relation"] for item in checks.values()}
    allowed_relations = {
        "ADMITTED_PRODUCT": {"EXACT_TARGET", "SUFFICIENT_FOR_TARGET"},
        "CANDIDATE_PRODUCT": {"EXACT_TARGET", "SUFFICIENT_FOR_TARGET"},
        "FALSIFICATION": {"REFUTES_TARGET"},
        "TARGET_FALSIFIED": {"REFUTES_TARGET"},
        "STRICT_REDUCTION": {"NECESSARY_FOR_TARGET", "ROUTE_LOCAL"},
        "ROUTE_REFUTED": {"ROUTE_LOCAL"},
        "NEW_OBSTRUCTION": {"NECESSARY_FOR_TARGET", "ROUTE_LOCAL"},
        "METHOD_BARRIER": {"NECESSARY_FOR_TARGET", "ROUTE_LOCAL"},
        "CORE_SHARPENED": {"NECESSARY_FOR_TARGET", "ROUTE_LOCAL"},
    }.get(packet["requested_outcome"])
    if allowed_relations is not None and (not relations or not relations <= allowed_relations):
        raise ReasoningError(
            f"{packet['requested_outcome']} has an incompatible target-fidelity relation"
        )


def _validate_search(
    packet: Mapping[str, Any], contract: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]], *, final: bool
) -> None:
    hypotheses = _unique(packet["hypotheses"], "hypothesis_id", "hypothesis")
    attacks = _unique(packet["attacks"], "attack_id", "attack")
    attempts = _unique(packet["attempts"], "attempt_id", "attempt")
    if len(hypotheses) > contract["limits"]["max_hypotheses"]:
        raise ReasoningError("reasoning state exceeds the hypothesis limit")
    if len(attacks) > contract["limits"]["max_attacks"]:
        raise ReasoningError("reasoning state exceeds the attack limit")
    if len(attempts) > contract["limits"]["max_attempts"]:
        raise ReasoningError("reasoning state exceeds the attempt limit")
    active = [item for item in hypotheses.values() if item["status"] == "ACTIVE"]
    if len(active) > contract["limits"]["max_active_hypotheses"]:
        raise ReasoningError("more than one hypothesis is active")
    if final and packet["requested_outcome"] != "WAITING_EXTERNAL" and active:
        raise ReasoningError("a completed return cannot retain an active hypothesis")
    for item in hypotheses.values():
        if set(item["claim_ids"]) - set(claims):
            raise ReasoningError(f"hypothesis {item['hypothesis_id']!r} names an unknown claim")
        if final and not item["claim_ids"]:
            raise ReasoningError(f"hypothesis {item['hypothesis_id']!r} has no claim output")
    for item in attacks.values():
        if item["claim_id"] not in claims:
            raise ReasoningError(f"attack {item['attack_id']!r} names an unknown claim")
    fingerprints: set[tuple[str, str, str]] = set()
    for item in attempts.values():
        if item["hypothesis_id"] not in hypotheses:
            raise ReasoningError(f"attempt {item['attempt_id']!r} names an unknown hypothesis")
        if not item["fixed_axes"]:
            raise ReasoningError(f"attempt {item['attempt_id']!r} has no fixed axes")
        if item["changed_axis"].casefold() in {
            axis.casefold() for axis in item["fixed_axes"]
        }:
            raise ReasoningError(
                f"attempt {item['attempt_id']!r} changes an axis it declares fixed"
            )
        fingerprint = (
            item["method_family"].casefold(),
            item["changed_axis"].casefold(),
            item["diagnostic"].casefold(),
        )
        if fingerprint in fingerprints:
            raise ReasoningError("an unchanged attempt is repeated")
        fingerprints.add(fingerprint)
        if item["result"] == "SUPPORTED" and (
            item["failure_class"] != "NONE" or item["failure_domain"] != "NONE"
        ):
            raise ReasoningError("a supported attempt cannot carry a failure")
        if item["result"] != "SUPPORTED" and (
            item["failure_class"] == "NONE" or item["failure_domain"] == "NONE"
        ):
            raise ReasoningError("a non-supporting attempt requires a failure class and domain")
    pivotal = packet["pivotal_claim_ids"]
    if len(pivotal) != len(set(pivotal)) or set(pivotal) - set(claims):
        raise ReasoningError("pivotal claims are unknown or duplicated")
    pressure = {
        item["claim_id"] for item in attacks.values() if item["result"] != "NOT_RUN"
    }
    if final and packet["requested_outcome"] != "WAITING_EXTERNAL":
        if not hypotheses:
            raise ReasoningError("a completed attack requires at least one discriminating hypothesis")
        if not pivotal:
            raise ReasoningError("a completed attack requires at least one pivotal claim")
        if not attempts:
            raise ReasoningError("a completed attack requires at least one recorded attempt")
        missing_pressure = sorted(set(pivotal) - pressure)
        if missing_pressure:
            raise ReasoningError(
                f"pivotal claims were not pressure-tested: {missing_pressure}"
            )
    if packet["requested_outcome"] in {"NEW_OBSTRUCTION", "METHOD_BARRIER"}:
        mechanisms = {
            " ".join(item["mechanism"].casefold().split())
            for item in hypotheses.values()
        }
        discriminators = {
            " ".join(item["discriminator"].casefold().split())
            for item in hypotheses.values()
        }
        if len(hypotheses) < 2 or len(mechanisms) < 2 or len(discriminators) < 2:
            raise ReasoningError(
                "barrier certification requires mechanism-distinct hypotheses and discriminators"
            )
    if packet["requested_outcome"] in PROMOTING_OUTCOMES:
        if not packet["closure_candidate_ids"]:
            raise ReasoningError("a promoting outcome requires a closure candidate")
        if not set(packet["closure_candidate_ids"]) <= set(pivotal):
            raise ReasoningError("every closure candidate must be marked pivotal")
        survived = {
            item["claim_id"] for item in attacks.values() if item["result"] == "SURVIVED"
        }
        missing = sorted(set(pivotal) - survived)
        if missing:
            raise ReasoningError(f"pivotal claims lack a survived pressure test: {missing}")


def _validate_contradictions(
    packet: Mapping[str, Any], contract: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    contradictions = _unique(
        packet["contradictions"], "contradiction_id", "contradiction"
    )
    if len(contradictions) > contract["limits"]["max_contradictions"]:
        raise ReasoningError("reasoning state exceeds the contradiction limit")
    pairs: set[tuple[str, str]] = set()
    open_items = []
    for item in contradictions.values():
        left, right = item["left_claim_id"], item["right_claim_id"]
        if left == right or left not in claims or right not in claims:
            raise ReasoningError("contradiction endpoints are invalid")
        pair = tuple(sorted((left, right)))
        if pair in pairs:
            raise ReasoningError("contradiction pair is duplicated")
        pairs.add(pair)
        if item["status"] == "OPEN":
            open_items.append(item)
            if item["resolution"]:
                raise ReasoningError("an open contradiction cannot claim a resolution")
            if claims[left]["status"] != "CONFLICTED" or claims[right]["status"] != "CONFLICTED":
                raise ReasoningError("open contradiction endpoints must be marked CONFLICTED")
        elif not item["resolution"].strip():
            raise ReasoningError("a closed contradiction requires an explicit resolution")
    if open_items and packet["requested_outcome"] in PROMOTING_OUTCOMES:
        raise ReasoningError("open contradictions block promotion")


def _validate_obligations(
    packet: Mapping[str, Any], contract: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    obligations = _unique(packet["obligations"], "obligation_id", "obligation")
    if len(obligations) > contract["limits"]["max_obligations"]:
        raise ReasoningError("reasoning state exceeds the obligation limit")
    for item in obligations.values():
        claim_id = item["claim_id"]
        if claim_id not in claims:
            raise ReasoningError(
                f"obligation {item['obligation_id']!r} names an unknown claim"
            )
        if item["status"] == "OPEN" and item["discharge"].strip():
            raise ReasoningError("an open obligation cannot claim a discharge")
        if item["status"] != "OPEN" and not item["discharge"].strip():
            raise ReasoningError("a closed or conditional obligation requires its disposition")
        if item["status"] == "DISCHARGED" and not item["evidence_refs"]:
            raise ReasoningError("a discharged obligation requires exact evidence references")
    if packet["requested_outcome"] in PROMOTING_OUTCOMES:
        closure_path: set[str] = set(packet["closure_candidate_ids"])
        for identifier in list(closure_path):
            closure_path.update(_claim_ancestors(identifier, claims))
        unresolved = sorted(
            item["obligation_id"] for item in obligations.values()
            if item["claim_id"] in closure_path and item["status"] != "DISCHARGED"
        )
        if unresolved:
            raise ReasoningError(
                f"closure path retains unresolved obligations: {unresolved}"
            )


def _validate_proof_state(
    packet: Mapping[str, Any],
    contract: Mapping[str, Any],
    claims: Mapping[str, Mapping[str, Any]],
    *,
    final: bool,
) -> None:
    subgoals = _unique(packet["subgoals"], "subgoal_id", "subgoal")
    invariants = _unique(packet["invariants"], "invariant_id", "invariant")
    if not subgoals or len(subgoals) > contract["limits"]["max_subgoals"]:
        raise ReasoningError("reasoning state requires a bounded nonempty subgoal graph")
    if not invariants or len(invariants) > contract["limits"]["max_invariants"]:
        raise ReasoningError("reasoning state requires bounded route invariants")
    route_invariant = invariants.get("INV-ROUTE")
    if route_invariant is None or (
        route_invariant["statement"] != contract["assigned_route"]["structural_object"]
        or route_invariant["scope"] != "ASSIGNED_ROUTE"
    ):
        raise ReasoningError("reasoning state changed the assigned route invariant")
    for item in subgoals.values():
        if item["claim_id"] not in claims:
            raise ReasoningError(f"subgoal {item['subgoal_id']!r} names an unknown claim")
        if item["subgoal_id"] in item["dependencies"] or set(item["dependencies"]) - set(subgoals):
            raise ReasoningError(f"subgoal {item['subgoal_id']!r} has invalid dependencies")
        claim = claims[item["claim_id"]]
        if item["status"] == "DISCHARGED" and claim["status"] not in {"SUPPORTED", "REFUTED"}:
            raise ReasoningError(f"discharged subgoal {item['subgoal_id']!r} has no decided claim")
        if item["status"] == "REFUTED" and claim["status"] != "REFUTED":
            raise ReasoningError(f"refuted subgoal {item['subgoal_id']!r} has no refuted claim")
        if item["status"] == "BLOCKED" and not item["failure_condition"].strip():
            raise ReasoningError(f"blocked subgoal {item['subgoal_id']!r} lacks a failure condition")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(identifier: str) -> None:
        if identifier in visiting:
            raise ReasoningError(f"subgoal dependency cycle passes through {identifier!r}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in subgoals[identifier]["dependencies"]:
            walk(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in subgoals:
        walk(identifier)
    if final and packet["phase"] != "RETURN":
        raise ReasoningError("completed Researcher state must enter RETURN phase")
    if packet["requested_outcome"] in PROMOTING_OUTCOMES:
        if any(item["status"] != "PRESERVED" for item in invariants.values()):
            raise ReasoningError("promotion requires every declared invariant to be preserved")
        discharged_claims = {
            item["claim_id"] for item in subgoals.values()
            if item["status"] == "DISCHARGED"
        }
        if not set(packet["closure_candidate_ids"]) <= discharged_claims:
            raise ReasoningError("each closure candidate requires a discharged subgoal")


def _validate_certificates(
    packet: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    outcome = packet["requested_outcome"]
    reduction = packet["reduction_certificate"]
    obstruction = packet["obstruction_certificate"]
    if outcome == "STRICT_REDUCTION":
        if reduction is None:
            raise ReasoningError("STRICT_REDUCTION requires a reduction certificate")
        known = set(claims)
        identifiers = {
            reduction["source_claim_id"], reduction["implication_claim_id"],
            *reduction["residual_claim_ids"],
        }
        if not identifiers <= known or reduction["source_claim_id"] != "TARGET":
            raise ReasoningError("reduction certificate names invalid claims")
        if reduction["implication_claim_id"] not in packet["closure_candidate_ids"]:
            raise ReasoningError("reduction implication is not a closure candidate")
        if not any(item["strict"] for item in reduction["burden_changes"]):
            raise ReasoningError("reduction certificate shows no strict burden decrease")
        if any(
            item["strict"] and item["before"].strip().casefold() == item["after"].strip().casefold()
            for item in reduction["burden_changes"]
        ):
            raise ReasoningError("strict burden decrease has identical before and after states")
    elif reduction is not None:
        raise ReasoningError("only STRICT_REDUCTION may carry a reduction certificate")
    if outcome in {"NEW_OBSTRUCTION", "METHOD_BARRIER"}:
        if obstruction is None:
            raise ReasoningError("a barrier outcome requires an obstruction certificate")
        known = set(claims)
        decisive = set(obstruction["decisive_claim_ids"])
        if set(obstruction["blocked_claim_ids"]) - known or decisive - known:
            raise ReasoningError("obstruction certificate names unknown claims")
        if not decisive <= set(packet["closure_candidate_ids"]):
            raise ReasoningError("obstruction basis is not closure-safe")
        attempt_methods = {item["method_family"] for item in packet["attempts"]}
        if not set(obstruction["covered_method_families"]) <= attempt_methods:
            raise ReasoningError("obstruction claims a method family that was not attempted")
        attempt_failures = {
            item["failure_domain"] for item in packet["attempts"]
            if item["result"] != "SUPPORTED"
        }
        if not set(obstruction["failure_domains"]) <= attempt_failures:
            raise ReasoningError("obstruction claims a failure domain absent from its attempts")
        if obstruction["no_go_basis"] == "REPEATED_INDEPENDENT_FAILURE":
            if len(set(obstruction["failure_domains"])) < 2:
                raise ReasoningError("repeated-failure obstruction lacks independent failure domains")
    elif obstruction is not None:
        raise ReasoningError("only a typed barrier outcome may carry an obstruction certificate")
    if outcome in {
        "NO_PROGRESS", "NO_DELTA", "ROUTE_REFUTED", "NEW_OBSTRUCTION",
        "METHOD_BARRIER", "CORE_SHARPENED", "SESSION_CHECKPOINT", "WAITING_EXTERNAL",
    } and not packet["first_failing_gate"].strip():
        raise ReasoningError(f"{outcome} requires the first failing gate")


def _validate_outcome_alignment(
    packet: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]
) -> None:
    outcome = packet["requested_outcome"]
    target = claims["TARGET"]
    objective = claims["OBJECTIVE"]
    if outcome in {"FALSIFICATION", "TARGET_FALSIFIED"}:
        if target["status"] != "REFUTED":
            raise ReasoningError("FALSIFICATION must mark the assigned TARGET refuted")
        decisive = [claims[item] for item in packet["closure_candidate_ids"]]
        if not any(
            item["kind"] == "CONCLUSION" and item["target_link"] == "DIRECT"
            for item in decisive
        ):
            raise ReasoningError(
                "FALSIFICATION requires a direct closure-safe conclusion"
            )
    elif outcome == "ADMITTED_PRODUCT":
        if target["status"] != "SUPPORTED" or objective["status"] != "SUPPORTED":
            raise ReasoningError(
                "ADMITTED_PRODUCT requires supported TARGET and OBJECTIVE claims"
            )
    elif outcome == "CANDIDATE_PRODUCT":
        if target["status"] != "OPEN" or objective["status"] != "SUPPORTED":
            raise ReasoningError(
                "CANDIDATE_PRODUCT must keep TARGET open while supporting the route objective"
            )
    elif outcome == "ROUTE_REFUTED":
        if target["status"] != "OPEN" or objective["status"] != "REFUTED":
            raise ReasoningError(
                "ROUTE_REFUTED must keep TARGET open and refute only OBJECTIVE"
            )
    elif outcome in {
        "STRICT_REDUCTION", "NEW_OBSTRUCTION", "METHOD_BARRIER", "CORE_SHARPENED",
        "POSITIVE_SIGNAL", "NO_PROGRESS", "NO_DELTA", "SESSION_CHECKPOINT",
        "WAITING_EXTERNAL",
    }:
        if target["status"] in {"SUPPORTED", "REFUTED"}:
            raise ReasoningError(f"{outcome} cannot return a decided TARGET")
    if outcome in {"NO_PROGRESS", "NO_DELTA", "SESSION_CHECKPOINT", "WAITING_EXTERNAL"} and packet["closure_candidate_ids"]:
        raise ReasoningError(f"{outcome} cannot carry a closure candidate")


def validate_state(
    root: Path,
    value: Mapping[str, Any],
    contract_value: Mapping[str, Any],
    *,
    expected_outcome: str | None = None,
    final: bool = True,
) -> dict[str, Any]:
    contract = validate_contract(root, contract_value)
    try:
        packet = contracts.validate_packet(root, STATE_SCHEMA, value)
    except contracts.ContractError as exc:
        raise ReasoningError(str(exc)) from exc
    expected = {
        "target_sha256": contract["target_sha256"],
        "episode_id": contract["episode_id"],
        "episode_sha256": contract["episode_sha256"],
        "route_fingerprint": contract["route_fingerprint"],
    }
    for field, expected_value in expected.items():
        if packet[field] != expected_value:
            raise ReasoningError(f"reasoning state {field} is stale")
    if expected_outcome is not None and packet["requested_outcome"] != expected_outcome:
        raise ReasoningError("reasoning state outcome differs from the delta")
    claims = _validate_claims(packet, contract)
    _validate_route(packet, contract, claims)
    _validate_closure(packet, contract, claims)
    _validate_target_fidelity(packet, contract, claims)
    _validate_search(packet, contract, claims, final=final)
    _validate_contradictions(packet, contract, claims)
    _validate_obligations(packet, contract, claims)
    _validate_proof_state(packet, contract, claims, final=final)
    _validate_certificates(packet, claims)
    _validate_outcome_alignment(packet, claims)
    if packet["requested_outcome"] in PROMOTING_OUTCOMES and packet["route_compliance"]["status"] == "REFRAME_REQUIRED":
        raise ReasoningError("off-route side results cannot promote the assigned episode")
    return packet


def summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reasoning_id": value["reasoning_id"],
        "episode_id": value["episode_id"],
        "requested_outcome": value["requested_outcome"],
        "phase": value["phase"],
        "route_status": value["route_compliance"]["status"],
        "claims": len(value["claims"]),
        "hypotheses": len(value["hypotheses"]),
        "attempts": len(value["attempts"]),
        "attacks": len(value["attacks"]),
        "open_contradictions": sum(
            item["status"] == "OPEN" for item in value["contradictions"]
        ),
        "open_obligations": sum(
            item["status"] != "DISCHARGED" for item in value["obligations"]
        ),
        "open_subgoals": sum(
            item["status"] not in {"DISCHARGED", "REFUTED"} for item in value["subgoals"]
        ),
        "broken_invariants": sum(
            item["status"] == "BROKEN" for item in value["invariants"]
        ),
        "closure_candidates": list(value["closure_candidate_ids"]),
        "first_failing_gate": value["first_failing_gate"],
        "payload_sha256": value["payload_sha256"],
    }
