#!/usr/bin/env python3
"""Shared WIT parser.

One parser, used by the structural checker, the generator, and the WIT->Lean
translator. Two copies of a grammar drift, and a translator that disagrees with
its checker about what a file says is worse than having neither.

Structures returned are deliberately plain so callers can do their own analysis
without importing behaviour.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STEP_KEYWORDS = {
    "HAVE", "SHOW", "ASSUME", "LET", "CONSIDER", "SUFFICES", "CASE", "CITE", "GAP",
}
DECL_KEYWORDS = {
    "DEFINE", "THEOREM", "LEMMA", "PROPOSITION", "COROLLARY",
    "CONJECTURE", "ALGORITHM", "REDUCTION",
}
# Only these four are legal in a `-- Status:` header. Research statuses such as
# OPEN / PARTIAL / CONDITIONAL belong in the report, never in the artifact.
LEGAL_STATUS = {"UNVERIFIED", "VERIFIED", "GAP", "REJECTED"}

# Steps that carry a provable obligation — the ones that become leaves.
OBLIGATION_KEYWORDS = {"HAVE", "SHOW", "SUFFICES", "CASE", "CITE", "GAP", "CONSIDER"}

RE_STATUS = re.compile(r"^--\s*Status:\s*(\w+)", re.IGNORECASE)
RE_TEMPLATE = re.compile(r"^--\s*Template:\s*true", re.IGNORECASE)
RE_MODULE = re.compile(r"^MODULE\s+\[?([A-Za-z]\w*)\]?")
RE_IMPORT = re.compile(r"^IMPORT\s+(\S+)\s+AS\s+\[?([A-Za-z]\w*)\]?")
RE_DECL = re.compile(rf"^({'|'.join(sorted(DECL_KEYWORDS))})\s+\[?([A-Za-z]\w*)\]?")
RE_PROOF_OF = re.compile(r"^PROOF\s+OF\s+\[?([A-Za-z]\w*)\]?")
RE_STEP = re.compile(r"^\[(\d+(?:\.\d+)*)\]\s+(\w+)")
RE_BY = re.compile(r"^BY\b\s*(.*)", re.IGNORECASE)
RE_QED = re.compile(r"^\[?(\d+(?:\.\d+)*)?\]?\s*QED\b(?:\s+BY\s+(.*))?", re.IGNORECASE)
RE_REF = re.compile(r"\[([A-Za-z_]\w*(?:\.\w+)?|\d+(?:\.\d+)*)\]")
RE_CITE_AT = re.compile(r"@\{([^}]*)\}")


@dataclass
class Step:
    label: str
    keyword: str
    text: str
    line_no: int
    by_text: str = ""
    refs: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    gap_expecting: str | None = None

    @property
    def parent(self) -> str | None:
        return self.label.rsplit(".", 1)[0] if "." in self.label else None

    @property
    def depth(self) -> int:
        return self.label.count(".")


@dataclass
class Document:
    status: str | None = None
    is_template: bool = False
    module: str | None = None
    module_lines: list[int] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)      # alias -> path
    declarations: dict[str, int] = field(default_factory=dict)  # name -> line
    given: list[tuple[str | None, str]] = field(default_factory=list)
    claim: str = ""
    proofs: list[tuple[str, int]] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    qed_labels: set[str] = field(default_factory=set)
    qed_refs: list[tuple[str, int]] = field(default_factory=list)

    def step(self, label: str) -> Step | None:
        return next((s for s in self.steps if s.label == label), None)

    @property
    def case_labels(self) -> set[str]:
        return {s.label for s in self.steps if s.keyword == "CASE"}

    @property
    def step_lines(self) -> dict[str, int]:
        return {s.label: s.line_no for s in self.steps}


def strip_comment(line: str) -> str:
    idx = line.find("--")
    return line if idx <= 0 else line[:idx]


def parse(text: str) -> Document:
    doc = Document()
    lines = text.splitlines()
    current: Step | None = None
    section: str | None = None       # GIVEN | CLAIM while inside a claim block

    for line_no, raw in enumerate(lines, start=1):
        stripped = raw.strip()

        m = RE_STATUS.match(stripped)
        if m:
            doc.status = m.group(1).upper()
            continue
        if RE_TEMPLATE.match(stripped):
            doc.is_template = True
            continue

        line = strip_comment(raw).strip()
        if not line:
            continue

        if RE_MODULE.match(line):
            doc.module = RE_MODULE.match(line).group(1)
            doc.module_lines.append(line_no)
            section = None
            continue

        m = RE_IMPORT.match(line)
        if m:
            doc.imports[m.group(2)] = m.group(1)
            continue

        m = RE_DECL.match(line)
        if m:
            doc.declarations[m.group(2)] = line_no
            current, section = None, None
            continue

        m = RE_PROOF_OF.match(line)
        if m:
            doc.proofs.append((m.group(1), line_no))
            current, section = None, None
            continue

        if re.match(r"^GIVEN:\s*$", line):
            section = "GIVEN"
            continue
        if re.match(r"^CLAIM:\s*$", line):
            section = "CLAIM"
            continue

        m = RE_STEP.match(line)
        if m:
            section = None
            label, keyword = m.group(1), m.group(2).upper()
            rest = line[m.end():].strip()
            if keyword == "QED":
                doc.qed_labels.add(label)
                for ref in RE_REF.findall(rest):
                    doc.qed_refs.append((ref, line_no))
                current = None
                continue
            step = Step(label=label, keyword=keyword, text=rest.lstrip(": ").strip(),
                        line_no=line_no)
            if keyword == "GAP":
                gm = re.match(r"EXPECTING\s+\[([A-Za-z]\w*)\]", rest, re.IGNORECASE)
                if gm:
                    step.gap_expecting = gm.group(1)
            step.citations += RE_CITE_AT.findall(rest)
            doc.steps.append(step)
            current = step
            continue

        m = RE_BY.match(line)
        if m and current is not None:
            current.by_text = m.group(1).strip()
            current.refs += RE_REF.findall(m.group(1))
            current.citations += RE_CITE_AT.findall(m.group(1))
            continue

        m = RE_QED.match(line)
        if m and "QED" in line.upper():
            doc.qed_labels.add(m.group(1) or "__top__")
            for ref in RE_REF.findall(line):
                doc.qed_refs.append((ref, line_no))
            current = None
            continue

        if section == "GIVEN":
            hm = re.match(r"^-\s*\[([A-Za-z]\w*)\]\s*:\s*(.*)$", line)
            if hm:
                doc.given.append((hm.group(1), hm.group(2).strip()))
            elif line.startswith("-"):
                doc.given.append((None, line.lstrip("- ").strip()))
            continue
        if section == "CLAIM":
            doc.claim = (doc.claim + " " + line).strip()
            continue

        if current is not None and not current.by_text:
            current.text = (current.text + " " + line).strip()

    return doc


def normalize(text: str) -> str:
    return " ".join(text.split())


def topological(steps: list[Step]) -> list[Step]:
    """Steps in dependency order. WIT forbids forward references, so document
    order is already topological; this makes that explicit and stable."""
    return sorted(steps, key=lambda s: [int(p) for p in s.label.split(".")])
