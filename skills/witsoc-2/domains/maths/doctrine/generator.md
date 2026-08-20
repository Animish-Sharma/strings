# Generator — mathematics

Loaded by the general Generator when a claim routes to this pack. Everything in
`generator/SKILL.md` still applies; this adds what is specific to mathematics.

## Artifacts

Two forms, in order:

- **WIT** (`.wit`) — the structured informal argument: labelled steps, each with
  a keyword, a claim, and a `BY` justification. Cheap to write, cheap to check,
  and it exposes the shape of the argument before any formal cost is paid.
- **Lean** (`.lean`) — the formal artifact, elaborated against Mathlib.

WIT precedes Lean unless the work item says otherwise. A gap that WIT makes
visible for free is a gap that would otherwise be found after an expensive
formalization attempt.

## Granularity

Split any step that fuses two moves. In this field the recurring fusions are:

- a manipulation together with an estimate;
- existence together with uniqueness;
- invoking an external result together with checking its preconditions;
- a construction together with its correctness;
- one direction together with its converse;
- termination together with a complexity bound;
- several cases at once.

A fused step is where a mistake hides, and it is also where the kernel will
stop with a diagnostic you cannot act on.

## The check loop

Preferred feedback order, cheapest first:

1. LSP / REPL per-command checking — the tightest loop, use it by default.
2. `lake env lean <file>` — file-level, for a candidate that survives (1).
3. Full `lake build` — **final confirmation only**. Never inside a repair loop.

Feed the exact goal state and diagnostic into the next repair. A repair driven
by a paraphrase of the error is a guess.

Elaborate the Mathlib import prefix once per campaign and fork candidates from
that snapshot. Import elaboration dominates the cost and is identical across
branches; re-importing per attempt is the single largest waste available here.

## What you may edit

**The proof body, and nothing else.** Changing a signature, a definition, a
domain, or a hypothesis requires an approved target update — which is a new
claim with a new hash, not an edit.

Run the target-protection diff before submitting. It exists because the easiest
way to make something type-check is to change what it says.

## Gates before any status claim

| Gate | Rejects |
|---|---|
| `placeholder-scan` | `sorry`, `admit`, `axiom`, `constant`, `opaque`, `unsafe`, `native_decide`, `?_`, `by?` |
| `target-protection-diff` | statement weakened, binder assumption smuggled in, definition redefined to trivialize |
| `axiom-audit` | dependence on any axiom outside the declared allowlist |
| `premise-precondition-audit` | a cited result whose hypotheses are unmet locally |
| `fidelity-review` | a formal statement that does not say what the informal target says |

A placeholder makes anything elaborate, so its presence voids the kernel verdict
entirely rather than merely reducing it.

**Elaboration success is necessary and not sufficient.** It establishes a fact
about the encoding. Whether the encoding is the target is what the fidelity
review answers, and no amount of kernel success substitutes for it.

## Say exactly what happened

The four-way distinction the frame requires, in this field's terms:

| Say | When |
|---|---|
| "structurally valid" | `wit check` passed — no semantic claim whatsoever |
| "contexts generated" | review contexts were built — **nothing has run** |
| "externally accepted" | an independent reviewer returned accept |
| `VERIFIED_LEAN` | fresh hash-bound kernel receipt + clean axiom audit + passing fidelity review |

`wit verify` prepares material for review. It does not call a checker. Never
report its exit code as verification.

## Repair budget

Three consecutive same-class failures with no obligation reduced, or eight
expensive runs on one approach, ends local repair. Going back to the sketch is
the correct move; more edits at that point are the dominant waste mode.

Failure classes are in `repair.md`. Diagnose into a class *before* editing — an
unclassified failure teaches nothing and the next attempt inherits the blind
spot.

## Honest failure

`GAP` — a specific bridge is missing, and the route may still work. Prefer the
structured form, `GAP EXPECTING [name]`, which names the missing sub-problem so
it can be enqueued as its own claim rather than remembered as prose.

`FAILED_ATTEMPT` — this route is shown not to work, with the diagnostic that
shows it.

`PARTIAL` — a narrower product only. State the narrow target explicitly and mark
the unresolved bridge as an open hole.
