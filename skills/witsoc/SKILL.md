---
name: witsoc
description: >
  General mathematical and computational-biology research orchestration. Use
  for target understanding, open-problem reduction, theorem and premise search,
  proof/disproof, WIT and Lean generation or repair, perturbation biology,
  target validation, omics evidence, and scientific claims whose correctness
  depends on chained premises. Coordinates Explorer, Lovasz, Generator, and
  Durbin with immutable targets, typed memory, evidence graphs, and receipts.
---

# Witsoc

## Canonical Runtime

Every serious run uses one immutable target, one typed research graph, one SOC
store, and one terminal-state contract:

```bash
python3 scripts/witsoc.py target init --source-file target.txt --output runs/<task>/canonical_target.json
python3 scripts/witsoc.py research-graph init runs/<task>/research_graph.json --target-sha256 <canonical-sha256>
python3 scripts/witsoc.py soc-memory init runs/<task>
python3 scripts/witsoc.py adapt runs/<task> --budget 20 --workers 4 --apply
python3 scripts/witsoc.py drive runs/<task> --finalize
python3 scripts/witsoc.py status-lattice runs/<task> --json
```

`drive` is the completion boundary. Exit `0` means deterministic acceptance
passed. Exit `3` means external Intelligence Bus replies are required. Exit `4`
means blocked or budget-exhausted. Waiting workers, critics, or verifiers never
count as success. Use `python3 scripts/witsoc.py map` for the installed command
surface and `reference-integrity` before release. Run
`python3 scripts/witsoc.py regression-audit` before packaging or changing a
shared gate; it executes domain-neutral trust-boundary and integration fixtures.

Witsoc is the top-level research workflow. It owns four internal subskills and decides which one runs, in what order, and when to stop. **Read this whole file before a serious run; it is the operating contract.** Deep detail lives in `references/`; load a reference only when the step below sends you there.

- `witsoc-explorer/SKILL.md` — intake, target freeze, status triage, search, premise/lemma discovery, counterexample pressure, proof-path selection, and **final arbitration** of whether Lovasz or Generator may proceed.
- `witsoc-research-lovasz/SKILL.md` — barrier attack on OPEN/blocked targets as a verification-driven research director (proof-DAG decomposition, semantic DAG scoring, reduction graphs, method allocation, near-miss mining, parallel workers, one-axis mutations, computational search). Returns to Explorer; never routes itself to Generator.
- `witsoc-bio/SKILL.md` — Durbin, the computational-biology research director for perturbation biology, virtual-cell evaluation, target validation, omics evidence, biological contradiction/confounder search, and joint Durbin-Lovasz biological/statistical claim synthesis.
- `witsoc-generator/SKILL.md` — `.wit` artifact generation/repair, structural checks, verifier context, receipts, optional Lean. Never upgrades claim status.

## SOC Memory Is Core

SOC is WITSOC's compact working memory. `soc_memory.json` is the typed source of
truth; `lovasz.soc` is its generated readable projection. Every serious run initializes and
validates SOC even when the active route is Explorer-only, Durbin, or
Generator repair, because failures, reusable insights, current barriers, and
queue state must survive across subskill boundaries. Use:

```bash
python3 scripts/witsoc.py soc memory init runs/<task>
python3 scripts/witsoc.py validate-soc-memory runs/<task>
```

All subskills must read SOC before repeating an approach and must append
failures with `do_not_repeat` conditions. Decisions link the SOC insight ids
that influenced them, and checked outcomes are attributed back to those
decisions. Scoped opposite insights remain explicit contradictions rather than
being merged away. SOC is not proof evidence by itself; it ranks attention and
never certifies a claim.

The subskills are nested here; read the nested `SKILL.md` directly, do not look for sibling top-level skills. When a task routes through Lovasz the user-facing progress line must read exactly:

```text
Using witsoc with witsoc-explorer -> witsoc-research-lovasz -> witsoc-explorer.
```

