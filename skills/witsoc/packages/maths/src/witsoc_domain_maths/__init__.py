"""Installed resource access for the Witsoc mathematics domain pack."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

__version__ = "1.0.1"


def metadata() -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("pack.json").read_text(encoding="utf-8"))


def domain_root():
    return files(__package__).joinpath("domain")
