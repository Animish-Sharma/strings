---
name: witsoc
description: General mathematics skill and subsystem for OpenScientist. Use for every type of mathematical work: problem solving, proof generation, proof critique, disproof, theorem formalization, premise search, supply search, lemma discovery, proof automation, Lean/Coq-adjacent planning, algorithms, complexity reductions, algebra, analysis, topology, number theory, combinatorics, graph theory, geometry, probability, logic, and scientific arguments whose correctness depends on chained premises. Contains internal subskills `witsoc-research-lovasz` for open-problem research programs, `witsoc-explorer` for mathematical exploration, and `witsoc-generator` for WIT proof artifacts; can also work directly for small math questions.
metadata:
  skill-author: OpenScientist
category: research
---

# Witsoc

Witsoc is the top-level mathematics workflow. It owns three internal subskills and decides which one runs, in what order, and when to stop. **Read this whole file before a serious run; it is the operating contract.** Deep detail lives in `references/`; load a reference only when the step below sends you there.

- `witsoc-explorer/SKILL.md` — intake, target freeze, status triage, search, premise/lemma discovery, counterexample pressure, proof-path selection, and **final arbitration** of whether Lovasz or Generator may proceed.
- `witsoc-research-lovasz/SKILL.md` — barrier attack on OPEN/blocked targets as a verification-driven research director (proof-DAG decomposition, parallel workers, one-axis mutations, computational search). Returns to Explorer; never routes itself to Generator.
- `witsoc-generator/SKILL.md` — `.wit` artifact generation/repair, structural checks, verifier context, receipts, optional Lean. Never upgrades claim status.

The subskills are nested here; read the nested `SKILL.md` directly, do not look for sibling top-level skills. When a task routes through Lovasz the user-facing progress line must read exactly:

```text
Using witsoc with witsoc-explorer -> witsoc-research-lovasz -> witsoc-explorer.
```

## The Loop (run this for every serious task)

```text
INTAKE -> EXPLORER_TRIAGE
EXPLORER_TRIAGE -> DIRECT_ANSWER | EXPLORER_PROOF_PLAN | LOVASZ_BARRIER_PACKET
LOVASZ_BARRIER_PACKET -> LOVASZ_ATTACK -> EXPLORER_REVIEW
EXPLORER_REVIEW -> LOVASZ_BARRIER_PACKET | GENERATOR_HANDOFF | HONEST_STOP
GENERATOR_HANDOFF -> GENERATE_WIT -> CHECK_WIT -> BUILD_CONTEXT -> OPTIONAL_LEAN -> REPORT
GENERATOR_FAILURE -> EXPLORER_REVIEW
```

Repeat `EXPLORER -> LOVASZ -> EXPLORER` until exactly one stop state holds: solved/routine plan ready · verified partial/special/conditional result ready · checked computational or counterexample result ready · formalizable narrow lemma ready · **no honest progress path remains**. Then, and only then, may Generator run.

One state per turn. Do not skip a state, do not re-run a state that already produced its artifact, and do not answer while a required state is still pending. `references/core/run_playbook.md` gives the concrete preflight commands and per-state validators; run its preflight at the start and its production-readiness block before reporting.

## Hard gates (the turn-discipline rules)

**Discovery-attempt gate.** For any prompt asking to prove / disprove / solve / make progress on / deep-run an open-style target, classification is NOT a finish. If Explorer (or a worker) concludes `OPEN`, `UNSOLVED`, `UNCONFIRMED`, "unsupported by known results", "requires a new theorem", or "blocked by a structural gap", Explorer MUST write a Lovasz barrier packet and route to Lovasz before the run is complete. "Known results do not prove it" is a *finding*, not a completed run. A single prose barrier artifact does not satisfy this — a real campaign needs `actual_lemma_queue`, a proof-DAG, barrier-attack records, worker evidence when available, skeptic review, and a retry ledger.

The run is INCOMPLETE (reject it) if all hold: the user asked for a proof/disproof/deep attempt · the problem was classified open/unsupported · no Lovasz proof-DAG/barrier attack was attempted · no concrete operational blocker prevented Lovasz dispatch.

