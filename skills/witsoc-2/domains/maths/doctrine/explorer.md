# Explorer — mathematics

Loaded by the general Explorer when a claim routes to this pack. Everything in
`explorer/SKILL.md` still applies; this adds what is specific to mathematics.

## Freezing

The frozen record binds, byte-exact:

- the original problem text as the requester wrote it;
- the canonical statement, with quantifier order explicit;
- variables and their domains;
- every definition the statement depends on;
- the `GIVEN` block (hypotheses) and the `CLAIM` block, hashed separately —
  drift shows up in one or the other, and separating them says which;
- `allowed_external_facts`: results the argument may cite. A citation outside
  this list is out-of-scope, not a step.

Separate hashes matter because the characteristic failure here is a `CLAIM`
quietly weakening while the `GIVEN` stays put, or a hypothesis appearing in a
binder that was never in the frozen `GIVEN`.

## Falsify before committing

The three frame layers, instantiated:

1. **Degenerate** — empty set, singleton, zero, one, the trivial group, `n = 0`
   and `n = 1`, empty graph, constant function.
2. **Symmetry** — relabel, permute, dualize, negate, swap quantifiers, take the
   complement.
3. **Regime extremes** — both ends of every parameter, asymptotic limits,
   and the boundary where a hypothesis becomes tight.

Then check the statement against the parameter regime where the *stated
hypotheses are barely satisfied*. That is where a missing hypothesis lives.

Run the `bounded` tier on small cases before committing to any approach. It is
cheap, and a counterexample at `n = 4` saves the entire campaign. Record the
bounds searched — outside them the search establishes nothing.

## Retrieval

Query the corpus (`scripts/corpus.py`) for the exact declarations an approach
would need, before ranking it. What comes back is one of:

- **known premise** — exists in Mathlib with a resolved name, type, and import;
- **search target** — plausibly exists but is unresolved;
- **absent** — would have to be established first, which is a sub-claim, not a
  citation.

Never assume a premise exists because it *should*. A guessed declaration name is
not evidence, and an approach resting on one is unranked until resolved. Record
rejected candidates with the exact blocking reason — a wrong name, a mismatched
type, an unmet precondition — so the same bad retrieval does not recur.

An empty corpus result is information. It usually means the formulation does not
match how the library states the concept, which is a reframing signal.

## Choosing a tier

Pick the cheapest tier that can reach the status the claim needs:

| Need | Tier | Ceiling |
|---|---|---|
| Is the shape even coherent? | `structural` | `SKETCH` |
| Does it hold for small cases? Is there a counterexample? | `bounded` | `CHECKED_BOUNDED` |
| Establish it outright | `kernel` | `VERIFIED` |

Freeze the choice before Generator starts, so a failed kernel attempt cannot be
downgraded to a bounded check and reported as if it were the same result.

Never open at `kernel` because the problem "looks hard". The cheap tiers are
also the fastest way to learn *how* it is hard, and formalizing early is a
microscope — it exposes missing definitions, wrong quantifier order, and
unavailable dependencies long before it proves anything.

## Ranking

`expected_value = target_fidelity × P(completion) × checkability`, ranked by gain
per unit cost. In this field `checkability` means: are the premises this approach
needs actually in the library, and is the statement expressible without inventing
new definitions?

Method families count as distinct only if the *key method* differs — extremal,
probabilistic, algebraic/spectral, constructive, induction/descent,
reduction/gadget, analytic. Two arguments that differ only in manipulation are
one family.

## Handing to the Researcher

Beyond the frame's work item, include: the variant/status ledger (what is known
for neighbouring statements), best known bounds with sources, obstructions
already recorded, precondition gaps found during retrieval, counterexample
pressure from the bounded pass, and the smallest tractable products worth
having.
