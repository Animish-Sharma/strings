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
        py_type = TYPE_MAP.get(expected)
        # bool is a subclass of int in Python; the contract never wants that.
        if py_type and (
            not isinstance(node, py_type)
            or (expected in {"integer", "number"} and isinstance(node, bool))
        ):
            errors.append(f"{path}: expected {expected}, got {type(node).__name__}")
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
        if schema.get("additionalProperties") is False:
            for key in node:
                if key not in properties:
                    errors.append(f"{path}: unknown field {key!r} is not part of the contract")
        for key, value in node.items():
            if key in properties:
                validate(value, properties[key], f"{path}.{key}", errors)
