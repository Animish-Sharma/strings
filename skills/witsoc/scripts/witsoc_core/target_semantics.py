"""Sealed target-acceptance clauses shared by Explorer and Researcher."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping

from . import contracts
from .canonical import digest_value, seal_packet


SCHEMA = "witsoc.target-acceptance.v1"
NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|without|unless|except|forbid(?:den)?|exclude[ds]?)\b",
    re.IGNORECASE,
)


class TargetSemanticsError(ValueError):
    pass


def _unique(items: list[Mapping[str, Any]], field: str, label: str) -> None:
    values = [item[field] for item in items]
    if len(values) != len(set(values)):
        raise TargetSemanticsError(f"{label} identifiers are duplicated")


def build(
    root: Path,
    state: Mapping[str, Any],
    target_model: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "schema": SCHEMA,
        "target_sha256": state["target"]["canonical_sha256"],
        "interpretation_sha256": digest_value(target_model["interpretation"]),
        "mode": state["mode"],
        "domains": sorted(set(state["domains"])),
        "clauses": copy.deepcopy(target_model["acceptance_clauses"]),
        "semantic_distinctions": copy.deepcopy(target_model["semantic_distinctions"]),
        "domain_controls": copy.deepcopy(target_model["domain_controls"]),
    }
    return validate(root, seal_packet(body), state=state)


def validate(
    root: Path,
    value: Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, SCHEMA, value)
    except contracts.ContractError as exc:
        raise TargetSemanticsError(str(exc)) from exc
    clauses = packet["clauses"]
    distinctions = packet["semantic_distinctions"]
    _unique(clauses, "clause_id", "target clause")
    _unique(distinctions, "distinction_id", "semantic distinction")
    kinds = {item["kind"] for item in clauses}
    if "ENDPOINT" not in kinds:
        raise TargetSemanticsError("target acceptance contract lacks an ENDPOINT clause")
    if packet["mode"] == "OPEN_DISCOVERY" and "QUANTIFIER" not in kinds:
        raise TargetSemanticsError("open discovery target lacks a QUANTIFIER clause")
    if "maths" in packet["domains"] and packet["mode"] == "OPEN_DISCOVERY":
        if "BOUNDARY" not in kinds:
            raise TargetSemanticsError("open mathematics target lacks a BOUNDARY clause")
    if "bio" in packet["domains"] and packet["mode"] == "OPEN_DISCOVERY":
        required = {"EVIDENCE_STANDARD", "GENERALIZATION"}
        if not required <= kinds:
            raise TargetSemanticsError(
                "open biology target lacks EVIDENCE_STANDARD or GENERALIZATION clauses"
            )
    controls = packet["domain_controls"]
    for domain in set(packet["domains"]) & {"maths", "bio"}:
        values = controls.get(domain)
        if not isinstance(values, Mapping) or not values:
            raise TargetSemanticsError(f"target contract lacks {domain} controls")
        if any(str(item).strip().upper() == "UNRECORDED" for item in values.values()):
            raise TargetSemanticsError(f"target contract retains unrecorded {domain} controls")
    interpretation = None
    if state is not None:
        expected = {
            "target_sha256": state["target"]["canonical_sha256"],
            "interpretation_sha256": digest_value(state["target"]["statement"]),
            "mode": state["mode"],
            "domains": sorted(set(state["domains"])),
        }
        for field, expected_value in expected.items():
            if packet[field] != expected_value:
                raise TargetSemanticsError(f"target acceptance {field} is stale")
        interpretation = state["target"]["statement"]
    if interpretation and NEGATION_PATTERN.search(interpretation):
        if "EXCLUSION" not in kinds:
            raise TargetSemanticsError(
                "a negated or mechanism-excluding target requires an EXCLUSION clause"
            )
        if not any(item["relation"] != "EQUIVALENT" for item in distinctions):
            raise TargetSemanticsError(
                "a negated or mechanism-excluding target requires a non-equivalence audit"
            )
    return packet
