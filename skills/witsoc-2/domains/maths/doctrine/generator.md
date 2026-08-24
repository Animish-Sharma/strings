# Generator — mathematics

Loaded by the general Generator when a claim routes to this pack. Everything in
`generator/SKILL.md` still applies; this adds what is specific to mathematics.

## Artifacts

Two forms, in order:

- **WIT** (`.wit`) — the structured informal argument: labelled steps, each with
  a keyword, a claim, and a `BY` justification. Cheap to write, cheap to check,
  and it exposes the shape of the argument before any formal cost is paid.
- **Lean** (`.lean`) — the formal artifact, elaborated against Mathlib.

WIT precedes Lean unless the work item says otherwise. A gap that WIT makes
visible for free is a gap that would otherwise be found after an expensive
formalization attempt.

## Granularity

Split any step that fuses two moves. In this field the recurring fusions are:

- a manipulation together with an estimate;
- existence together with uniqueness;
- invoking an external result together with checking its preconditions;
- a construction together with its correctness;
- one direction together with its converse;
- termination together with a complexity bound;
- several cases at once.

A fused step is where a mistake hides, and it is also where the kernel will
stop with a diagnostic you cannot act on.

## The check loop

Two loops exist here, not three. Cheapest first:

1. `lake env lean <file>` — file-level elaboration. **This is the default and it
   is also the floor.** There is deliberately no per-command fast path in this
   pack: the REPL that was available returned success-shaped JSON while running
   against an empty environment. The measurement, and the reasoning behind the
   rejection, are in `kernel_economics.md`. If you find yourself reaching for a
   faster backend, that document names the gate it has to pass first.
2. Full `lake build` — final confirmation only. Never inside a repair loop.

Because there is no fast path, **the import is the entire cost**: 5.0s to import
Mathlib against 0.1s to elaborate a three-obligation proof, measured. The proof
is under 2% of the run. Two things follow that you can act on:

- **Batch obligations into one file.** Ten obligations checked separately cost
  ten imports; the same ten in one file cost one. This is the largest saving
  actually available to you, and it needs no new machinery.
- **Never ask the kernel a question a cheaper tier answers.** Every structural
  error `wit check` catches is five seconds not spent, and the structural tier
  runs in milliseconds.

```bash
python3 scripts/availability.py --tier kernel --claim <claim.json>   # before spending anything
eval "$(python3 scripts/scaffold_lean.py --print-export)"            # if it says no project
python3 scripts/tiers/kernel.py <artifact.lean> --json               # the default loop
python3 scripts/tiers/kernel.py <artifact.lean> --full-build         # confirmation only
```

Pass `--claim` to the probe. Whether this tier needs a LIBRARY is a property of
the claim — a target whose `allowed_external_facts` is empty needs the kernel and
not Mathlib — and asking without the claim makes the probe refuse a tier that
would have run, which understates what the run could establish.

`scaffold_lean.py` builds the minimal project `lake env` needs. It gives an
**environment, not a library**: enough for a target citing nothing, and not
enough for one citing anything. A target that needs Mathlib still needs Mathlib,
and the probe will still say so.

Feed the exact goal state and diagnostic into the next repair. A repair driven
by a paraphrase of the error is a guess.

## Closing a leaf

Once the plan is split far enough, each leaf is small, and small goals are what
decision procedures are for. The pack searches for the tactic rather than asking
you to remember it:

```bash
python3 scripts/tactic_search.py --goal "n + 0 = n" --binders "(n : Nat)" --json
```

Every candidate goes into one file as its own `example` and the file is
elaborated **once**, so a twelve-tactic portfolio costs one import rather than
twelve. That is the batching rule above, applied to the pack's own machinery,
and it is the difference between a portfolio that is usable and one nobody runs.

What each candidate is for, so a failure tells you something:

| Tactic | Closes | Failing tells you |
|---|---|---|
| `rfl`, `trivial` | definitional identities | the two sides are not definitionally equal — there is real content here |
| `simp`, `simp_all` | anything the simp set normalizes to `True` | the needed lemma is not simp-tagged, so it has to be cited by name |
| `decide` | decidable propositions on concrete values | the proposition is not decidable, or the instance does not reduce |
| `omega` | linear arithmetic over `Nat` and `Int` | there is a multiplication of two variables, or a non-linear step hiding in the goal |
| `norm_num` | closed numeric goals | a variable survives; this is not a computation |
| `ring` | commutative-ring identities | the identity is false, or it needs a hypothesis, which `ring` never uses |
| `linarith`, `nlinarith` | linear (and lightly non-linear) arithmetic over ordered fields, using hypotheses | the hypotheses in context do not entail it — often a missing earlier step, not a missing tactic |
| `positivity` | goals of the form `0 < e` / `0 <= e` / `e != 0` | some subterm's sign is genuinely unknown, which is usually the real lemma |
| `tauto` | propositional consequence of the context | it is not propositional — the content is in the quantifiers |
| `aesop` | goals reachable by the default rule set | the step is not routine; treat a failure here as evidence the leaf needs splitting |
| `exact?` | anything a single library lemma closes | **the most informative failure in the list**: no single result does this, so the step is a real composition rather than a citation |

`exact?` earns its place twice over — when it succeeds it names the lemma, and
the name is worth more than the closure, because it tells you what the library
calls the thing you were describing.

**When nothing closes, do not widen the portfolio.** A leaf that survives all
fourteen is not small, and the answer is to split it in the plan. Adding a
fifteenth tactic is the dominant waste mode here, and it hides the finding.

