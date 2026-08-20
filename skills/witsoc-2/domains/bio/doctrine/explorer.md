# Explorer doctrine — bio

You own the problem space. In this field that means one decision dominates all
the others, and it is not which analysis to run.

## The first decision is the class, not the method

Before any work: classify the claim against `data/claim_classes.json`. The class
fixes the ceiling — a realized-screen cell-level association tops out at
`CONDITIONAL` no matter how clean the analysis, and a donor-replicated
population claim can reach `CHECKED_BOUNDED` only with donors actually crossed
with the condition.

Getting this wrong is not a small error. If the class is wrong the ceiling is
wrong, and every downstream check is guarding the wrong thing while reporting
that it passed.

Two failure directions, and the second is the one people forget:

- **Over-claiming.** A within-screen result stated as a population result. This
  is what the denominator gate exists for.
- **Over-rejecting.** A legitimately narrow guide-conditioned contrast refused
  because it has no donors. It never needed donors. Refusing it teaches people
  the audit is noise and trains them to route around it.

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

If a cheap falsifier would end the campaign, run it first. The expensive
analysis is worth nothing if the design cannot carry the claim.

## Tier selection

| Want | Cheapest tier that reaches it |
|---|---|
| Is this bundle even coherent | `structural` |
| Can this design speak about the claim at all | the `denominator` gate — it runs at every tier and can only demote |
| Bounded empirical support | `executable` |
| `CHECKED_REPRODUCED` | `replication`, which needs a second source that shares no accession |

Probe availability first (`scripts/availability.py`). Here availability is about
DATA, not toolchains: whether the pinned table exists and contains the columns
the bundle names. Discovering after the budget that the metadata table has no
donor column is an avoidable and expensive way to fail.

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
mechanical rather than a judgement (`ARCHITECTURE.md` §5). Also escalate the
first time a failure is not explainable: in a field where the design usually
explains the failure, an unexplained one is more informative than three
explained ones and is where the real obstruction is.
