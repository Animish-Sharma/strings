# Bio domain pack

Perturbation biology: deciding whether a claim about what a perturbation does to
a biological system deserves belief, and under exactly which context.

Researcher is called **Durbin** here. Explorer and Generator keep the frame
names.

## The one thing to know first

**This pack never reaches `VERIFIED`.** Not at any tier, not under any design,
not with any amount of data. Its ceiling is `CHECKED_BOUNDED`, and the strongest
thing it can say is the `CHECKED_REPRODUCED` refinement.

That is not caution. `VERIFIED` in this frame means an adapter that cannot be
argued with covered every obligation of the general statement. Empirical support
is always support *for a frozen dataset, context, and analysis*. Using the same
word for both would put a perturbation screen and a machine-checked identity in
the same box, and keeping them apart is what the status vocabulary is for.

The pack is therefore also the frame's most useful stress test: it is a domain
whose honest maximum is below the top of the lattice, which is a case the maths
pack cannot exercise.

## The six items

| Item | Here |
|---|---|
| **1. Verification adapter** | `scripts/check.py`, three tiers: `structural` (bundle shape and freeze, ceiling `SKETCH`), `executable` (recomputes the effect from pinned data and tests it by permutation, ceiling `CHECKED_BOUNDED`, adversarial), `replication` (a second source sharing no accession, grants `CHECKED_REPRODUCED`). Corpus in `scripts/corpus.py`. |
| **2. Claim schema** | `claim.schema.json`. Every dimension that changes what a result means, frozen — with `unknown` as a legal value and silence as an illegal one. |
| **3. Receipt format** | `receipt.schema.json`. Separates `max_status` (what a pass here could support) from `supports_status` (what this receipt establishes — null unless the verdict is a pass). |
| **4. Doctrine** | `doctrine/` — three role files plus ten rules. Escalation at 2 same-signature failures, because each attempt re-runs a pinned analysis over fixed data. |
| **5. Gates** | `permutation-null` (the refute-attempt, discharged by the executable tier) plus ten blocking gates, led by `denominator`. |
| **6. Selection** | `domain.json` → `selection`. Six examples and four counter-examples, replayed by `scripts/resolve_domain.py --self-test`. |

## The central idea: denominators

The dominant failure in this field is not a wrong number. It is a correct number
attached to the wrong denominator.

Observations inside one donor are not independent draws from the population a
claim is about. At an intra-cluster correlation of 0.01 — implausibly low for
single-cell data — three thousand cells from one donor carry the information of
about ninety-seven observations. At 0.05, about twenty. The effective sample size
approaches the number of *clusters*, and it does so fast.

The `denominator` gate reports that grid for the real design, so no correlation
value has to be argued for: every value in the grid tells the same story.

It is a **gate rather than a tier** because it can only demote. A clean design
with no results is not evidence of anything.

## The refute-attempt gate

`permutation-null`, and it has two halves:

1. Labels shuffled **within stratum** on unit-level means. Shuffling across
   batches would destroy the confounding along with the effect and make a
   confounded result look clean.
2. The control condition **split against itself**, which must come back silent.

The second is the most valuable check in the pack. A pipeline that finds a
difference between two halves of its own control is measuring its own structure,
and every number it has ever produced is uninformative until that is fixed. It
is also the check most likely to fire on a sincere, careful, subtly broken
analysis — which is the kind that gets published.

## It computes the endpoint

For most of this pack's life its endpoint was one pre-computed score column per
observation, accepted on faith — so everything it checked sat downstream of a
number it could not recompute. Its own doctrine says the adapter ignores reported
numbers; it ignored reported *statistics* and trusted the reported *endpoint*.

`scripts/counts.py` closes that. It reads a count matrix (MatrixMarket triples or
a dense genes-by-cells CSV), computes per-cell QC, normalizes to counts per ten
thousand and log1p, and scores a named gene signature against an
**expression-matched background** chosen deterministically by rank.

The background is the part that matters. Without it the score is largely a
measure of how deeply each cell was sequenced — the pack's own self-test builds a
matrix whose only difference between arms is a threefold depth confound, and the
score gap comes out **−0.02 against a real signal of 0.97**.

Every choice it makes is written to a provenance record and belongs in the
claim's `frozen_conditions`: a result under different QC thresholds or a
different normalization is a result about different data. The structural tier
says so when an endpoint arrives without one — not as a failure, because plenty
of real analyses arrive as a table, but as a stated ceiling on what the audit
covers.

Standard library only: 500,000 nonzeros stream in under a second.

## The adapter ignores reported numbers

The executable tier does not read the bundle's effect size or p-value. It
recomputes both from the pinned metadata table, at the unit the claim names,
with a fixed seed and iteration count. A bundle that reports a beautiful result
and pins a table that does not support it fails with the recomputed number in
the receipt.

## Protecting against over-rejection

A pack that refuses everything carries no information. `data/claim_classes.json`
protects in both directions: a guide-conditioned within-screen contrast can reach
`CHECKED_BOUNDED` with no donors at all, because it never needed donors.

The eval suite makes this concrete. `within_screen_is_legitimate` and
`same_data_as_population_claim_is_rejected` run against **the same metadata table
with the same numbers**. One passes and one is rejected, and the only difference
is the claim class. If both ever pass or both ever fail, the class table has
stopped doing any work.

The crossing check follows the same principle: a donor that saw one condition is
confounded with it, but a guide is targeting or non-targeting by construction and
cannot be crossed. Demanding that guides be crossed would reject every screen
ever run.

## Running it

Commands below are relative to this pack directory.

```bash
python3 scripts/availability.py --all --bundle <bundle.json>   # data, not toolchains
python3 scripts/check.py --artifact <bundle.json> --claim <claim.json> --tier executable
python3 scripts/check.py --self-test        # 9 known-bad bundles rejected, 1 good accepted
python3 evals/run_evals.py --verbose        # 6 outcome cases
python3 scripts/corpus.py --ledger <bundle.json>
```

Standard library only. Nothing here needs a scientific-Python stack, because a
tier that cannot run without one is a tier that is unavailable exactly when a run
needs it.

## Where the statistics live

Estimand, identifiability, uncertainty, multiplicity, power, and prespecification
are held by the `statistical-audit` gate **inside this pack, for now**, and it
says so on every run. The frame's answer to two competences on one claim is two
packs (`ARCHITECTURE.md` §2.2), not a fourth role. Register a statistics pack and
that gate becomes a delegation — the same obligations, audited by something that
did not also design the experiment. `doctrine/two_pack.md` has the boundary.
