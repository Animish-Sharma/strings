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


VERSION_TIMEOUT = int(os.environ.get("WITSOC2_VERSION_TIMEOUT", "5"))


def probe_kernel(requires_library: bool = True) -> dict:
    lake = find_lean()
    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    if not lake:
        return {"available": False,
                "detail": "no Lean found (checked WITSOC2_LEAN, ~/.elan/bin, PATH) — "
                          "the kernel tier cannot run, so this run's ceiling is "
                          "CHECKED_BOUNDED",
                "ceiling_without_it": "CHECKED_BOUNDED"}
    # A version query does no work. Anything but an immediate answer means the
    # thing being probed is what is hanging — a launcher resolving a toolchain
    # over the network, most often — and waiting a minute to learn that is the
    # exact cost a probe exists to avoid. Sixty seconds was the old bound, and
    # the honest answer it eventually printed was worth about a second.
    try:
        out = subprocess.run([lake, "--version"], capture_output=True, text=True,
                             timeout=VERSION_TIMEOUT, cwd=project or None)
        version = (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return {"available": False,
                "detail": f"{lake} did not report a version within {VERSION_TIMEOUT}s. A "
                          "version query does no work, so something it depends on is hanging — "
                          "commonly a launcher resolving a toolchain over the network. Point "
                          "WITSOC2_LEAN at a toolchain binary directly to skip it.",
                "ceiling_without_it": "CHECKED_BOUNDED"}
    except (OSError, subprocess.SubprocessError, IndexError):
        version = None
    if not version:
        return {"available": False, "detail": f"{lake} present but did not report a version",
                "ceiling_without_it": "CHECKED_BOUNDED"}
    result = {"available": True, "detail": version, "toolchain": version, "lean": lake}
    if project:
        lib = Path(project) / ".lake" / "build" / "lib" / "lean"
        mathlib = lib / "Mathlib"
        # Directory presence is not availability. A partially built checkout has
        # the directory and is missing most of what anyone will import, and a
        # tier that reports available on that basis sends a run to spend its
        # expensive budget discovering a build problem. Count the compiled
        # modules and say the number.
        built = list(mathlib.rglob("*.olean")) if mathlib.exists() else []
        any_built = list(lib.rglob("*.olean")) if lib.exists() else []
        result["mathlib_built"] = bool(built)
        result["mathlib_modules"] = len(built)
        result["compiled_modules"] = len(any_built)
        result["project"] = project
        toolchain_file = Path(project) / "lean-toolchain"
        if toolchain_file.is_file():
            result["project_toolchain"] = toolchain_file.read_text(encoding="utf-8").strip()

        # "The kernel is usable" and "Mathlib is built" are DIFFERENT questions,
        # and this probe used to answer only the second. A target whose
        # allowed_external_facts is empty needs the kernel and does not need the
        # library — and refusing it understates what the run could establish,
        # which is the same class of error as overstating, pointing the other
        # way. The Mathlib count stays, as a ceiling on what may be IMPORTED.
        needs_mathlib = requires_library
        if not any_built:
            result["available"] = False
            result["detail"] += ("  (project set and nothing compiled under it — no library is "
                                 "usable, whatever the directory listing suggests)")
            result["ceiling_without_it"] = "CHECKED_BOUNDED"
        elif needs_mathlib and not built:
            result["available"] = False
            result["detail"] += (f"  ({len(any_built)} module(s) compiled and no Mathlib among "
                                 "them; this claim cites external results, so the library is "
                                 "required)")
            result["ceiling_without_it"] = "CHECKED_BOUNDED"
        else:
            result["detail"] += (f"  ({len(any_built)} compiled module(s) at {project}"
                                 + (f", {len(built)} of them Mathlib" if built else
                                    "; no Mathlib, and this claim cites nothing that needs it")
                                 + ")")
    else:
        # No project means no usable environment, not merely no library. The
        # tier runs `lake env lean`, and `lake env` takes its search path from
        # the directory it is invoked in — outside a project there is nothing to
        # take, and lake sits trying to resolve one. Reporting `available` here
        # sent a run into a thirty-minute block that ended in a toolchain error,
        # which is the most expensive possible way to learn a configuration fact
        # a probe can state in milliseconds.
        result["available"] = False
        result["ceiling_without_it"] = "CHECKED_BOUNDED"
        result["detail"] += ("  (no WITSOC2_LEAN_PROJECT — `lake env` has no environment to "
                             "take a search path from, so the tier cannot run at all. Build one: "
                             "`eval \"$(python3 scripts/scaffold_lean.py --print-export)\"`. It "
                             "gives an environment, not a library, which is enough for a target "
                             "citing nothing.)")
    return result

PROBES = {"structural": probe_structural, "kernel": probe_kernel, "bounded": probe_bounded}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tier", choices=sorted(PROBES))
    ap.add_argument("--claim", help="the frozen claim. Its allowed_external_facts decide "
                    "whether the kernel tier needs a library at all — a target that cites "
                    "nothing needs the kernel and not Mathlib, and refusing it understates "
                    "what the run could establish")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tiers = [a.tier] if a.tier else sorted(PROBES)

    requires_library = True
    if a.claim:
        try:
            claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
            requires_library = bool(claim.get("allowed_external_facts"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: claim unreadable — {exc}", file=sys.stderr)
            return 2

    results = {}
    for name in tiers:
        probe = PROBES[name]
        results[name] = (probe(requires_library) if name == "kernel" else probe())
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
