# Confounders

A perturbation result competes against a short list of explanations that are
always available and mostly cheap to check. The list, with the cheap test for
each, is in `data/confounders.json`.

## The rule the gate enforces

**A confounder marked addressed with no recorded result is unaddressed.**

This is the single most common way the check gets defeated, and it is rarely
dishonest — someone intends to check, writes the row, and the intention becomes
a tick. So the gate reads `result`, not `verdict`, and a row with a verdict and
no result fails.

## Severities behave differently

- `fatal_if_complete` — a confounder *completely* confounded with treatment is a
  design failure. No analysis fixes it, and nothing downstream matters. Batch is
  the usual one: if every treated sample is in batch 1 and every control in batch
  2, treatment effect and batch effect are the same number.
- `fatal_if_dominant` — generic stress or viability moving as much as the claimed
  signature means the response is not specific. The effect may be entirely real;
  the frozen claim is still wrong.
- `fatal_if_circular` — a pathway defined using the data now used to support it.
  The statement carries no information, however significant it looks.
- `major` — must be addressed with a result.
- `scope_limiting` — does not block, but bounds what may be said. Context
  reversal is the standard example: not testing a second context is fine, and
  claiming generality without one is not.

## The three required negative controls

- **non-targeting guides** — separates the perturbation from the delivery
- **generic stress signature** — separates a specific response from a general one
- **permuted labels** — separates a real effect from the pipeline's own structure

The third is the refute-attempt gate itself. A pipeline never asked to find
nothing has never demonstrated that it can, and asking is nearly free.

## Composition versus expression

Worth calling out separately because it is misreported constantly. A change in
the average profile can come from cells changing what they express, or from the
mixture of cell states changing while each state expresses the same thing. These
are different biological claims and the second is usually the less interesting
one. Decompose before interpreting, or say which you have not distinguished.

## Ambient RNA

If the genes that moved are the high expressers of the dominant population in
the sample, suspect ambient contamination before biology. This one is cheap to
check and rarely checked.