**Generator-forbidden gate.** Generator may NOT run when: the target is open/blocked and no Lovasz return packet exists · the accepted product is only a conjecture · target hashes disagree with no mutation record · Explorer has not authorized artifact generation · formalization feasibility is `POOR_FORMALIZATION_TARGET` · the proof DAG has an open dependency the claimed theorem needs. Load `references/core/generator_gate.md` before invoking Generator on a nontrivial target.

**Two-stage solve gate.** A solve of the named problem is claimed in two stages, never one: `MATHEMATICAL_SOLVE` (the proof DAG passes `validate_mathematical_solve.py` — complete, gap-free, target-frozen) then `FORMAL_SOLVE` (a Lean receipt validated by `validate_lean_receipt.py`, so placeholder/environment-only Lean cannot stand in). Neither stage self-certifies. Report a solve ONLY when `solve_claim_protocol.py` reaches `SOLVE_ACCEPTED` — which additionally requires an independent re-derivation on the same frozen target hash and a `NOVEL_CANDIDATE` novelty verdict. Until then report the honest partial status; **no agent upgrades a claim to a solve on its own authority.**

**Subskill boundaries.** Explorer arbitrates every Lovasz/Generator return and does not write final `.wit` except for very small tasks. Lovasz does not do intake and does not route to Generator. Generator avoids broad theorem search, never upgrades claim status, and returns mathematical blockers to Explorer. Top-level Witsoc coordinates the loop and decides when to return to Explorer.

## Routing

Intake always starts at top-level `witsoc`; serious work then starts with Explorer.

| Task | Route |
|---|---|
| Simple math answer | Answer directly at top-level with a clear derivation. |
| Hard proof exploration | `witsoc-explorer`: Phase-0 profile, freeze target, triage status, map ontology, rank theorems, backward-chain, run falsification/obstruction checks, EV-rank sketches, emit `runs/<task>/handoff.json` (+ strict `handoff_v1.json` when Generator is needed). |
| Open / Erdős-style problem | `witsoc-explorer` first → if OPEN/blocked, write a barrier packet → `witsoc-research-lovasz` attacks → Explorer reviews and loops, demotes, stops, or authorizes Generator for a narrow accepted result. |
| Deep run on an open target | Explorer → **mandatory** Lovasz → Explorer. A "still open/unsupported" report is complete only if Lovasz already attempted barrier-breaking and Explorer reviewed it, or a concrete `lovasz_dispatch_blocker` is recorded. |
| Counterexample search | `witsoc-explorer` + computation; minimize and verify before presenting. |
| Premise / lemma discovery | `witsoc-explorer` supply search + dependency planning. |
| WIT generation | Explorer freezes/accepts the target first (nontrivial), then `witsoc-generator`. Existing `.wit` inspection/repair may start at Generator. |
| User explicitly asks for WIT / `.wit` | Explorer judges the target first (unless `.wit` repair); Generator is then mandatory and must emit a `.wit` or a concrete blocker. Do not answer with only prose/exploration/Lean. |
| WIT + Lean requested | Explorer → Generator for routine targets; Explorer → Lovasz → Explorer → Generator for open/blocked. Generator generates/checks WIT, generates Lean from that frozen WIT target, attempts verification, reports exact status. |
| WIT repair after rejection | `witsoc-generator` for edits; call Explorer when rejected steps need new premises/lemmas/strategy. |
| Lean build error | `witsoc-generator` repair: classify, cite compiler evidence, minimal fix, retry without changing the frozen target; on repeat, apply `references/core/failure_recovery.md`. |
| Structural check / verifier context / semantic verify | Deterministic `wit check` / `wit verify` / skeptical verifier + `wit receipt`; **never** treat check/verify as semantic proof; **no LLM** for structural checks, context, target-freeze, status, or receipt parsing. |

Operating principles: prefer deterministic tooling · strong models for discovery/repair, skeptical models for verification · never substitute confidence for receipts · freeze the target before serious work and reject unexplained hash drift · accept claims only through the claim-acceptance contract · state the achieved quality level before reporting.

## Contracts

