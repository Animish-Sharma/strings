# Failure Recovery and Escalation

The ladder is frame-owned. Each domain pack supplies only two values, through
`doctrine.escalation` in its manifest:

- `max_consecutive_failures` — the **N** below;
- `failure_signature` — how that field decides two failures are the same.

The counter and the mechanism live once, here. This is deliberate: left to
judgment, "when does this stop being Generator's problem" gets applied
inconsistently across runs and across fields, and inconsistently applied
escalation is how a run burns its budget re-trying the same thing.

## The escalation trigger

> **N consecutive Generator failures on the same frozen claim, or a repeat of
> an identical failure signature, escalates to Researcher.**

Not a suggestion, not a judgment call. Explorer and Researcher are both search; the
difference is time horizon and depth, and this trigger is what decides which one
the problem currently deserves.

## The failure record

Written **the instant a failure occurs**, not at synthesis time. A failure
reconstructed later is a failure half-remembered.

```json
{
  "attempt_id": "unique",
  "frozen_target": "exact target",
  "method_family": "which family this belongs to",
  "failure_class": "one of the classes below",
  "diagnostic": "backend or checker evidence, not a paraphrase",
  "obligation_delta": "reduced | same | worse | unknown",
  "repairs_tried": ["what was attempted"],
  "do_not_repeat": ["the specific route now ruled out"],
  "reusable_lesson": "what this rules out generally",
  "next_method_families": ["distinct family 1", "distinct family 2"]
}
```

Frame-level failure classes — a pack refines these but does not replace them:

`target_drift` · `missing_dependency` · `unmet_precondition` ·
`out_of_scope_reference` · `false_statement` · `hidden_assumption` ·
`circularity` · `step_too_compressed` · `forbidden_escape` ·
`computational_obstruction` · `genuine_obstruction` · `toolchain_unavailable`

## The recovery ladder

1. Keep the target frozen. Changing it is not recovery.
2. **Never retry the same method unchanged.** A retry must change the method,
   the decomposition, the encoding, the external dependency, or the search
   space. A different surface attempt on the same decomposition is a mutation,
   not a new method.
3. **No repair hypothesis, no expensive run.** An expensive attempt with no
   stated hypothesis about what will be different is a gamble, not a repair.
4. Mutate **one axis at a time**, recording the changed dimension and the
   constraints deliberately left unchanged. Do not rewrite the whole context
   after a failure.
5. Prefer alternates with **distinct failure domains** — a route that fails for
   the same underlying reason is not a second attempt.
6. Bind every alternate to the exact target, and tell it what already failed
   and what not to repeat.
7. Escalate at N. After escalation, the obstruction belongs to Researcher.
8. If conventional routes are exhausted, creative mode is mandatory before
   reporting failure — a target attacked only conventionally has not been
   attacked.

## Re-dispatch is contractual

A node that already failed may be re-dispatched only after its statement
changes, or the ledger records the one-axis mutation applied. A match against
recorded failures **blocks** dispatch until something actually changed. Reused
axes and known repeat-risk are penalized in ranking.

Do not open a new branch until the current failure has a class. An unclassified
failure teaches nothing and the next branch inherits the same blind spot.

Three recorded failures sharing one blocker promote that blocker to a named
obstruction. That promotion is the signal that the run has found something real
rather than merely being unlucky.

## Blocks expire

**Every `do_not_repeat` entry records what would make it worth retrying.**

A route ruled out by current knowledge is not ruled out permanently, and a block
with no revival condition throws away the reason it was blocked — leaving a
campaign that gets progressively more constrained by decisions whose grounds
nobody can reconstruct.

When a revival condition fires — a new admitted sub-claim, a refuted
obstruction, a new counterexample family, a rival branch collapsing — re-read
the failure ledger before ranking anything. That event re-prices every branch,
not only the one it landed on.

## Stop conditions

Stop the branch and report honestly when:

- the same failure class recurs N times without reducing the obligation;
- every available repair would change the frozen target;
- all active approaches depend on the same unresolved bridge;
- a needed external dependency is unavailable within budget;
- refutation pressure suggests the claim is false or missing a hypothesis;
- an essential gap is as hard as the target itself;
- the skeptic rejects and no narrower product survives;
- the budget is exhausted.

## Stopping well

An honest stop is a legitimate outcome, and a failure record that removes a
route from consideration is real negative progress. Preserve it.

Report: the frozen target · the best approach reached · where it failed · the
failure class · what was tried · why it did not close · the reusable lesson ·
the next useful mutation · **the first failing gate**.
