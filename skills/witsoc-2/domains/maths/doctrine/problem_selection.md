# Problem selection — choosing the product

The goal is not the grandest target. It is the target most likely to produce
verified progress on the frozen one. Choosing by ambition burns the budget;
choosing by ease produces true statements that do not add up.

## Candidates

List **3-7** candidate products before scoring any of them. A single candidate is
not a selection, it is a preference with a table attached.

Each candidate records: the product kind · the exact statement · its relation to
the original problem · **the barrier lemma it targets** · how it helps prove or
disprove that lemma · the background required · the likely verification route ·
the likely artifact · the first decisive test.

Product kind is one of:

`special_case | bound | conditional_theorem | reduction | obstruction |
counterexample | computation | conjecture | failed_attempt`

`failed_attempt` and `obstruction` are on that list deliberately. If every
candidate scores low, selecting one of them is the correct outcome — but the
record must still name the barrier lemma schema that failed, or the run has
produced nothing reusable.

## Scoring

Score each criterion 0-5, then weight:

| Criterion | Weight | What it measures |
|---|---:|---|
| Target fidelity | 3 | how much of the frozen target this actually settles |
| Actual-lemma leverage | 3 | whether it moves the specific blocking lemma |
| Novelty | 1 | whether the result is already in the literature |
| Tractability | 2 | reachable within the budget |
| Verification ease | 2 | checkable by computation, artifact, or short independent proof |
| Barrier leverage | 2 | whether it tests, bypasses, or converts a named barrier |
| Experimentability | 1 | whether a cheap first falsifying test exists |
| Artifactability | 1 | whether it can become a formal artifact |
| Source confidence | 1 | how solid the external results it leans on are |

```text
total = 3*target_fidelity + 3*actual_lemma_leverage + novelty
      + 2*tractability + 2*verification_ease + 2*barrier_leverage
      + experimentability + artifactability + source_confidence
```

Maximum 80. The two weight-3 criteria carry 30 of it, which is the point: the
score is built so that fidelity and lemma leverage cannot be outvoted by the
comfortable criteria.

## The overriding rule

**A high-tractability weak result cannot beat an actual-barrier-lemma route
unless the weak result has explicit lemma leverage.**

Without this rule the scoring degenerates. Tractability, verification ease,
experimentability, and artifactability all correlate with easiness, so a
sufficiently trivial product accumulates 6 of the 8 available weight and wins
while settling nothing. The rule severs that path: leverage on the blocking lemma
has to be argued, not scored around.

Select the highest total otherwise. A lower-scoring product may be selected only
with a recorded strategic reason — exposing a suspected false variant, or
building a reusable formal lemma — so that the override is auditable rather than
a taste.

## Preferences

- Narrow products with clear stop conditions. A product with no stop condition
  consumes the whole budget by default.
- Products attacking a named barrier, and specifically the missing lemma the
  frozen target needs.
- Products checkable by computation, artifact, or short independent proof —
  because an unverifiable win is indistinguishable from a mistake.

## Penalties

- Weaker variants whose relation to the barrier lemma is not explicit. This is
  the main way a campaign drifts off target while feeling productive.
- Dependence on vague external theorems or broad literature claims: the
  dependency cannot be precondition-audited, so the result cannot be trusted.
- Products whose failure would teach nothing. A product is worth running when
  both outcomes are informative; when only success is informative, the expected
  value is the success probability alone.

## Output

The selected product goes to the run record. Rejected candidates go to memory
when they carry reusable information — a rejected candidate with a recorded
reason is what stops the next run from re-deriving the same decision.
