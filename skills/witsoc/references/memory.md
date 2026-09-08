# Memory

Memory makes later runs cheaper without turning remembered guesses into facts.
Evidence and hints therefore remain separate immutable stores.

## Evidence store

Objects are sealed under canonical SHA-256. The index stores compact metadata:
kind, target, domain, scope hash, tags, reusability, and admission reference.
Queries filter this catalog before opening object bytes, then revalidate every
returned object. Older indexes are deterministically backfilled.

Default reuse requires exact target, domain, and declared scope. Admitted
products require their admission and evidence references. Source, route, and
obstruction records are reusable only within their stated scope. A hit creates
a candidate shortcut, never an admission.

Invalidation appends a separately addressed record; it never edits history.
Default queries omit invalidated entries while audits can recover the chain.
Use `memory-put`, `memory-query`, and `memory-invalidate`.

## Hint store

Hints contain failed routes, do-not-repeat records, structural analogies,
obstruction families, and transfer candidates. Retrieval requires compatible
scope and at least two structural feature axes. Hints rank attention only.
Any `hint:` reference in an evidence field is rejected recursively.

Use `hint-build`, `hint-put`, `hint-query`, and `hint-invalidate`. Dependencies
are immutable; invalidating a hint cascades through dependent hints with
append-only records.

## Reuse and contamination

Reuse requires agreement on every declared axis, including definitions,
assumptions, inputs, environment, intervention or transformation, measurement,
and target shape. A near match is a transfer candidate requiring an explicit
alignment argument.

Held-out answers, evaluation keys, benchmark outcomes, and unknown-provenance
material never enter either reusable store. Memory cannot upgrade status,
enter a receipt as evidence, silently widen scope, or replace current-byte
verification.

Write failures when they occur, with target and route hashes, mechanism,
diagnostic artifact, blocker, do-not-repeat condition, and revival condition.
When revival evidence arrives, rescan affected records before ranking. Repeated
failures sharing one mechanism should promote it to a named obstruction.

Resolve contradictions before proceeding. Neither old memory nor the current
run wins automatically; retain the resolution and the scope difference.

Kernel `state-index` and `state-compact` are read models, not memory evidence.
Their hashes accelerate navigation, but authoritative state still comes from
full deterministic event replay.
