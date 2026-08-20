# Archival domain pack

Documentary and historical claims: whether the sources that agree about something
are actually saying it independently.

Researcher is called **Ranke** here. Explorer and Generator keep the frame names.

## Why this pack exists

It is a real pack for a real field, and it is also the frame's third-party test.
The domain-pack contract had only ever been implemented by the person who wrote
it, against two fields chosen because they suited it. This one was chosen because
it does not: there is no kernel, no dataset to re-analyse, no numbers at all.

It was built under a strict rule — **change nothing in the frame** — and every
time that rule bit, the want was written down instead. `FRICTION.md` is that
list, and it is the most useful file here.

The rule held. No frame file was modified while building this pack.

## The one idea

When five sources agree, that is either five observations or one observation
copied four times. In a bibliography the two are written identically.

Following each chain back to its root and merging roots that share an author or
an archive is what tells them apart. It is the only operation in this field that
cannot be argued with, and it is both the verification tier and the refute-attempt
gate — the same computation, read in the two directions:

- forwards: how much independent support is there
- backwards: does the corroboration this claim asserts survive being collapsed

A claim whose corroboration collapses to one origin has been refuted **as
corroboration**, whether or not it is true. That distinction gets its own status
refinement, because a bad argument for a true thing should not get it disbelieved.

## The six items

| Item | Here |
|---|---|
| **1. Verification adapter** | `scripts/check.py`, two tiers: `structural` (dossier shape, dating, terminating chains, ceiling `SKETCH`) and `triangulation` (the collapse, ceiling `CHECKED_BOUNDED`, adversarial). |
| **2. Claim schema** | `claim.schema.json`. Who, what, where, when — plus `claimed_independent_support`, asserted *before* the chains are followed. |
| **3. Receipt format** | `receipt.schema.json`, extending `frame-receipt-v1`. The field to read is `independence`. |
| **4. Doctrine** | Three role files plus four rules. Escalation at 3, with a stated reason for differing from bio's 2. |
| **5. Gates** | `cascade-collapse` (the refute-attempt) plus dating-consistency, survivorship, transmission-chain, interest-audit, scope-language. |
| **6. Selection** | Six examples and four counter-examples, replayed by `resolve_domain.py --self-test`. |

## Ceiling

`CHECKED_BOUNDED`, never `VERIFIED`. A surviving document establishes that
something was written; that it happened is a further claim, and no quantity of
documents closes that gap. The ceiling is a property of the field, not a caution
about this implementation.

## The gates worth knowing about

**survivorship** is the one that catches the most. The archive is a
survivorship-biased sample of a survivorship-biased sample, and it requires two
things: an absence claim must say why a record would have survived, and *every*
claim must say what the record would look like if it were false. If the answer is
"the same", the sources are consistent with the claim rather than evidence for
it — and that difference is the whole audit.

**interest-audit** does not ask whether a source is biased. Interested parties
are often the only people present, and discarding them empties the archive. It
asks whether, after collapsing to distinct origins, anything is left that did not
want the claim to be true.

## Running it

Commands below are relative to this pack directory.

```bash
python3 scripts/check.py --artifact <dossier.json> --claim <claim.json> \
    --tier triangulation --json
python3 scripts/check.py --self-test      # 7 known-bad dossiers rejected, 1 accepted
python3 scripts/availability.py --all --bundle <dossier.json>
```

Standard library only.