When a serious biology task routes through Durbin and Lovasz the user-facing progress line must read exactly:

```text
Using witsoc with witsoc-explorer -> witsoc-bio (Durbin) <-> witsoc-research-lovasz -> witsoc-bio (Durbin) -> witsoc-explorer.
```

## Mandatory usage evidence (run before any mathematical work)

The platform (and any external audit) checks for these artifacts deterministically; a run without them is scored as not having used Witsoc at all, regardless of the mathematics. For every nontrivial task, run one command from the task workspace:

```bash
WITSOC_SCRIPTS="$(dirname "$("$PLANE_TOOL_BIN" skill-which witsoc/scripts/route.py 2>/dev/null || echo "${WITSOC_SKILL_DIR:-$HOME/.openscientist/strings/skills/witsoc}/scripts/route.py")")"
bash "$WITSOC_SCRIPTS/usage_evidence.sh" "<original user task text>" --workspace "$PWD"
```

It writes `witsoc_route_state.json` (the deterministic route decision — must exist in every audited run; also mirrored to the session dir), `witsoc_skills_list.txt` (captured skills-list output; if the CLI is unavailable, call the platform skills-list tool and append its successful output — missing skills-list evidence is an audit failure), and `witsoc_usage_evidence.json`. It also prints a worker instruction block: every spawned worker/sub-agent prompt must contain that block verbatim, so each worker instruction names the selected Witsoc subskill and the route-state path. A worker dispatched without it fails the usage audit.

## The Loop (run this for every serious task)

```text
INTAKE -> EXPLORER_TRIAGE
EXPLORER_TRIAGE -> DIRECT_ANSWER | EXPLORER_PROOF_PLAN | LOVASZ_BARRIER_PACKET
LOVASZ_BARRIER_PACKET -> LOVASZ_ATTACK -> EXPLORER_REVIEW
EXPLORER_REVIEW -> LOVASZ_BARRIER_PACKET | GENERATOR_HANDOFF | HONEST_STOP
GENERATOR_HANDOFF -> GENERATE_WIT -> CHECK_WIT -> BUILD_CONTEXT -> OPTIONAL_LEAN -> REPORT
GENERATOR_FAILURE -> EXPLORER_REVIEW
BIO_TARGET -> DURBIN_AUDIT -> LOVASZ_STAT_AUDIT -> DURBIN_JOINT_SYNTHESIS -> EXPLORER_REVIEW
```

Repeat `EXPLORER -> LOVASZ -> EXPLORER` until exactly one stop state holds: solved/routine plan ready · verified partial/special/conditional result ready · checked computational or counterexample result ready · formalizable narrow lemma ready · **no honest progress path remains**. Then, and only then, may Generator run.

One state per turn. Do not skip a state, do not re-run a state that already produced its artifact, and do not answer while a required state is still pending. `references/core/run_playbook.md` gives the concrete preflight commands and per-state validators; `references/core/core_efficiency_map.md` gives the leanest high-assurance path. For serious open-problem work, also load `references/core/open_problem_acceleration.md` and `references/core/lovasz_deep_research.md`, then maintain `open_problem_acceleration.json`: understanding map, reduction map, method-family portfolio, falsification ladder, barrier lemmas, formalization plan, kill criteria, and next three moves. Run preflight at the start and the production-readiness block before reporting. The composed local final gate is `python3 scripts/witsoc.py finalize runs/<task> --final-answer runs/<task>/final_answer.md --changed-only`; it is WITSOC-only and does not depend on backend or theater services.

## Hard gates (the turn-discipline rules)

**Discovery-attempt gate.** For any prompt asking to prove / disprove / solve / make progress on / deep-run an open-style target, classification is NOT a finish. If Explorer (or a worker) concludes `OPEN`, `UNSOLVED`, `UNCONFIRMED`, "unsupported by known results", "requires a new theorem", or "blocked by a structural gap", Explorer MUST write a Lovasz barrier packet and route to Lovasz before the run is complete. "Known results do not prove it" is a *finding*, not a completed run. A single prose barrier artifact does not satisfy this — a real campaign needs `actual_lemma_queue`, a proof-DAG, barrier-attack records, worker evidence when available, skeptic review, and a retry ledger.

