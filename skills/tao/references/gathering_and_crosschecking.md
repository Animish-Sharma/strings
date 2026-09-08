# Gathering and Cross-checking Information

Read this when a gap or a doubtful claim surfaces during any pass. The rule
of thumb: the skill teaches nothing it has not either verified or explicitly
labeled as unverified.

## When to go beyond the source material

Trigger an external lookup when:

- the material assumes background it does not contain and you cannot state
  that background precisely from what is on hand;
- the material asserts a fact, number, or prior result without justification
  and the explanation leans on it;
- two parts of the material appear to contradict each other;
- a step resists a concrete anchor — often a sign the underlying claim is
  wrong or misstated, not just hard.

Do not trigger lookups for facts the material itself proves or that the
target reader can verify from the report alone. Gathering is in service of
the explanation, not a literature review for its own sake.

## Using the internet

- Prefer primary sources: the cited paper itself, official docs, the
  upstream repository — over blog posts and secondary summaries.
- Record, for every consulted source: what claim it supports, the URL or
  identifier, and (for volatile pages) the date accessed. All of it goes in
  the report's *Sources* section.
- Distinguish in the report between the material's own content and added
  context: "context added from [source]". The reader must be able to tell
  what the original says from what you brought in.

## Delegating to other workers

When the harness supports subagents or workers, use them for breadth —
independent lookups in parallel rather than one long serial search.

Per-worker prompt shape (one gap or one claim per worker):

```
QUESTION: <the single gap or claim, stated precisely>
CONTEXT: <one or two sentences on why the explanation needs it>
RETURN: a short answer with ≤3 cited sources (URL or DOI per claim),
        plus a one-line confidence note. Raw facts only.
DO NOT: edit any files; browse beyond the question.
```

Harness notes:

- **OpenScientist**: use scout-style read-only workers. Check the platform's
  admission/budget guard before spawning; if spawning is blocked, serialize
  the lookups yourself. Workers write to their own scratch space and return
  pointers; you transcribe into the report — under a running session the
  orchestrator remains the only writer of the session's report.md.
- **Claude Code / Codex**: read-only search subagents fill the same role.
- **No delegation available**: do the lookups yourself in priority order
  (load-bearing claims first) and list anything left unchecked in the
  report rather than dropping it silently.

Treat worker output as leads, not verdicts: a worker's cited answer still
counts as one source in the independence arithmetic below.

## The verification ladder

For each load-bearing claim, use the strongest rung you can reach and record
which rung it was:

1. **Direct check** — rerun the computation, execute the code path, verify
   the special case by hand, rederive the bound. Strongest; one direct
   check suffices on its own.
2. **Two independent sources** — independent means separate origins: a
   paper and a textbook, the spec and a conforming implementation. A survey
   citing the original paper is the same origin as the paper. Model or
   worker consensus without citations is zero sources.
3. **One source, no check** — acceptable for `[helpful]` background; a
   load-bearing claim resting here is marked "not independently verified"
   in the report.
4. **Nothing found** — the claim is taught only as the material's assertion:
   "the paper states, and I could not verify, that ...".

Non-load-bearing claims need rung 3; do not spend the run pushing every
sentence to rung 1.

## When checks disagree

- Present both findings with citations, side by side, in the affected step.
- Say which reading the explanation follows and give the one-sentence
  reason (newer result, primary beats secondary, direct check beats quote).
- If the disagreement flips a conclusion of the material, promote it out of
  the step into the TL;DR and *Future Directions* — a contradicted central
  claim is a finding about the material, and resolving it is future work.
- Never average conflicting numbers or blend conflicting statements into
  one confident sentence.
