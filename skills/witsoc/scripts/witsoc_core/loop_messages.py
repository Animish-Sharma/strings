"""Sealed, typed Explorer and Researcher loop messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import contracts
from .canonical import seal_packet


SCHEMA = "witsoc.loop-message.v1"
RETURN_TYPES = {
    "REFRAME_REQUEST", "COUNTEREXAMPLE", "BARRIER_CERTIFICATE",
    "CLAIM_DELTA", "PROGRESS_REPORT",
}


class LoopMessageError(ValueError):
    pass


def build(
    contract: Mapping[str, Any],
    *,
    message_id: str,
    message_type: str,
    sender: str,
    recipient: str,
    summary: str,
    requested_change: str = "",
    failure_condition: str = "",
    claim_refs: list[str] | None = None,
    obligation_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    supersedes: list[str] | None = None,
) -> dict[str, Any]:
    return seal_packet({
        "schema": SCHEMA,
        "message_id": message_id,
        "message_type": message_type,
        "target_sha256": contract["target_sha256"],
        "episode_id": contract["episode_id"],
        "episode_sha256": contract["episode_sha256"],
        "base_state_sha256": contract["base_state_sha256"],
        "sender": sender,
        "recipient": recipient,
        "claim_refs": sorted(set(claim_refs or [])),
        "obligation_refs": sorted(set(obligation_refs or [])),
        "content": {
            "summary": summary,
            "requested_change": requested_change,
            "failure_condition": failure_condition,
        },
        "evidence_refs": sorted(set(evidence_refs or [])),
        "supersedes": sorted(set(supersedes or [])),
        "status_authority": False,
    })


def validate(
    root: Path, value: Mapping[str, Any], contract: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, SCHEMA, value)
    except contracts.ContractError as exc:
        raise LoopMessageError(str(exc)) from exc
    message_type = packet["message_type"]
    if message_type == "ATTACK_AUTHORIZATION":
        if (packet["sender"], packet["recipient"]) != ("EXPLORER", "RESEARCHER"):
            raise LoopMessageError("attack authorization must flow Explorer to Researcher")
    elif message_type in RETURN_TYPES:
        if (packet["sender"], packet["recipient"]) != ("RESEARCHER", "EXPLORER"):
            raise LoopMessageError("research return message must flow Researcher to Explorer")
    elif message_type == "REVIEW_CHALLENGE":
        if packet["recipient"] == packet["sender"]:
            raise LoopMessageError("review challenge requires distinct roles")
    elif message_type == "LEMMA_REQUEST" and packet["sender"] == packet["recipient"]:
        raise LoopMessageError("the request requires distinct roles")
    if message_type == "REFRAME_REQUEST" and not packet["content"]["requested_change"].strip():
        raise LoopMessageError("reframe request must name the requested change")
    if message_type in {"COUNTEREXAMPLE", "BARRIER_CERTIFICATE", "CLAIM_DELTA"} and not packet["claim_refs"]:
        raise LoopMessageError(f"{message_type} requires claim references")
    if message_type == "PROGRESS_REPORT" and not packet["content"]["failure_condition"].strip():
        raise LoopMessageError("progress report requires the first failing condition")
    if contract is not None:
        expected = {
            "target_sha256": contract["target_sha256"],
            "episode_id": contract["episode_id"],
            "episode_sha256": contract["episode_sha256"],
            "base_state_sha256": contract["base_state_sha256"],
        }
        for field, expected_value in expected.items():
            if packet[field] != expected_value:
                raise LoopMessageError(f"loop message has stale {field}")
    return packet


def authorization(contract: Mapping[str, Any]) -> dict[str, Any]:
    return build(
        contract,
        message_id=f"authorize:{contract['episode_id']}",
        message_type="ATTACK_AUTHORIZATION",
        sender="EXPLORER",
        recipient="RESEARCHER",
        summary=contract["objective"],
        failure_condition=contract["episode_return_condition"],
        claim_refs=["TARGET"],
    )


def research_return(
    contract: Mapping[str, Any], reasoning: Mapping[str, Any]
) -> dict[str, Any]:
    outcome = reasoning["requested_outcome"]
    message_type = {
        "ADMITTED_PRODUCT": "CLAIM_DELTA",
        "CANDIDATE_PRODUCT": "CLAIM_DELTA",
        "STRICT_REDUCTION": "CLAIM_DELTA",
        "FALSIFICATION": "COUNTEREXAMPLE",
        "TARGET_FALSIFIED": "COUNTEREXAMPLE",
        "ROUTE_REFUTED": "COUNTEREXAMPLE",
        "NEW_OBSTRUCTION": "BARRIER_CERTIFICATE",
        "METHOD_BARRIER": "BARRIER_CERTIFICATE",
        "CORE_SHARPENED": "CLAIM_DELTA",
        "POSITIVE_SIGNAL": "CLAIM_DELTA",
        "NO_PROGRESS": "PROGRESS_REPORT",
        "NO_DELTA": "PROGRESS_REPORT",
        "SESSION_CHECKPOINT": "PROGRESS_REPORT",
        "WAITING_EXTERNAL": "PROGRESS_REPORT",
    }[outcome]
    route = reasoning["route_compliance"]
    if route["status"] == "REFRAME_REQUIRED":
        message_type = "REFRAME_REQUEST"
    claim_refs = list(reasoning["closure_candidate_ids"] or reasoning["pivotal_claim_ids"])
    if message_type in {"COUNTEREXAMPLE", "BARRIER_CERTIFICATE", "CLAIM_DELTA"} and not claim_refs:
        claim_refs = ["TARGET"]
    evidence_refs = sorted({
        ref
        for collection in (reasoning["claims"], reasoning["attempts"], reasoning["attacks"])
        for item in collection
        for ref in item["evidence_refs"]
    })
    return build(
        contract,
        message_id=f"return:{contract['episode_id']}:{outcome.casefold()}",
        message_type=message_type,
        sender="RESEARCHER",
        recipient="EXPLORER",
        summary=f"Researcher returns {outcome} for the assigned route.",
        requested_change=route["reframe_request"],
        failure_condition=(
            reasoning["first_failing_gate"] or contract["episode_return_condition"]
        ),
        claim_refs=claim_refs,
        obligation_refs=[
            item["obligation_id"] for item in reasoning["obligations"]
            if item["status"] != "DISCHARGED"
        ],
        evidence_refs=evidence_refs,
        supersedes=[contract["authorization"]["payload_sha256"]],
    )
