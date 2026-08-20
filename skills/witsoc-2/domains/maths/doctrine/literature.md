# Literature — triage before theorem search

Runs before any search for usable theorems on a serious open problem. The order
matters because a wrong status claim early — "this is open", "this is known" —
misdirects the entire campaign and is expensive to unwind once routes are built
on it.

## Source stack

Prefer in this order:

| Rank | Source | Why it sits here |
|---:|---|---|
| 1 | original paper or problem list | the statement as posed, before restatement drift |
| 2 | author-maintained page | the person best placed to know current status, and it is dated |
| 3 | current survey | statements checked by someone who read the primary sources |
| 4 | recent preprint with an explicit theorem statement | precise, but unrefereed |
| 5 | formal library | machine-checked, but often a variant of the informal statement |
| 6 | database or pointer | tells you where to look, never what is true |
| 7 | blog, forum, or informal note | useful for leads and folklore, never for a status claim |

Each level below the first restates. Restatement is where quantifiers move,
hypotheses vanish, and a variant quietly replaces the target — so a claim taken
from level 6 or 7 and used as a premise is a variant-drift barrier waiting to
fire.

Levels 4-7 are **pointers, not evidence**. A source stays unread until someone
reads the primary statement; citing a search result is citing a title.

## Per-source record

Every source records: the title · the authors · the venue or archive id · the
publication date · the source type and stack level · the exact statement
extracted, verbatim · how it relates to the frozen target (`same | stronger |
weaker | neighbouring | unrelated`) · whether the primary source was actually
read · what it is being used for.

The verbatim extraction and the relation field are what make a later
variant-alignment check possible. Without them the campaign cannot tell whether
the theorem it is leaning on is about its problem.

## Problem-level record

Per problem: the origin · the exact statement variants and how they differ · best
known positive results · best known negative examples · known barriers · known
failed methods · current status with its date · sources checked · unchecked
leads.

Unchecked leads are recorded, not dropped. A lead that was never followed is a
known unknown; silently omitting it converts it into a false sense of coverage.

## Rules

- **Never transfer a solved neighbouring variant to the target without recording
  the variant alignment.** The transfer is the single most common way a campaign
  proves the wrong theorem while believing otherwise.
- Date every status claim. "Open" is a statement about a moment, and the whole
  value of the triage decays from that moment.
- Record "unknown after search" separately from "open". They differ in what they
  license: the first permits more searching, the second permits attacking.
- Route any theorem a source supplies through the corpus and precondition audit
  before using it as a premise. A source states a theorem; it does not establish
  that its hypotheses hold here.
- When triage exposes a barrier, record it in `barriers.md` and in memory.
- Offline is not evidence. A failed search is `network_unavailable`, never "no
  prior art".

## Staleness gate

A problem's triage ledger is **stale after 90 days**. Re-campaigning on a stale
ledger is forbidden until it is refreshed.

The gate exists because the failure it prevents is unrecoverable: an open problem
resolved during the interval turns the entire campaign into a re-derivation, and
nothing inside the run can detect that. Ninety days is short enough to catch a
preprint before a campaign completes, and long enough that the check is not the
work. Compare against the ledger's recorded date; do not estimate the age from
how recent the sources feel.
