#!/usr/bin/env bash
# check.sh — is this skill healthy? Runs every check the frame has, in the
# order that fails cheapest first.
#
#   frame purity        no frame file reaches into a domain pack
#   doc links           every path a document names actually exists
#   contract shapes     claims satisfy the frame's, declared gates exist,
#                       refinements refine a status that is real
#   delivery            context budget, shell entry points, registry accuracy,
#                       nothing shipped that should not be
#   doctrine coverage   every blocking gate is named in the doctrine of the
#                       role whose work it stops
#   reducer             15 adversarial admissions refused for the stated reason
#   working memory      the attention/evidence boundary, and the repeat gate
#   campaign            the loop closes, and the failure ladder engages
#   resolution          every pack's examples still resolve to it
#   conformance         every registered pack satisfies all six contract items
#   pack self-tests     each adapter rejects its known-bad inputs
#
# Run it after any change. Run it before trusting a result.
#
# Usage:
#   check.sh              # everything
#   check.sh --frame      # frame only, no pack self-tests (fast)
#   check.sh --pack NAME  # one pack
#
# Exit: 0 all green · 1 something failed

source "$(dirname "$0")/_common.sh"

MODE="all"; ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --frame) MODE="frame"; shift ;;
    --pack)  MODE="pack"; ONLY="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

FAILED=0
NOT_RUN=0
# A suite grows one justified check at a time and becomes unrunnable the same
# way. Governance rule 12 asks a check to prove it pays; you cannot govern a cost
# nobody measures, so every step is timed, anything slower than SLOW_STEP_S is
# marked, and the total is printed at the end. The marker is not a failure — some
# checks are legitimately expensive — it is the number the rule is argued from.
SLOW_STEP_S=${SLOW_STEP_S:-10}
TOTAL_MS=0
SLOW_STEPS=""
STEPS=0

run_step() {
  local label="$1"; shift
  local start elapsed_ms mark
  start=$(date +%s%N)
  if "$@" >/tmp/witsoc2-check.$$ 2>&1; then
    elapsed_ms=$(( ($(date +%s%N) - start) / 1000000 ))
    mark="ok  "
    if (( elapsed_ms > SLOW_STEP_S * 1000 )); then
      mark="slow"
      SLOW_STEPS="${SLOW_STEPS}${label} (${elapsed_ms}ms) "
    fi
    printf "  %s  %-22s %s\n" "$mark" "$label" "$(tail -1 /tmp/witsoc2-check.$$)"
  else
    local code=$?
    elapsed_ms=$(( ($(date +%s%N) - start) / 1000000 ))
    # Exit 3 is NOT_RUN: the check could not run here, which is a GAP. It is not
    # a failure of the skill and it is emphatically not a pass — a suite with
    # unrun checks that prints "all green" is the exact dishonesty this codebase
    # refuses everywhere else. Show it, count it, do not fail on it.
    if (( code == 3 )); then
      printf "  ----  %-22s %s\n" "$label" "$(tail -1 /tmp/witsoc2-check.$$)"
      NOT_RUN=$(( NOT_RUN + 1 ))
    else
      printf "  FAIL  %-22s\n" "$label"
      sed 's/^/          /' /tmp/witsoc2-check.$$ | tail -12
      FAILED=1
    fi
  fi
  TOTAL_MS=$(( TOTAL_MS + elapsed_ms ))
  STEPS=$(( STEPS + 1 ))
  rm -f /tmp/witsoc2-check.$$
}

packs() {
  find "$DOMAINS_DIR" -maxdepth 2 -name domain.json -printf '%h\n' | while read -r d; do
    basename "$d"
  done | sort
}

