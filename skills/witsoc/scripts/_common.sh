#!/usr/bin/env bash
# _common.sh — shared helpers for the witsoc skill.
# Source this at the top of every wrapper:
#     source "$(dirname "$0")/_common.sh"
#
# The wrappers exist because this runtime runs skills as shell scripts:
# `plane-tool skill-run` execs the resolved path directly, the agent spec
# documents `bash "$SCRIPT" --arg`, and global-sync chmods `**/*.sh` and
# nothing else. The frame's logic is Python and stays Python; these are the
# doors into it, and without them the skill has no surface the orchestrator
# knows how to open.

set -euo pipefail

# The skill root, derived from this file rather than from the caller's CWD.
# An agent invokes these from a worktree that has nothing to do with the
# checkout, so every path below is absolute from here down.
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$SKILL_ROOT/scripts"
DOMAINS_DIR="$SKILL_ROOT/domains"

log()  { printf "[witsoc] %s\n" "$*" >&2; }
die()  { log "ERROR: $*"; exit 2; }

need() {
  command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"
}

need python3

# Run a frame script by name, forwarding every argument.
frame() {
  local script="$1"; shift
  [[ -f "$SCRIPTS_DIR/$script" ]] || die "no such frame script: $script"
  python3 "$SCRIPTS_DIR/$script" "$@"
}

# Run a pack script by pack and relative path.
pack() {
  local domain="$1" script="$2"; shift 2
  [[ -f "$DOMAINS_DIR/$domain/$script" ]] || die "no such script in pack '$domain': $script"
  python3 "$DOMAINS_DIR/$domain/$script" "$@"
}
