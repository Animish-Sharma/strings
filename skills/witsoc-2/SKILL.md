---
name: witsoc-2
description: >
  Domain-agnostic discovery frame for work that must survive being wrong:
  freeze an exact target, triage competing leads, produce a checkable artifact,
  verify it against an objective backend, escalate the hard remainder, and
  report a receipt instead of a confidence. Use for serious research-shaped
  work in any field that has claims precise enough to freeze and some objective
  way to check a candidate against them. The field-specific machinery lives in
  a swappable domain pack; this frame never knows which field it is running.
compatibility: >
  The frame needs python3 and nothing else; every frame script is standard
  library, and the shell entry points under scripts/ need only bash and python3.
  What a run needs beyond that belongs to the domain pack it resolves to, and
  each pack declares it: every tier carries an `availability_check` that reports
  whether it can run before any budget is spent on it. A tier whose external
  dependency is absent reports NOT_RUN and the run states an honest lower
  ceiling rather than discovering the gap late. Without a registered pack the
  frame can freeze targets and triage, and cannot admit anything.
metadata:
  skill-author: OpenScientist
category: research
---

# Witsoc-2

A disciplined **propose → verify → deepen** loop. Search may speculate; status
may not.

The loop below is not a description of any one field. It is the scientific
method instrumented for an agent that cannot be trusted to self-report
correctness.

1. **Freeze the target.** State exactly what is claimed, in a form that cannot
   silently drift while work is in progress.
2. **Triage the space.** Decide which sub-claims and approaches are worth
   pursuing now, and route each to the role equipped to pursue it.
3. **Produce a candidate.** Turn an approach into something checkable.
4. **Verify against a backend that can say no.** Not a vote, not a review of
   the reasoning, not the model's own confidence.
5. **Escalate the hard remainder.** When direct production stalls against a
   real obstruction, hand that obstruction to the role built to attack it.
6. **Record a receipt.** Every claim of success is backed by a verification
   artifact bound to the exact bytes it verified, with a timestamp.

## Boundary

This is the only Witsoc-2 skill contract. The frame owns the loop, the roles,
the status vocabulary, and the admission rules. It does not own a field.

- **The frame** owns target freezing, routing, the claim graph, the status
  contract, the failure-recovery ladder, the bridge packets, and admission.
- **A domain pack** owns the verification adapter, the claim schema, the
  receipt format, its doctrine extension, and its gate definitions — and
  nothing else. See `references/domain_pack_contract.md`.
- **The orchestrator** owns providers, budgets, fanout, ordering, sessions,
  workers, retries, and cancellation. The frame recommends; it does not
  schedule.

The frame never reaches across the contract line. It resolves a pack through
its manifest and calls the adapter. `scripts/check_frame_purity.py` enforces
this mechanically — run it on every change.

## Roles

Three, never more, never merged. Each is a separate contract document; read the
one you are acting as.

| Role | Read | Owns |
|---|---|---|
| **Explorer** | `explorer/SKILL.md` | The problem space. Freezes targets, triages leads, arbitrates returns, decides what happens next. |
| **Generator** | `generator/SKILL.md` | Production. Turns one chosen approach into a checkable artifact and drives it through the adapter. |
| **Researcher** | `researcher/SKILL.md` | The hard tail. Sustained adversarial attack on one specific obstruction. |

They are documents, not separately registered skills — load them by path.

**The no-merge invariant.** Explorer must stay cheap or nothing gets scheduled.
Generator must stay volume-efficient or throughput collapses. Researcher must be
allowed to run long and expensive on a single blocker or the hard problems
never get solved. One engine doing all three is mediocre at each.

**The roles are general; fields plug into them.** Each role is written once and
knows nothing about any field. Loading a pack does not create a different role —
it creates the same role operating over that field's adapter, corpus, and
doctrine. A pack may label a role for its field, but a label is not a role.
`ARCHITECTURE.md` §2.1 lists exactly what each role plugs into, and §2.2 covers
a claim that engages two packs at once.

**Roles never call each other.** Every handoff is a typed packet routed by the
coordinator (`references/bridges.md`). This is what stops a role from growing a
dependency on another role's internals.

## Route

### Step 0 — resolve the pack. Always, before anything else.

```bash
SKILL=$(curl -fsS "$PLANE_SERVER_URL/skills-resolve/witsoc-2/scripts" | jq -r .absolutePath)
bash "$SKILL/resolve.sh" --statement "<the problem, verbatim>"
```

Do not skip this and do not do it by eye. A run that proceeds without a resolved
pack still produces work, still sounds confident, and has nothing underneath it
that can say no — that is the failure this step exists to prevent, and it is
silent when it happens.

The tool prints the exact files to load. **Each role loads its own entry from
`doctrine.roles`** and operates under it; that is the whole mechanism by which a
field's instructions reach the general roles.

| It says | Do this |
|---|---|
| `SELECTED` | Load every file it printed — role doctrine, adapter, claim and receipt schemas — before the first work item. Note the ceiling it reports; nothing in this run may exceed it. |
| `AMBIGUOUS` | Two packs are within scoring distance. Either the claim genuinely engages both — load both, and a fatal objection from either blocks admission (`ARCHITECTURE.md` §2.2) — or the statement is underspecified and Explorer narrows it first. Re-run with `--domain <name>` once decided. |
| `NO_MATCH` | Improvise a pack rather than working with none: `bash "$SKILL/scaffold.sh" --domain <name> --from <closest> --statement "..."`. What it produces is real and capped at `SKETCH`, because the checker and the producer are the same system. Say "provisional" in every report. |
| `UNRESOLVABLE` | Stop. The pack names files that are not there. Fix the manifest; do not proceed believing a field was loaded. |

