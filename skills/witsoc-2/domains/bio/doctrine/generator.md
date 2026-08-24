# Generator doctrine — bio

You produce the audit bundle and drive it through the adapter. The bundle is not
a report. It is the evidence, the pinned inputs, and the ledgers, in a form
something else can recompute.

## Start from the counts, not from a score column

The pack computes its own endpoint. If you have a count matrix, the audit covers
the measurement and not only the inference:

```bash
python3 scripts/counts.py --dense <genes_by_cells.csv> --signature <genes.txt> --design <design.csv> --out metadata.csv
python3 scripts/counts.py --self-test
```

QC, normalization, and an **expression-matched** signature background, each
recorded in `metadata.csv.provenance.json` and frozen with the claim. The
background is the load-bearing part: without it a signature score is largely a
measure of how deeply each cell was sequenced. On a matrix whose only difference
between arms is a threefold depth confound, the matched background returns
-0.02 against a real signal of 0.97.

Two things are errors here rather than empty results, and the distinction
matters because an empty result reads like a null: QC that removes every cell,
and a signature no gene of which is in the matrix. A score over zero genes is
not a small score, it is no score.

If the endpoint arrives as a column someone else computed, say so — the
structural tier records the absence of provenance. That is not a failure, and it
is a stated ceiling on what the audit covers.

Then build the bundle rather than copying one:

```bash
python3 scripts/bundle.py --claim <claim.json> --metadata metadata.csv --out bundle.json
```

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

## Confounders: compute the ones that can be computed

Twelve alternative explanations sit in `data/confounders.json`, and eight carry
a `computable_by` tool. Run those; do not write a sentence about them:

```bash
python3 scripts/diagnostics.py --metadata metadata.csv --label condition --unit donor --emit-confounders --json
python3 scripts/expression_diagnostics.py --dense <matrix.csv> --signature <genes.txt> --design <design.csv> --cluster cell_type --context timepoint --emit-confounders --out diag_expression.json
```

Then pin them in the bundle under `data.diagnostics`, so the reference is
covered by the bundle hash:

```json
"data": { "diagnostics": ["diag_design.json", "diag_expression.json"] }
```

The sweep gate takes the computed verdict over yours, and **a bundle asserting
something its own pinned diagnostics contradict fails outright**. That is not a
trap. It is the same rule as "the adapter ignores your numbers", applied to the
alternative explanations instead of to the effect: a confounder you graded
yourself is the producer marking their own work, which is the one thing this
pack allows nowhere else.

A tool returning `not_computable` has abstained. It does not overrule you and it
does not clear the confounder either. The remaining four genuinely need
information outside the matrix — the guide library, an off-target prediction,
how the gene set was defined — so an asserted result is the best available
there, and the receipt records which is which.

## What is still missing, in one answer

```bash
python3 scripts/missing.py <bundle.json> --claim <claim.json> --tier executable
```

Every gate reports its own failure, one at a time. Building a bundle for a real
claim that way took eight rounds — a field named `claim_element` and not
`element`, a resolution spelled with underscores, a metadata column the negative
control needs that nothing had asked for — each round costing a full adapter run
to learn one field name. That is teaching a format by rejection, and it makes
the pack usable by whoever wrote it and nobody else.

`missing` runs every gate in report-only mode and returns one list: what is
missing, where it goes, and the exact shape. It also pre-flights the metadata
table against the columns the bundle names, which is the one class of problem
that otherwise costs a whole tier run to discover.

**Passing it does not mean the bundle is good.** It means the gates have nothing
left to ask for, and what they ask for is the floor: they check the evidence is
PRESENT, and the tiers check what it says.

## Submitting

```bash
python3 scripts/availability.py --tier executable --bundle bundle.json
python3 scripts/check.py --artifact bundle.json --claim claim.json --tier executable
python3 scripts/check.py --self-test
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

Generate it FROM the receipt rather than writing it beside the receipt:

```bash
python3 scripts/report.py --receipt <receipt.json> --claim <claim.json>
```

A report written alongside a receipt drifts from it — not by dishonesty, but
because prose is written once and the receipt changes when the analysis is
re-run. The wording is in `doctrine/report_language.md` and it is boring on
purpose.
Supported under this dataset, this context, this perturbation, this analysis,
this metric set. Not established outside them. The scope-language gate checks
the vocabulary against the evidence tiers you declared, so escalating past the
readout fails rather than persuades.
