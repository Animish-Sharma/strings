#!/usr/bin/env python3
"""Blueprint -> WIT artifact.

Generation is a **rendering**, not an invention. The blueprint's `lemma_plan`
already is the proof structure: each entry becomes one step, its `depends_on`
becomes the `BY [n]` references, and each external dependency becomes a citation.
Nothing is added that the blueprint did not authorize.

That is the whole design. A generator that invents steps is a generator whose
output nobody can trace back to a reviewed plan, and the frozen target stops
meaning anything.

Refuses to emit when:
  - a `depends_on` names a step that does not exist or comes later;
  - a step cites something outside `external_dependencies`;
  - the rendered CLAIM does not hash to the blueprint's frozen target hash.

Usage:
    generate_wit.py --blueprint <handoff.json> [--out <file.wit>] [--json]
Exit: 0 written, 1 refused, 2 IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from witlib import STEP_KEYWORDS, normalize  # noqa: E402

REQUIRED_SECTIONS = [
    "metadata", "target_formalization", "target_protection",
    "external_dependencies", "lemma_plan", "generator_directive",
]
# The blueprint is structurally incapable of ordering a success claim.
LEGAL_ASSERTED_STATUS = {"UNVERIFIED", "PARTIAL", "CONDITIONAL", "GAP"}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_blueprint(bp: dict) -> list[str]:
    problems: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in bp:
            problems.append(f"blueprint is missing required section '{section}'")
    if problems:
        return problems

    protection = bp["target_protection"]
    if protection.get("statement_tampering_forbidden") is not True:
        problems.append(
            "target_protection.statement_tampering_forbidden must be literally true"
        )
    frozen = protection.get("frozen_target_sha256", "")
    if len(frozen) != 64:
        problems.append("target_protection.frozen_target_sha256 must be 64 hex chars")

    for index, mutation in enumerate(protection.get("authorized_mutations", []) or []):
        for field in ("old_target_sha256", "new_target_sha256", "mutation_kind",
                      "reason", "authorized_by"):
            if not mutation.get(field):
                problems.append(f"authorized_mutations[{index}] is missing '{field}'")

    directive = bp["generator_directive"]
    asserted = directive.get("status_to_assert", "UNVERIFIED")
    if asserted not in LEGAL_ASSERTED_STATUS:
        problems.append(
            f"generator_directive.status_to_assert is {asserted!r}; a blueprint may "
            f"only order one of {sorted(LEGAL_ASSERTED_STATUS)} — it cannot order a "
            "success claim"
        )

    known_deps = {d.get("theorem_name") for d in bp["external_dependencies"]}
    seen: list[str] = []
    for index, step in enumerate(bp["lemma_plan"], start=1):
        sid = str(step.get("step_id", index))
        kind = str(step.get("type", "HAVE")).upper()
        if kind not in STEP_KEYWORDS:
            problems.append(f"step {sid}: type {kind!r} is not a WIT step keyword")
        if not step.get("statement"):
            problems.append(f"step {sid}: no statement")
        for dep in step.get("depends_on", []) or []:
            if str(dep) not in seen:
                problems.append(
                    f"step {sid}: depends_on [{dep}] which is not an earlier step "
                    "(WIT forbids forward references)"
                )
        for cite in step.get("cites", []) or []:
            if cite not in known_deps:
                problems.append(
                    f"step {sid}: cites {cite!r}, which is not in external_dependencies. "
                    "Out of scope is not a step."
                )
        seen.append(sid)

    if not bp["lemma_plan"]:
        problems.append("lemma_plan is empty — there is nothing to render")

    return problems


def render(bp: dict) -> tuple[str, str]:
    """Return (wit_text, claim_block_text)."""
    target = bp["target_formalization"]
    name = bp["metadata"].get("name") or "artifact"
    claim = normalize(target.get("claim", ""))
    directive = bp["generator_directive"]

    lines: list[str] = []
    lines.append(f"-- Status: {directive.get('status_to_assert', 'UNVERIFIED')}")
    original = bp["target_protection"].get("original_statement", "")
    if original:
        lines.append(f"-- Original: {normalize(original)}")
    lines.append(f"-- Frozen-target-sha256: {bp['target_protection']['frozen_target_sha256']}")
    lines.append("")
    lines.append(f"MODULE [{name}]")
    lines.append("")

    kind = str(bp["metadata"].get("kind", "THEOREM")).upper()
    lines.append(f"{kind} [{name}]:")
    hypotheses = target.get("hypotheses", []) or []
    if hypotheses:
        lines.append("  GIVEN:")
        for hypothesis in hypotheses:
            if isinstance(hypothesis, dict):
                lines.append(f"    - [{hypothesis['name']}]: {normalize(hypothesis['text'])}")
            else:
                lines.append(f"    - {normalize(str(hypothesis))}")
    lines.append("  CLAIM:")
    lines.append(f"    {claim}")
    lines.append("")

    lines.append(f"PROOF OF [{name}]:")
    lines.append("")
    last_label = None
    for index, step in enumerate(bp["lemma_plan"], start=1):
        label = str(step.get("step_id", index))
        kind = str(step.get("type", "HAVE")).upper()
        statement = normalize(step["statement"])
        if kind == "GAP":
            expecting = step.get("expecting")
            head = (f"  [{label}] GAP EXPECTING [{expecting}]: {statement}"
                    if expecting else f"  [{label}] GAP: {statement}")
            lines.append(head)
        else:
            lines.append(f"  [{label}] {kind} {statement}")
            refs = [f"[{d}]" for d in (step.get("depends_on") or [])]
            refs += ["@{" + c + "}" for c in (step.get("cites") or [])]
            method = normalize(step.get("method", "") or "")
            # A BY of bare references with no method is a weak justification.
            parts = [", ".join(refs)] if refs else []
            if method:
                parts.append(method)
            if not parts:
                parts = ["hypothesis"]
            lines.append(f"      BY {', '.join(parts)}.")
        last_label = label
        lines.append("")

    lines.append(f"  QED BY [{last_label}].")
    lines.append("")
    return "\n".join(lines), claim


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blueprint", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        bp = json.loads(Path(args.blueprint).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    problems = check_blueprint(bp)
    if problems:
        result = {"verdict": "refused", "problems": problems}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"GENERATE: REFUSED — {len(problems)} blueprint problem(s)\n")
            for problem in problems:
                print(f"  {problem}")
            print("\nGeneration renders a reviewed plan. It does not repair one.")
        return 1

    text, claim = render(bp)
    frozen = bp["target_protection"]["frozen_target_sha256"]
    rendered = sha256(claim)
    if rendered != frozen:
        result = {
            "verdict": "refused",
            "problems": [
                f"rendered CLAIM hashes to {rendered[:16]}... but the blueprint's "
                f"frozen_target_sha256 is {frozen[:16]}...  The artifact would state "
                "something other than the frozen target."
            ],
            "rendered_claim": claim,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("GENERATE: REFUSED — rendered CLAIM does not match the frozen target")
            print(f"  rendered: {rendered}")
            print(f"  frozen:   {frozen}")
            print(f"  claim as rendered: {claim}")
        return 1

    out = Path(args.out) if args.out else Path(f"{bp['metadata'].get('name','artifact')}.wit")
    if out.exists():
        print(f"GENERATE: REFUSED — {out} already exists; refusing to overwrite",
              file=sys.stderr)
        return 1
    out.write_text(text, encoding="utf-8")

    result = {"verdict": "written", "path": str(out), "claim_sha256": rendered,
              "steps": len(bp["lemma_plan"]),
              "status_asserted": bp["generator_directive"].get("status_to_assert",
                                                              "UNVERIFIED")}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"GENERATE: wrote {out} ({result['steps']} steps, "
              f"status {result['status_asserted']})")
        print("  CLAIM hash matches the frozen target.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
