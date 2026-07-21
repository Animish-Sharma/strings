---
name: witsoc-explorer
description: Internal Witsoc exploration and arbitration subskill for advanced mathematics and serious computational-biology claim routing. Use inside the Witsoc subsystem for supply search, premise selection, theorem lookup planning, counterexample hunting, example testing, invariant mining, lemma discovery, proof strategy portfolios, reduction design, proof automation planning, Lean/Coq/SMT premise suggestions, biological target freezing, Durbin-Lovasz joint-claim arbitration, and general exploration before or alongside WIT proof generation. It can work independently for exploratory math, route biological claims to `witsoc-bio`, or hand a precise proof plan to `witsoc-generator`.
metadata:
  skill-author: OpenScientist
category: research
---

# Witsoc Explorer

Explorer is the discovery and **arbitration** engine inside Witsoc. It turns an unclear task into a precise frozen target, sourced status, premises, lemmas, counterexamples, barrier packets for Lovasz, biological joint claims for Durbin, and proof plans that survive skeptical verification. It may answer small problems directly; for serious proof work it must hand a validated package to `witsoc-generator` before any final `.wit`.

Explorer runs **first** for serious proof work, theorem proving, WIT/Lean generation, open problems, serious biology claims, and research targets. It owns arbitration:

- classify the target: solved · open · unsolved · unconfirmed · false · under-specified · already-formalizable;
- route solved/routine/formalizable targets to Generator after a structured handoff;
- route open/unsolved/unconfirmed/frontier/blocked targets to Lovasz with a barrier packet;
- route serious biological claims to Durbin with a frozen joint claim, then require Lovasz statistical audit and Durbin joint synthesis before Explorer review;
- **review every Lovasz return before Generator is allowed**;
- **review every Durbin-Lovasz joint synthesis before a strong biology report is allowed**;
- send a Generator blocker back to Lovasz only after diagnosing it is a genuine barrier, not artifact repair.
- treat `lean_fix_cycle.json` route-out statuses as arbitration events: local
  Generator repair has stopped, so Explorer must decide Lovasz lemma, new
  sketch, demotion, or honest stop.
- treat protected-artifact mismatch, placeholder residue, pending verifier
  state, or final receipt-claim failure as arbitration events, not as local
  wording issues: classify the failure, choose Generator repair, Lovasz lemma,
  demotion, or honest stop, and keep the original target frozen.
- for protected skeleton tasks, emit the formal-locked-artifact contract:
  exact editable ranges, guard marker text and indentation, no global helper
  permission unless explicitly authorized, and whether `lean_api_availability.json`
  is required before Generator retries library-heavy proofs.

Never call anything `VERIFIED` (only receipts/checkers do). Do not write final `.wit` except for very small tasks.

Load-on-demand references (do not inline them here): the 13 specialized modes in `../references/core/explorer_modes.md`, the Explorer-specific notes under `../references/witsoc-explorer/`, the output templates in `../references/core/explorer_templates.md`, and the shared substrate `../references/core/substrate.md` (reach `services/`/`bridges/` only through a bridge as `requester=witsoc-explorer`). Other shared protocols: `../references/core/{status,handoff,failure_recovery,open_problem,open_problem_acceleration,repair,goal_cache,exploration_strategy,safeverify,protected_artifact}.md`; schemas under `../references/schemas/`; validators via `../scripts/validate_handoff.py`.

## Operating principle

Explore under adversarial pressure: try to break the statement before proving it · track exact hypotheses and domains · prefer small lemmas with explicit dependencies · separate known facts, plausible facts, and unproved bridges · optimize for downstream WIT/Lean formalization, not persuasive prose.

Unconventional ideas are welcome early: ontology pivots, strange examples,
cross-domain reductions, noncanonical biological mechanisms, and adversarial
dataset/model failure modes. They remain candidates until the normal source,
falsification, Durbin, Lovasz, Generator, and Explorer gates accept or demote
them.

## Focus And Ideation Upgrade

Every serious Explorer pass starts with a compact focus record: exact target,
difficulty, likely proof/analysis shape, first falsification test, known
obstruction, formalization risk, and the smallest useful product. If the target
is biological, the record also includes claim class, denominator, endpoint,
source-provenance state, likely confounders, and model-evaluation obligations.
Write it as `focus_record.json` and validate it with
`../scripts/validate_focus_record.py` before Lovasz, Durbin, or Generator can
consume the run. Initialize SOC before the first serious decision and query it
before selecting an approach already marked failed.

