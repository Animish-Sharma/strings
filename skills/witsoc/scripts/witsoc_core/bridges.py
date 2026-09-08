"""Capability negotiation and content-bound bridge envelopes."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from . import contracts
from .canonical import digest_value, load_json, seal_packet, verify_packet_seal
from .capabilities import all_capabilities


SCHEMA = "witsoc.bridge-envelope.v1"
SCHEMA_V2 = "witsoc.bridge-envelope.v2"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BridgeError(ValueError):
    pass


def _catalog(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for capability in all_capabilities(root):
        qualified = f"{capability['owner']}:{capability['id']}"
        result[qualified] = capability
    return result


def negotiate(root: Path, source: str, destination: str) -> dict[str, Any]:
    catalog = _catalog(root)
    if source not in catalog or destination not in catalog:
        missing = [name for name in (source, destination) if name not in catalog]
        raise BridgeError("unknown bridge capability: " + ", ".join(missing))
    sender, receiver = catalog[source], catalog[destination]
    compatible = sorted(set(sender["outputs"]) & set(receiver["inputs"]))
    return {
        "source": source,
        "destination": destination,
        "compatible_types": compatible,
        "requires": sorted(set(sender["requires"]) | set(receiver["requires"])),
        "ok": bool(compatible),
    }


def build_envelope(
    root: Path,
    envelope_id: str,
    source: str,
    destination: str,
    message_type: str,
    target_sha256: str,
    correlation_id: str,
    payload: Mapping[str, Any],
    evidence_refs: list[str] | None = None,
    causation_id: str | None = None,
) -> dict[str, Any]:
    agreement = negotiate(root, source, destination)
    if message_type not in agreement["compatible_types"]:
        raise BridgeError(
            f"{source} cannot send {message_type!r} to {destination}; compatible types are "
            f"{agreement['compatible_types']}"
        )
    packet = {
        "schema": SCHEMA,
        "envelope_id": envelope_id,
        "source": source,
        "destination": destination,
        "message_type": message_type,
        "target_sha256": target_sha256,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "content_sha256": digest_value(payload),
        "payload": copy.deepcopy(dict(payload)),
        "evidence_refs": list(evidence_refs or []),
    }
    return validate_envelope(root, seal_packet(packet))


def validate_envelope(root: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "envelope_id", "source", "destination", "message_type",
        "target_sha256", "correlation_id", "causation_id", "content_sha256",
        "payload", "evidence_refs", "payload_sha256",
    }
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise BridgeError(f"bridge envelope shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    packet = copy.deepcopy(dict(value))
    if packet["schema"] != SCHEMA or not verify_packet_seal(packet):
        raise BridgeError("bridge envelope schema or seal is invalid")
    for field in ("envelope_id", "source", "destination", "message_type", "target_sha256", "correlation_id"):
        if not isinstance(packet[field], str) or not packet[field].strip():
            raise BridgeError(f"bridge envelope {field} is empty")
    if not SHA256.fullmatch(packet["target_sha256"]):
        raise BridgeError("bridge target hash is malformed")
    if not isinstance(packet["payload"], dict):
        raise BridgeError("bridge payload must be an object")
    if not isinstance(packet["evidence_refs"], list) or any(
        not isinstance(reference, str) or not reference.strip()
        for reference in packet["evidence_refs"]
    ):
        raise BridgeError("bridge evidence_refs must be an array of non-empty strings")
    if packet["causation_id"] is not None and (
        not isinstance(packet["causation_id"], str) or not packet["causation_id"].strip()
    ):
        raise BridgeError("bridge causation_id must be null or a non-empty string")
    if packet["content_sha256"] != digest_value(packet["payload"]):
        raise BridgeError("bridge content hash does not bind the payload")
    agreement = negotiate(root, packet["source"], packet["destination"])
    if packet["message_type"] not in agreement["compatible_types"]:
        raise BridgeError("bridge contract is no longer compatible")
    return packet


def compose(root: Path, envelopes: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not envelopes:
        raise BridgeError("bridge composition is empty")
    packets = [validate_envelope(root, value) for value in envelopes]
    target = packets[0]["target_sha256"]
    correlation = packets[0]["correlation_id"]
    seen: set[str] = set()
    for index, packet in enumerate(packets):
        if packet["target_sha256"] != target or packet["correlation_id"] != correlation:
            raise BridgeError("bridge composition crosses a target or correlation boundary")
        if packet["envelope_id"] in seen:
            raise BridgeError("bridge composition contains an envelope cycle")
        seen.add(packet["envelope_id"])
        if index:
            previous = packets[index - 1]
            if packet["causation_id"] != previous["envelope_id"]:
                raise BridgeError("bridge composition has a broken causation chain")
            if packet["source"] != previous["destination"]:
                raise BridgeError("bridge composition has a disconnected capability path")
    return {
        "schema": "witsoc.bridge-composition.v1",
        "target_sha256": target,
        "correlation_id": correlation,
        "envelopes": [packet["envelope_id"] for packet in packets],
        "path": [packets[0]["source"]] + [packet["destination"] for packet in packets],
        "content_sha256": digest_value([packet["payload_sha256"] for packet in packets]),
        "ok": True,
    }


def _adapter_catalog(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "contracts" / "bridge-adapters.json"
    try:
        value = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"cannot read bridge adapter policy: {exc}") from exc
    if set(value) != {"schema", "version", "adapters"} or value["schema"] != "witsoc.bridge-adapters.v1":
        raise BridgeError("bridge adapter policy shape or schema is invalid")
    required = {
        "id", "from_type", "to_type", "required_invariants", "losses", "embedding_field",
        "transform", "verification", "loss_units",
    }
    result: dict[str, dict[str, Any]] = {}
    for item in value["adapters"]:
        if not isinstance(item, dict) or set(item) != required:
            raise BridgeError("bridge adapter record shape is invalid")
        if item["id"] in result:
            raise BridgeError(f"bridge adapter {item['id']!r} is duplicated")
        source = contracts.resolve_type(root, item["from_type"])["canonical_id"]
        destination = contracts.resolve_type(root, item["to_type"])["canonical_id"]
        if contracts.resolve_type(root, destination)["status_authority"]:
            raise BridgeError("bridge adapters may not target a status-authoritative packet")
        if (
            not item["required_invariants"]
            or not item["losses"]
            or not item["embedding_field"]
            or item["transform"] != "embed-source-v1"
            or not item["verification"]
            or not isinstance(item["loss_units"], int)
            or isinstance(item["loss_units"], bool)
            or item["loss_units"] < 1
        ):
            raise BridgeError(f"bridge adapter {item['id']!r} lacks invariants, losses, or embedding")
        result[item["id"]] = {
            **copy.deepcopy(item),
            "from_type": source,
            "to_type": destination,
            "lossless": False,
        }
    return result


def _catalog_v2(root: Path) -> dict[str, dict[str, Any]]:
    from .capability_graph import compile_graph

    return {item["id"]: item for item in compile_graph(root)["nodes"]}


def _seal_agreement(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["adapter_contract_sha256"] = digest_value(result)
    return result


def _agreements_between(
    sender: Mapping[str, Any],
    receiver: Mapping[str, Any],
    adapters: Mapping[str, Mapping[str, Any]],
    type_index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    agreements: list[dict[str, Any]] = []
    for packet in sorted(set(sender["outputs"]) & set(receiver["inputs"])):
        agreements.append(_seal_agreement({
            "adapter_id": f"identity:{packet}",
            "source_type": packet,
            "message_type": packet,
            "message_schema_id": type_index[packet]["schema_id"],
            "required_invariants": ["payload_sha256", "target_sha256"],
            "losses": [],
            "embedding_field": "",
            "lossless": True,
            "transform": "identity-v1",
            "verification": ["validate both packet types", "require byte-identical content"],
            "loss_units": 0,
        }))
    for adapter in adapters.values():
        if adapter["from_type"] in sender["outputs"] and adapter["to_type"] in receiver["inputs"]:
            agreements.append(_seal_agreement({
                "adapter_id": adapter["id"],
                "source_type": adapter["from_type"],
                "message_type": adapter["to_type"],
                "message_schema_id": type_index[adapter["to_type"]]["schema_id"],
                "required_invariants": list(adapter["required_invariants"]),
                "losses": list(adapter["losses"]),
                "embedding_field": adapter["embedding_field"],
                "lossless": False,
                "transform": adapter["transform"],
                "verification": list(adapter["verification"]),
                "loss_units": adapter["loss_units"],
            }))
    return sorted(
        agreements,
        key=lambda item: (
            item["loss_units"], item["source_type"], item["message_type"], item["adapter_id"]
        ),
    )


def negotiate_v2(root: Path, source: str, destination: str) -> dict[str, Any]:
    catalog = _catalog_v2(root)
    if source not in catalog or destination not in catalog:
        missing = [name for name in (source, destination) if name not in catalog]
        raise BridgeError("unknown bridge capability: " + ", ".join(missing))
    type_index = contracts.type_index(root)
    sender, receiver = catalog[source], catalog[destination]
    agreements = _agreements_between(sender, receiver, _adapter_catalog(root), type_index)
    return {
        "schema": "witsoc.bridge-negotiation.v2",
        "source": source,
        "destination": destination,
        "agreements": agreements,
        "lossless_available": any(item["lossless"] for item in agreements),
        "ok": bool(agreements),
    }


def _agreement(root: Path, source: str, destination: str, adapter_id: str) -> dict[str, Any]:
    agreements = negotiate_v2(root, source, destination)["agreements"]
    matches = [item for item in agreements if item["adapter_id"] == adapter_id]
    if len(matches) != 1:
        raise BridgeError(f"bridge adapter {adapter_id!r} is not negotiated for {source} -> {destination}")
    return matches[0]


def translate_v2(
    root: Path,
    source: str,
    destination: str,
    adapter_id: str,
    source_packet: Mapping[str, Any],
    *,
    transfer_id: str,
    scope: Mapping[str, Any],
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    agreement = _agreement(root, source, destination, adapter_id)
    source_value = contracts.validate_packet(root, agreement["source_type"], source_packet)
    if agreement["lossless"]:
        return copy.deepcopy(source_value)
    if agreement["transform"] != "embed-source-v1":
        raise BridgeError(f"unsupported executable bridge transform {agreement['transform']!r}")
    target_sha256 = source_value.get("target_sha256")
    if not isinstance(target_sha256, str) or not SHA256.fullmatch(target_sha256):
        raise BridgeError("source packet does not carry a valid frozen target")
    if not isinstance(scope, Mapping) or not scope:
        raise BridgeError("loss-aware translation requires a non-empty destination scope")
    source_owner = source.split(":", 1)[0]
    destination_owner = destination.split(":", 1)[0]
    translated = seal_packet({
        "schema": "witsoc.transfer.v2",
        "transfer_id": transfer_id,
        "target_sha256": target_sha256,
        "source_domain": source_owner,
        "destination_domain": destination_owner,
        "source_type": agreement["source_type"],
        "destination_type": agreement["message_type"],
        "preserved_invariants": list(agreement["required_invariants"]),
        "losses": list(agreement["losses"]),
        "scope": copy.deepcopy(dict(scope)),
        "evidence_refs": sorted(set(evidence_refs or [])),
        agreement["embedding_field"]: source_value,
    })
    try:
        return contracts.validate_packet(root, agreement["message_type"], translated)
    except contracts.ContractError as exc:
        raise BridgeError(str(exc)) from exc


def build_envelope_v2(
    root: Path,
    envelope_id: str,
    source: str,
    destination: str,
    adapter_id: str,
    source_message_type: str,
    message_type: str,
    target_sha256: str,
    correlation_id: str,
    source_packet: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    scope_owner: str,
    preserved_invariants: list[str] | None = None,
    losses: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    conflict_refs: list[str] | None = None,
    causation_id: str | None = None,
) -> dict[str, Any]:
    agreement = _agreement(root, source, destination, adapter_id)
    source_type = contracts.resolve_type(root, source_message_type)["canonical_id"]
    destination_type = contracts.resolve_type(root, message_type)["canonical_id"]
    if (source_type, destination_type) != (agreement["source_type"], agreement["message_type"]):
        raise BridgeError("bridge message types do not match the negotiated adapter")
    source_value = contracts.validate_packet(root, source_type, source_packet)
    translated = contracts.validate_packet(root, destination_type, payload)
    for label, value in (("source", source_value), ("translated", translated)):
        if value.get("target_sha256") != target_sha256:
            raise BridgeError(f"{label} bridge packet differs from the frozen target")
    if agreement["lossless"] and source_value != translated:
        raise BridgeError("identity bridge requires byte-identical source and destination packets")
    if agreement["embedding_field"] and translated.get(agreement["embedding_field"]) != source_value:
        raise BridgeError("loss-aware bridge payload does not embed the exact source packet")
    if scope_owner not in {source, destination, "frame:coordinator"}:
        raise BridgeError("bridge scope owner must be one endpoint or frame:coordinator")
    invariants = sorted(set(agreement["required_invariants"]) | set(preserved_invariants or []))
    declared_losses = sorted(set(agreement["losses"]) | set(losses or []))
    packet = seal_packet({
        "schema": SCHEMA_V2,
        "envelope_id": envelope_id,
        "source": source,
        "destination": destination,
        "source_message_type": source_type,
        "source_content_sha256": source_value["payload_sha256"],
        "message_type": destination_type,
        "message_schema_id": agreement["message_schema_id"],
        "adapter_id": adapter_id,
        "adapter_contract_sha256": agreement["adapter_contract_sha256"],
        "target_sha256": target_sha256,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "scope_owner": scope_owner,
        "preserved_invariants": invariants,
        "losses": declared_losses,
        "conflict_refs": sorted(set(conflict_refs or [])),
        "content_sha256": digest_value(translated),
        "payload": translated,
        "evidence_refs": sorted(set(evidence_refs or [])),
    })
    return validate_envelope_v2(root, packet)


def validate_envelope_v2(root: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        packet = contracts.validate_packet(root, "witsoc.bridge-envelope.v2", value)
    except contracts.ContractError as exc:
        raise BridgeError(str(exc)) from exc
    agreement = _agreement(root, packet["source"], packet["destination"], packet["adapter_id"])
    if (
        packet["source_message_type"] != agreement["source_type"]
        or packet["message_type"] != agreement["message_type"]
        or packet["message_schema_id"] != agreement["message_schema_id"]
        or packet["adapter_contract_sha256"] != agreement["adapter_contract_sha256"]
    ):
        raise BridgeError("bridge v2 packet types or adapter contract differ from current negotiation")
    translated = contracts.validate_packet(root, packet["message_type"], packet["payload"])
    if translated.get("target_sha256") != packet["target_sha256"]:
        raise BridgeError("bridge v2 payload differs from the frozen target")
    if packet["content_sha256"] != digest_value(translated):
        raise BridgeError("bridge v2 content hash does not bind the translated packet")
    if not set(agreement["required_invariants"]).issubset(packet["preserved_invariants"]):
        raise BridgeError("bridge v2 omits a required preserved invariant")
    if not set(agreement["losses"]).issubset(packet["losses"]):
        raise BridgeError("bridge v2 hides a declared adapter loss")
    if agreement["lossless"]:
        if packet["source_content_sha256"] != translated["payload_sha256"] or packet["losses"]:
            raise BridgeError("identity bridge changed content or declared a loss")
    else:
        embedded = translated.get(agreement["embedding_field"])
        if not isinstance(embedded, dict):
            raise BridgeError("loss-aware bridge lacks its embedded source packet")
        source = contracts.validate_packet(root, packet["source_message_type"], embedded)
        if source["payload_sha256"] != packet["source_content_sha256"]:
            raise BridgeError("embedded source packet differs from the bound source content")
    if packet["scope_owner"] not in {packet["source"], packet["destination"], "frame:coordinator"}:
        raise BridgeError("bridge v2 scope owner is outside the capability path")
    return packet


def compose_v2(root: Path, envelopes: list[Mapping[str, Any]], *, max_losses: int = 4) -> dict[str, Any]:
    if not envelopes:
        raise BridgeError("bridge v2 composition is empty")
    if max_losses < 0:
        raise BridgeError("bridge loss budget cannot be negative")
    packets = [validate_envelope_v2(root, value) for value in envelopes]
    target = packets[0]["target_sha256"]
    correlation = packets[0]["correlation_id"]
    seen: set[str] = set()
    for index, packet in enumerate(packets):
        if packet["target_sha256"] != target or packet["correlation_id"] != correlation:
            raise BridgeError("bridge v2 composition crosses a target or correlation boundary")
        if packet["envelope_id"] in seen:
            raise BridgeError("bridge v2 composition contains an envelope cycle")
        seen.add(packet["envelope_id"])
        if index:
            previous = packets[index - 1]
            if packet["causation_id"] != previous["envelope_id"]:
                raise BridgeError("bridge v2 composition has a broken causation chain")
            if packet["source"] != previous["destination"]:
                raise BridgeError("bridge v2 composition has a disconnected capability path")
            if packet["source_message_type"] != previous["message_type"]:
                raise BridgeError("bridge v2 composition breaks packet type continuity")
            if packet["source_content_sha256"] != previous["payload"]["payload_sha256"]:
                raise BridgeError("bridge v2 composition breaks content continuity")
            if packet["scope_owner"] not in {previous["destination"], "frame:coordinator"}:
                raise BridgeError("bridge v2 composition changes scope without ownership")
    losses = sorted({item for packet in packets for item in packet["losses"]})
    loss_units = sum(
        _agreement(root, packet["source"], packet["destination"], packet["adapter_id"])["loss_units"]
        for packet in packets
    )
    if loss_units > max_losses:
        raise BridgeError(f"bridge v2 composition exceeds its loss budget: {loss_units} > {max_losses}")
    invariants = set(packets[0]["preserved_invariants"])
    for packet in packets[1:]:
        invariants &= set(packet["preserved_invariants"])
    if "target_sha256" not in invariants:
        raise BridgeError("bridge v2 composition does not preserve the frozen target invariant")
    conflicts = sorted({item for packet in packets for item in packet["conflict_refs"]})
    return {
        "schema": "witsoc.bridge-composition.v2",
        "target_sha256": target,
        "correlation_id": correlation,
        "envelopes": [packet["envelope_id"] for packet in packets],
        "path": [packets[0]["source"]] + [packet["destination"] for packet in packets],
        "preserved_invariants": sorted(invariants),
        "losses": losses,
        "loss_units": loss_units,
        "conflict_refs": conflicts,
        "requires_adjudication": bool(conflicts),
        "content_sha256": digest_value([packet["payload_sha256"] for packet in packets]),
        "ok": not conflicts,
    }


def plan_v2(
    root: Path,
    source: str,
    destination: str,
    *,
    max_hops: int = 4,
    max_loss_units: int = 4,
    limit: int = 8,
) -> dict[str, Any]:
    if not 1 <= max_hops <= 8 or not 1 <= limit <= 32 or max_loss_units < 0:
        raise BridgeError("bridge planning bounds are invalid")
    catalog = _catalog_v2(root)
    if source not in catalog or destination not in catalog or source == destination:
        raise BridgeError("bridge plan requires two distinct known capabilities")
    adapters = _adapter_catalog(root)
    type_index = contracts.type_index(root)
    queue: list[dict[str, Any]] = [
        {
            "capability": source,
            "message_type": packet,
            "capabilities": [source],
            "hops": [],
            "loss_units": 0,
            "context_tokens": catalog[source]["context_tokens"],
        }
        for packet in catalog[source]["outputs"]
    ]
    paths: list[dict[str, Any]] = []
    best: dict[tuple[str, str], tuple[int, int]] = {}
    while queue and len(paths) < limit * 4:
        queue.sort(
            key=lambda item: (
                item["loss_units"], len(item["hops"]), item["context_tokens"],
                item["capabilities"], item["message_type"],
            )
        )
        current = queue.pop(0)
        if len(current["hops"]) >= max_hops:
            continue
        sender = catalog[current["capability"]]
        if current["message_type"] not in sender["outputs"]:
            continue
        for next_id, receiver in sorted(catalog.items()):
            if next_id in current["capabilities"]:
                continue
            agreements = _agreements_between(sender, receiver, adapters, type_index)
            for agreement in agreements:
                if agreement["source_type"] != current["message_type"]:
                    continue
                loss_units = current["loss_units"] + agreement["loss_units"]
                if loss_units > max_loss_units:
                    continue
                hop = {
                    "source": current["capability"],
                    "destination": next_id,
                    **agreement,
                }
                candidate = {
                    "capability": next_id,
                    "message_type": agreement["message_type"],
                    "capabilities": [*current["capabilities"], next_id],
                    "hops": [*current["hops"], hop],
                    "loss_units": loss_units,
                    "context_tokens": current["context_tokens"] + receiver["context_tokens"],
                }
                if next_id == destination:
                    paths.append(candidate)
                    continue
                if agreement["message_type"] not in receiver["outputs"]:
                    continue
                state_key = (next_id, agreement["message_type"])
                cost = (loss_units, len(candidate["hops"]))
                if state_key in best and best[state_key] <= cost:
                    continue
                best[state_key] = cost
                queue.append(candidate)
    unique: list[dict[str, Any]] = []
    signatures: set[str] = set()
    for item in sorted(
        paths,
        key=lambda value: (
            value["loss_units"], len(value["hops"]), value["context_tokens"],
            value["capabilities"],
        ),
    ):
        signature = digest_value([
            (hop["source"], hop["destination"], hop["adapter_id"])
            for hop in item["hops"]
        ])
        if signature in signatures:
            continue
        signatures.add(signature)
        unique.append({
            "capabilities": item["capabilities"],
            "hops": item["hops"],
            "loss_units": item["loss_units"],
            "context_tokens": item["context_tokens"],
        })
        if len(unique) == limit:
            break
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": f"bridge-plan:{source}:{destination}",
        "kind": "BRIDGE_PLAN",
        "target_sha256": None,
        "source_refs": [digest_value({"catalog": catalog, "adapters": adapters})],
        "body": {
            "source": source,
            "destination": destination,
            "max_hops": max_hops,
            "max_loss_units": max_loss_units,
            "paths": unique,
            "recommended": unique[0] if unique else None,
            "hidden_capability_transforms": "FORBIDDEN",
        },
        "disposition": "READY" if unique else "BLOCKED",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise BridgeError(str(exc)) from exc


def compose_graph_v2(
    root: Path,
    envelopes: list[Mapping[str, Any]],
    *,
    max_loss_units: int = 8,
    report_id: str = "bridge-graph",
) -> dict[str, Any]:
    if not envelopes or max_loss_units < 0:
        raise BridgeError("bridge graph is empty or has an invalid loss budget")
    packets = [validate_envelope_v2(root, value) for value in envelopes]
    by_id = {packet["envelope_id"]: packet for packet in packets}
    if len(by_id) != len(packets):
        raise BridgeError("bridge graph contains duplicate envelope ids")
    target = packets[0]["target_sha256"]
    correlation = packets[0]["correlation_id"]
    if any(
        packet["target_sha256"] != target or packet["correlation_id"] != correlation
        for packet in packets
    ):
        raise BridgeError("bridge graph crosses a target or correlation boundary")
    children: dict[str, list[str]] = {identifier: [] for identifier in by_id}
    roots: list[str] = []
    for packet in packets:
        parent_id = packet["causation_id"]
        if parent_id is None:
            roots.append(packet["envelope_id"])
            continue
        if parent_id not in by_id:
            raise BridgeError(f"bridge graph has missing cause {parent_id!r}")
        parent = by_id[parent_id]
        if packet["source"] != parent["destination"]:
            raise BridgeError("bridge graph contains a disconnected capability edge")
        if (
            packet["source_message_type"] != parent["message_type"]
            or packet["source_content_sha256"] != parent["payload"]["payload_sha256"]
        ):
            raise BridgeError("bridge graph breaks type or content continuity")
        children[parent_id].append(packet["envelope_id"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise BridgeError("bridge graph contains a causation cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for child in children[identifier]:
            visit(child)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in sorted(by_id):
        visit(identifier)
    branches = [
        {"envelope_id": identifier, "children": sorted(ids)}
        for identifier, ids in sorted(children.items()) if len(ids) > 1
    ]
    arrivals: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for packet in packets:
        arrivals.setdefault((packet["destination"], packet["message_type"]), []).append(packet)
    joins: list[dict[str, Any]] = []
    for (destination, message_type), incoming in sorted(arrivals.items()):
        if len(incoming) < 2:
            continue
        content = sorted({item["content_sha256"] for item in incoming})
        joins.append({
            "destination": destination,
            "message_type": message_type,
            "envelopes": sorted(item["envelope_id"] for item in incoming),
            "content_sha256": content,
            "mergeable": len(content) == 1,
            "requirement": (
                "IDENTICAL_CONTENT" if len(content) == 1
                else "TYPED_ADAPTER_AND_EXPLORER_ADJUDICATION"
            ),
        })
    conflicts = sorted({item for packet in packets for item in packet["conflict_refs"]})
    loss_units = sum(
        _agreement(root, packet["source"], packet["destination"], packet["adapter_id"])["loss_units"]
        for packet in packets
    )
    blocking_joins = [item for item in joins if not item["mergeable"]]
    blocked = bool(conflicts or blocking_joins or loss_units > max_loss_units)
    packet = seal_packet({
        "schema": "witsoc.control-report.v1",
        "report_id": report_id,
        "kind": "BRIDGE_GRAPH",
        "target_sha256": target,
        "source_refs": sorted(item["payload_sha256"] for item in packets),
        "body": {
            "correlation_id": correlation,
            "roots": sorted(roots),
            "leaves": sorted(identifier for identifier, ids in children.items() if not ids),
            "branches": branches,
            "join_requirements": joins,
            "envelopes": sorted(by_id),
            "loss_units": loss_units,
            "max_loss_units": max_loss_units,
            "conflict_refs": conflicts,
            "status_inference": "NONE",
        },
        "disposition": "BLOCKED" if blocked else "READY",
        "status_authority": False,
    })
    try:
        return contracts.validate_packet(root, "witsoc.control-report.v1", packet)
    except contracts.ContractError as exc:
        raise BridgeError(str(exc)) from exc
