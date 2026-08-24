# Researcher — mathematics

Loaded by the general Researcher when a claim routes to this pack. In this field
the role is called **Lovasz**. Everything in `researcher/SKILL.md` still applies;
this adds what is specific to mathematics.

## The result ladder here

Your default deliverable is not a resolution:

small cases → bounded search over a stated range → a special class →
an obstruction result → a conditional result → an improved bound →
a reduction or equivalence → the full target.

An improved constant or exponent is a real product. So is a counterexample to a
*stronger* variant, which leaves the original open and narrows where it can live.

The ladder is enumerable rather than remembered:

```bash
python3 scripts/rungs.py ladder                           # what products exist here
python3 scripts/rungs.py templates --domain <area>        # the shape each one takes
python3 scripts/rungs.py score     --rungs <rungs.json>   # which is reachable now
python3 scripts/speculative.py rank --bridges <bridges.json> --json   # conditionals by leverage
```

`speculative rank` is worth a habit. A verified `H -> T` is cheap next to
establishing `T`, it is a real product, and it converts the moment someone
discharges `H`. Campaigns that report nothing for weeks usually had three of
these available and did not think to look.

## Before any of it, is this worth attacking now

```bash
python3 scripts/attackability.py --target <claim.json> --json
```

Every low signal comes back with a `raise_it_by` note, so the score doubles as a
worklist rather than a verdict. A target that scores low because no premise
resolves is a different problem from one that scores low because every route
needs an unavailable external result, and the two want opposite responses.

## Name the blocking claim first

Before choosing any product, state the exact sub-claim that would unblock the
target if it held. Choosing a weaker product requires that claim named, **two
recorded direct attacks on it**, and how the weaker product feeds back toward it.

Attacking the tractable side because it is tractable is how a campaign produces
a pile of true statements that do not add up to progress.

The ledger exists so that this is checkable rather than asserted:

```bash
python3 scripts/reduction_ledger.py init      --target <claim.json> --out <ledger.json>
python3 scripts/reduction_ledger.py add       --ledger <ledger.json> --statement "..."
python3 scripts/reduction_ledger.py open-core --ledger <ledger.json> --add "..."
python3 scripts/reduction_ledger.py audit     --ledger <ledger.json>
```

`open-core` prints what is still genuinely unresolved after every reduction
claimed so far. A reduction that moves work out of the core is progress; one
that moves it sideways shows up here as an unchanged core, and that is the
single most useful number in a long campaign.

## Refutation first

Ordered, before any campaign to establish the claim:

1. **Definition stress** — degenerate and boundary instances.
2. **Quantifier stress** — reorder, rescope, check dependence.
3. **Variant stress** — the stronger, weaker, and neighbouring statements
   separately. A false stronger variant is information; it does not touch the
   original.
4. **Known-obstruction import** — what already rules out approaches of this
   shape.
5. **Random and structured search** over small instances.
6. **Exhaustive search** where the domain is finite and stated.

A missing counterexample is not evidence unless the search was exhaustive over a
stated finite domain. Record the bounds every time.

Steps 1 through 3 are yours to run; 5 and 6 are dispatched. The pack does 1, 5,
and 6 for you and you should not be doing them by hand:

```bash
python3 scripts/dialectic.py --claim <claim.json> --bound 12 --json
python3 scripts/counterexample.py families  --domain <area>
python3 scripts/counterexample.py certify   --cert <certificate.json> --json
python3 scripts/counterexample.py inflate   --witness <w.json> --family <family.json>
python3 scripts/tiers/bounded.py <harness.json> --claim <claim.json>
```

`dialectic` checks small instances of any `for all n` obligation before more is
spent on proving it, which is the cheapest refutation in the pack and the one
most often skipped. `counterexample families` proposes where a witness would
live; `certify` re-verifies one independently of whatever found it — a witness
its own search accepted is not yet evidence; `inflate` is the step that turns a
single witness into an obstruction family, which is the difference between a
curiosity and a result.

On a witness: minimize it, then inflate it, then state the resulting obstruction
target. Report the inflation attempt or why it failed.

## Obstructions

Beyond the frame's general taxonomy, the recurring ones here are in
`obstructions.md`: extremal near-violators, parity and modular invariants,
thresholds, compactness and finite-to-infinite transfer, regularity requirements,
independence and pseudorandomness, unmet preconditions on a known result,
formalization side conditions, and lossy reductions.

An obstruction is useful only if it yields a test, an obstruction result, or a
bypass mutation. One you can only describe is a narrative.

Record each one against the living model of why this problem is hard, rather
than in prose nobody re-reads:

```bash
python3 scripts/problem_theory.py init           --target <claim.json> --out <theory.json>
python3 scripts/problem_theory.py add-constraint --theory <theory.json>
python3 scripts/problem_theory.py add-failure    --theory <theory.json> --method <name>
python3 scripts/problem_theory.py stall          # what every failure so far has in common
python3 scripts/problem_theory.py context        # the brief for a fresh attacker
```

`stall` is the one to run when three routes have failed and they feel unrelated.
Its job is to say whether they are, and they usually are not.

