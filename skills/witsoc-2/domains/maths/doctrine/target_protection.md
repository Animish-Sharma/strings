# Target protection

The easiest way to make something check is to change what it says. Everything
here exists because of that.

## Frozen, and hashed separately

- original problem text
- canonical statement
- variables and domains
- definitions
- the `GIVEN` block
- the `CLAIM` block
- `allowed_external_facts`

Separate hashes localize drift: a weakened `CLAIM` against an unchanged `GIVEN`
is a different failure from an assumption appearing in a binder, and the hashes
say which happened.

## Rejections

Reject an artifact that:

- uses `sorry`, `admit`, `axiom`, `constant`, `opaque`, `unsafe`,
  `native_decide`, `?_`, or `by?`;
- weakens the target to `True`, `Nonempty`, a toy proposition, or an easier
  domain;
- changes a definition so the statement becomes trivial or vacuous;
- adds a hypothesis to a binder that was not in the frozen `GIVEN`;
- introduces a postulated bridge result as though it were established;
- uses commentary in place of checkable content;
- claims full resolution from a partial artifact.

## Editable region

The proof body only. A signature, definition, domain, or hypothesis change is a
**new claim with a new hash**, recording the from/to hash pair and the kind of
change — never an edit to the existing one.

Where the artifact declares editable ranges, the protected projection — the
artifact with editable bodies removed and markers preserved — must be
byte-identical to the baseline. Duplicate or missing markers usually mean a patch
landed in the wrong place.
