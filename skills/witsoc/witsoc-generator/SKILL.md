---
name: witsoc-generator
description: >
  Witsoc proof-artifact engine. Use to create or repair WIT and Lean artifacts
  from an Explorer-approved frozen target, patch only authorized proof ranges,
  retrieve exact APIs, iterate against real compiler diagnostics, reject
  placeholders or skeleton drift, and emit reproducible terminal receipts.
---

# Witsoc Generator

The canonical repair command composes preflight, protected-byte validation,
placeholder scan, exact API validation, real Lean compilation, repair-ledger
update, target protection, and receipt gating:

```bash
python3 ../scripts/witsoc.py generator cycle runs/<task> \
  --lean-file runs/<task>/Solution.lean \
  --lean-api-packet runs/<task>/lean_api_availability.json \
  --lake-dir <project>
```

`CYCLE_PASSED` means local checks passed but is not a final proof claim.
`COMPLETE` requires a `VERIFIED_LEAN` package with matching target hash,
receipts, and `generator_clean_verification.json` bound to the exact current
Lean source hash. Repairs are proof-body patches only in locked mode; any need for a
helper outside the allowed range, a new import/open, or a changed statement is
routed back as a dependency or target problem.

For protected Lean repair, search competing bodies in isolated workspaces
before touching the source, then independently recheck the exact applied file:

```bash
witsoc generator patch-search runs/<task> patch_candidates.json \
  --lake-dir <project> --apply-best
witsoc generator patch-search runs/<task> \
  --synthesizer "<proof-body-synthesizer-command>" \
  --max-rounds 3 --candidates-per-round 6 \
  --lake-dir <project> --apply-best
witsoc generator clean-verify runs/<task> runs/<task>/Solution.lean \
  --lake-dir <project>
```

The synthesizer receives the exact source, editable ranges, protected contract,
and prior compiler diagnostics; each round must produce materially distinct
proof-body candidates. Every candidate is deduplicated and checked in an
isolated workspace and must preserve the protected projection byte for byte.
The clean verifier uses a fresh artifact copy, restricted environment, separate
process, real Lean check, placeholder scan, protected-contract validation, and
source hashes. A stale clean receipt cannot support `COMPLETE`, and
`generator_receipt_gate.py` additionally requires target-bound package and
clean-receipt hashes plus `formalization_fidelity.json`.

Generator is the artifact engine inside Witsoc. It converts an Explorer-accepted handoff into a `.wit` proof artifact with explicit labels, dependencies, structural checking, verifier contexts, receipts, and optional Lean. It is **not** a chat-proof mode and **not** a truth arbiter.
Generator must read SOC before repair so it does not repeat failed proof
decompositions, missing-premise loops, or compiler-chasing strategies. Mechanical
syntax/import repairs stay local; premise or target gaps return to Explorer or
Lovasz and are recorded in SOC.

Generator may use `witsoc generator discover init/search/harvest` after repeated
repair failures to search alternative proof-state representations, local helper
shapes, API-grounded lemma chains, and diagnostic minimizations. Its free arena
may be unconventional, but every harvested repair is proof-body-only: no arena
proposal authorizes statement, import, open, option, namespace, guard-marker,
or protected-byte edits outside declared ranges.
The resulting `repair_candidates.json` is advisory input to the normal
Generator decision packet; it cannot authorize a patch or claim success.

Hard rules:
- **Generator never upgrades claim status** — Explorer/top-level own status. Generator may report that a structural check passed, context was built, a receipt was accepted, or Lean passed; the mathematical status is assigned elsewhere. If WIT or Lean fails, report the exact failure to Explorer.
- **`wit check` is structural only**, `wit verify` builds contexts only, `wit receipt` records external verdicts, and `VERIFIED` requires complete accepted-receipt discipline (`../references/core/status.md`).
- If the user asks for WIT/`.wit`/WIT+Lean, producing WIT is **mandatory** — never return only a plan, prose proof, verifier discussion, or Lean. Either write a `.wit` or report a concrete blocker as `GAP`/`FAILED_ATTEMPT`/`REJECTED`.
- For nontrivial new targets, require an **Explorer handoff** first; for open/unsolved/unconfirmed targets, require that Explorer accepted a Lovasz-verified result for the narrow artifact target. Existing `.wit` inspection/repair may start here directly.
- For open problems, never let a partial artifact imply the original problem is solved — title, `-- Status:`, theorem statement, and report must distinguish the open problem from the narrower recorded result.
- For biological claims, Generator verifies only formal/computable evidence
  structure: schema validators, provenance receipts, statistical-obligation
  specs, reproducibility manifests, target hashes, and WIT artifacts for narrow
  claim gates. It must not "prove biology" or upgrade empirical support.
