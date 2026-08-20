#!/usr/bin/env python3
"""Axiom audit — what does the checked result actually depend on.

A plain type-check will not surface a new or metaprogrammed axiom, so a green
build over a postulated bridge looks identical to a real establishment. This
enumerates the dependencies and compares them against the claim's allowlist.

With no toolchain this returns NOT_RUN, which is a gap — never a pass.

Usage:  axiom_audit.py <artifact.lean> --claim <claim.json> [--json]
Exit: 0 clean, 1 violation, 3 not run, 2 IO error.
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

# Accepted without comment: the standard foundational three.
DEFAULT_ALLOWLIST = {"propext", "Classical.choice", "Quot.sound"}
# Locally introduced postulates. Any of these makes the result conditional at best.
LOCAL_POSTULATE = re.compile(r"^\s*(axiom|constant)\s+(\w+)", re.MULTILINE)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact"); ap.add_argument("--claim", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        source = Path(a.artifact).read_text(encoding="utf-8")
        claim = json.loads(Path(a.claim).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    allow = set(claim.get("frozen_conditions", {}).get("axiom_allowlist", [])) | DEFAULT_ALLOWLIST
    local = [m.group(2) for m in LOCAL_POSTULATE.finditer(source)]
    problems = [f"the artifact postulates '{name}' locally — a postulated bridge is "
                "not an establishment" for name in local if name not in allow]

    depends: list[str] = []
    ran = False
    if shutil.which("lake") or shutil.which("lean"):
        decl = re.search(r"^\s*(?:theorem|lemma)\s+([\w.']+)", source, re.MULTILINE)
        if decl:
            probe = Path(a.artifact).with_suffix(".axioms.lean")
            try:
                probe.write_text(source + f"\n#print axioms {decl.group(1)}\n", encoding="utf-8")
                cmd = ([shutil.which("lake"), "env", "lean", str(probe)]
                       if shutil.which("lake") else [shutil.which("lean"), str(probe)])
                # Same reason as the kernel tier: `lake env` takes its search
                # path from the directory it runs in. Run from the artifact's
                # own directory and every import fails, so `#print axioms`
                # never executes and the gate reports NOT_RUN — a gap where a
                # clean audit was available the whole time.
                project = os.environ.get("WITSOC2_LEAN_PROJECT")
                workdir = (project if project and Path(project).is_dir()
                           else str(Path(a.artifact).parent))
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                                      cwd=workdir)
                out = proc.stdout + proc.stderr
                m = re.search(r"depends on axioms:\s*\[([^\]]*)\]", out)
                if m:
                    ran = True
                    depends = [x.strip() for x in m.group(1).split(",") if x.strip()]
                    problems += [f"depends on '{ax}', which is not in the allowlist"
                                 for ax in depends if ax not in allow]
                elif "does not depend on any axioms" in out:
                    ran, depends = True, []
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                probe.unlink(missing_ok=True)

    if not ran and not local:
        out = {"verdict": "NOT_RUN", "problems": [],
               "why": "no toolchain could enumerate the axiom dependencies. That is a "
                      "gap, not a pass: an unaudited result may rest on a postulate."}
        print(json.dumps(out, indent=2) if a.json else
              f"AXIOM AUDIT: NOT_RUN\n  {out['why']}")
        return 3
    verdict = "FAIL" if problems else "PASS"
    out = {"verdict": verdict, "depends_on": depends, "locally_postulated": local,
           "allowlist": sorted(allow), "problems": problems}
    if a.json: print(json.dumps(out, indent=2))
    else:
        print(f"AXIOM AUDIT: {verdict}")
        if depends: print(f"  depends on: {depends}")
        for p in problems: print(f"  {p}")
    return 1 if problems else 0
if __name__ == "__main__":
    sys.exit(main())
