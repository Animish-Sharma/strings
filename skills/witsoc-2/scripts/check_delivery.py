#!/usr/bin/env python3
"""Delivery checks — is this thing shippable as a skill, not just correct as code?

Every other check here asks whether the frame is sound. This one asks whether it
can be delivered, which is a different question with its own failure modes — and
the one that mattered most in practice: this skill was complete, tested, and
entirely unshipped, so none of its correctness was reachable by anyone.

Four things, each of which has broken here at least once:

1. CONTEXT BUDGET. A skill is loaded into an agent's context by fetching its
   SKILL.md. That file is a cost paid on every activation, so it has a budget,
   and a frame that cannot state its own rules inside one has a design problem
   rather than a documentation problem.
2. ENTRY POINTS. The runtime execs skills as shell scripts. A skill whose only
   surface is `python3 some/path.py` has no door the orchestrator knows how to
   open, however good the room behind it is.
3. REGISTRY ACCURACY. The pack table in domains/README.md is what a reader
   trusts before running anything. A table listing a pack that no longer exists,
   or missing one that does, is worse than no table.
4. NO SHIPPED CRUFT. This repository is cloned onto every client machine, so a
   TRACKED build artifact is bytes on someone else's disk forever. An untracked
   one is nobody's business, and a check that cannot tell them apart fires on
   every developer and gets switched off.

Usage:  check_delivery.py [--budget-kb N] [--json]
Exit:   0 shippable, 1 not
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUDGET_KB = 16
CRUFT = ("__pycache__", ".pyc", ".pytest_cache", ".DS_Store", ".egg-info")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--budget-kb", type=int, default=DEFAULT_BUDGET_KB)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    problems: list[str] = []
    notes: list[str] = []
    facts: dict = {}

    # 1. context budget
    skill_md = SKILL_ROOT / "SKILL.md"
    size = skill_md.stat().st_size if skill_md.is_file() else 0
    facts["skill_md_bytes"] = size
    facts["skill_md_budget_bytes"] = args.budget_kb * 1024
    if not skill_md.is_file():
        problems.append("no SKILL.md — nothing to activate")
    elif size > args.budget_kb * 1024:
        problems.append(
            f"SKILL.md is {size / 1024:.1f}KB against a {args.budget_kb}KB budget. It is paid on "
            "every activation, and a frame that cannot state its own rules inside the budget has "
            "a design problem wearing a documentation problem's clothes")
    role_docs = {p.parent.name: p.stat().st_size
                 for p in SKILL_ROOT.glob("*/SKILL.md") if p.parent.name != "domains"}
    facts["role_doc_bytes"] = role_docs
    for role, role_size in role_docs.items():
        if role_size > args.budget_kb * 1024:
            notes.append(f"{role}/SKILL.md is {role_size / 1024:.1f}KB — loaded only when acting "
                         "as that role, so it is a second budget rather than the same one")

    # 2. entry points
    wrappers = sorted(p.name for p in (SKILL_ROOT / "scripts").glob("*.sh"))
    facts["shell_entry_points"] = wrappers
    if not wrappers:
        problems.append(
            "no shell entry point under scripts/. The runtime execs skills as shell scripts; "
            "Python alone gives the orchestrator no door it knows how to open")
    else:
        not_executable = [w for w in wrappers
                          if not os.access(SKILL_ROOT / "scripts" / w, os.X_OK)]
        if not_executable:
            problems.append(f"entry point(s) {not_executable} are not executable")
        for wrapper in wrappers:
            text = (SKILL_ROOT / "scripts" / wrapper).read_text(encoding="utf-8")
            if not text.startswith("#!"):
                problems.append(f"{wrapper} has no shebang; skill-run execs it directly")

    # SKILL.md must not document paths that only work from the checkout.
    if skill_md.is_file():
        body = skill_md.read_text(encoding="utf-8")
        bare = re.findall(r"^\s*python3 (?:scripts|domains)/", body, re.MULTILINE)
        if bare:
            problems.append(
                f"SKILL.md documents {len(bare)} command(s) with a relative path. An agent's "
                "working directory is a worktree, not this checkout, so those find nothing")

    # 3. registry accuracy
    registry = SKILL_ROOT / "domains" / "README.md"
    on_disk = sorted(p.parent.name for p in (SKILL_ROOT / "domains").glob("*/domain.json"))
    facts["packs_on_disk"] = on_disk
    if registry.is_file():
        text = registry.read_text(encoding="utf-8")
        listed = set(re.findall(r"^\|\s*`([a-z_][a-z0-9_-]*)`", text, re.MULTILINE))
        facts["packs_listed"] = sorted(listed)
        for pack in on_disk:
            if pack not in listed:
                problems.append(f"pack {pack!r} exists and the registry does not list it")
        for pack in sorted(listed - set(on_disk)):
            problems.append(f"registry lists {pack!r}, which is not on disk")
    else:
        notes.append("no domains/README.md; a reader has no index of what is registered")

    # 4. cruft
    # What ships, not what exists. A .pyc in a working tree is normal; a .pyc
    # that git tracks is bytes on every client machine forever. Asking the wrong
    # one fires on every developer and gets the check switched off.
    ignore = SKILL_ROOT / ".gitignore"
    ignored_markers = set()
    if ignore.is_file():
        for line in ignore.read_text(encoding="utf-8").splitlines():
            line = line.strip().rstrip("/")
            if line and not line.startswith("#"):
                ignored_markers.add(line.lstrip("*"))
    tracked_cruft = [
        str(p.relative_to(SKILL_ROOT)) for p in SKILL_ROOT.rglob("*")
        if any(marker in p.name or marker in str(p) for marker in CRUFT)
        and not any(m and m in str(p) for m in ignored_markers)]
    if not ignore.is_file():
        problems.append("no .gitignore; build artifacts will be tracked by default and this "
                        "repository is cloned onto every client machine")
    facts["cruft_paths"] = len(tracked_cruft)
    if tracked_cruft:
        problems.append(
            f"{len(tracked_cruft)} build artifact(s) present ({tracked_cruft[:3]}). This "
            "repository is cloned onto every client machine")

    if args.json:
        print(json.dumps({"shippable": not problems, "problems": problems,
                          "notes": notes, "facts": facts}, indent=2))
    else:
        print(f"DELIVERY: {'PASS' if not problems else 'FAIL'}")
        print(f"  SKILL.md          {size / 1024:.1f}KB of {args.budget_kb}KB budget")
        print(f"  entry points      {', '.join(wrappers) or '(none)'}")
        print(f"  packs registered  {len(on_disk)}: {', '.join(on_disk)}")
        print(f"  build artifacts   {len(tracked_cruft)}")
        for note in notes:
            print(f"  note: {note}")
        for problem in problems:
            print(f"  PROBLEM: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
