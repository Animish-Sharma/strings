#!/usr/bin/env python3
"""Structural tier — WIT syntax and reference checking.

Checks the *shape* of an argument, cheaply, before any semantic cost is paid.
It is deliberately NOT adversarial: passing here means the argument is
well-formed, not that it is correct. Its ceiling is SKETCH.

Rules enforced (see the WIT language reference):
  - exactly one MODULE declaration
  - every step has a label, a keyword, and a BY justification
  - labels are sequential within their scope: [1], [2], [3] — not [1], [3]
  - every bracketed reference resolves to a step, declaration, or import alias
  - no forward references inside a proof
  - no references into a sibling CASE's body, and none to a sibling's [n.0]
  - PROOF OF names a declared claim
  - every proof ends in QED
  - the Status header, if present, is one of the four legal values

Usage:  structural.py <artifact.wit>
Exit:   0 pass, 1 fail, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STEP_KEYWORDS = {
    "HAVE", "SHOW", "ASSUME", "LET", "CONSIDER", "SUFFICES", "CASE", "CITE", "GAP",
}
DECL_KEYWORDS = {
    "DEFINE", "THEOREM", "LEMMA", "PROPOSITION", "COROLLARY",
    "CONJECTURE", "ALGORITHM", "REDUCTION",
}
LEGAL_STATUS = {"UNVERIFIED", "VERIFIED", "GAP", "REJECTED"}

RE_STATUS = re.compile(r"^--\s*Status:\s*(\w+)", re.IGNORECASE)
RE_MODULE = re.compile(r"^MODULE\s+\[?([A-Za-z]\w*)\]?")
RE_IMPORT = re.compile(r"^IMPORT\s+\S+\s+AS\s+\[?([A-Za-z]\w*)\]?")
RE_DECL = re.compile(rf"^({'|'.join(sorted(DECL_KEYWORDS))})\s+\[?([A-Za-z]\w*)\]?")
RE_PROOF_OF = re.compile(r"^PROOF\s+OF\s+\[?([A-Za-z]\w*)\]?")
RE_STEP = re.compile(r"^\[(\d+(?:\.\d+)*)\]\s+(\w+)")
RE_QED = re.compile(r"^\[?(\d+(?:\.\d+)*)?\]?\s*QED(\s+BY\s+(.*))?", re.IGNORECASE)
RE_REF = re.compile(r"\[([A-Za-z_]\w*(?:\.\w+)?|\d+(?:\.\d+)*)\]")


def strip_comment(line: str) -> str:
    """Remove a trailing `--` comment, leaving content."""
    idx = line.find("--")
    return line if idx == 0 else (line[:idx] if idx > 0 else line)


def parent_of(label: str) -> str | None:
    return label.rsplit(".", 1)[0] if "." in label else None


def is_ancestor(candidate: str, label: str) -> bool:
    return label.startswith(candidate + ".")


def given_labels(text: str) -> set[str]:
    """Labels declared in a GIVEN block.

    This tier parses the text itself rather than going through the shared
    parser, so the labels are read here too. Scanned rather than imported on
    purpose: the two readers agreeing about what a GIVEN line looks like is
    checkable, and a shared helper that silently changed shape would move both
    at once.
    """
    labels: set[str] = set()
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^GIVEN:\s*$", stripped):
            inside = True
            continue
        if re.match(r"^(CLAIM:|PROOF OF|THEOREM|MODULE|LEMMA)", stripped):
            inside = False
            continue
        if inside:
            m = re.match(r"^-\s*\[([A-Za-z]\w*)\]\s*:", stripped)
            if m:
                labels.add(m.group(1))
    return labels


def check(text: str) -> list[str]:
    problems: list[str] = []
    lines = text.splitlines()

    modules: list[int] = []
    aliases: set[str] = set()
    decls: dict[str, int] = {}
    proofs: list[tuple[str, int]] = []
    steps: list[tuple[str, str, int]] = []          # (label, keyword, line_no)
    step_line: dict[str, int] = {}
    case_labels: set[str] = set()
    justified: set[str] = set()
    qed_for: set[str] = set()
    refs: list[tuple[str, str, int]] = []           # (from_label, ref, line_no)

    current_step: str | None = None
    in_proof = False

    for line_no, raw in enumerate(lines, start=1):
        status = RE_STATUS.match(raw.strip())
        if status and status.group(1).upper() not in LEGAL_STATUS:
            problems.append(
                f"line {line_no}: Status '{status.group(1)}' is not one of "
                f"{sorted(LEGAL_STATUS)}"
            )

        line = strip_comment(raw).strip()
        if not line:
            continue

        if RE_MODULE.match(line):
            modules.append(line_no)
            continue
        m = RE_IMPORT.match(line)
        if m:
            aliases.add(m.group(1))
            continue
        m = RE_DECL.match(line)
        if m:
            decls[m.group(2)] = line_no
            in_proof = False
            current_step = None
            continue
        m = RE_PROOF_OF.match(line)
        if m:
            proofs.append((m.group(1), line_no))
            in_proof = True
            current_step = None
            continue

        m = RE_STEP.match(line)
        if m:
            label, keyword = m.group(1), m.group(2).upper()
            if keyword == "QED":
                qed_for.add(label)
                current_step = None
            elif keyword in STEP_KEYWORDS:
                if label in step_line:
                    problems.append(
                        f"line {line_no}: duplicate step label [{label}] "
                        f"(first at line {step_line[label]})"
                    )
                steps.append((label, keyword, line_no))
                step_line[label] = line_no
                if keyword == "CASE":
                    case_labels.add(label)
                # GAP and CASE are self-justifying; the rest need a BY.
                if keyword in {"GAP", "CASE"}:
                    justified.add(label)
                current_step = label
            else:
                problems.append(
                    f"line {line_no}: [{label}] has unknown keyword '{m.group(2)}' "
                    f"(expected one of {sorted(STEP_KEYWORDS)})"
                )
                current_step = label
            for ref in RE_REF.findall(line[len(m.group(0)) :]):
                refs.append((label, ref, line_no))
            continue

        if re.match(r"^BY\b", line, re.IGNORECASE):
            if current_step is not None:
                justified.add(current_step)
                for ref in RE_REF.findall(line):
                    refs.append((current_step, ref, line_no))
            continue

        if RE_QED.match(line) and "QED" in line.upper():
            m = RE_QED.match(line)
            if m and m.group(1):
                qed_for.add(m.group(1))
            else:
                qed_for.add("__top__")
            for ref in RE_REF.findall(line):
                refs.append(("__qed__", ref, line_no))
            current_step = None
            continue

        if in_proof and current_step is not None:
            for ref in RE_REF.findall(line):
                refs.append((current_step, ref, line_no))

    # --- structure ---
    if not modules:
        problems.append("no MODULE declaration")
    elif len(modules) > 1:
        problems.append(f"{len(modules)} MODULE declarations (exactly one required)")

    for name, line_no in proofs:
        if name not in decls:
            problems.append(
                f"line {line_no}: PROOF OF [{name}] but no such claim is declared"
            )

    if proofs and not qed_for:
        problems.append("proof has no QED")

    # --- justification ---
    for label, keyword, line_no in steps:
        if label not in justified:
            problems.append(
                f"line {line_no}: [{label}] {keyword} has no BY justification"
            )

    # --- label sequentiality within scope ---
    by_scope: dict[str | None, list[str]] = {}
    for label, _, _ in steps:
        by_scope.setdefault(parent_of(label), []).append(label)
    for scope, labels in by_scope.items():
        tails = sorted(int(l.rsplit(".", 1)[-1]) for l in labels)
        expected = list(range(1, len(tails) + 1))
        if tails != expected:
            where = f"under [{scope}]" if scope else "at top level"
            problems.append(
                f"labels {where} are {tails}, expected {expected} — "
                "labels must be sequential within their scope"
            )

    # --- reference resolution and scoping ---
    # A labelled hypothesis is citable. The GIVEN block invites a label on every
    # hypothesis and nothing could reference one, so `BY [hP]` — the most
    # ordinary justification a proof has — was refused as a dangling reference.
    # The gap survived because the reference artifact declares `[hx]` and then
    # never cites it, which is not how anyone writes a proof.
    #
    # Hypotheses need no ordering check: they hold from the first line of the
    # proof, so citing one can never be a forward reference.
    hypotheses = given_labels(text)
    known_names = set(decls) | aliases | hypotheses
    for src, ref, line_no in refs:
        if "." in ref and ref.split(".")[0] in aliases:
            continue
        if re.match(r"^\d", ref):
            base = ref
            # [n.0] is the synthesized CASE hypothesis.
            synthesized_case = None
            if ref.endswith(".0"):
                synthesized_case = ref[:-2]
                if synthesized_case not in case_labels:
                    problems.append(
                        f"line {line_no}: [{ref}] names a CASE hypothesis but "
                        f"[{synthesized_case}] is not a CASE"
                    )
                    continue
                if src != "__qed__" and not (
                    src == synthesized_case or is_ancestor(synthesized_case, src)
                ):
                    problems.append(
                        f"line {line_no}: [{src}] references [{ref}], another CASE's "
                        "hypothesis — a case's assumption is not in scope outside it"
                    )
                continue
            if base not in step_line and base not in qed_for:
                problems.append(f"line {line_no}: [{src}] references [{ref}], which does not exist")
                continue
            if src in {"__qed__"}:
                continue
            # forward reference?
            if base in step_line and step_line[base] > line_no:
                problems.append(
                    f"line {line_no}: [{src}] forward-references [{ref}] "
                    f"(defined later, line {step_line[base]})"
                )
            # cross-case reference: into another block's body
            src_parent, ref_parent = parent_of(src), parent_of(base)
            # A block's own QED summarizes its body, so [n] may cite [n.k].
            if (
                ref_parent
                and ref_parent != src_parent
                and ref_parent != src
                and not is_ancestor(ref_parent, src)
            ):
                if ref_parent in case_labels:
                    problems.append(
                        f"line {line_no}: [{src}] references [{ref}] inside CASE "
                        f"[{ref_parent}] — cite [{ref_parent}] (its QED) instead"
                    )
        else:
            if ref not in known_names:
                problems.append(
                    f"line {line_no}: [{src}] references [{ref}], which is not a "
                    "declaration, import alias, or step in this file"
                )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("artifact")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        text = Path(args.artifact).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    problems = check(text)
    if args.json:
        print(json.dumps({"verdict": "pass" if not problems else "fail",
                          "problems": problems}, indent=2))
    elif problems:
        print(f"STRUCTURAL: FAIL — {len(problems)} problem(s)\n")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("STRUCTURAL: PASS — well-formed (shape only; says nothing about correctness)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
