# A campaign on a target nobody chose

Every other fixture in this pack was written to exercise something. This one was
drawn at random from an installed library — `random.Random(31337)` over the
source tree, filtered only for statements short enough to fit on a line, and
`drawn_targets.json` records the six that came out. Nothing about the target was
selected to suit the pipeline.

## What happened

**Attempt 1** (`attempt_1_failed.json`) proposed induction on `n` with the
standard recurrence, closed by `simp` and `omega`. The pipeline rendered it,
checked its shape, translated it, and the kernel refused:

```
unsolved_goal: omega could not prove the goal
```

The failure was classified `formalization_block`, the gap classifier named the
`formalization_target` axis, a revision request was written naming the step and
the edit, and working memory recorded the attempt with a revival condition — so
a re-run of the same blueprint is now refused before anything is produced.

**Attempt 2** (`attempt_2_admitted.json`) declared the recurrence as an external
dependency and cited it. The premise pre-flight resolved it against the corpus,
the kernel elaborated clean, all five blocking gates passed including a real
`#print axioms`, and with an independent review the campaign was admitted
`VERIFIED` — outcome `SOLVED`.

## What this is and is not evidence of

**It is** evidence that the loop closes on material the pipeline did not choose:
target in, artifact out, real kernel, honest failure, classified, revised,
admitted.

**It is not** evidence that the system can prove things. Attempt 2 cites a
library result rather than establishing it, which is a legitimate artifact and a
small one. The interesting number here is not that attempt 2 passed — it is that
attempt 1 failed and the failure was *informative*: a named step, a named axis,
and an edit, rather than a stack trace and a shrug.

Reproduce with:

```bash
python3 scripts/produce.py --blueprint evals/drawn/attempt_1_failed.json --tier kernel
python3 scripts/produce.py --blueprint evals/drawn/attempt_2_admitted.json --tier kernel
```

Both need `WITSOC2_LEAN_PROJECT`.
