#!/usr/bin/env python3
"""Doctrine must be runnable, and machinery must be reachable.

Two failures this catches, both found by hand in an audit and neither detectable
by any check that existed:

**A dead instruction.** The maths Generator doctrine opened its check loop with
"LSP/REPL per-command checking — use it by default." The pack had measured that
REPL, found it returned success-shaped JSON against an empty environment, and
rejected it in writing. Three documents advertised it anyway. Nothing was wrong
with the prose; the world had moved and the prose had not. A role reading it
would have defaulted to a backend the pack knew was unsafe.

**Orphaned machinery.** The maths pack holds thirty scripts. Its three role
doctrines named exactly one of them, so a Researcher told to "search, minimize,
certify a counterexample" had no pointer to `counterexample.py`, and the honest
reading of the doctrine was that no such tool existed.

So, per pack:

  COMMANDS   every command in a doctrine fence names a file that exists and
             answers `--help` with exit 0. A command nobody can run is a
             decoration, and it decays silently because nothing executes it.

  COVERAGE   every entry-point script is reachable from either the manifest or
             some doctrine file. A script the manifest wires in is reachable by
             the adapter; a script only a role would invoke has to be named
             where that role will read it. Anything else is declared dead in
             `domain.json` under `internal_scripts`, which is a claim someone
             has to write down rather than a silence.

Conservative on purpose: only fenced lines beginning `python3` or `bash` count,
and only paths under `scripts/`. An earlier link checker in this frame produced
seventeen false positives by reading prose, and a checker people learn to ignore
is worse than none.

Usage:  check_doctrine_commands.py [--domain <name>] [--commands-only] [--json]
Exit:   0 clean, 1 problems, 2 IO
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DOMAINS = ROOT / "domains"

# The reach of the flag check, stated rather than implied: --help shows the
# TOP-LEVEL parser, so a flag belonging to a subcommand will not appear there.
# Listing the exceptions keeps the check honest about what it does not see.
GENERIC_FLAGS = {"help"}

FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
COMMAND = re.compile(r"^\s*(?:python3|bash)\s+(\S+)", re.MULTILINE)
# Any extension, not a list of them: enumerating extensions puts a field's file
# types in a frame file, and the purity checker is right to refuse that. It also
# means a pack introducing a new artifact kind needs no change here.
SCRIPT_REF = re.compile(r"(?:scripts|playbooks|tiers|gates)/[\w/]+\.\w{1,6}")
ENTRY_POINT = re.compile(r"argparse\.ArgumentParser")



def rule_path(entry) -> str:
    """A doctrine rule is a path or an object carrying one."""
    return entry if isinstance(entry, str) else (entry or {}).get("path", "")

def doctrine_files(pack: Path, manifest: dict) -> list[Path]:
    doctrine = manifest.get("doctrine") or {}
    names = (list((doctrine.get("roles") or {}).values())
             + [rule_path(r) for r in doctrine.get("rules") or []])
    files = [pack / n for n in names]
    files += sorted(pack.glob("playbooks/*.md"))
    readme = pack / "README.md"
    if readme.exists():
        files.append(readme)
    return [f for f in files if f.exists()]


def manifest_text(pack: Path, manifest: dict) -> str:
    records = [manifest]
    for name in ("capabilities.json", "operators.json"):
        path = pack / name
        if path.is_file():
            records.append(json.loads(path.read_text(encoding="utf-8")))
    return json.dumps(records)


def line_tokens(block: str, rel: str) -> list[str]:
    """Tokens following the script path on the line that invokes it."""
    for line in block.splitlines():
        if rel in line:
            after = line.split(rel, 1)[1].split()
            return after
    return []


def check_commands(pack: Path, files: list[Path], timeout: int) -> list[str]:
    """Every command LINE, not every script.

    Checking once per script was wrong twice over: a doctrine block usually
    carries several lines for the same tool — `counterexample.py families`,
    `... certify`, `... inflate` — and each has its own subcommand and its own
    flags. Collapsing them checked one line's flags against another line's
    parser and reported eighty-eight failures, nearly all of them the check
    misreading itself. A check that cries wolf on its first real run gets
    switched off, which is worse than not having written it.
    """
    problems: list[str] = []
    usage_cache: dict[tuple[str, str], str] = {}

    def usage_for(script: Path, sub: str | None) -> str | None:
        key = (str(script), sub or "")
        if key in usage_cache:
            return usage_cache[key]
        cmd = [sys.executable, str(script)] + ([sub] if sub else []) + ["--help"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  cwd=str(pack))
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        usage_cache[key] = proc.stdout + proc.stderr
        return usage_cache[key]

    for path in files:
        text = path.read_text(encoding="utf-8")
        where_file = path.relative_to(pack.parent.parent)
        for block in FENCE.findall(text):
            for line in block.splitlines():
                match = COMMAND.match(line)
                if not match:
                    continue
                target = match.group(1).strip('"\'')
                if not target.startswith(("scripts/", "./scripts/")):
                    continue
                rel = target.lstrip("./")
                script = pack / rel
                where = f"{where_file}: {rel}"
                if not script.exists():
                    problems.append(f"{where} — no such file. The doctrine tells a role to run "
                                    "something that is not there")
                    continue
                if script.suffix != ".py":
                    continue

                tokens = line.split(rel, 1)[1].split()
                sub = next((tok for tok in tokens if not tok.startswith("-")), None)
                top = usage_for(script, None)
                if top is None:
                    problems.append(f"{where} — `--help` did not exit 0; the frame cannot even "
                                    "ask this script what it accepts")
                    continue

                usage = top
                # A subcommand advertises its own flags and the top level shows
                # none of them, so ask the subcommand when the top level names
                # one. `sub` is only treated as a subcommand if it appears in
                # the parser's own choice list — otherwise it is a positional
                # argument and the top-level usage is the right thing to read.
                if sub and re.search(rf"\{{[^}}]*\b{re.escape(sub)}\b[^}}]*\}}", usage):
                    deeper = usage_for(script, sub)
                    if deeper:
                        usage = deeper

                for flag in sorted({f for f in re.findall(r"(?<!\w)--([a-z][\w-]*)", line)}):
                    if flag in GENERIC_FLAGS or f"--{flag}" in usage:
                        continue
                    problems.append(
                        f"{where}{' ' + sub if sub else ''} — the doctrine passes `--{flag}`, "
                        "which this command does not accept. The file exists and answers "
                        "--help, and the instruction is still wrong")
    return problems


def check_coverage(pack: Path, files: list[Path], manifest: dict) -> tuple[list[str], dict]:
    named: set[str] = set()
    for path in files:
        for ref in SCRIPT_REF.findall(path.read_text(encoding="utf-8")):
            named.add(ref)
    wired = set(SCRIPT_REF.findall(manifest_text(pack, manifest)))
    declared = set(manifest.get("internal_scripts") or [])

    # Gates and tiers declare their implementing script in the manifest, so this
    # reads paths and nothing else. The first version guessed the binding from
    # naming conventions and got three of six wrong in the maths pack, because
    # `fidelity-review` lives in `fidelity.py` and no rule connects those. The
    # fix was not a better heuristic: it was making the manifest say which file
    # implements each gate, which the packs had left to a dict inside check.py.

    entry_points = []
    for script in sorted(pack.glob("scripts/**/*.py")):
        if "__pycache__" in script.parts or script.name.startswith("_"):
            continue
        if ENTRY_POINT.search(script.read_text(encoding="utf-8")):
            entry_points.append(str(script.relative_to(pack)))

    orphans = [s for s in entry_points
               if s not in named and s not in wired and s not in declared]
    stale = [s for s in declared if s not in entry_points]
    problems = []
    for s in orphans:
        problems.append(f"{pack.name}: {s} is an entry point no doctrine names and no manifest "
                        "wires in. A role that needs it has no way to learn it exists — name it "
                        "where the role will read it, or declare it in internal_scripts")
    for s in stale:
        problems.append(f"{pack.name}: internal_scripts declares {s}, which is not an entry "
                        "point here. A stale declaration hides a real orphan behind it")
    return problems, {"entry_points": len(entry_points), "named_in_doctrine": len(named & set(entry_points)),
                      "wired_in_manifest": len(wired & set(entry_points)),
                      "declared_internal": len(declared), "orphans": orphans}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", help="check one pack instead of all")
    ap.add_argument("--commands-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not DOMAINS.exists():
        print(f"ERROR: {DOMAINS} not found", file=sys.stderr)
        return 2
    packs = ([DOMAINS / args.domain] if args.domain
             else sorted(p for p in DOMAINS.iterdir() if (p / "domain.json").exists()))

    report, failures = {}, 0
    for pack in packs:
        manifest_path = pack / "domain.json"
        if not manifest_path.exists():
            print(f"ERROR: {manifest_path} not found", file=sys.stderr)
            return 2
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = doctrine_files(pack, manifest)
        problems = check_commands(pack, files, args.timeout)
        stats: dict = {}
        if not args.commands_only:
            cover, stats = check_coverage(pack, files, manifest)
            problems += cover
        report[pack.name] = {"doctrine_files": len(files), "problems": problems, **stats}
        failures += len(problems)

    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if failures else 0

    for name, entry in report.items():
        mark = "ok  " if not entry["problems"] else "FAIL"
        print(f"  [{mark}] {name:<10} {entry['doctrine_files']} doctrine file(s), "
              f"{entry.get('entry_points', 0)} entry point(s), "
              f"{len(entry['problems'])} problem(s)")
        for problem in entry["problems"]:
            print(f"          {problem}")
    print()
    print(f"  {'PASS' if not failures else 'FAIL'} — {failures} problem(s) across {len(report)} pack(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
