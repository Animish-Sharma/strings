#!/usr/bin/env python3
"""Doc-link check — do the documents point at files that exist?

Every document here names paths: a role's doctrine, a schema, a script, another
reference. Those names are load-bearing — `SKILL.md` telling a role to read
`references/failure_recovery.md` is the mechanism by which the role reads it —
and a name that resolves to nothing fails silently. The reader follows it, finds
nothing, and either invents what it should have said or carries on without it.
Both are worse than the document admitting the gap.

This is the cheapest guardrail after frame purity and it catches the specific
decay that happens when files move: the documentation keeps describing the tree
that used to be there.

What it checks:

- Markdown links and inline-code tokens that contain a slash. A bare filename in
  backticks is a name, not a path — flagging those was this checker's own first
  bug, seventeen false positives of pure prose
- Every `doctrine.roles.*` and `doctrine.rules[]` entry in every pack manifest
- Every `path` in a pack's claim_schema and receipt_format

What it deliberately does not check: URLs, and paths inside fenced blocks marked
as illustrative with `<name>`-style placeholders. A placeholder is not a broken
link, and flagging it trains people to ignore the checker.

Usage:  check_doc_links.py [--json]
Exit:   0 every named path resolves, 1 something does not
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules",
             # Foreign documents held for comparison — see check_frame_purity.
             "vendored"}

# A path-looking token: has a slash and a recognizable extension, or is a bare
# directory reference under a known root.
# A slash is required. `widget.py` in a sentence is a NAME — the thing being
# discussed — while `scripts/widget.py` is a PATH, a claim about where it is.
# The illustration is a made-up filename on purpose: an earlier version reached
# for a real pack's script here, and the structural purity rule was right to
# refuse it. A frame file explaining itself with one pack's filename has still
# learned that filename.
# The first version of this check did not distinguish them and reported
# seventeen false positives on its first run, every one of them prose. A checker
# that fires on ordinary writing gets switched off, and then it catches nothing.
# Any extension, not a list of them. Enumerating file types meant naming the
# ones particular fields use, which is field knowledge living in a frame file —
# the purity check caught it, correctly. A pack may invent any extension it
# likes and its paths still get checked.
RE_INLINE = re.compile(r"`([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,8})`")
RE_MDLINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)\)")
PLACEHOLDER = re.compile(r"<[^>]+>|\{[^}]+\}|\bNAME\b")


def candidates(text: str) -> set[str]:
    found = set(RE_INLINE.findall(text))
    for link in RE_MDLINK.findall(text):
        if not link.startswith(("http://", "https://", "mailto:")) and "/" in link:
            found.add(link)
    return {f for f in found if not PLACEHOLDER.search(f)}


def resolve(path_text: str, doc: Path) -> bool:
    """A path may be relative to the document, to the skill root, or to a pack
    root. Plane's canonical witsoc/ prefix names the same skill-root path."""
    if path_text.startswith("witsoc/"):
        path_text = path_text.removeprefix("witsoc/")
    bases = [doc.parent, SKILL_ROOT]
    # Walk up to any enclosing pack directory.
    for parent in doc.parents:
        if (parent / "domain.json").is_file():
            bases.append(parent)
            break
    return any((base / path_text).exists() for base in bases)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    broken: list[dict] = []
    checked = 0

    for doc in sorted(SKILL_ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in doc.relative_to(SKILL_ROOT).parts):
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        for candidate in sorted(candidates(text)):
            checked += 1
            if not resolve(candidate, doc):
                broken.append({"document": str(doc.relative_to(SKILL_ROOT)),
                               "path": candidate, "kind": "document reference"})

    for manifest in sorted((SKILL_ROOT / "domains").glob("*/domain.json")):
        pack = json.loads(manifest.read_text(encoding="utf-8"))
        root = manifest.parent
        doctrine = pack.get("doctrine", {}) or {}
        named = [(f"doctrine.roles.{role}", rel)
                 for role, rel in (doctrine.get("roles") or {}).items()]
        # A rule entry is a path or an object carrying one. Five readers had to
        # learn that, and this was the fifth — a shape change is only cheap when
        # something enumerates the readers, and nothing does.
        named += [(f"doctrine.rules[{i}]",
                   entry if isinstance(entry, str) else (entry or {}).get("path", ""))
                  for i, entry in enumerate(doctrine.get("rules") or [])]
        for label, key in (("claim_schema.path", "claim_schema"),
                           ("receipt_format.path", "receipt_format")):
            rel = (pack.get(key) or {}).get("path")
            if rel:
                named.append((label, rel))
        entry = (pack.get("verification_adapter") or {}).get("entry_point")
        if entry:
            named.append(("verification_adapter.entry_point", entry))
        for label, rel in named:
            checked += 1
            if not (root / rel).exists():
                broken.append({"document": str(manifest.relative_to(SKILL_ROOT)),
                               "path": rel, "kind": label})

    if args.json:
        print(json.dumps({"checked": checked, "broken": broken}, indent=2))
    elif broken:
        print(f"DOC LINKS: FAIL — {len(broken)} of {checked} named path(s) resolve to nothing\n")
        for item in broken:
            print(f"  {item['document']}  ->  {item['path']}   [{item['kind']}]")
        print("\nA name that resolves to nothing fails silently: the reader follows it, finds\n"
              "nothing, and either invents what it should have said or proceeds without it.")
    else:
        print(f"DOC LINKS: PASS — {checked} named path(s) all resolve")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
