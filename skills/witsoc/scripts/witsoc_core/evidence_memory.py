"""Content-addressed memory with explicit reuse and invalidation rules."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from .canonical import atomic_write_json, canonical_json, digest_value, load_json, utc_now


ENTRY_SCHEMA = "witsoc.memory-entry.v1"
INDEX_SCHEMA = "witsoc.memory-index.v1"
KINDS = {"FAILURE", "ADMITTED_PRODUCT", "OBSTRUCTION", "SOURCE", "ROUTE", "INVALIDATION"}
REUSABLE_KINDS = {"ADMITTED_PRODUCT", "OBSTRUCTION", "SOURCE", "ROUTE"}
CONTAMINATION_MARKERS = ("held-out answer", "held_out_answer", "answer key", "evaluation key")


class MemoryError(ValueError):
    pass


def _index_path(store: Path) -> Path:
    return store / "index.json"


def _object_path(store: Path, entry_id: str) -> Path:
    return store / "objects" / entry_id[:2] / f"{entry_id}.json"


def init_store(store: Path) -> dict[str, Any]:
    store = store.expanduser().resolve()
    store.mkdir(parents=True, exist_ok=True)
    index = {
        "schema": INDEX_SCHEMA,
        "entries": [],
        "catalog": {},
        "invalidations": {},
        "index_sha256": "",
    }
    index["index_sha256"] = digest_value({key: value for key, value in index.items() if key != "index_sha256"})
    atomic_write_json(_index_path(store), index)
    return index


def load_index(store: Path) -> dict[str, Any]:
    path = _index_path(store.expanduser().resolve())
    if not path.is_file():
        return init_store(store)
    index = load_json(path)
    expected = digest_value({key: value for key, value in index.items() if key != "index_sha256"})
    if index.get("schema") != INDEX_SCHEMA or index.get("index_sha256") != expected:
        raise MemoryError("memory index schema or content hash is invalid")
    # Old indexes remain readable; the next write fills the metadata catalog.
    index.setdefault("catalog", {})
    if not isinstance(index["entries"], list) or not isinstance(index["catalog"], dict):
        raise MemoryError("memory index entries or catalog is malformed")
    return index


def _write_index(store: Path, index: dict[str, Any]) -> None:
    index["entries"] = sorted(set(index["entries"]))
    index.setdefault("catalog", {})
    for entry_id in index["entries"]:
        if entry_id in index["catalog"]:
            continue
        path = _object_path(store, entry_id)
        if path.is_file():
            index["catalog"][entry_id] = _catalog_record(prepare_entry(load_json(path)))
    index["index_sha256"] = digest_value({key: value for key, value in index.items() if key != "index_sha256"})
    atomic_write_json(_index_path(store), index)


def _catalog_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": entry["kind"],
        "target_sha256": entry["target_sha256"],
        "domain": entry["domain"],
        "scope_sha256": digest_value(entry["scope"]),
        "tags": sorted(set(entry["tags"])),
        "reusable": entry["kind"] in REUSABLE_KINDS,
        "has_admission": bool(entry["admission_ref"]),
    }


def prepare_entry(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "kind", "target_sha256", "domain", "scope", "status",
        "admission_ref", "evidence_refs", "content", "tags", "created_at",
        "invalidated_by", "entry_id",
    }
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise MemoryError(f"memory entry shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    entry = copy.deepcopy(dict(value))
    if entry["schema"] != ENTRY_SCHEMA or entry["kind"] not in KINDS:
        raise MemoryError("memory entry schema or kind is invalid")
    if (
        not isinstance(entry["target_sha256"], str)
        or len(entry["target_sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in entry["target_sha256"])
    ):
        raise MemoryError("memory entry target hash is malformed")
    for field in ("domain", "status", "created_at"):
        if not isinstance(entry[field], str) or not entry[field].strip():
            raise MemoryError(f"memory entry {field} is empty")
    if not isinstance(entry["scope"], dict) or not isinstance(entry["content"], dict):
        raise MemoryError("memory scope and content must be objects")
    if not isinstance(entry["evidence_refs"], list) or not isinstance(entry["tags"], list):
        raise MemoryError("memory evidence_refs and tags must be arrays")
    if any(not isinstance(item, str) or not item.strip() for item in entry["evidence_refs"] + entry["tags"]):
        raise MemoryError("memory evidence_refs and tags must contain non-empty strings")
    blob = str(entry["content"]).casefold()
    marker = next((item for item in CONTAMINATION_MARKERS if item in blob), None)
    if marker:
        raise MemoryError(f"memory content contains forbidden evaluation material marker {marker!r}")
    if entry["kind"] in REUSABLE_KINDS and not entry["evidence_refs"]:
        raise MemoryError("reusable memory requires provenance evidence")
    if entry["kind"] == "ADMITTED_PRODUCT" and not entry["admission_ref"]:
        raise MemoryError("an admitted product requires admission and evidence references")
    if entry["kind"] != "INVALIDATION" and entry["invalidated_by"] is not None:
        raise MemoryError("new memory entries cannot begin invalidated")
    expected = digest_value({key: item for key, item in entry.items() if key != "entry_id"})
    if entry["entry_id"] not in ("", expected):
        raise MemoryError("memory entry id does not match its content")
    entry["entry_id"] = expected
    return entry


def make_entry(
    *,
    kind: str,
    target_sha256: str,
    domain: str,
    scope: Mapping[str, Any],
    status: str,
    content: Mapping[str, Any],
    tags: list[str] | None = None,
    admission_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return prepare_entry({
        "schema": ENTRY_SCHEMA,
        "kind": kind,
        "target_sha256": target_sha256,
        "domain": domain,
        "scope": copy.deepcopy(dict(scope)),
        "status": status,
        "admission_ref": admission_ref,
        "evidence_refs": list(evidence_refs or []),
        "content": copy.deepcopy(dict(content)),
        "tags": sorted(set(tags or [])),
        "created_at": created_at or utc_now(),
        "invalidated_by": None,
        "entry_id": "",
    })


def put(store: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    store = store.expanduser().resolve()
    index = load_index(store)
    entry = prepare_entry(value)
    path = _object_path(store, entry["entry_id"])
    if path.is_file():
        if load_json(path) != entry:
            raise MemoryError("content address collision")
        if entry["entry_id"] not in index["catalog"]:
            index["catalog"][entry["entry_id"]] = _catalog_record(entry)
            _write_index(store, index)
        return entry
    atomic_write_json(path, entry)
    index["entries"].append(entry["entry_id"])
    index["catalog"][entry["entry_id"]] = _catalog_record(entry)
    _write_index(store, index)
    return entry


def get(store: Path, entry_id: str) -> dict[str, Any]:
    path = _object_path(store.expanduser().resolve(), entry_id)
    if not path.is_file():
        raise MemoryError(f"memory entry {entry_id!r} does not exist")
    entry = prepare_entry(load_json(path))
    if entry["entry_id"] != entry_id:
        raise MemoryError("memory object is stored under the wrong content address")
    return entry


def invalidate(store: Path, entry_id: str, reason: str, evidence_ref: str) -> dict[str, Any]:
    target = get(store, entry_id)
    if not reason.strip() or not evidence_ref.strip():
        raise MemoryError("invalidation requires a reason and evidence reference")
    tombstone = make_entry(
        kind="INVALIDATION",
        target_sha256=target["target_sha256"],
        domain=target["domain"],
        scope=target["scope"],
        status="RECORDED",
        content={"invalidates": entry_id, "reason": reason},
        evidence_refs=[evidence_ref],
        tags=["invalidation"],
    )
    put(store, tombstone)
    index = load_index(store)
    index["invalidations"][entry_id] = tombstone["entry_id"]
    _write_index(store, index)
    return tombstone


def query(
    store: Path,
    *,
    target_sha256: str | None = None,
    domain: str | None = None,
    scope: Mapping[str, Any] | None = None,
    tags: list[str] | None = None,
    reusable_only: bool = True,
    include_invalidated: bool = False,
) -> list[dict[str, Any]]:
    if reusable_only and (target_sha256 is None or domain is None or scope is None):
        raise MemoryError("reusable retrieval requires exact target, domain, and scope")
    index = load_index(store)
    wanted_tags = set(tags or [])
    wanted_scope = copy.deepcopy(dict(scope)) if scope is not None else None
    wanted_scope_sha256 = digest_value(wanted_scope) if wanted_scope is not None else None
    result: list[dict[str, Any]] = []
    for entry_id in index["entries"]:
        if not include_invalidated and entry_id in index["invalidations"]:
            continue
        metadata = index["catalog"].get(entry_id)
        if metadata is not None:
            if reusable_only and not metadata["reusable"]:
                continue
            if target_sha256 and metadata["target_sha256"] != target_sha256:
                continue
            if domain and metadata["domain"] != domain:
                continue
            if wanted_scope_sha256 is not None and metadata["scope_sha256"] != wanted_scope_sha256:
                continue
            if wanted_tags and not wanted_tags.issubset(set(metadata["tags"])):
                continue
        entry = get(store, entry_id)
        if entry["kind"] == "INVALIDATION":
            continue
        if reusable_only and entry["kind"] not in REUSABLE_KINDS:
            continue
        if reusable_only and entry["kind"] == "ADMITTED_PRODUCT" and not entry["admission_ref"]:
            continue
        if target_sha256 and entry["target_sha256"] != target_sha256:
            continue
        if domain and entry["domain"] != domain:
            continue
        if wanted_scope is not None and entry["scope"] != wanted_scope:
            continue
        if wanted_tags and not wanted_tags.issubset(set(entry["tags"])):
            continue
        result.append(entry)
    return sorted(result, key=lambda item: (item["kind"], item["entry_id"]))


def compact_query(
    store: Path,
    *,
    target_sha256: str,
    domain: str,
    scope: Mapping[str, Any],
    tags: list[str] | None = None,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    if not 1024 <= max_bytes <= 65536:
        raise MemoryError("compact memory budget must be between 1024 and 65536 bytes")
    entries = query(
        store,
        target_sha256=target_sha256,
        domain=domain,
        scope=scope,
        tags=tags,
        reusable_only=True,
    )
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        content = entry["content"]
        mechanism = (
            content.get("mechanism_fingerprint")
            or content.get("route_fingerprint")
            or content.get("mechanism")
            or content.get("statement")
            or content.get("summary")
            or entry["entry_id"]
        )
        fingerprint = digest_value({
            "kind": entry["kind"],
            "domain": entry["domain"],
            "scope": entry["scope"],
            "mechanism": mechanism,
            "tags": entry["tags"],
        })
        groups.setdefault(fingerprint, []).append(entry)
    records: list[dict[str, Any]] = []
    omitted = 0
    for fingerprint, members in sorted(groups.items()):
        representative = members[0]
        content = representative["content"]
        summary = str(
            content.get("summary")
            or content.get("statement")
            or content.get("reason")
            or representative["status"]
        )
        record = {
            "structural_fingerprint": fingerprint,
            "representative_entry_id": representative["entry_id"],
            "equivalent_entry_ids": [item["entry_id"] for item in members],
            "kind": representative["kind"],
            "status": representative["status"],
            "summary": summary[:512],
            "tags": representative["tags"],
            "admission_ref": representative["admission_ref"],
            "evidence_refs": representative["evidence_refs"],
        }
        candidate = {
            "schema": "witsoc.memory-context-pack.v1",
            "target_sha256": target_sha256,
            "domain": domain,
            "scope_sha256": digest_value(scope),
            "records": [*records, record],
            "omitted_groups": 0,
            "source_entry_count": len(entries),
            "non_authoritative_read_model": True,
        }
        if len(canonical_json(candidate).encode("utf-8")) > max_bytes - 192:
            omitted += 1
            continue
        records.append(record)
    packet = {
        "schema": "witsoc.memory-context-pack.v1",
        "target_sha256": target_sha256,
        "domain": domain,
        "scope_sha256": digest_value(scope),
        "records": records,
        "omitted_groups": omitted,
        "source_entry_count": len(entries),
        "non_authoritative_read_model": True,
    }
    packet["context_sha256"] = digest_value(packet)
    packet["encoded_bytes"] = 0
    while True:
        encoded_bytes = len(canonical_json(packet).encode("utf-8"))
        if encoded_bytes == packet["encoded_bytes"]:
            break
        packet["encoded_bytes"] = encoded_bytes
    if packet["encoded_bytes"] > max_bytes:
        raise MemoryError("compact memory metadata alone exceeds the requested budget")
    return packet
