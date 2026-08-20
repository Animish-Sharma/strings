# The unconventional pass

Before reporting `FAILED_ATTEMPT` or a weak `CONJECTURE`, record at least five
non-obvious candidate explanations or falsifiers, and give the best two or three
a concrete cheap test or an explicit blocker.

This is not brainstorming. It is the step that most often converts an
unexplained failure into a named one, and a named failure is a result while an
unexplained one is a gap.

## Why it is a required step

A failure with no explanation gets recorded as "the effect was not found", which
is the least informative thing that could be written and is often wrong. The
effect may have been there and been swamped; it may have been an artifact
throughout; the design may have been unable to see it from the start. Those are
three different results with three different follow-ups.

## The standing list

Cheap to test, frequently right, and rarely the first thing considered:

- generic stress, apoptosis, or viability response rather than the claimed pathway
- hidden cell-state composition shift, not per-cell expression change
- donor-by-batch or donor-by-condition interaction
- off-target activity of the perturbation reagent
- compensatory pathway activation masking the direct effect
- wrong denominator — the effect exists at a unit nobody tested
- leakage through perturbation, cell-line, or donor labels
- metric gaming, or a metric that does not behave at this dimensionality
- baseline construction: the baseline is stronger or weaker than it looks
- pathway circularity in how the gene set was defined
- context-specific reversal: the effect is real and has the other sign here
- ambient RNA from the dominant population
- selection: the perturbation changed which cells survived to be sequenced
- the perturbation did not measurably hit its target at all

## Prefer the cheap ones

Rank candidates by cost to test, not by how interesting they are. Most of the
list above is answerable from metadata already in hand, before anything is
re-run. A candidate with no cheap test needs an explicit blocker recorded —
what would have to exist for it to be testable — rather than being dropped
quietly.

## The output

For each of the top candidates: the hypothesis, the cheap test, the result or the
blocker. That block is what turns an obstruction record into something the next
run can act on.