**This invents nothing.** The rule protects the plan: a step the blueprint did
not authorize may not appear, a citation may not be conjured, the target may not
drift. Searching for the tactic that discharges an *already authorized* step
adds no content — the obligation was stated before the search ran, and the
kernel is still the only thing that says whether it closed. `native_decide` is
excluded from the portfolio, because the placeholder scan rejects it downstream
and a search whose best answer is one the gates refuse is worse than no search.

## What you may edit

**The proof body, and nothing else.** Changing a signature, a definition, a
domain, or a hypothesis requires an approved target update — which is a new
claim with a new hash, not an edit.

Run the target-protection diff before submitting. It exists because the easiest
way to make something type-check is to change what it says.

## Gates before any status claim

| Gate | Rejects |
|---|---|
| `placeholder-scan` | `sorry`, `admit`, `axiom`, `constant`, `opaque`, `unsafe`, `native_decide`, `?_`, `by?` |
| `target-protection-diff` | statement weakened, binder assumption smuggled in, definition redefined to trivialize |
| `axiom-audit` | dependence on any axiom outside the declared allowlist |
| `premise-precondition-audit` | a cited result whose hypotheses are unmet locally, and one whose hypotheses were under-declared |
| `fidelity-review` | a formal statement that does not say what the informal target says |

A placeholder makes anything elaborate, so its presence voids the kernel verdict
entirely rather than merely reducing it.

Run them with the corpus, not without it:

```bash
python3 scripts/gates/placeholder_scan.py <artifact>
python3 scripts/gates/target_protection.py <artifact> --claim <claim.json>
python3 scripts/gates/premise_audit.py <artifact.wit> --claim <claim.json> --corpus corpus.json
python3 scripts/gates/fidelity.py <artifact> --claim <claim.json>
python3 scripts/gates/axiom_audit.py <artifact.lean> --claim <claim.json>
python3 scripts/gates/circularity_audit.py <artifact.lean> --decl <name> --claim <claim.json>
```

`circularity_audit` is the one gate that matters most on a target the library
already has. `theorem t : P := library_t` type-checks, depends on no unusual
axiom, does not drift from the frozen target, and cites a premise that resolves
— it passes everything else. It is also not a proof of anything.

Given `--corpus` it refuses four things:

1. the proof names the target, under any namespace abbreviation, including
   inside the `._proof_` auxiliaries a tactic lifts out;
2. it uses a declaration whose type is exactly the target's — a different name
   for the same result is the same citation;
3. its head constant has the target's type;
4. it uses a result CONCLUDING what the target concludes that the claim does
   not list in `allowed_external_facts`.

Rule 4 is what makes `allowed_external_facts` a statement about the PROOF
rather than about the plan. Without it a one-word tactic reaches any lemma it
likes while the premise audit reports "0 citations", because the premise audit
reads what the blueprint declares. Declare the result and the claim is honest
about resting on it; leave it undeclared and nothing in the receipt says the
proof rested on anything.

Every run also records `library_dependencies` — what the proof term actually
leaned on — whether or not a rule fires. See `../evals/drawn/RULE_SPIKE.md` for
how these rules were chosen and what they measurably catch.

Measured on forty targets drawn at random from Mathlib: thirty-six were closed
by the tactic portfolio and twenty-two of those closings cited the target. See
`evals/drawn/`.

`premise_audit` without `--corpus` reads two of its three checks out of the
claim: whether a cited name resolves is a boolean the author typed, and the
preconditions it matches are the ones the author chose to list. Under-declare a
theorem's hypotheses and every precondition check passes because there are fewer
of them. With `--corpus` it looks the premise up, compares the declared count
against the hypotheses in the library type, and reports both numbers. The arrow
count is a floor rather than a full parse — hypotheses written as explicit
binders are not counted — and a floor taken from the library still beats a
number taken from the author.

`fidelity` returns `NO_JUDGE` and exit 3 when nothing independent was available
to ask. That is NOT_RUN and it is not a pass; it is also not a failure, and a
report saying "fidelity failed" when no judge existed asserts a finding nobody
made.

**Elaboration success is necessary and not sufficient.** It establishes a fact
about the encoding. Whether the encoding is the target is what the fidelity
review answers, and no amount of kernel success substitutes for it.

## Say exactly what happened

The four-way distinction the frame requires, in this field's terms:

| Say | When |
|---|---|
| "structurally valid" | `wit check` passed — no semantic claim whatsoever |
| "contexts generated" | review contexts were built — **nothing has run** |
| "externally accepted" | an independent reviewer returned accept |
| `VERIFIED_LEAN` | fresh hash-bound kernel receipt + clean axiom audit + passing fidelity review |

`wit verify` prepares material for review. It does not call a checker. Never
report its exit code as verification.

## Repair budget

Three consecutive same-class failures with no obligation reduced, or eight
expensive runs on one approach, ends local repair. Going back to the sketch is
the correct move; more edits at that point are the dominant waste mode.

Failure classes are in `repair.md`. Diagnose into a class *before* editing — an
unclassified failure teaches nothing and the next attempt inherits the blind
spot.

## Honest failure

`GAP` — a specific bridge is missing, and the route may still work. Prefer the
structured form, `GAP EXPECTING [name]`, which names the missing sub-problem so
it can be enqueued as its own claim rather than remembered as prose.

`FAILED_ATTEMPT` — this route is shown not to work, with the diagnostic that
shows it.

`PARTIAL` — a narrower product only. State the narrow target explicitly and mark
the unresolved bridge as an open hole.
