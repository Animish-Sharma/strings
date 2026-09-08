#!/usr/bin/env python3
"""Check that Plane can describe Witsoc and hard cases route into a pack."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import resolve_domain
from witsoc_core import modes


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = SKILL_ROOT / "SKILL.md"
PLACEHOLDER_DESCRIPTIONS = {">", ">-", ">+", "|", "|-", "|+"}


def plane_frontmatter_scalar(content: str, key: str) -> str | None:
    """Mirror Plane's deliberately small frontmatter parser exactly."""
    frontmatter = re.match(r"^---\n([\s\S]*?)\n---", content)
    if not frontmatter:
        return None
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter.group(1), re.MULTILINE)
    if not match:
        return None
    return re.sub(r"^[\"']|[\"']$", "", match.group(1).strip())


def load_fixtures() -> tuple[
    list[dict[str, Any]], list[str], list[str], list[str], list[str]
]:
    cases: list[dict[str, Any]] = []
    terms: list[str] = []
    skill_terms: list[str] = []
    forbidden_phrases: list[str] = []
    problems: list[str] = []
    paths = sorted(SKILL_ROOT.glob("domains/*/evals/discovery/cases.json"))
    if not paths:
        return [], [], [], [], ["no discovery fixtures found"]

    seen_ids: set[str] = set()
    for path in paths:
        rel = path.relative_to(SKILL_ROOT)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{rel}: unreadable fixture: {exc}")
            continue
        if not isinstance(payload, dict) or payload.get("schema") != "witsoc.discovery-cases.v1":
            problems.append(f"{rel}: unsupported or missing schema")
            continue
        declared_terms = payload.get("description_terms")
        declared_cases = payload.get("cases")
        if not isinstance(declared_terms, list) or not all(
            isinstance(term, str) and term.strip() for term in declared_terms
        ):
            problems.append(f"{rel}: description_terms must be non-empty strings")
        else:
            terms.extend(declared_terms)
        for key, destination in (
            ("skill_terms", skill_terms),
            ("forbidden_skill_phrases", forbidden_phrases),
        ):
            values = payload.get(key, [])
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                problems.append(f"{rel}: {key} must contain non-empty strings")
            else:
                destination.extend(values)
        if not isinstance(declared_cases, list) or not declared_cases:
            problems.append(f"{rel}: cases must be a non-empty list")
            continue
        for index, case in enumerate(declared_cases):
            label = f"{rel}:cases[{index}]"
            if not isinstance(case, dict):
                problems.append(f"{label}: case must be an object")
                continue
            required = {"id", "statement", "expect_decision", "expect_domain", "source", "why"}
            missing = sorted(required - set(case))
            if missing:
                problems.append(f"{label}: missing {', '.join(missing)}")
                continue
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id:
                problems.append(f"{label}: id must be a non-empty string")
                continue
            if case_id in seen_ids:
                problems.append(f"{label}: duplicate id {case_id!r}")
                continue
            if not isinstance(case.get("statement"), str) or not case["statement"].strip():
                problems.append(f"{label}: statement must be a non-empty string")
                continue
            if "expect_mode" in case and case["expect_mode"] not in modes.MODES:
                problems.append(f"{label}: expect_mode is not a supported Witsoc mode")
                continue
            seen_ids.add(case_id)
            cases.append(case)
    return (
        cases,
        list(dict.fromkeys(terms)),
        list(dict.fromkeys(skill_terms)),
        list(dict.fromkeys(forbidden_phrases)),
        problems,
    )


def main() -> int:
    problems: list[str] = []
    try:
        content = SKILL_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"SKILL DISCOVERY: FAIL\n  cannot read SKILL.md: {exc}")
        return 1

    name = plane_frontmatter_scalar(content, "name")
    description = plane_frontmatter_scalar(content, "description")
    if name != "witsoc":
        problems.append(f"catalog name is {name!r}, expected 'witsoc'")
    if description is None or not description.strip():
        problems.append("catalog description is absent or empty")
    elif description in PLACEHOLDER_DESCRIPTIONS:
        problems.append(
            f"catalog description is a block scalar marker {description!r}; "
            "Plane exposes the marker instead of the following text"
        )

    cases, description_terms, skill_terms, forbidden_phrases, fixture_problems = load_fixtures()
    problems.extend(fixture_problems)
    normalized_description = (description or "").casefold()
    for term in description_terms:
        if term.casefold() not in normalized_description:
            problems.append(f"catalog description does not expose activation term {term!r}")
    normalized_skill = content.casefold()
    for term in skill_terms:
        if term.casefold() not in normalized_skill:
            problems.append(f"skill body does not expose retention term {term!r}")
    for phrase in forbidden_phrases:
        if phrase.casefold() in normalized_skill:
            problems.append(f"skill body retains forbidden opt-out phrase {phrase!r}")

    packs, pack_problems = resolve_domain.load_packs()
    problems.extend(f"domain registry: {problem}" for problem in pack_problems)
    for case in cases:
        result = resolve_domain.decide(packs, resolve_domain.normalize(case["statement"]))
        got = (result.get("decision"), result.get("domain"))
        expected = (case["expect_decision"], case["expect_domain"])
        if got != expected:
            problems.append(
                f"case {case['id']!r} routed to {got[0]}/{got[1]}, "
                f"expected {expected[0]}/{expected[1]}"
            )
        expected_mode = case.get("expect_mode")
        if expected_mode:
            actual_mode = modes.choose_mode(case["statement"])["mode"]
            if actual_mode != expected_mode:
                problems.append(
                    f"case {case['id']!r} selected mode {actual_mode}, expected {expected_mode}"
                )

    if problems:
        print(f"SKILL DISCOVERY: FAIL - {len(problems)} problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("SKILL DISCOVERY: PASS")
    print(f"  Plane catalog description: {len(description or '')} characters, one line")
    print(f"  Activation terms: {len(description_terms)}")
    print(f"  Retention terms: {len(skill_terms)}, forbidden opt-outs absent: {len(forbidden_phrases)}")
    print(f"  Hard/open routing cases: {len(cases)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
