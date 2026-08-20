# Witsoc-2 Architecture

Witsoc-2 is a domain-agnostic discovery frame: a disciplined
propose → verify → deepen loop, with the field-specific machinery factored out
into swappable domain packs.

The frame is deliberately small. Its predecessor grew to hundreds of scripts and
reference documents with the field-specific parts tangled through the shared
layer, which is the failure this rebuild exists to avoid. Every file here earns
its place or does not exist.

**Relationship to `witsoc`.** This is the same architecture as the one
documented in `../witsoc/ARCHITECTURE.md`, rebuilt with the frame and the
domain packs actually separated. The two describe one design and must stay
aligned: the same three protected roles under the same names
(Explorer / Generator / Researcher), the same contract items, the same two
structural refinements, and the same governance rules. Contract item 6,
`selection`, is the one place `witsoc-2` is ahead: `witsoc` has no separated
packs to resolve between, so the question does not arise there yet. `witsoc` is the
as-built system whose math pack is not yet extracted; `witsoc-2` is the frame
with nothing to extract. Where they differ, `../witsoc/ARCHITECTURE.md` §5 records
why — it is an honest audit of what has not been separated yet, not a second
design.

> **Paths in this document are relative to the skill root.** An agent working
> from a worktree resolves it first — `SKILL.md` has the one-liner — and the
> four shell entry points under `scripts/` are the supported surface.

## 1. The layers

```
                    Coordinator  (SKILL.md)
          routing · status vocabulary · arbitration · bridges
                              |
        +---------------------+---------------------+
        |                     |                     |
    Explorer              Generator               Researcher
  triage / routing     produce & verify        deep attack
        |                     |                     |
        +---------------------+---------------------+
                              |
                     Shared services
   verification interface · evidence store · retrieval · status
   contract · failure-recovery ladder · resource governor · reuse cache
                              |
======================= CONTRACT LINE =========================
   verification adapter · claim schema · receipt format ·
   doctrine extension · gate definitions · selection
                              |
        +---------------------+---------------------+
        |                     |                     |
    domains/<a>           domains/<b>           domains/<c>
```

Everything above the contract line is the frame. It is written once, is
domain-agnostic by construction, and does not know what any particular field's
verification backend is. Everything below the line is a domain pack. Domain
packs are swapped, not merged, into the frame.

**The contract line is exactly six items.** A pack supplies these and nothing
else; the frame supplies everything else and never reaches past them:

1. **Verification adapter** — `(candidate artifact) -> (pass/fail, receipt)`.
2. **Claim schema** — the frozen representation of what is claimed, extending
   `frame-claim-v1`.
3. **Receipt format** — what counts as evidence here, and when it goes stale.
4. **Doctrine extension** — field-specific rules, including the escalation
   threshold (§5).
5. **Gate definitions** — what a candidate must pass to move off
   `CONJECTURE`, including the refute-attempt gate (§4).
6. **Selection** — the terms, examples, and counter-examples that tell the
   frame *when this pack applies* (§1.1).

Items 4 and 5 each carry one mandatory sub-field, because they parameterize
frame machinery that would otherwise be left to judgment. Item 1 additionally
carries an optional `corpus` (1b) — Explorer is required to retrieve against a
domain corpus, so a pack needs somewhere to declare one. The normative spec is
`references/domain_pack_contract.md`; the machine-checkable form is
`schemas/frame-domain-pack-v2.schema.json`.

The contract is at version `2`. Version 1 had been extended in place — backend
audit fields, per-tier ceilings, the corpus slot, status refinements — which was
defensible only while no pack outside this repository implemented it. Item 6 is
the first change made as a deliberate bump (governance rule 6): v1 packs still
validate and still work, they are simply invisible to automatic resolution,
which `validate_domain_pack.py` states when it validates one.

## 1.1 Resolution: how a pack is chosen

A pack that is never loaded is indistinguishable from a pack nobody wrote. This
is the failure mode that matters most in the layering above, because it is
silent: the roles still run, still produce, and still sound confident — they
just do it with no field doctrine, no adapter, and therefore no way to be told
they are wrong.

