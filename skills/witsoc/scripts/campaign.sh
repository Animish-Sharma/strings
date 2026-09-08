#!/usr/bin/env bash
# campaign.sh - admit one candidate artifact through the generic frame packets:
# resolve, freeze, work item, adapter, receipt, result, optional review,
# admission, reducer, and state.
#
# Every packet is schema-validated and sealed on the way through, so the run
# stops at the first place the chain does not hold together.
#
# Usage:
#   campaign.sh artifact --domain <pack> --tier <name> \
#       --claim <claim.json> --artifact <path> [--review <r.json>] \
#       [--workdir <dir>] [--write]
#   campaign.sh self-test
#
# This is not a domain's campaign-wide open-problem loop. The selected pack's
# campaign doctrine names that entry point. `run` is a compatibility alias.
#
# Exit: 0 ADMITTED · 1 refused or not admitted · 2 usage · 3 ESCALATED
#
# Without --review the run cannot reach VERIFIED, by construction: one process
# cannot be both producer and independent reviewer. It tops out at
# CHECKED_BOUNDED and the report says why.

source "$(dirname "$0")/_common.sh"
frame campaign.py "$@"
