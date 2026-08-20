# Playbook: additive combinatorics

## Scope

Use for sumsets and difference sets, arithmetic progressions, density increment
arguments, Fourier uniformity, subsets of finite abelian groups, and inverse
problems.

## First normalizations

The ambient group is a choice, not a given, and most confusion here comes from
carrying a claim between groups without re-checking it.

- **Fix the ambient group explicitly**: `Z`, `Z/NZ`, or `F_p^n`. The finite-field
  model is easier because it has subspaces; the integer case has none, and a
  claim proved by passing to a subgroup does not transfer back.
- **Normalize density and scale.** Restate the hypothesis as `|A| = alpha N` and
  the conclusion in terms of `alpha` alone. A conclusion that still mentions `N`
  after normalization is either scale-dependent or misstated.
- **Identify the translation and dilation symmetries.** Any true statement must
  be invariant under them; testing this catches misstatements immediately and
  costs nothing.
- **Separate the structured and random components** of the set, since every tool
  in the area is a version of this decomposition and the claim usually concerns
  only one component.
- **Test in small cyclic groups first.** `Z/NZ` for `N` up to a few hundred is
  fully enumerable for small densities, and a claim false there is false.

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| Cauchy–Davenport, Kneser | exact lower bounds on `\|A+B\|` in `Z/pZ` and general abelian groups | Kneser's bound is stated modulo the stabilizer subgroup; ignoring the stabilizer term is the standard misuse, and torsion makes the exceptional cases real |
| Freiman and Ruzsa inverse theorems | small doubling implies containment in a generalized arithmetic progression | the rank and size bounds are exponential in the doubling constant, so nothing quantitatively tight survives |
| Balog–Szemerédi–Gowers | upgrades statistical additive structure to a genuinely structured subset | polynomial losses in the parameters, and it keeps only a fraction of the original set |
| Roth and Szemerédi via density increment | progression-freeness forces a density increment on a subprogression | each increment costs a passage to a shorter interval; the bound is only as good as the number of iterations survives |
| Fourier uniformity and large-spectrum analysis | either the set is uniform (count by the main term) or the spectrum is large (structure) | only reaches 3-term progressions; longer patterns need higher-order (Gowers) uniformity, a genuinely different theory |
| Gowers norms and the inverse conjecture for `U^k` | control of longer patterns | the inverse theorem's bounds are ineffective or tower-type in most formulations |
| Polynomial method and the cap-set argument | dramatic bounds in `F_p^n` for progression-free sets | almost entirely specific to the finite-field setting; there is no known integer analogue |
| Bohr sets and their regularization | a workable substitute for subspaces in `Z/NZ` | every regularization loses rank and radius, and the accumulated loss over iterations is the bottleneck of the whole approach |
| Hypergraph removal and containers | counting and almost-all statements for configurations | tower-type or `exp` losses; cannot deliver an explicit constant |

## Common barriers

- **The density increment loses too much per step.** Each iteration passes to a
  subprogression of length roughly `N^{c}`, so only `O(log log N)`-ish iterations
  are affordable and the resulting bound stalls well short of the conjectured
  truth. Improving the argument's bookkeeping does not change this; only a
  larger increment per step does.
- **Inverse theorems are quantitatively weak.** They convert structure into
  structure with exponential loss, so any route that applies one and then needs a
  polynomial-strength conclusion has already lost. Check the required precision
  before, not after, invoking one.
- **Torsion changes the answer.** Results in `F_p^n` and results in `Z` diverge —
  cap sets have exponentially small density in the former and the corresponding
  integer question is open. A finite-field proof is a model, not a reduction.
- **Bohr set losses accumulate.** Each regularization degrades rank and radius,
  and the composition over an iterative argument is what caps the final bound.
  This is the integer-setting analogue of not having subspaces, and it is
  structural, not technical.
- **Random sets falsify stronger variants.** A random subset of density `alpha`
  contains the expected count of nearly every configuration, so any claim that a
  configuration is *forced beyond* the random count is false unless the
  hypothesis excludes randomness. Test this first; it kills most overreaches.
- **Statistical structure is not structure.** Many additive energy hypotheses
  give only that *some* subset is structured. Treating an energy bound as if it
  described the whole set is the most common invalid step in the area, and
  Balog–Szemerédi–Gowers exists precisely because the step is not free.

## First experiments

1. Enumerate all subsets of `Z/NZ` of the relevant density for `N <= 30`, and all
   subsets of `F_2^n` for `n <= 6`, and check the claim exactly.
2. Sample random subsets at the target density and compute the configuration
   count against the random prediction. A claim asserting more than the random
   count is refuted here.
3. Compute `|A+A|`, `|A-A|`, and the additive energy for the standard families —
   intervals, subgroups, generalized progressions, random sets, and Behrend-type
   sets — and check which side of the claim each lands on.
4. Test progression-free and configuration-free constructions directly: Behrend
   in `Z`, cap sets in `F_3^n`, and compare their density against the claim's
   requirement at the same size.
5. Minimize any finite counterexample by element deletion until every deletion
   restores the claim, then check whether the minimal witness is a subgroup, a
   progression, or genuinely unstructured.

## Product ladder

1. The claim in a finite group (`Z/pZ` or `F_p^n`), with the group stated and the
   transfer to `Z` explicitly not claimed.
2. A counterexample to a stronger density claim, minimized and certified.
3. A weak quantitative bound with the loss attributed to a named step.
4. An inverse-structure lemma: what a set violating the conclusion must look
   like, stated as containment in a named structured family.
5. A conditional theorem under a uniformity or small-doubling hypothesis, with
   the hypothesis in the claim.
6. An improved increment: a larger density gain per iteration, or the same gain
   at a smaller cost in interval length.
7. A reduction to a known inverse theorem or removal lemma, with both directions
   checked and the quantitative loss stated.