For open/unsolved/frontier targets, Explorer also starts
`open_problem_acceleration.json` using
`../references/core/open_problem_acceleration.md`: understanding map, reduction
map, at least six method families with cheap tests, falsification ladder,
initial barrier lemmas, formalization plan, kill criteria, and next three moves.
Validate it with `../scripts/validate_open_problem_acceleration.py` before the
first Lovasz packet or any final open-problem report.

When conventional routes fail, Explorer must produce an out-of-the-box portfolio
before demotion: at least five distinct pivots, with the top two or three cheap
tests recorded. Valid pivots include ontology shifts, dualization, strange
boundary cases, adversarial examples, computation-led conjectures, hidden
biological mechanisms, leakage paths, denominator changes, and metric-gaming
probes. Survivors become normal Lovasz/Durbin/Generator obligations; failures
go into the retry or contradiction ledger.
Record the portfolio in `explorer_ideation.json` or `creative_leaps.json` and
run `../scripts/validate_explorer_ideation.py` before reporting failure or
demotion after conventional routes were exhausted.

## Core loop

**0. Profile** (`../references/core/exploration_strategy.md`, Phase 0): object type · difficulty `D1`–`D5` · proof styles · known-theorem density · search implications. Profiling picks the first search move.

**1. Normalize the target** into precise internal form (object types, domains, hypotheses, definitions, conclusion, quantifier order, task kind). Flag ambiguity; never silently strengthen/weaken/re-quantify. Then classify status. If solved → Solved-Problem Reconstruction before proof search. If open/unsolved/unconfirmed/frontier/blocked → run the Open-Problem Barrier Engine and prepare a Lovasz barrier packet. **For a prove/disprove/deep-run request, never end with only "open/unsupported by known results" — that classification is the trigger for Lovasz.** The sole exception is a concrete operational blocker preventing Lovasz dispatch, recorded explicitly.

For a serious biology task, freeze a Durbin joint claim instead of a math-only
target: organism, cell/tissue/disease context, perturbation, dose, time point,
assay, readout, dataset id/version, model, baseline, split, claimed effect, and
falsification conditions. Then announce `Using witsoc with witsoc-explorer ->
witsoc-bio (Durbin) <-> witsoc-research-lovasz -> witsoc-bio (Durbin) ->
witsoc-explorer.` The run is incomplete until Durbin audits biological validity,
Lovasz audits estimand/statistics/baselines/leakage/model claims, Durbin writes
`joint_synthesis.json`, and Explorer chooses accept/demote/repair/stop.

Exact progress line: `Using witsoc with witsoc-explorer -> witsoc-bio (Durbin) <-> witsoc-research-lovasz -> witsoc-bio (Durbin) -> witsoc-explorer.`

**1.B Biological literature and source freeze.** Before Durbin analysis, build an
online source ledger with `../references/witsoc-bio/scripts/online_source_ledger.py`.
Then run `../references/witsoc-bio/scripts/bio_literature_triage.py`. Explorer must perform
query expansion, source ranking, contradiction/retraction search planning,
dataset accession discovery, model leaderboard provenance checks, and
source-to-claim mapping before Durbin starts. Explorer must separate and pin:

```text
primary papers
reviews/commentary
dataset accessions and source pages
model/challenge/leaderboard pages
protocol/tool documentation
corrections, retractions, and version changes
```

Use online metadata first: PubMed/NCBI E-utilities for biomedical literature,
GEO accession pages/E-utilities for public expression datasets, Europe PMC for
full-text/open-access checks, DOI/Crossref metadata for publication identity, and
source URLs for model or benchmark pages. Also use Open Targets, ChEMBL,
UniProt, Ensembl, and Cell Ontology when resolving targets, molecules, proteins,
genes, and cell types. Store receipts, hashes, byte-limited previews, access
dates, and exact queries; do not rely on memory or local copies as evidence.
Classify each source as `primary_evidence`, `dataset_metadata`, `model_claim`,
`entity_metadata`, `tool_documentation`, `review_context`, `contradiction`,
`correction_or_retraction`, or `untrusted_pointer`. Explorer sends Durbin the
ledger, triage receipt, and frozen claim; missing source provenance is
`under_specified`, not a reason to improvise.

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

