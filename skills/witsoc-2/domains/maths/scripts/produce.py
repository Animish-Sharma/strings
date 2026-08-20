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

**Attempts compound.** A step that reached the kernel clean is recorded in the
campaign's lemma pool, and a failing kernel run has its residual goals mined out
of the diagnostics and proposed as bridging lemmas. Without that, every run
starts from nothing and the twentieth attempt at a hard target knows exactly
what the first one knew. The pool lives beside the workdir, so it accumulates
across runs against the same target and not across unrelated ones.

**Refutation comes first.** Before any expensive tier, the standard
counterexample families for the claim's area are named and the bounded tier is
offered the chance to break it. Doctrine has said "refute before you support"
since the pack was written, and nothing enforced it: production ran straight at
the proof, which is the order that spends the most to learn a claim was false.
A blueprint that declares a `search_domain` gets a bounded refutation attempt;
one that does not gets told which families it skipped, because an unrecorded
absence of counterexample search reads in a report exactly like a search that
found nothing.

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

**A failure hands back an edit, not an adjective.** When the kernel refuses, the
run writes `revision_request.json`: which step failed, which axis the gap
classifier says to move, what that means concretely for this blueprint, and any
bridging lemmas mined out of the diagnostic. "Revise the blueprint" is not
advice; a named step, a named axis, and a proposed change is.

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

    # What each axis means as an edit to THIS file. The classifier names the axis;
    # without this table the name is a category, and a category is not a change
    # anyone can make.
    AXIS_EDITS = {
        "theorem_source": ("a cited result is missing or misnamed. Correct the entry in "
                           "external_dependencies, or drop the citation and add the step that "
                           "establishes it — a premise that does not exist is a sub-claim"),
        "method": ("the tactic did not close the goal. Change the step's formalization.tactic; "
                   "the goal itself was accepted, so the statement is not what is wrong"),
        "encoding": ("the Lean rendering of a step does not say what the step says. Change "
                     "formalization.type, not the informal statement — the informal statement is "
                     "frozen"),
        "formalization_target": ("the formal_statement does not correspond to the frozen claim. "
                                 "This is a new claim with a new hash if the claim is what "
                                 "changes, and a correction if the formalization is"),
        "statement_strength": ("the plan proves something weaker or stronger than the target. "
                               "Narrowing the target starts a new claim; strengthening a step is "
                               "an edit to this one"),
        "invariant": ("the decomposition is missing the fact that makes the induction go "
                      "through. Add it as an earlier step, not as a stronger conclusion"),
        "object_class": ("the objects the plan reasons about are not the objects the statement "
                         "quantifies over. Fix the binders before the tactics"),
        "computational_bound": ("the search or bound in the plan is too wide to close. Narrow it "
                                "and state the narrowed range in the claim"),
    }

    def grade_sketch(self, blueprint: dict) -> dict | None:
        """Score the decomposition. The blueprint already is a proof DAG — one
        node per step with its dependencies — so the rubric that had no input
        has had one all along, in a different shape."""
        steps = blueprint.get("lemma_plan", []) or []
        if not steps:
            return None
        target = (blueprint.get("target_formalization", {}) or {}).get("claim", "")
        dag = {
            "target": target,
            "nodes": [{
                "id": str(step.get("step_id")),
                "statement": step.get("statement", ""),
                "formal_statement": (step.get("formalization") or {}).get("type"),
                "depends_on": step.get("depends_on", []),
                "kind": str(step.get("type", "HAVE")).lower(),
                # A step that cites an outside result is doing less work than one
                # that does not; a step with no dependencies and no citation is
                # either atomic or the whole problem in disguise.
                "granularity": ("atomic" if step.get("cites") or step.get("depends_on")
                                else "multi_step"),
            } for step in steps],
        }
        path = self.dir / "proof_dag.json"
        path.write_text(json.dumps(dag, indent=2) + "\n", encoding="utf-8")
        code, out, _ = run([sys.executable, str(HERE / "sketch_rubric.py"),
                            "--sketch", str(path), "--json"])
        scored = as_json(out)
        if not scored:
            return None
        components = scored.get("components", {})
        miracle = components.get("miracle_fraction", 0)
        scored["reading"] = (
            "a hole shaped like the problem: at least one step restates the target, so this "
            "decomposition has decomposed nothing"
            if miracle and miracle > 0 else
            "small, separately checkable holes — the useful kind"
            if scored.get("score", 0) >= 0.6 else
            "coarse: the steps are large or unlinked, so a failure will not localize")
        return scored

    def write_revision_request(self, blueprint: dict, blueprint_path: Path,
                               failure_class: str, diagnostic: str,
                               advice: dict, kernel: dict) -> Path:
        """Turn a classified failure into a specific, checkable edit."""
        axis = (advice.get("proposed_mutation") or {}).get("axis", "unknown")
        steps = blueprint.get("lemma_plan", []) or []

        # Which step? The diagnostic names a Lean identifier `stepN` when it can.
        failing = None
        for step in steps:
            ident = "step" + str(step.get("step_id", "")).replace(".", "_")
            if ident and ident in diagnostic:
                failing = step
                break

        pool = self.dir / "lemma_pool.json"
        bridges = []
        if pool.exists():
            code, out, _ = run([sys.executable, str(HERE / "lemma_pool.py"), "status",
                                "--pool", str(pool), "--json"])
            status = as_json(out)
            bridges = status.get("mined_statements") or []

        request = {
            "schema": "maths-revision-request-v1",
            "blueprint": str(blueprint_path),
            "target_sha256": blueprint.get("target_protection", {}).get("frozen_target_sha256"),
            "failure_class": failure_class,
            "gap_class": advice.get("gap_class"),
            "why_this_class": advice.get("why_this_class"),
            "axis_to_move": axis,
            "what_that_means_here": self.AXIS_EDITS.get(
                axis, "no concrete edit is recorded for this axis; say what you changed and why"),
            "failing_step": ({"step_id": failing.get("step_id"),
                              "statement": failing.get("statement"),
                              "formalization": failing.get("formalization")}
                             if failing else None),
            "step_identification": ("matched by the Lean identifier in the diagnostic"
                                    if failing else
                                    "the diagnostic names no step identifier, so the failure is "
                                    "in the statement or the preamble rather than in one step"),
            "diagnostic": diagnostic[:600],
            "mined_bridges": bridges,
            "do_not_repeat": advice.get("do_not_repeat"),
            "note": ("A revision is a new blueprint, not an edit to the artifact. The frozen "
                     "target does not move unless the claim itself is what changed, and then it "
                     "moves with a new hash and a recorded authorized_mutation."),
        }
        path = self.dir / "revision_request.json"
        path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        return path

    def pool_path(self) -> Path:
        pool = self.dir / "lemma_pool.json"
        if not pool.exists():
            run([sys.executable, str(HERE / "lemma_pool.py"), "init", "--out", str(pool)])
        return pool

    def harvest_lemmas(self, blueprint: dict) -> int:
        """Record each formalized obligation as proved. A step the kernel accepted
        is a fact about the library from now on, and forgetting it is how a long
        campaign re-derives the same bridge twenty times."""
        pool = self.pool_path()
        recorded = 0
        for step in blueprint.get("lemma_plan", []) or []:
            formal = step.get("formalization") or {}
            if not formal.get("type"):
                continue
            code, out, _ = run([sys.executable, str(HERE / "lemma_pool.py"), "propose",
                                "--pool", str(pool), "--statement", formal["type"],
                                "--origin", f"kernel-pass:{blueprint.get('metadata',{}).get('name','')}"])
            # `propose` prints "proposed <id>" as plain text, not JSON. Reading
            # it as JSON silently produced no id, so every harvested lemma stayed
            # PROPOSED and the pool recorded three facts it never learned.
            proposed = as_json(out)
            lemma_id = (proposed.get("id") or proposed.get("lemma_id")
                        if proposed else None)
            if not lemma_id:
                parts = out.strip().split()
                lemma_id = parts[-1] if parts and len(parts[-1]) >= 8 else None
            if lemma_id:
                run([sys.executable, str(HERE / "lemma_pool.py"), "record", "--pool", str(pool),
                     "--id", str(lemma_id), "--status", "PROVED",
                     "--evidence", "kernel elaboration of the containing artifact"])
                recorded += 1
        return recorded

    def mine_lemmas(self, diagnostic: str) -> int:
        """Read the checker's residual goals and propose each as a bridge."""
        if not diagnostic:
            return 0
        pool = self.pool_path()
        code, out, _ = run([sys.executable, str(HERE / "lemma_pool.py"), "mine",
                            "--pool", str(pool), "--diagnostic", diagnostic[:4000]])
        mined = as_json(out)
        candidates = mined.get("proposed") or mined.get("lemmas") or []
        return len(candidates) if isinstance(candidates, list) else 0

    def attempt_refutation(self, blueprint: dict, blueprint_path: Path) -> dict:
        """Try to break the claim before trying to establish it.

        Two things happen. The standard counterexample families for the claim's
        area are looked up and named — an area with no relevant family is itself
        a recorded finding, not silence. And where the blueprint declares a
        finite `search_domain`, the bounded tier actually searches it.

        A refutation here ends the campaign with a result. That is the cheapest
        good outcome available and the one the previous ordering could not reach
        without first paying for a proof attempt.
        """
        target_form = blueprint.get("target_formalization", {}) or {}
        area = target_form.get("area") or blueprint.get("metadata", {}).get("area")
        families = []
        code, out, _ = run([sys.executable, str(HERE / "counterexample.py"), "families"]
                           + (["--domain", area] if area else []))
        parsed = as_json(out)
        if isinstance(parsed, dict):
            families = parsed.get("families") or []

        search = target_form.get("search_domain")
        if not search:
            return {"refuted": False,
                    "detail": ("no search_domain declared, so nothing was searched. "
                               + (f"{len(families)} standard famil(ies) apply to this area and "
                                  "were not tested" if families else
                                  "no standard family is recorded for this area, which is itself "
                                  "the finding")),
                    "families_available": families}

        claim_path = self.dir / "bounded_claim.json"
        # The bounded tier reads its bounds from frozen_conditions, not from the
        # top level, because bounds that are not frozen can be quietly shrunk
        # after a failing search. Writing them anywhere else produces a tier that
        # runs, finds nothing, and reports it as evidence.
        claim_path.write_text(json.dumps({
            "claim_id": blueprint.get("metadata", {}).get("name", "claim"),
            "frozen_conditions": {"bounded_search": search}}, indent=2), encoding="utf-8")
        code, out, _ = run([sys.executable, str(HERE / "tiers" / "bounded.py"),
                            "--claim", str(claim_path), "--json"])
        bounded = as_json(out)
        if not bounded or bounded.get("verdict") in {None, "error"}:
            return {"refuted": False,
                    "detail": ("the bounded tier could not run over the declared search_domain, "
                               "so nothing was searched. NOT a clean search: an unrun search and "
                               "a search that found nothing are written the same way"),
                    "bounded": bounded}
        witnesses = bounded.get("counterexamples") or (
            [bounded["counterexample"]] if bounded.get("counterexample") else [])
        if witnesses:
            var = search.get("variable", "n")
            shown = ", ".join(f"{var}={w}" for w in witnesses[:4])
            return {"refuted": True,
                    "counterexamples": witnesses,
                    "bounds": bounded.get("bounds"),
                    "detail": (f"{shown} over {bounded.get('bounds')} "
                               f"({bounded.get('checked')} value(s) checked). The claim is false "
                               "as stated, and this cost nothing"),
                    "bounded": bounded}
        if bounded.get("verdict") in {"refuted", "fail"}:
            return {"refuted": True,
                    "detail": f"the bounded tier returned {bounded['verdict']} over "
                              f"{bounded.get('bounds')} without naming a witness — treat as a "
                              "refutation and go find the witness before reporting it",
                    "bounded": bounded}
        return {"refuted": False,
                "detail": (f"bounded search over {search} found no counterexample — which bounds "
                           "the claim inside that range and establishes nothing outside it"),
                "bounded": bounded, "families_available": families}

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

        # 1b. premise pre-flight ----------------------------------------------
        # Cheapest first. A citation that does not resolve costs five seconds of
        # import elaboration to discover at the kernel tier, and the diagnostic
        # it returns says exactly what a lookup says for free.
        preflight_cmd = [sys.executable, str(HERE / "premise_preflight.py"),
                         "--blueprint", str(blueprint_path), "--json"]
        corpus = os.environ.get("WITSOC2_MATHS_CORPUS")
        if corpus and Path(corpus).is_file():
            preflight_cmd += ["--corpus", corpus]
        code, out, _ = run(preflight_cmd)
        preflight = as_json(out)
        if preflight.get("problems"):
            self.step("premise pre-flight", False,
                      "; ".join(preflight["problems"])[:200])
            return self.report("REFUSED_BEFORE_PRODUCING", preflight=preflight)
        unresolved = preflight.get("unresolved") or []
        self.step("premise pre-flight", True,
                  f"{preflight.get('declared', 0)} declared, {len(unresolved)} unresolved"
                  + (f" ({', '.join(u['name'] for u in unresolved[:3])}) — a lead is not a "
                     "premise, and the kernel is about to say so" if unresolved else ""))

        # 1c. refutation first --------------------------------------------------
        refutation = self.attempt_refutation(blueprint, blueprint_path)
        if refutation.get("refuted"):
            self.step("refutation attempt", True,
                      f"COUNTEREXAMPLE: {refutation['detail'][:150]}")
            return self.report("REFUTED", target_sha256=target,
                               counterexample=refutation)
        self.step("refutation attempt", True, refutation.get("detail", "")[:150])

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
            # An incomplete artifact is not automatically a bad one. Whether its
            # gaps are GOOD gaps — small, independent, separately checkable — is
            # a different question, and the rubric that answers it needed a proof
            # DAG nobody was building. The blueprint IS that DAG: one node per
            # step, dependencies already declared, the target already frozen.
            open_steps = translated.get("open_steps", [])
            rubric = self.grade_sketch(blueprint)
            detail = (f"{len(open_steps)} obligation(s) still open. "
                      f"Sketch quality {rubric['score']} — {rubric['reading']}"
                      if rubric else
                      f"{len(open_steps)} obligation(s) still open, so the kernel would only "
                      "confirm the holes")
            self.step("kernel", False, detail)
            return self.report("PRODUCED_INCOMPLETE", artifact=str(lean_path),
                               status="SKETCH", target_sha256=target,
                               open_steps=open_steps, sketch=rubric)

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
                harvested = self.harvest_lemmas(blueprint)
                self.step(f"kernel (attempt {attempt})", True,
                          "elaborated clean"
                          + (f"; {harvested} obligation(s) recorded as proved in the pool"
                             if harvested else ""))
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

            mined = self.mine_lemmas(str(diagnostic))
            if mined:
                self.step("lemma mining", True,
                          f"{mined} bridging lemma(s) proposed from the residual goals — the "
                          "failed probe's diagnostics are the product, not a side effect")

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
            request = self.write_revision_request(
                blueprint, blueprint_path, failure_class, str(diagnostic), advice, kernel)
            axis = (advice.get("proposed_mutation") or {}).get("axis", "unknown")
            self.step("repair", False,
                      f"the artifact is unchanged, so a re-run would fail identically. "
                      f"{advice.get('gap_class', 'unclassified')} — move the {axis} axis. "
                      f"Edit written to {request.name}")
            return self.report("NEEDS_BLUEPRINT_REVISION", artifact=str(lean_path),
                               failure_class=failure_class, target_sha256=target,
                               attempts=attempt, guidance=advice,
                               revision_request=str(request))

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
