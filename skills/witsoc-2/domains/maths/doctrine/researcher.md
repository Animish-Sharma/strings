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

## Name the blocking claim first

Before choosing any product, state the exact sub-claim that would unblock the
target if it held. Choosing a weaker product requires that claim named, **two
recorded direct attacks on it**, and how the weaker product feeds back toward it.

Attacking the tractable side because it is tractable is how a campaign produces
a pile of true statements that do not add up to progress.

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

On a witness: minimize it, then try to inflate it into an obstruction family and
state the resulting obstruction target. Report the inflation attempt or why it
failed.

## Obstructions

Beyond the frame's general taxonomy, the recurring ones here are in
`obstructions.md`: extremal near-violators, parity and modular invariants,
thresholds, compactness and finite-to-infinite transfer, regularity requirements,
independence and pseudorandomness, unmet preconditions on a known result,
formalization side conditions, and lossy reductions.

An obstruction is useful only if it yields a test, an obstruction result, or a
bypass mutation. One you can only describe is a narrative.

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
anything stuck.

## Playbooks

`playbooks/` holds the per-subfield cold-start kits. A frontier problem must load
**at least one specific playbook** — plus `playbooks/erdos_level.md` when the problem has
that shape. If no playbook fits, record the missing one; the gap is worth knowing.

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
