# Blueprint — the contract Generator executes

Generation is a **rendering**, not an invention. The blueprint is the only
executable input; prose is not a blueprint.

## Required sections

| Section | Holds |
|---|---|
| `metadata` | name, kind (`THEOREM`/`LEMMA`/...) |
| `target_formalization` | `domains_and_variables`, `definitions`, `hypotheses`, `claim` |
| `target_protection` | `original_statement`, `frozen_target_sha256`, `statement_tampering_forbidden: true`, `authorized_mutations: []` |
| `epistemic_context` | known obstructions, degeneracy checks already passed |
| `external_dependencies` | each with `theorem_name`, `exact_statement`, `required_preconditions`, availability |
| `lemma_plan` | the proof DAG: `step_id`, `type`, `statement`, `depends_on`, `method`, optional `cites` |
| `generator_directive` | `artifact_target`, `status_to_assert` |

`status_to_assert` may only be `UNVERIFIED`, `PARTIAL`, `CONDITIONAL`, or `GAP`.
The blueprint is structurally incapable of ordering a success claim.

## The execution contract

> Execute the blueprint into an artifact. Do not invent helper claims unless a
> structural check explicitly fails. Do not change `target_formalization`. Do not
> bypass `target_protection`. Do not cite anything outside
> `external_dependencies`.

`scripts/generate_wit.py` enforces all four mechanically and refuses to emit
otherwise — including refusing when the rendered CLAIM does not hash to
`frozen_target_sha256`.

## Choosing which sketch becomes the blueprint

```
expected_value = target_fidelity x P(completion) x checkability
```

Take the highest, or record in writing why not. Fidelity beats elegance, and a
high completion probability never compensates for low fidelity unless the product
is explicitly labelled `PARTIAL` or `CONDITIONAL`.

## Justification quality

A `BY` consisting only of step references with no method is a **weak
justification**. The words "clearly", "obvious", "trivial", "standard",
"straightforward", "well-known", "classical" are smells, not justifications.

Invoking an external result **without a preceding step establishing its
preconditions** is the canonical bad pattern.

Prefer `GAP EXPECTING [name]` over a bare `GAP` whenever the hole is a nameable
sub-problem: the named form can be enqueued as its own claim, the bare form
becomes prose nobody acts on.
