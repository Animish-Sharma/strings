# What was done, and what it is worth

A record of one working session on `witsoc-2` and the delivery fixes that made it
reachable. Written to be checkable: every number below came from a command, and
the commands are named so they can be re-run.

Nothing in `frontend/` or `backend/` was touched. Every fix adapted the skill to
the runtime rather than the runtime to the skill.

---

## 1. The starting state

`witsoc-2` was complete, tested, and **entirely unshipped**: `git ls-files` on it
returned zero. It could not sync, could not be discovered by `GET /skills`, and
no agent could fetch it. None of its correctness was reachable by anyone.

Three further delivery faults, each of which would have survived indefinitely
because nothing looked for them:

| Fault | Consequence |
|---|---|
| `compatibility` frontmatter said "documentation plus two stdlib-only Python checks" | It was 96 scripts. A wrong line on the discovery surface is worse than a missing one |
| Nine `python3 scripts/...` commands in SKILL.md | An agent's working directory is a worktree, not the checkout. All nine find nothing |
| No `.sh` entry point; 0 of 96 scripts executable | The runtime execs skills as shell scripts and chmods `**/*.sh`. The skill had no door the orchestrator knew how to open |

## 2. Delivery, fixed

- **Committed.** 310 files now tracked across two commits.
- **Four shell entry points** — `resolve.sh`, `campaign.sh`, `scaffold.sh`,
  `check.sh` — in the house style of `machine-use` and `sandbox-use`, each
  resolving the skill root from `$0` so the caller's directory is irrelevant.
- **SKILL.md resolves its own path** through the plane, as the agent spec
  documents.
- **The compatibility line is now true**, and points at the per-tier
  `availability_check` mechanism rather than naming one pack's toolchain — the
  purity check caught the first attempt doing exactly that.
- **`.gitignore`**, because this repository is cloned onto every client machine.

`check.sh` found a real gap on its first run: the fixture pack — the one whose
whole job is to prove the frame carries no hidden domain dependency — had no
`--self-test`, so it had never demonstrated it rejects anything.

## 3. The improvement pass

Roughly forty changes across the frame, the maths pack, and the bio pack. What
follows is not the list; it is the findings, because the findings are the part
worth reading.

### The pattern that kept recurring

**A declaration nobody checked against its content.** It appeared six times, in
six unrelated places, and every instance was silent:

1. The reducer accepted `--receipt` and never opened it. `checks: {"refute_attempt": "PASS"}`
   was an assertion by whoever wrote the admission — the enforcement chain ended
   in a self-report at exactly the point self-reports are what it guards against.
2. `bio` and `archival` declared `extends: frame-claim-v1` while calling the
   frame's `exact_statement` field `statement`. **Every campaign state recorded
   an empty statement.** The chain ran, the status moved, the claim text was gone.
3. No pack carried `frozen_conditions` under the frame's key, so the frame's
   target-protection machinery could not see what any pack was protecting.
4. `_mock` declared a blocking gate its adapter never named.
5. Manifests declared a corpus, an escalation threshold, and `prefix_reuse`, all
   read by nothing.
6. `target_protection.py` skipped its comparison entirely whenever a claim lacked
   one optional field — and reported PASS. Every fixture in the pack carried that
   field. No claim from outside it did.

The response was the same each time: **check the content, not the declaration.**
`check_contract_shapes.py` validates the claims a pack actually ships rather than
comparing `required` lists; the reducer derives each acceptance condition from the
sealed receipt and refuses any disagreement with what was asserted.

### What external evaluation was worth

Two suites grade against material this pack did not write.

**maths** samples real theorem statements from an installed library and asks
whether the gates can tell a faithful restatement from a mutated one.

```
before   faithful accepted 12/12    mutations caught   0/35
after    faithful accepted 10/10    mutations caught  29/29
```

Zero of thirty-five. A blocking gate that runs at every tier had been a no-op on
every claim not authored inside the pack. That single number is the argument for
external evaluation, and nothing self-authored could have produced it.

**bio** grades against a regression family written for the predecessor system by
someone else. First run 8/10; both disagreements were real. Their `required_flags`
are report conditions, and the class table had population claims declaring
independence as *design evidence* only, never as something the report must state.
Added. Now **10/10**.

### Errors this pass made, and how they were caught

Worth recording, because a report listing only successes is describing something
that did not happen.

- **A paired-design bootstrap.** The new confidence interval resampled arms
  independently on a matched design and reported an interval spanning zero for an
  effect the same data put at p = 0.03. The same error class had already been
  caught once in `power.py`; it recurred because the two were written days apart
  and the second did not look at the first.
- **A NaN sign flip.** The multiverse applied `log1p` to a signed endpoint,
  produced NaN, and reported SPECIFICATION_DEPENDENT on data whose effect never
  moved — the worst possible error for a check whose job is to say whether the
  analysis is doing the work. An alternative that is not applicable to the data is
  not an alternative.
- **Seventeen false positives of pure prose.** The doc-link checker read
  `` `produce.py` `` in a sentence as a path. A checker that fires on ordinary
  writing gets switched off, and then it catches nothing.
- **A field's file extension in a frame file.** The same checker enumerated
  `.lean` among the extensions it recognized. The purity check caught it; the fix
  was to match any extension, which removed the field knowledge rather than
  exempting it.
- **A silent id parse.** Lemma-pool harvesting read plain-text output as JSON, got
  no id, and recorded three facts the pool never learned — as PROPOSED, forever.

### The optimization that was measured and rejected

Governance rule 9 says an optimization proves it pays. The measurement:

```
import the library, nothing else      5.16s  4.68s  5.05s
import + a three-obligation proof     5.08s  5.08s  5.10s
```

