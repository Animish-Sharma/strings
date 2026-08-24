# Playbook: the probabilistic method

## Scope

Use for existence claims with no construction in sight, lower bounds on
Ramsey-type parameters, claims about typical behaviour of a random structure
(`G(n,p)`, random regular graphs, random subsets, random colourings), threshold
and sharp-threshold statements, any claim of the form "there is a colouring with
no monochromatic X", and any counting argument that nearly works and is off by
a logarithm.

Load alongside `extremal_graph_theory.md` whenever the target is an extremal
number: the random lower bound and the algebraic upper bound usually meet at a
gap, and the gap is the problem.

## First objects to test

- `G(n, 1/2)`, then `G(n, p)` at `p = n^{-a}` for `a` on a grid — the exponent
  is where behaviour changes, not the constant.
- A random `d`-regular graph via the configuration model, and the same claim in
  `G(n, m)`. If the claim survives one and not the other, independence was doing
  the work.
- A uniformly random 2-colouring of the edges or of `[n]`.
- A random tournament on `n` vertices.
- A random subset of `[n]` at density `p`, each element independent.
- Random `±1` vectors, for anything that becomes a Rademacher sum.
- The **alteration** version of every object above: sample, then delete the
  witnesses. Sampling and sample-then-delete are different constructions with
  different answers, and the second is usually the one that works.

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| First moment / union bound | an object avoiding every bad event, whenever the expected number of bad events is below 1 | fails the moment `sum Pr[bad] >= 1`, and typically lands a logarithmic factor away from the truth because it charges overlapping events twice |
| Second moment (Chebyshev) | concentration of a count, and 0-1 behaviour | needs `Var = o(E^2)`; dies exactly at thresholds, where the count is carried by rare instances containing a dense sub-copy |
| Lovász Local Lemma, symmetric form | existence when each bad event is independent of all but `d` others and `e p (d+1) <= 1` | existence only — the constructive version needs Moser–Tardos and its resampling conditions; the factor `e` and the dependency count are where it actually breaks |
| Chernoff / Hoeffding | exponential tails for sums of independent bounded variables | genuine independence required; loses to martingale methods as soon as the quantity depends on earlier choices |
| Azuma / McDiarmid bounded differences | concentration for any Lipschitz function of independent choices | the Lipschitz constant enters squared, so one high-influence coordinate destroys the bound even when everything else is tame |
| Alteration / deletion | a constant-to-logarithmic improvement over the union bound | the object must stay in the class after deletion, and deletion routinely destroys exact size, regularity, or connectivity |
| Janson and Harris–FKG inequalities | a sharp upper tail for avoiding a monotone family, and correlation in the right direction | Janson needs increasing events on a common ground set and degrades badly once the pair-dependency term `Delta` is comparable to the mean |
| Talagrand's inequality | concentration for certifiable Lipschitz functions, where Azuma is too weak | the certificate condition has to be checked, and the constants are poor enough to matter in a tight problem |
| Entropy and Shearer's lemma | counting bounds for structures with local constraints | gives a count, not an object; converting a count into the structure you wanted usually loses the constraint that made it interesting |

## Common barriers

**The union bound charges overlaps twice.** Whenever the bad events are nearly
disjoint in truth, the first-moment answer is short by roughly the number of
overlaps not credited. This predicts which existence proofs come out a
logarithm below the real answer, and it says the fix is inclusion–exclusion at
second order or alteration, not a sharper estimate of the same sum.

**Second-moment collapse at a threshold.** When `E[X] -> infinity` while
`Pr[X = 0]` stays bounded away from zero, the expectation is carried by a
vanishing family of instances that contain a dense sub-structure. Every
"expectation is large, therefore it exists" argument fails there, and the
standard repair is to count only balanced copies — which changes the estimate
and often the whole plan.

**The local lemma cannot see global constraints.** LLL needs a sparse
dependency graph. For events defined by a global property — connectivity,
Hamiltonicity, a spanning condition — the dependency count grows with `n`, and
`e p (d+1) <= 1` then forces `p` exponentially small. A campaign planning to
LLL its way to a global property is finished before it starts, and this is
visible by computing `d` for `n = 8`.

**Concentration is not existence.** A functional can concentrate beautifully
around a mean that sits on the wrong side of the target. Proving concentration
feels like progress and moves nothing; the question is always where the mean is,
and that is a different computation.

**Random is extremal only up to constants.** For many extremal problems the
truth is an algebraic construction, and the random lower bound plateaus strictly
below it — Kővári–Sós–Turán against norm graphs is the standard instance. So a
probabilistic route to an exact extremal constant will stall at a fixed
distance, and the distance does not shrink with effort.

**Derandomization needs a pessimistic estimator.** Conditional expectation turns
an existence proof into an algorithm only when the estimator is computable. With
no estimator, a claim that asked for an explicit object has not been addressed,
however clean the existence proof is.

**Independence is usually false in the object you care about.** Random regular
graphs, the configuration model, and any model with fixed statistics all break
independence. A result proved in `G(n,p)` reaches `G(n,m)` or `G_{n,d}` only
through contiguity or two-round exposure, and that transfer has its own
hypotheses which are frequently the unmet ones.

## First experiments

1. Enumerate every 2-colouring of `K_n` for `n = 5, 6, 7`, record the exact
   minimum number of monochromatic triangles, and compare with the expectation
   under a uniform random colouring. If random is already beaten at `n = 7`, the
   probabilistic lower bound is not the right target.
2. Sample `10^5` copies of `G(n, 1/2)` for `n = 20, 30, 40`, record the maximum
   clique, and compare with the first-moment prediction near `2 log_2 n`. This
   measures the union-bound loss on a case where the truth is computable.
3. Compute `d` and `p` exactly for the LLL formulation of the target at
   `n = 6..12` and evaluate `e p (d + 1)`. If it exceeds 1 and grows, the local
   lemma is out, and knowing that costs an afternoon rather than a fortnight.
4. Run the alteration version — sample, delete, record the surviving size — over
   `10^4` trials at three densities. If the deletion loss is the entire gain,
   the route is the union bound wearing a different hat.
5. Compute `Var/E^2` for the relevant count over `n = 10..60` against a grid of
   `p`, and locate where it crosses 1. That crossing is the threshold, and it
   tells you which side of the problem the second moment can speak about.

## Product ladder

1. A first-moment lower bound with an explicit constant, confirmed against
   exhaustive enumeration at small `n`. Verification: `scripts/tiers/bounded.py`.
2. The same bound improved by alteration, with the exact factor gained stated
   separately from the base bound.
3. An LLL version with the dependency count `d` computed rather than estimated,
   and the range of `n` where the condition holds.
4. A concentration statement for the governing functional, with the Lipschitz
   constant recorded — because the constant, not the inequality, is what a later
   step will need.
5. A threshold location `p*`, with first-moment behaviour above it and
   second-moment behaviour below it, each verified on its own side.
6. A derandomization: an explicit construction matching the probabilistic bound,
   or a recorded obstruction to one, which is a genuine product and closes the
   question of whether to keep trying.
7. A counterexample to a **stronger** variant, found by random search and then
   certified deterministically. The original stays open and the space where it
   can live is smaller, which is the cheapest real progress in this area.

Each rung fails informatively: a failed rung 3 teaches that the constraint is
global, a failed rung 5 locates the threshold on the other side, and a failed
rung 6 is itself the obstruction result.