The run is INCOMPLETE (reject it) if all hold: the user asked for a proof/disproof/deep attempt · the problem was classified open/unsupported · no Lovasz proof-DAG/barrier attack was attempted · no concrete operational blocker prevented Lovasz dispatch.

**Generator-forbidden gate.** Generator may NOT run when: the target is open/blocked and no Lovasz return packet exists · the accepted product is only a conjecture · target hashes disagree with no mutation record · Explorer has not authorized artifact generation · formalization feasibility is `POOR_FORMALIZATION_TARGET` · the proof DAG has an open dependency the claimed theorem needs. Load `references/core/generator_gate.md` before invoking Generator on a nontrivial target.

**Formal-locked-artifact gate.** If a task supplies a protected skeleton or guard markers, WITSOC enters `formal_locked_artifact` mode (`references/core/protected_artifact.md`). Generator may edit only declared proof bodies. Global helper lemmas, imports, opens, scoped opens, `set_option`, namespace/end edits, theorem-signature edits, guard-marker formatting changes, and protected whitespace drift are forbidden. Nontrivial Mathlib/API dependencies require `lean_api_availability.json`; guessed lemma names are a Lovasz/Explorer premise-search problem, not a Generator retry.

**Evaluator-adversary gate.** An executable command is not a research evaluator
until `evaluator_factory.py` binds it to the exact target, candidate, and
evaluator hashes and audits independent authorship, two-sided outcomes,
semantic measurements, held-out separation, contamination controls, and
adversarial cases. Trivial or constant-exit probes are rejected.
`CHECKED_BOUNDED` requires an `INDEPENDENT_HELDOUT` audit; output wording is
never an oracle.

**Typed acceptance-evidence gate.** Any result-asserting status (`PARTIAL`,
`CONDITIONAL`, `PROVED_SKETCH`, `CHECKED_*`, or `VERIFIED_*`) requires an
evidence object with an explicit mechanism and scope, a lowercase target
SHA-256, and current hashed receipts. Bare `VERIFIED` is forbidden. A
`VERIFIED_LEAN` claim additionally requires a matching Generator package,
target freeze, exact-current-source clean verification, kernel result,
independence fields, protected validation when applicable, and formalization
fidelity. `status_lattice.py` enforces this and `finalize` invokes it.

**Two-stage solve gate.** A solve of the named problem is claimed in two stages, never one: `MATHEMATICAL_SOLVE` (the proof DAG passes `validate_mathematical_solve.py` — complete, gap-free, target-frozen) then `FORMAL_SOLVE` (a Lean receipt validated by `validate_lean_receipt.py`, so placeholder/environment-only Lean cannot stand in). Neither stage self-certifies. Report a solve ONLY when `solve_claim_protocol.py` reaches `SOLVE_ACCEPTED` — which additionally requires an independent re-derivation on the same frozen target hash and a `NOVEL_CANDIDATE` novelty verdict. Until then report the honest partial status; **no agent upgrades a claim to a solve on its own authority.**

**Biology joint-review gate.** Serious biological claims, perturbation/virtual-cell evaluations, target-validation claims, and omics-derived mechanism claims must not be reported as strongly supported until Durbin and Lovasz both sign off. Durbin owns biological context, endpoint relevance, controls, contradiction/confounder search, and interpretation. Lovasz owns estimand validity, statistics, baselines, leakage, uncertainty, and algorithmic claims. Strong status requires `joint_synthesis.json` plus Explorer arbitration; disagreement stays as a gap.

