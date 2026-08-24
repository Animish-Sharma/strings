#!/usr/bin/env python3
"""The journey — one claim, the whole path, nothing pre-fitted.

Every check in this tree tested a COMPONENT. The adapter self-test asked whether
the adapter refuses bad input; the role evals asked whether a decision is right;
the bridge suite asked whether the frame can call a pack. All green, all useful,
and none of them ever took a claim from a sentence to a status.

So when this pack was pointed at modus ponens — the simplest theorem there is —
six defects surfaced in a row, each of which had been sitting behind that green
suite:

  1. a labelled GIVEN hypothesis could not be cited, because the reference
     artifact declares one and never cites it;
  2. kernel availability meant "Mathlib is built", so a target citing nothing
     was refused the tier it needed and the run silently under-claimed;
  3. an `incomplete` receipt was recorded as FAILED_ATTEMPT and fed to the
     escalation ladder — a deep-attack role dispatched at a proof the kernel
     had already accepted;
  4. a doctrine command passed a flag its script does not take;
  5. fifteen more of those, once anything checked flags at all;
  6. three fields of a kernel receipt keyed off the aggregate verdict rather
     than their own evidence, so a receipt whose refutation had SURVIVED
     reported it as broken.

None of these is exotic. Each was on the shortest path through the system, and
the shortest path had never been walked. That is what this file is for, and the
fixture is deliberately trivial: a journey test whose subject is hard tells you
about the subject, and this one has to tell you about the road.

Both directions, as everywhere else here. The correct proof must reach the
kernel; the wrong one — `hP` where `hPQ hP` belongs — must be refused by it.

Usage:  run_journey.py [--json]
Exit:   0 the journey behaved as specified, 1 it did not, 2 IO
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent.parent
FRAME = PACK.parent.parent

CLAIM = HERE / "modus_ponens_claim.json"
WIT = HERE / "modus_ponens.wit"
LEAN = HERE / "modus_ponens.lean"
WRONG = HERE / "modus_ponens_wrong.lean"


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=str(PACK))
        return proc.returncode, (proc.stdout + proc.stderr)
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, str(exc)


def receipt_of(output: str) -> dict:
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cases: list[dict] = []

    def record(label: str, ok: bool, detail: str, why: str) -> None:
        cases.append({"step": label, "ok": ok, "detail": detail[:160], "why": why})

    # 1. resolution — the statement must reach this pack from its own words.
    code, out = run([sys.executable, str(FRAME / "scripts" / "resolve_domain.py"),
                     "--statement", json.loads(CLAIM.read_text())["exact_statement"], "--json"])
    decision = receipt_of(out)
    record("resolve", decision.get("decision") == "SELECTED" and decision.get("domain") == "maths",
           f"{decision.get('decision')} -> {decision.get('domain')}",
           "a pack that is never loaded is indistinguishable from one nobody wrote")

    # 2. falsification — the bounded tier over the claim's frozen truth table.
    code, out = run([sys.executable, "scripts/tiers/bounded.py", "--claim", str(CLAIM), "--json"])
    bounded = receipt_of(out)
    record("falsify", bounded.get("verdict") == "pass" and bounded.get("exhaustive") is True,
           f"{bounded.get('verdict')}, exhaustive={bounded.get('exhaustive')}, "
           f"{bounded.get('checked')} instance(s)",
           "Explorer refutes before committing; an exhaustive small search is the cheapest "
           "way to learn the claim is false")

    # 3. structural — the WIT artifact, including a cited hypothesis.
    code, out = run([sys.executable, "scripts/check.py", "--artifact", str(WIT),
                     "--claim", str(CLAIM), "--tier", "structural", "--json"])
    structural = receipt_of(out)
    record("structural", structural.get("verdict") == "pass",
           f"{structural.get('verdict')}; {structural.get('log_excerpt', '')[:80]}",
           "the proof cites [hPQ] and [hP] — a labelled hypothesis must be citable, which it "
           "was not until a real proof tried")

    # 4. kernel — available, made available, or honestly absent.
    #
    # The journey used to SKIP its three kernel assertions whenever no project
    # was configured, which is most machines — so the most expensive tier in the
    # pack was the least walked, and the defects that surfaced there surfaced by
    # hand. The scaffold builds the environment `lake env` needs in a temporary
    # directory, which costs a few seconds and buys the steps back. It gives an
    # environment and not a library; a target citing nothing needs exactly that.
    def kernel_available(extra_env: dict | None = None) -> bool:
        code, out = run([sys.executable, "scripts/availability.py", "--tier", "kernel",
                         "--claim", str(CLAIM), "--json"], timeout=60)
        return receipt_of(out).get("kernel", {}).get("available") is True

    available = kernel_available()
    scaffolded = None
    if not available:
        scaffold_dir = Path(tempfile.mkdtemp(prefix="journey_lean_"))
        code, out = run([sys.executable, "scripts/scaffold_lean.py",
                         "--out", str(scaffold_dir), "--json"], timeout=300)
        payload = receipt_of(out)
        if payload.get("status") in {"built", "already_built"}:
            os.environ["WITSOC2_LEAN_PROJECT"] = payload["project"]
            lean = payload.get("lean")
            if lean:
                os.environ["PATH"] = f"{Path(lean).parent}:{os.environ['PATH']}"
            scaffolded = payload["project"]
            available = kernel_available()
        record("scaffold", True,
               f"{payload.get('status', 'unavailable')}"
               + (f" at {scaffolded}" if scaffolded else ""),
               "a check that skips the expensive tier whenever it is inconvenient leaves the "
               "tier untested on most machines; building the environment costs seconds")
    if available:
        code, out = run([sys.executable, "scripts/check.py", "--artifact", str(LEAN),
                         "--claim", str(CLAIM), "--tier", "kernel", "--json"])
        kernel = receipt_of(out)
        record("kernel", kernel.get("refute_attempt", {}).get("outcome") == "survived",
               f"verdict {kernel.get('verdict')}, refutation "
               f"{kernel.get('refute_attempt', {}).get('outcome')}, "
               f"axioms {str(kernel.get('axiom_audit'))[:30]}",
               "the theorem must ELABORATE, and the receipt must say the refutation survived "
               "rather than keying that field off the aggregate verdict")
        record("kernel gap named",
               kernel.get("verdict") == "incomplete" and "fidelity-review" in (kernel.get("gaps") or []),
               f"verdict {kernel.get('verdict')}, gaps {kernel.get('gaps')}",
               "with no independent judge the run cannot self-certify fidelity, and the "
               "missing check is named rather than folded into a failure")

        code, out = run([sys.executable, "scripts/check.py", "--artifact", str(WRONG),
                         "--claim", str(CLAIM), "--tier", "kernel", "--json"])
        broken = receipt_of(out)
        record("kernel refuses a wrong proof",
               broken.get("verdict") == "fail"
               and broken.get("refute_attempt", {}).get("outcome") == "broken",
               f"verdict {broken.get('verdict')}, refutation "
               f"{broken.get('refute_attempt', {}).get('outcome')}",
               "a tier nothing has ever failed is unaudited, not trustworthy")
    else:
        record("kernel", True, "NOT_RUN — no usable toolchain here",
               "an absent backend is a gap in this journey's coverage and an honest ceiling, "
               "never a pass; the rest of the path is still walked")

    # 5. the loop — the campaign driver, end to end.
    code, out = run([sys.executable, str(FRAME / "scripts" / "campaign.py"), "run",
                     "--claim", str(CLAIM), "--artifact", str(LEAN if available else WIT),
                     "--tier", "kernel" if available else "structural",
                     "--domain", "maths", "--json"], timeout=300)
    report = receipt_of(out)
    outcome = report.get("outcome")
    expected = "INCOMPLETE" if available else None
    record("campaign", outcome == expected if expected else outcome is not None,
           f"outcome {outcome}, missing {report.get('missing_checks')}",
           "an incomplete run is a GAP: recording it as FAILED_ATTEMPT states the route was "
           "shown not to work and escalates a deep-attack role at a proof that elaborated")

    failures = [c for c in cases if not c["ok"]]
    if args.json:
        print(json.dumps({"cases": cases, "failures": len(failures)}, indent=2))
        return 1 if failures else 0

    print("\n  JOURNEY — one claim, the whole path\n")
    for case in cases:
        print(f"  {'ok  ' if case['ok'] else 'FAIL'}  {case['step']:<28} {case['detail']}")
        print(f"          {case['why'][:120]}")
    print("\n" + "=" * 70)
    print(f"  {'PASS' if not failures else 'FAIL'} — {len(cases) - len(failures)}/{len(cases)} "
          "steps behaved as specified")
    if not available:
        print("  the kernel steps were NOT walked here: no usable toolchain. That is coverage "
              "this run does not have, and saying so beats reporting green over it.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
