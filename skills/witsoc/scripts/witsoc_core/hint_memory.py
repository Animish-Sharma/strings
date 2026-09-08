"""Structurally indexed, non-evidentiary memory for attention and analogy."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import contracts
from .canonical import atomic_write_json, canonical_json, digest_value, load_json, seal_packet, utc_now


HINT_SCHEMA = "witsoc.memory-hint.v1"
INDEX_SCHEMA = "witsoc.hint-index.v1"
INVALIDATION_SCHEMA = "witsoc.hint-invalidation.v1"
KINDS = {"ROUTE", "OBSTRUCTION", "FAILURE", "TRANSFER", "TECHNIQUE"}
COMMON_FEATURES = {
    "task_kind", "operator", "obstruction_family", "evidence_pattern", "scale_regime",
    "failure_domain", "representation", "dependency_shape", "verification_tier",
}
DOMAIN_FEATURES = {
    "maths": {
        "object_family", "quantifier_shape", "conclusion_shape", "method_family",
        "bound_regime", "construction_family",
    },
    "bio": {
        "claim_layer", "biological_scale", "intervention_class", "readout_class",
        "context_class", "unit_relation", "mechanism_shape",
    },
    "archival": {"source_class", "transmission_shape", "dating_regime", "independence_shape"},
}
CONTAMINATION_MARKERS = (
    "held-out answer", "held_out_answer", "answer key", "evaluation key", "benchmark answer",
)


class HintMemoryError(ValueError):
    pass


def _index_path(store: Path) -> Path:
    return store / "hint-index.json"


def _object_path(store: Path, hint_id: str) -> Path:
    address = hint_id.removeprefix("hint:")
    return store / "hint-objects" / address[:2] / f"{address}.json"


def _invalidation_path(store: Path, record_id: str) -> Path:
    return store / "hint-invalidations" / record_id[:2] / f"{record_id}.json"


def _index_digest(index: Mapping[str, Any]) -> str:
    return digest_value({key: value for key, value in index.items() if key != "index_sha256"})


def init_store(store: Path) -> dict[str, Any]:
    store = store.expanduser().resolve()
    store.mkdir(parents=True, exist_ok=True)
    index = {
        "schema": INDEX_SCHEMA,
        "hints": [],
        "dependencies": {},
        "invalidations": {},
        "index_sha256": "",
    }
    index["index_sha256"] = _index_digest(index)
    atomic_write_json(_index_path(store), index)
    return index


def load_index(store: Path) -> dict[str, Any]:
    path = _index_path(store.expanduser().resolve())
    if not path.is_file():
        return init_store(store)
    index = load_json(path)
    required = {"schema", "hints", "dependencies", "invalidations", "index_sha256"}
    if set(index) != required or index["schema"] != INDEX_SCHEMA or index["index_sha256"] != _index_digest(index):
        raise HintMemoryError("hint index shape or content hash is invalid")
    return index


def _write_index(store: Path, index: dict[str, Any]) -> None:
    index["hints"] = sorted(set(index["hints"]))
    index["dependencies"] = {
        key: sorted(set(value)) for key, value in sorted(index["dependencies"].items())
    }
    index["invalidations"] = dict(sorted(index["invalidations"].items()))
    index["index_sha256"] = _index_digest(index)
    atomic_write_json(_index_path(store.expanduser().resolve()), index)


def _normalize_features(domain: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if domain not in DOMAIN_FEATURES:
        raise HintMemoryError(f"no structural feature vocabulary for domain {domain!r}")
    allowed = COMMON_FEATURES | DOMAIN_FEATURES[domain]
    unknown = set(value) - allowed
    if unknown:
        raise HintMemoryError(f"non-structural or unknown hint features: {sorted(unknown)}")
    if len(value) < 2:
        raise HintMemoryError("a structural hint requires at least two feature axes")
    result: dict[str, Any] = {}
    for key, raw in value.items():
        if isinstance(raw, (str, int, float, bool)) and not isinstance(raw, complex):
            if isinstance(raw, float) and not math.isfinite(raw):
                raise HintMemoryError(f"hint feature {key!r} is not finite")
            normalized = " ".join(raw.split()) if isinstance(raw, str) else raw
            if normalized == "":
                raise HintMemoryError(f"hint feature {key!r} is empty")
            result[key] = normalized
        elif isinstance(raw, list) and raw and all(isinstance(item, (str, int, float, bool)) for item in raw):
            result[key] = sorted(set(raw), key=lambda item: canonical_json(item))
        else:
            raise HintMemoryError(f"hint feature {key!r} must be a scalar or non-empty scalar array")
    return dict(sorted(result.items()))


def _content(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"kind", "summary", "rationale", "revival_condition", "operator_ids"}
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise HintMemoryError(f"hint content shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    result = copy.deepcopy(dict(value))
    if result["kind"] not in KINDS:
        raise HintMemoryError(f"unknown hint kind {result['kind']!r}")
    for field in ("summary", "rationale", "revival_condition"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise HintMemoryError(f"hint content {field} is empty")
    if not isinstance(result["operator_ids"], list) or any(
        not isinstance(item, str) or not item.strip() for item in result["operator_ids"]
    ):
        raise HintMemoryError("hint operator_ids must be an array of non-empty strings")
    result["operator_ids"] = sorted(set(result["operator_ids"]))
    blob = canonical_json(result).casefold()
    marker = next((item for item in CONTAMINATION_MARKERS if item in blob), None)
    if marker:
        raise HintMemoryError(f"hint content contains forbidden evaluation material marker {marker!r}")
    return result


def make_hint(
    root: Path,
    *,
    domain: str,
    features: Mapping[str, Any],
    content: Mapping[str, Any],
    scope: Mapping[str, Any] | None = None,
    provenance_refs: Iterable[str] = (),
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_features = _normalize_features(domain, features)
    normalized_content = _content(content)
    references = sorted(set(provenance_refs))
    if any(not isinstance(item, str) or not item.strip() for item in references):
        raise HintMemoryError("hint provenance references must be non-empty strings")
    body = {
        "domain": domain,
        "features": normalized_features,
        "content": normalized_content,
        "provenance_refs": references,
        "scope": copy.deepcopy(dict(scope or {})),
        "non_evidentiary": True,
        "created_at": created_at or utc_now(),
    }
    packet = seal_packet({
        "schema": HINT_SCHEMA,
        "hint_id": "hint:" + digest_value(body),
        "structural_fingerprint": digest_value({"domain": domain, "features": normalized_features}),
        **body,
    })
    try:
        return contracts.validate_packet(root, "witsoc.memory-hint.v1", packet)
    except contracts.ContractError as exc:
        raise HintMemoryError(str(exc)) from exc


def get(root: Path, store: Path, hint_id: str) -> dict[str, Any]:
    path = _object_path(store.expanduser().resolve(), hint_id)
    if not path.is_file():
        raise HintMemoryError(f"hint {hint_id!r} does not exist")
    packet = contracts.validate_packet(root, "witsoc.memory-hint.v1", load_json(path))
    if packet["hint_id"] != hint_id:
        raise HintMemoryError("hint object is stored under the wrong id")
    return packet


def put(
    root: Path,
    store: Path,
    value: Mapping[str, Any],
    *,
    depends_on: Iterable[str] = (),
) -> dict[str, Any]:
    store = store.expanduser().resolve()
    index = load_index(store)
    packet = contracts.validate_packet(root, "witsoc.memory-hint.v1", value)
    expected_id = "hint:" + digest_value({
        key: packet[key]
        for key in ("domain", "features", "content", "provenance_refs", "scope", "non_evidentiary", "created_at")
    })
    if packet["hint_id"] != expected_id:
        raise HintMemoryError("hint id does not bind its immutable content")
    dependencies = sorted(set(depends_on))
    if packet["hint_id"] in dependencies:
        raise HintMemoryError("a hint cannot depend on itself")
    missing = set(dependencies) - set(index["hints"])
    if missing:
        raise HintMemoryError(f"hint dependencies do not exist: {sorted(missing)}")
    path = _object_path(store, packet["hint_id"])
    if path.is_file() and load_json(path) != packet:
        raise HintMemoryError("hint id collision")
    if not path.is_file():
        atomic_write_json(path, packet)
    if packet["hint_id"] in index["hints"] and index["dependencies"].get(packet["hint_id"], []) != dependencies:
        raise HintMemoryError("stored hint dependencies are immutable")
    index["hints"].append(packet["hint_id"])
    index["dependencies"][packet["hint_id"]] = dependencies
    _write_index(store, index)
    return packet


def query(
    root: Path,
    store: Path,
    *,
    domain: str,
    features: Mapping[str, Any],
    scope: Mapping[str, Any] | None = None,
    min_score: float = 0.5,
    limit: int = 8,
    include_invalidated: bool = False,
) -> dict[str, Any]:
    if not 0 <= min_score <= 1 or not 1 <= limit <= 32:
        raise HintMemoryError("hint min_score or limit is outside its safe range")
    wanted = _normalize_features(domain, features)
    wanted_scope = copy.deepcopy(dict(scope or {}))
    index = load_index(store)
    matches: list[dict[str, Any]] = []
    for hint_id in index["hints"]:
        if hint_id in index["invalidations"] and not include_invalidated:
            continue
        hint = get(root, store, hint_id)
        if hint["domain"] != domain:
            continue
        if any(wanted_scope.get(key) != value for key, value in hint["scope"].items()):
            continue
        common = sorted(
            key for key, value in hint["features"].items()
            if key in wanted and wanted[key] == value
        )
        union = set(hint["features"]) | set(wanted)
        score = len(common) / len(union)
        exact = hint["structural_fingerprint"] == digest_value({"domain": domain, "features": wanted})
        if not exact and len(common) < 2:
            continue
        if score < min_score:
            continue
        matches.append({
            "score": round(score, 6),
            "exact": exact,
            "matched_features": common,
            "hint": hint,
            "invalidation_ref": index["invalidations"].get(hint_id),
        })
    matches.sort(key=lambda item: (-item["score"], item["hint"]["hint_id"]))
    return {
        "schema": "witsoc.hint-query.v1",
        "domain": domain,
        "query_fingerprint": digest_value({"domain": domain, "features": wanted}),
        "matches": matches[:limit],
        "count": min(len(matches), limit),
        "non_evidentiary": True,
    }


def invalidate(
    root: Path,
    store: Path,
    hint_id: str,
    reason: str,
    provenance_ref: str,
) -> dict[str, Any]:
    store = store.expanduser().resolve()
    get(root, store, hint_id)
    if not reason.strip() or not provenance_ref.strip():
        raise HintMemoryError("hint invalidation requires a reason and provenance reference")
    index = load_index(store)
    dependents: dict[str, set[str]] = {identifier: set() for identifier in index["hints"]}
    for child, parents in index["dependencies"].items():
        for parent in parents:
            dependents.setdefault(parent, set()).add(child)
    affected: set[str] = set()
    frontier = [hint_id]
    while frontier:
        current = frontier.pop()
        if current in affected:
            continue
        affected.add(current)
        frontier.extend(sorted(dependents.get(current, set())))
    records: list[dict[str, Any]] = []
    for identifier in sorted(affected):
        record = {
            "schema": INVALIDATION_SCHEMA,
            "hint_id": identifier,
            "root_hint_id": hint_id,
            "reason": reason if identifier == hint_id else f"dependency invalidated: {hint_id}",
            "provenance_ref": provenance_ref,
            "created_at": utc_now(),
        }
        record["record_id"] = digest_value(record)
        atomic_write_json(_invalidation_path(store, record["record_id"]), record)
        index["invalidations"][identifier] = record["record_id"]
        records.append(record)
    _write_index(store, index)
    return {
        "schema": "witsoc.hint-invalidation-report.v1",
        "root_hint_id": hint_id,
        "invalidated": [item["hint_id"] for item in records],
        "records": [item["record_id"] for item in records],
        "non_evidentiary": True,
    }
