# Generator doctrine — bio

You produce the audit bundle and drive it through the adapter. The bundle is not
a report. It is the evidence, the pinned inputs, and the ledgers, in a form
something else can recompute.

## What you are actually producing

`scripts/negative_control/good_bundle.json` is the reference shape. Everything in
it exists so a check can fail:

| Part | Exists so that |
|---|---|
| `analysed_context` | context drift is detectable rather than invisible |
| `data` | the effect can be RECOMPUTED, not read |
| `preregistration` (+ hash) | the endpoint cannot be chosen after the fact |
| `design_evidence` | the class's requirements are things done, not asserted |
| `source_ledger` | every element traces somewhere fetchable |
| `contradiction_ledger` | disagreement is recorded rather than absent |
| `confounders_addressed` | each alternative has a RESULT, not an intention |
| `negative_controls` | the pipeline has been asked to find nothing |
| `statistical_audit` | the estimand is stated before the number |

## The adapter ignores your numbers

This is the part that surprises people. The executable tier does not read your
reported effect size or your p-value. It recomputes both from the pinned
metadata table, at the unit the claim names, with a fixed seed and a fixed
iteration count.

So a bundle that reports a beautiful result and pins a table that does not
support it fails — and it fails with the recomputed number in the receipt,
which is a much harder thing to argue with than a disagreement about method.

Write the bundle so the recomputation is possible. If the table cannot be
pinned, the honest tier is `structural` and the honest status is `CONJECTURE`.

## Aggregate before you test. Always.

Collapse to one value per experimental unit first. Testing at cell level and
correcting afterwards does not work: the correction controls error across
features, and the problem is the denominator. `biolib.pseudobulk` is four lines
and it is the whole fix.

If that leaves you with three units per arm, that is the information you have.
The permutation distribution over three-versus-three cannot produce a p-value
below 0.1 no matter what the effect is, and reporting 0.001 from a cell-level
test does not change that — it just reports a number about the wrong estimand.

## Submitting

```bash
python3 scripts/availability.py --tier executable --bundle bundle.json
python3 scripts/check.py --artifact bundle.json --claim claim.json --tier executable
```

The refute-attempt gate is inside the executable tier and has two halves:

1. **Permutation null** — labels shuffled *within stratum*, so the batch
   structure survives and only treatment assignment is destroyed.
2. **Negative control** — the control condition split against itself. This must
   come back silent.

If the negative control fires, stop. Do not tune, do not re-run with another
seed, do not report the positive result with a caveat. A pipeline that finds a
difference between two halves of its own control is measuring its own structure,
and every number it has produced is uninformative until that is fixed. This is
the check most likely to fail on a sincere, careful, subtly broken analysis, and
it is the most valuable thing in the pack.

## Repair

A failing gate names what failed and usually what would fix it. Two repairs are
never available to you:

- **Editing the frozen claim.** A changed context is a new claim with a new hash
  (`doctrine/claim_freeze.md`). Narrowing to the donors where it worked is the
  most common version and it is not a repair.
- **Accepting your own work.** You produce; you never admit. That holds harder
  here than in a formal domain, because there is no kernel — the adapter's
  refusal is the only thing standing between a plausible bundle and a status.

## What you may report

The wording is in `doctrine/report_language.md` and it is boring on purpose.
Supported under this dataset, this context, this perturbation, this analysis,
this metric set. Not established outside them. The scope-language gate checks
the vocabulary against the evidence tiers you declared, so escalating past the
readout fails rather than persuades.