**Protected-target gate.** The statements, definitions, and signatures a task hands you are the frozen target (`references/core/target_freeze.md`, `references/core/protected_artifact.md`). Fill in proof bodies only; never rename, restate, weaken, strengthen, comment out, or delete a given declaration, and never add axioms to close a goal. Every nontrivial Generator handoff carries `target_protection.original_statement`, `frozen_target_sha256`, `statement_tampering_forbidden=true`, and authorized mutations if any. Every formal artifact that contains protected statement text should also carry `protected_artifact_contract.json`; Generator repairs use `protected_body_patcher.py`, then run `validate_protected_artifact.py` and `validate_no_placeholders.py`. If a statement looks wrong or unprovable, that is a finding to report, not a license to edit it. A proof that "passes" only by altering the target is `REJECTED`, not a solve.

**Verification-honesty gate.** Every claim that a build or verifier passed must be backed by a captured receipt — the command, exit status, and concluding output lines, from a run that postdates the last edit — and quoted in the final message (`references/core/status.md`, `references/core/safeverify.md`). No official verifier / `lake build` run without a stated repair hypothesis; obey the repair budgets in `references/core/lean_verification.md` and record nontrivial Lean repair in `references/core/generator_lean_fix_cycle.md` (3 same-class failures → back to the sketch; distinct method families exhausted → `references/core/creative_leaps.md`). Pending critic/verifier/worker state blocks success language; run `validate_pending_state.py` and `validate_final_receipt_claim.py` when final answers cite success. A false success claim is worse than an honest failure report.

**Subskill boundaries.** Explorer arbitrates every Lovasz/Durbin/Generator return and does not write final `.wit` except for very small tasks. Lovasz does not do intake and does not route to Generator; in paired biology work it returns its audit to Durbin for joint synthesis before Explorer review. Durbin does not override Lovasz on statistical or mathematical validity. Generator avoids broad theorem search, never upgrades claim status, and returns mathematical blockers to Explorer. Top-level Witsoc coordinates the loop and decides when to return to Explorer.

## Routing

Intake always starts at top-level `witsoc`; serious work then starts with Explorer.

| Task | Route |
|---|---|
| Simple math answer | Answer directly at top-level with a clear derivation. |
| Hard proof exploration | `witsoc-explorer`: Phase-0 profile, freeze target, triage status, map ontology, rank theorems, backward-chain, run falsification/obstruction checks, EV-rank sketches, emit `runs/<task>/handoff.json` (+ strict `handoff_v1.json` when Generator is needed). |
| Open / Erdős-style problem | `witsoc-explorer` first → write `open_problem_acceleration.json` → if OPEN/blocked, write a barrier packet → `witsoc-research-lovasz` attacks → Explorer reviews and loops, demotes, stops, or authorizes Generator for a narrow accepted result. |
| Deep run on an open target | Explorer → acceleration record → **mandatory** Lovasz → Explorer. A "still open/unsupported" report is complete only if Lovasz already attempted barrier-breaking and Explorer reviewed it, or a concrete `lovasz_dispatch_blocker` is recorded. |
| Serious computational-biology claim | Explorer freezes organism/context/perturbation/assay/dataset/model/baseline/split/falsification conditions → `witsoc-bio` (Durbin) audits biology → Lovasz audits estimand/statistics/baselines/leakage/model claims → Durbin writes joint synthesis → Explorer arbitrates. |
| Lightweight biology explanation | `witsoc-bio` may answer directly, but it must not promote a strong empirical/model claim without the Durbin-Lovasz route. |
| Counterexample search | `witsoc-explorer` + computation; minimize and verify before presenting. |
| Premise / lemma discovery | `witsoc-explorer` supply search + dependency planning. |
| WIT generation | Explorer freezes/accepts the target first (nontrivial), then `witsoc-generator`. Existing `.wit` inspection/repair may start at Generator. |
| User explicitly asks for WIT / `.wit` | Explorer judges the target first (unless `.wit` repair); Generator is then mandatory and must emit a `.wit` or a concrete blocker. Do not answer with only prose/exploration/Lean. |
| WIT + Lean requested | Explorer → Generator for routine targets; Explorer → Lovasz → Explorer → Generator for open/blocked. Generator generates/checks WIT, generates Lean from that frozen WIT target, attempts verification, reports exact status. |
| WIT repair after rejection | `witsoc-generator` for edits; call Explorer when rejected steps need new premises/lemmas/strategy. |
| Lean build error | `witsoc-generator` repair: classify, cite compiler evidence, record `lean_fix_cycle.json`, minimal fix with a stated hypothesis, retry without changing the frozen target. Three same-class failures without reducing the obligation → stop local repair, return to the sketch level (Explorer) before any further verifier runs; see `references/core/failure_recovery.md` and `references/core/generator_lean_fix_cycle.md`. |
| Conventional approaches exhausted | `references/core/creative_leaps.md` — required before concluding failure: ≥5 genuinely distinct unconventional candidates, cheap-test the top 2-3, promote survivors to normal sketches. |
| Structural check / verifier context / semantic verify | Deterministic `wit check` / `wit verify` / skeptical verifier + `wit receipt`; **never** treat check/verify as semantic proof; **no LLM** for structural checks, context, target-freeze, status, or receipt parsing. |

