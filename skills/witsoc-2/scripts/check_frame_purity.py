#!/usr/bin/env python3
"""Frame purity check — governance rule 2 (see ARCHITECTURE.md).

The frame is only domain-agnostic if that claim is checkable. This script makes
it checkable, and is the cheapest guardrail the frame has against contract
erosion. Run it on every change.

Three checks. The first two run over frame files (everything under the skill
root except ``domains/`` and the exemptions below):

1. REFERENCE DIRECTION — no frame file may reference a concrete domain pack
   directory. Frame code never reaches down across the contract line; domain
   packs are reached only through the manifest.

2. VOCABULARY — no frame file may carry field-specific vocabulary. A frame
   document that needs a field's word to explain itself has stopped being a
   frame document. Terms are grouped by the domain they belong to, so a
   violation names which field leaked in.

3. RUNTIME LEAKAGE — every packet schema must still refuse provider, model,
   session, worktree, budget, and retry fields. Those belong to the
   orchestrator's execution envelope; a packet that knows what model produced it
   has coupled the discovery loop to the runtime.

A line may be exempted with a trailing ``frame-purity: allow`` marker. This
should be rare; the script reports the running count so its growth stays
visible in review rather than accumulating silently.

Exit status: 0 clean, 1 violations found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

SCANNED_SUFFIXES = {".md", ".json", ".py", ".sh", ".txt"}

# Domain packs live below the contract line and are exempt by construction.
EXCLUDED_DIRS = {"domains", ".git", "__pycache__", ".venv", "node_modules"}

# Two files necessarily contain the vocabulary they are checked for.
#
# The checker itself, obviously. And the improvement report, which is a record of
# work across the WHOLE skill — it has to name the packs it is reporting on, and
# a report that could not would be a report about nothing. It is a session
# record rather than frame doctrine, and the distinction is the point: doctrine
# tells a role what to do and must survive a pack being swapped out, while this
# describes what happened to particular packs on a particular day.
#
# Exemptions should stay rare and the count is printed on every run so their
# growth is visible in review rather than accumulating quietly.
EXEMPT_FILES = {"scripts/check_frame_purity.py", "IMPROVEMENT_REPORT.md"}

ALLOW_MARKER = "frame-purity: allow"

# Vocabulary that signals a particular field has leaked into the frame. Terms
# are matched case-insensitively on word boundaries. Only terms with no ordinary
# generic use belong here — the check has to stay credible to stay enabled, and
# a check that fires on ordinary scientific English gets switched off.
#
# Deliberately NOT banned, though they may look like candidates: "conjecture",
# "counterexample", "hypothesis", "evidence", "claim". These are part of the
# frame's own domain-neutral status and refutation vocabulary — a biologist and
# a mathematician both call an unestablished statement a conjecture. Banning
# them would push the frame into worse prose for no gain in purity.
#
# "admit" is likewise NOT banned: admission is the frame's own core verb for
# accepting evidence into state. Its formal-methods sense (a hole-punching
# directive) is a placeholder token, which every pack already has to declare in
# its own placeholder scan — that is the right place to catch it.
#
# "lean" IS banned despite colliding with ordinary English ("rely on"). A tool
# name leaking into the frame is the exact failure this check exists to catch,
# so the rare rephrase is worth paying for.
DOMAIN_VOCABULARY: dict[str, tuple[str, ...]] = {
    "formal-mathematics": (
        "lean",
        "mathlib",
        "coq",
        "isabelle",
        "theorem",
        "lemma",
        "proof",
        "prover",
        "tactic",
        "qed",
        "sorry",
        "axiom",
    ),
    "biology": (
        "gene",
        "genome",
        "protein",
        "assay",
        "knockdown",
        "pathway",
        "perturbseq",
        "in-vitro",
        "wet-lab",
    ),
    "quantum": (
        "qubit",
        "hamiltonian",
        "unitary",
        "decoherence",
        "entanglement",
    ),
    # A pack may name its Researcher whatever suits the field, but that name is
    # pack-side. The frame calls the role Researcher. These are the two existing
    # instantiations; the frame carried one of them as its role name until it was
    # caught, which is exactly the drift this check exists to prevent.
    "domain-role-names": (
        "lovasz",
        "durbin",
    ),
    "statistics-as-a-field": (
        "p-value",
        "confidence-interval",
    ),
}

# A concrete pack directory reference, e.g. "domains/chemistry/". Packs whose
# name starts with "_" are frame fixtures (domains/_mock), not fields.
DOMAIN_REF = re.compile(r"\bdomains/(?!_)([a-z0-9][a-z0-9-]*)")


class Violation:
    def __init__(self, path: Path, line_no: int, kind: str, detail: str, line: str):
        self.path = path
        self.line_no = line_no
        self.kind = kind
        self.detail = detail
        self.line = line.strip()

    def render(self) -> str:
        rel = self.path.relative_to(SKILL_ROOT)
        return f"  {rel}:{self.line_no}  [{self.kind}] {self.detail}\n      {self.line[:120]}"


def frame_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(SKILL_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        rel = path.relative_to(SKILL_ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.as_posix() in EXEMPT_FILES:
            continue
        out.append(path)
    return out


def build_term_patterns() -> list[tuple[str, str, re.Pattern[str]]]:
    patterns = []
    for domain, terms in DOMAIN_VOCABULARY.items():
        for term in terms:
            # Hyphenated terms need their internal hyphen escaped, and must not
            # match inside a longer word.
            patterns.append(
                (domain, term, re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE))
            )
    return patterns


def scan(paths: list[Path]) -> tuple[list[Violation], int]:
    patterns = build_term_patterns()
    violations: list[Violation] = []
    allowed = 0

    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line_no, line in enumerate(lines, start=1):
            if ALLOW_MARKER in line:
                allowed += 1
                continue

            for match in DOMAIN_REF.finditer(line):
                violations.append(
                    Violation(
                        path,
                        line_no,
                        "reference-direction",
                        f"frame file references concrete domain pack 'domains/{match.group(1)}'",
                        line,
                    )
                )

            for domain, term, pattern in patterns:
                if pattern.search(line):
                    violations.append(
                        Violation(
                            path,
                            line_no,
                            "vocabulary",
                            f"'{term}' is {domain} vocabulary and belongs in a domain pack",
                            line,
                        )
                    )

    return violations, allowed


# Runtime concerns belong to the orchestrator's execution envelope, never to a
# packet. Each packet schema carries a denylist; this checks nobody dropped it.
RUNTIME_KEYS = {
    "provider", "model", "session_id", "worktree", "machine", "process_id",
    "retry_count", "tokens", "cost_usd", "wall_clock_ms", "budget",
}
PACKET_SCHEMAS = (
    "frame-claim-v1", "frame-work-item-v1", "frame-result-v1",
    "frame-receipt-v1", "frame-review-v1", "frame-admission-v1",
)


def check_runtime_denylists() -> list[str]:
    """Every packet schema must still refuse runtime fields."""
    problems: list[str] = []
    for name in PACKET_SCHEMAS:
        path = SKILL_ROOT / "schemas" / f"{name}.schema.json"
        if not path.exists():
            problems.append(f"{name}.schema.json is missing")
            continue
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{name}.schema.json does not parse: {exc}")
            continue
        denied = {
            entry.get("required", [None])[0]
            for entry in schema.get("not", {}).get("anyOf", [])
            if isinstance(entry, dict)
        }
        missing = RUNTIME_KEYS - denied
        if missing:
            problems.append(
                f"{name}.schema.json does not refuse runtime field(s): "
                f"{', '.join(sorted(missing))}"
            )
        leaked = RUNTIME_KEYS & set(schema.get("properties", {}))
        if leaked:
            problems.append(
                f"{name}.schema.json DEFINES runtime field(s): {', '.join(sorted(leaked))}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--quiet", action="store_true", help="print only the verdict line"
    )
    args = parser.parse_args()

    paths = frame_files()
    violations, allowed = scan(paths)

    runtime_problems = check_runtime_denylists()
    if runtime_problems:
        print(f"FRAME PURITY: FAIL — {len(runtime_problems)} runtime-leak problem(s)\n")
        for problem in runtime_problems:
            print(f"  {problem}")
        print(
            "\nA packet that knows what model produced it has coupled the discovery"
            "\nloop to the runtime. See references/bridges.md."
        )
        return 1

    if violations:
        print(f"FRAME PURITY: FAIL — {len(violations)} violation(s)\n")
        if not args.quiet:
            for violation in violations:
                print(violation.render())
            print(
                "\nFix by moving the field-specific content into a domain pack under"
                "\ndomains/, or by rephrasing the frame text so it does not depend on"
                "\nany one field's vocabulary. See ARCHITECTURE.md governance rule 2."
            )
        return 1

    summary = f"FRAME PURITY: PASS — {len(paths)} frame file(s) clean"
    if allowed:
        summary += f", {allowed} explicitly allowed line(s)"
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
