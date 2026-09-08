#!/usr/bin/env python3
"""Build and verify the independently installable Witsoc domain distributions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "contracts" / "domain-packages.json"
CORE_API = 1
PACK_SCHEMA = "witsoc.domain-package.v1"
REGISTRY_SCHEMA = "witsoc.domain-package-registry.v1"
PACKAGES = {
    "maths": {
        "project": ROOT / "packages" / "maths",
        "module": "witsoc_domain_maths",
        "distribution": "witsoc",
    },
    "bio": {
        "project": ROOT / "packages" / "bio",
        "module": "witsoc_domain_bio",
        "distribution": "witsoc-bio",
    },
}
SELECTION_KEYS = {
    "signals", "strong_signals", "excludes", "examples", "counter_examples",
    "min_score", "priority",
}
SKIP_PARTS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
RUNTIME_EVAL_PREFIXES = {
    "maths": {
        ("evals", "blueprints"),
        ("evals", "open_problem"),
        ("evals", "path"),
        ("evals", "wit_contract"),
    },
    "bio": set(),
}


def source_projection(domain: str) -> dict[str, Any]:
    return {
        "exclude_parts": sorted(SKIP_PARTS),
        "exclude_part_prefixes": [".witsoc_"],
        "exclude_suffixes": sorted(SKIP_SUFFIXES),
        "exclude_root_paths": ["README.md"],
        "include_eval_prefixes": sorted(
            "/".join(parts) for parts in RUNTIME_EVAL_PREFIXES[domain]
        ),
    }


class PackageError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_metadata(project: Path) -> tuple[str, str]:
    try:
        value = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
        metadata = value["project"]
        distribution, version = metadata["name"], metadata["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise PackageError(f"cannot read package metadata from {project}: {exc}") from exc
    if not isinstance(distribution, str) or not isinstance(version, str):
        raise PackageError(f"package name and version must be strings in {project}")
    return distribution, version


def payload_paths(domain: str) -> list[Path]:
    root = ROOT / "domains" / domain
    if not (root / "domain.json").is_file():
        raise PackageError(f"domain source is missing: {root}")
    result: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        in_runtime_eval = any(
            relative.parts[: len(prefix)] == prefix
            for prefix in RUNTIME_EVAL_PREFIXES[domain]
        )
        if (
            not path.is_file()
            or any(part in SKIP_PARTS for part in relative.parts)
            or any(part.startswith(".witsoc_") for part in relative.parts)
            or ("evals" in relative.parts and not in_runtime_eval)
            or path.suffix in SKIP_SUFFIXES
            or relative == Path("README.md")
        ):
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(root).as_posix())


def payload_records(domain: str) -> list[dict[str, Any]]:
    root = ROOT / "domains" / domain
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
        for path in payload_paths(domain)
    ]


def pack_metadata(domain: str) -> dict[str, Any]:
    spec = PACKAGES[domain]
    distribution, version = project_metadata(spec["project"])
    if distribution != spec["distribution"]:
        raise PackageError(
            f"{domain} must build distribution {spec['distribution']!r}, got {distribution!r}"
        )
    init_path = spec["project"] / "src" / spec["module"] / "__init__.py"
    version_match = re.search(
        r'^__version__\s*=\s*["\x27]([^"\x27]+)["\x27]',
        init_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not version_match or version_match.group(1) != version:
        raise PackageError(f"{domain} module version differs from pyproject.toml")
    manifest = json.loads((ROOT / "domains" / domain / "domain.json").read_text(encoding="utf-8"))
    records = payload_records(domain)
    return {
        "schema": PACK_SCHEMA,
        "domain": domain,
        "distribution": distribution,
        "version": version,
        "import_package": spec["module"],
        "payload_subdir": "domain",
        "core_api": {"minimum": CORE_API, "maximum": CORE_API},
        "domain_contract_version": int(manifest["contract_version"]),
        "payload_sha256": hashlib.sha256(canonical_json(records)).hexdigest(),
        "payload_files": len(records),
        "payload_bytes": sum(item["size"] for item in records),
        "files": records,
    }


def registry_document() -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    for domain in sorted(PACKAGES):
        packed = pack_metadata(domain)
        manifest = json.loads(
            (ROOT / "domains" / domain / "domain.json").read_text(encoding="utf-8")
        )
        selection = manifest.get("selection") or {}
        missing = SELECTION_KEYS - set(selection)
        if missing:
            raise PackageError(f"{domain} selection is missing {sorted(missing)}")
        packages.append({
            "domain": domain,
            "distribution": packed["distribution"],
            "version": packed["version"],
            "import_package": packed["import_package"],
            "payload_subdir": packed["payload_subdir"],
            "core_api": packed["core_api"],
            "domain_contract_version": packed["domain_contract_version"],
            "payload_sha256": packed["payload_sha256"],
            "payload_files": packed["payload_files"],
            "payload_bytes": packed["payload_bytes"],
            "source_projection": source_projection(domain),
            "selection": {key: selection[key] for key in sorted(SELECTION_KEYS)},
        })
    return {
        "schema": REGISTRY_SCHEMA,
        "version": 1,
        "core_api": CORE_API,
        "packages": packages,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def registry_report(*, write: bool = False) -> dict[str, Any]:
    expected = registry_document()
    if write:
        write_json(REGISTRY_PATH, expected)
    try:
        actual = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "problems": [f"cannot read registry: {exc}"]}
    problems = [] if actual == expected else [
        "contracts/domain-packages.json is stale; run package_domains.py registry --write"
    ]
    return {
        "ok": not problems,
        "problems": problems,
        "packages": [
            {
                key: item[key]
                for key in ("domain", "distribution", "version", "payload_sha256", "payload_files", "payload_bytes")
            }
            for item in expected["packages"]
        ],
    }


def copy_payload(domain: str, destination: Path) -> None:
    source = ROOT / "domains" / domain
    for path in payload_paths(domain):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def stage_project(domain: str, destination: Path) -> dict[str, Any]:
    spec = PACKAGES[domain]
    shutil.copytree(spec["project"], destination)
    module = destination / "src" / spec["module"]
    payload = module / "domain"
    copy_payload(domain, payload)
    metadata = pack_metadata(domain)
    write_json(module / "pack.json", metadata)
    return metadata


def inspect_wheel(path: Path, metadata: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    module = metadata["import_package"]
    expected = {
        f"{module}/pack.json",
        f"{module}/{metadata['payload_subdir']}/domain.json",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = expected - names
            if missing:
                problems.append(f"{path.name} omits {sorted(missing)}")
            prefix = f"{module}/{metadata['payload_subdir']}/"
            payload_names = sorted(
                name[len(prefix):] for name in names
                if name.startswith(prefix) and not name.endswith("/")
            )
            expected_names = [item["path"] for item in metadata["files"]]
            if payload_names != expected_names:
                problems.append(f"{path.name} payload file set differs from pack metadata")
            if f"{module}/pack.json" in names:
                packed = json.loads(archive.read(f"{module}/pack.json"))
                if packed != metadata:
                    problems.append(f"{path.name} carries stale pack metadata")
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        problems.append(f"cannot inspect {path}: {exc}")
    return problems


def inspect_sdist(path: Path, metadata: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    module = metadata["import_package"]
    try:
        with tarfile.open(path, "r:gz") as archive:
            names = archive.getnames()
            if not any(name.endswith(f"/src/{module}/pack.json") for name in names):
                problems.append(f"{path.name} omits pack.json")
            if not any(name.endswith(f"/src/{module}/domain/domain.json") for name in names):
                problems.append(f"{path.name} omits the domain payload")
            if any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names):
                problems.append(f"{path.name} contains generated Python bytecode")
    except (OSError, tarfile.TarError) as exc:
        problems.append(f"cannot inspect {path}: {exc}")
    return problems


def build_packages(output: Path, domains: Iterable[str]) -> dict[str, Any]:
    report = registry_report()
    if not report["ok"]:
        raise PackageError("; ".join(report["problems"]))
    builder = shutil.which("uv")
    if not builder:
        raise PackageError("uv is required to build reproducible wheel and source artifacts")
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    problems: list[str] = []
    for domain in domains:
        if domain not in PACKAGES:
            raise PackageError(f"unknown packaged domain {domain!r}")
        with tempfile.TemporaryDirectory(prefix=f"witsoc-{domain}-build-") as raw:
            temporary = Path(raw)
            project = temporary / "project"
            built_dir = temporary / "dist"
            metadata = stage_project(domain, project)
            completed = subprocess.run(
                [
                    builder,
                    "build",
                    "--no-progress",
                    "--no-create-gitignore",
                    "--out-dir",
                    str(built_dir),
                    str(project),
                ],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stdout + completed.stderr).strip()[-2000:]
                raise PackageError(f"build failed for {domain}: {detail}")
            built = sorted(path for path in built_dir.iterdir() if path.is_file())
            if not built:
                raise PackageError(f"build produced no artifacts for {domain}")
            for path in built:
                if path.suffix == ".whl":
                    problems.extend(inspect_wheel(path, metadata))
                elif path.name.endswith(".tar.gz"):
                    problems.extend(inspect_sdist(path, metadata))
                target = output / path.name
                shutil.copy2(path, target)
                artifacts.append({
                    "domain": domain,
                    "file": target.name,
                    "sha256": sha256(target),
                    "size": target.stat().st_size,
                })
    artifact_manifest = {
        "schema": "witsoc.domain-package-artifacts.v1",
        "registry_sha256": sha256(REGISTRY_PATH),
        "artifacts": sorted(artifacts, key=lambda item: item["file"]),
    }
    if problems:
        raise PackageError("; ".join(problems))
    write_json(output / "manifest.json", artifact_manifest)
    return {"ok": True, "out": str(output), **artifact_manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    registry = sub.add_parser("registry", help="check or regenerate the core package registry")
    registry.add_argument("--write", action="store_true")
    build = sub.add_parser("build", help="build and inspect wheels and source distributions")
    build.add_argument("--out", type=Path, default=ROOT / "dist" / "domain-packs")
    build.add_argument("--domain", action="append", choices=sorted(PACKAGES))
    args = parser.parse_args()
    try:
        result = (
            registry_report(write=args.write)
            if args.command == "registry"
            else build_packages(args.out, args.domain or sorted(PACKAGES))
        )
    except (OSError, ValueError, PackageError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "problems": [str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
