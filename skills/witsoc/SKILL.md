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

The host transports; Witsoc owns target, route, frontier, and evidence. Roles
are workers. Runtime code is the pinned `witsoc-core` package, not skill data.

The Git skill keeps only this file, `ARCHITECTURE.md`, and three role folders.
First use installs the pinned core privately. `witsoc-setup` then hydrates its
resources in the global skill root and activates `witsoc` (maths) and
`witsoc-bio` (biology). Later calls verify the installation idempotently.

Resolve the installed root and complete setup before any Witsoc command:

```bash
if [ -n "${WITSOC_SKILL_DIR:-}" ]; then
  WITSOC_ROOT="$WITSOC_SKILL_DIR"
elif [ -f "$HOME/.openscientist/strings/skills/witsoc/SKILL.md" ]; then
  WITSOC_ROOT="$HOME/.openscientist/strings/skills/witsoc"
elif [ -n "${PLANE_TOOL_BIN:-}" ]; then
  WITSOC_ROOT=$(dirname "$("$PLANE_TOOL_BIN" skill-which witsoc/SKILL.md)")
elif command -v plane-tool >/dev/null 2>&1; then
  WITSOC_ROOT=$(dirname "$(plane-tool skill-which witsoc/SKILL.md)")
else
  WITSOC_ROOT="$HOME/.openscientist/skills/witsoc"
fi
export WITSOC_SKILL_DIR="$WITSOC_ROOT"

CORE_VERSION="0.0.3"
CORE_SHA256="bfa2d02211e91035dabb34e2ce98d8ca1a3944f865c62121e10932344eb6f791"
CORE_ENV="${WITSOC_CORE_HOME:-$HOME/.openscientist/witsoc-core}/$CORE_VERSION"
CORE_PYTHON="$CORE_ENV/bin/python"
if ! "$CORE_PYTHON" -c \
  'import importlib.metadata,sys; sys.exit(importlib.metadata.version("witsoc-core") != sys.argv[1])' \
  "$CORE_VERSION" >/dev/null 2>&1; then
  python3 -m venv --clear "$CORE_ENV" || exit $?
  CORE_SOURCE="$WITSOC_ROOT/../../packages/witsoc-core"
  if [ -f "$CORE_SOURCE/pyproject.toml" ]; then
    "$CORE_PYTHON" -m pip install --disable-pip-version-check --no-input --no-deps \
      "$CORE_SOURCE" || exit $?
  else
    printf '%s\n' "witsoc-core==$CORE_VERSION --hash=sha256:$CORE_SHA256" \
      > "$CORE_ENV/witsoc-core.requirements.txt"
    "$CORE_PYTHON" -m pip install --disable-pip-version-check --no-input --no-deps \
      --only-binary=:all: --require-hashes \
      -r "$CORE_ENV/witsoc-core.requirements.txt" || exit $?
  fi
fi
"$CORE_ENV/bin/witsoc-setup" --skill-root "$WITSOC_ROOT" --quiet || exit $?
WITSOC="$CORE_ENV/bin/witsoc"
```

The local branch supports frontend/backend development; normal installs use the
hash-pinned PyPI wheel. Setup must finish; never continue core-only.

## Route And Bind

Maths is the `maths` pack from PyPI `witsoc`; biology is `bio` from
`witsoc-bio`. First-use setup installs both into
`~/.openscientist/strings/skills/witsoc/domains/`; routing re-verifies and
reactivates a missing pinned pack. Never continue core-only after
`UNRESOLVABLE` or `ACTIVATION_FAILED`.

For a catalogued problem, put only its source-canonical mathematical statement
in `request.txt`; keep run paths, role instructions, and deliverables in the
objective or constraints.

Before creating the task directory:

```bash
TASK_REL="runs/<task>"; ACT="$KIMI_WORK_DIR/.witsoc-activation-<task>.json"
"$WITSOC" orchestrator-preflight --statement-file request.txt \
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
"$WITSOC" start --statement-file request.txt \
  --objective '<required outcome>' --preflight "$ACT" \
  --out "$TASK/frontier.json" --target-out "$TASK/target.json"
"$WITSOC" orchestrator-next --state "$TASK/frontier.json"
```

`start` consumes the receipt and cannot reroute. Run `orchestrator-next` before
launch, after return, and before exit; only it grants launch or completion.
`CAMPAIGN_RECONCILIATION` forbids both.

Open work follows:

`Explorer -> sealed authorization/handoff -> Researcher -> typed return/delta -> Explorer`

Explorer freezes target/sources, maintains the minimal-core DAG, issues one
route, and arbitrates returns. Its acceptance contract preserves endpoint,
quantifier, boundary, exclusion, evidence, and generalization clauses.

Researcher verifies v4 bindings, loads domain resources, keeps state read-only,
and runs `reasoning-check` then `delta-build`. It cannot reframe or grant status;
each closure candidate must satisfy clause-level `target_fidelity`.

Use the exact status vocabulary in `references/status_vocabulary.md`.
Candidates return through a distinct `VERIFY` route before admission.

Only one episode may be pending. Only its sealed delta is a return; re-enter
Explorer immediately. Parallel work needs `STRONG` independence across route,
actor, resources, and failure domain.

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

Schemas are machine contracts selected through `contracts/type-registry.json`;
agents do not load them as general instructions. Load `references/memory.md`
only when the `research-memory` capability is selected.
