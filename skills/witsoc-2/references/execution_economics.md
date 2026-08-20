# Execution Economics

How the frame goes fast. Everything here is about spending effort where it pays
and not spending it anywhere else.

None of it may change what is true. Rankings order work; validators decide
trust. A mechanism in this document that changes a status has escaped its lane.

## The claim graph is also the schedule

The dependency structure that decides *closure* also decides *concurrency*. It
is the same graph read twice, and reading it only once is the largest piece of
performance left on the floor.

| Relation | Closure | Schedule |
|---|---|---|
| **AND** | closes when **every** child closes | fan out over all ready children concurrently; loop until no node is ready |
| **OR** | closes when **any one** child closes | **race** the siblings; the first to pass cancels the rest |
| **LEAF** | closes on its own evidence | dispatch directly |

An OR-group is a race, not a queue. Alternative approaches to the same
sub-claim are exactly the case where you want the fastest winner and nothing
else — dispatch them together, accept the first that passes the checker, cancel
the losers. Running them in sequence pays the full cost of every approach that
was never going to win.

A node is **ready** when its dependencies have closed. Re-derive the ready set
after every return rather than planning a full schedule up front; the graph
changes as results land.

Cancellation is not failure. A cancelled sibling records `superseded`, not
`FAILED_ATTEMPT` — it was never refuted, it just lost a race, and recording it
as a failure would poison the do-not-repeat ledger against an approach that may
be the right one for a different claim.

## Fan-out is capped by diversity, not by N

Sampling the same approach harder saturates fast: doubling identical attempts
buys very little, while a genuinely different angle can buy everything.

So width is allocated across **cells** — (method family × representation ×
backend tier) — and every cell gets one candidate before any cell gets a second.
Correlated fan-out is not diversity; it is the same attempt billed several
times.

Portfolio constraints, whatever the width:

- at least one refutation lane on any target being established;
- at least one adversarial lane before promoting a product;
- generation-only lanes capped at roughly **40%** unless nothing checkable
  exists yet;
- at least one production lane when a product was actually requested.

## Role cost profiles

The no-merge invariant is a performance argument as much as a correctness one.
The three roles have different cost shapes and must be scheduled differently:

| Role | Shape | Scheduling |
|---|---|---|
| **Explorer** | cheap, frequent, on the critical path of everything | Must never become the bottleneck. If triage gets expensive, nothing gets scheduled and the whole loop stalls. Keep its context small and its decisions bounded. |
| **Generator** | high volume, individually cheap | Parallelize wide. Cheapest tier first. This is where throughput is won or lost. |
| **Researcher** | expensive, long-running, low concurrency | Serialize on one obstruction at a time. Its budget is justified only by depth, so spending it on the tractable middle wastes the only role that can afford to go deep. |

Merging any two of these forces one schedule onto two cost shapes.

## Spend cheap before spending dear

**Probe availability before spending.** A tier declares an `availability_check`.
Run it first, so a run states its honest ceiling up front instead of discovering
after the budget is gone that the backend it needed was never there.

**Cheapest sufficient tier.** Explorer freezes the tier a claim requires from
`max_status` — the cheapest tier that can reach the needed status, never the
strongest available. An expensive backend should only ever see what a cheap
deterministic pass failed to close.

**Effort tiers escalate one way**, with a recorded reason at each step: a
deterministic pass, then a searching pass, then a heavy pass. Never start at the
top because the problem "looks hard"; the cheap pass is also the fastest way to
learn that it is.

**Degrade rather than crash near a budget cap.** Drop to cheap tiers and
checkpoint. A run that stops with a recorded state is recoverable; one that dies
mid-attempt is not.

## Never pay twice

**Hoist the invariant prefix.** Where a backend has expensive shared setup, pay
for it once and fork every branch from that snapshot rather than re-paying per
branch. This is the single largest available speedup in most verification
pipelines — an order of magnitude, not a percentage. A pack declares whether its
adapter supports it.

