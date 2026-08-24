# Playbook: algebraic and spectral methods

## Scope

Use for claims about eigenvalues of a graph or matrix family, expansion and
pseudorandomness, independence and chromatic numbers approached through a
dimension or eigenvalue bound, set systems with restricted intersections,
polynomial-method claims (cap sets, finite-field Kakeya, distinct distances),
and any statement where the object carries a group or field structure that a
purely combinatorial argument is ignoring.

Load alongside `probabilistic_method.md` on extremal numbers: the algebraic
construction and the random bound are usually the two ends of the gap.

## First objects to test

- The Paley graph on `q` vertices, `q = 1 mod 4` — the standard pseudorandom
  object, and the standard source of a counterexample to "pseudorandom implies".
- The hypercube `Q_n` and its adjacency and Laplacian spectra.
- Kneser graphs `K(n, k)`, where the answer is known exactly and any method can
  be calibrated against it.
- Incidence graphs of projective planes `PG(2, q)` — the extremal examples that
  beat random for Zarankiewicz-type problems.
- Cayley graphs on `F_2^n` for a small generating set, so Fourier analysis is
  available in closed form.
- The Sylvester–Hadamard matrix, for anything that becomes a rank or sign
  question.
- A random `d`-regular graph as the benchmark: an algebraic construction that
  does not beat random on the target parameter is not yet doing anything.
- The Frankl–Wilson family, for restricted-intersection claims.

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| Expander mixing lemma | edge counts between any two sets, from `lambda` alone | the error term is useless once `lambda` approaches `d`, and the lemma says nothing about irregular graphs without a normalization that changes which theorems apply |
| Cauchy interlacing and the Hoffman ratio bound | an upper bound on the independence number, and eigenvalue control for induced subgraphs | the clean ratio form needs regularity; it returns a number and never a structure, so tightness has to come from elsewhere |
| Alon–Boppana | `lambda_2 >= 2 sqrt(d-1) - o(1)`: a ceiling on how good expansion can be | asymptotic in `n`, so it constrains families and says nothing about any fixed graph |
| Combinatorial Nullstellensatz | a combinatorial existence statement from a single non-vanishing coefficient | the difficulty moves into computing the coefficient of one monomial in a large product, which is frequently as hard as the original problem |
| Polynomial method / slice rank (Croot–Lev–Pach) | exponential upper bounds for cap-set-shaped problems | tied to `F_q^n`; there is no general transfer to `Z/N`, and the analogues where the truth differs are known |
| Linear algebra bound (oddtown, Frankl–Wilson) | upper bounds on set systems with restricted intersections | the bound is a dimension, usually loose by a polynomial factor, and it is one-sided by construction |
| Schwartz–Zippel | identity testing and zero-set size bounds | needs a field large relative to the degree, and returns a probabilistic statement where an exact one may be required |
| Fourier analysis on abelian groups | diagonalizes Cayley graphs and turns convolution into multiplication | needs the group; the non-abelian version costs the representation theory, and the characters are rarely as usable |
| Trace / moment method | bounds on the spectral radius by counting closed walks | even moments only, and it loses logarithmic factors against sharp results |

## Common barriers

**Cospectral graphs are invisible to spectra.** Two graphs can share a spectrum
and differ on the property being claimed. So any route ending "the gap is small,
therefore P" needs `P` to be a quasirandom property in the Chung–Graham–Wilson
sense, and a campaign that never checks this discovers it at the end rather than
at the start. One cospectral pair with different parameter values kills the
whole spectral approach in an afternoon.

**The ratio bound is tight only under rigid eigenspace structure.** On anything
less symmetric it loses a factor that no sharpening recovers, because the loss
is the distance between the graph and the one the bound is exact for. A plan
routing to an exact extremal number through Hoffman will land near it and stop.

**Nullstellensatz relocates the difficulty rather than removing it.** When the
polynomial's degree grows with `n`, the target coefficient is itself a
combinatorial identity of comparable hardness. The method is a genuine win when
the coefficient is computable in closed form and a treadmill otherwise, and
which case you are in is decidable at `n = 5` by direct symbolic computation.

**The polynomial method does not cross out of the finite-field model.** The
slice-rank bound is essentially tight for `F_q^n` and there are analogues where
the integer truth differs, so a plan to import a cap-set argument into `Z/N`
fails at the transfer step, not at the estimate. Planning the estimate first
wastes the whole run.

**Dimension bounds are one-sided.** Linear algebra gives an upper bound on a
family's size and never produces the family. A campaign needing tightness must
supply the construction from a different area, and if none exists the ladder
stops at the upper bound — which is worth knowing before rung 1.

**Spectral methods degrade sharply with irregularity.** With a heavy-tailed
degree sequence the top eigenvalue is governed by the largest degree and carries
no global information. The repairs — normalized Laplacian, non-backtracking
spectrum — change which theorems are available, so the fix is a different plan
rather than a correction to this one.

**Characteristic is an invisible hypothesis.** Rank over `F_2`, over `F_p`, and
over `Q` are different numbers. A proof that computes a determinant modulo 2 for
a claim about the integers has a gap exactly where the reduction was assumed,
and the gap is silent because every step type-checks.

## First experiments

1. Compute the full spectrum of the target family for `n = 5..30` in exact
   arithmetic and plot `lambda_2` against the bound the plan needs. If the
   spectral quantity cannot reach the target's precision even in the small
   range, no theorem will fix that.
2. Compare the Hoffman bound with the exhaustively computed independence number
   for `n <= 20`. This measures the ratio-bound loss on this specific family
   rather than in general, and the number decides whether rung 2 is worth
   attempting.
3. For a Nullstellensatz plan, compute the target monomial's coefficient
   symbolically at `n = 3..8`. Zero at any of them ends the route; nonzero with
   a visible pattern is the proof.
4. Compute the slice-rank bound at the exact instance size for `n <= 10` and
   compare with brute-force maximum cap size. The slack tells you whether the
   polynomial route has anything left to give on this problem.
5. Search for a cospectral pair differing in the target parameter at `n <= 12`.
   A single hit ends the spectral approach, which makes this the highest-value
   experiment in the list and the one to run first.

## Product ladder

1. The exact spectrum of the family with multiplicities, in exact arithmetic.
   Verification: `scripts/tiers/bounded.py` with `scripts/backends/exact.py`.
2. A ratio or interlacing bound with its loss against small-case truth recorded
   as a number, not as "some loss".
3. A pseudorandomness statement — `lambda_2 <= f(d)` — together with exactly
   what the expander mixing lemma then buys for this target.
4. A dimension or rank upper bound for the set-system formulation.
5. A polynomial-method bound in the finite-field model, stated with the transfer
   obstruction to the integer case rather than with a hope about it.
6. An explicit algebraic construction beating the random lower bound, or a
   recorded obstruction to one.
7. A cospectral counterexample refuting the spectral route. This is a real
   product: it removes an approach from consideration permanently, and it is
   cheaper to find than any of the rungs above it.

Rung 7 sits at the bottom in cost and at the top in what it settles, which is
why experiment 5 runs before experiment 1.
