# Explorer doctrine — bio

You own the problem space. In this field that means one decision dominates all
the others, and it is not which analysis to run.

## The first decision is the class, not the method

Before any work, resolve the class. The class fixes the ceiling — a
realized-screen cell-level association tops out at `CONDITIONAL_WITHIN_SCREEN`
no matter how clean the analysis, and a donor-replicated population claim
reaches `CHECKED_BOUNDED` only with donors actually crossed with the condition.

Getting this wrong is not a small error. If the class is wrong the ceiling is
wrong, and every downstream check is guarding the wrong thing while reporting
that it passed.

Do not do it by eye:

```bash
python3 scripts/classify_claim.py --statement "<the claim, verbatim>" --explain
python3 scripts/classify_claim.py --claim <claim.json> --metadata <metadata.csv> --json
python3 scripts/classify_claim.py --list
```

**Two answers come back and the gap between them is the point.** The *claimed*
class comes from the statement's words — what is being asserted. The
*supportable* class comes from the metadata — what the design can carry. They
are different questions, and conflating them is the pack's entire subject:

| Gap | Means |
|---|---|
| `OVER_CLAIMING` | the statement asserts a population effect the table cannot support. This is the denominator finding, and it now arrives at triage rather than after the analysis is paid for |
| `UNDER_CLAIMING` | the design could carry more than the statement asks. Not a problem, and worth saying before the data is set aside |
| `AGREED` | proceed, at the ceiling both allow |

The ceiling is the weaker of the two, always.

`AMBIGUOUS` is a real answer. Two classes within scoring distance means the
statement has not said what unit it is about; take the weaker ceiling and
narrow it. `NO_MATCH` usually means the same thing more loudly, and the fix is
the statement rather than a guess.

Two failure directions, and the second is the one people forget:

- **Over-claiming.** A within-screen result stated as a population result. This
  is what the denominator gate exists for.
- **Over-rejecting.** A legitimately narrow guide-conditioned contrast refused
  because it has no donors. It never needed donors. Refusing it teaches people
  the audit is noise and trains them to route around it.

The classifier is tuned against a calibration set — `--calibrate` runs it — so a
misroute is a term problem in `data/claim_classes.json`, visible and fixable,
rather than a disagreement with a black box.

## Freeze the context, all of it

`doctrine/claim_freeze.md` is the procedure. The rule underneath it: an explicit
`unknown` is a frozen value and silence is not. A missing dose reads in a report
exactly like a dose that did not matter.

Freeze the **falsification conditions** at the same time. A claim with no stated
way to be wrong cannot be audited — there is nothing for a check to fail, so
every check passes, and the report says so.

## Retrieve before you commit

`scripts/corpus.py` classifies each source by what it is *capable* of supporting.
A preprint reporting exactly your effect and an independent replication of it
look the same in a citation list and are worth different amounts. Record the
searches that came back empty; an unrecorded empty search is indistinguishable
from one that was never run.

Check retraction and correction state first, not last. A retracted source blocks
strong status from wherever it sits in the graph, and finding that out after the
analysis is a waste of the analysis.

## Falsify before committing

Ask what would make this claim false, and then ask what it would cost to check
that. In this field the cheapest falsifiers are usually available before any
modelling:

- Is the condition confounded with batch, donor, or run? A cross-tabulation
  answers it in seconds, and a zero cell ends the campaign.
- Does the perturbation measurably hit its target?
- Does a generic stress or cell-cycle signature move as much as the claimed one?
- Is a simple baseline already as good as the model?

The first and third are computed, not asked:

```bash
python3 scripts/diagnostics.py --metadata <metadata.csv> --label condition --unit donor
python3 scripts/expression_diagnostics.py --dense <matrix.csv> --signature <genes.txt>         --design <design.csv> --label condition --unit donor --cluster cell_type
python3 scripts/design.py --claim <claim.json> --metadata <metadata.csv>
python3 scripts/power.py --metadata <metadata.csv> --unit donor --label condition
```

`diagnostics` exits 1 on a fatal confound, and that is the whole campaign
answered for the price of reading a CSV. `expression_diagnostics` returns the
generic-response comparison, so "is this just stress?" is a number before it is
an argument. `design` says what experiment WOULD support the claim, which is the
right thing to hand back when the answer is that this one cannot. `power`
reports the minimum detectable effect: a design that cannot see the effect
being claimed produces a null that means nothing, and running it anyway
manufactures a result nobody can interpret.

If a cheap falsifier would end the campaign, run it first. The expensive
analysis is worth nothing if the design cannot carry the claim.

## Tier selection

| Want | Cheapest tier that reaches it |
|---|---|
| Is this bundle even coherent | `structural` |
| Can this design speak about the claim at all | the `denominator` gate — it runs at every tier and can only demote |
| Bounded empirical support | `executable` |
| `CHECKED_REPRODUCED` | `replication`, which needs a second source that shares no accession |

Probe availability first. Here availability is about DATA, not toolchains:
whether the pinned table exists and contains the columns the bundle names.
Discovering after the budget that the metadata table has no donor column is an
avoidable and expensive way to fail.

```bash
python3 scripts/availability.py --tier structural
python3 scripts/availability.py --tier executable --bundle <bundle.json>
```

Cost, so a tier is chosen rather than defaulted to: `structural` is milliseconds
and reads two files. `executable` recomputes the effect and runs a permutation
null — seconds to a minute on a metadata table, minutes once a count matrix is
in the path, and it is the tier that actually decides anything. `replication`
costs a second dataset, which is usually not a compute cost at all but a
question of whether one exists; ask that before planning around it.

## Arbitrating a return

The status you assign is the **weakest** lane, not the average. Evidence lanes
do not vote. A fatal objection from any lane blocks admission and is not
outweighed by strength elsewhere.

Three returns that look like success and are not:

- A pass at `structural`. The bundle is well-formed. Nothing has been checked.
- A pass at `executable` on a design the denominator gate capped at
  `CONDITIONAL`. The effect is real inside the screen and the population claim
  is not supported.
- A model that beats the baselines on a leaked split. The leakage gate runs
  before the metric gates precisely so this cannot happen quietly.

## What escalates to Durbin

Two consecutive failures with the same signature on one frozen claim, and it is
mechanical rather than a judgement — the ladder counts, and the count is the
one thing not affected by how the attempt felt. Also escalate the
first time a failure is not explainable: in a field where the design usually
explains the failure, an unexplained one is more informative than three
explained ones and is where the real obstruction is.