The proof is under 2% of the cost. Prefix reuse is worth roughly fifty times on a
repair loop, and a REPL delivered eighty. It was **rejected**: inspecting its
messages rather than its timings showed `Unknown identifier trivial` after a
reported successful import. Every command had run against an empty environment
while returning success-shaped JSON.

That is the worst failure mode available to a verification backend — it does not
fail, it succeeds emptily — and the numbers looked excellent the whole way.
`domains/maths/doctrine/kernel_economics.md` records it, and the manifest now says
`supported: false` with the reason and the gate any future fast path must clear.

## 4. What the packs can do now that they could not

**maths** could refuse an artifact in nine ways and could not make one. The
production chain existed — `generate_wit`, `wit_to_lean`, `repair_cycle` — and
nothing composed it, and no blueprint with the six sections `generate_wit`
demands existed anywhere in the pack. The generator had never been fed.

```
blueprint -> WIT -> structural -> Lean -> kernel -> admission
```

Eleven blueprints: six reach a clean kernel pass, one against a real Mathlib
checkout, one honestly incomplete, four refused before anything is produced. The
loop now refutes before it proves, checks that cited results exist before paying
for the expensive tier, compounds proven steps into a pool, and answers a failure
with a written revision request naming the step and the axis.

**bio** had zero scripts that produced anything — seventeen scripts, all gates and
tiers. It now sizes a design prospectively by simulating the test that will
actually run, computes multiplicity with selection inflation, runs a
specification multiverse, computes the cheap confounder diagnostics from the
metadata instead of asking for them, proposes the negative-control split, and
generates the report from the receipt so the prose and the check cannot disagree.

## 4b. Working memory, added as a frame component

The frame held campaign state and cross-run memory and nothing between them, so
a long run had no compact record of what it was pursuing or what it had ruled
out. `frame-soc-v1` fills that, adapted from the predecessor's `.soc` file with
four changes.

**Tiers are frame statuses.** The predecessor invented VERIFIED / CHECKED /
CONJECTURAL alongside the status lattice — two ladders with different rungs and
no rule connecting them, so an insight marked VERIFIED in working memory read
like a claim that had been through admission. An insight above CONJECTURE must
now name its evidence and the tool refuses otherwise.

**"Attention is never evidence" is mechanical.** The schema closes the crude
route: an insight id is not sixty-four hex characters. The reducer closes the
careful one — hand it `--soc` and it refuses any admission whose evidence hashes
to an entry in the file. Hashing a hunch does not change what it is.

**Bound to the target**, so a memory cannot drift onto the next problem and
carry its conclusions there. **Consolidation says what it dropped**, because a
memory that compacts silently leaves a reader unable to tell forgetting from
never-knowing.

The repeat gate runs before a work item is issued and, on a match, escalates —
reaching the same conclusion the failure threshold would, before any budget is
spent rather than after. The ledger holds a normalized signature; working memory
holds the reason and the revival condition. Neither is redundant: a count cannot
tell you what to change, and a reason cannot fire a threshold.

## 4c. A campaign on a target nobody chose

The gap named at the end of the last report was that no campaign had ever run
against a problem someone else picked. One has now.

A target was drawn at random from an installed library — a seeded sample over
the source tree, filtered only for length. The first attempt proposed induction
with the standard recurrence and the kernel refused it (`omega could not prove
the goal`). The failure was classified, the axis named, a revision request
written, and working memory recorded it so the same blueprint is now refused
before anything is produced. The revision declared the recurrence as a premise,
the pre-flight resolved it, the kernel elaborated clean, five blocking gates
passed including a real axiom audit, and with an independent review it was
admitted `VERIFIED`.

`domains/maths/evals/drawn/` holds both attempts and is reproducible.

What it is evidence of: the loop closes on material the pipeline did not choose.
What it is not: evidence the system can prove things. The second attempt cites a
library result rather than establishing it. **The interesting number is that the
first attempt failed and the failure was informative** — a named step, a named
axis, and an edit, rather than a stack trace and a shrug.

## 4d. The role doctrine pass

The six role doctrines — Explorer, Generator, Researcher in each of the maths
and bio packs — were graded as instruments and came back 6.0 to 7.5. One finding
dominated and it was structural rather than editorial.

**Five of the six named zero runnable commands.** The maths pack held thirty
scripts and its three role documents named exactly one. A Researcher told to
"search, minimize, certify a counterexample" had no pointer to
`domains/maths/scripts/counterexample.py`, so the honest reading of the doctrine was that no such tool
existed. The instructions were right and unreachable.

**Two instructions were worse than unreachable — they were wrong.**

- The maths Generator doctrine opened its check loop with "LSP/REPL per-command
  checking — use it by default." The pack had measured that REPL, found it
  returned success-shaped JSON against an empty environment, and rejected it in
  writing. Three documents still advertised it. Nothing was wrong with the prose;
  the world had moved and the prose had not.
- `domains/bio/scripts/gates/confounder_sweep.py` read `entry["result"]` — a sentence the producer wrote
  about the producer's own work — and classified it by keyword. Twelve
  alternative explanations were self-reported, in the pack's most important
  scientific gate, while the frame's reducer had already closed exactly this
  hole by deriving checks instead of reading them.

### What was built

`scripts/check_doctrine_commands.py` is the durable half: every command in every
doctrine must name a file that exists and answer `--help` with exit 0, and every
entry-point script must be reachable from either a doctrine or the manifest.
Both directions matter. The first kills dead instructions; the second surfaces
orphaned machinery. It found 33 problems on its first run, 27 of which were the
checker's own fault — gates are declared by NAME in a manifest and it was
reading for PATHS. The fix was not a better heuristic but a contract change:
tiers and gates now carry a `script` field, so the binding between a declared
name and the file that runs it is declared rather than conventional.