Operating principles: prefer deterministic tooling · strong models for discovery/repair, skeptical models for verification · never substitute confidence for receipts · freeze the target before serious work and reject unexplained hash drift · accept claims only through the claim-acceptance contract · state the achieved quality level before reporting.

## Unconventional Idea Policy

Use the two-plane engine in `references/core/discovery_engine.md`. Raw search in
`discovery_arena.jsonl` is deliberately outside claim acceptance so Lovasz and
Durbin can explore implausible and serendipitous ideas without first making
them defensible. Only harvested candidates cross into the typed probe plane;
unprobed candidates enter the research graph only as `OPEN` hypotheses, while
receipt-backed survivors may become attack candidates. This separation must
never be misread as permission to report unchecked mathematics or biology.

Prefer scalable meta-methods over an ever-growing expert rulebook: quality-
diversity search, recombination, program synthesis, coevolved falsifiers,
outcome learning, and larger evaluator throughput. Built-in domain operators
seed the search but do not define its limits. Initialize with `witsoc discover
init`, expand with `witsoc discover search`, synthesize and audit evaluators
with `witsoc evaluator-factory`, rank probes with `witsoc explorer
information-gain`, execute them durably with `witsoc schedule`, and promote
only reconciled receipts with `witsoc discover promote`. The full contract is
`references/core/scalable_research_runtime.md`.

WITSOC should actively generate unconventional mathematical and biological
ideas: odd reductions, ontology pivots, neglected boundary cases, adversarial
examples, cross-domain analogies, negative-space hypotheses, weird perturbation
mechanisms, and model-failure probes. This is a discovery obligation, not a
license to overclaim. Every unconventional idea starts as
`CONJECTURE`/`ATTACK_CANDIDATE`/`BIO_CONJECTURE` until it survives the same
target-freeze, source, falsification, receipt, Lovasz, Durbin, Generator, and
Explorer gates as conventional ideas.

When conventional ideas run out, creative mode is mandatory, not optional:
`references/core/creative_leaps.md` is the operational protocol. Its triggers —
two or more distinct conventional method families exhausted, the same failure
class repeating three times, the verifier-run budget spent, or "no standard
route" concluded — require generating at least 5 genuinely distinct
unconventional candidates (reformulations, distant machinery, computation-led
guessing, formalization-side dodges), ranked by cheapness of falsification,
with the top 2-3 cheap-tested and survivors promoted to normal sketches. A
target attacked only conventionally may not be reported as a final failure.
Explorer records this in `explorer_ideation.json`/`creative_leaps.json` and
validates it with `validate_explorer_ideation.py`.

