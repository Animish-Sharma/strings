#!/usr/bin/env python3
"""Build the minimal Lean project the kernel tier needs, so a run does not have to.

The kernel tier runs `lake env lean`, and `lake env` takes its search path from
the directory it is invoked in. Outside a project there is nothing to take, so
the tier cannot run at all — the availability probe says so and tells the
operator to point `WITSOC2_LEAN_PROJECT` at a built project. That instruction is
correct and it was the last thing standing between a working toolchain and a
kernel pass: a three-line lakefile that everybody has to write for themselves is
a three-line lakefile that stops people.

## What this gives you, and what it does not

It gives you an ENVIRONMENT: a built project the kernel tier can elaborate
against. That is enough for any target whose `allowed_external_facts` is empty —
a statement about the logic's own primitives, which needs the kernel and not a
library.

It does **not** give you Mathlib, and it does not pretend to. A target citing
external results needs the library, the availability probe will still refuse the
tier without it, and building Mathlib is a different and much larger operation
than this. Saying so is the point: a scaffold that produced an environment and
let a run believe it had a library would be worse than no scaffold, because the
failure would arrive later and look like mathematics.

## Toolchain selection

It prefers an INSTALLED toolchain binary over the launcher on PATH. The launcher
resolves a toolchain name, which can mean a network round trip, and a version
query that needs the network is how a probe comes to take sixty seconds. The
generated `lean-toolchain` pins whatever was found, so `lake build` resolves
locally too.

Usage:
    scaffold_lean.py [--out <dir>] [--json] [--force]
    scaffold_lean.py --print-export      # just the line to eval

Exit: 0 built (or already present), 1 no usable toolchain, 2 the build failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_OUT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "witsoc2-lean"
VERSION_TIMEOUT = int(os.environ.get("WITSOC2_VERSION_TIMEOUT", "5"))
BUILD_TIMEOUT = int(os.environ.get("WITSOC2_SCAFFOLD_TIMEOUT", "300"))

LAKEFILE = """name = "witsoc2"
defaultTargets = ["Witsoc2"]

[[lean_lib]]
name = "Witsoc2"
"""

MODULE = """-- The one module this project needs to exist so that `lake env` has an
-- environment to hand the kernel tier. It imports nothing on purpose: this
-- scaffold provides a place to elaborate, never a library to cite.
def witsoc2Scaffold : Nat := 0
"""


def toolchain_name(path: Path) -> str:
    """`.../leanprover--lean4---v4.33.0/bin/lean` -> `leanprover/lean4:v4.33.0`."""
    for part in path.parts:
        if "--" in part:
            head, _, version = part.partition("---")
            return head.replace("--", "/") + ":" + version
    return ""


def responds(binary: Path) -> str | None:
    try:
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                             timeout=VERSION_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None


def find_toolchain() -> tuple[Path | None, str, str]:
    """An installed toolchain, preferred over the launcher, newest first.

    A launcher resolves a toolchain NAME, and resolution can reach the network.
    An installed binary answers immediately or is broken, which are the only two
    states a probe should have to distinguish.
    """
    explicit = os.environ.get("WITSOC2_LEAN")
    if explicit and Path(explicit).exists():
        version = responds(Path(explicit))
        if version:
            return Path(explicit), version, toolchain_name(Path(explicit))

    installed = sorted(Path.home().glob(".elan/toolchains/*/bin/lean"),
                       key=lambda p: [int(n) for n in re.findall(r"\d+", p.parts[-3])] or [0],
                       reverse=True)
    for candidate in installed:
        version = responds(candidate)
        if version:
            return candidate, version, toolchain_name(candidate)

    from shutil import which
    launcher = which("lean")
    if launcher:
        version = responds(Path(launcher))
        if version:
            return Path(launcher), version, ""
    return None, "", ""


def build(out: Path, lean: Path, pin: str) -> tuple[bool, str]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "lakefile.toml").write_text(LAKEFILE, encoding="utf-8")
    (out / "Witsoc2.lean").write_text(MODULE, encoding="utf-8")
    if pin:
        (out / "lean-toolchain").write_text(pin + "\n", encoding="utf-8")
    lake = lean.parent / "lake"
    if not lake.exists():
        return False, f"no lake beside {lean}; a toolchain without lake cannot build a project"
    try:
        proc = subprocess.run([str(lake), "build"], capture_output=True, text=True,
                              timeout=BUILD_TIMEOUT, cwd=str(out))
    except subprocess.TimeoutExpired:
        return False, (f"`lake build` did not finish in {BUILD_TIMEOUT}s. A project this small "
                       "builds in seconds, so something is resolving rather than compiling — "
                       "usually a toolchain name that is not installed locally")
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip().splitlines()[-1][:200]
    return True, (proc.stdout or "").strip().splitlines()[-1][:120] if proc.stdout else "built"


def compiled(out: Path) -> int:
    lib = out / ".lake" / "build" / "lib" / "lean"
    return len(list(lib.rglob("*.olean"))) if lib.exists() else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--force", action="store_true", help="rebuild even if one is already there")
    ap.add_argument("--print-export", action="store_true",
                    help="print only the export line, for eval")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()

    if not args.force and compiled(out):
        result = {"status": "already_built", "project": str(out),
                  "compiled_modules": compiled(out),
                  "reading": "a scaffold already stands here; --force rebuilds it"}
    else:
        lean, version, pin = find_toolchain()
        if lean is None:
            payload = {"status": "no_toolchain",
                       "reading": "no Lean answered a version query. The kernel tier cannot run "
                                  "here and this run's ceiling is CHECKED_BOUNDED — which is an "
                                  "honest result, not a failure to work around."}
            print(json.dumps(payload, indent=2) if args.json else f"NO TOOLCHAIN: {payload['reading']}",
                  file=sys.stderr)
            return 1
        ok, detail = build(out, lean, pin)
        if not ok:
            payload = {"status": "build_failed", "project": str(out), "toolchain": version,
                       "detail": detail}
            print(json.dumps(payload, indent=2) if args.json else f"BUILD FAILED: {detail}",
                  file=sys.stderr)
            return 2
        result = {"status": "built", "project": str(out), "toolchain": version,
                  "toolchain_pin": pin, "lean": str(lean),
                  "compiled_modules": compiled(out), "detail": detail,
                  "reading": "an environment for the kernel tier. NOT a library: a target "
                             "citing external results still needs Mathlib, and the "
                             "availability probe will still refuse the tier without it."}

    export = f'export WITSOC2_LEAN_PROJECT="{result["project"]}"'
    lean_bin = result.get("lean")
    if lean_bin:
        export = f'export PATH="{Path(lean_bin).parent}:$PATH"\n' + export
    result["export"] = export

    if args.print_export:
        print(export)
        return 0
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"LEAN SCAFFOLD: {result['status']} — {result['project']}")
    if result.get("toolchain"):
        print(f"  toolchain      {result['toolchain']}")
    print(f"  compiled       {result['compiled_modules']} module(s)")
    print(f"  {result['reading']}")
    print("\n  eval this, or run with --print-export:\n")
    for line in export.splitlines():
        print(f"    {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