So resolution is a mechanism, not an instruction. **Before any other work**, a
run resolves the pack:

```bash
python3 scripts/resolve_domain.py --statement "<the problem, verbatim>"
```

It reads only contract item 6 from each manifest and scores the statement:
`1 x signals + 3 x strong_signals - 3 x excludes`. Four outcomes, each with a
defined next move:

| Outcome | Exit | What it means | Next |
|---|---|---|---|
| `SELECTED` | 0 | One pack cleared its threshold and beat the runner-up by 3 | Each role loads its own file from `doctrine.roles`, which the tool prints by path |
| `AMBIGUOUS` | 3 | Two or more qualifying packs within 3 points | Either the claim genuinely engages both (§2.2) or the statement is underspecified; Explorer narrows it before any budget is spent |
| `NO_MATCH` | 4 | Nothing cleared its threshold | Improvise a provisional pack — see below |
| `UNRESOLVABLE` | 5 | A pack was chosen and its declared files are missing | Stop. Fail closed |

The field's vocabulary lives in the pack and never in the frame, which is what
keeps this compatible with governance rule 2: `resolve_domain.py` carries no
field terms of its own, and could not, since the purity check would catch them.

**The ceiling is carried, not just printed.** Resolution reports
`max_admissible_status` — the strongest status the resolved pack's tiers can
support, lowered further if the pack is provisional. Pass it to the reducer when
the campaign is created:

```bash
python3 scripts/reducer.py init --claim <claim.json> --out state.json \
    --ceiling <max_admissible_status>
```

The reducer then refuses any admission above it, with every other check passing.
A ceiling is set when a claim is created and never raised — there is no delta
operation that lifts one — which is what turns a provisional pack's cap from a
warning in a report into something the state machine will not do.

`--self-test` runs every pack's declared examples back through resolution and
requires each to select its own pack, and every counter-example not to. That is
what keeps a signal list from quietly broadening until it steals another pack's
problems — the failure surfaces at edit time rather than in a run.

**When nothing matches.** NO_MATCH is not a refusal and not a dead end. The
orchestrator improvises a pack from the closest registered one:

```bash
python3 scripts/scaffold_domain.py --domain <name> --from <closest> \
    --statement "<the problem>"
```

The result is a real pack — a working adapter that checks the field-independent
properties (no placeholder tokens, every frozen obligation addressed, target
hash unchanged), a refute-attempt gate that perturbs the claim and requires the
verdict to flip, negative controls it must reject, and doctrine for all three
roles. What it cannot be is trusted like a registered pack: `authored_by` is
`orchestrator`, meaning the system that produces candidates also wrote the thing
that checks them, so the ceiling is `SKETCH` and the validator refuses a higher
one unless the pack wraps a genuinely external checker. An improvised pack lets a
run proceed. It does not let a run conclude.

## 2. The three protected roles

| Role | Owns | Never does |
|---|---|---|
| **Explorer** | The problem space, not any single problem. Freezes targets, triages competing leads, decides what gets worked next, selects the verification tier. The only role permitted to change what the system is currently pursuing. | Produce a final artifact. Assign truth. |
| **Generator** | Production. Turns a chosen approach into a candidate artifact and drives it through the domain's verification adapter. Optimizes throughput on the tractable middle of the difficulty distribution. | Accept its own work. Change the frozen target. |
| **Researcher** | The hard tail. Sustained, multi-step, adversarial attack on a specific obstruction that resisted direct production — refutation-first search, decomposition, barrier analysis. | Dispatch work. Close a target unilaterally. |

**The no-merge invariant.** These three are never collapsed into one engine, in
any domain. The reason is structural, not stylistic: they have different failure
modes and different time budgets. Explorer must be cheap and fast or nothing
gets scheduled. Generator must be volume-efficient or throughput collapses.
Researcher must be allowed to run long and expensive on a single blocker or the hard
problems never get solved. Merging them produces a system that is mediocre at
all three jobs at once.

**No fourth role.** A proposal to add a fourth domain-spanning role gets the
same skepticism as a proposal to merge two of the existing three. If a domain
appears to need one, the need almost always belongs in one of the six contract
items.

