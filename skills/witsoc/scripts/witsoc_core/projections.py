"""Read-only compatibility projections and reducer-owned admission packets."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from . import contracts, kernel
from .canonical import seal_packet


class ProjectionError(ValueError):
    pass


def state_view(root: Path, state_value: Mapping[str, Any], view: str) -> dict[str, Any]:
    state = kernel.validate_state(state_value)
    views = {"frame": "FRAME_COMPATIBILITY", "campaign": "CAMPAIGN_COMPATIBILITY", "summary": "RESEARCH_SUMMARY"}
    if view not in views:
        raise ProjectionError(f"unknown projection view {view!r}")
    claims = {
        item["item_id"]: {
            "statement": item["statement"],
            "status": item["status"],
            "dependencies": copy.deepcopy(item["dependencies"]),
            "evidence_refs": copy.deepcopy(item["evidence_refs"]),
            "admission_ref": item["admission_ref"],
        }
        for item in state["frontier"]["items"]
    }
    body = {
        "schema": "witsoc.projection.v1",
        "view": views[view],
        "source_state_sha256": state["state_sha256"],
        "target_sha256": state["target"]["canonical_sha256"],
        "revision": state["revision"],
        "status_authority": False,
        "status": state["status"],
        "outcome": state["outcome"],
        "claims": claims,
        "active": sorted(set(state["frontier"]["active"])),
        "obstructions": copy.deepcopy(state["frontier"]["obstructions"]),
    }
    return contracts.validate_packet(root, "witsoc.projection.v1", seal_packet(body))


def admission_packet(
    root: Path,
    state_value: Mapping[str, Any],
    frame_value: Mapping[str, Any],
    claim_id: str,
    item_id: str,
) -> dict[str, Any]:
    import reducer

    state = kernel.validate_state(state_value)
    frame = copy.deepcopy(dict(frame_value))
    replay = reducer.replay(frame)
    if not replay["consistent"]:
        raise ProjectionError("frame admission history is inconsistent")
    claim = (frame.get("claims") or {}).get(claim_id)
    if not isinstance(claim, dict):
        raise ProjectionError(f"frame state has no claim {claim_id!r}")
    item = next((entry for entry in state["frontier"]["items"] if entry["item_id"] == item_id), None)
    if item is None or claim.get("target_sha256") != item["target_sha256"]:
        raise ProjectionError("frame claim does not bind the requested frontier item")
    admission_ref = claim.get("admitted_by")
    if claim.get("status") in kernel.ACCEPTED and not admission_ref:
        raise ProjectionError("accepted frame claim has no reducer admission reference")
    body = {
        "schema": "witsoc.admission.v2",
        "admission_id": f"projection:{claim_id}:{frame.get('revision', 0)}",
        "target_sha256": item["target_sha256"],
        "item_id": item_id,
        "status": claim.get("status", "OPEN"),
        "frame_admission_ref": admission_ref or f"rejection:{claim_id}",
        "frame_state_sha256": reducer.state_hash(frame),
        "frame_revision": int(frame.get("revision", 0)),
        "evidence_refs": list(claim.get("evidence_refs") or []),
        "independent_review_ref": claim.get("independent_review_ref"),
    }
    return contracts.validate_packet(root, "witsoc.admission.v2", seal_packet(body))


def apply_frame_admission(
    root: Path,
    state_value: Mapping[str, Any],
    frame_value: Mapping[str, Any],
    claim_id: str,
    item_id: str,
    event_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = admission_packet(root, state_value, frame_value, claim_id, item_id)
    updated = kernel.import_frame_admission(
        state_value, frame_value, claim_id, item_id, event_id
    )
    return updated, packet
