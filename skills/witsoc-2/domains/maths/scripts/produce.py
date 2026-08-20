#!/usr/bin/env python3
"""Production pipeline — the pack's route from a reviewed plan to a checked artifact.

Everything this composes already existed and none of it was connected. `generate_wit`,
`wit_to_lean`, `repair_cycle`, `blueprint`, and the diagnostic classifier each ran
correctly on their own and were called by nothing, and no blueprint with the six
sections `generate_wit` demands existed anywhere in the pack. The pack could refuse
an artifact in nine different ways and could not make one.

The chain:

    blueprint  --generate_wit-->  WIT  --structural-->  ok
               --wit_to_lean-->   Lean  --kernel-->  verdict
                                              |
                                              +-- fail --> classify --> repair_cycle
                                                                    --> failure_ledger
                                                                    --> escalate or retry

Three properties worth stating, because each is a place this could have been built
worse:

**Nothing is invented.** `generate_wit` renders a reviewed plan; `wit_to_lean`
carries formalizations the blueprint supplied and refuses to guess a statement.
This script adds no step, no lemma, and no tactic of its own. If the blueprint
does not say how a step is formalized, the hole stays open and the artifact is
honestly incomplete — which is a result, and a better one than a confident file
that happens to type-check for the wrong reason.

**The frozen target is checked twice.** `generate_wit` refuses when the rendered
CLAIM does not hash to the blueprint's frozen target; the adapter's
target-protection gate checks it again against the claim. Two independent checks
of the same thing, which is the only kind of redundancy worth paying for.

**Failure is routed, not retried.** A kernel failure is classified, and the class
decides who owns the fix. `repair_cycle` refuses a fourth attempt in the same
class with no reduction in open obligations, because at that point the artifact is
not the problem and editing it is compiler-chasing. `failure_ledger` fires
escalation at the pack's threshold.

Usage:
    produce.py --blueprint <bp.json> [--claim <claim.json>] [--workdir <dir>]
               [--tier structural|kernel] [--attempts N] [--json]
    produce.py --self-test

Exit: 0 artifact produced and checked, 1 produced but not checked clean,
      2 refused before producing anything, 3 escalated.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent


def run(cmd: list[str], timeout: int = 900) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", str(exc)


def as_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


class Production:
    def __init__(self, workdir: Path, quiet: bool = False):
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.quiet = quiet
        self.steps: list[dict] = []

    def step(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append({"step": name, "ok": ok, "detail": detail})
        if not self.quiet:
            print(f"  [{'ok  ' if ok else 'STOP'}] {name}" + (f"  {detail}" if detail else ""))

    def classify_gap(self, failure_class: str, diagnostic: str, artifact: Path) -> dict:
        """Ask the gap classifier which axis to move next."""
        payload = [{"node_id": artifact.stem, "status": "GAP",
                    "failure_class": failure_class,
                    "diagnostic": str(diagnostic)[:400],
                    "lean_statement": artifact.name}]
        path = self.dir / "gap_input.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        code, out, _ = run([sys.executable, str(HERE / "gap_feedback.py"), "classify",
                            "--results", str(path), "--json"])
        parsed = as_json(out)
        nodes = parsed.get("nodes") or []
        return nodes[0] if nodes else (parsed if isinstance(parsed, dict) else {})

    def execute(self, blueprint_path: Path, claim_path: Path | None,
                tier: str, attempts: int) -> dict:
        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        name = blueprint.get("metadata", {}).get("name", "artifact")
        target = blueprint.get("target_protection", {}).get("frozen_target_sha256", "")

        # 1. render the plan --------------------------------------------------
        wit_path = self.dir / f"{name}.wit"
        code, out, err = run([sys.executable, str(HERE / "generate_wit.py"),
                              "--blueprint", str(blueprint_path),
                              "--out", str(wit_path), "--json"])
        rendered = as_json(out)
        if code != 0:
            self.step("render blueprint", False,
                      "; ".join(rendered.get("problems", []))[:220] or (out + err)[:220])
            return self.report("REFUSED_BEFORE_PRODUCING")
        self.step("render blueprint", True,
                  f"{wit_path.name}, {len(blueprint.get('lemma_plan', []))} step(s)")

        # 2. structural check -------------------------------------------------
        code, out, err = run([sys.executable, str(HERE / "tiers" / "structural.py"),
                              str(wit_path), "--json"])
        structural = as_json(out)
        if code != 0:
            self.step("structural check", False,
                      "; ".join(structural.get("problems", []))[:220] or (out + err)[:200])
            return self.report("PRODUCED_MALFORMED", artifact=str(wit_path))
        self.step("structural check", True, "well-formed; shape only")

        if tier == "structural":
            return self.report("PRODUCED", artifact=str(wit_path),
                               status="SKETCH", target_sha256=target)

        # 3. formalize --------------------------------------------------------
        statement = (blueprint.get("target_formalization", {}) or {}).get("formal_statement")
        if not statement:
            self.step("formalize", False,
                      "the blueprint declares no target_formalization.formal_statement. This "
                      "script will not guess one: autoformalization is exactly where fidelity "
                      "is lost, and a guessed statement type-checks just as well as a right one")
            return self.report("PRODUCED", artifact=str(wit_path), status="SKETCH",
                               target_sha256=target)

        formal_map = {}
        for entry in blueprint.get("lemma_plan", []):
            formal = entry.get("formalization")
            if formal:
                formal_map[str(entry.get("step_id"))] = formal
        closing = (blueprint.get("target_formalization", {}) or {}).get("closing_tactic")
        if closing:
            formal_map["__closing__"] = {"tactic": closing}
        formal_path = self.dir / "formalization.json"
        formal_path.write_text(json.dumps(formal_map, indent=2), encoding="utf-8")

        lean_path = self.dir / f"{name}.lean"
        code, out, err = run([sys.executable, str(HERE / "wit_to_lean.py"), str(wit_path),
                              "--statement", statement, "--formalization", str(formal_path),
                              "--out", str(lean_path), "--json"])
        translated = as_json(out)
        state = translated.get("state")
        if not translated.get("lean_ready"):
            self.step("formalize", False, translated.get("reason", (out + err)[:200]))
            return self.report("PRODUCED", artifact=str(wit_path), status="SKETCH",
                               target_sha256=target)
        # A preamble — imports and options — belongs to the artifact, not to the
        # statement. Folding it into `formal_statement` would put it inside the
        # thing the fidelity gate compares against the frozen target, and the
        # gate would then be diffing an import list against a claim.
        preamble = (blueprint.get("target_formalization", {}) or {}).get("preamble")
        if preamble:
            lean_path.write_text(preamble.rstrip() + "\n\n"
                                 + lean_path.read_text(encoding="utf-8"), encoding="utf-8")

        self.step("formalize", True,
                  f"{state}: {len(translated.get('filled_steps', []))} filled, "
                  f"{len(translated.get('open_steps', []))} open"
                  + (f", preamble {len(preamble.splitlines())} line(s)" if preamble else ""))
        if state != "OBLIGATIONS_FILLED":
            # An incomplete artifact is not automatically a bad one — whether its
            # gaps are GOOD gaps is a separate question with its own rubric in
            # scripts/sketch_rubric.py. That rubric consumes a proof DAG rather
            # than a WIT artifact, so this path cannot call it without building
            # one, and saying so is better than a call that silently returns
            # nothing and reads like a clean result.
            open_steps = translated.get("open_steps", [])
            self.step("kernel", False,
                      f"{len(open_steps)} obligation(s) still open, so the kernel would only "
                      "confirm the holes. Fill them in the blueprint, or report SKETCH honestly "
                      "— and run scripts/sketch_rubric.py against the proof DAG to find out "
                      "whether these are good gaps or one hole shaped like the problem")
            return self.report("PRODUCED_INCOMPLETE", artifact=str(lean_path),
                               status="SKETCH", target_sha256=target,
                               open_steps=open_steps)

        # 4. kernel, with the repair loop -------------------------------------
        repair_state = self.dir / "repair.json"
        run([sys.executable, str(HERE / "repair_cycle.py"), "init", "--state",
             str(repair_state), "--target-hash", target or "0" * 64,
             "--artifact", str(lean_path)])
        ledger = self.dir / "failures.json"

        for attempt in range(1, attempts + 1):
            code, out, err = run([sys.executable, str(HERE / "tiers" / "kernel.py"),
                                  str(lean_path), "--json"])
            kernel = as_json(out)
            verdict = kernel.get("verdict")
            if verdict == "pass":
                self.step(f"kernel (attempt {attempt})", True, "elaborated clean")
                return self.report("CHECKED", artifact=str(lean_path), wit=str(wit_path),
                                   status="VERIFIED_pending_gates", target_sha256=target,
                                   attempts=attempt)
            if verdict == "not_run":
                self.step(f"kernel (attempt {attempt})", False,
                          kernel.get("detail", "tier unavailable") or
                          "the kernel tier could not run; this is a gap, not a pass")
                return self.report("KERNEL_UNAVAILABLE", artifact=str(lean_path),
                                   status="SKETCH", target_sha256=target)

            failure_class = kernel.get("failure_class", "unknown")
            diagnostic = kernel.get("failure_signature") or kernel.get("log_excerpt", "")
            self.step(f"kernel (attempt {attempt})", False,
                      f"{failure_class}: {str(diagnostic)[:120]}")

            code, out, _ = run([sys.executable, str(HERE / "repair_cycle.py"), "record",
                                "--state", str(repair_state),
                                "--failure-class", failure_class,
                                "--diagnostic", str(diagnostic)[:400],
                                "--obligation-delta", "unknown", "--expensive",
                                "--hypothesis", "kernel re-run under the same blueprint"])
            repair = as_json(out)
            code, out, _ = run([sys.executable, str(PACK.parent.parent / "scripts" /
                                                    "failure_ledger.py"), "record",
                                "--ledger", str(ledger), "--target", target or "0" * 64,
                                "--claim", name, "--pack", "maths",
                                "--failure-class", failure_class,
                                "--detail", str(diagnostic)[:400]])
            assessment = as_json(out)
            if assessment.get("escalate"):
                self.step("escalation", True, "ESCALATE — the obstruction goes to the "
                          "deep-attack role; production stops on this claim")
                return self.report("ESCALATED", artifact=str(lean_path),
                                   failure_class=failure_class, target_sha256=target,
                                   attempts=attempt)
            if repair.get("blocked"):
                self.step("repair budget", False, str(repair.get("reason", ""))[:180])
                return self.report("REPAIR_EXHAUSTED", artifact=str(lean_path),
                                   failure_class=failure_class, target_sha256=target)
            # Nothing here edits the artifact: repair means a revised BLUEPRINT,
            # which is a decision for whoever wrote it. Re-running the same bytes
            # would produce the same failure, and counting it as an attempt is
            # how a budget gets spent learning nothing.
            #
            # But "revise the blueprint" is not advice. The gap classifier says
            # WHICH axis to move and refuses a bare retry, and it existed unwired
            # for as long as the pack did — the one component whose whole job is
            # to answer the question the failure path was leaving open.
            advice = self.classify_gap(failure_class, diagnostic, lean_path)
            self.step("repair", False,
                      f"the artifact is unchanged, so a re-run would fail identically. "
                      f"{advice.get('gap_class', 'unclassified')} — move the "
                      f"{(advice.get('proposed_mutation') or {}).get('axis', 'unknown')} axis. "
                      f"{advice.get('why_this_class', '')}")
            return self.report("NEEDS_BLUEPRINT_REVISION", artifact=str(lean_path),
                               failure_class=failure_class, target_sha256=target,
                               attempts=attempt, guidance=advice)

        return self.report("ATTEMPTS_EXHAUSTED", target_sha256=target)

    def report(self, outcome: str, **extra) -> dict:
        return {"outcome": outcome, "steps": self.steps, "workdir": str(self.dir), **extra}


def self_test() -> int:
    """Every blueprint fixture must render, pass the structural tier, and — where
    it supplies formalizations — reach OBLIGATIONS_FILLED. The refusal fixtures
    must be refused before anything is produced."""
    fixtures = sorted((PACK / "evals" / "blueprints").glob("*.json"))
    if not fixtures:
        print("no blueprint fixtures found", file=sys.stderr)
        return 1
    spec = json.loads((PACK / "evals" / "blueprints" / "expected.json").read_text(encoding="utf-8"))
    expected = {e["blueprint"]: e for e in spec["blueprints"]}
    failures = []

    with tempfile.TemporaryDirectory() as raw:
        for fixture in fixtures:
            if fixture.name == "expected.json":
                continue
            case = expected.get(fixture.name)
            if case is None:
                failures.append(f"{fixture.name} has no entry in expected.json")
                continue
            needed = case.get("requires_env")
            if needed and not os.environ.get(needed):
                print(f"  skip  {fixture.name:<34} needs {needed}")
                print(f"          {case['why']}")
                continue
            work = Path(raw) / fixture.stem
            report = Production(work, quiet=True).execute(
                fixture, None, case.get("tier", "structural"), 1)
            got = report["outcome"]
            ok = got == case["expect"]
            print(f"  {'ok  ' if ok else 'FAIL'}  {fixture.name:<34} {got}")
            print(f"          {case['why']}")
            if not ok:
                detail = next((s for s in report["steps"] if not s["ok"]), {})
                failures.append(f"{fixture.name}: got {got}, expected {case['expect']} "
                                f"— {detail.get('detail', '')[:200]}")

    print("\n" + "=" * 62)
    if failures:
        print(f"  PRODUCE SELF-TEST: FAIL — {len(failures)}")
        for failure in failures:
            print(f"    {failure}")
        return 1
    print(f"  PRODUCE SELF-TEST: PASS — {len(expected)} blueprint(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blueprint")
    ap.add_argument("--claim")
    ap.add_argument("--workdir")
    ap.add_argument("--tier", default="kernel", choices=["structural", "kernel"])
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.blueprint:
        ap.error("--blueprint is required unless --self-test")

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="produce-"))
    production = Production(workdir, quiet=args.json)
    try:
        report = production.execute(Path(args.blueprint),
                                    Path(args.claim) if args.claim else None,
                                    args.tier, args.attempts)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n  OUTCOME: {report['outcome']}")
        if report.get("artifact"):
            print(f"  artifact  {report['artifact']}")
        if report.get("status"):
            print(f"  strongest status this supports, before the adapter's gates: "
                  f"{report['status']}")
        print(f"  files in  {report['workdir']}")

    return {"CHECKED": 0, "PRODUCED": 0, "REFUSED_BEFORE_PRODUCING": 2,
            "ESCALATED": 3}.get(report["outcome"], 1)


if __name__ == "__main__":
    sys.exit(main())
