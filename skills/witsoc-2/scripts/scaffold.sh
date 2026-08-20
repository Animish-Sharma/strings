#!/usr/bin/env bash
# scaffold.sh — improvise a provisional domain pack when resolve.sh returns
# NO_MATCH.
#
# What it writes is real: a working adapter that checks the properties any
# field's artifact must have, a refute-attempt gate that perturbs the claim and
# requires the verdict to flip, negative controls, and doctrine for all three
# roles. What it is not is trusted — the system that produces candidates also
# wrote the thing that checks them, so the ceiling is SKETCH and the validator
# refuses a higher one.
#
# An improvised pack lets a run proceed. It does not let a run conclude.
#
# Usage:
#   scaffold.sh --domain <name> --from <closest-pack> --statement "<problem>"
#   scaffold.sh --domain <name> --from <closest-pack> --file problem.txt
#
# Exit: 0 written and conformant · 1 written but needs attention · 2 usage

source "$(dirname "$0")/_common.sh"
frame scaffold_domain.py "$@"
