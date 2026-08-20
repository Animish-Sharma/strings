# Bridges

Roles never call each other. Every cross-role handoff is a typed packet routed
by the coordinator.

This is not ceremony. A role that reaches into another role's internals grows a
dependency on them, and the next change to either breaks both. The bridge layer
is what keeps the three roles independently replaceable.

```
                    ┌──────────────┐
                    │ Coordinator  │
                    └──────┬───────┘
        work-item          │           work-item
    ┌──────────────────────┼──────────────────────┐
    ▼                      │                      ▼
┌────────┐            ┌────────┐             ┌────────┐
│Explorer│            │  ...   │             │ Researcher │
└────┬───┘            └────────┘             └───┬────┘
     │ work-item                                 │ result
     ▼                                           │
┌──────────┐   result    ┌──────────────┐        │
│Generator ├────────────►│ Coordinator  │◄───────┘
└──────────┘             └──────┬───────┘
                                │ escalation (ladder trigger)
                                ▼
                            Explorer
```

## Packets

| Packet | From → To | Carries |
|---|---|---|
| `frame-claim-v1` | Explorer → state | The frozen claim: exact statement, conditions, hash. The thing everything else binds to. |
| `frame-work-item-v1` | Coordinator → Generator or Researcher | Exactly one claim, its dependency path, the active obstruction, the falsifier, the expected artifact, the cost cap, the stop rule. |
| `frame-result-v1` | Generator or Researcher → Coordinator | A **candidate** claim plus its evidence, bound to the work item and the frozen target hash. Never an accepted status. |
| `frame-receipt-v1` | Adapter → Coordinator | The verification outcome, bound to the artifact's content hash. |
| `frame-review-v1` | Reviewer → Coordinator | An independent check, bound to the exact result bytes, asserting a producer/reviewer distinction. |
| `frame-admission-v1` | Coordinator → state | **The only packet that moves a status.** Records each acceptance condition as PASS/FAIL/NOT_RUN and carries a typed, hashed state delta. |

## Binding rules

**One hash across everything.** The frozen target hash must agree across the
claim, the work item, the artifact, the adapter input, the receipt, and the
result. A mismatch anywhere is rejected, not reconciled — and it is
disqualifying rather than a penalty to be traded off. The claim declares
`canonical_fields`, the exact ordered list the hash is computed over, so two
parties independently computing "the canonical form" get the same answer.

**Every packet seals itself.** `payload_sha256` covers the packet's canonical
JSON with that field removed. This is what lets a later packet name *this exact*
earlier one: an id is a mutable label, and a chain built on ids can be re-pointed
at different bytes. Results bind the work item by seal as well as by id, because
the target hash does not cover the dispatch constraints — tier, forbidden drift,
stop rule — which is precisely where a re-issued work item could loosen.

**An identifier names fixed content.** If the bytes behind a result, receipt, or
artifact reference change, that is a new record with a new identifier, not an
update. Reusing an identity over changed content fails closed. Re-submitting the
same record against the same state is idempotent and admits once.

**Every packet is anchored to a state revision.** `base_revision` and
`base_state_sha256` record what the packet was cut against. Without them a delta
is unapplyable safely — and the gap gets worse the better Researcher does its job,
since a long campaign returning against state that moved beneath it is exactly
the lost-update case.

**Packets carry no runtime.** Provider, model, machine, session, worktree,
process, wall-clock, token counts, and retry state belong to the orchestrator's
execution envelope, not to the packet. A packet that knows what model produced
it has coupled the discovery loop to the runtime.

**Candidates stay candidates.** A result packet cannot assert an accepted
status. It proposes; admission disposes. A role that could accept its own work
would make every other rule in the frame decorative.

**Dispatch is specific or it is refused.** A work item needs an explicit
forbidden-drift statement and a stop condition. You cannot dispatch a vague
worker and expect a sharp answer.

**Every accepted product carries a dependency path to the target.** A checked
sub-result that cannot be traced back is not progress toward the target,
however solid it is on its own.

## Deltas, not replays

Send the active obstruction subtree and content-addressed references, and send
state deltas on subsequent turns. Do not replay the whole campaign into every
packet — context spent re-reading history is context not spent on the problem.
