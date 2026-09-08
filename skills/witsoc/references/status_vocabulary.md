# Status Vocabulary

Frame-owned and domain-neutral. A domain pack registers substrate-specific
refinements (`VERIFIED_<substrate>`) but does not invent a parallel ladder.

> A status is a statement about **evidence**, not about effort, progress,
> plausibility, or how the run felt.

## Labels

| Status | Means |
|---|---|
| `OPEN` | Unresolved, or currently treated as unresolved. The honest default. |
| `CONJECTURE` | Proposed, supported by evidence or analogy. Not established. |
| `CHECKED_BOUNDED` | Holds over a **stated finite domain** that was actually searched. Says nothing outside those bounds. |
| `SKETCH` | A complete-looking argument exists, unchecked by any backend. |
| `PARTIAL` | A narrower product — a sub-case, a bound, a reduction — while the target stays unresolved. |
| `CONDITIONAL` | Depends on an explicit unestablished assumption or an unchecked precondition. |
| `VERIFIED` | An admitted receipt from the domain's adapter covers every obligation, and the refute-attempt gate passed. |
| `GAP` | A specific unresolved obligation is named and open. |
| `FAILED_ATTEMPT` | A documented approach failed for a stated reason. Preserved as negative information. |
| `REJECTED` | Structurally invalid, refuted, drifted from target, or rejected by the backend. |

## Below the vocabulary: search material

Speculative output is **not** a status. Explorer's and Researcher's creative modes
both require generating ideas that are allowed to be implausible, source-free,
or contradictory — that is what makes the search worth running.

Such material carries **no status at all**. It is search material until it
crosses the promotion boundary, at which point it enters at `CONJECTURE` or
`OPEN` and is subject to everything below.

Labelling arena junk `CONJECTURE` to have somewhere to put it degrades the
weakest real label into meaninglessness. Keep generation bold and status
conservative by keeping them in different containers.

## Legal transitions

Only an **admission** moves a status (`frame-admission-v1`). A role may propose;
none may grant.

**Upgrades** require the evidence for the target status, not merely more effort
at the current one. These upgrades are forbidden outright, because no amount of
the evidence backing the left side ever constitutes the evidence for the right:

| Forbidden | Why |
|---|---|
| `CONJECTURE` → `VERIFIED` | Skips every gate. Requires a receipt, a refute-attempt, and a fidelity record. |
| `SKETCH` → `VERIFIED` | A complete-looking argument is not a checked one. |
| `CHECKED_BOUNDED` → `VERIFIED` | Bounded evidence never becomes universal evidence. See below. |
| `FAILED_ATTEMPT` → any checked status | Re-running a failed route unchanged is not new evidence. Mutate first, then it is a new attempt. |
| `PARTIAL` → the full target's status | The narrower product is not the target. Promoting it is target drift. |

**Demotions** may happen at any time and need no admission — the ladder is
`VERIFIED → CHECKED_BOUNDED → SKETCH → PARTIAL → CONJECTURE → FAILED_ATTEMPT →
REJECTED`. Move only as far as the evidence requires, and:

- Never delete a failed claim. Preserve the strongest true weaker statement.
- Never let that weaker statement silently become the main target.
- A demotion **names the obstruction** that blocked the original.
- If an artifact failed because the target drifted, demote the *artifact*, not
  the claim.

## Rules

**Grades propagate downward.** Every result carries the ceiling of the weakest
input it rests on. A composite built on a `CHECKED_BOUNDED` input is itself
bounded by that input's stated domain; one built on a `CONJECTURE` input is
`CONDITIONAL` on it, named explicitly. Admission of the composite does not
launder the grade of its parts — a receipt covering the composition step says
nothing about the inputs that step consumed.

**Bounded means bounded.** Search and mining are permanently capped at
`CHECKED_BOUNDED` no matter how much evidence accumulates. A finite search that
found nothing is not evidence for a universal claim unless it was exhaustive
over a stated finite domain — and then it establishes only that domain. Each
adapter tier declares its own `max_status` ceiling for exactly this reason.

**Only admission upgrades.** Scores, votes, reviews, and confidence do not
upgrade anything. A role may never accept its own work.

**Process states are not status.** "The check exited zero", "the cycle
completed", "the budget was spent", "the worker returned" describe what a
program did. They are artifact and run states, and never appear where a status
belongs. The same holds for lifecycle states such as waiting on an external
result — real and worth recording, but not evidence about a claim.

**Candidate grades are not evidence.** Anything a role emits before admission —
however it is labelled — is a candidate. A candidate laundering into an accepted
product by being restated confidently is the failure this vocabulary exists to
prevent.

**Unresolved adverse evidence caps status at `CONJECTURE`.** See
`verification_interface.md`.

**Separate the mechanisms when reporting.** Structural validity, context
generation, external acceptance, and backend verification are four different
claims. Collapsing them into "verified" destroys the honesty layer. Report each
explicitly, using `none` or `not run` where that is the truth.