Computational-biology additions must not weaken mathematical capability. Pure
math routes keep the existing Explorer -> Lovasz -> Explorer -> Generator
contract, status lattice, WIT-before-Lean discipline, and open-problem gates.
Bio may reuse Lovasz for statistical/mathematical audits, but bio-specific
heuristics, statuses, fixtures, and source gates must stay under
`references/witsoc-bio/` or explicitly marked paired-biology sections.

## Contracts

**Target freeze** (`references/core/target_freeze.md`): maintain a frozen target statement + target hash; record any change in `target_mutation.json`/`target_mutations.jsonl` with old/new hash, mutation kind, reason, authorization, and whether it weakens the original. Run `validate_target_protection.py` before final reporting.

**Claim acceptance** (`references/core/claim_acceptance.md`): a claim is accepted only with exact statement, stable claim/DAG-node id, matching target hash, dependency path to target, legal status transition, evidence receipt or checked artifact, skeptic review for strong claims, and a registered artifact when one is cited. Anything else is `OPEN`, `GAP`, `CONJECTURE`, `FAILED_ATTEMPT`, `REJECTED`, `PARTIAL`, or `CONDITIONAL` — never a full solution.

**Explorer → Generator handoff** is mandatory before writing WIT on nontrivial problems: Explorer pins the full profile (ontology map, ranked theorems, backward chains, falsification results, obstructions, selected target, hypotheses/definitions, likely counterexamples, lemma plan, mutation tracker, sketches, EV scores, freeze hashes), writes `runs/<task>/handoff.json` and strict `runs/<task>/handoff_v1.json`, both validated before Generator runs. Generator reads only `handoff_v1.json` and never invents truth beyond it. For Lovasz work, `validate_handoff.py` also enforces the proof-DAG and worker-result invariants.

## Quality levels (`references/core/production_gates.md`)

`L0_DIRECT` direct answer · `L1_SKETCH` informal sketch · `L2_CHECKED_DERIVATION` deterministic/bounded/structural check · `L3_WIT_ARTIFACT` · `L4_WIT_LEAN_ATTEMPTED` · `L5_WIT_LEAN_VERIFIED` · `L6_RESEARCH_PRODUCT` (Lovasz product with checked/verified artifacts + Explorer review, or Durbin-Lovasz biological/statistical joint synthesis + Explorer review). **The final answer must never imply a higher level than the run achieved.**

## Status honesty

Use granular `VERIFIED_WIT`/`VERIFIED_LEAN`/`VERIFIED_EXTERNAL` only with the
matching formal/verifier evidence; bare `VERIFIED` is invalid. Use
`CHECKED_BOUNDED` only with an independent held-out evaluator audit and
`CHECKED_SYMBOLIC` only with a symbolic receipt. `PROVED_SKETCH`, `PARTIAL`, and
`CONDITIONAL` require typed target-bound evidence and independent skeptical
review; `CONJECTURE`, `FAILED_ATTEMPT`, and `REJECTED` remain honest candidate
states.

User-facing verification labels (do not write bare "verified" unless the sentence names one of these):

- `STRUCTURE_OK` — `wit check` / structural validation passed.
- `CONTEXT_BUILT` — verifier context generated (not semantic proof).
- `RECEIPT_ACCEPTED` — `.wit.receipt.json` exists and accepted verdicts cover the obligations.
- `LEAN_VERIFIED` — Lean/Lake verification passed and SafeVerify/target-freeze passed.
- `OPEN` / `GAP` / `PARTIAL` / `CONDITIONAL` / `CONJECTURE` / `FAILED_ATTEMPT` / `REJECTED` — no full verified proof of the frozen target.

Any claim that an official verifier or build passed must be backed by a captured receipt — the command, exit status, and concluding output lines, from a run that postdates the last edit to the checked files — and the receipt must be quoted in the final message. Missing, stale, or rejecting receipt → report the run as failed; a false success claim is scored worse than an honest failure.

## Explicit WIT request contract

