#!/usr/bin/env bash
# resolve.sh — step 0 of every run: decide which domain pack this problem
# belongs to, and print the exact files each role must load.
#
# Do not skip this and do not do it by eye. A run that proceeds without a
# resolved pack still produces work, still sounds confident, and has nothing
# underneath it that can say no.
#
# Usage:
#   resolve.sh --statement "<the problem, verbatim>"
#   resolve.sh --domain <pack>          # when the field is already known
#   resolve.sh --list                   # what is registered
#   resolve.sh --self-test              # every pack still resolves to itself
#
# Exit: 0 SELECTED · 3 AMBIGUOUS · 4 NO_MATCH · 5 UNRESOLVABLE · 2 usage
#
# On NO_MATCH, improvise rather than proceeding with no doctrine:
#   scaffold.sh --domain <name> --from <closest-pack> --statement "..."

source "$(dirname "$0")/_common.sh"
for argument in "$@"; do
  case "$argument" in
    --list|--self-test)
      frame resolve_domain.py "$@"
      exit $?
      ;;
  esac
done
frame witsoc.py route "$@"
