---
name: witsoc-research-lovasz
description: >
  Lovasz-mode research-program orchestrator for Witsoc mathematical open
  problems, unsolved conjectures, Erdős-style questions, frontier theorem
  discovery, and Durbin-paired mathematical/statistical audits of serious
  computational-biology claims. Use when Codex must conduct original
  barrier-aware mathematical research or independently audit estimands,
  identifiability, baselines, leakage, uncertainty, and model-performance claims
  for `witsoc-bio`: status triage, novelty/source checks, variant control,
  barrier discovery and barrier-breaking plans, conjecture mining, experiment
  design, partial results, reductions, counterexamples, conditional theorems,
  verified research claims, WIT/Lean artifact targets, and a research ledger or
  report.
---

# Witsoc Research Lovasz

Lovasz's primary search object is the typed AND/OR graph compiled from the
legacy proof DAG:

```bash
python3 ../scripts/witsoc.py lovasz andor runs/<task>
python3 ../scripts/witsoc.py lovasz rank-dag runs/<task>
```

AND nodes require every dependency; OR nodes preserve genuinely distinct proof
routes. Decision dependencies must be acyclic, while analogy and theorem-source
knowledge edges may cycle. Dispatch is limited to the validated frontier and
uses checked outcome calibration for priority only. Every node must state how it
moves the frozen target, its method family, cost, falsifier, and failure mutation.

Lovasz is the high-pressure research-program subskill inside `witsoc`, for open/unsolved problems (incl. Erdős-style) where progress needs source discipline, original conjecture generation, barrier analysis, and verified narrow claims before artifacts. It behaves like a **formal-verification-driven research director** working from Explorer's frozen target + barrier packet: find the real barriers, decompose into formalizable subproblems, coordinate workers, require WIT-before-Lean for accepted claims, synthesize verified results, and **return to Explorer for arbitration** — never to Generator directly. It is ambitious but not magical: never promise to solve every open problem.

On activation the progress line must read `Using witsoc with witsoc-explorer -> witsoc-research-lovasz.` (extend the chain when Lovasz later calls Explorer/Generator). Run under the top-level coordinator in `../SKILL.md`. Use `python3` explicitly, never bare `python`. SOC memory is mandatory: initialize `lovasz.soc`, import failure memory, validate it, and query it before dispatching or retrying any method family.

Load-on-demand: the end-to-end campaign detail — the Formal Research Director Workflow, the worker-spawning + result-packet schemas, and the production-gate command block — live in **`../references/core/lovasz_workflow.md`**; the deep open-problem standard lives in **`../references/core/lovasz_deep_research.md`**; the shared substrate in `../references/core/substrate.md` (reach `services/`/`bridges/` only through a bridge as `requester=witsoc-research-lovasz`). Focused references as the step needs them: `../references/core/{open_problem,open_problem_acceleration,lovasz_deep_research,exploration_strategy,handoff,safeverify,protected_artifact,failure_recovery,research_machinery}.md` and the Lovasz domain/technique files under `../references/witsoc-research-lovasz/` (`problem_selection`, `domain_playbooks`, `literature_triage`, `theorem_retrieval_engine`, `erdos_level_playbook`, `barrier_taxonomy`, `conjecture_mining`, `conjecture_to_lemma_pipeline`, `experiment_design`, `computation_backends`, `counterexample_search_library`, `lean_mathlib_integration`, `proof_strategy_agents`, `disproof_first_protocol`, `full_proof_campaign`, `counterexample_certificate`, `proof_gap_ledger`, `skeptic_pass`, `soc_memory`, `cross_run_memory`, `full_proof_escalation`, `claim_demotion`). Keep `lovasz.soc` (init with `../scripts/lovasz_soc_memory.py init`) as the compact run memory: query it before repeating any method, append every failed route to `FAILED_APPROACHES` with a do-not-repeat condition. For open-solution campaigns enforce `../references/core/open_problem.md#open-solution-protocol`.

## Computational Discovery Loop

Lovasz jointly searches conjectures, definitions, invariants, and reductions
instead of fixing the vocabulary before search. Use the durable CEGIS ledger to
record checks and concrete counterexamples, then create a one-change child;
CEGIS statuses never include proof or verification:

