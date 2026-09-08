# Witsoc Architecture

Witsoc is a domain-agnostic discovery frame: a disciplined
propose → verify → deepen loop, with the field-specific machinery factored out
into swappable domain packs.

The frame is deliberately small. Its predecessor grew to hundreds of scripts and
reference documents with the field-specific parts tangled through the shared
layer, which is the failure this rebuild exists to avoid. Every file here earns
its place or does not exist.

## Runtime v5: typed depth on demand

The operational architecture is now a narrow path over the existing evidence
machinery:

```
sticky activation -> research IR -> typed capability path -> role capsule
                  -> bounded episode or round -> operator -> reducer admission
```

The shell routes and loads; it does no research. A canonical type registry
closes cross-layer packet contracts. The kernel owns one frozen target, a
domain-neutral frontier projection, event replay, and at most one pending
episode or independent round. The capability graph computes a typed, costed
path, and sealed role capsules carry only the current frontier view. Domain
operators load deep doctrine on demand. The reducer remains the only status
authority; the kernel imports its decisions and cannot manufacture one.

The machine-readable ownership map is
`references/runtime_architecture.json`; its deterministic budget summary is
`references/runtime_contracts.json`. Generic packet identities live in
`contracts/type-registry.json`. Compatibility wrappers remain while new
integrations enter through `scripts/witsoc.sh`.

The discovery loop makes the return edge explicit. Explorer issues one episode
for coupled work or a two-to-eight attack round only when actors, routes,
failure domains, and resources are independent against one immutable snapshot.
Researchers return deltas and cannot select successors. Explorer performs a
conflict-visible merge, recomputes the frontier, and only then decides whether
another move is justified. A renamed route remains blocked by its structural
fingerprint; revival requires a changed axis and evidence.

**Publication.** This directory is the candidate source tree. Release policy
projects the runtime subset, verifies it, and atomically publishes that subset
to the single active `witsoc` location. The active tree is never hand-merged;
the generated contract and release manifest make drift visible before sync.

> **Paths in this document are relative to the skill root.** An agent working
> from a worktree resolves it first — `SKILL.md` has the one-liner — and the
> four shell entry points under `scripts/` are the supported surface.

## Path checks

Component checks test one script. Every defect that survived four green suites
and twenty of twenty planted regressions lived in a SEAM: a receipt field the
adapter never wrote and the reducer read as absent, a placeholder the renderer
counted as filled, a memory store the revision could not reach.

`witsoc_core.tools.check_paths` walks whole campaigns — claim in, admission decision
out — and asserts the outcome. The cases are DECLARED BY THE PACK, in
`<pack>/evals/path/cases.json`, and walked by the frame: a case names the
environment variables it needs and the frame checks they resolve without
learning what they mean. That keeps the walk on the frame side of the contract
line and the field knowledge on the pack side — the first version of this
checker named one field's backend directly and `check_frame_purity.py` rejected
it, which is the rule working on the person who wrote the rule.

Loops that are procedures over a pack's own pipeline are not that shape, and
they live in the pack: `<pack>/evals/path/run_*.py`, run by the pack's suite.

Cases are written in pairs where possible: the artifact that must be admitted
and the one that must not, differing only in what the seam is supposed to
notice. A suite of refusals proves only that a gate can say no. Cases whose
requirements are absent report NOT_RUN, and NOT_RUN is never counted as a pass.

The bar is the same one `check_checkers.py` holds the checkers to: remove a fix
and a path case must go red.


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
   contract · failure ladder · resource governor · schedule planner · reuse cache
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

**The contract line is exactly six items.** A pack supplies these; the frame
supplies everything else and never reaches past them:

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

**And a pack carries more than six things.** Saying "these six and nothing else"
was false of every pack ever written here: a claim-class taxonomy, a unit
taxonomy, a confounder catalogue, a technique list — all real structure, all
sitting outside the contract where no validator could see it. Undeclared
structure is not less structure; it is structure nobody can check.

So contract v3 adds `reference_data`: the tables a pack reasons from, each with
its purpose, its readers, and optionally the calibration that measures whether
it is still right. This does **not** make the frame read those tables — the
frame still never reaches past the contract line. It makes their existence and
their absence checkable, and a declared table that is missing now fails
validation, where an undeclared one used to fail a run.

