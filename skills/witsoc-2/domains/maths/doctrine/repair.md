# Repair — failure classes and budget

Diagnose into a class **before** editing. An unclassified failure teaches
nothing and the next attempt inherits the same blind spot.

## Budget

- **3** consecutive same-class failures with no obligation reduced → stop local
  repair; the frame's ladder escalates to the Researcher.
- **8** expensive runs on one approach → that approach is exhausted.
- **No repair hypothesis, no expensive run.** An expensive attempt with no
  stated expectation of what will differ is a gamble.

Every attempt records: a unique id, a failure class, the repair hypothesis, and
an obligation delta (`reduced | same | worse | unknown`).

## Failure signature

`(failure_class, normalized first diagnostic line)` — with file positions,
identifier suffixes, and metavariable numbers stripped. Two failures sharing a
signature are the same failure, and a repeat escalates immediately: the second
attempt evidently changed nothing the checker could see.

## Classes

Frame-level classes, refined for this field:

| Class | Means | Usual repair |
|---|---|---|
| `unknown_identifier` | cited name does not exist | resolve against the corpus; a guessed name is not evidence |
| `import_missing` | the declaration exists but is not imported | add the import, expect invalidation, record why |
| `type_mismatch` | the types do not line up | check the statement encodes the intended object |
| `coercion_issue` | numeric or structural coercion | make the coercion explicit rather than hoping |
| `unsolved_goal` | a branch was left open | split the step; a fused step hides which half failed |
| `missing_premise` | a needed fact was never established | promote to a sub-claim; do not assert it |
| `precondition_not_discharged` | cited result's hypotheses unmet locally | discharge them as steps or drop the citation |
| `quantifier_or_domain_mismatch` | order or scope differs from the target | this is target drift until proven otherwise |
| `algebra_logic_error` | the step is simply wrong | recheck against a small instance first |
| `case_not_closed` | a case analysis is incomplete | enumerate the cases explicitly |
| `step_too_compressed` | the step fuses two moves | split it |
| `vacuous_proof` | the hypotheses are unsatisfiable | the statement is probably wrong — say so |
| `target_drift` | the artifact no longer states the target | demote the **artifact**, never the claim |
| `forbidden_escape` | a placeholder or escape hatch is present | remove it; it voids the verdict |
| `out_of_scope_reference` | cites something outside `allowed_external_facts` | out of scope is not a step |
| `toolchain_unavailable` | no checker to run | a gap, never a pass, and never support |

## Rules

Mutate **one axis at a time**, recording what changed and what was deliberately
held constant. Cosmetic rewrites are forbidden: every repair must reduce a real
obligation while preserving the frozen target.

Never ask for "fix this". Ask for a **distinct route, with an explanation of why
it avoids the recorded failure**.

Every `do_not_repeat` entry records a revival condition — most dead routes here
are dead only conditional on a premise that is currently unavailable, and that
changes.

## Running the loop

A revision is a new blueprint and the same workdir:

```bash
python3 scripts/produce.py --blueprint bp.json --tier kernel --workdir run/
# fails -> read run/revision_request.json, which names the failing WIT step
# edit bp.json
python3 scripts/produce.py --blueprint bp.json --tier kernel --workdir run/
```

Re-running an UNCHANGED blueprint is refused: the repeat guard keys on a
fingerprint of the plan — its steps, tactics, preamble and declared citations —
so a revision is a different attempt and a retry is not. The previous render is
kept beside the new one as `<name>.wit.supersededN`.

Working memory follows the target rather than the directory. Set
`WITSOC2_SOC_STORE` to keep it across workdirs; without it memory lives in the
workdir and a run in a fresh directory starts from an empty ledger.
