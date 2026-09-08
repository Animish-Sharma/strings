"""Compatibility migrations into the replayable kernel state."""

from __future__ import annotations

from typing import Any, Mapping

from . import kernel
from .canonical import digest_value


class MigrationError(ValueError):
    pass


def from_frame_state(
    frame_value: Mapping[str, Any],
    *,
    domain: str,
    mode: str = "OPEN_DISCOVERY",
    created_at: str | None = None,
) -> dict[str, Any]:
    import reducer

    frame = dict(frame_value)
    replay = reducer.replay(frame)
    if not replay["consistent"]:
        raise MigrationError("frame state history is inconsistent: " + "; ".join(replay["problems"][:4]))
    claims = frame.get("claims") or {}
    root_id = frame.get("root_claim_id")
    root = claims.get(root_id)
    if not isinstance(root, dict):
        raise MigrationError("frame state has no valid root claim")
    statement = str(root.get("statement") or "").strip()
    if not statement:
        raise MigrationError("frame root claim has no exact statement")
    target = kernel.target_record(
        statement,
        "migrated from frame-state-v1",
        canonical_sha256=root.get("target_sha256") or frame.get("target_sha256"),
    )
    ceiling = root.get("ceiling") or frame.get("ceiling") or "VERIFIED"
    if ceiling not in kernel.STATUSES:
        ceiling = "VERIFIED"
    state = kernel.new_state(
        target,
        mode,
        [domain],
        ceiling=ceiling,
        route_sha256=digest_value({"source": "frame-state-v1", "state": reducer.state_hash(frame)}),
        created_at=created_at,
    )
    id_map = {root_id: "ROOT"}
    for claim_id in sorted(claims):
        if claim_id == root_id:
            continue
        id_map[claim_id] = claim_id
        claim = claims[claim_id]
        status = claim.get("status", "OPEN")
        kind = "PRODUCT" if status in kernel.ACCEPTED else (
            "REDUCTION" if claim.get("dependencies") else "OPEN_CORE"
        )
        item = {
            "item_id": claim_id,
            "kind": kind,
            "statement": str(claim.get("statement") or claim_id),
            "target_sha256": claim.get("target_sha256") or target["canonical_sha256"],
            "status": "OPEN",
            "dependencies": [],
            "evidence_refs": [],
            "route_fingerprint": None,
            "admission_ref": None,
        }
        event = kernel.build_event(
            state, "FRONTIER_ADD", {"item": item, "activate": status not in kernel.ACCEPTED},
            f"migrate:add:{claim_id}",
        )
        state = kernel.apply_event(state, event)

    for claim_id in sorted(claims):
        dependencies = [id_map[item] for item in claims[claim_id].get("dependencies", []) if item in id_map]
        item_id = id_map[claim_id]
        current = next(item for item in state["frontier"]["items"] if item["item_id"] == item_id)
        if dependencies != current["dependencies"]:
            event = kernel.build_event(
                state,
                "FRONTIER_LINK",
                {"item_id": item_id, "dependencies": dependencies},
                f"migrate:link:{claim_id}",
            )
            state = kernel.apply_event(state, event)

    for claim_id in sorted(claims):
        if claims[claim_id].get("status", "OPEN") == "OPEN":
            continue
        state = kernel.import_frame_admission(
            state,
            frame,
            claim_id,
            id_map[claim_id],
            f"migrate:status:{claim_id}",
        )
    basis = reducer.state_hash(frame)
    decision = {
        "decision_id": "migration:frame-state-v1",
        "action": "IMPORT_COMPATIBILITY_STATE",
        "basis_refs": [f"sha256:{basis}"],
        "alternatives": [],
        "changed_axis": "state representation only",
    }
    event = kernel.build_event(
        state, "DECISION_RECORD", {"decision": decision}, "migrate:complete"
    )
    return kernel.apply_event(state, event)
