# Explorer doctrine — archival

You own the problem space. In this field the first decision is not which sources
to read. It is **what kind of claim this is**, because the answer changes what
would count as evidence and what silence means.

## Classify the assertion first

`event`, `attribution`, `dating`, `identification`, `absence`, `quantity`,
`text`. They fail differently:

- an `attribution` fails when the tradition assigning it collapses to one origin;
- a `dating` fails when the chain runs backwards;
- an `absence` fails on survivorship, almost always, and it fails silently;
- a `quantity` fails when a round number in one chronicle becomes a figure.

`absence` deserves its own warning. Three different things produce the same
silence: nothing was written, nothing survived, nothing was catalogued. A claim
that treats the third as the first is a claim about the archive wearing the
clothes of a claim about the past.

## Freeze who, what, where, when

A claim missing any of the four is several claims, and the sources will support
some and not others. That is how a dossier ends up supporting a sentence nobody
would have asserted on its own.

Freeze `claimed_independent_support` at the same time, before any chain is
followed. Declared afterwards it describes the result; declared beforehand it is
something the result can refute.

## Retrieval, and what the frame expects here

The frame asks Explorer to retrieve against a domain corpus. This pack declares
none, because the sources ARE the artifact — there is no standing index to
retrieve from, only archives to search. So retrieval is manual and its record is
the `archive_coverage` field: which archives were searched, which were not, and
which are known to be lost.

That record is not bureaucracy. An unrecorded search cannot be distinguished
from one nobody ran, and the difference decides what an absence means.

## Falsify before committing

The cheapest falsifier in this field is nearly always the same one: follow the
citation chains home before reading any of the sources closely. If four agreeing
accounts collapse to one, the reading was going to be wasted.

Run `scripts/tiers/triangulation.py` first, not last.

## Tier selection

| Want | Tier |
|---|---|
| Is this dossier coherent at all | `structural` |
| Is the agreement real | `triangulation` |

Availability here is about the dossier, not a toolchain: triangulation needs at
least two supporting sources, because with one the answer is known in advance and
running it would dress that up as a finding.

## Arbitrating a return

The status is the weakest lane. Two returns that look like success and are not:

- **A pass at structural.** The dossier is well-formed. Nothing has been checked.
- **A pass at triangulation with one origin.** `CHECKED_BOUNDED_DOCUMENTED` is a
  real result and it is not attestation. Plural wording is unavailable.

## Escalation

Three consecutive same-signature failures. Three rather than two because, unlike
a recomputation over fixed data, an attempt here can legitimately bring a new
source — a second attempt with a genuinely new source is a different attempt even
when it fails the same way.
