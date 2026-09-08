---
name: witsoc
description: "Open-problem discovery, status synthesis, and verification for hard mathematics and biology, including asymptotic questions, causal biological mechanisms, perturbations, replication, and generalization. Use automatically for hard/open domain work, even when not named. Activation is sticky and known-results framing never deselects Witsoc. Stack with orchestration skills such as autoresearch, but keep an explicit Witsoc loop in the current invocation rather than a nested deep run. Treat witosc and witsoc-* as Witsoc; exclude routine coding and ordinary summaries."
metadata:
  skill-author: OpenScientist
---

# Witsoc

Freeze one target, retain one replayable frontier, and keep search separate from
evidence-backed status.

## Activation

Activation is sticky for hard/open work. Source labels may select
`SOURCE_SYNTHESIS`; they never deselect Witsoc. Stay in Witsoc.
Autoresearch can schedule retrieval but cannot replace Witsoc.
The current invocation owns that loop.
Do not launch a nested root orchestrator or a new deep run unless asked.
A dispatch acknowledgment is not Witsoc completion.

The host schedules and transports; Witsoc owns target, route, domain, frontier,
packets, and evidence. Roles are worker resources, not root agents.

Resolve the installed root:

```bash
if [ -n "${WITSOC_SKILL_DIR:-}" ]; then
  WITSOC_ROOT="$WITSOC_SKILL_DIR"
elif [ -n "${PLANE_TOOL_BIN:-}" ]; then
  WITSOC_ROOT=$(dirname "$("$PLANE_TOOL_BIN" skill-which witsoc/SKILL.md)")
elif command -v plane-tool >/dev/null 2>&1; then
  WITSOC_ROOT=$(dirname "$(plane-tool skill-which witsoc/SKILL.md)")
elif [ -f "$HOME/.openscientist/strings/skills/witsoc/SKILL.md" ]; then
  WITSOC_ROOT="$HOME/.openscientist/strings/skills/witsoc"
else
  WITSOC_ROOT="$HOME/.openscientist/skills/witsoc"
fi
WITSOC="$WITSOC_ROOT/scripts/witsoc.sh"
[ -x "$WITSOC" ] || { echo "witsoc skill not found" >&2; exit 2; }
```

## Route And Bind

Maths is the `maths` pack from PyPI `witsoc`; biology is `bio` from
`witsoc-bio`. Routing installs and activates a missing pinned pack. Never
continue core-only after `UNRESOLVABLE` or `ACTIVATION_FAILED`.

For a catalogued problem, put only its source-canonical mathematical statement
in `request.txt`; keep run paths, role instructions, and deliverables in the
objective or constraints.

Before creating the task directory:

```bash
TASK_REL="runs/<task>"; ACT="$KIMI_WORK_DIR/.witsoc-activation-<task>.json"
bash "$WITSOC" orchestrator-preflight --statement-file request.txt \
  --objective '<required outcome>' --workspace-root "$KIMI_WORK_DIR" \
  --task-dir "$TASK_REL" --plane-tool "$PLANE_TOOL_BIN" --out "$ACT"
```

Require `PREFLIGHT_READY` and execute every returned `skill_view_argv`. Plane
paths start with `witsoc/`; local reads use `WITSOC_ROOT`. Domain role labels
are never skill locators. Open discovery must load root, mode, Explorer,
Researcher, and selected domain resources. The sealed receipt binds exact
resource/package digests, domain, route, target, workspace, and return policy.

## Protected Loop

```bash
TASK="$KIMI_WORK_DIR/$TASK_REL"; mkdir -p "$TASK"
bash "$WITSOC" start --statement-file request.txt \
  --objective '<required outcome>' --preflight "$ACT" \
  --out "$TASK/frontier.json" --target-out "$TASK/target.json"
bash "$WITSOC" orchestrator-next --state "$TASK/frontier.json"
```

`start` consumes the receipt and cannot reroute. Run `orchestrator-next` before
launch, after return, and before exit; only it grants launch or completion.
`CAMPAIGN_RECONCILIATION` forbids both.

Open work follows:

`Explorer -> sealed authorization/handoff -> Researcher -> typed return/delta -> Explorer`

Explorer is control-only: it freezes target/sources, maintains the minimal-core
DAG, ranks non-recoupling proposals, issues one route, and arbitrates returns.
Its sealed acceptance contract has atomic endpoint, quantifier, boundary,
exclusion, evidence, and generalization clauses plus semantic distinctions. In
a negative target, derivation non-use and global nonexistence differ unless both
directions are proved. After two `ROOT` attacks, dispatch requires a real child.

Researcher requires matching v4 authorization, verifies bindings, loads domain
doctrine/operators, keeps state read-only, and runs `reasoning-check` then
`delta-build`. It cannot reframe, dispatch, or grant status. It separates
`TARGET` from route `OBJECTIVE` and completes clause-level `target_fidelity` for
each closure candidate; a result missing any clause remains local.

Use `CANDIDATE_PRODUCT` for an endpoint-shaped result awaiting review,
`ROUTE_REFUTED` only for a false assigned objective, `METHOD_BARRIER` for a
scoped mechanism failure, `CORE_SHARPENED` for a stricter residual, and
`TARGET_FALSIFIED` only for the frozen target. Candidates return through a
distinct `VERIFY` route before admission.

Only one episode may be pending. Only its sealed delta is a return; re-enter
Explorer immediately. Parallel work needs `STRONG` independence across route,
actor, resources, and failure domain.

Handoff text has no 4,096-character truncation. Preserve claims, objectives,
failure conditions, and returns; carry one selected portfolio row and
content-addressed references rather than rejected portfolios or transcripts.

Retries need a changed axis and revival evidence. `NO_PROGRESS` is not
exhaustion. Prefer `PAUSE_WITH_FRONTIER`; stop needs scoped search coverage,
no unresolved route, retained alternatives, and independent control review.

## Review And Exit

After terminal arbitration, run `campaign-audit`. `DIRECT_ANSWER` requires an
independent review of exact product bytes with distinct failure domains. Run
`finalize`, then pass its packet to `orchestrator-next`; later edits invalidate
review and finalization.

Exact activation, issue, return, round, stop, review, recovery, and finalization
commands are in `references/orchestrator_protocol.md`. Use `legacy-audit` for
old packets; do not import them as active authority. Only reducer admission
moves status. Search may speculate; status may not.