- In `formal_locked_artifact` mode, Generator is a proof-body patcher only:
  no new imports, opens, scoped opens, options, namespace/end edits, global
  helper declarations, theorem-signature edits, guard-marker edits, or protected
  whitespace changes. Helper facts must be local `have`/`suffices`/`calc` inside
  the editable body unless Explorer authorizes a new skeleton.

Load-on-demand: specialized artifact modes (open-problem partials, disproof, reductions, algorithm correctness, audits) in `../references/core/generator_modes.md`; Generator-specific notes and examples under `../references/witsoc-generator/`; worked Bad/Good WIT in `../references/core/generator_examples.md`; full syntax in `../references/wit.md`; shared substrate in `../references/core/substrate.md` (reach `services/`/`bridges/` only through a bridge as `requester=witsoc-generator`); plus `../references/core/{handoff,failure_recovery,repair,goal_cache,safeverify,lean_verification,generator_lean_fix_cycle,protected_artifact,open_problem_acceleration,tooling}.md` and schemas/examples under `../references/`.

## Tooling

Prefer typed API tools (`run_wit_check`, `run_wit_cycle`, `run_target_freeze_check`) when present. Otherwise resolve scripts through Plane (`skill-run` for shell, `skill-which`+`python3` for validators); do not assume skills are materialized under `$KIMI_WORK_DIR`.

| Script | Purpose |
|---|---|
| `../scripts/witsoc-generator/init.sh --name N --claim X [--given H] [--out f.wit]` | `.wit` skeleton (refuses overwrite) |
| `../scripts/witsoc-generator/check.sh <file|dir>` | structural validation |
| `../scripts/witsoc-generator/audit.sh <file>` | static audit: `GAP`, `CITE`, vague `BY`, receipt issues |
| `../scripts/witsoc-generator/verify.sh <file> [--step N]` | structural gate + verifier context (no LLM) |
| `../scripts/witsoc-generator/cycle.sh <file>` | full prep cycle: check+audit+context+status -> `<name>.verify.txt` |
| `../scripts/witsoc-generator/receipt.sh <file> --from verifier.txt` | parse verdicts -> `.wit.receipt.json`, update status |
| `../scripts/witsoc-generator/status.sh <file>` | summarize status/receipt/structural result |
| `validate_handoff.py <handoff.json>` | validate handoff incl. Lovasz proof-DAG + worker invariants |
| `../references/witsoc-bio/scripts/validate_bio_evidence_structure.py <run_dir>` | validate biological evidence structure, provenance classes, hashes, and dual-signoff shape |
| `generator_cycle.py <run_dir> --artifact ...` | local Generator cycle: preflight, manifest/artifact registration, target-protection check, WIT-to-Lean manifest validation |
| `lean_fix_cycle.py <run_dir> --lean-file ... --record-attempt` | stateful Lean repair controller: failure class, repair hypothesis, same-class budget, expensive-run budget, forbidden-token scan |
| `validate_wit_lean_manifest.py <manifest>` | require WIT label → Lean declaration mapping and frozen/WIT/Lean target-hash equality |
| `validate_protected_artifact.py <run_dir>` | prove artifact text outside editable proof-body ranges did not drift |
| `formal_locked_artifact.py init|validate <run_dir>` | initialize/validate locked Lean skeletons with baseline protected text and drift classification |
| `protected_body_patcher.py <run_dir> --artifact ... --range-id ... --replacement-file ...` | patch only a declared editable proof range |
| `generator_patch_search.py <run_dir> [patches.json] --synthesizer ... --lake-dir ... --apply-best` | search multi-round proof-body candidates with compiler feedback; apply only a protected-safe Lean success and roll back if exact clean verification fails |
| `generator_clean_verify.py <run_dir> <file.lean> --lake-dir ...` | recheck an exact source-hash copy in a fresh process before terminal status |
| `generator_receipt_gate.py <run_dir>` | reject stale/missing target-bound Generator package, clean verification, source hash, or fidelity evidence |
| `validate_no_placeholders.py <files...>` | reject `sorry`/`admit`/TODO/placeholders/Lean holes before final reporting |
| `validate_lean_api_packet.py <lean_api_availability.json>` | reject guessed/nonexistent Mathlib APIs and unhandled semantic edge cases |
| `validate_pending_state.py <run_dir>` | block success while critic/verifier/worker state remains nonterminal |
| `validate_final_receipt_claim.py <final.md> --run-dir <run_dir>` | require terminal receipts for final success wording |
| `classify_formal_failure.py --text ...` | map failures to Generator/Explorer/Lovasz repair routes |

