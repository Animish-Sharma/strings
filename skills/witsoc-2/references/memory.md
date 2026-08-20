# Memory

A frame-owned shared service, and the only thing in the system that compounds.
Every other mechanism makes one run honest. This is what makes run N+1 cheaper
than run N.

It is also the single most dangerous store in the frame, because a memory that
can absorb the answer will eventually hand it back as a prior, and no gate
downstream can tell that apart from insight.

## Two tiers, kept apart

**Attention tier.** Failures, do-not-repeat entries, method priors, technique
suggestions, obstruction families, prior-run notes. This tier *ranks* future
work. It never constitutes evidence, appears in a receipt, or moves a status.

**Reuse tier.** Admitted results from earlier runs, reusable in a later one —
but only on exact context match (below). A reuse-tier hit still produces a
candidate, not an admission: the new claim is reached faster, not granted.

Collapsing the two is how a remembered guess becomes a cited fact. Store them
separately and label every entry with its tier.

## The contamination rule

**Held-out material never enters memory.** Evaluation keys, answers, benchmark
targets, and any content the run is meant to be tested against stay out —
permanently, not until the run ends.

This is not a hypothetical. A store that learns from outcomes will preferentially
retain the ones that scored well, and if the scoring saw the answer, the store
has now laundered it into a prior that looks like accumulated skill.

Anything whose provenance cannot be established does not enter the reuse tier.
Unknown provenance fails closed.

## Reuse preconditions

A remembered result may be reused only when the context matches on **every**
declared axis — assumptions, definitions, inputs, environment, and the shape of
the target. A domain pack declares which axes it has.

A near-match is not a match. The value of a memory hit is that it skips work; a
near-match skips the work *and* the correctness, which is strictly worse than
starting cold.

> A cache hit is evidence about **checkability**, never about truth. It says
> this shape of thing has been established before, not that this instance is
> established now.

## What memory may and may not do

**May**: block a known repeat · supply do-not-repeat entries · recall
obstructions, reductions, and counterexample families · reset progress counters ·
offer prior successes as candidate approaches · order retrieval.

**Must not**: upgrade any status · substitute for verification · import a
neighbouring variant's result without an explicit alignment argument · enter a
receipt · silently widen its own scope.

## Failures are written immediately

A failure record written at synthesis time is a failure half-remembered — the
diagnostic is gone, the exact statement has drifted, and what remains is a
feeling that the approach did not work.

Write on failure, with: the statement hash, the method family, why it failed, the
blocking obstruction or counterexample, and the **revival condition**.

## Blocks expire

Every do-not-repeat entry records what would make it worth retrying. A route
ruled out by current knowledge is not ruled out permanently, and a block with no
revival condition throws away the reason it was blocked — leaving a campaign
progressively more constrained by decisions nobody can reconstruct.

When a revival condition fires — a new admitted sub-claim, a refuted obstruction,
a new counterexample family, a rival branch collapsing — rescan the ledger before
ranking anything. That event re-prices every branch, not only the one it landed
on.

Three recorded failures sharing one blocker promote that blocker to a named
obstruction. That promotion is the signal the run found something real rather
than being unlucky.

## Contradiction

A contradiction between memory and the current state is resolved *before*
proceeding, not averaged. Memory is the older observation and the current run is
the better-instrumented one, but neither wins automatically — the resolution is
recorded either way, because an unexplained contradiction usually means one of
the two has an unstated assumption.
