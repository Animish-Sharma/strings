# Barriers — why a problem resists

A barrier explains *why* the attack failed. `obstructions.md` catalogues the
recurring shapes and their tests; this file is the classification step that runs
first, because an unclassified barrier licenses no mutation and the next route
walks into the same wall.

A barrier earns its record only if it yields a **test**, an **obstruction
result**, or a **bypass mutation**. One that yields none of those is a
description of the difficulty, not knowledge of it.

## Universal classes

| Class | The mechanism that blocks |
|---|---|
| **Extremal** | known or suspected examples sit arbitrarily close to violating the target, so any argument with slack fails |
| **Parity / modular** | a congruence, sign, or residue invariant separates the cases a naive argument merges |
| **Threshold** | truth changes at a critical density, size, rank, dimension, or smoothness — an argument uniform across the threshold is wrong on one side |
| **Compactness** | finite behaviour does not pass to the infinite object, or the infinitary argument loses effectivity |
| **Regularity** | the available tool requires smoothness, measurability, pseudorandomness, or bounded complexity that the object does not have |
| **Independence / randomness** | dependencies between the events break the probabilistic or averaging step |
| **Precondition** | a named theorem is one unmet hypothesis away, and establishing that hypothesis may be the whole problem |
| **Formalization** | the sketch hides definitions or side conditions that only surface under encoding |
| **Reduction** | the tempting transformation changes the problem or loses equivalence in one direction |

## Erdos-level classes

Hard combinatorial and number-theoretic targets fail in a narrower set of ways.
Naming which one applies is what turns "this is hard" into a next move.

| Class | The mechanism that blocks |
|---|---|
| **Generic bound** | the known bound is sharp over all objects but possibly not over the structured ones the target concerns |
| **Extremal construction** | the standard examples nearly violate the desired conclusion, killing every argument with room to spare |
| **Local obstruction** | a congruence, parity, prime, graph-local, or boundary condition rules the conclusion out locally |
| **Dependency chain** | satisfying the condition forces recursive dependencies that the induction cannot carry |
| **Constant loss** | existing tools prove the right shape but shed a fatal constant or logarithm |
| **Rare object** | witnesses are so sparse that computation over reachable ranges misleads about the truth |
| **Variant drift** | a neighbouring variant is solved or false while the exact problem is untouched |

Variant drift is the one that costs whole campaigns: the literature reads as
settled, and the effort goes into transferring a proof across a gap that does not
close. Treat every transferred result as unaligned until the alignment is
recorded.

## Sub-field lists

Consult the target's own area before attacking. Most areas have two or three
standard barriers that rule out whole approach classes, and rediscovering one by
exhaustion is the expensive way to learn it.

- **Graph theory and extremal combinatorics** — sharp examples (complete
  multipartite, random, projective and norm graphs, blow-ups, cages); degree
  conditions failing to force global structure; colouring barriers from critical
  graphs, list assignments, degeneracy gaps; Hall/Menger/min-cut preconditions
  failing; spectral bounds too coarse to be tight.
- **Ramsey and Erdos-style** — small witnesses that do not scale; probabilistic
  lower bounds beating constructive intuition; container and regularity methods
  losing constants; inductive recurrences too weak; diagonal and off-diagonal
  variants behaving differently.
- **Additive combinatorics** — density increment losing too much density; missing
  Bohr-set or Fourier-uniformity hypotheses; sumset estimates non-sharp at the
  target scale; structured/random decomposition leaving uncontrolled error; local
  field and torsion variants diverging from the integer case.
- **Number theory** — local obstructions at primes or valuations; ineffective
  constants in analytic tools; equidistribution unavailable at the required
  scale; Diophantine finiteness giving no construction; the sieve parity barrier.
- **Geometry and topology** — compactness or boundary-regularity gaps; incidence
  bounds degrading at degeneracies; homological obstructions absent in low
  dimension; metric embedding distortion; transversality or smoothness
  preconditions failing.
- **Algebra and logic** — classification theorems too heavy or formally
  unavailable; representations not faithful to the original object;
  undecidability or independence risk; model-theoretic compactness changing the
  finite content; rank and dimension invariants too weak.

## Barrier record

Every barrier records: an id and name · the sub-field · what it threatens · the
evidence · known extremal examples · **the barrier lemma or obstruction
certificate that would settle it** · direct attacks already made on that lemma ·
the justification for any weaker product chosen instead · the test · the bypass
mutation · what it becomes as a product if real · status.

Status is one of `suspected | tested | bypassed | converted_to_obstruction |
rejected`. The middle three are the payload: an untested `suspected` barrier is a
guess being used to justify abandoning a route, and a route abandoned on a guess
comes back.

Bypassed and rejected barriers go to memory. Their value is entirely in stopping
the next run from paying for them again.

## From barrier to mutation

A diagnosed barrier licenses specific mutation axes and no others. The mapping
from gap class to permitted axes is implemented in `scripts/select.py`
(`AXES_BY_GAP`); `select.py mutation --gap-class C --used ...` ranks them and
`select.py axes` prints the table. Read it there rather than from memory — it is
the executable version and it moves.

The rule the table encodes: change **exactly one axis**, and record what was held
constant. A repair that changes several axes at once cannot attribute the
outcome, so a success teaches nothing reusable and a failure eliminates nothing.
