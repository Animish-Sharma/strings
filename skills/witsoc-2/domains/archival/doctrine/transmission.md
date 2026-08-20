# Transmission

Between a claim and the document it rests on, things happen to the words.
Translation, abridgement, paraphrase, editorial reconstruction, emendation. None
of them is visible in a citation.

## Count the hops

The `transmission-chain` gate walks each supporting source to its root and counts
language changes and lossy transformations. Past two language changes, the key
wording must be quoted somewhere in the dossier **in the original**.

The reason is not pedantry. A claim resting on a phrase that has been through
three translations is a claim about the third translator's reading, and the
argument for it is an argument about that reading whether or not anyone says so.

## Reconstructions must announce themselves

An editor's conjecture printed without brackets becomes a fact within one
generation. This is not a hypothetical failure mode; it is the ordinary life
cycle of a well-regarded critical edition.

So a chain passing through a reconstruction or an emendation must carry a
`transformation_note` saying what was changed and on what basis. A chain that
does not is refused — not because the conjecture is wrong, but because a
conjecture that cannot be distinguished from a reading is being used as one.

## Abridgement drops the qualifier first

When a long account is summarized, what goes first is the hedging: the "it is
said that", the "some report", the number given as an estimate. The abridgement
is shorter, cleaner, more confident, and asserts more than its source did.

This is worth checking specifically when a later source is *more* precise than an
earlier one. Precision that increases with distance from the event is precision
that was added.

## Dating consistency is a constraint, not a label

The `dating-consistency` gate reads dates as constraints on the graph rather
than as decoration on each entry. Two things it refuses:

- **A chain that runs backwards.** A source cannot derive from something written
  after it. This sounds too obvious to check and it is one of the most common
  defects in an inherited citation list, because the dates and the edges are
  usually entered by different people at different times.
- **A late witness called contemporary.** A source dated a century after the
  event is not a contemporary witness however early it is *relative to the other
  sources* — and relative earliness is what a bibliography sorted by date
  actually shows you.

Dates here are ordinal and a range is compared by its bounds. `circa` is an
admission of uncertainty and not a licence to ignore an ordering violation of two
hundred years.

## The direction of borrowing can be wrong

A and B agree. The tradition says B copied A. The dates say otherwise, or the
shared error appears in a form that only makes sense one way round.

Reversing an edge can turn one origin into two or two into one, which changes the
verdict entirely. When the direction is genuinely uncertain, the honest dossier
records both edges and accepts the lower count.
