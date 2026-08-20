# Leakage

The held-out axis is the claim. If it leaks, the number measures memorization on
exactly the thing being claimed.

## Why this gate runs first

The leakage audit runs before the baseline and metric gates. Order matters: a
leaked split makes every downstream number a measurement of something else, so
computing them first invites arguing about a metric that was never meaningful.

## Severity follows the claim, not the overlap

| Finding | Fatal when | Otherwise |
|---|---|---|
| test perturbations seen in training | the claim is about held-out perturbations | warning |
| cell lines shared across the split | the claim is cross-context | warning |
| donors shared across the split | the claim is about new donors | warning |
| control units in both splits | always | — |
| split falls exactly on batch lines | — | warning, must be acknowledged |

This asymmetry is deliberate. Overlap irrelevant to what is claimed is not a
defect. Treating every overlap as fatal produces a check people learn to route
around, and a check that is routed around is worse than none because it still
reports passing.

Control contamination is unconditionally fatal because every control-referenced
metric — which is most of the good ones — is then computed against data the
model trained on.

## Reconstruct the split, do not read it

A split policy and a split are different objects. When it matters, rebuild the
split from the metadata and compare it against what the bundle declares. The
gap between the two is where leakage lives, and it is almost never deliberate.

## Warnings must be acknowledged

A warning that nobody is required to read is not a warning. The gate requires
each one to appear in `acknowledged_leakage_warnings`, so carrying it forward is
a decision someone made rather than a line that scrolled past.

## Batch-confounded splits

If the training set is batch A and the test set is batch B, then generalization
performance and batch effect are the same measurement, and no amount of
modelling separates them afterwards. This is a warning rather than a fatality
because sometimes it is the only split available — but it bounds every
conclusion, and the bound belongs in the report.