if [[ "$MODE" != "pack" ]]; then
  run_step "frame purity"    python3 "$SCRIPTS_DIR/check_frame_purity.py"
  run_step "doc links"       python3 "$SCRIPTS_DIR/check_doc_links.py"
  run_step "contract shapes" python3 "$SCRIPTS_DIR/check_contract_shapes.py"
  run_step "delivery"        python3 "$SCRIPTS_DIR/check_delivery.py"
  run_step "doctrine coverage" python3 "$SCRIPTS_DIR/check_doctrine_coverage.py"
  run_step "schema examples" python3 "$SCRIPTS_DIR/check_schema_examples.py"
  run_step "doctrine commands" python3 "$SCRIPTS_DIR/check_doctrine_commands.py"
  run_step "alignment"       python3 "$SCRIPTS_DIR/check_alignment.py"
  run_step "bridge"          python3 "$SCRIPTS_DIR/check_bridge.py"
  run_step "governor"        python3 "$SCRIPTS_DIR/governor.py" --self-test
  run_step "schedule plan"   python3 "$SCRIPTS_DIR/schedule.py" --self-test
  run_step "reducer"         python3 "$SCRIPTS_DIR/reducer_selftest.py"
  run_step "cross-run memory" python3 "$SCRIPTS_DIR/memory_selftest.py"
  run_step "registry"        python3 "$SCRIPTS_DIR/registry.py" --self-test
  # Who checks the checkers: each guard gets a regression planted into a copy of
  # the tree and must fail, then must pass again on the clean copy. Expensive by
  # the standards of the other steps and it earns it — the first run found a
  # validator that had never applied `additionalProperties` as a schema, so the
  # claim graph the reducer solely writes had never been schema-checked at all.
  run_step "checker regressions" python3 "$SCRIPTS_DIR/check_checkers.py"
  run_step "working memory"  python3 "$SCRIPTS_DIR/soc_selftest.py"
  run_step "campaign loop"   python3 "$SCRIPTS_DIR/campaign.py" self-test
  run_step "resolution"      python3 "$SCRIPTS_DIR/resolve_domain.py" --self-test
  # Whole campaigns, not components. Every defect that survived four green
  # suites lived in a seam between two checked things.
  run_step "paths"           python3 "$SCRIPTS_DIR/check_paths.py"
  # No gate may be inert. A gate that answers the same thing to every artifact
  # in a corpus built to disagree with itself is not checking anything, and
  # three of them were shipping in receipts looking like checks.
  run_step "gate inertness"  python3 "$SCRIPTS_DIR/check_gate_inertness.py"
fi

