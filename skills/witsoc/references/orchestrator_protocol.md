# Orchestrator Protocol

Plane schedules; Witsoc owns state.

## Activate

Seal preflight before creating the task directory:

```bash
TASK_REL="runs/<task>"; TASK="$KIMI_WORK_DIR/$TASK_REL"
ACT="$KIMI_WORK_DIR/.witsoc-activation-<task>.json"
bash "$WITSOC" orchestrator-preflight --statement-file request.txt \
  --objective '<required outcome>' --workspace-root "$KIMI_WORK_DIR" \
  --task-dir "$TASK_REL" --plane-tool "$PLANE_TOOL_BIN" --out "$ACT"
```

Require `PREFLIGHT_READY`; execute every `skill_view_argv`:

```bash
mkdir -p "$TASK"; STATE="$TASK/frontier.json"; SM="$TASK/source-map.json"
EX="$TASK/explorer.json"; EP="$TASK/episode.json"
bash "$WITSOC" start --statement-file request.txt \
  --objective '<required outcome>' --preflight "$ACT" \
  --out "$STATE" --target-out "$TASK/target.json"
bash "$WITSOC" orchestrator-next --state "$STATE"
```

Revision zero initializes; reconcile `CAMPAIGN_RECONCILIATION` first.

## Issue

```bash
bash "$WITSOC" source-map-draft --state "$STATE" \
  --source-map-id sources-001 --checked-at '<ISO-8601>' \
  --out "$TASK/source-map.draft.json"
bash "$WITSOC" source-map-check --state "$STATE" \
  --input "$TASK/source-map.draft.json" --out "$SM"
bash "$WITSOC" explorer-draft --state "$STATE" \
  --proposals "$TASK/proposals.json" --out "$TASK/explorer.draft.json"
# Refine acceptance clauses/distinctions and domain controls; retain baselines.
bash "$WITSOC" explorer-check --state "$STATE" \
  --input "$TASK/explorer.draft.json" --proposals "$TASK/proposals.json" \
  --source-map "$SM" --out "$EX"
bash "$WITSOC" episode-issue --state "$STATE" --write \
  --explorer-state "$EX" --proposals "$TASK/proposals.json" \
  --source-map "$SM" --episode-id E001 --episode-out "$EP"
bash "$WITSOC" orchestrator-handoff --state "$STATE" --episode "$EP" \
  --source-map "$SM" --workspace-root "$KIMI_WORK_DIR" --task-dir "$TASK"
bash "$WITSOC" orchestrator-next --state "$STATE" \
  --handoff "$TASK/researcher-handoff.json"
```

`launch_argv` grants launch. V4 binds state, sources, domains, authorization,
return. Handoff has no 4,096-character truncation; carry one selected row
and sealed refs.

## Return

The worker fills reasoning state and all `target_fidelity` clauses/distinctions,
then runs `reasoning-check` and `delta-build --handoff`. Use
`ROUTE_REFUTED` for a false route objective and `CANDIDATE_PRODUCT` for complete
endpoint coverage awaiting verification; neither grants target status.

```bash
DELTA="$TASK/research-delta.json"
bash "$WITSOC" orchestrator-next --state "$STATE" --delta "$DELTA"
bash "$WITSOC" episode-return --state "$STATE" --write --delta "$DELTA"
bash "$WITSOC" orchestrator-next --state "$STATE"
```

Require `EXPLORER_RETURN_ARBITRATION`; rebuild with `--prior-explorer`. Parallel
rounds need `STRONG` independence, bound deltas, merge, and arbitration.

## Stop And Exit

`HONEST_STOP` binds distinct review through arbitration, scoped to
`CURRENT_AUTHORIZED_SEARCH_ONLY`.

Terminal arbitration leads to `BUILD_FINALIZATION`. Run `campaign-audit`.
`DIRECT_ANSWER` requires review of every product:

```bash
bash "$WITSOC" review-draft --state "$STATE" --review-id RV1 \
  --revision-id '<snapshot>' --producer-id '<producer>' \
  --producer-method '<method>' --producer-failure-domain '<domain>' \
  --reviewer-id '<reviewer>' --reviewer-method '<different-method>' \
  --reviewer-failure-domain '<independent-domain>' \
  --artifact "$TASK/<product>" --item-id ROOT --source-map "$SM" \
  --out "$TASK/review.draft.json"
bash "$WITSOC" review-check --state "$STATE" \
  --input "$TASK/review.draft.json" --source-map "$SM" \
  --out "$TASK/review.json"
bash "$WITSOC" finalize --state "$STATE" --artifact "$TASK/<product>" \
  --review "$TASK/review.json" --out "$TASK/finalization.json" \
  --result-out "$TASK/RESULT.md"
bash "$WITSOC" orchestrator-next --state "$STATE" \
  --finalization "$TASK/finalization.json"
```

The last command completes; later edits invalidate it. `WAIT_EXTERNAL` and
`HONEST_STOP` need no review. Audit v1-v3; never resume them. Search may
speculate; status may not.
