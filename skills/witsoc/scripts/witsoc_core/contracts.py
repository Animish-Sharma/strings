"""Versioned packet registry and schema validation for research IR."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

try:
    import jsonschema_lite
except ModuleNotFoundError:  # Imported as scripts.witsoc_core from the source tree.
    from scripts import jsonschema_lite

from .canonical import load_json, verify_packet_seal


REGISTRY_SCHEMA = "witsoc.type-registry.v1"


class ContractError(ValueError):
    pass


def _inside(root: Path, candidate: Path) -> Path:
    root = root.expanduser().resolve()
    candidate = candidate.expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"contract path escapes the skill root: {candidate}") from exc
    return candidate


def _validate_json(value: Any, schema: dict[str, Any], label: str) -> None:
    errors: list[str] = []
    jsonschema_lite.validate(value, schema, label, errors)
    if errors:
        raise ContractError("; ".join(errors[:8]))


def load_registry(root: Path) -> dict[str, Any]:
    path = root / "contracts" / "type-registry.json"
    schema_path = root / "schemas" / "research-type-registry-v1.schema.json"
    try:
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read the type registry: {exc}") from exc
    documents = [path, *sorted((root / "domains").glob("*/packet-types.json"))]
    records: list[dict[str, Any]] = []
    version: int | None = None
    for document in documents:
        try:
            value = load_json(document)
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"cannot read the type registry {document}: {exc}") from exc
        _validate_json(value, schema, f"type registry {document.relative_to(root)}")
        if version is None:
            version = value["version"]
        elif value["version"] != version:
            raise ContractError("type registry fragments use different versions")
        if document != path:
            owner = document.parent.name
            for record in value["types"]:
                if record["owner"] != owner:
                    raise ContractError(
                        f"domain type {record['id']!r} is owned by {record['owner']!r}, expected {owner!r}"
                    )
                expected = (Path("domains") / owner / "schemas").as_posix() + "/"
                if not record["schema_path"].startswith(expected):
                    raise ContractError(
                        f"domain type {record['id']!r} schema is outside its owning pack"
                    )
        elif any(not record["schema_path"].startswith("schemas/") for record in value["types"]):
            raise ContractError("the shared type registry may not own domain schema paths")
        records.extend(value["types"])
    identifiers: set[str] = set()
    aliases: set[str] = set()
    authorities: list[str] = []
    for record in records:
        identifier = record["id"]
        if identifier in identifiers or identifier in aliases:
            raise ContractError(f"packet type {identifier!r} is duplicated or shadows an alias")
        identifiers.add(identifier)
        if record["status_authority"]:
            authorities.append(identifier)
        packet_schema_path = _inside(root, root / record["schema_path"])
        if not packet_schema_path.is_file():
            raise ContractError(f"packet type {identifier!r} has no schema at {record['schema_path']}")
        packet_schema = load_json(packet_schema_path)
        if packet_schema.get("$id") != record["schema_id"]:
            raise ContractError(
                f"packet type {identifier!r} expects schema id {record['schema_id']!r}, "
                f"found {packet_schema.get('$id')!r}"
            )
        for alias in record["compatible_from"]:
            if alias in aliases or alias in identifiers:
                raise ContractError(f"packet compatibility alias {alias!r} is ambiguous")
            aliases.add(alias)
    if authorities != ["witsoc.admission.v2"]:
        raise ContractError(
            "the type registry must have exactly one status-authoritative type: witsoc.admission.v2"
        )
    return {"schema": REGISTRY_SCHEMA, "version": version, "types": copy.deepcopy(records)}


def type_index(root: Path) -> dict[str, dict[str, Any]]:
    records = load_registry(root)["types"]
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        canonical = copy.deepcopy(record)
        canonical["canonical_id"] = record["id"]
        result[record["id"]] = canonical
        for alias in record["compatible_from"]:
            aliased = copy.deepcopy(canonical)
            aliased["requested_id"] = alias
            result[alias] = aliased
    return result


def resolve_type(root: Path, type_id: str) -> dict[str, Any]:
    record = type_index(root).get(type_id)
    if record is None:
        raise ContractError(f"unknown packet type {type_id!r}")
    return record


def compatible(root: Path, produced: str, consumed: str) -> bool:
    try:
        left = resolve_type(root, produced)["canonical_id"]
        right = resolve_type(root, consumed)["canonical_id"]
    except ContractError:
        return False
    return left == right


def validate_packet(
    root: Path,
    type_id: str,
    value: Mapping[str, Any],
    *,
    require_seal: bool = True,
) -> dict[str, Any]:
    record = resolve_type(root, type_id)
    schema = load_json(root / record["schema_path"])
    packet = copy.deepcopy(dict(value))
    _validate_json(packet, schema, type_id)
    if packet.get("schema") != record["schema_id"]:
        raise ContractError(
            f"packet declares {packet.get('schema')!r}, expected {record['schema_id']!r}"
        )

    def reject_hint_evidence(value: Any, key: str = "") -> None:
        if key.endswith("_ref") or key.endswith("_refs"):
            references = value if isinstance(value, list) else [value]
            if any(isinstance(item, str) and item.startswith("hint:") for item in references):
                raise ContractError("non-evidentiary hint references cannot enter evidence fields")
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                reject_hint_evidence(nested_value, nested_key)
        elif isinstance(value, list):
            for nested_value in value:
                reject_hint_evidence(nested_value, key)

    reject_hint_evidence(packet)
    if require_seal and "payload_sha256" in schema.get("properties", {}):
        if not verify_packet_seal(packet):
            raise ContractError(f"{type_id} packet seal is broken")
    return packet


def registry_report(root: Path) -> dict[str, Any]:
    registry = load_registry(root)
    records = registry["types"]
    return {
        "schema": "witsoc.type-registry-report.v1",
        "ok": True,
        "version": registry["version"],
        "type_count": len(records),
        "aliases": sum(len(item["compatible_from"]) for item in records),
        "status_authority": next(item["id"] for item in records if item["status_authority"]),
        "owners": sorted({item["owner"] for item in records}),
    }
