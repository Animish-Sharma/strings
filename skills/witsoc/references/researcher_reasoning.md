# Researcher Reasoning Contract

## State Discipline

- Verify the contract's sealed `ATTACK_AUTHORIZATION`. Use phases
  `SCREENING -> DEEP_ATTACK -> RETURN`; finish at `RETURN`.
- Preserve the exact `TARGET` claim and episode binding.
- Preserve separate `OBJECTIVE`; its counterexample is `ROUTE_REFUTED` unless
  it also refutes a target clause.
- Work `ASSIGNED` unless one semantic route field changes. For a local mutation,
  name the changed axis and preserve at least five route fields.
- Mark off-route work `SIDE_RESULT` and `REFRAME_REQUIRED`; it cannot promote.
- Keep at most four hypotheses and one `ACTIVE`; record mechanism,
  discriminator, predicted failure, and output.
- Change one axis per attempt; record fixed axes, method, diagnostic, obligation
  change, and failure domain. Exact repeats are invalid.
- Keep an acyclic subgoal DAG. Closure needs discharged subgoals, `INV-ROUTE`
  equal to the assigned object, and all invariants `PRESERVED`.

## Claim Graph

Represent assertions once in an acyclic graph. Type assumptions, transfer,
derivation, formalization, empirical limits, and review as `obligations`;
closure-path obligations need `DISCHARGED` exact evidence.

Ceilings are `EXACT`, scope-matched `SOURCE_VERIFIED`, finite
`COMPUTATIONAL_BOUNDED`, `EMPIRICAL`, `SEARCH_BOUNDED`, and guidance-only
`HEURISTIC`/`CONJECTURAL`/`UNKNOWN`.

For each closure candidate, complete `target_fidelity`: relation, every clause,
and every distinction. Endpoint candidates require all clauses `SATISFIED`, no
scope limit, and boundary/exclusion evidence. Route-local results state limits
and never claim complete target coverage.

Only `EXACT`/`SOURCE_VERIFIED` claims with safe ancestors may close. Checks,
searches, scores, and agreement cannot raise evidence class.

V4 is complete imported context. `SOURCE_VERIFIED` uses only allowed refs with
their scope; never widen sources or globalize scoped failure.

## Attack Cycle

1. Parse the assigned claim into the smallest dependency graph that can affect
   the requested outcome.
2. Generate one to four distinct mechanisms; choose the cheapest decisive test.
3. Derive then attack the pivotal claim: boundaries, quantifiers, assumptions,
   implication direction, source scope, circularity, and a domain adversary.
   Test initial cases before extrapolation. Derivation/search absence is not a
   nonexistence result.
4. On failure repair, demote, or backtrack; invalidate dependent claims.
5. Return the episode when the evaluator decides, the first required gate
   fails, the bound is reached, or every allowed hypothesis is rejected. This
   never stops the campaign.

Every pivotal/closure claim needs a `SURVIVED` attack. Contradictions mark both
claims `CONFLICTED`; reject one side, separate assumptions, or return control.

## Outcome Gates

- `CANDIDATE_PRODUCT`: clauses/distinctions pass; `TARGET` stays open pending
  independent verification and admission.
- `ROUTE_REFUTED`: keep `TARGET` open; return the route-local counterclaim and
  first failing gate.

- `STRICT_REDUCTION`: provide a supported implication from the residual claims
  to `TARGET` and show at least one strict burden decrease in quantifiers,
  assumptions, dependencies, scope, estimate, or open core. Renaming is not a
  reduction.
- `TARGET_FALSIFIED` (legacy `FALSIFICATION`): mark `TARGET` refuted and identify a closure-safe decisive
  conclusion with a direct target consequence. Bounded evidence limits scope.
- `METHOD_BARRIER` (legacy `NEW_OBSTRUCTION`): compare two distinct mechanisms; name attempted families,
  failure domains, decisive claims, alternatives, limits, and revival. One
  failed technique is `NO_PROGRESS`.
  A positive endpoint-shaped identity cannot be returned under this label.
- `CORE_SHARPENED`: return a more primitive residual plus attackable children.
- `POSITIVE_SIGNAL`: retain bounded directional evidence without closure status.
- `NO_PROGRESS`, `NO_DELTA`, or `SESSION_CHECKPOINT`: report the strongest valid
partial result, first failing gate, diagnostic, revival, and follow-up seeds.
- `WAITING_EXTERNAL`: name the unavailable artifact or protocol and the import
  condition. Waiting is not support.
- `ADMITTED_PRODUCT`: requires an admission already in issued state.

Before return, run `reasoning-check` against the sealed handoff. Then run
`delta-build --handoff`; it derives exactly one typed return message from the
reasoning state. Return only the sealed delta to Explorer. The contract fixes
`campaign_authority=false` and `allowed_termination=EPISODE_RETURN_ONLY`.