`domains/bio/scripts/expression_diagnostics.py` computes the four Durbin attacks that were
prose: generic response against cell-cycle and stress signatures, the exact
composition-versus-expression decomposition, ambient RNA estimated from the
droplets QC discards, and cross-context sign reversal. Every score runs through
`domains/bio/scripts/counts.py`'s `score_set` — the same expression-matched background that computes the
endpoint — because comparing a claimed signature against a stress signature is
only meaningful when both numbers were built the same way.

The sweep gate now takes computed verdicts over asserted ones and **fails a
bundle that contradicts its own pinned diagnostics**. Abstention is handled
separately and deliberately: `not_computable` does not overrule an author who
settled the question elsewhere, because treating an abstention as a refutation
would teach people to withhold diagnostics.

`domains/bio/scripts/classify_claim.py` closes the bio Explorer's largest gap. The class
sets the ceiling and was assigned by eye, while the far less consequential
choice of which PACK to load had a scorer, an explain mode, and a calibration
set. It returns two answers — the claimed class from the statement's words, the
supportable class from the metadata — and the gap between them is the
denominator finding, arriving at triage instead of after the analysis is paid
for. 12/12 on its calibration set.

`domains/maths/scripts/tactic_search.py` gives the maths Generator a way to CLOSE an
authorized leaf. Fourteen tactics go into one file as separate `example`s and
elaborate once, so a portfolio costs one import rather than fourteen — the
pack's own measured economics applied to its own machinery.

The `bounded` tier searched one integer variable. Most small-case questions are
about a pair, so a role told to "check small cases first" had to hand-write a
harness and usually did not. It now enumerates a product of ranges, with a
budget stop that reports UNKNOWN rather than passing.

### Role evals

Every eval in both packs scored an ARTIFACT through a gate. None could tell
whether a role doctrine had regressed — the doctrine could rot while every gate
still passed. `evals/roles/` scores decisions: 17 in bio, 11 in maths.

The constraint is the useful part. A role eval is writable exactly where the
judgement has machinery under it, so writing them forces the wiring, and the
absence of a case is a finding about which decisions are still made by eye.

They found a real bug on their first run. `domains/maths/scripts/lanes.py`'s catalogue described
statement-freeze as "always first" and its ranker put it third — a disagreement
that survived because the two live in different functions and nothing compared
them. Freezing after the counterexample search means the search ran against a
statement that could still move.

### Errors this pass made

Three self-test failures in `expression_diagnostics` were the fixtures, not the
detectors: context was keyed off the same index as the arm, so every context
level held one arm and no contrast existed; the synthetic cells detected every
gene, so a droplet with twice the counts detected exactly as many and the
doublet screen had nothing to look at; and cluster membership did not affect the
score, so a pure proportion shift moved nothing.

The claim classifier matched `rat` inside `proliferation` — the third
substring-matching bug in this project. Whole-term matching then started missing
plurals, which is the same error facing the other way and harder to notice
because nothing fires. Both are fixed; the pattern is worth naming, since it has
now cost three separate debugging sessions.

`check_doctrine_commands.py` listed `.lean` among the extensions it matched, and
the frame purity checker refused it — a frame file naming a field's file types.
The fix was to match any extension, which is also more correct.

## 4e. The architecture pass

An honest grading put the architecture at 8.0 with nine specific weaknesses. All
nine are addressed; three of them turned out to be larger than the grading said.

**Identity was a string.** `decided_by_role`, `emitted_by`, `reviewer_role` and
`method_family` are fields one agent may write all of, and the reducer compared
the labels. So the founding premise — an agent cannot be trusted to self-report
— was enforced rigorously for evidence and not at all for identity, which is the
thing that makes "a role may never accept its own work" mean anything.

Packets now carry an `actor` block: an opaque orchestrator-assigned `actor_id`
and `attested_by`. Two packets sharing an actor are the same actor whatever
their labels say. An unattested chain gets `independent_review: NOT_RUN` — not
FAIL, because nothing was shown to be wrong; not PASS, because nothing was shown
at all — which puts `CONDITIONAL` and `VERIFIED` out of reach. The frame cannot
verify identity itself, and that dependency is now stated in the boundary rather
than assumed. The reducer suite went from 15 refusals to 18.

**Two named components did not exist.** The layer diagram and §5.1 listed a
resource governor as a frame-owned service and there was no such file, and the
"largest piece of performance the predecessor left unclaimed" had nothing
implementing it either. `scripts/governor.py` and `scripts/schedule.py` are
those two, and building them resolved the contradiction that came with them:
the frame **plans** — which claims are ready, which are racing, what a wave
costs — and the orchestrator **runs**. The governor is also the first thing in
the frame that can stop a run on cost; until it existed a run could be stopped
by failures and nothing else, in a design whose Researcher is explicitly allowed
to run long and expensive.

Building the planner surfaced a rule violation in the document it came from.
§5.1 said a cancelled sibling *is* `SUPERSEDED`, as though losing a race were a
status — and the frame's own rule is that process states never appear as
epistemic ones. Losing a race teaches nothing about a claim. The status now
stays put and the cancellation is an annotation, which also buys revival: an
OPEN claim with `superseded_by` is reschedulable the moment the winner fails,
where a status would have needed a transition.

**The calibration was circular, and much worse than that reads.** Resolution
scored 30/30 and the claim classifier 12/12, both against cases their own
authors wrote. Run against text written by other people — library statements,
and claims authored for the predecessor system before this pack existed — the
classifier scored **21%**.

