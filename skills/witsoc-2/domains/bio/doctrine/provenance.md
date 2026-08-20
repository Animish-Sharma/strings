# Provenance

## Two failures, in opposite directions

**An untraced element.** The claim asserts a cell type, a dataset version, a
prior effect size, and nothing records where it came from. In a report this looks
exactly like a traced element. That is why it needs a mechanical check rather
than a careful reader — careful readers cannot see absence.

**A poisoned source.** A retracted paper does not stop being cited. It stops
being *checked*. So a retraction anywhere in the ledger blocks strong status
regardless of how peripheral the source looks, and a correction or expression of
concern blocks until someone records which direction the change cuts.
"Corrected" is an open question, not a severity.

## What a source can support

`scripts/corpus.py` classifies by kind, because the question that matters is not
whether a source agrees but what class of claim it is capable of supporting.

| Kind | Can support | Cannot |
|---|---|---|
| dataset / accession | bounded empirical support | replication on its own |
| journal article | context, method, prior effect | replication of *your* result |
| independent replication | all of the above, plus replication | — |
| preprint | context, method | independent replication |
| method paper | method | biology |
| challenge or benchmark page | method, leaderboard context | biology |
| review | orientation | anything directly — its citations are the evidence |
| company blog, press release | orientation | validation |

A preprint reporting exactly your effect and an independent replication of it
look identical in a citation list. They are worth different amounts, and the
ledger is where that difference gets written down.

## The source-capability gate

`source-capability` asks the corpus a different question from the provenance
gate. Provenance asks whether every element traces to something fetchable and
unretracted. Capability asks whether a source of that KIND could establish the
thing it is being used for — and catches two failures that run in opposite
directions.

**Over-reach.** A bundle reaching for independent replication whose ledger holds
only preprints, method papers, and benchmark pages. None of those can be the
replication, whatever they report.

**Under-use.** A dataset accession sitting unused in the ledger while the claim
rests on a review of it. The primary evidence was there and the report cited the
summary.

## Record the empty searches

A search that came back empty is information. A search nobody recorded is
indistinguishable from a search nobody ran. The contradiction ledger accepts
`searched_and_found_none` — with the queries — precisely so the honest version of
"nothing found" is available and checkable.

## Every source must be fetchable

Accession, DOI, or URL. A source that cannot be fetched cannot be checked, and
an unfetchable citation is a claim about the literature rather than a use of it.
