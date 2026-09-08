#!/usr/bin/env python3
"""Exercise thin-core installation from locally built domain wheels."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import package_domains
import release


ROOT = Path(__file__).resolve().parent.parent


class CheckError(RuntimeError):
    pass


def run(core: Path, cache: Path, wheels: Path, args: list[str], **extra: str) -> tuple[int, dict[str, Any]]:
    environment = {
        **os.environ,
        "WITSOC_PACK_CACHE": str(cache),
        "WITSOC_PACK_WHEELHOUSE": str(wheels),
        "WITSOC_PACK_OFFLINE": "1",
        **extra,
    }
    completed = subprocess.run(
        [sys.executable, str(core / "scripts" / "witsoc.py"), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CheckError(
            f"command did not return JSON: {(completed.stdout + completed.stderr)[-1000:]}"
        ) from exc
    return completed.returncode, value


def selected_activation(value: dict[str, Any], domain: str, effect: str) -> None:
    if value.get("decision") != "SELECTED" or value.get("domains") != [domain]:
        raise CheckError(f"{domain} route did not select its domain")
    if not value.get("load_plan", {}).get("ok"):
        raise CheckError(f"{domain} route did not produce a valid load plan")
    effects = value["domain_packages"]["activation"]["side_effects"]
    if not any(item.startswith(effect) for item in effects):
        raise CheckError(f"{domain} activation did not report {effect}")


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="witsoc-pack-check-") as raw:
            workspace = Path(raw)
            wheels = workspace / "wheels"
            package_domains.build_packages(wheels, sorted(package_domains.PACKAGES))
            core = workspace / "core"
            release.copy_tree(ROOT, core)
            cache = workspace / "cache"

            code, value = run(
                core,
                cache,
                wheels,
                ["route", "--statement", "Refactor the API endpoint unit tests."],
            )
            if code != 4 or value.get("decision") != "NO_MATCH" or (core / "domains").exists():
                raise CheckError("an unrelated request installed a domain pack")

            code, value = run(
                core,
                cache,
                wheels,
                ["route", "--statement", "Attack an open Erdos problem about prime gaps."],
                WITSOC_PACK_AUTO_INSTALL="0",
            )
            if code != 5 or value.get("decision") != "UNRESOLVABLE":
                raise CheckError("disabled installation did not fail closed")

            code, value = run(
                core,
                cache,
                wheels,
                ["route", "--statement", "Attack an open Erdos problem about prime gaps."],
                WITSOC_PACK_INSTALLER="pip",
            )
            if code != 0:
                raise CheckError(f"maths route exited {code}")
            selected_activation(value, "maths", "INSTALL:witsoc==")

            code, value = run(
                core,
                cache,
                wheels,
                ["route", "--statement", "Attack an open Erdos problem about prime gaps."],
            )
            if code != 0 or value["domain_packages"]["activation"]["side_effects"]:
                raise CheckError("a cache hit was not side-effect free")

            active_file = core / "domains" / "maths" / "doctrine" / "literature.md"
            original = active_file.read_bytes()
            active_file.write_bytes(original + b"\nTAMPERED\n")
            code, value = run(
                core,
                cache,
                wheels,
                ["route", "--statement", "Attack an open Erdos problem about prime gaps."],
            )
            effects = value["domain_packages"]["activation"]["side_effects"]
            if code != 0 or effects != ["ACTIVATE:maths"] or active_file.read_bytes() != original:
                raise CheckError("active payload tampering was not repaired from the verified cache")

            code, value = run(
                core,
                cache,
                wheels,
                [
                    "route",
                    "--statement",
                    "Discover an open biology mechanism with CRISPR gene perturbation.",
                ],
                WITSOC_PACK_INSTALLER="curl",
            )
            if code != 0:
                raise CheckError(f"bio route exited {code}")
            selected_activation(value, "bio", "INSTALL:witsoc-bio==")

            for domain in ("maths", "bio"):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(core / "domains" / domain / "scripts" / "check.py"),
                        "--self-test",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                output = completed.stdout + completed.stderr
                if completed.returncode != 0 or "fixture missing" in output:
                    raise CheckError(f"{domain} packaged adapter self-test is incomplete: {output[-1000:]}")
    except (OSError, ValueError, CheckError, subprocess.SubprocessError) as exc:
        print(f"DOMAIN PACKAGES: FAIL - {exc}")
        return 1
    print("DOMAIN PACKAGES: PASS - thin routing, pip, curl extraction, cache, and adapters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
