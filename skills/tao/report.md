# Tao 0.1.0 Report

## Objective

Add a portable "explanatory teacher" skill (named Tao) that breaks any
research material — paper, proof, algorithm, codebase, or result — into
simpler terms. It activates on an explicit request to explain (e.g.
"explain what is done here") and loads automatically alongside
higher-reasoning or complex tasks — research problems, proof campaigns,
dense papers, difficult analysis, long agent runs — so the reasoning is
taught as the work happens, without changing the main task's outcome. It
skips trivial or mechanical tasks. The skill works in three fixed passes: map and explain the
prerequisites first, then explain each step carefully in plain language,
then lay out future directions for the research. Its single deliverable is
a `report.md` that is kept valid throughout the run.

## Changes

- Added `SKILL.md` defining the three-pass workflow:
  - Pass one builds a dependency-ordered prerequisite map; every entry
    states what the concept is, why the material needs it, and where to
    learn more, tagged `[core]` or `[helpful]`.
  - Pass two explains each step with a fixed shape: plain statement, why
    it is here, how it works, concrete anchor, common trap. Gaps in the
    source material are reported as findings, never papered over.
  - Pass three lists open questions, natural extensions, and enabled
    downstream work, each tagged with an effort guess (`[weekend]`,
    `[months]`, `[open problem]`).
  - A document-wide invariant: the first use of any technical term is
    either defined in place or listed in Prerequisites.
- Added a gather-and-cross-check stage that runs alongside every pass:
  missing background is filled from the internet with mandatory citation
  ("context added from [source]"); where the harness supports it,
  independent lookups fan out to workers/subagents (read-only, one gap or
  claim each, admission guards respected under OpenScientist); every
  load-bearing claim needs a direct check or two independent sources, and
  source disagreements are reported side by side, never silently resolved.
- Added `references/gathering_and_crosschecking.md`: lookup triggers,
  primary-source preference, worker prompt shape per harness, the
  four-rung verification ladder (direct check → two independent sources →
  single source → unverified assertion), and disagreement handling.
- Added an explicit OpenScientist display path (SKILL.md §0.1): under a
  plane session the skill stacks on `planning-with-files`, writes
  `$PLANE_SESSION_DIR/report.md` first (the deep-run window renders it
  live), registers it in `plan.json` artifacts as the Report tab, appends
  one `progress.md` line per pass, and follows the single-writer rule
  (workers write scratch and mail pointers; the orchestrator transcribes).
- Added `references/example_report_erdos359.md`: a complete worked example
  of the report format — an explanation of an agent run on Erdős problem
  #359 (MacMahon's sequence, OEIS A002048), demonstrating prerequisite
  tagging, the five-part step shape, effort-tagged future directions, and
  per-claim verification status.
- Added `references/explanation_techniques.md`: layered depth (sentence →
  paragraph → precise statement), analogy discipline (state where the
  analogy breaks), concrete-anchor selection, misconception handling,
  prerequisite honesty, and rules for gaps and disputed claims.
- Added `references/report_structure.md`: the `report.md` section contract
  (TL;DR, Prerequisites, Step-by-step Explanation, Future Directions,
  Glossary, Sources), target-path resolution, incremental update rules,
  and a density floor instead of a length cap.
- Added `assets/report_template.md`: the stub the skill instantiates
  before pass one so the report exists from the start of the run.

## Platform grounding

The report-target rules were checked against the OpenScientist platform
(read-only; no changes made there):

- The backend stores run files such as `report.md` as execution artifacts
  served to the frontend (`backend/src/core/assets/artifacts_manager.py`,
  `backend/src/files/routes.py`), and its citation checker reads
  `/artifacts/report.md` by default (`backend/src/cortex/workflows.py`).
  Keeping the deliverable named `report.md` and valid at every point in
  the run means the frontend and downstream checkers can consume it live.
- The theater-code-server orchestrator spec makes `report.md` an
  orchestrator-owned file in the shared session pool
  (`theater-code-server/docs/spec/agents/orchestrator.md`), and skills are
  synced into sessions from `SKILL.md` frontmatter + body
  (`theater-code-server/src/kimi_cli/theater/sync.py`,
  `src/kimi_cli/skill/__init__.py`). The skill therefore resolves its
  report target as: explicit user path, else `$PLANE_SESSION_DIR/report.md`
  under OpenScientist (workers write scratch and mail a pointer instead of
  writing orchestrator-owned files), else `./report.md` — with a rule to
  never overwrite a `report.md` it did not create.

## Portability

No required external tools; web search and worker/subagent
delegation are used when available and degrade gracefully — without them
the skill still runs and marks unverified claims as such. No hardcoded
OpenScientist paths — the `$PLANE_SESSION_DIR` branch is a fallback, not a
dependency, per `docs/authoring-workflows.md`. Usable as a selected folder
in Claude Code (`.claude/skills`), Codex (`.agents/skills`), and generic
Agent Skills clients.
