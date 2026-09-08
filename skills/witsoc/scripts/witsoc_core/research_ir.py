"""Construct sealed v2 research IR packets without domain reasoning."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from . import contracts
from .canonical import digest_value, seal_packet


class ResearchIRError(ValueError):
    pass


def request(
    root: Path,
    statement: str,
    *,
    intent: str = "",
    constraints: list[str] | None = None,
    requested_output: str = "witsoc.decision.v2",
) -> dict[str, Any]:
    statement = statement.strip()
    if not statement:
        raise ResearchIRError("research request statement is empty")
    body = {
        "schema": "witsoc.request.v2",
        "request_id": f"RQ-{digest_value(statement)[:16]}",
        "statement": statement,
        "intent": intent.strip(),
        "constraints": list(constraints or []),
        "requested_output": requested_output,
    }
    return contracts.validate_packet(root, "witsoc.request.v2", seal_packet(body))


def target(
    root: Path,
    request_packet: Mapping[str, Any],
    *,
    mode: str,
    domains: list[str],
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = contracts.validate_packet(root, "witsoc.request.v2", request_packet)
    identity = {
        "statement": source["statement"],
        "intent": source["intent"],
        "constraints": source["constraints"],
        "scope": copy.deepcopy(dict(scope or {})),
    }
    body = {
        "schema": "witsoc.target.v2",
        "target_id": f"WT-{digest_value(identity)[:16]}",
        "statement": source["statement"],
        "intent": source["intent"],
        "constraints": source["constraints"],
        "mode": mode,
        "domains": sorted(set(domains)),
        "scope": identity["scope"],
        "content_sha256": digest_value(identity),
    }
    return contracts.validate_packet(root, "witsoc.target.v2", seal_packet(body))


def frontier_projection(root: Path, state_value: Mapping[str, Any]) -> dict[str, Any]:
    from . import kernel

    state = kernel.validate_state(state_value)
    items = [
        {
            key: copy.deepcopy(item[key])
            for key in (
                "item_id", "kind", "statement", "status", "dependencies",
                "evidence_refs", "admission_ref",
            )
        }
        for item in state["frontier"]["items"]
    ]
    body = {
        "schema": "witsoc.frontier.v2",
        "target_sha256": state["target"]["canonical_sha256"],
        "state_sha256": state["state_sha256"],
        "revision": state["revision"],
        "items": items,
        "active": sorted(set(state["frontier"]["active"])),
        "obstruction_refs": sorted(
            item["obstruction_id"] for item in state["frontier"]["obstructions"]
        ),
        "frontier_measure": sum(1 for item in items if item["status"] == "OPEN"),
    }
    return contracts.validate_packet(root, "witsoc.frontier.v2", seal_packet(body))
