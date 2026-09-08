# report.md Structure Contract

The report is the skill's single deliverable. Start it from
`assets/report_template.md` and keep it valid at every point in the run —
readers (including the OpenScientist frontend, which renders the session's
`report.md` live) may open it before the run finishes.

## Target resolution

1. A path the user named explicitly.
2. `$PLANE_SESSION_DIR/report.md` when running under OpenScientist — this is
   the run-files directory the frontend reads; the orchestrator owns these
   files, so a worker running this skill writes to its own scratch directory
   and mails the orchestrator a pointer instead.
3. `./report.md` otherwise.

Never overwrite a `report.md` this skill did not create. Append a new
top-level `# Explaining: <topic>` section, or ask for a different path.

## Required sections, in order

| Section | Contract |
|---|---|
| Title + metadata line | Topic, date, audience level, and source material paths/URLs. |
| TL;DR | At most five sentences, zero undefined jargon. A reader who stops here still knows what the material claims and why it matters. |
| Prerequisites | Dependency-ordered list. Each entry: what it is, why this material needs it, where to learn more, tagged `[core]` or `[helpful]`. |
| Step-by-step Explanation | One subsection per step. Each: plain statement, why it is here, how it works, concrete anchor, common trap. |
| Future Directions | Open questions, extensions, and enabled work, each tagged `[weekend]`, `[months]`, or `[open problem]`. |
| Glossary | One line per term defined anywhere above, alphabetical. |
| Sources | Everything read, including material consulted beyond the source, with paths or URLs. |

## Incremental update rules

- Create the file with stubbed headers before pass one begins.
- After each pass, its section is complete; earlier sections may be revised
  (pass two often reveals a missing prerequisite — add it, do not inline it).
- The TL;DR is written twice: a draft when scoping, a rewrite at finish.
- Flagged gaps ("stated without proof", "context added from ...") stay in the
  final report. They are findings, not blemishes.

## Length discipline

There is no length cap, but there is a density floor: every paragraph must
either explain, anchor, or connect. Delete paragraphs that only narrate the
document itself ("in this section we will ..."). If a single step's
explanation exceeds roughly a page, split the step.
