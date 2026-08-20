# The Verification Interface

The frame's central abstraction. Something a candidate artifact is submitted to,
which returns pass/fail plus a receipt, and about which the frame knows nothing
except that signature.

```
verify(artifact, claim, tier) -> (pass | fail, receipt)
```

Swapping this backend is the whole point of the frame/domain split. A domain
whose verification is a single deterministic checker and a domain whose
verification spans a symbolic check, a simulation, and a physical run both
implement the same interface — the second simply declares more tiers and lets
Explorer freeze which one a claim requires.

## Verification is two-step

Generator's flow is **propose → refute-attempt → receipt**, never a single
adapter call.

The reason is structural. A role under throughput pressure has an incentive to
under-scrutinize its own output, and a single adapter call can return a pass
that does not survive a second look. Where the backend is already adversarial
that incentive is harmless — the backend refuses regardless. Where verification
is graded, it is not.

| Backend | Refute-attempt gate |
|---|---|
| **Adversarial** (`adversarial: true`) — cannot be talked into a false pass | The adapter run *is* the gate. Nothing more is owed. Declare it with `satisfied_by_tier`. |
| **Graded** — sampling, estimation, tolerance, simulation, or human judgment | A separate step is owed: re-run under a deliberately perturbed condition — a different seed, a tightened tolerance, a held-out split, a perturbed model — or route through a skeptic pass whose only job is to break the result. |

> A result that survives only one favorable run does not earn a receipt.

`gates.refute_attempt` is a **required** field of every pack manifest, precisely
so a future pack cannot skip it by omission. `scripts/validate_domain_pack.py`
refuses a manifest whose `satisfied_by_tier` names a non-adversarial tier —
claiming a friendly backend discharges the gate is the exact mistake the field
exists to prevent.

## Auditing the backend

Everything above assumes the backend can actually say no. That assumption is the
one the frame most needs and least controls, so it is not granted — it is
earned, tier by tier.

**Declaring a tier `adversarial` is a claim about the backend, and it is
auditable.** A pack author asserting the flag is the party being checked
asserting they are checkable. A tier earns it only if it is:

- **Two-sided** — it demonstrably returns fail on inputs that should fail. A
  backend nothing has ever failed is unaudited, not trustworthy. Declare the
  negative control: a known-bad artifact the adapter must reject.
- **Independently authored** — not written by whatever produces candidates for
  it, and not tuned against the candidates it will judge.
- **Uncontaminated** — evaluated against material constructed *after* the
  candidate, not material the producer could see or fit to.
- **Degeneracy-hardened** — an empty, erroring, or trivial input fails rather
  than scoring. An error is never a pass.

A tier that cannot state these is `adversarial: false`, whatever its author
believes.

**A tier's ceiling is separate from its honesty.** These are two independent
properties and conflating them is a soundness hole: an exhaustive search over a
stated finite domain can be perfectly adversarial — it genuinely cannot be
argued into a false pass — and still establish nothing outside those bounds. So
each tier also declares `max_status`, the strongest status a pass on it can ever
support. Discharging the refute-attempt gate does not lift that ceiling.

## Independence

The frame requires independent review in several places. It means one thing:

> **Independence means distinct recorded failure domains, and unknown fails
> closed.**

Two checks are independent only when the thing that would make one wrong is
recorded, and is not the thing that would make the other wrong. Sharing an
author, an input corpus, an environment, an assumption, or a method family
defeats it. A different name on the wrapper does not establish it, and an
assertion of separateness is not evidence of separateness.

Where independence is required and the failure domains are unknown or
unrecorded, the review does not count. Never assume independence you did not
check. A reviewer who is also the producer is not a reviewer.

A review is bound to the exact bytes it reviewed (`frame-review-v1`). If the
artifact or the set of reviews changes afterwards, any adjudication over them is
stale and must be redone.

## Receipts

A receipt is only evidence about the artifact **that exists now**.

Staleness is the central attack on any verification pipeline: a passing run from
a previous edit trivially launders a later broken artifact. So a receipt must be
bound to the artifact's content, and the binding must be re-checked at the exit
gate, not merely recorded at production time.

Every pack declares a `freshness_rule` stating how staleness is detected in its
field. The frame requires it to be non-trivial; a pack that cannot say how a
receipt goes stale has not thought about the attack.

A receipt is **complete** when every obligation has a verdict, the concluding
step is covered, there are no open gaps and no rejections, and its overall
verdict matches the status being claimed. Truncated backend output is flagged as
incomplete rather than read optimistically.

## Fidelity is a separate gate

Passing the backend proves things about the **encoding**. Whether the encoding
says what the frozen target says is a different question, and no backend can
answer it.

So a fidelity record is required alongside the receipt. A record saying *not
faithful* is a demotion. A **missing** record is equally an error — the gap
between "the checker was happy" and "the checker was checking the right thing"
is where confident wrong answers live.

## Adverse evidence

Adverse evidence is tracked separately from supporting evidence and is never
netted against it.

**An unresolved contradiction blocks any status above `CONJECTURE`.** Resolve
it, or state the claim as `CONDITIONAL` on its resolution. Never dispose of a
challenge by restating the original result more confidently.

The asymmetry between backend types applies here too, and getting it backwards
is dangerous in both directions:

- Where the backend is **adversarial**, a disagreeing re-check elsewhere is a
  warning worth investigating; the fresh hash-bound receipt stands.
- Where verification is **graded**, it is not a warning. A failed re-check is
  adverse evidence and carries the block. A failed replication is not noise to
  be averaged away.

## A check you could not run is a gap

When a backend, dependency, or data source is unavailable, name it and record
the obligation as open.

**Do not write the account a successful run would have produced.** Narrating a
check is not running one, and no reader can tell the difference afterwards.

**Absence of a contrary finding from a check that never executed is not
evidence for the claim.** It is evidence about your toolchain. An unavailable
screening step is a precondition gap, never support.

Where a pack declares an `availability_check` for a tier, run it before spending
against that tier, so a run can state its honest ceiling up front rather than
discovering it after the budget is gone.

## What verification is not

A process exiting successfully. A budget being exhausted. A vote. A score. A
survived bounded search. A structural check. A generated review context. A
plausible argument. An agent's own confidence. A second agent agreeing. A file
existing at the expected path.
