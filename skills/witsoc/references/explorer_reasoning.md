# Explorer Reasoning Control

Explorer controls interpretation, frontier, routes, and returns. It may
normalize, retrieve, compile, and arbitrate, but never attack. Convert ideas
into bounded proposals.

## State Machine

`TRIAGE -> ARBITRATION -> ISSUE -> WAITING_RETURN -> RETURN_ARBITRATION`

- `TRIAGE`: bind target, sources, frontier, kernel route memory, and at most
  five proposals.
- `ARBITRATION`: seal one action and evidence ceiling.
- `ISSUE`: atomically record arbitration and one episode or STRONG round.
- `WAITING_RETURN`: no decision or successor dispatch is legal.
- `RETURN_ARBITRATION`: classify exact returned bytes before frontier change,
  route closure, stopping, or more work.

Revision zero and host missions are input, not decisions. Researcher successors
are advisory. Reconcile every `campaign-audit` blocker before action.

## Target And Sources

Record statement, definitions, quantifiers, assumptions, boundaries, variants,
ambiguities, and generated domain controls. Blockers permit only `DEMOTE` or
`WAIT_EXTERNAL`.

Refine `acceptance_clauses` into atomic endpoint, fixed-structure,
quantifier, assumption, boundary, exclusion, evidence, and generalization
checks; never delete required clauses. Record non-equivalences: derivation non-use
versus global nonexistence, bounded least factor versus finite index covering,
and one-way reduction versus equivalence.

Each map entry binds locator, digest, claim, status, preconditions, and
reliability. A catalogue target also binds `canonical_problem_id:<catalog:id>`.
Failed search is scoped; role output is not a source.

`BOUNDED_COMPLETE` accounts for all entries with none unavailable or unresolved.
Correctness, novelty, and open status are separate. Only `ESTABLISHED` or
`CORRECTED` entries authorize `SOURCE_VERIFIED`.

## Frontier

Use schema-defined node and edge types. Each node needs a path from `ROOT`;
empirical signals use `EMPIRICAL_ONLY` and cannot close a logical edge.

The frontier is the minimal open-leaf antichain controlling the target. Add
nodes before proposing via `REFRAME_FRONTIER` or `EXPAND_FRONTIER`. After two
ROOT attacks, activate and dispatch against a strict child.

## Routes

Each proposal binds one frontier node and decisive question, with its semantic
route, branches, ceiling, prerequisites, target path, bound, and revival data.
`explorer-draft` derives a closed portfolio from proposals and route memory:
metrics, score, fingerprints, recoupling, disposition, diversity, recommendation.

Prefer distinct mechanisms, cores, and failures. Scores are not evidence.
Memory comes only from kernel history. A recoupled proposal needs changed axis,
retained predicate, and evidence. Overrides name the recommendation in
`alternatives`.

## Return Arbitration

Bind the latest return hash. Check target/revision, route, scope, claim graph,
contradictions, target path, and proposed frontier effect. Classify target
progress, local product, route refutation, core sharpening, empirical signal,
source update, external wait, no progress, or conflict.

- Bounded computation/observation can add a signal or refute a tested finite
  instance, not exhaust a general route or admit a general obstruction.
- `NO_PROGRESS` records the first failing gate; it proves no impossibility.
- `ROUTE_REFUTED` decides the assigned objective while leaving `TARGET` open.
- `CANDIDATE_PRODUCT` remains unaccepted and can dispatch only a distinct
  `VERIFY` route before admission.
- Only exact `ROUTE_REFUTED` exhausts the assigned route. Barriers and sharper
  cores require a new child and revival-aware route portfolio.
- A local product without a dependency path remains local.
- Open contradictions block dispatch and completion.

Choose one allowed action. `WORK_ITEM_TO_GENERATOR` uses a separate generator
path, not a Researcher episode. Only reducer-owned admission changes status.

## Honest Stop

Use `PAUSE_WITH_FRONTIER` for a resumable session boundary. Stop is unavailable
at triage and requires a frozen `campaign-stop-scope:`, bounded-complete
sources, six adjudicated attempts, four mechanism axes, two attacks per live
core, two post-reduction attacks, no unresolved route, a minimal core, and an
independent control reviewer outside Explorer and Researcher. The review may
conclude only `ALL_RECORDED_ROUTES_ADJUDICATED`, with scope
`CURRENT_AUTHORIZED_SEARCH_ONLY` and no status authority.

Do not add/reframe a claim and stop in one decision, stop during return
arbitration, or infer universal impossibility, closure, novelty, solved status,
or open status. Use `explorer-stop-review-draft`, independent review,
`explorer-stop-review-check`, then bind the review in `explorer-check` and
`explorer-arbitrate`.

## Workflow

Use `source-map-draft/check`, proposal draft/check, then
`explorer-draft/check --source-map`. Pass the same map to issue and v4 handoff.
After return, rebuild from `--prior-explorer` and the current kernel state. See
`references/orchestrator_protocol.md` for exact commands. Raw lifecycle events
are refused. Preserve explicit state and decisions, not hidden deliberation.
