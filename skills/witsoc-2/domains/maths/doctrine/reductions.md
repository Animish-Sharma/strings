# Reductions — obligations, the open core, honest progress

A reduction is the claim that a hard target follows from a list of easier ones.
The ledger makes that claim explicit and auditable:

    target  <==  (every obligation discharged)  AND  (open_core empty)

An **obligation** is a sub-claim that, together with the others, would imply the
target. Obligations enter `OPEN` or `FORMALIZED` and are moved only by a kernel
or checker gate — the ledger records statuses, it never awards one.

## The open core is the point

The **open core** is the residual the obligations do **not** cover — the hard
part nobody has reduced yet, named explicitly and in the run's own words (for
Erdős–Straus: the primes `n ≡ 1 (mod 24)` that resist the elementary families).

Without a named core, a run that discharges eight of ten self-chosen obligations
reports 80% progress on a conjecture it has not touched — because the ten
obligations were themselves chosen for being tractable. Closing what you picked
is not closing the conjecture.

An empty `open_core` is therefore a strong claim, not a default: it asserts that
the obligations fully reduce the target. State it only when that is true.

## Reduction map vocabulary

Each recorded reduction from the frozen target to another statement carries:

| Field | Values | Records |
|---|---|---|
| `direction` | `implies \| implied_by \| equivalent \| obstruction` | which way the implication runs |
| `status` | `checked \| conjectural \| rejected \| open` | how much the implication itself is trusted |
| `what_it_buys` | prose | why the move is worth making |

Direction is not decoration. `implies` and `implied_by` point opposite ways, and
a route that proves the wrong one has proved a different theorem; recording the
direction is what makes that mistake visible instead of silent.

`what_it_buys` empty means the reduction was never justified as useful — a
target rewritten sideways for no gain, which costs budget and hides drift.

## The applicability gate

Every obligation carries `applies_because`: why this sub-claim bears on **this**
target. It is refused if it is a placeholder, shorter than 12 characters, or a
verbatim echo of the obligation's own statement.

The gate is deliberately permissive about content — the kernel judges the
mathematics, and relevance cannot be adjudicated by string matching — and strict
about presence: someone must have written a real reason.

The failure it prevents is a generic template injecting its own obligations into
every problem sharing a keyword. A rule that fires on `"erdos" in target` will
push Erdős–Straus arithmetic into an unrelated Erdős problem, and every one of
those obligations is then discharged for free, inflating progress on a target
none of them touch.

## The coverage audit

Once obligations exist, the decomposition is audited adversarially, once. The
auditor is given the target and the claimed cover — every obligation's `covers`
plus every `open_core` description — and asked to **exhibit a concrete instance
satisfying the target's hypotheses that neither an obligation nor an open-core
item covers**.

A hole found this way makes the decomposition **UNSOUND**, not merely
incomplete: discharging every obligation would then not establish the target,
so all subsequent work on those obligations is spent proving something weaker
than the frozen target while reporting it as progress on the target.

The auditor's default is `hole_found: false`. Inventing a hole is as damaging as
missing one — it stalls a sound reduction behind imaginary work.

## Progress bands

Progress toward the target is **capped** by the state of the reduction, never by
the count of closed obligations. `coverage` is the fraction of obligations
discharged.

| Band | Cap | Condition |
|---|---|---|
| `REFUTED_OBLIGATION` | 5 | an obligation was shown false — the reduction is broken, not partially done |
| `COVERAGE_HOLE` | 5 | the audit found an uncovered case — the decomposition is unsound |
| `OPEN_CORE_OPEN` | 8 + 12·coverage | the hard core is still open; the easy obligations are not the conjecture |
| `CORE_CLOSED_OBLIGATIONS_OPEN` | 40 + 40·coverage | core addressed, named obligations remain — genuine reduction progress |
| `UNJUSTIFIED_REDUCTION` | 45 | everything discharged, but nobody argued the obligations imply the target |
| `REDUCED_ASSERTED` | 85 | complete, reduction asserted as a claim but not kernel-checked |
| `REDUCED` | 100 | complete, `open_core` empty, no hole, `obligations ⟹ target` kernel-checked |

The two 5-caps are the load-bearing ones: a refuted obligation and a coverage
hole both mean the reduction does not establish the target at all, so any number
of discharged obligations under them buys nothing.

`UNJUSTIFIED_REDUCTION` at 45 exists because "I closed all my lemmas" and "my
lemmas imply the theorem" are different claims. The gap between 85 and 100 is
exactly the difference between asserting the implication and proving it.

`solve_ready` is true only in the `REDUCED` band. An open core, an
only-asserted reduction, or a coverage hole each returns false on their own.

## Implementation

`scripts/reduction_ledger.py` implements the ledger, the applicability gate, the
coverage audit and the band computation; run `--help` for the commands. Do not
restate its CLI here — doctrine states the contract, the script enforces it.
