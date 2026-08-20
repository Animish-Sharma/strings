# Demotion and the gap ledger

Demotion runs whenever verification, counterexample search, a worker, or the
checker weakens a claim. It preserves the research instead of hiding the failure:
a claim that quietly disappears takes its evidence with it, and the next run pays
to rediscover both.

## The ladder

`VERIFIED → CHECKED_BOUNDED → SKETCH → PARTIAL → CONJECTURE → FAILED_ATTEMPT →
REJECTED`

Demotion needs no admission — only upgrades do. Move **only as far down as the
evidence requires**. Over-demoting discards a true weaker statement that was
already earned; under-demoting leaves an unsupported status in the ledger where
later work will lean on it.

## Common demotions here

| From → to | Trigger |
|---|---|
| theorem → `SKETCH` | the argument is coherent but has no formal artifact |
| theorem → `PARTIAL` | only a special case, a bounded case, or a conditional statement survives |
| theorem → `CONDITIONAL` | a hidden hypothesis was found and can be stated explicitly |
| theorem → `CONJECTURE` | examples support it, a proof gap remains |
| conjecture → search material | the statement is too vague or its scope is unclear |
| proof → `FAILED_ATTEMPT` | the method fails but yields a reusable blocker |
| claim → `REJECTED` | false, circular, contradicted, or source-mismatched |
| broad target → obstruction | the best available product is a barrier theorem or counterexample |

## Record

Each demotion records: the original claim · previous and new status · the trigger
· the evidence · **the surviving strongest true weaker statement** · the barrier
lemma affected · why that weaker statement still helps, or why it does not · what
was learned · the memory update · the next product.

## The four rules

**Never delete the failed claim; mark it demoted.** A deleted claim is
re-proposed, and its refutation has to be re-derived to reject it again. The
failed claim plus its trigger is the cheapest negative result the run produces.

**Preserve the strongest true weaker statement.** Most failures are partial: the
argument establishes something, just not the target. Discarding the whole
attempt throws away real work, and it also destroys the evidence for where the
boundary of truth lies.

**The demotion must NAME the barrier** — the actual lemma or obstruction that
blocked the original claim. An unnamed demotion records that something failed
without recording what, so it licenses no mutation and the next route walks into
the same wall. This is the rule that turns the demotion log into a map instead of
a graveyard.

**If the artifact failed because the target drifted, demote the artifact, not the
claim.** The claim was never tested — a different statement was. Demoting it
would record a refutation that did not happen and would drop a live target.
Restore the frozen target and re-attempt.

Two further consequences: a counterexample is minimized and recorded; a hidden
hypothesis becomes a conditional-theorem candidate rather than a dead end. The
weaker statement never silently becomes the main target — it is marked `PARTIAL`
or `CONDITIONAL` and the frozen target stays open.

## The gap ledger

Every occurrence of "it remains to show", "standard", "clear", "by a known
result", or "should follow" becomes a **numbered gap** unless an exact dependency
is cited. These phrases mark exactly the steps the author did not check; left
unnumbered they read as prose and pass review unexamined.

Each gap records: the claim needed · where it is used · its dependencies ·
candidate theorems · failed attempts · counterexample search · formalization risk
· the owner · status · discharge evidence.

Status is `open | reduced | blocked | discharged | demoted`.

## Ledger rules

- **A gap as hard as the original target ends the full-proof escalation.** The
  proof has not reduced the problem, it has relocated it; continuing spends the
  budget on the same difficulty under a new name. Select a narrower product.
- A gap that repeats across routes is promoted to a named barrier. Two routes
  sharing a gap means the gap is the obstruction, not the routes.
- **Production is blocked while any essential gap is `open`, `blocked`, or
  `demoted`.** Formalizing a target with a live essential gap produces an
  artifact that either fails on the gap or hides it behind an assumption — both
  cost more than resolving the gap first.
- Individual gaps may be dispatched as lemma-discovery targets. That is their
  best use: a named gap is a well-posed sub-problem.

Before a full proof or disproof is accepted: every essential gap is
`discharged`, each discharge cites proof, computation, source, artifact, or
verifier evidence, and every non-essential gap is explicitly marked as no longer
needed after proof compression.
