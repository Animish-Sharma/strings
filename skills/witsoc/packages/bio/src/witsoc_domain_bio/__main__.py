"""Inspect the installed biology pack without invoking the Witsoc core."""

from __future__ import annotations

import json

from . import domain_root, metadata


def main() -> int:
    value = metadata()
    value["installed_domain_root"] = str(domain_root())
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
