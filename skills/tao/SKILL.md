---
name: tao
description: Explanatory teacher for higher-reasoning and complex work. Load whenever the task involves deep or multi-step reasoning — research problems, proofs, difficult analysis or debugging, dense papers, intricate systems, long agent runs — so the reasoning gets taught, not just performed; and always on an explicit request to explain ("explain what is done here", "break this down", or invocation by name). Breaks the material into simpler terms in three passes — first map and explain the prerequisites, then explain each step carefully in plain language, then lay out what can be done next in the research. Gathers missing background from the internet and, where the harness supports it, delegates lookups to other workers or subagents; load-bearing claims are cross-checked against independent sources before they are taught. Writes the full explanation into report.md as it goes. Skip it for trivial or purely mechanical tasks (one-line questions, small edits, routine commands) where a structured explanation adds nothing.
compatibility: Works in Codex, Claude Code, OpenScientist, and generic Agent Skills clients. No required external tools. Web/literature search and worker/subagent delegation are used when available for gap-filling and cross-checking; without them the skill still runs and marks unverified claims as such.
metadata:
  skill-author: OpenScientist
category: research
---

# Tao — the explanatory teacher

This skill activates in two situations:

- **Explicit request** — the user asked for an explanation of something: the
  work done here, a paper, a proof, a codebase, a result. The "something" is
  whatever they pointed at; "what is done here" means the current repository
  or session's work.
- **Complex work in progress** — the current task itself demands higher
  reasoning: an open research problem, a proof campaign, a dense paper, a
  gnarly debugging or analysis job, a long multi-agent run. Here Tao rides
  alongside the main task: the material to explain is the work being done,
  and the report grows as the work does, so the reasoning is taught rather
  than merely performed. Tao never replaces the main task or changes its
  outcome — it only documents and explains it.

If the task is trivial or mechanical, do not activate — an explanation
nobody needs is noise.

You are teaching, not summarizing. A summary compresses; a teacher decompresses:
every claim gets unpacked until a motivated reader one level below the material
can follow it. The deliverable is a single living document, `report.md`, built
in three passes: **prerequisites → step-by-step explanation → future work**.

## 0. Scope the lesson

1. Identify the material: a paper, proof, algorithm, codebase, experimental
   result, or informal topic description. Read it fully before explaining any
   of it. If it is a directory or repo, skim the entry points (README, main
   modules) first, then read the parts the explanation will actually cover.
2. Identify the audience level. If the user stated one, use it. Otherwise
   default to "smart reader one level below the material" (e.g. a strong
   undergraduate for a graduate paper) and say so in the report.
3. Resolve the report target, in this order:
   - a path the user named explicitly;
   - `$PLANE_SESSION_DIR/report.md` when that variable is set (OpenScientist —
     the frontend reads this file live);
   - `./report.md` in the working directory otherwise.
   If the target already exists and was not produced by this skill, do not
   overwrite it — append a new top-level section or ask for a path.
4. Create `report.md` immediately from `assets/report_template.md`, with the
   TL;DR and section headers stubbed in. Update it after every pass below, not
   once at the end — partial explanations are useful; a report that appears
   only at the end is not.

### 0.1 Showing the explanation in OpenScientist

When `$PLANE_SESSION_DIR` is set, the OSci frontend is the audience surface:
the deep-run window renders `$PLANE_SESSION_DIR/report.md` live through the
plane files API — writing that file *is* showing the explanation to the
user. To display correctly:

1. Load `planning-with-files` first and follow its file discipline; this
   skill owns only the content of the explanation, not the bookkeeping.
2. Write `$PLANE_SESSION_DIR/report.md` first, before any mirror — the user
   sees it on the next poll. Update it at the end of every pass, not once at
   the end of the run.
3. Register the report in `$PLANE_SESSION_DIR/plan.json` under `artifacts`
   as `{ "artifact": "report.md", "label": "Report" }` so it appears as the
   Report tab, and append one line to `progress.md` per completed pass.
4. Respect the single-writer rule: only the orchestrator writes
   `$PLANE_SESSION_DIR` files. A worker running this skill writes the
   explanation into its own scratch directory and mails the orchestrator a
   pointer; the orchestrator transcribes into the canonical `report.md`.

A complete example of what the rendered report should look like is
`references/example_report_erdos359.md` — an explanation of an agent run on
Erdős problem #359, in exactly the template's shape.

## 0.5 Gather and cross-check — runs alongside every pass

The source material alone is rarely complete. Before teaching a claim,
make sure you actually have it and that it holds up:

