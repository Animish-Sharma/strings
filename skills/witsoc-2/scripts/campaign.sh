#!/usr/bin/env bash
# campaign.sh — run one campaign end to end, through every packet the frame
# defines: resolve → freeze → work item → adapter → receipt → result →
# [review] → admission → reducer → state.
#
# Every packet is schema-validated and sealed on the way through, so the run
# stops at the first place the chain does not hold together.
#
# Usage:
#   campaign.sh run --domain <pack> --tier <name> \
#       --claim <claim.json> --artifact <path> [--review <r.json>] \
#       [--workdir <dir>] [--write]
#   campaign.sh self-test
#
# Exit: 0 ADMITTED · 1 refused or not admitted · 2 usage · 3 ESCALATED
#
# Without --review the run cannot reach VERIFIED, by construction: one process
# cannot be both producer and independent reviewer. It tops out at
# CHECKED_BOUNDED and the report says why.

source "$(dirname "$0")/_common.sh"
frame campaign.py "$@"