**The roles are general; fields plug into them.** There is one Explorer, one
Generator, one Researcher, written once and knowing nothing about any field.
Loading a pack does not produce a different role — it produces the same role
operating over that field's adapter, corpus, and doctrine. A pack may give the
role a display name for its field, recorded in its manifest, but that is a
label on the general role, never a separate one. Two packs' Researchers are the
same Researcher with different things plugged in.

### 2.1 What each role plugs into

Every role consumes specific contract items and nothing else. This is the whole
plug surface — if a role needs something not on this list, either the contract
is incomplete or the need is not really domain-specific.

| Role | Consumes from the pack | Uses it to |
|---|---|---|
| **Explorer** | selection (6) · claim schema (2) · corpus (1b) · tier list + `cost_hint` + `max_status` (1) · doctrine thresholds (4) | Resolve which pack this problem belongs to at all (§1.1); freeze the target with the field's frozen content; retrieve prior art; pick the cheapest tier that can reach the needed status; know when to escalate. |
| **Generator** | verification adapter (1) · receipt format (3) · gates (5) | Produce, submit, get a receipt, pass the refute-attempt and the field's other gates. |
| **Researcher** | doctrine incl. obstruction catalogue (4) · corpus (1b) · bounded/cheap tiers (1) | Attack the obstruction with the field's known families; run bounded searches that cannot exceed their `max_status`. |

Nothing here lets a pack reach *up* into a role. The flow is one-way: the role
asks the manifest, the manifest answers.

### 2.2 A claim may engage more than one pack

A claim can be simultaneously about two fields — an empirical result whose
statistical sub-claims need separate treatment, say. That is **two packs on one
claim**, not a fourth role.

Rules when packs are paired:

- Each pack's Researcher audits within its own competence and returns its own
  candidate verdict. Neither speaks for the other's field.
- The frozen claim is shared; each pack contributes its own frozen conditions
  to it, and the target hash covers all of them.
- **A fatal objection from any engaged pack blocks admission.** Verdicts are not
  averaged, and a pass in one field never compensates for a failure in another.
- Establishing something in one field does not establish it in another. Support
  from one pack caps at `CONDITIONAL` on the other's open questions.

## 3. Bridges

Roles never call each other directly. Every cross-role handoff is a typed packet
routed by the coordinator, so no role grows a dependency on another role's
internals. The packet types are in `schemas/`, and the routing rules are in
`references/bridges.md`.

```
Explorer  --frame-work-item-->  Generator  --frame-result-->  Coordinator
Explorer  --frame-work-item-->  Researcher     --frame-result-->  Coordinator
Coordinator --escalation--> Explorer   (on ladder trigger; see §5)
```

## 4. Verification is two-step

A domain's verification adapter is a function
`(candidate artifact) -> (pass/fail, receipt)`. It may dispatch over several
backends internally; the frame only sees the signature.

Generator's flow is **propose → refute-attempt → receipt**, never a single
adapter call. Where a domain's adapter is already adversarial — it cannot be
talked into a false pass — the adapter run *is* the refute-attempt gate, and no
extra mechanism is needed. Where a domain's verification is graded, a result
that survives only one favorable run does not earn a receipt: it must be re-run
under a deliberately perturbed condition, or routed through a skeptic pass whose
only job is to break it.

Every domain pack must therefore declare a **named refute-attempt gate**. This
is a required field in `schemas/frame-domain-pack-v1.schema.json`, so a pack
cannot skip it by omission.

**And the backend itself is audited.** Everything above assumes the adapter can
say no — the frame's most load-bearing assumption and the one it least controls.
`adversarial: true` was originally a self-report by the party being checked,
inside a frame whose whole premise is that self-reports do not count. So the flag
now has conditions: independent authorship, two-sided evidence, contamination
controls, and a registered negative control the adapter must reject.

A tier's honesty and its reach are also separate, and conflating them was a
soundness hole: an exhaustive search over a stated finite domain is genuinely
adversarial *and* permanently bounded. Each tier therefore declares `max_status`
independently of `adversarial`. Passing the gate never lifts the ceiling.

