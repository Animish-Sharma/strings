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