Fixing it needed a methodology, not just better terms: tuning against a held-out
set turns it into an in-house set silently. So the external set is split by a
deterministic rule, only the tune half was ever inspected, and the reported
figure is the untouched half. Two genuine defects came out of the tune half —
`causal` sat in a strong-signal slot, so any claim using the word in its
ordinary sense was routed to the network class; and one class's vocabulary had
been written by someone who already knew the class name, so it matched
"cell-level" and not "single cells". Holdout is now **71%** against a 60% floor
set before the first run, with the tune half at 86%.

Resolution got the same treatment and the first number was **22%** — which was
my own harness bug, calling `decide()` on un-normalized text. That is exactly
what a held-out set is for, and it is worth noting that the bug survived because
every in-house number stayed green. Held-out resolution is now 78%.

This became governance rule 10: measure generalization separately from
consistency, report the two apart, and treat a set used for fixing as burned.

**The rest.** The purity check reads for field *vocabulary*, which is why it
passed a frame file enumerating pack script filenames — a structural leak, not a
lexical one. It now also refuses a frame file naming a path that exists in only
some packs, and it caught two more on its first run, one of them mine. The
contract went to v3, adding `script` bindings and `reference_data`, because "a
pack supplies six items and nothing else" was false of every pack ever written
here: taxonomies and catalogues sat outside the contract where no validator
could see them. And `check_alignment.py` compares this architecture against the
predecessor's on roles, contract items and governance rules, requiring every
difference to be declared with a reason — the alignment had been asserted in
prose for as long as both documents existed.

## 4f. The bridge, made a regression test

Everything that checked the contract line was **static**: read a manifest, open
the files it points at, compare two documents. All useful, and none of it ever
crossed the line. Nothing invoked a pack the way the frame invokes it, and
nothing compared today's boundary against yesterday's.

That gap had already cost a real failure. The adapter's calling convention went
unstated through two contract versions, the packs diverged, and one of them
could not be called by the frame at all — while every pack's own self-test stayed
green throughout, because each called itself the way it happened to expect. A
boundary tested from one side is not tested.

`scripts/check_bridge.py` closes it in three layers, and each was verified
against a planted regression rather than assumed to work:

| Layer | Catches | Planted regression |
|---|---|---|
| **live** | the frame's call is not understood | renamed `--artifact` to `--candidate` → caught |
| **surface** | the boundary changed and nobody said so | raised a tier's ceiling to `VERIFIED` → caught |
| **doc** | prose and code drifted apart | changed the documented flag → caught |

The live layer needed a second attempt, and the reason is worth keeping. An
adapter that cannot PARSE the frame's argv exits 2 — and so does one that hit an
honest error during verification. The first version accepted exit 2
unconditionally and **did not notice the renamed flag**, which is precisely the
failure the layer exists for. The two are now separated by what the rejection
says rather than by its code.

It also checks a receipt a pack actually emitted against the fields that pack's
own `receipt_format` declares. Nothing had: a pack could require a field it never
writes, and every static check would still pass because the manifest is
internally consistent.

`references/bridge_baseline.json` records the observable surface — tiers,
ceilings, gate names, receipt fields, refinements. It is generated, never hand
edited, and `--update` is the one deliberate command that changes it, so a
change to the contract line shows up in a diff as a change to the contract line
rather than as an invisible consequence of an edit elsewhere.

Two honest limits. The maths kernel tier reports NOT_RUN, because Lean cannot
run on this machine — the check says so rather than reporting green over it. And
inserting the new governance rule mid-list desynchronized the numbering with the
predecessor **for the second time this session**; the alignment checker caught it
both times, which is the system working, and additions now go at the end.

## 4g. Wiring, and a rule for checks

The 9.0 grading named one structural weakness left: `campaign.py` referenced
`governor`, `schedule` and `actor` **zero times**. The governor was enforceable
and not enforced, the planner had planned nothing real, and every campaign chain
was self-attested — the newest capabilities were exactly as inert as the
components that had been documented and absent, one layer in.

The loop now asks three questions before it works:

    ready?        the planner reads the dependency graph
    affordable?   the governor charges the tier against a declared ceiling
    who is acting? the orchestrator's attestation flows into the chain

The readiness gate needed two attempts, and the bug is worth keeping. The first
version guarded on a non-empty wave to avoid tripping when nothing was runnable
— which turns the gate off in exactly the case it exists for, because everything
blocked means an empty wave. The reducer refused the admission downstream anyway
(defence in depth working), but by then the tier had been paid for, and saving
that is the only reason to ask before rather than after.

Six new self-test cases cover it: a blocked claim, an exhausted budget, a budget
charged rather than merely consulted, one process wearing two role labels being
refused, and two attested actors closing the loop. The last matters as much as
the fourth — a check that refuses every attested chain enforces nothing.

### Governance rule 12, and it applied to itself immediately

Rule 9 asks an optimization to prove it pays; nothing asked the same of a check,
and a suite grows one justified check at a time and becomes unrunnable the same
way. So `check.sh` now times every step, marks anything over ten seconds, and
prints the total.

The first thing it caught was the bridge check: 43 of the suite's 55 seconds
spent discovering the same unavailable backend twice. Asking the cheap question
first brought the frame suite from **55s to 23s**. The first attempt at that
saving also skipped three tiers of real coverage by treating "no bundle supplied,
so I cannot tell" as "the backend is absent" — a worse bargain than the timeout
it saved, and the reason the rule says *prove* rather than *claim*.

### The answer key stopped being mine

The held-out classification test had one weakness left, stated in its own
docstring and unfixed: the claim text was external and the expected class was
mine. `externally_labelled.py` derives the answer key from the predecessor's own
`required_flags` annotations — written years before these classes existed — by a
stated rule, skipping any case whose flags are ambiguous rather than inventing a
tiebreak. **9/9.**

