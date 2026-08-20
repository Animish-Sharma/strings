# The Domain-Pack Contract

A domain pack is the only thing that changes between fields. To plug into the
frame it supplies exactly six things — no more, and none of them optional.

The machine-readable form is `schemas/frame-domain-pack-v2.schema.json`, which
is the source of truth. This document explains what each item is *for*.

Contract v1 packs still validate, and carry only items 1–5. They are reachable
solely by explicit name: item 6 is what lets the frame find a pack on its own,
so a v1 pack is silently never auto-selected. `validate_domain_pack.py` says so
when it validates one.

## 1. Verification adapter

A function `(candidate artifact) -> (pass/fail, receipt)`.

The frame knows nothing about it except that signature. It may dispatch over
several backends internally — a cheap symbolic check, a simulation, a physical
or experimental run — and Explorer freezes which tier a claim requires before
Generator starts. The frame's Generator role never needs to know which tier ran;
it only needs a receipt back.

Declare each tier with `adversarial: true|false`. A tier is adversarial only if
it **cannot be talked into a false pass**. That flag decides whether the
refute-attempt gate (item 5) is already discharged or still owed — and it is
audited, not taken on trust: an adversarial tier must declare independent
`authorship`, `two_sided_evidence`, and a `negative_control` the frame re-runs.
See `verification_interface.md` §Auditing the backend.

Declare `max_status` separately. A tier's honesty and its reach are independent:
an exhaustive search over a stated finite domain is genuinely adversarial and
still establishes nothing outside its bounds. Passing the gate never lifts the
ceiling.

A pack that has a knowledge corpus declares it under `verification_adapter.corpus`
(item 1b) — Explorer is required to retrieve against one, so the slot exists
rather than leaving that mandate unsatisfiable. Substrate-specific status names
go in `status_refinements`.

### Calling convention

The adapter is a function, and a function has a signature. This is it:

```bash
<entry_point> --artifact <path> --claim <path> --tier <name> --json
```

stdout is a `frame-receipt-v1` and nothing else. Exit 0 pass, 1 fail, 2 error,
3 tier could not run. Every adapter accepts `--json` even if it always emits
JSON.

This went unstated through two contract versions and three packs, and the packs
diverged: one of them rejected `--json` and so could not be called by the frame
at all. Nothing found it, because nothing had ever run the loop end to end —
each pack was tested by its own self-test, which called it the way that pack
happened to expect. A contract item that says what a thing IS without saying how
it is CALLED is half a contract.

## 2. Claim schema

The structured, frozen representation of what is being claimed. It extends
`frame-claim-v1` with whatever this field must pin down.

The frame's generic fields cover the claim identity, the exact statement, the
success and failure conditions, the frozen conditions, the inputs, the allowed
mutations, and the status. A field adds its own: a dataset version, an
environment, a tolerance, a population, a baseline.

The test of whether a field belongs here: **if it changed silently, would a
result stop meaning what it claimed to mean?** If yes, it is frozen content.

## 3. Evidence/receipt format

What counts as a receipt in this field, and — required, and required to be
non-trivial — **when one goes stale**.

A receipt produced before the artifact's last edit is not evidence about the
artifact that exists now. This is the single most common way a system launders
a broken result into a passing one, so the frame refuses to let a pack leave
`freshness_rule` unstated. Say how staleness is detected here: a content hash,
a modification time against a run timestamp, a re-run under a recorded seed.

## 4. Doctrine extension

Field-specific rules layered on the frame's generic doctrine. Two things are
mandatory, because they parameterize frame machinery:

- `escalation.max_consecutive_failures` — the **N** in the escalation ladder.
- `escalation.failure_signature` — how this field decides two failures are
  "the same failure".

Everything else is the pack's own: a pre-registration requirement, a correction
procedure, an order-of-operations rule, a budget discipline. Point at the
documents with `doctrine.rules`.

## 5. Gate definitions

The checks a candidate must pass before its status may move off `CONJECTURE`.
These are this field's instantiation of the frame's generic gate mechanism, not
new frame code.

`gates.refute_attempt` is **required**, so no pack can skip it by omission.
See `verification_interface.md` for what makes a refute-attempt real.

Typical additions: a placeholder or hole scan with the field's own token set, a
tampering diff against a protected baseline, a threshold check, a
multiple-comparison correction, an independence check.

## 6. Selection

*What tells the frame this pack is the right one.*

This is the item that decides whether a pack is ever used at all. Everything
else describes how a pack works once loaded; without this, nothing loads it. A
registered pack with no selection block is indistinguishable, at run time, from
a pack nobody wrote — and the failure is silent, because the roles still run,
just with no field doctrine underneath them.

