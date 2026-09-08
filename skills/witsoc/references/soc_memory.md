# SOC memory — working memory for one run

## Three memories, kept apart

| Holds | Where | Who may move it | May it be wrong? |
|---|---|---|---|
| **Status** | `frame-state-v1` | only an admission, through the reducer | no — it is evidence |
| **What survives a campaign** | `memory.py` | recorded outcomes, with a contamination guard | the attention tier may; the reuse tier may not |
| **Attention, within one run** | `frame-soc-v1` | anything in the run | **yes, and that is the point** |

The permission at the bottom right is the design. Attention that can never be
wrong is not attention — it is a second evidence store with no gates on it. So
working memory is allowed to hold a hunch, and is forbidden from holding a
status.

## What it holds

```
CURRENT             one line each: pursuing, obstruction, move
INSIGHTS            what the run believes, each at a frame status
PROGRESS            attempts since progress, admitted, failed, insights
FAILED_APPROACHES   what is ruled out, why, and what would revive it
DECISIONS           the choice, the options, the reason — and later the reward
QUEUE               what is planned, each with a state
```

Five sections, small enough to re-read. That is a constraint, not a
description: a file nobody re-reads is a file with nothing in it.

## The rule that makes it safe

**Attention may not become evidence, and this is mechanical.**

The crude route is closed by the schema — an insight id is not sixty-four hex
characters, so it cannot appear in `evidence_sha256`. The careful route is to
hash a soc entry and offer the digest, and the reducer closes that: give it
`--soc` and it refuses any admission whose evidence hashes to an entry in the
file.

```
REFUSED — evidence 65df3d064287... is insight i-f361100320ed from the run's
working memory. Attention is allowed to be wrong, which is exactly why it may
not stand behind a status — hashing it does not change what it is.
```

## Tiers are frame statuses

An insight carries the strongest status the **evidence** supports, not the
strength of the belief. `CONJECTURE` is the default and needs nothing;
everything above it must name an `evidence_ref`, and the tool refuses otherwise.

The tier **orders attention and never confers trust**. Writing `VERIFIED` in
working memory does not make anything verified — only an admission through the
reducer can — and the reason the tiers are frame statuses rather than a private
vocabulary is that a private one produces two ladders with different rungs and no
rule connecting them.

## The repeat gate

Before a work item is issued, the run asks working memory whether this attempt
has already failed. A match on method **and** statement is a HIGH repeat risk and
the campaign stops:

```
REPEAT_REFUSED — this attempt matches a recorded failure:
  the executable tier on this artifact unchanged
```

Matching on method alone catches too much — the same technique on a different
sub-claim is a different attempt. On statement alone it catches too little,
because the interesting repeat is the same statement approached the same way.

The matching is lexical on purpose. The frame is standard library only, and a
similarity model that is present on one machine and absent on another makes the
gate fire differently in different places — which is worse than firing less
often.

## Failure records need a revival condition

A route closed with no revival condition is closed forever, which is rarely what
anyone meant. The tool records the failure either way and says so, because a
silent permanent closure is the expensive kind.

## Decisions and rewards

A decision is recorded with its options and its reason **before** the outcome is
known. A decision log written afterwards records the justification rather than
the reasoning, and the two are not the same document.

Attribution — outcome plus reward, added later — is the only thing that makes
this memory learn rather than merely accumulate.

## Consolidation says what it dropped

Memory that compacts silently leaves a reader unable to tell forgetting from
never-knowing. Every consolidation records what it removed and why: a
near-duplicate at no higher tier, or an entry over the cap where the lowest tier
and oldest go first.

## Two records of one failure

The failure ledger and working memory both record a failed attempt and neither
is redundant. The ledger holds a normalized **signature**, which is what
escalation counts. Working memory holds the **reason and the revival
condition**, which is what stops the next attempt repeating it. A count cannot
tell you what to change, and a reason cannot fire a threshold.