See `references/verification_interface.md`.

## 5. Escalation is mechanical

Explorer and Researcher are both search; the difference is time horizon and depth.
Left to judgment, "when does this become Researcher's problem" gets applied
inconsistently across runs and domains. So it is not left to judgment.

The frame's failure-recovery ladder owns one generic rule: **N consecutive
Generator failures on the same frozen claim, or a repeated identical failure
signature, triggers escalation to Researcher.** The counter and the ladder live once,
in the frame. Each domain pack supplies only its own `N` and its own definition
of "identical failure signature", as required fields of its manifest. See
`references/failure_recovery.md`.

**It is now counted rather than described.** `scripts/failure_ledger.py` records
each failure against `(target, claim)`, normalizes the diagnostic generically —
stripping paths, numbers, quoted identifiers, and hex, all of which vary between
two instances of the same failure — and fires at the pack's threshold. Every pack
had declared a threshold and a signature rule for as long as it had existed, and
nothing read either: the ladder was a paragraph.

Two triggers, and the second usually fires first. The count, and a repeated
signature — because a second attempt that produced an identical signature changed
nothing the checker could see, and waiting out the count in that state spends
budget to learn what is already known. Only a success resets the counter; not a
retry with a different seed, and not a repair that was not attempted.

The reason it must be mechanical is specific: the decision to stop attacking a
problem directly is exactly the decision a system in the middle of attacking it
is worst placed to make. Each attempt feels like it is closing in, and the count
is the only thing that is not affected by that feeling.

## 5.1 Performance: the graph is the schedule

The frame's speed comes from reading one structure twice. The claim graph's
dependency relations decide closure *and* concurrency:

- an **OR** group is a **race** — siblings dispatch together, the first pass
  cancels the rest;
- an **AND** group is concurrent **fan-out** over every ready child, looped
  until nothing is ready;
- a cancelled sibling is `SUPERSEDED`, never a failure. It lost a race; it was
  not refuted.

Running an OR group in sequence pays the full cost of every approach that was
never going to win. That is the largest piece of performance the predecessor
left unclaimed — it had the closure semantics and never turned them into a
schedule.

The no-merge invariant (§2) is also a scheduling argument. The three roles have
different cost shapes: Explorer is cheap and on everything's critical path,
Generator is high-volume and parallel, Researcher is expensive and serialized on
one obstruction. One engine cannot be scheduled three ways.

### The reducer

One piece of frame code is the **only** thing that may move a status
(`scripts/reducer.py`, state shape in `schemas/frame-state-v1.schema.json`).

This closes the gap at the centre of the design. The founding premise is that an
agent cannot be trusted to self-report correctness — but for as long as the
gates were scripts an agent could choose to run, the enforcement mechanism *was*
trusting the agent. A role could skip every check and assert `VERIFIED`.

Now a status changes only by applying an admission through the reducer.

**Checks are derived, not read.** This is the second half of the same argument
and it was missing for longer. Until it landed, `checks: {"refute_attempt":
"PASS"}` was an *assertion by whoever wrote the admission* — the reducer guarded
seals, staleness and closure, then took the verification result on trust, at
exactly the point where the founding premise says trust is unavailable. The
receipt was accepted on the command line and never opened.

Now the admission carries `receipt_ref`, bound by seal, and the reducer computes
each condition itself: target binding from the chain, freshness by re-hashing the
live artifact, the refutation outcome and completeness from the receipt, closure
from its own graph walk, review from the supplied reviews. The admission's
`checks` block is kept as a record of what the admitting role believed — and a
**disagreement between what was asserted and what the evidence shows is refused
rather than silently corrected**, because the disagreement is the finding.

**Each status requires only what it means.** `REQUIRED_BY_STATUS` follows the
vocabulary: `SKETCH` needs the target and nothing else, because a sketch is an
unchecked argument and demanding a passing receipt for one would be a lie about
what the word means. `CHECKED_BOUNDED` needs a fresh receipt that survived
refutation. `CONDITIONAL` additionally needs independent review, because someone
other than the producer has to agree the named condition is the only gap.
`VERIFIED` needs everything. If every status demanded the same evidence there
would be no reason to have more than one word.