v3 also adds `script` to each tier and gate: which file implements it. In v2
that binding lived inside each pack's own adapter, where nothing could check it,
so a rename broke the wiring silently and a gate that was never dispatched read
in the receipt exactly like a gate that passed.

The contract is at version `3`. Version 1 had been extended in place — backend
audit fields, per-tier ceilings, the corpus slot, status refinements — which was
defensible only while no pack outside this repository implemented it. Item 6 was
the first change made as a deliberate bump (governance rule 6), and v3 is the
second: v1 and v2 packs still validate and still work — a v1 pack is simply
invisible to automatic resolution, which `validate_domain_pack.py` states when
it validates one.

## 1.1 Resolution: how a pack is chosen

A pack that is never loaded is indistinguishable from a pack nobody wrote. This
is the failure mode that matters most in the layering above, because it is
silent: the roles still run, still produce, and still sound confident — they
just do it with no field doctrine, no adapter, and therefore no way to be told
they are wrong.

So resolution is a mechanism, not an instruction. **Before any other work**, a
run resolves the pack:

```bash
witsoc-tool resolve-domain --statement "<the problem, verbatim>"
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

## 1.2 Distribution boundary

The development tree keeps complete domain sources under `domains/`; the
synchronized runtime does not ship them. It carries only the generated
`contracts/domain-packages.json` selection and integrity index plus the loader.
The maths source builds the `witsoc` distribution and the bio source builds
`witsoc-bio`. Distribution names are independent of the installed skill name.

Routing has a two-step domain decision. It first scores the compact registry.
For every selected but dormant domain, the loader:

1. acquires a per-domain installation lock;
2. installs the exact pinned wheel with no dependencies and no source build, or
   downloads the universal wheel with curl and verifies PyPI's SHA256;
3. checks the package core API, domain contract version, full file manifest,
   and registry-pinned payload digest;
4. atomically materializes the verified payload under the active skill's
   `domains/<name>/` path; and
5. runs ordinary resolution and capability planning against those bytes.

This compatibility materialization keeps existing Plane locators and commands
stable without putting domain payloads in the original orchestrator release.
The cache is authoritative, activation is reproducible, and the runtime release
manifest deliberately ignores activated payloads. Installation and activation
are explicit pre-task side effects in the route receipt. Any unavailable wheel,
version mismatch, incompatible API, or digest mismatch produces
`UNRESOLVABLE`; generic orchestration is not a fallback.

**The ceiling is carried, not just printed.** Resolution reports
`max_admissible_status` — the strongest status the resolved pack's tiers can
support, lowered further if the pack is provisional. Pass it to the reducer when
the campaign is created:

```bash
witsoc-tool reducer init --claim <claim.json> --out state.json \
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

**And that number measures self-consistency, which is why there is a second
one.** The same hand writes a pack's signals and its examples, so a perfect
score there shows a fit to those examples and nothing else. A pack may declare
`held_out_cases`: statements phrased by people who did not know the terms —
statements lifted from a field's own reference library, claims written for the
predecessor system before this pack existed. The self-test reports both, separately, and
labels which is which. A pack with no held-out set is not failing; it is
unmeasured, and the output says so rather than implying otherwise.

The gap between the two numbers is the finding. In-house resolution scores 30/30
and held-out scores 78%; the bio pack's claim classifier scores 12/12 in-house
and 71% on a held-out half. Neither held-out number is good enough to stop
looking at, and both are the only figures of the four that mean anything.

**When nothing matches.** NO_MATCH is not a refusal and not a dead end. The
orchestrator improvises a pack from the closest registered one:

