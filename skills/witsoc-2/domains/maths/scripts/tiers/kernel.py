#!/usr/bin/env python3
"""Kernel tier — Lean elaboration against Mathlib.

The adversarial tier: a candidate either elaborates or it does not, and no
argument changes that. Its verdict is only worth anything alongside the
placeholder scan and the axiom audit, because a placeholder makes anything
elaborate and an unaudited axiom makes anything derivable.

Feedback order, cheapest first — a full `lake build` never belongs in a repair
loop:
  1. per-command LSP/REPL check (when a server is configured)
  2. `lake env lean <file>`   <- default here
  3. `lake build`             <- final confirmation only

Usage:  kernel.py <artifact.lean> [--full-build] [--json]
Exit:   0 pass, 1 fail, 3 toolchain unavailable, 2 IO error.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

# Diagnostic -> failure class. Patterns are matched against the diagnostic BODY
# with the "file.lean:LINE:COL:" prefix stripped first — otherwise a file named
# coercion.lean makes every error in it look like a coercion issue, which is
# exactly the false pass this table had before it was tested against real output.
CLASSES = [
    (r"unknown identifier|unknown constant", "unknown_identifier"),
    # Observed wording in Lean 4.31/4.33: "unknown module prefix 'X'", and —
    # when the project IS on the search path but that module was never built —
    # "object file '...olean' of module X does not exist". The second was
    # classified as unsolved_goal until a real partial Mathlib produced it,
    # which sent a build problem to the role that repairs mathematics.
    (r"unknown module prefix|unknown package|could not find module|"
     r"object file .* of module .* does not exist|"
     r"no directory .* or file .* in the search path", "import_missing"),
    (r"failed to synthesize", "coercion_issue"),
    # A definitional-equality failure showing a coercion arrow IS a coercion
    # problem; without the arrow it is a plain type or unfolding problem.
    (r"not definitionally equal[\s\S]*↑|↑[\s\S]*not definitionally equal", "coercion_issue"),
    (r"\bcoercion\b", "coercion_issue"),
    (r"type mismatch", "type_mismatch"),
    (r"function expected|application type mismatch", "type_mismatch"),
    (r"not definitionally equal", "type_mismatch"),
    (r"unsolved goals", "unsolved_goal"),
    (r"maximum recursion|deep recursion|deterministic.{0,3}timeout", "computational_obstruction"),
]
# Strips "path/to/File.lean:12:34:" so a filename can never drive classification.
RE_LOCATION = re.compile(r"^\s*\S*?\.lean:\d+:\d+:\s*", re.MULTILINE)


def body(diagnostic: str) -> str:
    return RE_LOCATION.sub("", diagnostic or "")


# Lean 4 tags errors with a stable machine code, e.g. error(lean.unknownIdentifier).
# Prefer it: prose wording changes between releases, the code does not.
ERROR_CODES = {
    "unknownIdentifier": "unknown_identifier",
    "unknownConstant": "unknown_identifier",
    "typeMismatch": "type_mismatch",
    "unsolvedGoals": "unsolved_goal",
    "functionExpected": "type_mismatch",
    "deterministicTimeout": "computational_obstruction",
}
RE_ERROR_CODE = re.compile(r"error\(lean\.(\w+)\)")


def classify(diagnostic: str) -> str:
    code = RE_ERROR_CODE.search(diagnostic or "")
    if code and code.group(1) in ERROR_CODES:
        return ERROR_CODES[code.group(1)]
    text = body(diagnostic)
    for pattern, cls in CLASSES:
        if re.search(pattern, text, re.IGNORECASE):
            return cls
    return "unsolved_goal"

def signature(diagnostic: str) -> str:
    """(class, normalized first diagnostic line) — positions and metavariable
    numbers stripped, so the same failure twice looks the same."""
    first = next((l for l in body(diagnostic).splitlines() if l.strip()), "")
    first = re.sub(r"\d+:\d+", "L:C", first)
    first = re.sub(r"[?]m\.\d+|\bm\.\d+", "?m", first)
    first = re.sub(r"\.\d+\b", "", first)
    return f"{classify(diagnostic)}|{' '.join(first.split())[:120]}"

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact")
    ap.add_argument("--full-build", action="store_true",
                    help="final confirmation only; never inside a repair loop")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    path = Path(a.artifact)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    lake = shutil.which("lake")
    lean = shutil.which("lean")
    if not (lake or lean):
        result = {"verdict": "not_run", "failure_class": "toolchain_unavailable",
                  "detail": "no `lake` or `lean` on PATH",
                  "note": "A check that could not run is a gap, never a pass, and "
                          "never support for the claim."}
        print(json.dumps(result, indent=2) if a.json else
              f"KERNEL: NOT RUN — {result['detail']}\n  {result['note']}")
        return 3

    # `lake env` sets LEAN_PATH from the project it is run IN. Running it from
    # the artifact's own directory therefore elaborates against the ambient
    # toolchain with an empty search path — which is why availability could
    # report the library present while every import of it failed. A tier that
    # says available and then cannot import is worse than one that says
    # unavailable, because the run has already committed by the time it finds out.
    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    workdir = project if project and Path(project).is_dir() else str(path.parent)

    cmd = ([lake, "build"] if (a.full_build and lake)
           else ([lake, "env", "lean", str(path)] if lake else [lean, str(path)]))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                              cwd=workdir)
    except subprocess.TimeoutExpired:
        print("KERNEL: FAIL — timed out"); return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2

    diagnostic = (proc.stdout + proc.stderr).strip()
    passed = proc.returncode == 0
    result = {
        "verdict": "pass" if passed else "fail",
        "command": " ".join(cmd),
        "artifact_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "log_excerpt": diagnostic[:2000],
    }
    if not passed:
        result["failure_class"] = classify(diagnostic)
        result["failure_signature"] = signature(diagnostic)

    if a.json:
        print(json.dumps(result, indent=2))
    elif passed:
        print("KERNEL: PASS — elaborated")
        print("  Necessary, not sufficient: run the placeholder scan, the axiom")
        print("  audit, and the fidelity review before claiming any status.")
    else:
        print(f"KERNEL: FAIL — {result['failure_class']}")
        print(f"  signature: {result['failure_signature']}")
        print(f"  {diagnostic.splitlines()[0][:160] if diagnostic else ''}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