Two things that number is not, and the report says both: it grades the estimand,
which has four values, not the class, which has ten — so it is an easier target
than the 71% class number and the two are not comparable. And it cannot check
whether the taxonomy has the right shape. One case makes the derivation visible:
a claim resolved to `target_conditioned`, a class I would not have labelled it,
and scored correct because its estimand matches what the external annotation
says.

Every external eval now RUNS in the suite rather than being listed as advice —
they are the only numbers a pack has that it did not produce about itself, and
they were the ones nothing executed. An eval needing outside material nobody
supplied reports as needs-material, not as a failure, because reporting the
first as the second teaches people to ignore the line.

## 4h. The journey: what happened when the skill was actually used

The maths pack was pointed at modus ponens — the simplest theorem there is —
and run through its own route: resolve, freeze, falsify, produce, verify, admit.
**Nine defects surfaced in a row.** Every one of them sat on the shortest path
through the system, and every one was behind a fully green suite.

| # | Defect | Why it hid |
|---|---|---|
| 1 | a labelled `GIVEN` hypothesis could not be cited | the reference artifact declares one and never cites it |
| 2 | kernel availability meant "Mathlib is built" | no target citing nothing had ever been run |
| 3 | an `incomplete` receipt was recorded as `FAILED_ATTEMPT` | the adapter has three verdicts and the driver had two branches |
| 4 | a doctrine command passed a flag its script rejects | the checker only ran `--help` |
| 5 | fifteen more of those, once flags were checked at all | nobody had run the commands |
| 6 | three receipt fields keyed off the aggregate verdict | no run had ever been partly right |
| 7 | the pack could not resolve a statement of pure logic | every selection example was arithmetic |
| 8 | with no project, availability said `available` and the tier blocked for thirty minutes | the misconfigured path was never taken |
| 9 | a fixture needing an absent library was scored as a failure | the library was always either present or the tier skipped |

Defects 3, 6 and 9 are one mistake in three places: **a gap read as a failure.**
An `incomplete` verdict, a refutation whose tier survived while a separate gate
could not run, and a fixture whose library is absent are all "a check did not
run" — and each was recorded as "this was shown not to work". The third of those
had teeth: it fed the escalation ladder, so a deep-attack role would have been
dispatched at a formalization the kernel had already accepted.

Defect 6 is the sharpest. A kernel receipt reported
`refute_attempt.outcome: "broken"` on a run where the kernel elaborated
cleanly, because the field was computed from the receipt's aggregate verdict
rather than from the tier's own result — and `refute_attempt` is the field the
frame's reducer DERIVES the refutation check from. The reducer would have
refused a refutation that had in fact survived, and the refusal would have
looked principled. That is the frame's own derive-don't-read rule, violated one
level further in than anyone had looked.

### The systemic fix

`domains/maths/evals/journey/` walks one claim through the whole path and
asserts each step, with modus ponens as a permanent fixture. Both directions:
the correct proof must reach the kernel, and `hP` where `hPQ hP` belongs must be
refused by it. It degrades honestly — with no toolchain it walks five steps
instead of seven and says which two it did not.

It found defect 7 on its first run.

The suite now has a name for the thing it was missing. Every other check tests a
COMPONENT: does the adapter refuse bad input, is a decision right, can the frame
call a pack. All useful, all green throughout, and none of them had ever taken a
claim from a sentence to a status. A road nobody drives is not a road.

### What this says about the grade

The frame's JUDGEMENT was sound at every step of that run: nothing crashed,
nothing overstated, every refusal was correct, and the one place it erred it
erred conservatively. Its ERGONOMICS were not: reaching a kernel pass on the
simplest theorem available took roughly fifteen interventions, nine of them
repairs to the skill. A user who could not edit the skill would have been
stopped twice and finally handed `FAILED_ATTEMPT` for a theorem the kernel had
proved.

## 4i. Token cost: measured, then cut

The skill is loaded into an agent's context, so its size is a running cost paid
on every turn, not a one-time one. Measured before changing anything:

```
SKILL.md                          ~3,370 tok   (always)
resolver output                     ~482 tok   (every run)
maths doctrine, as the resolver
  told every run to load it      ~21,175 tok
per-call tool output              44–482 tok
```

Tool output turned out to be cheap. **The cost was doctrine**, and the shape of
the waste was specific: the resolver printed all three role documents plus all
thirteen shared rules as things to read *before any work begins*. An Explorer
freezing a target needs its own role doc and the freeze rule — about 2,400
tokens. It was being told to load 21,000. Roughly **82% of the doctrine load was
unused at the moment it arrived**, and it is not free: it is most of a run's
context, spent on documents for situations that had not happened.

Three changes, none of which removes any doctrine:

**Rules declare when they are needed.** Contract v3 lets a `doctrine.rules`
entry be an object with `load_when` — `freeze`, `retrieval`, `failure`,
`escalation`, `pre_admission` — and optionally which roles need it. A bare path
still means `always`, so a pack that declares nothing works and costs exactly
what it always cost.

**The resolver stages its output and takes `--role`.** A run acts as one role at
a time, and printing all three costs the other two for nothing.

**The cost is printed.** Same discipline as the rule about optimizations and the
one about checks: a cost nobody measures cannot be argued about.

```
maths explorer     ~2,361 tok now,  ~6,688 deferred     (was ~21,175)
maths generator    ~2,536 tok now,  ~6,075 deferred
maths researcher   ~2,664 tok now,  ~9,903 deferred
bio explorer       ~1,896 tok now,  ~3,607 deferred
archival explorer    ~795 tok now,  ~2,298 deferred
```

**89% off the pack doctrine an Explorer pays to start a maths run**, and nothing was
deleted — the deferred documents are printed with their trigger and their price,
and read when the trigger fires.

`check_doctrine_coverage.py` now names any rule that still loads always, because
`always` is a claim — that a role cannot take its first step without the
document — and claims should be visible.