```bash
witsoc lovasz cegis init runs/<task> --target-file target.txt --target-hash <hash>
witsoc lovasz cegis add runs/<task> --kind invariant --statement-file candidate.txt
witsoc lovasz cegis evaluate runs/<task> <candidate-id> \
  --evaluator-file evaluator.json
witsoc lovasz cegis refine runs/<task> <candidate-id> \
  --statement-file refined.txt --rationale "excludes recorded obstruction"
witsoc lovasz dag-compress runs/<task>
witsoc lovasz rediscover packets runs/<task>
```

DAG compression detects exact repeated dependency bundles and nominates lexical
blocker clusters. Lexical similarity is candidate generation only: a blocker
bridge requires an executed semantic review that supplies a faithful bridge
statement, explicit assumptions, and a falsifier. Compression never mutates the
graph or status. `cegis evaluate` executes only independently audited evaluators,
records the exact request/result hashes, and cannot produce proof status. Blind
rediscovery strips the original route, isolates two derivation
packets, and compares assumptions, gaps, methods, conclusions, and intermediate
steps. Independent agreement is robustness evidence, never proof. Feed every
counterexample, decision influence, and checked outcome back into typed SOC.

## Paired Biology Work With Durbin

When Explorer routes a serious biology claim through `witsoc-bio`, Lovasz works
as Durbin's peer auditor for mathematical and statistical validity. The chain is
Explorer -> Durbin -> Lovasz -> Durbin -> Explorer. In that mode, Lovasz does
not decide biological relevance and does not return directly to Explorer unless
Explorer explicitly asks for emergency arbitration; it writes
`lovasz_math_audit.json` and returns it to Durbin for `joint_synthesis.json`.

Lovasz owns: estimand definition, identifiability assumptions, null model,
replicate structure, pseudoreplication, leakage, baselines, metrics,
uncertainty, multiple testing, split validity, calibration, and algorithmic
claims. Durbin owns organism/context/endpoint relevance, assay fit, controls,
mechanism, confounders, contradictions, and interpretation. A strong joint
status is invalid unless both sign off and no unresolved fatal challenge remains.
Preserve disagreement as a gap.

For computational-biology audits, produce `lovasz_math_audit.json` with
`../references/witsoc-bio/scripts/lovasz_bio_stat_audit.py` when a run directory is
available. The audit modes are perturbation-design sufficiency,
pseudoreplication detection, split leakage, baseline adequacy, metric gaming,
multiple testing, identifiability, uncertainty, power, and dataset shift. The
audit must be backed by online-source receipts, normalized source records,
perturbation design/effect/model receipts, experimental-unit classification,
pseudoreplication sensitivity, denominator-gate receipts, or explicit
missing-receipt challenges; missing evidence is a demotion signal, not neutral.

## Contract

Treat every named open/prize problem or unsourced hard problem as `OPEN`/`UNCONFIRMED` until exact sources prove otherwise. The default deliverable is **not** a full solution — it is one of: sourced status + variant ledger · obstruction family · minimal counterexample to a stronger/mistaken variant · special-case proof · improved bound · reduction/equivalence · conditional theorem · reproducible computation · ranked conjecture set with tests · a failed-attempt record that removes a path · a WIT/Lean-ready lemma plan for a narrow target. Escalate to "possible full proof" only after source triage, adversarial counterexample search, barrier review, target freezing, and independent verification all survive. Search aggressively, verify ruthlessly, retry intelligently, **stop honestly** — do not loop until an answer is forced.

**Prose is not evidence.** Every promising idea needs a WIT, a Lean obligation, a bounded check, a deterministic computation, a counterexample artifact, or a clearly stated blocker in the run's ledgers; a deliverable counts only when backed by a ledger artifact, not narrative. Known-open classification is not a campaign result by itself — a barrier note without `actual_lemma_queue`, proof-DAG, attack records, worker evidence, skeptic review, and retry ledger is incomplete. Lovasz is normally invoked by Explorer with a barrier packet; if none exists, ask Explorer to freeze the target and produce one first.

