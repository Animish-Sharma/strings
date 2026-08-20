# Playbook: Erdős-level frontier problems

The meta-playbook. It sits above the subfield playbooks and is loaded alongside
one of them, never instead of one. Its subject is not a technique but the
failure mode of attacking a famous problem head-on with a generic tool.

## Recognition

Treat a problem as Erdős-level when several of these hold: the target is
asymptotic (`o(.)`, `O(.)`, a density, a threshold, a growth rate); the objects
are trivial to define and hard to control globally; the known generic bounds are
provably too weak; many neighbouring variants exist with different truth values;
and the realistic first deliverable is a partial result rather than the theorem.

The statement being short is not evidence of tractability. It is evidence that
every easy attack has already been tried by someone, which is what makes the
generic-bound barrier below the default state rather than a risk.

## The central tension

Write this record before choosing any approach. It is the single most useful
artifact in an Erdős-level campaign, because it names what the campaign must
beat rather than what it hopes to prove.

```markdown
### Central Tension
- Quantity to bound or force:
- Generic maximal or minimal behaviour:
- Extra structure the problem's hypothesis supplies:
- Why the generic bounds fail:
- What special structure might beat the generic barrier:
```

The shape it almost always takes: *generic objects reach scale X, but objects
satisfying the problem's equation, avoidance, or density condition may be forced
below X.* These problems are advanced by exploiting the special structure, not by
improving the generic bound — the generic bound is usually already sharp for
generic objects, so improving it is impossible rather than merely hard.

A route that never uses the extra structure cannot resolve the tension. Checking
each proposed route against the third and fifth lines of this record removes most
of them in a minute.

## Theorem retrieval spine

Build the ranked list before proof search, not during it.

| Family | Candidate theorem | Needed form | Missing preconditions | Barrier if unavailable |
|---|---|---|---|---|

Draw from: maximal and normal order estimates · sieve and parity-barrier results
· primitive divisor and valuation tools · density increment, regularity and
container tools · the probabilistic method and random-construction lower bounds ·
extremal graph and set bounds · Fourier and spectral inequalities · inverse
theorems · compactness and local-to-global principles · known classifications and
finite obstruction theorems.

A theorem is promoted onto the spine only after its exact statement and
preconditions are audited against a pinned source. An unaudited citation is how a
campaign builds a full argument on a hypothesis the cited theorem does not
supply, and discovers it at formalization.

## Barrier classes to check every time

- **Generic bound barrier** — the known bound is sharp across all objects, so it
  can only be beaten on the structured subclass, and only by an argument that
  touches the structure.
- **Extremal construction barrier** — a known family comes within `o(1)` of
  violating the conclusion, so any proof must distinguish it, and any proof that
  does not mention it is wrong.
- **Local obstruction barrier** — a congruence, parity, prime, or boundary
  condition eliminates the whole candidate family, usually cheaply and usually
  before the analytic work is worth starting.
- **Dependency-chain barrier** — satisfying the hypothesis forces recursive
  constraints, so the search tree branches faster than it prunes and exhaustive
  attacks stall at small parameters.
- **Constant-loss barrier** — the available tools prove the right shape and lose
  a constant or a logarithm that the target's precision cannot absorb. This is
  fatal at the statement level; no amount of care in the argument recovers it.
- **Rare-object barrier** — examples are sparse enough that a large computation
  contains a handful, and any pattern over a handful is a coincidence.
- **Variant drift barrier** — a neighbouring variant is settled, and its solution
  is quoted as though it applied. State the exact difference between the settled
  variant and the frozen target, in one line, before citing it.

## Attack portfolio

Produce **at least five genuinely distinct attack families** before any full
attempt, unless a pinned source already settles the problem.

1. Extremal or counterexample construction.
2. A structural lemma route on a minimal or extremal violator.
3. A probabilistic or random-model route.
4. An analytic or asymptotic estimate route.
5. A computational search or finite-model route.
6. A reduction to a known theorem or a known barrier.

Rank by information value, not by likelihood of success. An attack that will
prove a useful obstruction if it fails outranks a speculative full proof that
teaches nothing when it dies. Five cosmetic variants of one method are one
family, and counting them as five is the standard way this rule is evaded.

## Product ladder

Do not attack the full problem first unless the route is unusually clear.

1. Computation and small cases.
2. Counterexample pressure against the stronger variants.
3. A special family.
4. A bounded-parameter case.
5. A conditional theorem.
6. A structural lemma.
7. A reduction or equivalence.
8. The full attempt.

Each rung needs a verification route before it is attempted, and each failed rung
must either teach a barrier or demote a false strengthening. A rung whose failure
produces neither was not a rung; it was a guess with a number next to it.

## Full-solution readiness

Full-attack mode is not allowed until **all seven** hold. Each one exists because
a campaign that skipped it produced a confident wrong answer.

| Precondition | Prevents |
|---|---|
| Exact variant alignment with the frozen target | proving a neighbour and reporting it as the target |
| The central tension resolved by a **named** mechanism | a full attempt with no account of how the generic barrier is beaten |
| At least one nontrivial rung verified or bounded-checked | committing the budget on an untested picture |
| No active counterexample pressure | attacking something the evidence says is false |
| Every external fact on the retrieval spine precondition-audited | an argument resting on a hypothesis the cited theorem does not give |
| Explorer can express the proof as a dependency DAG | a narrative that has no decomposition and therefore no gaps to close |
| Generator can artifact at least the key lemma or a bounded subresult | a full attempt with nothing formalizable in it |

If any fails, continue on the ladder with partial products. Declaring readiness
without the seven is the single most expensive error available at this level: it
converts a campaign that would have produced three real partial results into one
that produces nothing.
