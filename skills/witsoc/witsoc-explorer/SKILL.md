---
name: witsoc-explorer
description: Internal Witsoc exploration subskill for advanced mathematics. Use inside the Witsoc subsystem for supply search, premise selection, theorem lookup planning, counterexample hunting, example testing, invariant mining, lemma discovery, proof strategy portfolios, reduction design, proof automation planning, Lean/Coq/SMT premise suggestions, and general mathematical exploration before or alongside WIT proof generation. It can work independently for exploratory math, or hand a precise proof plan to `witsoc-generator`.
metadata:
  skill-author: OpenScientist
category: research
---

# Witsoc Explorer

Explorer is the discovery and **arbitration** engine inside Witsoc. It turns an unclear task into a precise frozen target, sourced status, premises, lemmas, counterexamples, barrier packets for Lovasz, and proof plans that survive skeptical verification. It may answer small problems directly; for serious proof work it must hand a validated package to `witsoc-generator` before any final `.wit`.

Explorer runs **first** for serious proof work, theorem proving, WIT/Lean generation, open problems, and research targets. It owns arbitration:

- classify the target: solved · open · unsolved · unconfirmed · false · under-specified · already-formalizable;
- route solved/routine/formalizable targets to Generator after a structured handoff;
- route open/unsolved/unconfirmed/frontier/blocked targets to Lovasz with a barrier packet;
- **review every Lovasz return before Generator is allowed**;
- send a Generator blocker back to Lovasz only after diagnosing it is a genuine barrier, not artifact repair.

Never call anything `VERIFIED` (only receipts/checkers do). Do not write final `.wit` except for very small tasks.

Load-on-demand references (do not inline them here): the 13 specialized modes in `../references/core/explorer_modes.md`, the output templates in `../references/core/explorer_templates.md`, and the shared substrate `../references/core/substrate.md` (reach `services/`/`bridges/` only through a bridge as `requester=witsoc-explorer`). Other shared protocols: `../references/core/{status,handoff,failure_recovery,open_problem,repair,goal_cache,exploration_strategy,safeverify}.md`; schemas under `../references/schemas/`; validators via `../scripts/validate_handoff.py`.

## Operating principle

Explore under adversarial pressure: try to break the statement before proving it · track exact hypotheses and domains · prefer small lemmas with explicit dependencies · separate known facts, plausible facts, and unproved bridges · optimize for downstream WIT/Lean formalization, not persuasive prose.

## Core loop

**0. Profile** (`../references/core/exploration_strategy.md`, Phase 0): object type · difficulty `D1`–`D5` · proof styles · known-theorem density · search implications. Profiling picks the first search move.

**1. Normalize the target** into precise internal form (object types, domains, hypotheses, definitions, conclusion, quantifier order, task kind). Flag ambiguity; never silently strengthen/weaken/re-quantify. Then classify status. If solved → Solved-Problem Reconstruction before proof search. If open/unsolved/unconfirmed/frontier/blocked → run the Open-Problem Barrier Engine and prepare a Lovasz barrier packet. **For a prove/disprove/deep-run request, never end with only "open/unsupported by known results" — that classification is the trigger for Lovasz.** The sole exception is a concrete operational blocker preventing Lovasz dispatch, recorded explicitly.

**1.1 Write the Lovasz barrier packet** before invoking Lovasz:

```json
{
  "frozen_target_statement": "exact statement with quantifiers and definitions",
  "variant_status_ledger": ["variant, status, source/evidence"],
  "source_trail": ["primary sources, surveys, maintained pages, formal facts"],
  "best_known_results": ["exact known bounds, cases, reductions, or negative facts"],
  "known_obstructions_failed_methods": ["obstruction or method and why it blocks"],
  "theorem_precondition_gaps": ["candidate theorem and missing precondition"],
  "actual_barrier_lemmas": ["lemma/reduction/obstruction that would directly move the frozen target"],
  "actual_lemma_queue_seed": ["prioritized exact lemmas with why each unlocks the target"],
  "counterexample_pressure": ["families, boundary cases, small cases to test"],
  "formalization_blockers": ["definitions, libraries, theorem availability, target drift risks"],
  "smallest_tractable_products": ["special case, conditional theorem, obstruction, computation, counterexample"],
  "lovasz_success_criteria": ["what would count as progress for this loop"]
}
```

Then announce `Using witsoc with witsoc-explorer -> witsoc-research-lovasz.` Creating the packet does **not** complete the run — it completes only after Lovasz returns and Explorer reviews it into a verified solution, verified partial/special/conditional product, verified obstruction/counterexample/reduction, conjecture-with-evidence, failed-attempt-with-memory, or still-open-after-documented-attacks. Reject any Lovasz return that attacks only convenient weaker products without an `actual_lemma_queue`, target-fidelity scores, skeptic review for accepted nodes, retry ledger, and synthesis audit; and reject "equivalent to a known open conjecture" with no campaign ledger — known-open is the *start* of Lovasz work.

**2. Attack before proving.** Run the Falsification Pass Hierarchy (trivial/degenerate → symmetry/parity → asymptotic extremes; plus missing positivity/finiteness/continuity/compactness/etc.). Check every `O/o/Ω/Θ`/limit claim with `../scripts/asymptotic_analyzer.py`; a rejected bound is `REJECTED`, an `unknown`/no-SymPy result is a theorem-precondition gap, not evidence. On a counterexample, switch to disproof mode, minimize + verify it, then attempt to generalize into an obstruction family (`../scripts/research_search.py --inflate`) and an obstruction-theorem target.

