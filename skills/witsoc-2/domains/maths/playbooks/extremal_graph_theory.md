# Playbook: extremal graph theory

## Scope

Use for Turán-type problems, subgraph forcing, colouring, matching and
connectivity, degree conditions, and Ramsey/Turán hybrids stated on graphs.

## First objects to test

Every claim gets tested against these before anything is attempted, because each
one is the standard killer of a different class of false strengthening.

| Family | Kills |
|---|---|
| Complete graphs `K_n` | claims whose constant is wrong at density 1 |
| Complete multipartite, especially the Turán graph | claims that forget the extremal example is already sharp |
| Random graphs `G(n,p)` at the relevant `p` | claims that a structural conclusion follows from a counting hypothesis |
| Cycles and paths | claims that break on girth or on long induced structure |
| Bipartite extremal graphs (incidence, norm, Kővári–Sós–Turán extremals) | claims with the wrong exponent in the degenerate regime |
| Sparse regular graphs | claims that use average degree where max degree was needed |
| Blow-ups of small graphs | claims not invariant under blow-up, which most density claims must be |
| Colour-critical graphs (Mycielski, Kneser, high-girth) | claims tying chromatic number to local structure |
| Projective and incidence geometries | claims about forbidden bipartite subgraphs |

Blow-up invariance is the cheapest single test: a density statement that changes
truth value under blow-up is either false or misstated.

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| Turán, Erdős–Stone–Simonovits | exact asymptotic density for any non-bipartite forbidden graph | says nothing when `chi(H) = 2`; the whole degenerate theory sits in the error term |
| Kővári–Sós–Turán and its constructions | upper bounds for forbidden bipartite `H` | exponent is conjectural for most `H`; matching constructions exist only in special cases |
| Hall, Kőnig, Menger, max-flow min-cut | exact min-max for matching and connectivity | strictly bipartite or strictly flow-shaped; no approximate version survives perturbation |
| Brooks, degeneracy, list-colouring bounds | chromatic bounds from local data | local degree conditions do not force global chromatic structure; list version is genuinely harder |
| Dependent random choice | a large set with all small subsets having many common neighbours | needs a density hypothesis and gives sets of size `n^{c}` only |
| Graph containers | a small family covering all independent or `H`-free sets | loses constants and a logarithm per iteration; container count is `exp(o(n))`, not polynomial |
| Szemerédi regularity and the removal lemma | structure-vs-randomness decomposition of any dense graph | tower-type dependence on the accuracy; useless below density `1/log`-ish and useless for sparse targets without a sparse variant |
| Spectral extremal bounds (Hoffman, interlacing, Wilf) | clean bounds from eigenvalues alone | typically off by a constant or a logarithm; sharp only for very symmetric extremal graphs |
| Probabilistic method with alteration and the local lemma | existence of graphs avoiding many structures at once | gives existence without construction, so it cannot deliver the explicit family a reduction may need |

## Common barriers

- **Random lower bounds are already near-optimal.** For most Ramsey-type and
  girth-type targets the best known construction is a random graph plus deletion,
  and any deterministic route must beat a probability computation that is already
  tight to within a constant. Attacks that "just construct it explicitly" fail
  here for a structural reason, not for lack of cleverness.
- **The complete multipartite example is sharp.** When the Turán graph attains
  the bound, no argument that only counts edges can improve it; improvement
  requires a hypothesis the Turán graph violates. If your route never uses such a
  hypothesis, it cannot beat the example.
- **Local degree conditions do not propagate.** Minimum-degree and neighbourhood
  hypotheses constrain a ball of radius one; the target is usually global.
  Mycielski-type constructions have every local neighbourhood as simple as you
  like and unbounded chromatic number, so the gap is real and not a proof gap.
- **Regularity and containers lose the constant you needed.** Both prove the
  right shape with an `o(1)` or an `exp(-1/eps)` attached. A target stated with
  an explicit constant, or in the sparse regime, is out of reach of these tools
  as stated, whatever effort is spent on the argument.
- **Small critical obstructions.** A single small forbidden configuration
  (an odd cycle, a `K_4` minor, a specific critical graph) can carry all the
  difficulty, so exhaustive search on `n <= 10` looks clean while the true
  obstruction first appears at `n = 14`.
- **Spectral bounds are off by a log.** Eigenvalue arguments are cheap and
  usually one logarithm or one constant factor short. Reaching for them after
  a counting route stalls typically reproduces the same loss in new notation.
- **Bipartite degeneracy.** Once `chi(H) = 2` the extremal exponent is unknown
  for almost every `H`; a route that reduces to a general bipartite Turán
  exponent has reduced to an open problem.

## First experiments

1. Enumerate all graphs up to `n = 9` (or all with a fixed property to `n = 11`)
   and check the claim exactly. Record the exact bound; a bounded search only
   ever certifies its stated range.
2. Search the standard families for a forbidden-subgraph witness, then minimize
   it by vertex and edge deletion until every deletion destroys the witness.
3. Sample `G(n,p)` at the predicted threshold and one octave either side. The
   interesting outcome is the claim surviving well past where a counting
   heuristic says it should fail — that means a hidden hypothesis is doing work.
4. Blow up each small extremal example by factors 2 and 3 and re-test. A change
   in truth value locates the misstatement.
5. Compute degree sequence, clique number, independence number, chromatic
   number, and the top two adjacency eigenvalues on every near-violator found,
   and look for the invariant that separates violators from non-violators.

## Product ladder

1. A finite counterexample to a stronger variant, minimized and certified.
2. An exact threshold for small `n`, with the search range stated.
3. The claim for a restricted class: bipartite, regular, triangle-free, or
   bounded-degeneracy graphs.
4. A structural lemma about a minimal counterexample — a forced minimum degree,
   a forbidden local configuration, a connectivity floor.
5. An asymptotic bound with the loss made explicit, naming which tool contributes
   the constant and which contributes the logarithm.
6. A stability statement: near-extremal graphs are near the extremal example.
7. A reduction to a named extremal theorem, with both directions checked and the
   unmet precondition stated if the reduction is one-way.
