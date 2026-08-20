# Skeptic pass — the adversarial review before acceptance

Runs before any proof, disproof, full-proof escalation, or Generator handoff on a
high-stakes claim.

**No full proof or disproof of an open problem may be reported without a skeptic
record.** The author of an argument is the worst reader of it: the reasoning that
produced a gap is the same reasoning that will look past it. The record exists so
that the check is a separate, attributable act rather than a feeling of
confidence.

## Checklist

Every pass records the claim reviewed and each of these, individually, with what
was found:

| Check | Catches |
|---|---|
| Frozen target match | the argument settles a different statement from the one admitted |
| Variant drift | a neighbouring variant substituted somewhere mid-proof |
| Quantifier order and scope | a dependence introduced or dropped between statement and proof |
| Hidden hypothesis | a condition used in a step but absent from the statement |
| Source / theorem mismatch | a cited result that does not say what the step needs |
| Circular dependency | the conclusion assumed inside a lemma |
| Counterexample pressure | a known extremal example that violates some step |
| Gap ledger | "standard", "clear", "it remains to show" left undischarged |
| Computation certificate | exhaustiveness claimed beyond the stated finite range |
| Formalization feasibility | a step that cannot be encoded, meaning it is not yet stated |

## Attack questions

Ask each explicitly rather than reading for coherence:

- Did the proof establish a **weaker** theorem than the frozen target?
- Did a lemma assume the desired conclusion?
- Are every external theorem's preconditions actually established here?
- Does a known extremal example violate a step?
- Are the computations exhaustive only within a stated finite range?
- Does the claimed counterexample satisfy **every** hypothesis?
- Does the artifact's target match the frozen target?

## Independent re-derivation

Acceptance of a full proof or disproof requires the argument to be independently
re-derived by a **distinct method family** — a separate run, not the same route
re-read. Same-family re-derivation reproduces the original's blind spot, because
the shared machinery is exactly where an error hides. The re-derivation must pass
its own audit and reach the same frozen target hash; a re-derivation of a drifted
target is not a re-derivation.

Method families here: extremal or minimal-counterexample · algebraic or spectral
· probabilistic · constructive or algorithmic · induction or descent · reduction
or gadget · computational search · formalization-first.

## Verdicts

`accept | demote | reject | needs_explorer | needs_generator`

| Verdict | Means | Routes to |
|---|---|---|
| `accept` | every check passed and re-derivation held | report or handoff, at the exact earned status |
| `demote` | the argument survives at a weaker statement | `demotion.md` |
| `reject` | false, circular, contradicted, or source-mismatched | recorded as rejected, with the blocker |
| `needs_explorer` | one identified gap needs a lemma found | the exact gap, not the whole claim |
| `needs_generator` | a narrow checked claim is ready to formalize | the narrow claim only |

**An undecided skeptic returns `demote`, never `accept`.** Acceptance is a
positive finding and requires positive evidence; absence of a detected error is
not that. Allowing "nothing obviously wrong" to reach `accept` makes the pass a
formality that ratifies whatever it is handed, which is worse than no pass at all
because it launders the claim.

`needs_explorer` and `needs_generator` are not soft accepts. They carry the
specific object needed and leave the claim at its current status until the
returned work is itself reviewed.