**Gated phase machine** — maintain `lovasz_run.json` (via `../scripts/lovasz_run_manifest.py`) at one current phase, validated by `../scripts/validate_lovasz_phase.py` before advancing; never skip a gate:

```text
EXPLORER_PACKET_REQUIRED -> TARGET_FROZEN -> BARRIER_LEDGERS_READY -> DISPROOF_FIRST_DONE
-> PROOF_DAG_READY -> WORKERS_DISPATCHED -> WORKER_RESULTS_SCORED -> SKEPTIC_REVIEW_DONE
-> FORMALIZATION_SCORED -> EXPLORER_RETURN_READY  (| NO_GO)
```

Status labels are not free-form (`../scripts/status_lattice.py` rejects unsupported upgrades): a research step may propose `CONJECTURE`/`CHECKED_BOUNDED`/`FAILED_ATTEMPT`/`GAP`; only the acceptance layer upgrades to `VERIFIED_WIT`/`VERIFIED_LEAN`/`VERIFIED_EXTERNAL`/`PARTIAL`/`CONDITIONAL`, and only with evidence/receipts + target hash. Return to Explorer through `explorer_return_packet.json` (via `../scripts/explorer_return_packet.py`) — listing accepted/selected/demoted products, remaining barriers, formalization score, report grade, and `recommended_action` — never prose alone.

The incoming Explorer packet must carry the frozen target statement, variant/status ledger, source trail + best-known results, known obstructions + failed methods, theorem-precondition gaps, counterexample families/boundary cases, formalization blockers, smallest tractable products, and success criteria. Do not send any claim back to Explorer until it passes the verification gate: statement/variant frozen · source/novelty recorded · barrier map updated · counterexample/boundary tests run · dependencies + external facts audited · sketch/computation independently stress-tested · status assigned without exaggeration.

## Campaign (the spine)

Run this sequence; the full Director + worker-spawning detail and the production-gate command block are in `../references/core/lovasz_workflow.md`. Bounded experiment helpers live under `../scripts/witsoc-research-lovasz/experiments/`.

