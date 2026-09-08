#!/usr/bin/env bash
# Unified Witsoc entry point. Compatibility wrappers remain supported.

source "$(dirname "$0")/_common.sh"
frame witsoc.py "$@"