**Target freeze** (`references/core/target_freeze.md`): maintain a frozen target statement + target hash; record any change in `target_mutation.json`/`target_mutations.jsonl` with old/new hash, mutation kind, reason, authorization, and whether it weakens the original.

**Claim acceptance** (`references/core/claim_acceptance.md`): a claim is accepted only with exact statement, stable claim/DAG-node id, matching target hash, dependency path to target, legal status transition, evidence receipt or checked artifact, skeptic review for strong claims, and a registered artifact when one is cited. Anything else is `OPEN`, `GAP`, `CONJECTURE`, `FAILED_ATTEMPT`, `REJECTED`, `PARTIAL`, or `CONDITIONAL` — never a full solution.

**Explorer → Generator handoff** is mandatory before writing WIT on nontrivial problems: Explorer pins the full profile (ontology map, ranked theorems, backward chains, falsification results, obstructions, selected target, hypotheses/definitions, likely counterexamples, lemma plan, mutation tracker, sketches, EV scores, freeze hashes), writes `runs/<task>/handoff.json` and strict `runs/<task>/handoff_v1.json`, both validated before Generator runs. Generator reads only `handoff_v1.json` and never invents truth beyond it. For Lovasz work, `validate_handoff.py` also enforces the proof-DAG and worker-result invariants.

## Quality levels (`references/core/production_gates.md`)

`L0_DIRECT` direct answer · `L1_SKETCH` informal sketch · `L2_CHECKED_DERIVATION` deterministic/bounded/structural check · `L3_WIT_ARTIFACT` · `L4_WIT_LEAN_ATTEMPTED` · `L5_WIT_LEAN_VERIFIED` · `L6_RESEARCH_PRODUCT` (Lovasz product with checked/verified artifacts + Explorer review). **The final answer must never imply a higher level than the run achieved.**

## Status honesty

`VERIFIED` only with formal/verifier evidence · `CHECKED` only for deterministic computation/structural checks · `PROVED_SKETCH` only for a coherent non-formal sketch · `PARTIAL` for special cases/bounds/reductions/conditionals · `CONJECTURE` for evidence without proof · `FAILED_ATTEMPT`/`REJECTED` when apt.

User-facing verification labels (do not write bare "verified" unless the sentence names one of these):

- `STRUCTURE_OK` — `wit check` / structural validation passed.
- `CONTEXT_BUILT` — verifier context generated (not semantic proof).
- `RECEIPT_ACCEPTED` — `.wit.receipt.json` exists and accepted verdicts cover the obligations.
- `LEAN_VERIFIED` — Lean/Lake verification passed and SafeVerify/target-freeze passed.
- `OPEN` / `GAP` / `PARTIAL` / `CONDITIONAL` / `CONJECTURE` / `FAILED_ATTEMPT` / `REJECTED` — no full verified proof of the frozen target.

## Explicit WIT request contract

If the user asks for "WIT code" / ".wit" / "provide WIT" / "WIT + Lean", producing WIT is mandatory — do not satisfy it with only an exploration summary, prose proof, sketch, or Lean. In a deep run the orchestrator must dispatch a Generator step that writes the `.wit`. Whenever a `.wit` is generated/updated, activate the Witsoc plugin iframe and open the file. If WIT cannot be produced, return `GAP`/`FAILED_ATTEMPT`/`REJECTED` with the exact blocker and the best partial sketch. If Lean is also requested, generate it from the WIT target, not an unrelated statement. After a structurally valid `.wit` exists and Lean was not requested, ask whether to generate and `lake build` a Lean 4 proof from it.

## Preflight, scripts, and production readiness

The full command sequences live in **`references/core/run_playbook.md`** — its Witsoc-Preflight block (route + handoff validators, `witsoc_route_state.json`, `generator_authorized` check) and its Lovasz/Generator production-readiness blocks. Run preflight at the start of a serious run and the production-readiness block before reporting. The CLI entrypoint is `scripts/witsoc.py` (route/init/check/verify/status/artifacts/validation); register every generated artifact with `witsoc.py artifacts register …` so the plugin reads the registry first. If `witsoc_route.json` sets `required_followup: witsoc-research-lovasz`, a status-only open-problem report is not complete. If `witsoc_route_state.json` has `generator_authorized: false`, Generator may not write yet.

