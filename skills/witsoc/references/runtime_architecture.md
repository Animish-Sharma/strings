# Runtime architecture

Runtime v11 has one selective path:

`sticky shell -> sealed activation -> pinned domain -> typed path -> Explorer issue -> bound Researcher -> typed delta -> Explorer arbitration -> admission -> exact review -> finalization`

The shell routes without researching. One registry owns canonical packet ids;
legacy packets are audit-only. The event kernel freezes target and frontier.
The graph chooses a least-cost dependency path plus explicit extensions. A
domain operator compiles a bound execution contract. A compact claim graph
guards the Researcher return. Only the reducer imports status.

The synchronized runtime ships no domain payload. Its compact generated registry
can identify a dormant pack, then install an exact wheel, verify its core API,
contract version, source projection, complete payload digest, sealed install
receipt, and activation attestation before atomic materialization. Setup occurs
before task artifacts; a missing or invalid package fails closed.

## Control

- Preflight seals route, target, domain/package and resource digests, and
  immutable workspace; `start` consumes that receipt without rerouting.
- `orchestrator-next` closes dispatch at revision zero, opens it only for a
  sealed episode handoff or one bound child of a STRONG round, and closes it
  again until Explorer arbitrates. It blocks on disk/state drift.
- V4 handoffs attest pack, source map, capability, operators, resources,
  reasoning contract, and Explorer authorization. V1-v3 are audit-only.
- Role resources project onto supported host workers. Same-named plugins and
  legacy route summaries are never activation or lifecycle authority.
- Explicit Witsoc loops stay in the current invocation; child workers return
  sealed deltas to Explorer.
- Mail, scores, and checkpoints are advisory. Completion requires a current
  canonical finalization; direct answers also require exact independent review.
- One coupled episode or one STRONG lineage-audited round may be pending. Every
  round child has its own role handoff and delta; only the aggregate mutates state.
- Returns cannot choose successors. Explorer validates, merges, and arbitrates.
- Route identity is semantic. Explorer derives recoupling, revival, diversity,
  and recommendation from proposal bytes and replayable route memory.
- Off-route work becomes a typed side result and reframe request. It cannot
  promote the assigned episode before Explorer arbitration.

## Information

- Capsules, capabilities, operators, and rounds have hard context/width caps.
- Researcher state moves through screening, deep attack, and return with bounded
  subgoal/claim DAGs, route invariants, at most three hypotheses and one active,
  typed evidence, attacks, attempts, contradictions, and obligations.
- Every handoff and return crosses the loop as a sealed typed message.
- Every pivotal closure claim must survive pressure. Open contradictions and
  non-closing evidence block promotion and invalidate dependent claims.
- Strict reductions show an implication plus a real burden decrease. New
  obstructions cover attempted methods and failure domains, retain alternatives,
  state limits, and name a revival condition.
- Operator contracts bind backend, command, inputs, evaluator, falsifier,
  outputs, ceiling, resources, and external blockers.
- Bridge v2 plans typed paths, executes hash-bound transforms, and validates
  causal DAGs. Nonidentical joins require typed adaptation and arbitration.
- Novelty audits bind claim-level comparisons and never infer correctness.
- Indexed memory avoids full scans; bounded context packs deduplicate mechanisms
  but preserve immutable evidence references.
- Maths v3 IR, claim-novelty ledgers, tiered checks, and result bundles keep
  numeric evidence, potential novelty, general conclusions, and endpoint status apart.
- State indexes/checkpoints accelerate reads but never replace event replay.

`runtime_architecture.json` is the ownership map;
`runtime_contracts.json` is its generated budget-checked snapshot. Compatibility
wrappers remain at ingress; integrations use `scripts/witsoc.sh`. Read
`domain_packages.md` only for installation, release, or package diagnosis.