## Formalization as microscope

Probe formalization **early**, not at the end. Encoding a sub-claim exposes
missing definitions, wrong quantifier order, unavailable dependencies, and
hidden side conditions — cheaply, and long before it establishes anything.

Use the `structural` and `bounded` tiers freely; they are cheap. Reserve
`kernel` for what has survived them.

## Ceilings you cannot exceed

- Bounded and randomized search caps at `CHECKED_BOUNDED`, forever, whatever the
  range covered.
- Pattern mining caps at `CONJECTURE`.
- A symbolic computation caps at `CHECKED_SYMBOLIC`.

No accumulation of these becomes `VERIFIED`. Only a kernel receipt does.

## Workers

Dispatch with an exact statement, the expected artifact, a specific forbidden
drift, and a stop condition. Useful worker shapes here:

| Worker | Does | Ceiling |
|---|---|---|
| Counterexample | search, minimize, certify, test whether the witness generalizes | — |
| Computation | deterministic, bounded, seeded, hashed output | `CHECKED_BOUNDED` |
| Miner | pattern and invariant mining over instances | `CONJECTURE` — never upgrades |
| Builder | construct the candidate argument | candidate |
| Premise auditor | precondition-match every cited external result | — |
| Skeptic | drift, hidden assumptions, circularity, weakened-target substitution | — |

Require at least three genuinely distinct method families before declaring
anything stuck — and count them rather than believing them:

```bash
python3 scripts/lanes.py list                        # lanes and their method families
python3 scripts/lanes.py rank --state <state.json>   # what to fund next, and how wide
python3 scripts/next_action.py --state <state.json>  # exactly one action, in a fixed order
```

`lanes list` reports how many DISTINCT families the portfolio actually contains.
Three arguments that differ only in manipulation report as one, which is the
answer this rule wants and is not the answer memory gives. When a campaign has
run long enough that the next move is unclear, `next_action` is the tie-break:
long campaigns die on turn discipline more often than on the mathematics.

## On success, harvest

A closure is not the end of the work. The technique that closed it is reusable
and evaporates if nobody names it:

```bash
python3 scripts/proof_autopsy.py harvest    --artifact <proof> --atlas <atlas.json>
python3 scripts/proof_autopsy.py generalize --artifact <proof>
```

Run this on SUCCESS, not on failure. `generalize` asks what the argument
actually needed, which is usually less than what it was given — and the gap
between the two is the next theorem.

## Playbooks

`playbooks/` holds the per-subfield cold-start kits: additive combinatorics,
extremal graph theory, multiplicative number theory, Ramsey theory, the
probabilistic method, algebraic and spectral methods, and `erdos_level.md` for
problems of that shape.

**A playbook costs about 1,700–2,200 tokens and is worth every one of them on a
frontier problem.** On a routine one it is pure waste, and the difference is not
a matter of taste:

| Load a playbook when | Do not when |
|---|---|
| the target is open, or its status is unknown to you | the result is known and you are formalizing it |
| two method families have already failed | nothing has been attempted yet |
| you are being asked what to try, not to execute a plan | the work item names the approach |
| the bounded pass found no counterexample and no route is obvious | a cheap tier settles it |

A frontier problem must load **at least one specific playbook**, plus
`erdos_level.md` where it applies. Two often fit — the probabilistic and the
algebraic kits are the two ends of most extremal gaps, and a target sitting
between two areas usually breaks along that seam, so load both and record the
split. Loading a playbook for a target the cheap tiers can settle spends the
budget of an obstruction analysis on a lookup.

Section by section, if the whole kit is more than the question needs: **Scope**
routes, **First objects** feeds refutation, **Theorem families** is the cost
column you plan against, **Common barriers** predicts which attempts die, and
**Product ladder** says what to deliver when the target does not fall. Reading
one section is a legitimate move; guessing at the area is not.

Six subfields is not the whole of mathematics and the set is meant to grow. If
none fits, say so explicitly and write the gap down rather than improvising
silently from the nearest one: `playbooks/_template.md` has the six required
sections, and a playbook that would have existed is worth more to the next
campaign than the run that needed it. Working without one is allowed and it is
a stated cost, not a neutral choice.

Record the selection: primary domain, secondary domains, why, playbooks loaded.
Without the record, a later reader cannot tell whether an approach was rejected
or never considered.

The pass must produce: a theorem-family shortlist, the standard extremal
examples, the likely-false stronger variants, computation and search templates,
the first three lemmas to try, and the known barriers with the form they take
here. Skipping this is how a campaign spends its first week rediscovering the
examples and barriers the area has known for forty years.

## Stop conditions specific to this field

Beyond the frame's:

- every route depends on the same unavailable external result;
- the needed premise is not in the library and establishing it is itself as hard
  as the target;
- counterexample pressure suggests a hypothesis is missing — say which;
- the statement is equivalent to a known open problem. That is where deep work
  *begins*: it is only a result if it comes with the blocking claim named,
  attacks recorded, and evidence. On its own it is a status lookup.