**3. Map ontology + search backward.** Map to ontology nodes/theorem families (retrieval hints, not proof dependencies). Backward-chain the conclusion into subgoals. Rank theorem candidates (name, similarity, prerequisite-satisfaction, formal availability, expected utility, missing preconditions, weakest usable form); promote only high-ranked precondition-audited ones into `external_facts`, and record rejected candidates with the exact reason.

**4. Discover obstructions.** For open / `D4`–`D5` targets, generate ≥3 obstruction candidates before proving; build a barrier map (each approach names the barrier it hits and the single mutation that tries to bypass it). A non-routine mathematical blocker goes to Lovasz, not prose.

**5. Mine conjectures** from patterns (ranked, with evidence/scope/risk/next-test) — never upgrade a conjecture to a theorem.

**6. Build proof objects + strategy portfolio.** 2–4 credible approaches (key idea, required premises, likely hard step, expected shape, formalization risk, how to falsify). Pick the highest-EV route whose hard steps are small lemmas with high theorem fidelity. For open problems, pick exactly one open-product target (finite counterexample, obstruction lemma, or conditional step) and run proof compression before handoff.

**6.1 Recovery after failure** (`../references/core/failure_recovery.md`): keep the target frozen, mutate exactly one dimension, avoid repeating a failed method unless a real ingredient changes; a mathematical barrier → new Lovasz packet, artifact/syntax/Lean-friction → back to Generator unchanged.

**6.2 Lovasz-return review — the decision gate.** Lovasz returns to Explorer (not Generator) with resolved/open barriers, classified claims (`REJECTED`/`FAILED_ATTEMPT`/`CONJECTURE`/`PARTIAL`/`PROVED_SKETCH`/`CHECKED`/`VERIFIED`), evidence/sources, search results, gaps, next target. Explorer chooses **exactly one**:
- `LOVASZ_AGAIN` — send another barrier packet;
- `DEMOTE` — mark `CONJECTURE`/`FAILED_ATTEMPT`/`REJECTED`/`OPEN`/`PARTIAL`/`CONDITIONAL`;
- `GENERATOR_READY` — a solved/routine plan, verified partial, checked computation/counterexample, conditional theorem, or formalizable narrow lemma is ready;
- `HONEST_STOP` — no defensible progress path remains.

Generator may run **only** from `GENERATOR_READY`. Do not choose `HONEST_STOP` on a deep run merely because the literature says the target is open — that requires recorded Lovasz attempts or a concrete inability to dispatch Lovasz.

**7. Discover lemmas** (local, explicit, checkable, reusable, formalization-aware, economical). Prefer high-value helpers (goals-unlocked / proof-complexity) over vague citations.

**8. Select premises** — smallest set that implies the step; list named-theorem preconditions separately; never write "by standard theorem". Before adding any external/Mathlib dependency to the handoff, verify availability + module path with `../scripts/mathlib_atlas.py` and record atlas status/path/imports; no match → formal availability `UNKNOWN`, keep it a search target.

Specialized modes (open-problem campaigns, proof-sketch protocol, rater mode, counterexample hunting, reduction design, proof-automation planning, etc.) are in **`../references/core/explorer_modes.md`** — load it when the task needs one.

## Handoff to Witsoc Generator

For a nontrivial `.wit` target, write both **`runs/<task>/handoff.json`** (rich state, `../references/schemas/handoff.schema.json`) and strict **`runs/<task>/handoff_v1.json`** (`../references/schemas/witsoc-handoff-schema.json`), set state `HANDOFF_READY` only after both validate:

```bash
VALIDATOR="$("$PLANE_TOOL_BIN" skill-which witsoc/scripts/validate_handoff.py)"
python3 "$VALIDATOR" runs/<task>/handoff.json
python3 "$VALIDATOR" runs/<task>/handoff_v1.json
```

The blueprint `lemma_plan` must be a DAG (every `depends_on` references an earlier `step_id`; every external theorem in `method` appears in `external_dependencies`). The handoff must carry: Phase-0 profile, budget/stop-conditions, solved-problem map (if solved), status/theorem-claim sources, ontology map + retrieval hints, ranked and rejected theorem candidates, backward-chaining graph, falsification results, obstruction candidates + barrier map + selected open-product target, ranked conjectures, frozen target + freeze hashes, artifact target/status, proof objects and EV-scored sketches (with calibration notes), selected sketch id, structured lemma arrays + economics, obligation graph, external facts with preconditions/fallbacks + verification records, mutation-tracker entries, proof-compression record, counterexamples checked, `wit_notes` WIT structure, and Lean notes when relevant. Keep it concise enough that Generator writes labeled WIT without redoing exploration. Output templates: **`../references/core/explorer_templates.md`**.

## Quality bar

Succeeds when it narrows ambiguity, catches false statements early, reduces search to checkable lemmas, minimizes premise sets, exposes missing preconditions, and gives Generator a WIT-ready path. Fails when it invents theorem names, hides uncertainty, overclaims on open problems, treats examples as universal proof, skips edge cases, silently changes the theorem, or produces prose that cannot become WIT labels.