For biological evidence structure, expect `source_ledger.json`,
`normalized_bio_sources.json`, `perturbation_design_audit.json`,
`experimental_unit_classification.json`, `pseudoreplication_sensitivity.json`,
`claim_denominator_gate.json`, `perturbation_receipt.json` or
`model_performance_receipt.json`, `source_to_claim_trace_validation.json`,
`lovasz_math_audit.json`, and final `joint_synthesis.json` when a strong status
is requested. Missing normalized/design/denominator receipts are warnings before
final synthesis and blockers for strong support.

Fallback native CLI: `wit check|verify|context|receipt`.

## WIT writing protocol (the pipeline)

Triggers ("provide WIT code", "write a `.wit` proof", "give WIT and Lean", "deep run proving X, provide WIT + Lean"). Run in order:

1. **Freeze the exact target** — name; kind (theorem/lemma/disproof/reduction/algorithm/audit); original open problem if any; WIT header status (`UNVERIFIED`/`VERIFIED`/`GAP`/`REJECTED`); research status (`OPEN`/`PARTIAL`/`CONDITIONAL`/`CONJECTURE`/`FAILED_ATTEMPT`/`CHECKED`/`PROVED_SKETCH`/`VERIFIED`/`GAP`/`REJECTED`); variables/domains; hypotheses; definitions; conclusion; allowed external facts. Record target-freeze hashes (`../references/core/safeverify.md`). Never silently strengthen or weaken.
2. **Require + validate the handoff.** For nontrivial targets get/create an Explorer handoff; open/blocked needs an Explorer-reviewed Lovasz result. Execute only `runs/<task>/handoff_v1.json` (treat `handoff.json` as context). Validate before writing:
   ```bash
   VAL="$("$PLANE_TOOL_BIN" skill-which witsoc/scripts/validate_handoff.py)"
   GEN="$("$PLANE_TOOL_BIN" skill-which witsoc/scripts/validate_generator_handoff.py)"
   python3 "$VAL" runs/<task>/handoff_v1.json
   python3 "$GEN" runs/<task>/handoff_v1.json --route-state "$PLANE_SESSION_DIR/witsoc_route_state.json" --manifest-out runs/<task>/generator_handoff_validation.json
   ```
   On failure, return to Explorer with the exact errors. Do not invent helper lemmas unless a structural check fails; do not cite any theorem outside `external_dependencies`.
3. **Enter a dedicated proof worktree** for this exact target (`witsoc-proof-${OSCI_SESSION_ID}-${proof_id}`). Never generate in the coordinator root or another proof's worktree. Record `session_id`, `proof_id`, `proof_worktree`, `proof_worktree_dedicated`, `worktree_status`, and WIT/Lean/frozen target hashes (a Lean proof is `VERIFIED` only when Lean hash = WIT hash = frozen hash).
4. **Build an obligation graph** (goal → lemmas / case splits → hypotheses+definitions / external theorems). Each node becomes a WIT step, helper claim, `CITE`, or `GAP`.
5. **Choose granularity** — enough labels that a skeptic judges each step locally. Split a step that combines algebra+inequality, existence+uniqueness, theorem-invocation+precondition, construction+correctness, forward+reverse, termination+complexity, or multiple case branches.
6. **Write the WIT** inside the worktree, preserve a copy in the run dir, register it (`witsoc.py artifacts register …`):
   ```wit
   -- Status: UNVERIFIED
   MODULE [module_name]

   THEOREM [module_name]:
     GIVEN:
       - [hyp_name]: hypotheses
     CLAIM:
       conclusion.

   PROOF OF [module_name]:
     [1] ASSUME setup fact.
         BY [hyp_name].
     [2] HAVE intermediate claim.
         BY [1], @{named method or theorem}.
     [3] SHOW conclusion.
         BY [2], final assembly.
     QED BY [3].
   ```
   Labels sequential per scope; no forward/self/cross-case refs; bracket local/imported/hyp/step refs (`[lemma]`, `[alias.thm]`, `[hyp]`, `[3]`); `@name`/`@{citation}` for external givens; case hypothesis is `[n.0]`; `GAP` (or `GAP EXPECTING [subproblem]`) beats handwaving; avoid `BY obvious/clearly/standard/Mathlib` and bare `BY [n]` for nontrivial steps; no Lean syntax in WIT.