### What it cost to make the change

The rule entry changed shape from a string to an object, and **five** separate
readers had to learn it: the validator, the resolver, the command checker, the
coverage checker, and the doc-link checker. Four were found by running the
suite; the fifth crashed it. Nothing enumerates the readers of a contract field,
which is the reason a shape change is never as local as it looks.

The bridge check then reported archival's `contract_version` moving 2 → 3 as
undeclared drift, which is the check doing its job: the change was deliberate,
so the baseline was updated deliberately, and the diff carries it.

## 4j. The rest of the levers, and a number I had wrong

Four remained after the staging work. Three were real; one was not there, and
the fourth measurement corrected a figure I had reported.

**ARCHITECTURE.md and the pack contract are maintainer documents** — 9.8k and
3.4k tokens that no RUN needs. `SKILL.md`'s load table now splits by audience
and prices every row, and says plainly that the bottom group never belongs in a
run. Two doctrine files cited `ARCHITECTURE.md` §-numbers for a one-sentence
rule, which invites loading 9.8k to find a paragraph; both now state the rule.

**A pointer at `schemas/`** invited the same trap in a worse form: the pack
manifest schema alone is 7.2k tokens, and `bridges.md` describes every packet in
1.3k. A packet is validated by running the check, not by reading the schema.

**A playbook costs 1,700–2,200 tokens** and is worth all of them on a frontier
problem and none of them on a routine one. The Lovasz doctrine now has the table
that separates the two cases, plus a section-by-section guide for when the whole
kit is more than the question needs.

**The prose trim was not available.** I had estimated 15% could come out of the
role documents without losing a rule. A duplicate-sentence pass across every
doctrine file in two packs found **one** repeated sentence — the boilerplate
opening line. The documents are about 79% prose by line, and that prose is
unique content: the reasoning attached to each rule, which is what makes doctrine
followed rather than gamed. Cutting it would have been a quality regression
bought with tokens, so it was not cut. The estimate was wrong and the
measurement said so.

### The number I had wrong

I reported an Explorer's start cost as ~2,361 tokens. That was the PACK doctrine
only. The real first-turn load is:

```
SKILL.md              ~3,700   every run, before the resolver is even called
explorer/SKILL.md     ~2,765   the generic role contract
doctrine/explorer.md  ~2,361   the field's instantiation
resolver output         ~482
                      ------
                      ~9,300
```

Worse, the resolver **never named `explorer/SKILL.md`** — every pack doctrine
opens by saying the generic role contract still applies, and the load plan
omitted it. A plan that leaves out a document the role is required to read is
not a plan, and its cost was missing from the total for exactly the same reason.
Both are fixed: the plan names it and the total includes it.

Final, honest:

```
maths explorer     ~8,826 first turn,  ~6,688 deferred
maths generator    ~8,435 first turn,  ~6,075 deferred
maths researcher   ~9,864 first turn,  ~9,903 deferred
```

The floor is close to irreducible — a route document, a role contract, and the
field's doctrine, and no run can act without all three. What the staging bought
is that the other 6–10k is now paid when its trigger fires rather than at the
start, and that the number is printed instead of guessed at.

## 4k. The last piece of friction, removed

Re-running modus ponens after the ten defects were fixed took **zero repairs** —
the whole path ran, and the only thing wrong was a probe that took sixty seconds
to report a toolchain unavailable, because it waited out a launcher's own
network timeout. A version query does no work; anything but an immediate answer
means the thing being probed is what is hanging. Bounded to five seconds, and
the message now names the fix rather than only the problem.

What remained was the fix itself: `WITSOC2_LEAN_PROJECT` had to point at a built
project, and the operator had to write it. Three lines of lakefile that everyone
must write for themselves is three lines that stops people.

`domains/maths/scripts/scaffold_lean.py` writes and builds it. One command, and
it prints the two export lines to eval. It prefers an INSTALLED toolchain binary
over the launcher on PATH — a launcher resolves a toolchain name, which can mean
a network round trip, which is how a probe comes to take a minute — and pins
whatever it found so `lake build` resolves locally too.

It is explicit about what it is not:

> an environment for the kernel tier. **NOT a library**: a target citing external
> results still needs Mathlib, and the availability probe will still refuse the
> tier without it.

A scaffold that produced an environment and let a run believe it had a library
would be worse than none, because the failure would arrive later and look like
mathematics.

### The part that matters more than the convenience

The journey test used to SKIP its three kernel assertions whenever no project
was configured — which is most machines. So the most expensive tier in the pack
was the least walked, and every defect that surfaced there surfaced by hand.

The journey now scaffolds into a temporary directory and walks them:

```
before:  5/5 steps, "the kernel steps were NOT walked here"
after:   8/8 steps, in 5 seconds, with nothing configured
```

Under governance rule 12 the check has to prove it pays: five seconds, and it
buys back three assertions on the tier where the expensive mistakes live,
everywhere rather than only on a machine somebody had prepared.

## 4l. Archival, brought to parity and given a method

Graded 6/10: it conformed, refused every known-bad dossier, and was a third of a
pack — no producer, no role evals, no journey, no held-out set, and its central
computation resting on a self-report.

### The self-report at the centre

`domains/archival/scripts/archlib.py`'s `independence` collapses the agreeing sources to distinct origins, and it
learned which sources shared an origin from the `origin` FIELD the dossier's
author wrote. Declare five distinct origins and the pack believed you — this
pack's whole argument resting on the one kind of evidence the frame says does not
count.

The discipline has a method and it is computable. **Agreement in error indicates
common descent; agreement in a correct reading indicates nothing.** Two witnesses
that both read `Constantinum` where the archetype had `Constantium` are related,
because nobody makes the same slip twice; two that both read it correctly have
said only that the word was legible.

