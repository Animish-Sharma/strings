#!/usr/bin/env python3
"""Toolchain availability probe.

Run before spending against a tier, so a run states its honest ceiling up front
instead of discovering after the budget is gone that the backend it needed was
never there.

An unavailable tier is a precondition gap. It is never evidence, and never a
reason to narrate what a successful run would have produced.

Usage:  availability.py [--tier structural|kernel|bounded] [--json]
Exit:   0 available, 3 unavailable, 2 usage error.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

def probe_structural() -> dict:
    return {"available": True, "detail": "pure-Python parser; no external toolchain"}

def probe_bounded() -> dict:
    return {"available": True, "detail": "pure-Python search harness; no external toolchain"}

def find_lean() -> str | None:
    """elan installs proxies that need a toolchain context, and a bare `lake` on
    PATH may be an elan shim that reports nothing useful outside a project. Look
    for a real binary before falling back to PATH."""
    for candidate in (os.environ.get("WITSOC2_LEAN"),
                      str(Path.home() / ".elan" / "bin" / "lean")):
        if candidate and Path(candidate).exists():
            return candidate
    return shutil.which("lean") or shutil.which("lake")


def probe_kernel() -> dict:
    lake = find_lean()
    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not lake:
        return {"available": False,
                "detail": "no Lean found (checked WITSOC2_LEAN, ~/.elan/bin, PATH) — "
                          "the kernel tier cannot run, so this run's ceiling is "
                          "CHECKED_BOUNDED",
                "ceiling_without_it": "CHECKED_BOUNDED"}
    try:
        out = subprocess.run([lake, "--version"], capture_output=True, text=True,
                             timeout=60, cwd=project or None)
        version = (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, IndexError):
        version = None
    if not version:
        return {"available": False, "detail": f"{lake} present but did not report a version",
                "ceiling_without_it": "CHECKED_BOUNDED"}
    result = {"available": True, "detail": version, "toolchain": version, "lean": lake}
    if project:
        mathlib = Path(project) / ".lake" / "build" / "lib" / "lean" / "Mathlib"
        # Directory presence is not availability. A partially built checkout has
        # the directory and is missing most of what anyone will import, and a
        # tier that reports available on that basis sends a run to spend its
        # expensive budget discovering a build problem. Count the compiled
        # modules and say the number.
        built = list(mathlib.rglob("*.olean")) if mathlib.exists() else []
        result["mathlib_built"] = bool(built)
        result["mathlib_modules"] = len(built)
        result["project"] = project
        toolchain_file = Path(project) / "lean-toolchain"
        if toolchain_file.is_file():
            result["project_toolchain"] = toolchain_file.read_text(encoding="utf-8").strip()
        if not built:
            result["available"] = False
            result["detail"] += ("  (project set and no compiled modules under it — the library "
                                 "is not usable, whatever the directory listing suggests)")
            result["ceiling_without_it"] = "CHECKED_BOUNDED"
        else:
            result["detail"] += f"  ({len(built)} compiled module(s) at {project})"
    else:
        result["detail"] += "  (no WITSOC2_LEAN_PROJECT; Mathlib imports unavailable)"
    return result

PROBES = {"structural": probe_structural, "kernel": probe_kernel, "bounded": probe_bounded}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tier", choices=sorted(PROBES))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tiers = [a.tier] if a.tier else sorted(PROBES)
    results = {t: PROBES[t]() for t in tiers}
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for name, r in results.items():
            mark = "available" if r["available"] else "UNAVAILABLE"
            print(f"  {name:<12} {mark:<12} {r['detail']}")
        ceilings = [r.get("ceiling_without_it") for r in results.values() if not r["available"]]
        if ceilings:
            print(f"\nHonest ceiling for this run: {sorted(set(ceilings))[0]}")
    return 0 if all(r["available"] for r in results.values()) else 3

if __name__ == "__main__":
    sys.exit(main())
