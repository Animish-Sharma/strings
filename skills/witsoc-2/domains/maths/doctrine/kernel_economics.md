# Kernel economics

## The measurement

Governance rule 9 says an optimization proves it pays. This is the measurement,
taken against a real Mathlib checkout (8,174 compiled modules, Lean 4.31.0-rc1),
three runs each:

```
import Mathlib, nothing else          5.16s  4.68s  5.05s
import Mathlib + a 3-obligation proof 5.08s  5.08s  5.10s
```

**The proof is under 2% of the cost. The import is everything.** So the repair
loop — which re-elaborates after every edit — spends essentially all of its
budget re-importing a library that did not change, and prefix reuse is worth
something like fifty to eighty times on that loop. The manifest has declared
`prefix_reuse.supported` since it was written, on exactly this reasoning.

## The optimization was attempted and rejected

A Lean REPL was available and built at the same toolchain. Importing once and
sending each candidate to the running process gave:

```
import once     0.37s
per theorem     0.06s     ~80x
```

Those numbers are real and the mechanism does not work. Inspecting the REPL's
messages rather than its timings:

```
#eval 1 + 1                  ->  error: Unknown constant `OfNat`
example : True := trivial    ->  error: Unknown identifier `trivial`
```

The import had not taken. Every command after it ran against an essentially
empty environment, and the REPL returned success-shaped JSON — an `env` id, a
`messages` array, a plausible elapsed time — the whole way through.

That is the worst failure mode available to a verification backend, and it is
worth naming precisely: **it does not fail, it succeeds emptily.** Wired in
without reading the messages, every artifact would have "elaborated" in sixty
milliseconds against nothing, and the timings would have looked like the
optimization working.

## What this means for the ablation rule

Rule 9 asks that an optimization ship with an ablation showing identical
behaviour with it off. This one could not produce that, because with it ON the
behaviour was not verification at all. The rule caught it, and it caught it on
the strength of a check nobody would have run if the numbers had merely looked
disappointing — the numbers looked *excellent*.

The lesson generalizes past Lean: **a fast path must be validated against the
slow path on a known-BAD input, not a known-good one.** A backend that has lost
its environment passes nothing and fails nothing; on a good input it looks
broken, on a bad input it looks broken, and only on a *set* of inputs whose
verdicts should differ does the emptiness show.

## Where this leaves the pack

- Prefix reuse remains justified by the measurement and unbuilt.
- The manifest says so, rather than advertising a capability that has no
  implementation.
- Before any future fast path is enabled by default it must reproduce the slow
  path's verdict on `scripts/negative_control/` — every rejection AND the
  acceptance. That is the only test that distinguishes a fast checker from an
  absent one.

## The cheap win that does exist

`WITSOC2_LEAN_PROJECT` must be set for the kernel tier to see the library at
all: `lake env` takes its search path from the directory it runs in, so
elaborating from the artifact's own directory silently uses the ambient
toolchain with an empty path. Both the kernel tier and the axiom audit had that
bug; availability reported the library present while every import of it failed.

`scripts/availability.py` now counts compiled modules rather than checking that
a directory exists, because a partially built checkout has the directory and
none of the content.