7. **Check + lint**: activate the plugin iframe and open the file; run `check.sh`/`lint_wit_quality.py`; build verifier context; register logs. Repair structural failures before semantic contexts. Write the manifest with `generator_manifest.py` (target-hash drift is a hard failure).
8. **Optional Lean** (ask first unless requested): generate from the WIT target in the same worktree, write a WIT-to-Lean translation manifest mapping WIT labels to Lean declarations/blocks, ensure frozen/WIT/Lean target hashes match, then create/validate `protected_artifact_contract.json` for theorem skeletons and edit only proof-body ranges through `protected_body_patcher.py`. For nontrivial library facts write `lean_api_availability.json` and validate it before retrying; guessed identifiers are blockers. Run final `lake build`, SafeVerify, `validate_protected_artifact.py`, `formal_locked_artifact.py validate`, and `validate_no_placeholders.py`. Validate any claimed Lean success with `../scripts/validate_lean_receipt.py`; stale receipts, missing command/output, `sorry`, `admit`, `axiom`, `constant`, `opaque`, placeholder text, guessed APIs, skeleton drift, or SafeVerify failure block `LEAN_VERIFIED`.
9. **Cleanup**: delete temporary Lean projects/worktrees after the worker finishes (unless marked preserved); preserve `.wit`, Lean source, logs, receipts, SafeVerify records, reports; report cleanup status.

**Failure diversification.** Before returning a final `GAP`/`FAILED_ATTEMPT`/`REJECTED` on a nontrivial theorem, write a failure note beside the artifact (frozen target, failed method, artifact path, exact diagnostic, rejected step/missing premise, repairs tried, methods to avoid, two distinct alternate families) and return it to Explorer — which decides Generator-repair vs Lovasz-barrier. If `open_problem_acceleration.json` exists, add the blocker to its formalization plan or next-three-moves feedback: missing definition, library search target, theorem-precondition gap, smallest formalizable subclaim, or target-drift risk. Only stop locally without alternates when the failure is purely mechanical and immediately repairable, or spawning is unavailable and ≥2 materially different local methods already failed. Forbidden for explicit WIT requests: stopping after exploration, returning only prose, returning only Lean, saying WIT "could be generated", or passing a sketch off as the artifact.

## `.wit` quality + audit

A good file: valid header (`-- Status: UNVERIFIED`/`GAP`/`REJECTED`, or `VERIFIED` only when a receipt says so); one `MODULE`; all domains/hypotheses stated; target aligned with the request; one move per step; exact `BY` dependencies; every case closed; every proof ends `QED BY ...`; `GAP` not fake bridges; no Lean syntax. Audit for: label-only `BY [3]`/`BY obvious`; unproven theorem preconditions; final-claim drift; unclosed case splits; vague external refs; accidental Lean syntax; hidden assumptions (nonzero, finite, compact, measurable, positive).

## Check, verify, receipts

