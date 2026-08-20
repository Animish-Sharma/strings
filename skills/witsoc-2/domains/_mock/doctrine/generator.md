# Mock pack — generator doctrine

## Producing here

An artifact is content that must normalize to the claim's `expected_value`. That
is the whole field, and it is enough to exercise freeze, produce, verify,
receipt, refute, and escalate without any real toolchain.

## Submitting

    python3 adapter/check.py --artifact <file> --claim <claim.json> --tier exact

The `exact-recheck` refute-attempt gate re-runs the exact tier against the
artifact's current bytes. Because that tier is deterministic and total,
surviving it is a genuine attempt to break the result rather than a second
friendly run.

The `placeholder-scan` gate rejects an artifact still carrying TODO, FIXME,
placeholder, or omitted. Every field needs this gate and only the token set
differs — an artifact that says it will do the hard part later has not done it.

## What you may not do

Edit the claim to match the artifact. Accept your own work.
