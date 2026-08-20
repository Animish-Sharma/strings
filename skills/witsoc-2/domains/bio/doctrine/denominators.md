# Denominators

The dominant failure in perturbation biology is not a wrong number. It is a
correct number attached to the wrong denominator.

## The arithmetic

Observations inside one donor, animal, or screen are not independent draws from
the population the claim is about. With intra-cluster correlation `p`, a cluster
of `n` observations carries the information of

    n / (1 + (n - 1) * p)

independent observations. At `p = 0.01` — implausibly low for single-cell data —
a cluster of a thousand cells is worth about ninety-one. At `p = 0.05` it is
worth about twenty. Across a handful of clusters, the effective sample size
approaches the number of **clusters**, not cells, and it does so quickly.

So a population claim resting on cell count is not weakly supported. It is
unsupported, and collecting more cells makes the interval narrower around an
estimand nobody asked about.

The `denominator` gate reports this grid for the actual design. The point of
showing several correlations is that none has to be argued for: every value in
the grid tells the same story.

## Hard rejections

From `data/claim_classes.json`, applied mechanically:

| Rule | Why |
|---|---|
| Cells as the only replicate evidence for a population claim | more cells, wrong estimand |
| Lanes, captures, libraries, or batches promoted to biological replicates | a process split shares the biology it was split from |
| FDR offered as the answer to clustered cell-level uncertainty | corrects across features; the denominator is what is wrong |
| Multiple guides replacing donor or screen replication | several guides test the perturbation, not the population |

The third one deserves its own note because it is offered sincerely and often.
Multiple-testing correction is a real and necessary thing that solves a
different problem. Presenting it as a response to pseudoreplication is itself a
demotion trigger, and the statistical-audit gate treats it as one.

## Crossing, not just counting

Six donors is not six replicates if each donor saw only one condition. Then the
contrast is entirely between donors, and donor difference and treatment
difference are the same number. The gate reports `fully_crossed` and
`completely_confounded` separately from the unit count, because the count is the
number people quote and the crossing is the thing that matters.

## Few clusters

Between the class floor and five upstream units, cluster-robust uncertainty is
unreliable. That range is legal and carries an explicit few-cluster caveat in
the report — it is not silently fine and not automatically rejected.

## What each class can reach

`data/claim_classes.json` is the table, and it protects in both directions.

Over-claiming is the famous failure. Over-rejecting is the quieter one: a
guide-conditioned within-screen contrast with guide assignment, matched
controls, capture, efficacy, and batch-aware uncertainty can reach
`CHECKED_BOUNDED` and never needed a donor. Refusing it because it has no donors
is wrong, and it teaches people that the audit does not track anything real.

## Upgrading a population claim

All of:

- frozen estimand and target population;
- independent upstream units crossed with perturbation and context;
- replicate-aware analysis at the estimand-matching denominator;
- guide, control, and QC evidence for assignment and efficacy;
- confounder sensitivity for batch, depth, capture, MOI, doublets, ambient RNA,
  cell state composition, selection, viability, and proliferation where relevant.

Missing any of these is a ceiling, not a caveat.