1. **Fill gaps from the internet.** When the material assumes background it
   does not contain, or asserts something without justification, search the
   web/literature for the missing piece. Everything consulted goes into
   *Sources*, and the explanation marks it: "context added from [source]".
2. **Delegate to other workers.** When the harness provides subagents or
   workers (OpenScientist scouts, Claude Code agents, or similar), fan
   independent lookups out to them instead of serializing: one worker per
   gap or per claim to verify, each returning a short cited answer. Under
   OpenScientist, respect the platform's admission/budget guards before
   spawning; with no delegation available, do the lookups yourself in
   priority order and note anything left unchecked.
3. **Cross-check load-bearing claims.** A claim is load-bearing if the
   explanation collapses when it is wrong (a central theorem, a headline
   number, a key design fact). Each one needs either two independent
   sources that agree, or one source plus a direct check you performed
   (rerun the computation, verify the special case by hand, read the code
   path). Sources citing each other are one source, not two.
4. **Report disagreements, do not resolve them silently.** If sources
   conflict, or a worker's finding contradicts the material, the report
   presents both with citations and says which reading the explanation
   follows and why. Verification status belongs in the report: cross-checked
   claims cite their evidence; unverified ones are marked "not independently
   verified".

Detailed procedure — source independence, worker prompt shape, verification
ladder — is in `references/gathering_and_crosschecking.md`.

## 1. Pass one — prerequisites

Before explaining a single step, answer: *what must the reader already
understand for the explanation to land?*

1. List every concept, definition, technique, or prior result the material
   leans on. Walk the material claim by claim and ask "what does this line
   assume?" — the honest list is longer than the polite list.
2. Order the list dependency-first: if concept B is defined in terms of
   concept A, A comes first.
3. For each prerequisite write, in the report's *Prerequisites* section:
   - **What it is** — one to three sentences in plain language, no undefined
     jargon.
   - **Why this material needs it** — the specific step that uses it.
   - **Where to learn more** — a standard reference, if one exists.
4. Mark each prerequisite `[core]` (explanation collapses without it) or
   `[helpful]` (adds depth but skippable). A reader should be able to read
   only the `[core]` entries and still follow pass two.

Rule for the whole document: **the first use of any technical term is either
defined in place or listed in Prerequisites.** No third option.

## 2. Pass two — explain each step

Decompose the material into its natural steps: sections of a paper, lemmas of
a proof, stages of a pipeline, modules of a codebase. For each step write, in
the report's *Step-by-step Explanation* section:

1. **Plain statement** — what this step says or does, in one or two everyday
   sentences before any notation.
2. **Why it is here** — what breaks in the overall argument or system if this
   step is removed. This is the sentence readers most often need and authors
   most often omit.
3. **How it works** — the careful walkthrough. Introduce notation only after
   the idea; connect explicitly back to the prerequisites it uses ("this is
   where [core] concept X does its work").
4. **Concrete anchor** — a small worked example, special case, analogy, or
   numeric instance. Prefer a degenerate case the reader can verify by hand.
5. **Common trap** — the misreading a newcomer is most likely to make, and
   why it is wrong.

Techniques for keeping the explanation honest — layered depth, analogy
discipline, misconception handling — are in
`references/explanation_techniques.md`; read it if a step resists plain
language. If, while explaining, you find a claim you cannot justify from the
material, say so in the report ("the paper asserts this without proof")
rather than papering over it. Teaching a gap as if it were solid is the one
failure mode this skill must never have.

## 3. Pass three — future directions

End by opening the door forward. In the report's *Future Directions* section:

1. **Open questions the material itself raises** — limitations the authors
   admit, assumptions that look removable, cases not covered.
2. **Natural extensions** — what a researcher could attempt next, each with
   one sentence on why it is plausible and one on what makes it hard.
3. **What this enables** — downstream work or applications that become
   possible if the material holds up.
4. Mark each item with an effort guess: `[weekend]`, `[months]`, or
   `[open problem]`. Guesses are fine; unlabeled wishlists are not.

## 4. Finish

1. Fill the report's *Glossary* (every defined term, one line each) and
   *Sources* (everything read, with paths/URLs).
2. Reread the report top to bottom as the target reader. Any sentence that
   needs a second read gets rewritten. Any term that appears before its
   definition gets moved or defined.
3. Stop when the report answers all three reader questions: "what do I need
   to know first?", "how does it actually work?", and "what could be done
   next?". The report structure contract lives in
   `references/report_structure.md`.

Escalate to the user only when the source material is genuinely ambiguous
about its own claims, or when the audience level materially changes what the
explanation should contain and no default is defensible.
