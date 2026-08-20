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
run_step() {
  local label="$1"; shift
  if "$@" >/tmp/witsoc2-check.$$ 2>&1; then
    printf "  ok    %-22s %s\n" "$label" "$(tail -1 /tmp/witsoc2-check.$$)"
  else
    printf "  FAIL  %-22s\n" "$label"
    sed 's/^/          /' /tmp/witsoc2-check.$$ | tail -12
    FAILED=1
  fi
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
  run_step "schema examples" python3 "$SCRIPTS_DIR/check_schema_examples.py"
  run_step "reducer"         python3 "$SCRIPTS_DIR/reducer_selftest.py"
  run_step "working memory"  python3 "$SCRIPTS_DIR/soc_selftest.py"
  run_step "campaign loop"   python3 "$SCRIPTS_DIR/campaign.py" self-test
  run_step "resolution"      python3 "$SCRIPTS_DIR/resolve_domain.py" --self-test
fi

for name in $(packs); do
  [[ -n "$ONLY" && "$name" != "$ONLY" ]] && continue
  run_step "conformance: $name" python3 "$SCRIPTS_DIR/validate_domain_pack.py" \
      "$DOMAINS_DIR/$name/domain.json"
  [[ "$MODE" == "frame" ]] && continue
  for entry in "$DOMAINS_DIR/$name/scripts/check.py" "$DOMAINS_DIR/$name/adapter/check.py"; do
    [[ -f "$entry" ]] && run_step "adapter: $name" python3 "$entry" --self-test
  done
done

if [[ $FAILED -eq 0 ]]; then
  log "all green"
else
  log "something failed — a failure here is a finding about the skill, not a broken test"
fi
exit $FAILED