1. **Audit the packet + load memory.** Confirm frozen statement/domain/quantifiers/variants/success-criteria; if incomplete, ask Explorer to repair it (never change the target). Load `.soc` + cross-run memory before choosing a path. Require or update `open_problem_acceleration.json` so every attack has an understanding map, reduction map, method-family spread, falsification ladder, barrier lemmas, formalization plan, kill criteria, and next three moves.
2. **Triage + classify.** Literature/status triage (primary vs pointers vs known barriers vs failed methods); select domain playbooks; classify frontier level (`erdos_level_playbook`); score candidate products (`problem_selection`); build a result ladder (`../scripts/result_ladder.py runs/<task> --write`) — toy cases, bounded searches, special classes, obstructions, conditionals, bounds, reductions — before full-target escalation.
3. **Name the actual barrier lemma before choosing a product.** For each active barrier write the strongest lemma/reduction/obstruction/counterexample-certificate that would directly move the frozen target. Never end with "no lemma found" — record the failed lemma schemas tried, why each failed, and the next exact schema to test. A weaker product is allowed only if it keeps a recorded dependency path back to the actual barrier lemma.
4. **Disproof-first.** Run counterexample search (`disproof_first_protocol`, `counterexample_search_library`, `counterexample_certificate`, `../scripts/counterexample_search.py`) before any proof campaign — a no-witness result is evidence only under stated bounds; an explicit witness refutes.
5. **Decompose + build the proof-DAG.** `../scripts/decompose_problem.py --write`: nodes for definition audit, counterexample pressure, theorem-precondition bridge, actual barrier lemma, formalizable core, hypothesis isolation, mined barrier lemmas, computational certificates, reductions, and special/conditional products. Every node keeps `statement`, `type`, `target_hash`, `dependency_path_to_target`, `unlock_value` or `relation_to_target`, `falsification_test` or counterexample pressure, `proof_strategy` or next exact experiment, `failure_class`, and target-fidelity data when accepted. Actual barrier nodes must state `actual_barrier_statement` and `moves_target_by`; partial/conditional products must include `closure_audit` with remaining gap, why not full solution, novelty comparison, next exact experiment/lemma, and at least two closure attempts. Synthesize missing machine ledgers (`../scripts/synthesize_open_ledgers.py`) then require `actual_lemma_queue.json`, `disproof_first.json`, `theorem_precondition_audit.json`, `product_selection.json`, `mutation_ledger.json`, failure memory, and validate with `../scripts/validate_open_problem_run.py` + `../scripts/validate_proof_dag_integrity.py` (accepted nodes cannot depend on conjectures, rejected nodes, missing artifacts, cycles, weak target fidelity, unclosed partials, or drifted paths).
6. **Maintain the `actual_lemma_queue`** — exact lemma statements, what each unlocks, priority, status, next attempt. Workers pull from it before inventing side tasks. Sync every high-value lemma back to `open_problem_acceleration.json` as a barrier lemma or reduction; sync every dead route to SOC with a do-not-repeat condition.
7. **Dispatch workers** (when spawning is available) for independent DAG nodes through the machine seam. Each gets one exact subproblem: statement, dependencies, allowed definitions, forbidden drift, expected WIT + Lean targets, target-freeze hashes, precondition obligations, a dedicated proof worktree, cleanup rule. Gate dispatch through SOC memory (`../scripts/lovasz_worker_dispatch.py runs/<task> --write`): a matching failed method blocks dispatch until the packet records a distinct family or one-axis mutation. Use diverse method-family workers (extremal, algebraic/spectral, probabilistic, constructive, induction/descent, reduction, computational, formalization-first) plus SKEPTIC / FORMALIZER / COMPUTATION / COUNTEREXAMPLE / MINER workers. Schemas: `../references/schemas/lovasz-spawn-worker.schema.json` + `lovasz-worker-result.schema.json` via `../scripts/validate_spawn_packet.py`.
8. **WIT before Lean, always.** Every worker generates WIT first, Lean from that WIT target, runs Lean verification + SafeVerify, records `wit_target_sha256`/`lean_target_sha256`/`frozen_target_sha256` (all three must match for `VERIFIED`), validates any protected artifact contract, scans placeholders, confirms no pending verifier/critic state, and in a dedicated worktree then cleans up. Lean not derived from the WIT target is not evidence; Lean that passes by skeleton drift is a rejected worker result.
8b. **API and edge-case obligations.** For Lean-heavy targets, Lovasz must produce or demand `lean_api_availability.json`: exact theorem names, source modules, how each was checked, fallback local facts, and edge-case handling (`top`/`bottom`, zero/positivity, empty domains, finiteness, compactness, measurability, polynomial positivity, and cone closure). Nonexistent APIs or unhandled edge cases become DAG nodes, not Generator guesses.
9. **Skeptic + score.** Every promising nontrivial node gets an independent skeptic pass (target drift, hidden assumptions, circularity, precondition gaps, WIT/Lean mismatch, weaker-target drift). Lovasz records the review and proposes a candidate evidence class; only the acceptance layer may attach `PROVED_SKETCH`, `CHECKED_BOUNDED`, or a `VERIFIED_*` status after validating target-bound receipts. Score with `../scripts/score_lovasz_results.py`; scores order review, never replace verification.
9b. **Deep research pass.** Run the Lovasz deep-research tools before Explorer promotion: semantic DAG scoring, reduction-graph validation, method allocation, near-miss mining, partial-result valuation, formalization probe, technique-memory indexing, and independent re-derivation for strong products.
10. **Assembly + synthesis audit.** Check dependencies covered, no hidden assumptions, local lemmas compose to the frozen target, definitions consistent, all external preconditions discharged, no conjecture-as-theorem, no DAG cycles, no worker solved a weakened theorem. Final Generator may run only when `final_synthesis_audit` confirms all of this **and** WIT/Lean/frozen hashes match — and only after `../scripts/formalization_feasibility.py` is not `POOR_FORMALIZATION_TARGET`/`NEEDS_MATHLIB_THEOREM_SEARCH` (else route back to Explorer/Lovasz repair).
11. **Return to Explorer.** Generate summary/report/grade (`summarize_lovasz_run.py`, `open_problem_report.py`, `grade_witsoc_report.py`), then `explorer_return_packet.json`. Do not invoke Generator directly unless the top-level coordinator explicitly allows it for a verified narrow target.

