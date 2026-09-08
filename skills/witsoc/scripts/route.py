#!/usr/bin/env python3
"""Compatibility entry point for deterministic Witsoc routing."""

from __future__ import annotations

import sys

from witsoc_core.cli import main


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments[:1] == ["route"]:
        arguments = arguments[1:]
    sys.argv = [sys.argv[0], "route", *arguments]
    raise SystemExit(main())