```json
"selection": {
  "signals":        ["ordinary terms of the field"],
  "strong_signals": ["terms essentially unused outside it"],
  "excludes":       ["terms that fire the signals but mean another field"],
  "examples":       ["real problem statements this pack handles"],
  "counter_examples": ["statements that look like its business and are not"],
  "min_score": 3
}
```

`scripts/resolve_domain.py` scores an incoming statement:
`1 x signals + 3 x strong_signals - 3 x excludes`. A pack clearing its
`min_score` and beating the runner-up by 3 is selected; within 3 of another
qualifying pack the answer is AMBIGUOUS, which is a real outcome and often the
correct one (§2.2 of `ARCHITECTURE.md` — a claim can genuinely engage two
packs). Below every threshold the answer is NO_MATCH.

Three things make this worth more than a keyword list:

- **The field's vocabulary lives in the pack, never in the frame.** Governance
  rule 2 forbids the frame from carrying a field's words. Resolution has to
  happen somewhere, so it happens by the pack declaring its own terms and the
  frame reading them without understanding them.
- **`excludes` is what stops over-claiming.** Every field borrows words. A pack
  whose common words appear in another field's problems will take those
  problems unless it says which borrowings to disown.
- **`examples` and `counter_examples` are executable.**
  `resolve_domain.py --self-test` requires each example to resolve back to its
  own pack and each counter-example not to. A signal list that grows broad
  enough to steal another pack's example fails there, at edit time, instead of
  in a run six weeks later.

Resolution **fails closed**. If the winning pack's manifest names doctrine,
adapter, or schema files that do not exist, the result is UNRESOLVABLE, not a
selection: a run that believes it loaded a field and did not is worse off than
one that knows it has no pack.

## When no pack matches

NO_MATCH is not a refusal. The frame can freeze a target and triage with no
pack at all, but nothing can be admitted without an adapter to say no — and
running the roles with no field doctrine is the silent failure this whole
contract exists to prevent.

So the orchestrator improvises one:

```bash
python3 scripts/scaffold_domain.py --domain <name> --from <closest-pack> \
    --statement "<the problem>"
```

The generated pack is real, not a stub. Its adapter checks the properties any
field's artifact must have — no placeholder tokens, every frozen obligation
addressed by name, the target hash unchanged — and it ships a refute-attempt
gate that perturbs the claim and requires the verdict to flip. A checker that
passes an artifact just as happily after an obligation is removed was never
reading the obligations; that gate catches exactly that, in any field.

What it may **not** do is grant the status a real pack can. The `provisional`
block declares `authored_by: orchestrator`, and that is the whole point: the
system producing candidates also wrote the thing that checks them. So the
ceiling is `SKETCH`, `validate_domain_pack.py` refuses a higher one unless the
pack wraps a genuinely external checker (adversarial, independently authored,
with a negative control that exists), and every receipt it emits carries
`provisional: true`.

Promotion out of provisional is a checklist in the manifest, not a judgement
call: an independent backend, a negative control it demonstrably rejects, a
signal list drawn from real problems rather than one statement, and role
doctrine rewritten from real runs.

## What a pack must never do

A domain pack must never import, monkey-patch, or special-case Explorer,
Generator, Researcher, or the bridge layer.

If a field seems to need the frame to behave differently, that need almost
always belongs in one of the six items above. Ask the diagnostic question:
*is this genuinely domain-neutral, or is it this field's verification adapter
in disguise?* Only a genuinely neutral need — a new status value useful to
every field, say — is a frame change, and that is a deliberate contract version
bump.

This one rule is what keeps the frame from re-accumulating field-specific
assumptions the moment a second field is added. That erosion is easy under time
pressure and expensive to unwind later.

## 7. Writing a pack

1. Create `domains/<name>/` and write `domain.json` against the schema.
2. Model the layout on a single self-contained directory. Resist spreading a
   pack across several top-level directories — the predecessor system did that
   and the pieces drifted apart.
3. Implement the adapter behind the declared entry point.
4. Declare the refute-attempt gate and the escalation threshold. They are
   mandatory contract items, not optional extras.
5. Declare `selection`, including at least one counter-example. A pack that
   cannot be resolved will never run, and one that over-claims will run on
   problems that belong elsewhere.
6. Reuse the frame's status vocabulary rather than inventing a parallel one.
7. Validate:

```bash
python3 scripts/validate_domain_pack.py domains/<name>/domain.json
python3 scripts/resolve_domain.py --self-test
python3 scripts/check_frame_purity.py
```

All three must pass before the pack is registered. `domains/_mock/` is a minimal
conformant example — it is a frame test fixture rather than a real field, so
copy its shape, not its content.
