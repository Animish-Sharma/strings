# Claim freeze

## The rule

Freeze every dimension, even when the value is unknown. Write `unknown`,
`not_reported`, or `not_applicable` explicitly. Never omit a dimension that
could change interpretation.

An omitted dose and a dose that did not matter look identical in a report. The
first is a hole; the second is a finding. Only the explicit form survives review.

## What gets frozen

Claim, identity, and hash:

- stable claim id and the exact statement, in the form *perturbing X with
  modality P changes response Y in context Z*. If it cannot be written that way
  it is more than one claim, and it should be frozen as more than one.
- the claim class from `data/claim_classes.json` — this sets the ceiling
- `target_sha256` over the canonical form with the hash field removed

Context:

- organism and genome build where relevant
- cell type, tissue, disease state, donor or model system

Perturbation:

- entity, modality, dose, duration, delivery, and whether it is a combination

Measurement:

- assay type, readout, experimental unit, controls, batches, replicates

Data:

- dataset id, version, source, license, preprocessing state

For a predictive claim, additionally:

- model and version, training data, baseline, split policy, evaluation unit

Claim content and limits:

- direction, magnitude, endpoint
- falsification conditions
- allowed scope

## Falsification conditions are not optional

A claim with no stated way to be wrong cannot be audited. Every check passes
because none of them can fail, and the report says the audit passed. Write at
least one condition that could actually occur, and prefer ones the frozen data
could exhibit.

## Preprocessing state is part of the identity

"The same dataset" at raw counts and at integrated-and-batch-corrected is two
datasets. Most disagreements about whether an effect replicates are disagreements
about this line, discovered late.

## A changed context is a new claim

Narrowing, widening, specializing, or repairing an ambiguity starts a **new
claim id with a new hash**, recording `derived_from` and the kind of change. It
does not mutate the old one, and a result for the new claim is never reported as
a result for the old one.

The most common violation is invisible: restricting the analysis to the donors
where the effect appeared. The context-protection gate catches it by diffing
`analysed_context` against the frozen claim, which is why the bundle must state
what it analysed rather than leaving it implied.

## Before collecting any evidence

```bash
python3 scripts/check.py --artifact bundle.json --claim claim.json --tier structural
```

A freeze that fails here has failed cheaply. A freeze that fails after the
analysis has cost the analysis.