```bash
witsoc-tool scaffold-domain --domain <name> --from <closest> \
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

**And it runs for one artifact.** `campaign.py artifact --also <pack>:<tier>:<artifact>` engages a
second pack on the same frozen claim: its adapter runs, a `fail` from ANY
engaged pack returns `BLOCKED_BY_PAIR` whatever the others said, and the ceiling
becomes the weakest of the engaged tiers. Until that existed, resolution could
report `AMBIGUOUS` and this section could state the rules, and the loop took a
single `--domain` — so "a fatal objection from any engaged pack blocks
admission" was a rule about a situation the system could not reach. Both
directions are in the campaign self-test, because a rule that blocks every
paired claim enforces nothing.

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
is a required field in the pack manifest schema, so a pack
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

**It is now counted rather than described.** `witsoc_core.tools.failure_ledger` records
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

## 5.1 Performance: the graph is the schedule PLAN

**The frame plans; the orchestrator runs.** This section used to read as though
the frame did the scheduling, which contradicts the boundary stated in
`SKILL.md`: providers, budgets, fanout, ordering, sessions, workers, retries and
cancellation are the orchestrator's. The split is real and it is worth being
exact about, because both halves are load-bearing:

| The frame | The orchestrator |
|---|---|
| reads the dependency graph and says which claims are ready, which are racing, which are blocked and on what | starts, orders, retries and cancels the work |
| costs the wave against the governor and refuses one that exceeds the budget | owns the workers that would have spent it |
| `scripts/schedule.py plan --state <s> [--governor <g>]` | consumes the plan and may ignore it |

The plan itself is one structure read twice. The claim graph's dependency
relations decide closure *and* concurrency:

- an **OR** group is a **race** — siblings dispatch together, the first pass
  makes the rest pointless;
- an **AND** group is concurrent **fan-out** over every ready child, looped
  until nothing is ready;
- a cancelled sibling keeps its status and gains `superseded_by`.

That last point was wrong here for as long as this section existed. It said a
cancelled sibling *is* `SUPERSEDED`, as though losing a race were a status —
and the frame's own rule is that process states never appear as epistemic ones.
Losing a race teaches nothing about a claim. So the status does not move, the
cancellation is recorded as the scheduling fact it is, and the practical payoff
is revival: an `OPEN` claim carrying an annotation is reschedulable the moment
the winner fails, where a status would have needed a transition to come back.

Running an OR group in sequence pays the full cost of every approach that was
never going to win. That is the largest piece of performance the predecessor
left unclaimed — it had the closure semantics and never turned them into a
plan.

The no-merge invariant (§2) is also a scheduling argument. The three roles have
different cost shapes: Explorer is cheap and on everything's critical path,
Generator is high-volume and parallel, Researcher is expensive and serialized on
one obstruction. One engine cannot be scheduled three ways.

### The reducer

One piece of frame code is the **only** thing that may move a status
(`witsoc_core.tools.reducer`, state shape in `schemas/frame-state-v1.schema.json`).

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

**Identity is attested, not declared.** This was the deepest hole in the design
and the document did not admit it. `decided_by_role`, `emitted_by`,
`reviewer_role` and `method_family` are *fields in packets*, and one agent may
write all of them. The reducer compared the labels. So the founding premise —
an agent cannot be trusted to self-report correctness — was enforced rigorously
for **evidence** and not at all for **identity**, which is the thing that makes
"a role may never accept its own work" mean anything at all.

The frame cannot verify identity by itself, and that is a real dependency rather
than an oversight: sessions, workers and processes belong to the orchestrator.
Stating the dependency is the first half of the fix, because an unstated one is
indistinguishable from a guarantee.

The second half is refusing to treat an unattested separation as a demonstrated
one. Every packet may carry an `actor` block — an opaque `actor_id` the
orchestrator assigns, and `attested_by`, either `orchestrator` or `self`:

- two packets sharing an `actor_id` are the **same actor** whatever their role
  labels say, and the pairs that must differ are refused outright;
- `attested_by: "self"`, or no actor block at all, means nobody outside the run
  vouched. Independence is then `NOT_RUN` — not `FAIL`, because nothing was
  shown to be wrong, and not `PASS`, because nothing was shown at all.

The consequence is deliberate: **without orchestrator attestation a run cannot
reach `CONDITIONAL` or `VERIFIED`**, because those are exactly the statuses whose
meaning depends on someone other than the producer agreeing. That is the same
ceiling `campaign.py` reaches from the other direction, arrived at from the
identity side instead of the evidence side, and the two agreeing is a good sign
about both.

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
| an admitting actor that IS the producing actor | the role labels differ and the actor does not; a label is not a fact |
| a reviewing actor that IS the producing actor | self-review wearing a second role label |
| an unattested chain, for any status needing independence | nobody outside the run vouched that these were different actors, and an unattested separation is not a demonstrated one |
| a review whose `producer_ref` is not the supplied result | an unbound review discharges independence for work it never saw |
| a reviewer sharing the producer's role **and** method family | two checks sharing a failure domain are one check; this fails closed when either side declines to say which family it used |
| a stale `base_revision` | the state moved underneath a long-running attempt, so its conclusion may rest on a premise since demoted. This bites hardest on the role that runs longest. |
| a broken `payload_sha256` | the packet was edited after it was sealed |
| a result not bound to its work item by seal | the dispatch constraints it answered cannot be checked |
| dependency closure unmet | AND needs every dependency accepted, OR needs one |
| a status above the claim's ceiling | bounded evidence does not become universal by accumulating admissions |
| a delta adding a claim at anything but `OPEN` | otherwise a pre-established conclusion enters as a side effect |
| `independent_review: PASS` with no distinct reviewer | self-review is not review |

`witsoc_core.tools.reducer_selftest` is what makes that checkable. Eighteen adversarial
admissions — the first of them the forged-checks case that motivated all of
this — must each be refused **for the stated reason**, and two honest chains
must be accepted. The
accept cases matter as much as the refusals: a reducer that refuses everything
enforces nothing, it just stops.

Every applied admission produces a new content-addressed revision naming its
predecessor, so a run is replayable rather than merely logged — and re-applying
the same admission is refused, because its base no longer matches.

Two further shared services support the schedule and are frame-owned:

- a **resource governor** (`witsoc_core.tools.governor`) — the single place that
  answers "may another expensive worker start", and the only thing in the frame
  that can stop a run on cost. Saturation **queues**, because a refused
  expensive worker and a delayed one have very different consequences for a
  campaign. An exhausted budget **refuses**, because a ceiling that queues is
  not a ceiling. Until this existed a run could be stopped by failures and by
  nothing else — in a design whose Researcher is explicitly "allowed to run long
  and expensive on a single blocker", which is exactly the role that needs a
  number rather than a temperament. A run with no budget set is reported as
  having no ceiling, never as having a large one;
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

`witsoc_core.tools.campaign` drives one campaign through every packet the frame defines:

```
resolve pack -> freeze -> init state -> work item
   -> ready? -> affordable? -> adapter -> receipt -> charge
   -> result -> [review] -> admission -> reducer -> state -> report