`domains/archival/scripts/stemma.py` counts errors and nothing else. That asymmetry is the part a
similarity measure gets backwards — correct readings are the majority of every
text, so clustering on agreement clusters on noise — and the self-test's
discriminating case proves it: two witnesses agreeing twice in CORRECT readings
are left unrelated. Two shared errors is the threshold, a locus with no original
judged is excluded rather than counted, and a dossier declaring two origins for
witnesses that share two errors now FAILS.

The accepted dossier carries a collation whose witnesses agree once in a correct
reading and err separately, so the adapter proves both directions rather than
only the refusal.

### The argument from silence, priced

The survivorship gate asked an absence claim to say why a record would have
survived, and accepted prose — a sentence somebody wrote about their own claim,
always available, because every absence claim's author believes the record would
have shown it.

`domains/archival/scripts/silence.py` computes `P(no surviving record | it happened) = (1-r)^n`
from a survival-rate INTERVAL and a count of recording opportunities, judged at
the pessimistic end. A conclusion that holds only at the optimistic end of a
guessed rate is a conclusion about the guess, and the tool names that case
instead of passing quietly. With no rate stated it returns `not_computable` and
refuses to invent one.

### Parity

`domains/archival/scripts/dossier.py` — the pack could check a dossier and could not make one, so
it taught its format by rejection. The producer derives `supporting_sources` from
the graph rather than accepting a list, refuses cycles and dangling derivations,
and assigns evidence tiers from what the sources ARE: a later chronicle offers
`tradition_attested` and never `independent_origins`, however confidently it
reports the event. Three fields come back empty and stay empty — the archive
coverage, the falsity discriminator, the interpretation — and the gates refuse
the dossier until a person answers them, which is the point of not filling them.

Role evals (12/12), a journey (6/6), a held-out set (7/7 on seven cases, which is
a small set that I wrote and therefore weak evidence).

### The journey found a defect on its first run, again

The pack could not resolve its own journey claim. Its selection terms were all
MATERIALS — manuscript, codex, papyrus, shelfmark — and all TECHNIQUE — stemma,
palaeography, prosopography. None of that is how the questions get asked: a
historian writes "are these two independent sources or one copied twice", and not
one word of it matched. Source-criticism vocabulary added, and the resolver's own
self-test then caught a second miss where `shared error` did not match "share an
error" and `copied` did not match "copying" — the honest running cost of a
term-scoring method.

```
archival suite: 8 steps, 5s
  adapter 8 rejected / 1 accepted · dossier 8 · silence 7 · stemma 8
  journey 6/6 · role evals 12/12 · evals 6/6 · held-out 7/7
```

## 4m. Closing the gaps against the predecessor

Running the same target through `witsoc/` showed it stronger in three places.
All five items below close those, and the last two found defects while doing it.

**Escalation handed off to nobody.** The ladder was mechanical, defended at
length, and returned the word `ESCALATED` — the Researcher was a document with
no invocation path. `witsoc/` at least names the workers to dispatch. Escalation
now emits a sealed `frame-work-item-v1` addressed to the researcher, carrying
the obstruction, the failure signature that fired, the stop rule, and the
doctrine to read first, so the next role does not reconstruct the run's logs.
The frame still does not dispatch it; it does have to write it.

**There was no verifier role.** Attestation covered producer, reviewer and
admitter and never asked who RAN the verification, where `witsoc/` requires a
distinct VERIFIER receipt. The fix used a contract field that had been
decoration since it was written: every tier declares `authorship`, and a tier
declaring `independent` is a backend that knows nothing about the run and cannot
be talked into a pass — the producer may run it. Any other tier now requires a
verifier actor distinct from the producer, and a receipt that says nothing is
refused, because an unknown checker is the party being checked until somebody
says otherwise. Two new refusals; the suite is 20 refused, 2 accepted.

**`campaign.py` had two subcommands.** Once a campaign became a graph there was
no way to ask where one was and no way to pick one up. `status` prints the
claims, what is ready, what is blocked and why, races, and the budget; `doctor`
checks the invariants — unbound claims, dependencies pointing at nothing,
dependency cycles, statuses above their ceiling — each of which a real run in
this repo has violated, and each of which was found by a downstream refusal
rather than by asking.

### Who checks the checkers

Ten guards, no tests. The proofs that they work were done by hand and lived
nowhere, and two of the three proved that way were WRONG on the first attempt.
`check_checkers.py` plants a regression into a COPY of the tree for each one —
a field word, a pack path, a dead command, a wrong flag, an undeclared gate, a
ceiling raised, a renamed adapter flag, an emptied divergence list, a corrupted
example — and requires each to fail, then to pass again on the clean copy.

It found a real hole on its first proper run. `jsonschema_lite` treated
`additionalProperties` only as a boolean, so when it is a SCHEMA — which is how
`frame-state-v1` describes every claim in the graph — the values were never
validated. **The claim graph the reducer is the sole writer of had never been
schema-checked at all**: an illegal status validated clean.

Fixing that surfaced a second one. `check_schema_examples.py` stopped at the
first instance that passed, so a broken example elsewhere was reported green and
which file it reached first depended on directory order. Now every matching
instance is validated — and the bio manifest, reached for the first time, turned
out to have declared `CONDITIONAL_WITHIN_SCREEN` refining `CONDITIONAL` and
`REJECTED_DENOMINATOR` refining `REJECTED` against a schema that allowed neither.
The pack was right and the schema was too narrow: refuted BY DESIGN and refuted
by data are different findings with different remedies.

### Cross-run memory

The one load-bearing component with no test, and it had been silently recording
nothing. Nine cases now, and the ones that matter are about laundering: a hit
requires the SAME context on every axis, a near-match is refused with the axis
named, and a recorded failure blocks its own method without blocking every other.