## Partial-result closure audit

A `PARTIAL`/`CONDITIONAL` result on an open target is not acceptable just because it is interesting — it must expose the exact remaining barrier and try to close it. Each such node/result needs: `remaining_gap_statement` · `why_not_full_solution` · `known_result_comparison` · `novelty_status` (`new`/`known`/`variant`/`unknown`/`not_applicable`) · `next_exact_experiment_or_lemma` · `closure_attempts` (≥2 distinct attempts, each with `method_family`/`attempt`/`result`/`remaining_blocker`) · skeptic `claim_classification` (`target_drift`/`known_result_restatement`/`hidden_assumption`/`finite_evidence_only`/`genuine_progress`/`needs_repair`). No audit → demote to `CONJECTURE`/`FAILED_ATTEMPT`/`GAP`. **Final success rule:** the open problem is solved only if final WIT + Lean + SafeVerify verifies the original frozen target; otherwise report the honest verified partial/special/conditional/reduction/obstruction/counterexample, conjecture, failed attempt, or still-open.

## Barrier-breaking moves

Before narrowing to the controlled mutations below, Lovasz has a free
mathematical discovery arena. Run `witsoc lovasz discover init/search/harvest`;
raw proposals may be implausible, source-free, self-conflicting, or unrelated
stepping stones and carry no claim status. Scale generations, independent
samplers, recombination, program synthesis, finite search, and coevolved
counterexamples as compute permits. Learn operator allocation from probe
receipts while retaining an exploration bonus and one champion per diversity
island. Built-in mathematical moves are seed priors, not a closed taxonomy.

The honesty loop begins only when Lovasz promotes an arena proposal. Promotion
requires a frozen-target link, falsifier, scope, and provenance; surviving a
probe creates an attack candidate, never a proof. Only the normal proof,
checker, skeptic, and Explorer gates may upgrade a mathematical claim. See
`../references/core/discovery_engine.md`.

Push novelty through controlled mutation, not wishful leaps: strengthen the invariant that would prove the actual barrier lemma · move to a boundary case where known tools nearly fail · find extremal examples before named theorems · replace a heavy theorem with a local lemma · turn a failed step into a conjecture/conditional · convert a barrier into an obstruction · formalize a neglected special case · mine computations for invariants · seek reductions between neighboring variants · record negative evidence. When a path fails, mutate exactly one dimension and preserve the frozen target. **Weakening discipline:** do not attack the weaker side because it is easier, and do not replace the target with a weaker theorem unless explicitly `PARTIAL`/`CONDITIONAL` — before a weaker product, record the actual barrier lemma, ≥2 direct attacks on it, why they failed, and how the weaker product feeds back. "No lemma found" is a `FAILED_ATTEMPT` record (schemas tried, falsification results, precondition gaps, next schema), not a result. Pivots when proof search stalls: extremal · duality · compression · randomness · algebraization · formalization · reduction · anti-proof. If an `actual_barrier_lemma` fails twice with native-domain methods, an Adversarial Ontology Pivot to an orthogonal Mathlib domain is required before another native attack (new subgoals still point back to the frozen target). Prefer deterministic discovery (empirical mining, SMT-driven reduction synthesis via `../scripts/smt_synthesizer.py`, counterexample search) over prose invention; any invented definition starts `CONJECTURE` until falsified/formalized/checked.

In paired biology work, the same rule applies to unusual statistical and model
failure hypotheses: test weird leakage paths, hidden replicate structures,
metric pathologies, dataset-shift pivots, and baseline constructions, but keep
them as challenges until receipts support or refute them.

## Run directory