```

**Two of those questions used to be answerable and unasked.** The planner and
the governor existed as libraries nothing in the runtime path called — present,
tested, and doing nothing, which is the same failure as a component named in an
architecture and absent from the tree, one layer in. Now:

- **ready?** the planner reads the dependency graph. A claim whose dependencies
  are undischarged produces evidence that cannot close anything, and the
  reducer would refuse the admission at the end — after the tier had been paid
  for. Asking first is the whole saving.
- **affordable?** with `--governor`, the tier's cost is charged against a
  declared ceiling and a run that exceeds it stops with `STOPPED_ON_BUDGET`.
  Without one, nothing stops the run on cost, and the report says which of the
  two happened rather than leaving a reader to assume a limit existed.
- **who is acting?** `--producer-actor` and `--admitter-actor` carry the
  orchestrator's attestation into the chain. Supplied and distinct, the reducer
  can grant a status that depends on independence. Supplied and identical, it
  refuses — the labels differ and the actor does not. Absent, the chain is
  self-attested and tops out at `CHECKED_BOUNDED`, which is where this loop
  already stopped for a separate reason.

Before it existed, `frame-work-item-v1`, `frame-result-v1`, and
`frame-review-v1` were schemas with no writer — specifications nothing had ever
produced or consumed — and the gap between the adapter (which emits a receipt)
and the reducer (which consumes an admission) was filled by hand every time it
was crossed. Running the loop found real defects in one afternoon that years of
reading would not have: the adapter's **calling convention had never been
stated**, and the packs had quietly diverged to the point where the frame could
not invoke one of them at all.

**The outcome says which of two very different things happened.** `PARTIAL`
used to mean both "the root is established as strongly as this pack can manage"
and "a sub-claim closed and the target is still open" — situations calling for
opposite next moves, reported with the same word, so a campaign that had done
everything available to it was indistinguishable from one that had barely
started. `CLOSED` is now the first of those: the root admitted AT the campaign
ceiling, with its own status saying how strong that is. A closed campaign under
a provisional pack is closed at `SKETCH`, and that is a real result.

**It deliberately cannot reach `VERIFIED`.** One process cannot be both producer
and independent reviewer, and the frame already refuses a self-certified fidelity
record. So an automatic run tops out at `CHECKED_BOUNDED` and the report says
why. That is not a limitation to route around — it is the architecture holding
under the exact condition it was designed for.

The self-test covers all of it: a blocked claim, an exhausted budget, a budget
actually charged rather than merely consulted, one process wearing two role
labels being refused, and two attested actors closing the loop. A check that
refuses every attested chain enforces nothing, so the last of those matters as
much as the fourth.

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
   checked by `witsoc_core.tools.check_frame_purity`, which is the single cheapest
   guardrail against contract erosion. Run it on every change.
3. **The contract is the only extension point.** If adding a domain seems to
   require a new frame capability, ask first: is this genuinely domain-neutral,
   or is it this domain's verification adapter in disguise? A genuinely neutral
   need becomes a new contract item and a version bump (rule 6), never an
   in-place widening.
4. **No fourth role without a structural reason** (§2).
5. **Per-pack conformance, plus one frame suite.** The frame tests against
   `domains/_mock/` — a fixture, not a field — so it can prove it has no hidden
   domain dependency. Each pack separately proves it implements all six
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
witsoc-tool validate-domain-pack domains/<name>/domain.json
witsoc-tool resolve-domain --self-test
witsoc-tool check-frame-purity
witsoc-tool package-domains registry
witsoc-tool package-domains build
```