Writing it produced the fourth substring collision of this project — `"NO REUSE:"`
contains `"REUSE:"`, after `rat` in `proliferation`, `a ` in `a real number`, and
`shared error` failing to match "share an error". A containment test on prose is
a coin flip with extra steps.

## 4n. Persistence and method depth

### SQLite for coordination, files for evidence

The predecessor keeps its campaign in SQLite with leases and deadlines. Copying
that wholesale would have been the wrong move: this frame's state is
content-addressed and replayable, every revision names its predecessor, and a
mutable table is a worse home for an evidence chain than an append-only file.

Three things genuinely need a transaction, and files cannot give one — a
REGISTRY of which campaigns exist and where their state lives, LEASES saying who
is working which claim, and EXPIRY so a worker that dies does not hold one
forever. `scripts/registry.py` is those three and nothing else. **Nothing in it
is authoritative about a status; the database can be deleted without losing one
verified fact.**

The scheduler now takes the lease set and does not offer a claim somebody holds.
It could offer the same claim to every worker that asked; the reducer then
refused the second admission on a stale base revision, which is correct and
arrives after both have paid.

`campaign.py resume` reads a stopped campaign back: what is in flight, what was
ABANDONED — a lease that expired and nothing released, so whatever that worker
was doing, nobody is doing it now — and what to pick up. `--state` had let a run
join a graph and nothing detected an interrupted one: a workdir holding a work
item and no admission looked exactly like a workdir nobody had touched.

### Method depth: the two I named and never built

Not the predecessor's 292 scripts. Two methods that earn their place, both
outstanding from a plan made much earlier in this project.

**`domains/maths/scripts/decompose.py`** — the pack could render a plan, check a
plan, and score whether a plan's gaps were good ones, and could not PROPOSE one.
The first creative step in the loop was the only step with no tooling, and
`sketch_rubric.py`, which exists to compare two decompositions of the same
target, had never had two to compare. It emits candidates from the shape of the
frozen statement — direct, chain, bridge, cases, induction — and ranks them with
that rubric.

Pointed at the target from this session's graph campaign, it independently
proposed **the exact decomposition built by hand there**: `a+c <= b+c <= b+d`,
by rewriting `a` to `b` in the left side. Two bugs on the way: the binder parser
stopped at the first colon, which is inside the first binder, so every
hypothesis went unseen and DIRECT was the only pattern ever proposed; and the
bridge looked for a bare variable the conclusion did not mention, when the
middle of `a+c <= b+d` is the composite `b+c`.

**`domains/bio/scripts/differential.py`** — which genes moved, at the unit the
claim is about. The standard answer is wrong in the one way this pack exists to
catch, and correcting for multiplicity does not fix it: the correction controls
error across FEATURES and the problem is the DENOMINATOR.

Its self-test disagreed with me and was right. Zero genes passed FDR, and the
reason is real: a sign flip over six units gives p only in multiples of 1/32, so
about two of sixty null genes reach the floor by chance, and once genes tie
there BH cannot push any below it. **No gene of any effect size can pass q<=0.05
at six donors.** Returning an empty list without saying that reads as "nothing
moved" when what happened is that the design cannot answer the question at this
scale. The tool now states the discreteness first, and the five planted genes
still rank top five by effect — which is the part this design can support.

## 5. Current state

```
frame purity           PASS   55 files
doc links              PASS   181 named paths resolve
contract shapes        PASS   4 packs
delivery               PASS   12.9KB of 16KB budget, 4 entry points, 0 shipped artifacts
doctrine coverage      PASS   every blocking gate named in the doctrine it governs
schema examples        PASS   8 of 9 exercised by real packets
reducer                PASS   15 adversarial admissions refused for the stated reason
working memory         PASS   8 boundary and gate cases
campaign               PASS   loop closes, ladder engages, packets reproducible
resolution             PASS   30 cases across 4 packs

maths    adapter PASS · evals 7/7 · produce 11/11 · external 10/10 and 29/29
bio      adapter 9-1 · evals 6/6 · bundle PASS · external 10/10
archival adapter 7-1 · evals 6/6 · external 250/250 chains, two traversals agreeing

end to end   maths -> VERIFIED   bio -> CHECKED_BOUNDED   archival -> CHECKED_BOUNDED
drawn target maths -> VERIFIED on the second attempt, first failed and was classified
```

## 6. What is still true and uncomfortable

- **One author.** Four packs, the contract, and every check were written by the
  same hand. The archival pack was built under a no-frame-changes rule to test
  that (`domains/archival/FRICTION.md` logs what the rule cost), and it is still
  one person's idea of an outside view.
- **`cost_hint` measures the wrong thing.** It is about compute. In archival the
  real cost is archive access — travel, permissions, months — and a pack
  declaring `moderate` because its Python is fast tells Explorer something
  actively misleading. This is the first friction item to fix.
- **The corpus scans source, not an elaborated environment.** It resolves 121,926
  qualified names and misses declarations generated by attributes or macros. The
  pre-flight reports rather than refuses for exactly this reason.
- **Resolution weights are tied, not calibrated.** `calibrate_resolution.py`
  sweeps 256 settings over all 30 declared cases: the shipped weights score 30/30
  — along with 103 other settings. The corpus cannot distinguish them, and the
  script says so rather than claiming vindication.
- **One campaign has run against a problem nobody chose, and it is a small one.**
  The drawn target was admitted by citing a library result rather than by
  establishing anything. The loop closing on unchosen material is real evidence;
  the mathematics done inside it is not much.
- **Every pack is still one author's.** The archival friction log and the
  external suites are attempts at an outside view and remain mine.
