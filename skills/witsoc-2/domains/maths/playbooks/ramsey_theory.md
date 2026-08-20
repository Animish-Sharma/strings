# Playbook: Ramsey theory

## Scope

Use for forced monochromatic structures, colouring avoidance, Ramsey/Turán
hybrids, van der Waerden and Hales–Jewett style questions, and extremal
set-colouring.

## First objects to test

The area is a contest between constructions and counting, so the first move is
always to build the best construction anyone knows and see how far it gets.

| Family | Why it is first |
|---|---|
| Random colourings, each edge or cell coloured independently | the benchmark lower bound; if the claim beats a random colouring only by a constant, the target is essentially the known frontier |
| Cyclic and algebraic colouring templates (Paley, quadratic residues) | the standard explicit constructions; they match random bounds in small cases and then fall behind, which localizes where explicitness costs |
| Blow-ups of small colourings | tests whether the avoidance property is blow-up stable, which decides whether small-case data extrapolates at all |
| Finite fields and affine or projective geometries | the source of most exact lower-bound constructions for hypergraph and arithmetic variants |
| Greedy and iterated-greedy colourings | the cheapest deterministic baseline; beating it is the minimum bar for a new construction |
| Known extremal lower-bound constructions for the exact parameters | prevents rediscovering a 1975 construction and reporting it as a product |

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| Probabilistic method with alteration | lower bounds `R(k,k) > 2^{k/2}`-shaped, essentially free | existence only, and the constant in the exponent has resisted improvement for decades |
| Lovász local lemma | existence when bad events are sparsely dependent | needs `e p d <= 1`; a dependency degree slightly too large kills it outright, and the constructive versions add further conditions |
| Hypergraph containers | almost all `H`-free colourings live in few near-extremal containers | loses constants and a logarithm per application, and the container family is `exp(o(n))`, so nothing polynomially precise survives |
| Dependent random choice | a set whose small subsets all have large common neighbourhoods | requires density; output size is `n^{c}` with `c` shrinking fast in the parameters |
| Stepping-up lemmas | transfers a bound from `k`-uniform to `(k+1)`-uniform hypergraphs | needs the base case to be strong enough, and it does not start at graphs — the graph-to-3-uniform step is exactly the missing one |
| van der Waerden and density Hales–Jewett machinery | forced arithmetic structure in any colouring | primitive bounds are Ackermannian; even Gowers' bounds are tower-type, so no explicit small case follows |
| Hypergraph Ramsey bounds (Erdős–Hajnal–Rado) | the standard tower-height upper and lower bounds | upper and lower differ by one exponential level, and closing that gap is the open problem, not a lemma |
| Finite field and Behrend-type constructions | explicit colourings beating naive bounds | highly parameter-specific; small changes to the forbidden configuration break them entirely |
| SAT and exact search on small cases | certified exact values and certified lower bounds | the search space grows like `2^{binom(n,2)}`; certified values stop around `R(5,5)` and no method extends them |

## Common barriers

- **Random beats deterministic intuition.** For most parameters the best lower
  bound is a random colouring, and it is tight to within a constant factor in the
  exponent. Any construction route must state what it does that randomness does
  not, or it will land below the known bound.
- **Induction recurrences lose too much.** The standard `R(k,l) <= R(k-1,l) +
  R(k,l-1)` shape is what produces the `4^k` upper bound, and each step throws
  away the structure of the previous colouring. A route built on this recurrence
  inherits its loss whatever is done to the base case.
- **Container and regularity bounds lose constants and logarithms.** They prove
  that almost all colourings are near-extremal but never say which, and the
  approximation cannot be tightened below the tool's own error term. Targets with
  an explicit constant are out of scope for these methods as stated.
- **Diagonal and off-diagonal variants diverge.** `R(k,k)` and `R(3,k)` have
  different truth shapes and different tools — `R(3,k) = Theta(k^2/log k)` is
  settled while the diagonal exponent is not. Importing a technique across that
  boundary is the most common wasted route here.
- **Small exact cases do not predict asymptotics.** Every exactly known Ramsey
  number lies in the regime where the asymptotic behaviour has not started.
  Fitting a curve to `R(3,3)` through `R(4,4)` produces a conjecture with no
  evidential weight, and the miner ceiling exists for this reason.
- **Colouring avoidance is not blow-up stable in general.** A colouring avoiding
  a configuration may lose that property under blow-up, so small-case
  constructions do not automatically lift. Check stability before building a
  family on one.

## First experiments

1. SAT-encode the existence of a colouring avoiding the target configuration at
   the critical parameter, and run both directions — satisfiable gives a
   certified lower bound, UNSAT gives a certified upper bound at that size.
2. Random search near the predicted threshold with local repair, recording where
   the success probability crosses one half. That crossing is the empirical
   threshold to compare against the union-bound prediction.
3. Minimize any avoiding colouring found: repeatedly delete a vertex or merge two
   colour classes until the property breaks, then certify the minimal object.
4. Compute exact values for all small cases the search reaches, and check whether
   the ratio to the asymptotic prediction is even monotone in that range.
5. Blow up each small avoiding colouring by factors 2 and 3, and test whether the
   avoidance survives. Failure means the construction cannot be a family.

## Product ladder

1. An exact small case, with the search method and the exhaustiveness stated.
2. A SAT or exhaustive certificate for a finite lower or upper bound, hashed and
   reproducible.
3. A counterexample to a stronger threshold claim, which narrows the target
   without touching it.
4. An improvement to the recurrence or its base case, with the resulting
   asymptotic loss made explicit.
5. A construction family: an explicit infinite sequence of colourings, with the
   parameter dependence stated.
6. An off-diagonal or restricted-uniformity special case, kept separate from the
   diagonal claim.
7. A reduction to a hypergraph, container, or density statement, with both
   directions checked.