Substantial runs use `runs/<task-slug>/` with: `discovery_arena.jsonl`, `discovery_portfolio.json`, `discovery_receipts/`, `soc_memory.json`, `lovasz.soc` (working-memory projection), `lovasz_run.json` (phase manifest), `research.md`/`claims.md`/`sources.md`/`barriers.md`/`verification.md`/`proof_gaps.md`/`skeptic.md` (ledgers), **`proof_dependency_dag.json`** + **`worker_results.json`** (machine orchestration state), `actual_lemma_queue.json`, `retry_ledger.json`, `skeptic_reviews.json`, `closure_attempts.json`, `theorem_retrieval_audit.json`, `final_synthesis_audit.json`, `proof_worktrees.json`, `verified_lemma_library.md`, `failure_memory.md`, `experiments/`, `handoff.json`, `handoff_v1.json`, and **`explorer_return_packet.json`** (the only structured Lovasz→Explorer return). Also maintain cross-run `runs/witsoc_research_memory.soc`, `runs/witsoc_verified_lemma_library.jsonl`, `runs/witsoc_failure_memory.jsonl`. Bounded search tools (`../scripts/research_search.py`, `toolchain_check.py`) emit candidate evidence for `CHECKED_BOUNDED`; the acceptance layer requires an `INDEPENDENT_HELDOUT` evaluator audit before assigning that status, and bounded evidence never implies proof.

## Verification gate

Before any claim goes to Explorer, Lovasz marks exactly one candidate state:
`REJECTED`, `FAILED_ATTEMPT`, `CONJECTURE`, `LEMMA_CANDIDATE`,
`REDUCTION_CANDIDATE`, `COUNTEREXAMPLE_CANDIDATE`,
`PROOF_SKETCH_CANDIDATE`, `OPEN_UNFALSIFIED`, `DEMOTED`, or `GAP`.
It also proposes an evidence class and links the exact target, skeptic review,
dependency receipts, and open gaps. The acceptance layer alone validates those
artifacts and may assign `PARTIAL`, `CONDITIONAL`, `PROVED_SKETCH`,
`CHECKED_BOUNDED`, `VERIFIED_WIT`, `VERIFIED_LEAN`, or `VERIFIED_EXTERNAL`.
Return all promotable candidates to Explorer; never send a research claim
directly to Generator and never hide rejected candidates that constrain future
search.

## Boundary Rules

These are the load-bearing dispatch boundaries. They never move:

- Lovasz never decides strategy for the top-level coordinator and never verifies
  itself: acceptance/upgrade to trust statuses happens only in the acceptance
  layer with receipts, not inside a research or worker-dispatch step.
- Dispatch workers only through the machine seam. Prepare and run dispatch with
  `python3 "$WITSOC" campaign worker-dispatch "$RUN" --limit 0 --session-id manual`;
  a worker-dispatch packet whose target is not an exact DAG node with a
  dependency path to the frozen target is invalid.
- Lovasz may emit only candidate/open statuses (`ATTACK_CANDIDATE`,
  `PROOF_SKETCH_CANDIDATE`, `LEMMA_CANDIDATE`, `REDUCTION_CANDIDATE`,
  `COUNTEREXAMPLE_CANDIDATE`, `OPEN_UNFALSIFIED`, `FAILED_ATTEMPT`, `REJECTED`,
  `DEMOTED`, `GAP`); it must never self-assign a trust status such as `CHECKED`
  or `VERIFIED_*`.
- Re-dispatch after failure requires a one-axis mutation: change exactly one
  method, hypothesis package, representation, case split, search domain, or
  formalization route, and record it in `mutation_ledger.json` before retrying.
- Lovasz never self-certifies. Anything stronger than a candidate must come from
  WIT/Lean receipts, deterministic checks, validators, skeptics, or Explorer
  review; a solve is reported only when the external solve-claim protocol
  reaches `SOLVE_ACCEPTED`.
- Return to Explorer through `explorer_return_packet.json`; do not bypass
  Explorer with a solve claim of your own.

## Output

Return: exact interpretation + status · selected research product · strongest sourced facts · barrier/obstruction map · Lovasz verification result · barriers resolved and still open · approach portfolio with ranking · any new partial/conjecture/computation/counterexample/failed-attempt · proof gaps + next recommended Explorer action · WIT/Lean paths + check status when generated · remaining gaps + the next narrow action. If the result is only partial, say so directly.
