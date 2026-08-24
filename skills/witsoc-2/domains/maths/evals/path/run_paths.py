#!/usr/bin/env python3
"""Pack-owned path checks — the loops only this pack can walk.

`scripts/check_paths.py` walks the generic path: frozen claim in, admission
decision out, declared in `cases.json` and run by the frame. Two of this pack's
seams are not that shape. They are procedures over the production pipeline, and
the frame is not allowed to know that this pack has one.

  * a blueprint whose TARGET SIGNATURE is unfilled must never reach the backend.
    The renderer counted step obligations and not the signature, so a blueprint
    carrying a `FILL-ME` produced a file whose theorem line was that sentence and
    handed it to the kernel. It failed as a parse error, which is luck.

  * the repair loop has to complete: a failure, then a refusal of the UNCHANGED
    retry, then acceptance of the revision — all in one workdir. Each of those
    three was blocked by the next until the seams were fixed, so testing them
    separately proves nothing about the loop the doctrine describes.

Usage:  run_paths.py [--json]
Exit:   0 every case that ran behaved as specified, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
PRODUCE = PACK / "scripts" / "produce.py"


def toolchain_ready() -> bool:
    project = os.environ.get("WITSOC2_LEAN_PROJECT")
    return bool(project and Path(project).is_dir() and shutil.which("lake"))


def outcome_of(text: str) -> str:
    for line in text.splitlines():
        if "OUTCOME:" in line:
            return line.split("OUTCOME:", 1)[1].strip().split()[0]
    return "NO_OUTCOME"


def produce(blueprint: Path, workdir: Path, env: dict | None = None) -> str:
    proc = subprocess.run(
        [sys.executable, str(PRODUCE), "--blueprint", str(blueprint),
         "--tier", "kernel", "--workdir", str(workdir)],
        capture_output=True, text=True, timeout=2400, env=env or os.environ.copy())
    return proc.stdout + proc.stderr


def placeholder_target_never_reaches_the_kernel(tmp: Path) -> tuple[str, str]:
    bp = json.loads((HERE / "even_prod_blueprint.json").read_text(encoding="utf-8"))
    bp["target_formalization"]["formal_statement"] = "FILL-ME: the Lean signature"
    path = tmp / "fillme.json"
    path.write_text(json.dumps(bp, ensure_ascii=False), encoding="utf-8")
    out = produce(path, tmp / "fill")
    if "kernel (attempt" in out:
        return "REACHED_KERNEL", "PRODUCED_INCOMPLETE"
    return outcome_of(out), "PRODUCED_INCOMPLETE"


def repair_loop_completes_in_one_workdir(tmp: Path) -> tuple[str, str]:
    good = json.loads((HERE / "even_prod_blueprint.json").read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(good))
    broken["lemma_plan"][1]["formalization"]["tactic"] = (
        "induction n with\n| zero => simp\n| succ k ih => exact step_1 k ih")
    path, work = tmp / "loop.json", tmp / "loop"
    env = dict(os.environ, WITSOC2_SOC_STORE=str(tmp / "soc"))

    path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    first = outcome_of(produce(path, work, env))
    second = outcome_of(produce(path, work, env))
    path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    third = outcome_of(produce(path, work, env))
    return (f"{first} -> {second} -> {third}",
            "NEEDS_BLUEPRINT_REVISION -> REPEAT_REFUSED -> CHECKED")


CASES = [
    ("a placeholder target never reaches the kernel",
     placeholder_target_never_reaches_the_kernel, False),
    ("the repair loop completes in one workdir",
     repair_loop_completes_in_one_workdir, True),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    have = toolchain_ready()
    rows, failures, ran = [], 0, 0
    for name, fn, needs_toolchain in CASES:
        if needs_toolchain and not have:
            rows.append({"case": name, "verdict": "NOT_RUN",
                         "why": "needs WITSOC2_LEAN_PROJECT and a toolchain"})
            print(f"  ---- {name:<46} NOT_RUN")
            continue
        with tempfile.TemporaryDirectory(prefix="mathspaths_") as td:
            got, want = fn(Path(td))
        ran += 1
        ok = got == want
        failures += not ok
        rows.append({"case": name, "verdict": "ok" if ok else "FAIL",
                     "got": got, "want": want})
        print(f"  {'ok  ' if ok else 'FAIL'} {name:<46} {got}"
              + ("" if ok else f"   (wanted {want})"))

    print()
    print(f"MATHS PATHS: {'FAIL' if failures else 'PASS'} — {ran} of {len(rows)} case(s) ran"
          + (f", {failures} behaved differently" if failures else
             ", none NOT_RUN counted as passing"))
    if a.json:
        print(json.dumps({"schema": "maths.paths.v1", "rows": rows}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