The reducer refuses:

| Refusal | Because |
|---|---|
| a check that is `FAIL` **or `NOT_RUN`** | a check that did not run is not a check that passed |
| no `receipt_ref` for a status that needs evidence | nothing binds the admission to a verification |
| a receipt whose seal does not match its reference | the reference names a different receipt than the one supplied |
| a granted status above the receipt's `max_status` | a ceiling is a property of the backend that produced the evidence; no number of admissions raises it |
| a live artifact hash differing from the receipt's | a passing run from an earlier edit is how a broken artifact launders itself |
| `decided_by_role` that is not `explorer` | a production role admitting its own output is what the no-merge invariant forbids |
| a review whose `producer_ref` is not the supplied result | an unbound review discharges independence for work it never saw |
| a reviewer sharing the producer's role **and** method family | two checks sharing a failure domain are one check; this fails closed when either side declines to say which family it used |
| a stale `base_revision` | the state moved underneath a long-running attempt, so its conclusion may rest on a premise since demoted. This bites hardest on the role that runs longest. |
| a broken `payload_sha256` | the packet was edited after it was sealed |
| a result not bound to its work item by seal | the dispatch constraints it answered cannot be checked |
| dependency closure unmet | AND needs every dependency accepted, OR needs one |
| a status above the claim's ceiling | bounded evidence does not become universal by accumulating admissions |
| a delta adding a claim at anything but `OPEN` | otherwise a pre-established conclusion enters as a side effect |
| `independent_review: PASS` with no distinct reviewer | self-review is not review |

`scripts/reducer_selftest.py` is what makes that checkable. Thirteen adversarial admissions — the
first of them the forged-checks case that motivated all of this — must each be
refused **for the stated reason**, and two honest chains must be accepted. The
accept cases matter as much as the refusals: a reducer that refuses everything
enforces nothing, it just stops.

Every applied admission produces a new content-addressed revision naming its
predecessor, so a run is replayable rather than merely logged — and re-applying
the same admission is refused, because its base no longer matches.

Two further shared services support the schedule and are frame-owned:

- a **resource governor** — the single place that answers "may another expensive
  worker start"; saturation queues rather than errors;
- a **reuse cache**, keyed on full context match, which orders work and never
  confers status. Its rules — the two trust tiers, the contamination rule, and
  revival conditions — are in `references/memory.md`. It is the only part of the
  frame that compounds across runs, and the only store that can launder an
  answer back in as a prior.

`references/execution_economics.md` carries the full lever set: tier economics,
prefix hoisting, diversity-capped fan-out, kill criteria, context discipline,
and gain-per-cost ordering.

## 5.15 Working memory

The frame holds three memories and the distinction between them is load-bearing:

| Holds | Where | May it be wrong? |
|---|---|---|
| status | `frame-state-v1` | no — it is evidence, and only an admission moves it |
| what survives a campaign | `memory.py` | the attention tier may; the reuse tier may not |
| attention, within one run | `frame-soc-v1` | **yes, and that is the point** |

That last permission is the design. Attention that can never be wrong is not
attention — it is a second evidence store with no gates on it. So working memory
may hold a hunch, and is forbidden from holding a status.

**The forbidding is mechanical.** The schema closes the crude route: an insight
id is not sixty-four hex characters, so it cannot appear in `evidence_sha256`.
The reducer closes the careful one: hand it `--soc` and it refuses any admission
whose evidence hashes to an entry in the file. Hashing a hunch does not change
what it is.

Insight tiers are **frame statuses**, not a parallel vocabulary, and anything
above `CONJECTURE` must name its evidence. A private tier vocabulary produces two
ladders with different rungs and no rule connecting them, which is how an
insight marked VERIFIED in working memory comes to look like a claim that went
through admission.

The **repeat gate** runs before a work item is issued: an attempt matching a
recorded failure on method and statement stops the campaign before any budget is
spent. `references/soc_memory.md` carries the rest — decisions and rewards,
consolidation that says what it dropped, and why the failure ledger and working
memory both record a failure without being redundant.