The shared engines and ownership matrix (import-only `services/`, witsoc-owned `bridges/`, no-merge rules) are documented in **`references/core/substrate.md`**. Other shared protocols — load only what the current step needs: `routing.md`, `claim_acceptance.md`, `target_freeze.md`, `artifact_policy.md`, `generator_gate.md`, `production_gates.md`, `status.md`, `handoff.md`, `failure_recovery.md`, `open_problem.md`, `exploration_strategy.md`, `research_machinery.md`, `repair.md`, `goal_cache.md`, `safeverify.md`, `lean_verification.md`, `tooling.md`, `plugin_integration.md` (all under `references/core/`), plus the strict handoff schemas under `references/schemas/`.

## Platform services (probe first, degrade honestly)

Run `python3 scripts/services/fuel.py --backend` once per session: it enumerates what the platform actually offers this JWT (Herald read/**write**, Loogle, remote E2B Lean, literature pools, budgets via `/auth/usage`) and caches it for every consumer. The mechanical seams that build on it: `scripts/falsification_battery.py` (run against every frozen target BEFORE Lean effort), `scripts/services/lemma_pool.py` (federated verified-lemma pool — local SQLite + kernel-verified-only Herald pushes; premise selection reads it first), `scripts/services/proof_harvest.py` (every kernel-verified proof compounds into proof/pattern/lemma banks — engine paths call it automatically), `scripts/remote_verify.py` + `scripts/remote_lean_burst.py` (E2B soft-signal verification and burst compiles — NEVER certification), `scripts/personas.py --publish` then `scripts/dispatch_prompts.py <run>` (typed worker fleet + duration-aware Agent calls: foreground probes uncapped in one message, background workers within the cap, standing disproof lane), `scripts/graph_memory.py` (cross-run GraphRAG mirror), `scripts/campaign_budget_gate.py check` (now budget-aware: respect its tier recommendation near the daily LLM cap). For harness-enforced campaign loops enter via `/flow:witsoc-flow` (see `witsoc-flow/SKILL.md`; write `runs/current_flow_target.json` first — the entry ignores arguments).

## RAM budget

The skill is sized for a 16 GB machine: Lean processes stay within **8 GB usual / 10 GB max**, governed by `scripts/services/ram_governor.py` (run it directly for status). All Lean execution flows through ONE shared Mathlib REPL session (`lean_repl.shared_session`, ~7 GB steady) — never spawn extra REPLs or raise thread fanout to "go faster"; concurrent `lake env lean` file builds are slot-gated and heap-capped (`lean -M`), and the shared session recycles itself if it bloats past the ceiling. Tuning knobs (env, all optional): `WITSOC_RAM_BUDGET_GB` (default 8), `WITSOC_LEAN_SLOTS`, `WITSOC_LEAN_PROC_GB` (default 3.5), `WITSOC_REPL_RECYCLE_GB` (default budget+2), `WITSOC_LEAN_MAX_MB` (default 6144). On bigger boxes raise the budget; never disable the governor.

## Failure-recovery routing

Lean syntax/import/namespace/context failure → Generator repair · WIT lint/structural failure → Generator repair · missing lemma → Explorer repair (Lovasz if it is an open/blocked barrier) · DAG integrity failure → Lovasz repair · target mismatch → Explorer target-freeze repair · poor formalization feasibility → Explorer/Lovasz decomposition · worker disagreement → skeptic review + merge · repeated same failure class → apply `references/core/failure_recovery.md` before stopping.

## Before final answer

Apply `references/core/production_gates.md`: route state checked · frozen target + hash stated · hash consistency checked · accepted statuses justified by the claim-acceptance contract · artifacts registered or paths shown · exact WIT/Lean status · Lovasz return packet reviewed when Lovasz ran · Generator authorization checked when artifacts were generated · report grade or gaps stated when Lovasz ran · achieved quality level stated. Production is complete only with no unexplained target mismatch, no illegal status upgrade, no accepted claim without evidence, no unregistered cited artifact, no skipped required Lovasz phase, and no Generator handoff before Explorer authorization.

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
