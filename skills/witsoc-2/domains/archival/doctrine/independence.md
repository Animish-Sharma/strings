# Independence

When five sources agree, that is either five observations or one observation
copied four times. In a bibliography the two are written identically. Separating
them is the whole of what this pack does.

## The operation

Follow each supporting source back along `derives_from` until it reaches
something that derives from nothing else in the set. That is its root. Merge
roots that share an author or an archive. Count what is left.

The number that matters is never how many sources agree. It is how many are still
distinct after the chains come home.

## Why merging by origin matters

Two volumes printed from one manuscript are one origin. Two entries by the same
scribe in two registers are one origin. Independence is about who observed, not
about how many objects the observation survives in — and the objects are what get
counted, because they are what has shelfmarks.

## `derives_from` is not `cites`

It means *takes this claim from*. A chronicle citing a register for a different
fact does not derive from it for this one.

Two errors, and they are not symmetric:

- **An edge recorded that is not there** costs apparent support. The claim looks
  weaker than it is. Recoverable.
- **A real edge omitted** invents independence. The claim looks stronger than it
  is, the adapter cannot detect it, and nothing downstream will catch it.

So when a derivation is uncertain, include it and say it is uncertain. The
asymmetry is the reason.

## One origin is a result

`CHECKED_BOUNDED_DOCUMENTED` — a single surviving origin records this — is a
legitimate, narrow, useful finding. It establishes that the thing was written
down, in that place, by that hand.

It is not attestation. Plural wording is unavailable, and "sources record" is
false when there is one.

## A cascade refutes the argument, not the claim

When the collapse comes back short, what has been refuted is the reason given for
believing the claim. The claim itself may be perfectly true and is now
unsupported, which is a different state from being false and should be recorded
as `REJECTED_CASCADE` rather than as a disproof.

Conflating the two is how a bad argument for a true thing gets it disbelieved.