If the user asks for "WIT code" / ".wit" / "provide WIT" / "WIT + Lean", producing WIT is mandatory — do not satisfy it with only an exploration summary, prose proof, sketch, or Lean. In a deep run the orchestrator must dispatch a Generator step that writes the `.wit`. Whenever a `.wit` is generated/updated, activate the Witsoc plugin iframe and open the file. If WIT cannot be produced, return `GAP`/`FAILED_ATTEMPT`/`REJECTED` with the exact blocker and the best partial sketch. If Lean is also requested, generate it from the WIT target, not an unrelated statement. After a structurally valid `.wit` exists and Lean was not requested, ask whether to generate and `lake build` a Lean 4 proof from it.

## Preflight, scripts, and production readiness

The full command sequences live in **`references/core/run_playbook.md`** — its Witsoc-Preflight block (route + handoff validators, `witsoc_route_state.json`, `generator_authorized` check) and its Lovasz/Generator production-readiness blocks. The efficient default route lives in **`references/core/core_efficiency_map.md`**. Run preflight at the start of a serious run and the production-readiness block before reporting. Durbin runs additionally use `references/witsoc-bio/scripts/init_durbin_run.py`, `validate_bio_claim.py`, `advance_durbin_phase.py`, `validate_durbin_run.py`, and for open-answer biology `open_answer_readiness_gate.py`. The CLI entrypoint is `scripts/witsoc.py` (route/init/check/verify/status/artifacts/validation/production-check); register every generated artifact with `witsoc.py artifacts register …` so the plugin reads the registry first. If `witsoc_route.json` sets `required_followup: witsoc-research-lovasz`, a status-only open-problem report is not complete. If `witsoc_route_state.json` sets `joint_bio_required: true`, a strong biology report is not complete until Durbin-Lovasz synthesis and Explorer arbitration are done. If `witsoc_route_state.json` has `generator_authorized: false`, Generator may not write yet.

The shared engines and ownership matrix (import-only `services/`, witsoc-owned `bridges/`, no-merge rules) are documented in **`references/core/substrate.md`**. Other shared protocols — load only what the current step needs: `routing.md`, `claim_acceptance.md`, `target_freeze.md`, `protected_artifact.md`, `artifact_policy.md`, `generator_gate.md`, `production_gates.md`, `status.md`, `handoff.md`, `failure_recovery.md`, `open_problem.md`, `open_problem_acceleration.md`, `lovasz_deep_research.md`, `scalable_research_runtime.md`, `research_quality_contract.md`, `exploration_strategy.md`, `research_machinery.md`, `repair.md`, `goal_cache.md`, `safeverify.md`, `lean_verification.md`, `generator_lean_fix_cycle.md`, `core_efficiency_map.md`, `tooling.md`, `plugin_integration.md` (all under `references/core/`), plus the strict handoff schemas under `references/schemas/`.

## Platform services (probe first, degrade honestly)

