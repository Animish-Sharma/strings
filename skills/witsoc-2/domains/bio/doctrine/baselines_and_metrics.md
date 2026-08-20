# Baselines and metrics

For any claim that a model predicts perturbation responses better than something.

## The burden of proof is on the model

Simple baselines are not a formality in this field. Predicting the control
profile, the mean of training perturbations, control-plus-average-delta, and —
for combinations — the additive prediction are repeatedly competitive with and
often better than elaborate models. So "the model performs well" is not yet a
claim about the model.

The baselines are in `data/metrics.json` and the gate builds the comparison
whatever the bundle reports. Baselines stay in the results table regardless of
outcome; a table with the baselines removed is the artifact the gate exists to
prevent.

## Beating means beating everything

The model must beat the strongest baseline on **every** gate metric, by a stated
margin. Not on average. Not on the headline. A model that wins one gate metric
and loses another has demonstrated a trade-off, and a trade-off is not
superiority.

## Report the whole panel

Every metric here is gameable by something specific:

- a discrimination score, by embedding structure with no accurate magnitudes;
- a differential-expression score, by predicting the globally most frequently
  differential genes;
- an absolute error, by predicting that nothing changed.

Reporting one metric is therefore not a summary of performance. It is a choice
of which failure mode to hide. A missing metric counts as a failed one, because
"we did not compute it" and "we computed it and set it aside" are
indistinguishable from outside.

Metrics flagged `report_only` exist to expose an artifact, not to rank on. A
claim that leans on one is refused rather than discounted.

## Rank instability is a finding

If the model's rank against the baselines moves by two or more places across the
gate metrics, the panel disagrees with itself. The choice of metric is doing
more work than the model. That must appear in the report — not be resolved by
presenting the ordering that flatters.

## The two diagnostics

- **control bias**: the model's score is identical to the control-mean
  baseline's. That is what predicting "no perturbation" looks like from the
  outside.
- **signal dilution**: a better absolute error alongside a near-zero
  DEG-weighted correlation. That is what shrinking every prediction toward the
  mean looks like.

Both are cheap, both are common, and both survive a review that only reads the
headline number.

## Distance metrics

A distance metric is admissible only if it has been shown to behave at the
dimensionality it is being used at. Several standard ones do not in
high-dimensional single-cell space — lower distance stops meaning more similar,
and a trivial baseline can beat a perfect reference. Prefer a metric with a
permutation test attached, and report the panel rather than a composite.

## What a clean pass means

Beating the baselines with a clean split and a full panel is **necessary, not
sufficient**. It says the model is ahead of the trivial predictors. It says
nothing about whether the estimand is the right quantity, whether the biology is
real, or whether the result holds anywhere else.