`--domain <name>` selects a pack explicitly when you already know the field, and
`--list` shows what is registered. `--explain` shows which terms matched, so a
surprising result can be checked rather than argued with.

### Then route the work

| Situation | Action |
|---|---|
| Routine work inside the field's ordinary competence | Answer directly. State assumptions and edge cases. Load no campaign machinery. |
| A precise claim to establish or refute | Freeze the target, then Explorer triage. |
| A candidate artifact needs producing or repairing | Explorer issues a work item; Generator executes it. Repair may enter Generator directly. |
| Production stalled N times on one frozen claim | The ladder escalates to Researcher automatically. Not a judgment call. |
| Status lookup ("is this known?") | Answer from sources. A lookup is not an attempt, and its result is not an outcome. |
| Working under a provisional pack | Everything above still applies, with a `SKETCH` ceiling and the word "provisional" in the report. |

## Status

The vocabulary is frame-owned and domain-neutral. Full definitions and the
legal transitions are in `references/status_vocabulary.md`. The rule that
matters most:

> A status is a statement about **evidence**, not about effort, progress,
> plausibility, or how the run felt.

Process states — a step finished, a budget was spent, a check exited zero, a
worker returned — are not epistemic status and never appear as one.

## Acceptance

Terminal admission requires all of:

- one frozen target hash agreeing across claim, artifact, adapter input, and
  receipt;
- a receipt from the domain's verification adapter that is **fresh** — bound to
  the artifact's current bytes, not to an earlier edit;
- the domain's named refute-attempt gate passed (`references/verification_interface.md`);
- dependency closure: every sub-claim the result rests on is itself admitted;
- no unresolved gap on the closing path;
- independent review, where the domain's doctrine requires it.

Admission is a recorded act, not a judgement: `frame-admission-v1` writes each
condition as PASS / FAIL / **NOT_RUN**, so a skipped check is distinguishable
from a passed one, and it is the only packet that may grant `VERIFIED`.

It is also **enforced, not merely specified**. `scripts/reducer.py` is the only
thing that may move a status, and it does not read the checks — it **derives**
them from the sealed receipt, the result, the reviews, and its own closure walk,
then refuses any disagreement with what the admission asserted. It refuses a
stale base revision, a broken seal, an unclosed dependency, a status above the
receipt's own ceiling, an artifact edited since it was verified, a producer
admitting its own work, and a reviewer who shares the producer's role and method
family. A status that did not come through the reducer did not happen.

None of the following is any of the above: a process exiting successfully, a
budget being exhausted, a vote, a score, a survived bounded search, a plausible
argument, an agent's own confidence, or a file existing where one was expected.
**A role may never accept its own work**, and independence has a definition that
fails closed (`references/verification_interface.md`) — two checks sharing a
failure domain are one check.

## Reporting

Report the frozen target, the outcome, the strongest admitted product, the
mechanism that assures it, the evidence provenance, and the unresolved
obligations. Say `OPEN`, `PARTIAL`, or `STOPPED` when that is what the evidence
establishes — an honest stop is a legitimate result and a failure record that
removes a path from consideration is real negative progress.

Three things the report must not do. Do not imply a higher assurance level than
was achieved — the strongest wording permitted is capped by the highest status an
admitted receipt actually supports. Do not present the route taken as the only
route that existed. And do not cite an artifact that cannot be resolved: an
artifact whose target hash differs from the frozen hash, with no mutation record,
is historical context and never evidence.

State what **must not** be claimed on the strength of this run, and whether the
result was already known — a result that never asks is not a discovery.

`references/execution_discipline.md` covers reporting under interruption: any
message may be the last one.

## Load on demand

| Need | Read |
|---|---|
| The frame/domain split, invariants, governance | `ARCHITECTURE.md` |
| How a pack gets chosen; what to do when none fits | `ARCHITECTURE.md` §1.1, `scripts/resolve_domain.py` |
| Writing or registering a domain pack | `references/domain_pack_contract.md` |
| Status labels and legal transitions | `references/status_vocabulary.md` |
| The adapter interface and the two-step gate | `references/verification_interface.md` |
| Escalation, repair budgets, stop conditions | `references/failure_recovery.md` |
| Operating under interruption; snapshot safety | `references/execution_discipline.md` |
| Concurrency, cost tiers, caching, kill criteria | `references/execution_economics.md` |
| Cross-run memory: tiers, contamination, revival | `references/memory.md` |
| Packet shapes and routing between roles | `references/bridges.md`, `schemas/` |
| Applying an admission; campaign state | `scripts/reducer.py`, `schemas/frame-state-v1.schema.json` |
| Running the whole loop end to end | `scripts/campaign.py` |
| Counting failures; firing escalation | `scripts/failure_ledger.py` |

Resolve the skill's scripts directory once, then everything below is a path
away. The agent's working directory is a worktree, not this checkout, so a
relative path finds nothing:

```bash
SKILL=$(curl -fsS "$PLANE_SERVER_URL/skills-resolve/witsoc-2/scripts" | jq -r .absolutePath)

bash "$SKILL/resolve.sh"  --statement "..."                  # step 0, every run
bash "$SKILL/campaign.sh" run --domain <pack> --tier <t> \
     --claim <claim.json> --artifact <path> --write          # the whole loop
bash "$SKILL/scaffold.sh" --domain <name> --from <closest> --statement "..."
bash "$SKILL/check.sh"                                       # is this skill healthy
```

`check.sh` runs frame purity, the reducer's adversarial suite, the campaign
loop, resolution, per-pack conformance, and every adapter's self-test, cheapest
first. Run it after any change and before trusting any result. The Python
underneath is callable directly if you prefer — `python3 "$SKILL/campaign.py"`
and so on — but the four wrappers are the supported surface.
