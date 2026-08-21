# Maths domain pack

The frame's baseline domain. Witsoc was built for mathematics first, so this
pack is the reference instantiation of all six contract items — read it
alongside `references/domain_pack_contract.md` when writing a new pack.

Researcher is called **Lovasz** here. Explorer and Generator keep the frame
names.

## The six items

| Item | Here |
|---|---|
| **1. Verification adapter** | `scripts/check.py`, dispatching three tiers: `structural` (WIT shape, ceiling `SKETCH`), `bounded` (finite search, ceiling `CHECKED_BOUNDED`), `kernel` (elaboration against Mathlib, ceiling `VERIFIED`). Corpus retrieval in `scripts/corpus.py`. |
| **2. Claim schema** | `claim.schema.json`. Adds `formal_target` and `allowed_external_facts`; freezes the `GIVEN` and `CLAIM` blocks under **separate** hashes. |
| **3. Receipt format** | `receipt.schema.json`. Adds `toolchain` and `axiom_audit`. Stale if the artifact hash or the toolchain differs at the exit gate. |
| **4. Doctrine** | `doctrine/` — one file per role, plus `doctrine/repair.md`, `doctrine/obstructions.md`, `doctrine/target_protection.md`. Escalation at 3 same-class failures. |
| **5. Gates** | `kernel-recheck` (the refute-attempt, discharged by the kernel tier), plus placeholder scan, target-protection diff, axiom audit, premise-precondition audit, fidelity review. |
| **6. Selection** | `domain.json` → `selection`. What makes this pack resolvable at all: ordinary terms of the field at weight 1, near-conclusive ones at weight 3, borrowed words that mean another field at −3, plus six examples and four counter-examples that `scripts/resolve_domain.py --self-test` replays. |

## Why the tiers are declared the way they are

`adversarial` and `max_status` are independent, and conflating them is a
soundness hole:

- `kernel` is adversarial **and** reaches `VERIFIED` — it cannot be argued into
  a false pass, and its pass is about the general statement.
- `bounded` is adversarial **and** capped at `CHECKED_BOUNDED` — an exhaustive
  search over a stated range genuinely cannot be fooled *within that range*, and
  says nothing at all outside it.
- `structural` is **not** adversarial and caps at `SKETCH` — it checks shape, and
  a well-formed argument can be entirely wrong.

Only `kernel` discharges the refute-attempt gate.

## Elaboration is necessary, not sufficient

A pass from the kernel tier means the *encoding* checks out. Three things can
still be wrong, which is why they are separate blocking gates:

- a placeholder makes anything elaborate (`placeholder-scan`);
- an unaudited axiom makes anything derivable (`axiom-audit`);
- the encoding may not say what the target says (`fidelity-review`).

## Running it

Commands below are relative to this pack directory.

```bash
python3 scripts/availability.py                      # what can actually run right now
python3 scripts/check.py --self-test                 # negative controls must be rejected
python3 scripts/check.py --artifact a.wit --claim c.json --tier structural --json
python3 scripts/corpus.py Nat.succ_le_of_lt          # KNOWN / SEARCH_TARGET / ABSENT
```

`--self-test` is what makes the manifest's `adversarial: true` a claim with
evidence behind it rather than a self-report by the party being checked.

## Toolchain

The `kernel` tier needs Lean and a Mathlib checkout. Without them
`scripts/availability.py` reports the tier unavailable and the run's honest ceiling as
`CHECKED_BOUNDED`. An unavailable tier is a precondition gap — never a pass, and
never support for the claim.

Set `WITSOC2_MATHLIB_INDEX` to a JSON map of `name -> {type, module}` to enable
corpus lookups. Without it every query returns `SEARCH_TARGET` rather than a
fabricated hit.

## Toolkit

Machinery the three roles invoke. Everything here ranks, renders, or checks.
**Nothing here grants a status** — only an admission does, and only on a receipt.
The role doctrine files say when each is used.

### Production (Generator)

| Script | Does |
|---|---|
| `scripts/generate_wit.py` | Blueprint → WIT. A *rendering*, not an invention: refuses on a dangling dependency, an out-of-scope citation, or a CLAIM that does not hash to the frozen target. |
| `scripts/wit_to_lean.py` | WIT → per-step Lean skeleton, one `have … := by sorry` per step so failure localizes to one rung. Refuses to guess the statement. |
| `scripts/repair_cycle.py` | Enforces the budget: 3 same-class failures with nothing reduced, 8 expensive runs, and no expensive run without a stated hypothesis. |
| `scripts/wit_cycle.py` | check → audit → context → status, including receipt completeness. |