Order (typed tools when available): `run_wit_check -> run_wit_audit -> run_wit_context|run_wit_verify -> run_wit_status -> run_target_freeze_check`; else `../scripts/witsoc-generator/check.sh -> ../scripts/witsoc-generator/audit.sh -> ../scripts/witsoc-generator/verify.sh -> ../scripts/witsoc-generator/status.sh` (or `../scripts/witsoc-generator/cycle.sh`). A verifier judges each context skeptically (`[1] ACCEPT`/`[2] REJECT`/`[3.1] GAP`); persist with `../scripts/witsoc-generator/receipt.sh`. Before reporting `VERIFIED`: all obligations have verdicts · the final `SHOW` is covered · no `GAP`/`REJECTED` remain · receipt status matches the header · verifier output is not truncated. A suspiciously incomplete receipt is not high assurance.

## Repair + Lean

Use `../references/core/repair.md`: before editing after a WIT/structural/Lean/SafeVerify rejection, write a structured repair diagnosis and keep the target frozen (a repair may change proof terms, tactics, helpers, allowed imports, or decomposition — never variables, hypotheses, definitions, or conclusion). Record failed attempts as reusable evidence (attempt id, path, failure class, diagnostic excerpt, repair, outcome, lesson).

Lean loop (`../references/core/lean_verification.md` and `../references/core/generator_lean_fix_cycle.md`): prefer LSP/REPL/per-file checks for iterations, full `lake build` for final/dependency-sensitive changes. Never introduce `sorry`, `admit`, `axiom`, `constant`, `opaque`, fake bridge lemmas, or comments-as-proof. Record every expensive Lean run with `lean_fix_cycle.py`, including the failure class, repair hypothesis, and whether obligations reduced. When a linear repair stalls, run one breadth scan (`lean_tactic_scan.py --file …`, configured via `WITSOC_LEAN_REPL_CMD`) — guidance only; success still needs a real checker pass + SafeVerify (target-freeze diff/hash of source, canonical target, `GIVEN`, `CLAIM`, definitions; SafeVerify failure is `REJECTED` until repaired). `Lean VERIFIED` = final `lake build` passed + SafeVerify passed + no forbidden placeholders; otherwise say `Lean code generation failed`. Do not claim Lean verification without `lake build`.

Lean repair is proof-body-first. For a fixed user or Explorer statement, do not
change theorem signatures, domains, hypotheses, definitions, or conclusions.
For protected Lean files, repair through the declared editable markers and
reject duplicate/missing markers as target-drift risk.
If the statement cannot close, return `GAP`/`REJECTED` with the exact diagnostic
and missing lemma instead of changing the target.

Repair budget (`../references/core/lean_verification.md` Repair Budget): every expensive run (verifier, full `lake build`) needs a stated hypothesis — what changed and why it should fix the previous error; no hypothesis means no run, that is compiler-chasing. 3 consecutive same-class failures without reducing the obligation → stop local repair and return the sketch to Explorer for material revision or rotation. 8 expensive runs on one sketch → sketch exhausted; record the failure entry and rotate. Never edit the frozen statement/definitions to make a proof close, and claim success only from a captured verifier/`lake build` receipt that postdates the last edit (`../references/core/safeverify.md`, `../references/core/status.md`).

For open-problem campaigns, Generator is also a reduction sensor. A formalization
failure can be useful progress when it identifies the exact missing definition,
unavailable theorem, bad quantifier order, hidden side condition, or smaller
subclaim that should be attacked next. Record that feedback in the acceleration
record and return it to Explorer/Lovasz; do not silently change the statement to
fit the prover.

## Reporting

End every response with the artifact block (use `none`/`not run`, never omit a field):

```text
Artifacts:
- WIT: <path|none>
- Lean: <path|none>
- Receipt: <path|none>
- Status: STRUCTURE_OK=<yes/no/not run>; CONTEXT_BUILT=<yes/no/not run>; RECEIPT_ACCEPTED=<yes/no/not run>; LEAN_VERIFIED=<yes/no/not run>
- Plugin: <opened/open failed/not attempted>
```

Precise language: "structurally valid" = check passed · "verifier contexts generated" = `wit verify` ran · "semantically accepted" = verifier verdicts accepted the obligations · `VERIFIED` = complete accepted-receipt discipline. The status label is inherited from the accepted handoff or mechanically justified by checks/receipts — never upgrade a `CONJECTURE`/`PARTIAL`/`PROVED_SKETCH`/`CHECKED` handoff to `VERIFIED` without complete formal/verifier evidence and SafeVerify. Worked Bad/Good WIT examples: `../references/core/generator_examples.md`.
