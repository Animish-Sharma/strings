# Experiments and conjecture mining

Computation produces evidence, witnesses, and pressure on conjectures. It does
not produce proof, and every rule here exists to keep that boundary visible.

## Types

exhaustive small-case enumeration · random or heuristic search · extremal
construction search · SAT/SMT/ILP encoding · symbolic algebra or recurrence
expansion · graph generation with invariant measurement · finite-field and
modular testing · witness minimization · proof-sketch stress testing.

Encodings are for finite problems with crisp constraints. A solver run records
its variables, constraints, symmetry breaking, objective if any, solver, the
**completeness bound**, and the model or certificate path. Without the
completeness bound an UNSAT result says nothing about the range it did not reach.

## Plan

Every experiment records, before it runs: the question · the product it supports
· the input domain · the search bounds · the method · `deterministic |
randomized` and the seed if randomized · the expected witness format · the
success criterion · the failure criterion · the output path · the reproduction
command.

Stating success and failure criteria in advance is what stops an inconclusive run
from being read as whichever outcome the campaign wanted. A seed recorded after
the fact is not a seed.

## Design rules

- **Search for counterexamples before searching for confirming examples.** A
  confirming search is guaranteed to succeed on a true statement and usually
  succeeds early on a false one too, so it discriminates almost nothing while
  consuming the compute. The refutation search is the one whose outcome carries
  information either way.
- Start with the smallest domain that could falsify the claim. If it cannot
  falsify, it is not an experiment.
- Include the degenerate cases every time: **empty, zero, one, equality,
  disconnected, singular, boundary dimension, low prime.** These are where the
  definition is under-specified and where a false statement is cheapest to break
  — and they are systematically skipped, because the interesting cases feel more
  informative.
- When a witness is found, minimize it. A minimal witness shows which hypothesis
  is doing the work; a large one shows only that something is wrong.
- When no witness is found, record the exact bounds and never imply the
  unrestricted claim. Bounded search caps at a bounded status, forever.
- Prefer structured encodings to ad-hoc manipulation, so results are re-checkable
  by something other than the script that produced them.

## Witnesses

Every counterexample or extremal object carries: a machine-readable form · a
human-readable summary · an independent verification check · its minimality
status · its relation to the original problem and to the variant it refutes.

The independent check matters because a witness found by a buggy search is
verified by the same bug.

## Conjecture mining

Conjectures come from repeated small-case behaviour, extremal examples with
stable structure, a failed proof step that would work under a new hypothesis, a
counterexample to a stronger variant, equality cases in a bound, a theorem
precondition that looks stronger than needed, or a formalization failure exposing
a missing lemma.

Rank a conjecture high only with precise scope and quantifiers, evidence beyond
one example, a clear falsification test, a relation to a named barrier, and a
plausible route to a real status. Rank it low if it is aesthetic, broad, or hard
to test — a conjecture with no cheap falsification test cannot direct the work,
which is the only thing a conjecture is for.

Mining caps at `CONJECTURE`. No amount of agreeing data upgrades it.

## Strength control

For each conjecture, generate three things:

1. **One stronger version, and try to break it.** If it breaks, the counterexample
   is preserved as an obstruction — it marks the boundary of what can be true and
   rules out every proof that would have established the stronger form.
2. **One weaker version, and try to prove or compute it.** If it holds, it is the
   next product candidate: a real result that also confirms the shape.
3. **One boundary case where the conjecture almost fails.** This is where the
   hypotheses are actually load-bearing; a conjecture with no such case is
   probably stated too loosely to be either proved or refuted.

The mechanism is bracketing. A conjecture examined alone accumulates supportive
examples indefinitely without its scope ever being tested. Pushing it up until it
breaks and down until it is provable locates the true statement between them, and
does so with cheap tests rather than a campaign.
