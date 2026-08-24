#!/usr/bin/env python3
"""A deliberately small JSON Schema subset — the keywords this frame's contracts
actually use.

Extracted so the pack validator and the reducer share one implementation. Two
copies of a validator drift, and the second one to drift is the one nobody
notices, because it keeps passing.

Unknown keywords are IGNORED rather than guessed at: silently approximating a
keyword is how a schema comes to mean something different from what it says. If
a contract grows a keyword, teach it here explicitly.
"""

from __future__ import annotations

import re
from typing import Any

TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate(node: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    """Append a message to `errors` for each way `node` violates `schema`."""

    if "const" in schema and node != schema["const"]:
        errors.append(f"{path}: must be {schema['const']!r}, got {node!r}")
        return

    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}, got {node!r}")
        return

    expected = schema.get("type")
    if expected:
        # `type` may be a list — `["string", "null"]` is used by the frame's own
        # state schema for a nullable hash. The first version indexed TYPE_MAP
        # with it directly and crashed, which nothing noticed because nothing had
        # ever validated a state: a validator that cannot read its own schemas is
        # a validator nobody has pointed at them.
        options = expected if isinstance(expected, list) else [expected]
        allowed = tuple(TYPE_MAP[o] if not isinstance(TYPE_MAP.get(o), tuple) else TYPE_MAP[o]
                        for o in options if o in TYPE_MAP)
        flat: list[type] = []
        for entry in allowed:
            flat.extend(entry if isinstance(entry, tuple) else [entry])
        nullable = "null" in options
        if node is None and nullable:
            return
        if flat and (
            not isinstance(node, tuple(flat))
            or (set(options) & {"integer", "number"} and isinstance(node, bool)
                and "boolean" not in options)
        ):
            names = " or ".join(options)
            errors.append(f"{path}: expected {names}, got {type(node).__name__}")
            return

    if isinstance(node, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(node) < min_length:
            errors.append(
                f"{path}: must be at least {min_length} characters "
                f"(got {len(node)}) — a placeholder value does not satisfy the contract"
            )
        pattern = schema.get("pattern")
        if pattern is not None and not re.search(pattern, node):
            errors.append(f"{path}: {node!r} does not match required pattern {pattern}")

    if isinstance(node, (int, float)) and not isinstance(node, bool):
        minimum, maximum = schema.get("minimum"), schema.get("maximum")
        if minimum is not None and node < minimum:
            errors.append(f"{path}: must be >= {minimum}, got {node}")
        if maximum is not None and node > maximum:
            errors.append(f"{path}: must be <= {maximum}, got {node}")

    if isinstance(node, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(node) < min_items:
            errors.append(f"{path}: needs at least {min_items} item(s), got {len(node)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(node):
                validate(item, item_schema, f"{path}[{index}]", errors)

    if isinstance(node, dict):
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if field not in node:
                description = properties.get(field, {}).get("description", "")
                hint = f" — {description}" if description else ""
                errors.append(f"{path}: missing required field {field!r}{hint}")
        extra = schema.get("additionalProperties")
        if extra is False:
            for key in node:
                if key not in properties:
                    errors.append(f"{path}: unknown field {key!r} is not part of the contract")
        for key, value in node.items():
            if key in properties:
                validate(value, properties[key], f"{path}.{key}", errors)
            elif isinstance(extra, dict):
                # `additionalProperties` as a SCHEMA describes every value in a
                # map, and only the boolean form was handled — so a keyed map
                # validated as if it were empty. `frame-state-v1` keeps every
                # claim under exactly such a map, which means the graph the
                # reducer is the sole writer of has never been schema-checked at
                # all: an illegal status in a claim validated clean.
                validate(value, extra, f"{path}.{key}", errors)