All checks must pass before the pack is registered. Installable packs also need
a project under `packages/` and a regenerated compact registry. Resolution is the easy
step to skip and the expensive one to skip: a pack that validates perfectly and
resolves for nothing has been added to the tree and not to the system.
10. **Measure generalization separately from consistency.** Any scorer the frame
   or a pack relies on — resolution, classification, ranking — is calibrated
   against cases somebody wrote. Where possible it is ALSO run against material
   written without knowledge of it, and the two numbers are reported apart.
   Tuning against a held-out set turns it into an in-house set silently, so a
   set used for fixing is split, the used half is marked burned, and the
   replacement comes from outside again.
11. **The contract line is regression-tested from both sides.** Static checks
   read a manifest and the files it points at; they cannot tell whether the
   frame can still CALL a pack, and they cannot tell whether today's boundary
   is yesterday's. `witsoc_core.tools.check_bridge` invokes every pack the way
   `campaign.py` does, compares the observable surface against a recorded
   baseline, and checks the documented calling convention against the argv the
   frame actually builds. A boundary tested from one side is not tested: the
   calling convention went unstated through two contract versions until a pack
   turned out to be unreachable, and every pack's own self-test was green
   throughout, because each called itself the way it happened to expect.
12. **A check proves it pays, too.** Rule 9 asks an optimization to justify its
    cost and nothing asked the same of a check, so a suite grows one justified
    check at a time and becomes unrunnable the same way. A new check states the
    regression it catches and is demonstrated against a **planted** one — a
    check nobody has watched fail is a check nobody knows works, and two of the
    three bridge layers only became correct because a planted regression showed
    the first version missing it. `check.sh` times every step, marks anything
    slower than ten seconds, and prints the suite's total, because a cost nobody
    measures cannot be argued about. The rule has already applied to itself: the
    bridge check spent 43 of the suite's 55 seconds discovering an unavailable
    backend twice, and asking the cheap question first brought it to 11 — while
    a first attempt at that saving skipped three tiers of real coverage, which
    is the worse bargain and the reason the rule says *prove*.
