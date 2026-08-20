# Playbook: multiplicative number theory

## Scope

Use for divisor sums, Euler's totient, abundancy and perfect or multiperfect
numbers, smoothness, prime factor counts, valuations, and any claim about a
multiplicative function.

## First normalizations

Nothing is readable in this area until the claim is rewritten in local data.
Apply all five before attempting anything.

- Factor `n = prod p_i^{a_i}` and restate the claim in terms of the exponent
  vector, not `n`. Most false claims here are false because `n` was treated as a
  single magnitude when the truth depends on the shape of the factorization.
- Rewrite every multiplicative function as an Euler product. This turns a global
  claim into a product of independent local claims and exposes immediately
  whether any single prime can carry the whole obstruction.
- Isolate the local factors `f(p^a)` and check the claim prime by prime. A claim
  that fails at one small prime is dead before any analytic work starts.
- Separate the squarefree kernel from the exponents. Many statements are
  genuinely about the kernel, with the exponents contributing a bounded factor —
  and if so, the bounded-exponent case is a real product, not a toy case.
- Record `omega(n)`, `Omega(n)`, the largest prime factor, the smoothness, and
  every integrality or valuation constraint the hypothesis forces. These are the
  parameters the ladder is built on.

## Theorem families

| Tool | Buys | Costs |
|---|---|---|
| Gronwall, Robin, and maximal-order bounds for `sigma`, `phi`, `d` | sharp asymptotic extremes of the standard multiplicative functions | sharp for *arbitrary* `n`; gives nothing extra for `n` carrying a special structure, which is usually the whole point |
| Mertens' theorems and Euler product estimates | control of `prod_{p<=x}(1-1/p)` and its relatives | only for products over all primes below a bound; a product over a *constrained* prime set needs a sieve, not Mertens |
| Zsigmondy's primitive divisor theorem | a new prime divisor of `a^n - b^n` for every `n` | a listed finite set of exceptions, and the exceptions are exactly where hard cases hide |
| Lifting the exponent and valuation lemmas | exact `v_p` of structured expressions | requires the precise `p \| a - b` and `p` odd side conditions; the `p = 2` case is a separate statement people misquote |
| CRT and local-global congruence analysis | reduces a global constraint to independent local ones | local solvability everywhere does not give a global solution; asserting it is the classical failure mode here |
| Sieve methods (Selberg, large sieve, Brun) | upper bounds of the right order for counts of constrained integers | the parity barrier: no sieve alone distinguishes numbers with an even from an odd number of prime factors, so no sieve alone produces primes |
| Smooth number estimates (Dickman, Hildebrand–Tenenbaum) | density of `y`-smooth integers up to `x` | valid only in stated ranges of `u = log x / log y`; the uniformity is exactly what gets misquoted |
| Classification results on perfect, multiperfect, and abundant numbers | strong structural constraints on any hypothetical example | mostly conditional, and the odd cases usually reduce to open problems |
| Chebotarev and Dirichlet-type prime distribution | primes in prescribed residue classes and splitting behaviour | effective versions carry ineffective constants unless GRH is assumed; an ineffective constant kills a computational finish |

## Common barriers

- **Generic maximal-order bounds are already sharp.** Robin- and
  Gronwall-type bounds are attained along a known sequence, so no route that
  only uses "n is an integer" can improve them. Progress requires the special
  hypothesis to force the factorization off that sequence, and a route that
  never touches the factorization cannot do this.
- **Integrality forces dependency chains.** A constraint like `sigma(n)/n = k`
  makes each prime's contribution determine which primes are admissible next, so
  the search is a tree of forced choices rather than a free product. The tree
  branches faster than it prunes, which is why exhaustive attacks stall at
  moderate `omega(n)`.
- **Primitive divisor exceptions.** Zsigmondy's finite exception list is small,
  which makes it easy to forget, and the target case is often inside it. Every
  citation must be precondition-audited against the actual exception table.
- **The parity barrier.** Sieve upper and lower bounds differ by a factor of two
  in exactly the situations where a claim about primes is wanted. A route whose
  final step is "the sieve lower bound is positive" is blocked for a structural
  reason and no amount of optimization of the sieve weights removes it.
- **A single small prime can obstruct everything.** Congruence conditions mod 3,
  4, 8 or 9 routinely eliminate an entire candidate family. Check them before
  building any analytic machinery, since finding one afterwards invalidates the
  work rather than completing it.
- **Exponent explosion.** Allowing unbounded exponents makes the search space
  infinite in a direction where the claim is usually easy; the difficulty is in
  the squarefree direction. Bounding exponents is therefore an honest special
  case, not a cheat — but it must be declared as one.
- **Rare objects mislead computation.** Perfect numbers, multiperfect numbers,
  and Zsigmondy exceptions are sparse enough that a search to `10^{12}` may
  contain two examples. A pattern over two examples is a coincidence with a
  narrative attached.

## First experiments

1. Enumerate factorizations under a smoothness bound and an `omega` bound, and
   evaluate the claim exactly on each — as rationals, never floating point, since
   abundancy comparisons turn on the last few digits.
2. Compute the multiplicative ratio (`sigma(n)/n`, `phi(n)/n`, `d(n)/n^eps`)
   exactly for all `n` up to a stated bound and locate the record-holders. The
   record sequence, not the typical value, is what the barrier is about.
3. Build the prime-dependency graph from the divisibility constraints: a node per
   admissible prime, an edge when one prime's presence forces another. Cycles and
   sinks in that graph are candidate obstruction lemmas.
4. Search for primitive divisor exceptions in the relevant family and check each
   found case directly against the theorem's exception list.
5. Test the bounded-exponent and squarefree-kernel restrictions separately. If
   the claim is easy in one and hard in the other, the ladder is decided.

## Product ladder

1. A local obstruction lemma: a small prime or congruence class no example can
   contain, with the exact modulus stated.
2. The bounded-exponent case, with the bound stated and the search exhaustive
   inside it.
3. The squarefree-kernel case.
4. A dependency-chain theorem: an upper or lower bound on `omega(n)` for any
   example, derived from the forced-prime structure.
5. A conditional result under a primitive-divisor or GRH-type assumption, with
   the assumption in the claim statement rather than the prose.
6. A computation certificate over a stated bounded range, hashed and
   reproducible, capped at `CHECKED_BOUNDED` regardless of the range covered.
7. A reduction from the full problem to the chain or graph lemma, with the loss
   in both directions stated.