Run `python3 scripts/services/fuel.py --backend` once per session: it enumerates what the platform actually offers this JWT (Herald read/**write**, Loogle, remote E2B Lean, literature pools, budgets via `/auth/usage`) and caches it for every consumer. The mechanical seams that build on it: `scripts/falsification_battery.py` (run against every frozen target BEFORE Lean effort), `scripts/services/lemma_pool.py` (federated verified-lemma pool — local SQLite + kernel-verified-only Herald pushes; premise selection reads it first), `scripts/services/proof_harvest.py` (every kernel-verified proof compounds into proof/pattern/lemma banks — engine paths call it automatically), `scripts/remote_verify.py` + `scripts/remote_lean_burst.py` (E2B soft-signal verification and burst compiles — NEVER certification), `scripts/personas.py --publish` then `scripts/dispatch_prompts.py <run>` (typed worker fleet + duration-aware Agent calls: foreground probes uncapped in one message, background workers within the cap, standing disproof lane), `scripts/graph_memory.py` (cross-run GraphRAG mirror), `scripts/campaign_budget_gate.py check` (now budget-aware: respect its tier recommendation near the daily LLM cap). For harness-enforced campaign loops enter via `/flow:witsoc-flow` (see `witsoc-flow/SKILL.md`; write `runs/current_flow_target.json` first — the entry ignores arguments).

## System-Friendly Resource Policy

WITSOC must adapt to the machine it is running on. Probe available RAM, CPU,
disk, toolchain state, and platform services before expensive work; then choose
the smallest viable plan. Never assume a fixed workstation size, GPU, cloud
service, or atlas-scale local storage. If the current machine cannot support a
requested run, narrow the target, reduce concurrency, use smaller fixtures or
subsets, disable optional workers, and report a concrete `compute_blocker`
instead of swapping until unusable or silently weakening the claim.

For Lean/WIT work, all Lean execution stays under `scripts/services/ram_governor.py`
(run it directly for status). Use one shared Mathlib REPL session when available,
slot-gate concurrent builds, and cap heap use with the governor settings. Tuning
knobs are optional and should reflect the actual host: `WITSOC_RAM_BUDGET_GB`,
`WITSOC_LEAN_SLOTS`, `WITSOC_LEAN_PROC_GB`, `WITSOC_REPL_RECYCLE_GB`, and
`WITSOC_LEAN_MAX_MB`. On small machines prefer structural WIT checks, smaller
formalization obligations, fewer workers, and honest `LEAN_NOT_RUN`/`GAP`
statuses over forcing a full Lean build.

## Failure-recovery routing

Lean syntax/import/namespace/context failure → Generator repair · WIT lint/structural failure → Generator repair · missing lemma → Explorer repair (Lovasz if it is an open/blocked barrier) · DAG integrity failure → Lovasz repair · target mismatch → Explorer target-freeze repair · poor formalization feasibility → Explorer/Lovasz decomposition · worker disagreement → skeptic review + merge · repeated same failure class → apply `references/core/failure_recovery.md` before stopping.

## Before final answer

Apply `references/core/production_gates.md`: route state checked · target-protection validation passed · protected-artifact validation passed when formal artifacts exist · no placeholders in final formal artifacts · no pending critic/verifier/worker state · frozen target + hash stated · hash consistency checked · typed acceptance-evidence/status-lattice validation passed · final status wording and receipt claim audited · artifacts registered · exact WIT/Lean status and Generator receipt gate · Lovasz return packet reviewed when Lovasz ran · Durbin-Lovasz joint synthesis reviewed when Durbin ran · Generator authorization checked when artifacts were generated · report grade or gaps stated when Lovasz ran · achieved quality level stated. Production is complete only with no unexplained target mismatch, no illegal status upgrade, no accepted claim without evidence, no unregistered cited artifact, no skipped required Lovasz/Durbin phase, no unresolved placeholders, and no Generator handoff before Explorer authorization.

## Default output

Small answer: result + reasoning. Serious task: exact interpretation · achieved quality level · exploration summary (if used) · open-problem status (if applicable) · sketch/partial/conjecture/failed/gap status (if applicable) · `.wit` path (or inline WIT when requested) · structural-check result · verifier-context path/summary · receipt path (if any) · current status · failure output if stopped · next useful step.

End every serious response with this block (use `none`/`not run` explicitly, never omit a field):

```text
Artifacts:
- WIT: <path|none>
- Lean: <path|none>
- Receipt: <path|none>
- Status: STRUCTURE_OK=<yes/no/not run>; CONTEXT_BUILT=<yes/no/not run>; RECEIPT_ACCEPTED=<yes/no/not run>; LEAN_VERIFIED=<yes/no/not run>
- Plugin: <opened/open failed/not attempted>
```

If Lean is requested, use `witsoc-generator`, prefer LSP/REPL/per-file checks during repair, and return Lean only after final `lake build` + SafeVerify succeed. If Lean repair is blocked, say `Lean code generation failed`.