**Content-hash every dispatch.** Identical requests then dedupe for free and a
replay finds the earlier answer instead of recomputing it. Advisory context must
stay *out* of the identity hash, or memoization breaks every time memory grows.

**Reuse has a precondition.** A cached result may be reused only when the
context matches on every declared axis — assumptions, definitions, inputs,
environment, target shape. A cache hit is evidence about **checkability**, never
about truth: it orders work, it does not confer status.

**A failed cached route is also cached.** Record its failure class and never
retry it unchanged.

**Keep a method ledger separate from the results ledger.** Results are what was
established; methods are what tends to work, tagged with the conditions they
apply under and their track record. The second is what makes run N+1 faster than
run N, and it is the frame's only compounding asset.

## Kill early, kill honestly

The dominant waste mode is re-running an attempt that already failed for a known
reason. The defenses, cheapest first:

- **Mutation before retry.** A failed node is re-dispatchable only with a
  recorded failure class and a one-axis change. Enforced, not advised.
- **Repair before resample.** Feed the checker's own diagnostics back and revise
  a small number of times — this is the cheapest reliable win available — then
  resample from scratch rather than revising forever.
- **Stagnation window of three.** Three attempts on one obstruction, or three
  same-class failures, escalate one rung. One way, with a reason.
- **Loop health is measured by absence.** No changed statement, no mutation, no
  score movement, no new evidence — that is a stuck loop regardless of how busy
  it looks.
- **A large failure cluster is a systematic obstruction**, not bad luck. Promote
  it; do not keep retrying members of it.

And the counterweight, because early termination is also how a run quits cheap:

> Before an honest stop, a run must have covered several distinct method
> families, more than one representation, and at least one bounded probe with a
> receipt. Stopping is legitimate; stopping *early and unexamined* is not.

Every kill records a **revival condition**. A new admitted result, a refuted
obstruction, or a new counterexample family re-prices every branch — when one
lands, rescan the dead ends before ranking anything new.

## Conditional results are cheap and real

A result of the form *assumption → target* is a genuine product and costs a
fraction of discharging the assumption. Build the consequence structure first,
rank candidate assumptions by **leverage** — how much each would unlock if it
held — and only then spend on establishing the single highest-leverage one.

This turns one expensive all-or-nothing attempt into a cheap map plus one
targeted spend. Conditional products are admitted as `CONDITIONAL`, naming the
assumption; they never quietly become unconditional.

## Context discipline

Send a worker only: the target digest, the assigned claim, its dependency path,
the active obstruction subtree, the accepted premises it needs, the exact
artifact contract, and the stop rule.

- **Work packets are self-contained.** A packet that needs outside context
  cannot be fanned out, which caps concurrency at one.
- **Reference immutable material by hash**, and send **deltas** on later turns
  rather than replaying the campaign.
- **Cap advisory context** — a handful of entries, not a history. Past a small
  size it stops helping and starts crowding out the problem.
- **Compress before dispatch.** Reduce the selected route to the smallest
  obligation graph that preserves fidelity, then hand that over.

## Ordering work

```
priority = (expected_information_gain + prior) / max(cost, ε)
```

Gain **per unit cost**, never raw gain. Ties break toward the cheaper item.

An uncalibrated gain estimate is opt-in and marked as such — a made-up numerator
over a real denominator is worse than no ordering at all. Every score carries a
reason and a falsifiable `confidence_would_drop_if`.

For intermediate results, value is `things_unlocked / complexity`. A cheap
sub-result that unblocks five others beats an expensive one that unblocks one.

## Prove the optimization pays

Any mechanism in this document ships with an ablation: run the cheap baseline,
then run the full path **only on what the baseline left open**, and compare.
Regressions must be empty. Without that, a performance layer is a cost centre
that nobody can prove is earning.

Learned or heuristic ordering may **reorder only**. With the model absent,
behavior must be identical to the hand-written order. That makes every ranking
addition safe by construction: it can waste time, but it can never change an
outcome.
