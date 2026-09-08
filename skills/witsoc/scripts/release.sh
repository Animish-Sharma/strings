#!/usr/bin/env bash
# Build, verify, compare, or atomically install the Witsoc skill.

source "$(dirname "$0")/_common.sh"
frame release.py "$@"
