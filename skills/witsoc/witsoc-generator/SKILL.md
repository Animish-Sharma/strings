---
name: witsoc-generator
description: Internal Witsoc proof-artifact generation subskill. Use inside the Witsoc subsystem to create, repair, structurally check, verifier-context-build, receipt-track, and optionally Lean-formalize `.wit` proof artifacts for mathematics and rigorous arguments. Use for WIT proofs, disproofs, formalizations, audits, reductions, algorithm correctness proofs, rejected-step repair, and Lean-adjacent proof artifacts. `wit check` is structural only; `wit verify` builds contexts only; semantic acceptance requires external verifier verdicts and a receipt; Lean output must pass `lake build`.
metadata:
  skill-author: OpenScientist
category: research
---

# Witsoc Generator

Generator is the artifact engine inside Witsoc. It converts an Explorer-accepted handoff into a `.wit` proof artifact with explicit labels, dependencies, structural checking, verifier contexts, receipts, and optional Lean. It is **not** a chat-proof mode and **not** a truth arbiter.

Hard rules:
- **Generator never upgrades claim status** — Explorer/top-level own status. Generator may report that a structural check passed, context was built, a receipt was accepted, or Lean passed; the mathematical status is assigned elsewhere. If WIT or Lean fails, report the exact failure to Explorer.
- **`wit check` is structural only**, `wit verify` builds contexts only, `wit receipt` records external verdicts, and `VERIFIED` requires complete accepted-receipt discipline (`../references/core/status.md`).
- If the user asks for WIT/`.wit`/WIT+Lean, producing WIT is **mandatory** — never return only a plan, prose proof, verifier discussion, or Lean. Either write a `.wit` or report a concrete blocker as `GAP`/`FAILED_ATTEMPT`/`REJECTED`.
- For nontrivial new targets, require an **Explorer handoff** first; for open/unsolved/unconfirmed targets, require that Explorer accepted a Lovasz-verified result for the narrow artifact target. Existing `.wit` inspection/repair may start here directly.
- For open problems, never let a partial artifact imply the original problem is solved — title, `-- Status:`, theorem statement, and report must distinguish the open problem from the narrower recorded result.

Load-on-demand: specialized artifact modes (open-problem partials, disproof, reductions, algorithm correctness, audits) in `../references/core/generator_modes.md`; worked Bad/Good WIT in `../references/core/generator_examples.md`; full syntax in `../references/wit.md`; shared substrate in `../references/core/substrate.md` (reach `services/`/`bridges/` only through a bridge as `requester=witsoc-generator`); plus `../references/core/{handoff,failure_recovery,repair,goal_cache,safeverify,lean_verification,tooling}.md` and schemas/examples under `../references/`.

## Tooling

Prefer typed API tools (`run_wit_check`, `run_wit_cycle`, `run_target_freeze_check`) when present. Otherwise resolve scripts through Plane (`skill-run` for shell, `skill-which`+`python3` for validators); do not assume skills are materialized under `$KIMI_WORK_DIR`.

| Script | Purpose |
|---|---|
| `init.sh --name N --claim X [--given H] [--out f.wit]` | `.wit` skeleton (refuses overwrite) |
| `check.sh <file|dir>` | structural validation |
| `audit.sh <file>` | static audit: `GAP`, `CITE`, vague `BY`, receipt issues |
| `verify.sh <file> [--step N]` | structural gate + verifier context (no LLM) |
| `cycle.sh <file>` | full prep cycle: check+audit+context+status → `<name>.verify.txt` |
| `receipt.sh <file> --from verifier.txt` | parse verdicts → `.wit.receipt.json`, update status |
| `status.sh <file>` | summarize status/receipt/structural result |
| `validate_handoff.py <handoff.json>` | validate handoff incl. Lovasz proof-DAG + worker invariants |

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
8. **Optional Lean** (ask first unless requested): generate from the WIT target in the same worktree, then `lake build`.
9. **Cleanup**: delete temporary Lean projects/worktrees after the worker finishes (unless marked preserved); preserve `.wit`, Lean source, logs, receipts, SafeVerify records, reports; report cleanup status.

**Failure diversification.** Before returning a final `GAP`/`FAILED_ATTEMPT`/`REJECTED` on a nontrivial theorem, write a failure note beside the artifact (frozen target, failed method, artifact path, exact diagnostic, rejected step/missing premise, repairs tried, methods to avoid, two distinct alternate families) and return it to Explorer — which decides Generator-repair vs Lovasz-barrier. Only stop locally without alternates when the failure is purely mechanical and immediately repairable, or spawning is unavailable and ≥2 materially different local methods already failed. Forbidden for explicit WIT requests: stopping after exploration, returning only prose, returning only Lean, saying WIT "could be generated", or passing a sketch off as the artifact.

## `.wit` quality + audit

A good file: valid header (`-- Status: UNVERIFIED`/`GAP`/`REJECTED`, or `VERIFIED` only when a receipt says so); one `MODULE`; all domains/hypotheses stated; target aligned with the request; one move per step; exact `BY` dependencies; every case closed; every proof ends `QED BY ...`; `GAP` not fake bridges; no Lean syntax. Audit for: label-only `BY [3]`/`BY obvious`; unproven theorem preconditions; final-claim drift; unclosed case splits; vague external refs; accidental Lean syntax; hidden assumptions (nonzero, finite, compact, measurable, positive).

## Check, verify, receipts

Order (typed tools when available): `run_wit_check → run_wit_audit → run_wit_context|run_wit_verify → run_wit_status → run_target_freeze_check`; else `check.sh → audit.sh → verify.sh → status.sh` (or `cycle.sh`). A verifier judges each context skeptically (`[1] ACCEPT`/`[2] REJECT`/`[3.1] GAP`); persist with `receipt.sh`. Before reporting `VERIFIED`: all obligations have verdicts · the final `SHOW` is covered · no `GAP`/`REJECTED` remain · receipt status matches the header · verifier output is not truncated. A suspiciously incomplete receipt is not high assurance.

## Repair + Lean

Use `../references/core/repair.md`: before editing after a WIT/structural/Lean/SafeVerify rejection, write a structured repair diagnosis and keep the target frozen (a repair may change proof terms, tactics, helpers, allowed imports, or decomposition — never variables, hypotheses, definitions, or conclusion). Record failed attempts as reusable evidence (attempt id, path, failure class, diagnostic excerpt, repair, outcome, lesson).

Lean loop (`../references/core/lean_verification.md`): prefer LSP/REPL/per-file checks for iterations, full `lake build` for final/dependency-sensitive changes. Never introduce `sorry`, `admit`, `axiom`, `constant`, `opaque`, fake bridge lemmas, or comments-as-proof. When a linear repair stalls, run one breadth scan (`lean_tactic_scan.py --file …`, configured via `WITSOC_LEAN_REPL_CMD`) — guidance only; success still needs a real checker pass + SafeVerify (target-freeze diff/hash of source, canonical target, `GIVEN`, `CLAIM`, definitions; SafeVerify failure is `REJECTED` until repaired). `Lean VERIFIED` = final `lake build` passed + SafeVerify passed + no forbidden placeholders; otherwise say `Lean code generation failed`. Do not claim Lean verification without `lake build`.

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