## 5.2 The loop, end to end

`scripts/campaign.py` drives one campaign through every packet the frame defines:

```
resolve pack -> freeze -> init state -> work item -> adapter -> receipt
-> result -> [review] -> admission -> reducer -> state -> report
```

Before it existed, `frame-work-item-v1`, `frame-result-v1`, and
`frame-review-v1` were schemas with no writer — specifications nothing had ever
produced or consumed — and the gap between the adapter (which emits a receipt)
and the reducer (which consumes an admission) was filled by hand every time it
was crossed. Running the loop found real defects in one afternoon that years of
reading would not have: the adapter's **calling convention had never been
stated**, and the packs had quietly diverged to the point where the frame could
not invoke one of them at all.

**It deliberately cannot reach `VERIFIED`.** One process cannot be both producer
and independent reviewer, and the frame already refuses a self-certified fidelity
record. So an automatic run tops out at `CHECKED_BOUNDED` and the report says
why. That is not a limitation to route around — it is the architecture holding
under the exact condition it was designed for.

Failure is a first-class path: a failing adapter is recorded in the ledger, the
threshold is evaluated, and the report says whether the next move is another
attempt or the deep-attack role. The self-test exercises both, because a harness
tested only on the success path has not been tested against the case it exists
for.

## 6. Governance

These rules exist to stop the frame from quietly re-accumulating domain-specific
assumptions until "domain-agnostic frame" is a fiction.

1. **One canonical location.** No second, independently-editable copy of frame
   code. Duplicated copies drift, and then a sync silently destroys whichever
   copy loses.
2. **Reference-direction enforcement.** Frame files must never reference
   `domains/<name>/` or carry field-specific vocabulary. This is mechanically
   checked by `scripts/check_frame_purity.py`, which is the single cheapest
   guardrail against contract erosion. Run it on every change.
3. **The contract is the only extension point.** If adding a domain seems to
   require a new frame capability, ask first: is this genuinely domain-neutral,
   or is it this domain's verification adapter in disguise? A genuinely neutral
   need becomes a new contract item and a version bump (rule 6), never an
   in-place widening.
4. **No fourth role without a structural reason** (§2).
5. **Per-pack conformance, plus one frame suite.** The frame tests against
   `domains/_mock/` — a fixture, not a field — so it can prove it has no hidden
   domain dependency. Each pack separately proves it implements all five
   contract items. A frame change ships only once the purity check and the
   conformance check are green **across every registered pack**, not just the
   one being worked on.
6. **Versioned contract.** A contract change is a deliberate version bump, not
   an implicit drift because one pack needed a workaround. Each pack declares
   the version it implements and the frame never infers it; the validator picks
   the schema from that declaration, so both versions stay checkable.
7. **Documentation lives with the frame.** This file describes the layers, the
   invariants, and the contract. A domain pack carries only its own
   instantiation of the contract, not a re-explanation of the architecture.
8. **Cruft has no home in the frame tree.** Build artifacts and generated files
   are gitignored, not tracked; their accumulation obscures real structural
   drift in diffs.
9. **An optimization proves it pays.** Any performance mechanism ships with an
   ablation: cheap baseline first, full path only on what the baseline left
   open, regressions empty. And learned or heuristic ordering may **reorder
   only** — with the model absent, behavior must be identical. That keeps every
   ranking addition safe by construction: it can waste time, never change an
   outcome.

## 7. Adding a domain

Domain packs live in `domains/` and are kept off to the side of the frame
deliberately. To add one, see `references/domain_pack_contract.md` §7 — write
the manifest, implement the adapter, declare the refute-attempt gate, the
escalation threshold, and the selection block, then run:

```bash
python3 scripts/validate_domain_pack.py domains/<name>/domain.json
python3 scripts/resolve_domain.py --self-test
python3 scripts/check_frame_purity.py
```

All three must pass before the pack is registered. The middle one is the easy
step to skip and the expensive one to skip: a pack that validates perfectly and
resolves for nothing has been added to the tree and not to the system.
