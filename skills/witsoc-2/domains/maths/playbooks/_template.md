# Playbook: <subfield>

A playbook is a cold-start kit. Its job is to stop a campaign spending its first
week rediscovering the standard examples, the standard tools, and the three
barriers everyone in the area already knows about.

Copy this file, keep the six sections and their order, delete this header block.

## Scope

One line, beginning "Use for ...", listing the problem shapes that route here.
It is a routing trigger, so it must name recognizable features of a *statement*
(sumsets, divisor sums, forced monochromatic structure), not a mood.

If two playbooks both match, load both and record the split. A frontier problem
sitting between two areas usually breaks along that seam.

## First objects to test / First normalizations

Combinatorial areas get **objects**: the families a claim is tested against
before anything is attempted. Arithmetic and analytic areas get
**normalizations**: the rewritings applied before a claim is even readable.

Rule for the list: every entry must be a family or a rewriting someone can
actually construct in an hour. "Random graphs" qualifies; "hard instances" does
not. These are the inputs to refutation-first, so a vague entry costs a pass.

## Theorem families

Seven to nine named tools, as a table with what each one buys and what it costs.

| Tool | Buys | Costs |
|---|---|---|

The cost column is the load-bearing one. A tool listed without its loss —
the constant, the logarithm, the tower-type dependence, the unmet precondition —
invites the campaign to plan a route that cannot reach the target's precision.
Name the actual theorem, not the technique class.

## Common barriers

Five to seven, each stated as a **mechanism**, not a label.

"Container bounds lose constants and logarithms because the container family has
size exp(loss) and every container is counted" is a mechanism: it predicts when
the barrier appears and suggests what would dodge it. "Counting barrier" is a
label: it names the corpse.

The test is whether the sentence tells you which attempts will die. If it does
not, it is not finished.

## First experiments

Exactly five concrete computations, each runnable without new theory. Say what
is enumerated, over what range, and what outcome would change the plan.

An experiment whose every outcome leaves the campaign unchanged is not an
experiment; it is a chore. Cut it and find one that discriminates.

## Product ladder

Six or seven rungs, specialized to this area — the general ladder in
`doctrine/researcher.md` already exists and does not need repeating. A rung
earns its place by naming the *form* of the deliverable here: which special
class, which bounded parameter, which known theorem the reduction targets.

Each rung needs a verification route, and each failed rung must teach a barrier
or demote a false strengthening. A rung that can fail without anyone learning
anything is not on the ladder.

## Required outputs of a domain pass

Whatever the subfield, loading a playbook must produce: a theorem-family
shortlist, the standard extremal examples, the likely-false stronger variants,
computation and search templates, the first three lemmas to try, and the known
barriers with the form they take here.