### Strategy (Explorer)

| Script | Does |
|---|---|
| `scripts/lanes.py` | Ranks lanes and allocates workers, with hard mix constraints — a refutation lane and a skeptic lane are guaranteed, idea-generation is capped at 40%. |
| `scripts/rungs.py` | The 8-rung result ladder and the rung templates, universal and per-subfield. |
| `scripts/attackability.py` | Which target is worth attacking, with a `raise_it_by` note on every low signal. |
| `scripts/feasibility.py` | Can this be formalized, and at what cost. READY needs score **and** zero blockers. |
| `scripts/next_action.py` | Exactly one next action in a fixed priority order. |
| `scripts/scoring.py` | Every weight in one tunable surface. |

### Knowledge

| Script | Does |
|---|---|
| `scripts/corpus.py` | Pinned premise retrieval: `KNOWN` / `SEARCH_TARGET` / `ABSENT`, with drift detection. An empty result is information, never a fallback guess. |
| `scripts/predicates.py` | An unregistered predicate is a **blocker**, not a stub. |
| `scripts/problem_theory.py` | The enemy profile and failure *mechanisms*. Refuses a label where a mechanism is required. |

### Obligations (Researcher)

| Script | Does |
|---|---|
| `scripts/proof_dag.py` | Node typology plus the four integrity rules a generic graph cannot know. |
| `scripts/reduction_ledger.py` | Obligations, the **open core**, and the honest progress cap. |
| `scripts/gap_feedback.py` | One gap class, one rotating axis, and `BLOCKED_NO_MUTATION` on a bare retry. |
| `scripts/counterexample.py` | Standard families, the 11-field certificate, and inflation (which always drops to `CONJECTURE`). |
| `scripts/select.py` | Barrier choice and the mutation axes keyed by gap class. |
| `scripts/status.py` | The maths transition lattice. `CHECKED_BOUNDED` has **no** edge to any `VERIFIED_*`. |
| `scripts/solve_gate.py` | The four requirements before "solved" may be said. |

### Compounding machinery

These are what make run N+1 cheaper than run N. Nothing here grants a status.