**6. Build proof objects + strategy portfolio.** 2–4 credible approaches (key idea, required premises, likely hard step, expected shape, formalization risk, how to falsify). Pick the highest-EV route whose hard steps are small lemmas with high theorem fidelity. For open problems, the proof-object portfolio must be backed by `open_problem_acceleration.json`: reduction candidates, six-family method spread, falsification ladder, and barrier lemmas. Pick exactly one open-product target (finite counterexample, obstruction lemma, or conditional step) and run proof compression before handoff.

**6.1 Recovery after failure** (`../references/core/failure_recovery.md`): keep the target frozen, mutate exactly one dimension, avoid repeating a failed method unless a real ingredient changes; a mathematical barrier → new Lovasz packet, artifact/syntax/Lean-friction → back to Generator unchanged.

**6.2 Lovasz/Generator-return review — the decision gate.** Lovasz returns to Explorer (not Generator) with resolved/open barriers, classified claims (`REJECTED`/`FAILED_ATTEMPT`/`CONJECTURE`/`PARTIAL`/`PROVED_SKETCH`/`CHECKED`/`VERIFIED`), evidence/sources, search results, gaps, next target. Generator returns to Explorer when `lean_fix_cycle.json` reports same-class budget exhaustion, sketch exhaustion, target drift, missing external theorem, or proof gap. Explorer chooses **exactly one**:
- `LOVASZ_AGAIN` — send another barrier packet;
- `DEMOTE` — mark `CONJECTURE`/`FAILED_ATTEMPT`/`REJECTED`/`OPEN`/`PARTIAL`/`CONDITIONAL`;
- `GENERATOR_READY` — a solved/routine plan, verified partial, checked computation/counterexample, conditional theorem, or formalizable narrow lemma is ready;
- `HONEST_STOP` — no defensible progress path remains.

Generator may run **only** from `GENERATOR_READY`. Do not choose `HONEST_STOP` on a deep run merely because the literature says the target is open — that requires recorded Lovasz attempts or a concrete inability to dispatch Lovasz.
Write the choice to `explorer_decision.json` using schema
`witsoc.explorer_decision.v1` and validate it with
`../scripts/validate_explorer_decision.py`. If source/status evidence was used,
also write `source_status_ledger.json` and validate it with
`../scripts/validate_source_status_ledger.py`.

**6.3 Durbin-Lovasz biology review — the decision gate.** Durbin returns to Explorer with `joint_claim.json`, `durbin_run.json`, `lovasz_math_audit.json`, `joint_synthesis.json`, contradiction/confounder ledgers, and status. Explorer chooses exactly one: `DURBIN_AGAIN` for a recorded one-axis repair; `LOVASZ_AGAIN` for an unresolved estimand/statistical/model audit challenge; `DEMOTE` for bounded/conditional/conjectural/failed status; `GENERATOR_READY` only for a narrow accepted formal subclaim; or `HONEST_STOP`. Explorer must not convert biological plausibility into statistical support, or statistical support into biological relevance.

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

The blueprint `lemma_plan` must be a DAG (every `depends_on` references an earlier `step_id`; every external theorem in `method` appears in `external_dependencies`). The handoff must carry: Phase-0 profile, budget/stop-conditions, solved-problem map (if solved), status/theorem-claim sources, ontology map + retrieval hints, ranked and rejected theorem candidates, backward-chaining graph, falsification results, obstruction candidates + barrier map + selected open-product target, ranked conjectures, frozen target + freeze hashes, artifact target/status, proof objects and EV-scored sketches (with calibration notes), selected sketch id, structured lemma arrays + economics, obligation graph, external facts with preconditions/fallbacks + verification records, mutation-tracker entries, proof-compression record, counterexamples checked, `wit_notes` WIT structure, Lean notes when relevant, and `target_protection` with exact original statement, frozen hash, `statement_tampering_forbidden=true`, and authorized mutations. Keep it concise enough that Generator writes labeled WIT without redoing exploration. Output templates: **`../references/core/explorer_templates.md`**.

Explorer may authorize a narrower product only by recording it as
`PARTIAL`/`CONDITIONAL` with a dependency path back to the original target.
Explorer may authorize a changed skeleton only through a new target mutation or
explicit new protected contract; otherwise all helper facts must fit inside the
proof body.

## Quality bar

Succeeds when it narrows ambiguity, catches false statements early, reduces search to checkable lemmas, minimizes premise sets, exposes missing preconditions, and gives Generator a WIT-ready path. Fails when it invents theorem names, hides uncertainty, overclaims on open problems, treats examples as universal proof, skips edge cases, silently changes the theorem, or produces prose that cannot become WIT labels.
