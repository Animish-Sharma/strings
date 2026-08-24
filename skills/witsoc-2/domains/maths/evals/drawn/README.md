# A campaign on targets nobody chose

Every other fixture in this pack was written to exercise something. These were
drawn at random from an installed library. `draw_targets.py` is the sampler and
`run_batch.py` the runner, so both are re-runnable rather than described.

## The batch

`batch40.json` — 40 theorems drawn with `random.Random(31337)` from the 67,707
single-line `theorem`/`lemma` statements in Mathlib. The only filters are
structural: one line, no `sorry`, and a statement short enough to lift. Nothing
was filtered for being provable, small, or in a friendly part of the library.

Each target carries the `import` lines of its file and the `namespace`,
`section`, `open`, `universe` and `variable` lines live at its scope, replayed
verbatim so Lean applies its own variable-inclusion rule. `batch40_results.json`
is the run.

```
drawn          40
elaborated     40      the statement type-checked in its replayed scope
closed         37      some tactic in the portfolio discharged it
independent    15      ...and the proof term does not cite the target
```

Independent closures: `rfl` 9, `simp` 5, `exact?` 1. Median 3.3s per target.

Re-measured after the gate gained type-alias and conclusion-head rules: the
funnel is unchanged at 15/40. This batch exercises the name and type checks; the
conclusion-head rule is the net for a case no drawn target contains, and
`RULE_SPIKE.md` reports what it does catch.

## The number that matters is 15, not 37

The portfolio contains `exact?`, whose job is to find a library result of the
goal's type — and every target here **is** a library result of that type. So 22
of the 37 closings were the search finding the answer key. They pass the kernel,
pass `#print axioms`, pass target protection, pass the premise audit, and prove
nothing. `../../scripts/gates/circularity_audit.py` renders the proof term and refuses them.

Without that gate this page would report 37/40 and be worthless. That is the
finding: **on any target the library already contains, a closure rate measured
without a circularity check measures the library.**

The three that closed nothing — `mfderiv_bijective`, `ContDiff.sigmoid`,
`IsScott.isUpperSet_of_isOpen` — are the honest residue: real statements where
the portfolio is simply not strong enough, and where a plan would have to
decompose rather than search.

## What 15/40 is and is not evidence of

**It is** evidence that the automatic path closes real, unchosen statements
without being handed the answer, at a rate anyone can reproduce with two
commands.

**It is not** evidence of proving anything hard. Nine of the fifteen are `rfl` —
definitional lemmas that are true by unfolding. Five are `simp`. The batch says
the machinery runs end to end on arbitrary library material and that its
guardrail against self-citation works; it does not say the search is strong.

## Defects this batch found

Running it was worth more than the number. It surfaced six real defects that
every component suite passed through:

1. `corpus.py` read `WITSOC2_PREMISE_CORPUS` while the builder and `produce.py`
   advertised `WITSOC2_MATHS_CORPUS` — the documented setup silently returned
   all-SEARCH_TARGET.
2. `tactic_search` ignored diagnostics that fell outside every candidate's line
   range, so a file that failed to parse reported the whole portfolio closing
   the goal in 0.6 seconds.
3. Candidates were anonymous `example`s. A tactic that closed the `example` left
   a `sorry` in the named theorem the audit read — the search was validating a
   different statement from the artifact.
4. `public meta import` matched none of the expected prefixes and got a second
   `import` prepended.
5. The circularity audit compared fully-qualified names while `#print` renders
   the shortest unambiguous one, so a proof that was nothing but a citation of
   its own target passed.
6. The scanner read prose. A doc comment containing the word "section" at the
   start of a line opened a scope that never closed.
7. `#print` renders universe parameters as `name.{u}`, and the block splitter
   swallowed the trailing dot — so the audit had been scanning Lean's ENTIRE
   output rather than the declaration it was asked about. Safe in the direction
   that mattered for a forbidden-name check, and wrong for anything needing
   that one term.

## Two earlier single-target campaigns

`attempt_1_failed.json` proposed induction with the standard recurrence and the
kernel refused: `unsolved_goal: omega could not prove the goal`. It was
classified `formalization_block`, the gap classifier named the
`formalization_target` axis, a revision request named the step and the edit, and
working memory recorded a revival condition — so re-running that blueprint is
refused before anything is produced. `attempt_2_admitted.json` declared the
recurrence as an external dependency, the pre-flight resolved it, five blocking
gates passed, and the campaign was admitted `VERIFIED`.

The interesting part was never that attempt 2 passed. It is that attempt 1
failed *informatively*: a named step, a named axis, and an edit.

## Reproduce

```bash
export WITSOC2_LEAN_PROJECT=~/mathlib4
export WITSOC2_MATHS_CORPUS=corpus.json          # optional; adds type-aliases
python3 draw_targets.py --src ~/mathlib4/Mathlib --n 40 --seed 31337 --out batch40.json
python3 run_batch.py --targets batch40.json --workers 3 --out batch40_results.json

python3 ../../scripts/produce.py --blueprint attempt_1_failed.json --tier kernel
python3 ../../scripts/produce.py --blueprint attempt_2_admitted.json --tier kernel
```