| Script | Does |
|---|---|
| `scripts/lemma_pool.py` | Mines bridging lemmas from **real checker diagnostics** — the probe is expected to fail, the residual goals are the product. Three attempts and an entry is `INTRACTABLE`, recorded with evidence. |
| `scripts/library.py` | Tiered results. Tier 3 (`LEAN_VERIFIED`) cannot be asserted, only reached via a soundness scan — a green build over a `sorry` is only a warning, so the scan is what makes the tier mean anything. `promote` copies tier 3 only. |
| `scripts/proof_autopsy.py` | Abstracts literals from a closure and re-checks. Kernel-gated by construction: a false generalization fails to close. Atlas entries carry no trust. |
| `scripts/speculative.py` | Conditional results ranked by leverage. A verified `H → T` is a conditional fact, never a solve. |
| `scripts/sketch_rubric.py` | Are the gaps *good* gaps. Penalizes **miracle** nodes — a "step" that restates the target has decomposed nothing. |
| `scripts/blueprint.py` | Resumable obligation ledger. An unknown-identifier failure becomes a `THEORY_GAP` with an auto-created prerequisite, not a retry. |
| `scripts/cegis.py` | Refinement ledger with a hard `SURVIVED_CHECKS` ceiling. Passing checks never become a proof. |
| `scripts/dialectic.py` | Refute instances before spending more on proving. A witness routes to statement repair, never another proof attempt. |
| `scripts/recheck.py` | Re-executes recorded certificates. **UNCHECKED is not PASS.** |
| `scripts/backends/` | `scripts/backends/sat.py` (witness re-verified in process; refutations labelled by what actually checked them), `scripts/backends/exact.py` (finding is numeric and untrusted, verifying is exact), `scripts/backends/finite.py`. |
| `scripts/gates/lean_receipt.py` | Catches a **stale** receipt (predates the artifact's last edit) and a **hollow** one (proved the toolchain works, not the claim). |
| `scripts/gates/dependency_packet.py` | A guessed declaration name is not repair evidence. |
| `scripts/gates/manifest.py` | The informal and formal artifacts must hash to the same target. |
| `scripts/gates/protected_patch.py` | Projection comparison **plus** a body constraint — the projection removes bodies, so anything hidden inside one is invisible to it. |
| `data/pivots.json`, `data/techniques.json` | Ontology pivots and the technique KB. Search priors, `OPEN_UNFALSIFIED`, no trust. |

## Producing, not only refusing

For most of this pack's life it could refuse an artifact in nine ways and could
not make one. The production chain existed — `generate_wit`, `wit_to_lean`,
`repair_cycle` — and nothing composed it, and no blueprint with the six sections
`generate_wit` demands existed anywhere in the pack. The generator had never been
fed.

```bash
python3 scripts/produce.py --blueprint evals/blueprints/01_add_zero.json --tier kernel
python3 scripts/produce.py --self-test        # 11 blueprints, both directions
```

`produce.py` runs blueprint → WIT → structural → Lean → kernel, and on failure
classifies the gap, proposes one axis to move, and records the failure against
the escalation threshold. It invents nothing: `generate_wit` renders a reviewed
plan, `wit_to_lean` carries formalizations the blueprint supplied and refuses to
guess a statement, and a step the blueprint does not formalize stays an open hole.

`evals/blueprints/` holds eleven: five that reach a clean kernel pass on core
Lean, one that reaches it against Mathlib, one honestly incomplete, and four
refused before anything is produced.

## Running against Mathlib

Set `WITSOC2_LEAN_PROJECT` to a built Lean project. Without it the kernel tier
elaborates against the ambient toolchain with an empty search path, and every
library import fails — `lake env` takes its path from the directory it runs in,
which is why availability could report the library present while nothing could
import it. `scripts/availability.py` now counts compiled modules rather than
checking that a directory exists.

See `doctrine/kernel_economics.md` for the measurement (the import is 98% of
kernel cost) and for why the obvious optimization was rejected.

## Premise retrieval

Retrieval asks one question — does this name exist — and for most of this pack's
life it answered wrongly. The corpus was built by a regular expression over
source files, which cannot see a declaration produced by an attribute, generated
by a macro, or living in a core library outside the scanned tree.

Measured on one installation: **182,025 declarations from the source scan against
330,887 theorems in the elaborated environment.** On a set of six real names the
source scan resolved **2**; the environment index resolves **6**.

```bash
export WITSOC2_LEAN_PROJECT=/path/to/project
bash scripts/build_corpus.sh --out corpus.json
export WITSOC2_MATHS_CORPUS=corpus.json     # produce.py picks it up
```

`scripts/lean/DumpNames.lean` asks the environment; `corpus.py build-from-env`
consumes it, and `--merge-types-from` carries types across from a source scan,
since the two are incomplete in opposite ways: the scan misses declarations, the
dump misses their types.

This turns the premise pre-flight from advisory noise into a check. Before, every
blueprint reported its citations unresolved and the kernel was the first thing to
discover a missing premise — five seconds of import elaboration to learn what a
lookup answers for free.

Two bugs here were found by running the dumper on a **small** import rather than
the whole library, in seconds instead of minutes: `run_cmd` needs
`Lean.Elab.Command` imported explicitly, and the module-name accessor used first
was a library extension rather than core — so it worked against the full library
and failed against core, the exact inversion of where you want a script to be
robust.

## External evaluation

```bash
python3 evals/external_statements.py --library <path/to/library/source>
```

Samples real theorem statements — written by the library's contributors, for
their own purposes — and asks whether the target-protection gate can tell a
faithful restatement from a mutated one. It found the gate catching **zero of
thirty-five** mutations, because it skipped its comparison entirely whenever the
claim lacked one optional field, and reported PASS. Every fixture in this pack
carried that field. No claim from outside it did.

That is the argument for external evaluation in one number, and it is the reason
to run this before trusting anything else here.

## Operator tools

Nine scripts are reachable from no other script, and they are not dead weight —
their consumer is whoever is running a campaign, not the adapter. Naming the
category is what lets "orphan" mean something again:

| Script | The decision it supports |
|---|---|
| `lanes.py` | which approach families to fund, and how much of each |
| `problem_theory.py` | the living model of *why* this problem is hard |
| `speculative.py` | conditional results, ranked by what they would unlock |
| `cegis.py` | counterexample-guided refinement, with a ceiling on rounds |
| `proof_autopsy.py` | harvesting a closure into a reusable technique |
| `sketch_rubric.py` | are these good gaps, or one hole shaped like the problem |
| `dependency_packet.py` | what a worker may rely on, stated before it starts |
| `protected_patch.py` | editing an artifact without touching its frozen regions |
| `gap_feedback.py` | which axis to move next — now also called by `produce.py` |

`sketch_rubric.py` consumes a proof DAG rather than a WIT artifact, so the
production path cannot call it without building one; `produce.py` says so on the
incomplete path rather than making a call that returns nothing and reads clean.

