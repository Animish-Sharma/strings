# Campaign shape

The phase order, and why each phase precedes the next.

## 1. Refutation first — before any campaign to establish the claim

Seven passes, in order: definition stress (empty, zero, one, equality, singleton,
disconnected, low dimension, low prime, boundary exponent) · quantifier stress ·
variant stress (stronger, weaker, neighbouring — separately) · known-obstruction
import · random and model search · structured search · solver or exhaustive
search.

Record for each: the target statement, the search domain, the method, **the
bounds**, the outcome (`no_witness | witness_found | variant_false |
inconclusive`), and the next search.

> A missing counterexample is not evidence unless the search was exhaustive over
> a stated finite domain.

Skipping this is how a campaign spends its whole budget establishing something
false.

## 2. Escalation gate — before committing to a full attack

Five hard rejections. Do not proceed if:

- the argument depends on an unproved conjecture;
- a barrier was waved away rather than attacked;
- the statement has drifted from the frozen target;
- the target is a famous open problem and the only evidence is local;
- the artifact would establish something weaker than the frozen target.

## 3. The campaign itself

At least **three materially distinct routes**. The default spread: one
structural or minimal-counterexample route, one analytic/algebraic/probabilistic
route, one reduction or computational-certificate route.

If two routes share a gap, **promote the gap to a named obstruction** rather than
running both into it. Do not split a campaign into cosmetic variants of one
method — that is one route billed three times.

## 4. The gap ledger

Every occurrence of "it remains to show", "standard", "clear", "by a known
result", or "should follow" becomes a **numbered gap** unless an exact
dependency is cited.

Statuses: `open | reduced | blocked | discharged | demoted`. An artifact target
may not be dispatched while any essential gap is open, blocked, or demoted.

## 5. Exit

Exactly one of: a full candidate, a disproof witness, a partial product, a
barrier or obstruction result, or a failed-attempt synthesis.

A failed-attempt synthesis that removes a route from consideration is a real
result. Report it as one.

## Creative mode is a required stop

A run may **not** conclude `FAILED_ATTEMPT` on a target attacked only
conventionally.

Triggers: two exhausted conventional method families, or the same failure class
three times, or the repair budget spent.

Requires at least five genuinely distinct ideas, ranked by (cheapness of the
first falsifying test) x (how directly it dodges the shared obstruction) — wild
but cheaply testable beats safe but expensive. One axis per idea, timeboxed, and
no status credit for a reframing that did not check out.

Idea menu: reformulate in an orthogonal setting · import machinery from a
neighbouring field · let computation lead and prove the guess · attack the
formalization rather than the mathematics · strengthen for induction ·
generalize to the cleaner ambient setting · dualize · minimal criminal.

## Ontology pivot

After **two** failed attacks in the native representation, a third native attack
is forbidden. Require a structure-preserving map to an orthogonal representation,
stating what it preserves and where the obstruction reappears.

Common pivots: graph theory → spectral methods or polynomial algebra · number
theory → finite algebra or additive Fourier · additive combinatorics → Fourier
and linear algebra, or ergodic dynamics · geometry → polynomial method · order
theory → topology · combinatorics → the linear algebra method or entropy
compression.

A pivot is a direction, never a result: everything it produces enters
`CONJECTURE`.
