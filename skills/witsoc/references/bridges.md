# Bridges

Roles and capabilities exchange sealed packets through the coordinator. They do
not inspect one another's state or send untyped prose as evidence.

## Typed path

Every capability declares canonical input/output packet types. Use
`bridge-plan-v2` to find bounded paths ranked by semantic loss, hops, and
context. An empty path is a type error. Explicit capability selection remains
dependency-closed.

Use `bridge-negotiate-v2` for one edge. Its agreement binds source and
destination capability, canonical types, adapter id and current adapter hash,
deterministic transform, verification steps, preserved invariants, named
losses, and loss units.

`bridge-translate-v2` executes the agreement:

- `identity` emits byte-identical content;
- `embed-source-v1` emits a canonical transfer packet containing the complete
  sealed source packet and validates its destination type.

There is no implicit conversion. Changed adapter bytes invalidate an old
agreement. A lossy adapter cannot target the status-authoritative type.

## Envelope continuity

`witsoc.bridge-envelope.v2` seals source/destination capabilities and types,
input/output hashes, frozen target, correlation, causation, scope owner,
adapter contract, invariants, losses, conflicts, evidence references, and its
own hash. Build it only after translation.

For each edge require:

- one frozen target and correlation id;
- input hash equal to the source packet hash or preceding output hash;
- input type equal to the preceding destination type;
- causation equal to the preceding envelope hash;
- scope ownership and all required invariants preserved;
- total loss units within the declared budget;
- conflicts visible rather than overwritten.

Use `bridge-compose-v2` for a chain. Use `bridge-graph-v2` for unordered
branches and joins. The graph rejects cycles, missing causes, discontinuous
types/content, and ambiguous roots. A join of nonidentical packets requires a
declared typed join adapter plus Explorer adjudication citing every parent.
Arrival order or priority never resolves a conflict.

## Authority

A bridge only transports a candidate. The destination revalidates assumptions,
scope, representation fidelity, and its own evidence gates. Semantic loss can
lower a ceiling but cannot be traded against a score. No envelope, adapter,
path, or join can grant status.

Version 1 remains ingress compatibility only. New internal traffic uses
canonical packet ids and bridge v2.