for name in $(packs); do
  [[ -n "$ONLY" && "$name" != "$ONLY" ]] && continue
  run_step "conformance: $name" python3 "$SCRIPTS_DIR/validate_domain_pack.py" \
      "$DOMAINS_DIR/$name/domain.json"
  [[ "$MODE" == "frame" ]] && continue
  for entry in "$DOMAINS_DIR/$name/scripts/check.py" "$DOMAINS_DIR/$name/adapter/check.py"; do
    [[ -f "$entry" ]] && run_step "adapter: $name" python3 "$entry" --self-test
  done
  # DISCOVERED, not enumerated. An earlier version listed the pack scripts by
  # name here -- produce, bundle, counts -- which put one field's file names in
  # a frame file. The purity check did not catch it, because those are not field
  # VOCABULARY: it reads for words, and that was a structural leak. Anything a
  # pack ships that answers --self-test is part of what the pack claims to do,
  # and therefore part of what green means.
  while IFS= read -r extra; do
    [[ -z "$extra" ]] && continue
    grep -q -- '--self-test' "$extra" || continue
    run_step "$(basename "$extra" .py): $name" python3 "$extra" --self-test
  done < <(find "$DOMAINS_DIR/$name/scripts" -maxdepth 1 -name '*.py' ! -name 'check.py' 2>/dev/null | sort)
  # Calibration, where a pack has one: a scorer nobody measures drifts, and the
  # drift is invisible because every individual answer still looks reasonable.
  while IFS= read -r cal; do
    [[ -z "$cal" ]] && continue
    grep -q -- '--calibrate' "$cal" || continue
    run_step "calibration: $name" python3 "$cal" --calibrate
  done < <(find "$DOMAINS_DIR/$name/scripts" -maxdepth 1 -name '*.py' 2>/dev/null | sort)
  # The JOURNEY: one claim, the whole path, nothing pre-fitted. Every other
  # check here tests a component, and the first time a pack was pointed at the
  # simplest claim in its field, eight defects surfaced in a row — every one of
  # them on the shortest path through the system, and every one behind a green
  # suite. A road nobody drives is not a road.
  while IFS= read -r journey; do
    [[ -z "$journey" ]] && continue
    run_step "journey: $name" python3 "$journey"
  done < <(find "$DOMAINS_DIR/$name/evals/journey" -maxdepth 1 -name 'run_*.py' 2>/dev/null | sort)

  # PATH checks a pack owns: loops over its own pipeline that the frame is not
  # allowed to know about. The generic claim-to-admission paths live in
  # <pack>/evals/path/cases.json and are walked by scripts/check_paths.py.
  while IFS= read -r pathrun; do
    [[ -z "$pathrun" ]] && continue
    run_step "paths: $name" python3 "$pathrun"
  done < <(find "$DOMAINS_DIR/$name/evals/path" -maxdepth 1 -name 'run_*.py' 2>/dev/null | sort)

  # Role evals score the DECISIONS a role makes. Every other check here scores an
  # artifact through a gate, which cannot tell you whether a role doctrine has
  # regressed — the doctrine can rot while every gate still passes.
  [[ -f "$DOMAINS_DIR/$name/evals/roles/run_roles.py" ]] &&     run_step "role evals: $name" python3 "$DOMAINS_DIR/$name/evals/roles/run_roles.py"
  # A pack's evals ask what it CONCLUDED; its self-test asks whether the adapter
  # can refuse. Running only the second let one pack ship with no outcome evals
  # at all, and nothing said so.
  #
  # Every external eval RUNS. These are the only numbers a pack has that were
  # not produced by grading itself, so listing them as advice was the wrong
  # shape: the most valuable checks in the tree were the ones nothing executed.
  while IFS= read -r held; do
    [[ -z "$held" ]] && continue
    grep -q "argparse" "$held" || continue
    label="external: $name/$(basename "$held" .py)"
    # An eval that needs outside material nobody supplied has NOT failed — it
    # has not run, and those are different findings. Reporting the first as the
    # second trains people to ignore the line, and this line is the only one in
    # a pack carrying a number the pack did not produce about itself.
    if python3 "$held" >/tmp/witsoc2-ext.$$ 2>&1; then
      printf "  ok    %-22s %s\n" "$label" "$(tail -1 /tmp/witsoc2-ext.$$)"
      STEPS=$(( STEPS + 1 ))
    elif grep -qE "arguments are required|NOT_RUN" /tmp/witsoc2-ext.$$; then
      printf "  ----  %-22s needs outside material: %s\n" "$label" \
        "$(grep -oE 'required: --[a-z-]+|NOT_RUN[^\n]*' /tmp/witsoc2-ext.$$ | head -1 | cut -c1-70)"
      NOT_RUN=$(( NOT_RUN + 1 ))
    else
      printf "  FAIL  %-22s\n" "$label"
      sed 's/^/          /' /tmp/witsoc2-ext.$$ | tail -8
      FAILED=1
    fi
    rm -f /tmp/witsoc2-ext.$$
  done < <(find "$DOMAINS_DIR/$name/evals/external" -maxdepth 1 -name '*.py' 2>/dev/null | sort)
  # A pack with no external evaluation at all is worth naming: every number it
  # reports was produced by grading itself.
  if ! compgen -G "$DOMAINS_DIR/$name/evals/external/*.py" > /dev/null; then
    printf "  ----  %-22s no external evaluation; every number this pack reports it graded itself\n" \
      "external: $name"
  fi

  evals="$DOMAINS_DIR/$name/evals/run_evals.py"
  if [[ -f "$evals" ]]; then
    run_step "evals: $name" python3 "$evals"
  elif [[ -d "$DOMAINS_DIR/$name/scripts" ]]; then
    printf "  ----  %-22s no outcome evals; the adapter can refuse and nothing asks what it concludes\n" "evals: $name"
  fi
done

printf "\n  suite cost: %ss across %s step(s)\n" "$(( TOTAL_MS / 1000 ))" "$STEPS"
if [[ -n "$SLOW_STEPS" ]]; then
  printf "  slow: %s\n" "$SLOW_STEPS"
  printf "  a check earns its place by naming the regression it catches and being shown to catch\n"
  printf "  a planted one. A slow check that does neither is the first thing to drop.\n"
fi

if [[ $FAILED -eq 0 ]]; then
  if (( NOT_RUN > 0 )); then
    log "green, with $NOT_RUN check(s) NOT_RUN — a gap, not a pass"
  else
    log "all green"
  fi
else
  log "something failed — a failure here is a finding about the skill, not a broken test"
fi
exit $FAILED
