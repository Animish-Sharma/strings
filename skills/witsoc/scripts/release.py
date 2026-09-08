#!/usr/bin/env python3
"""Build, verify, compare, and atomically install the Witsoc skill tree."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = Path.home() / ".openscientist" / "strings" / "skills" / "witsoc"
MANIFEST_NAME = ".witsoc-manifest.json"
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}
SKIP_FILES = {MANIFEST_NAME, ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
POLICY_RELATIVE = Path("references/runtime_release.json")
POLICY_SCHEMA = "witsoc.runtime-release-policy.v1"


def load_policy(root: Path) -> dict[str, object] | None:
    path = root / POLICY_RELATIVE
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid runtime release policy: {exc}") from exc
    required = {
        "schema", "profile", "exclude_patterns", "required_paths",
        "max_files", "max_bytes",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeError("runtime release policy has an invalid shape")
    if value["schema"] != POLICY_SCHEMA:
        raise RuntimeError("unsupported runtime release policy schema")
    if not isinstance(value["exclude_patterns"], list) or not isinstance(value["required_paths"], list):
        raise RuntimeError("runtime release policy paths must be arrays")
    return value


def policy_excludes(relative: Path, policy: dict[str, object] | None) -> bool:
    if policy is None:
        return False
    name = relative.as_posix()
    return any(fnmatch.fnmatch(name, str(pattern)) for pattern in policy["exclude_patterns"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def included_files(root: Path) -> list[Path]:
    policy = load_policy(root)
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or any(part in SKIP_DIRS for part in relative.parts)
            or path.name in SKIP_FILES
            or path.suffix in SKIP_SUFFIXES
            or policy_excludes(relative, policy)
        ):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def projection_problems(root: Path, files: list[Path] | None = None) -> list[str]:
    policy = load_policy(root)
    if policy is None:
        return []
    selected = files if files is not None else included_files(root)
    relative = {path.relative_to(root).as_posix() for path in selected}
    problems = [
        f"required runtime path is missing or excluded: {path}"
        for path in policy["required_paths"]
        if path not in relative
    ]
    byte_count = sum(path.stat().st_size for path in selected)
    if len(selected) > int(policy["max_files"]):
        problems.append(
            f"runtime projection has {len(selected)} files, above policy maximum {policy['max_files']}"
        )
    if byte_count > int(policy["max_bytes"]):
        problems.append(
            f"runtime projection has {byte_count} bytes, above policy maximum {policy['max_bytes']}"
        )
    return problems


def manifest(root: Path) -> dict[str, object]:
    files = included_files(root)
    entries = []
    for path in files:
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256(path),
                "mode": oct(path.stat().st_mode & 0o777),
                "size": path.stat().st_size,
            }
        )
    identity = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "witsoc.release-manifest.v1",
        "skill": "witsoc",
        "tree_sha256": identity,
        "profile": (load_policy(root) or {}).get("profile", "complete-tree"),
        "total_bytes": sum(item["size"] for item in entries),
        "files": entries,
    }


def write_manifest(root: Path) -> dict[str, object]:
    payload = manifest(root)
    (root / MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def copy_tree(source: Path, destination: Path) -> dict[str, object]:
    if destination.exists():
        raise RuntimeError(f"destination already exists: {destination}")
    files = included_files(source)
    problems = projection_problems(source, files)
    if problems:
        raise RuntimeError("runtime projection is invalid: " + "; ".join(problems))
    destination.mkdir(parents=True)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return write_manifest(destination)


def load_manifest(root: Path) -> dict[str, object]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise RuntimeError(f"missing release manifest: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid release manifest: {exc}") from exc
    if payload.get("schema") != "witsoc.release-manifest.v1":
        raise RuntimeError("unsupported release manifest schema")
    return payload


def verify(root: Path, *, run_checks: bool) -> dict[str, object]:
    declared = load_manifest(root)
    actual = manifest(root)
    problems: list[str] = []
    if declared.get("tree_sha256") != actual.get("tree_sha256"):
        problems.append("tree hash differs from the release manifest")
    if declared.get("files") != actual.get("files"):
        problems.append("file list, content, or executable modes differ from the manifest")
    problems.extend(projection_problems(root))
    skill = root / "SKILL.md"
    if not skill.is_file() or "\nname: witsoc\n" not in f"\n{skill.read_text(encoding='utf-8')}":
        problems.append("SKILL.md does not declare name: witsoc")
    for wrapper in ("witsoc.sh", "resolve.sh", "campaign.sh", "check.sh"):
        path = root / "scripts" / wrapper
        if not path.is_file() or not os.access(path, os.X_OK):
            problems.append(f"missing or non-executable wrapper: scripts/{wrapper}")
    if not (root / "scripts" / "witsoc.py").is_file():
        problems.append("missing unified runtime entrypoint: scripts/witsoc.py")
    route = root / "scripts" / "route.py"
    if not route.is_file() or not os.access(route, os.X_OK):
        problems.append("missing or non-executable routing entrypoint: scripts/route.py")
    checks: list[dict[str, object]] = []
    if run_checks and not problems:
        completed = subprocess.run(
            ["bash", str(root / "scripts" / "check.sh")],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        checks.append({"args": [], "exit_code": completed.returncode})
        if completed.returncode != 0:
            output = (completed.stdout + completed.stderr).strip()
            findings = [
                line.strip()
                for line in output.splitlines()
                if "FAIL" in line or "something failed" in line
            ]
            problems.append(
                "complete check.sh failed"
                + (": " + " | ".join(findings[-20:]) if findings else "")
                + f"; tail: {output[-1000:]}"
            )
    return {
        "root": str(root),
        "tree_sha256": actual["tree_sha256"],
        "checks": checks,
        "problems": problems,
        "ok": not problems,
    }


def compare(left: Path, right: Path) -> dict[str, object]:
    left_manifest = manifest(left)
    right_manifest = manifest(right)
    left_files = {item["path"]: item for item in left_manifest["files"]}
    right_files = {item["path"]: item for item in right_manifest["files"]}
    return {
        "left": str(left),
        "right": str(right),
        "left_tree_sha256": left_manifest["tree_sha256"],
        "right_tree_sha256": right_manifest["tree_sha256"],
        "only_left": sorted(set(left_files) - set(right_files)),
        "only_right": sorted(set(right_files) - set(left_files)),
        "changed": sorted(
            path
            for path in set(left_files) & set(right_files)
            if left_files[path] != right_files[path]
        ),
        "in_sync": left_manifest["tree_sha256"] == right_manifest["tree_sha256"],
    }


def backup_root(target: Path) -> Path:
    """Keep releases outside the directory Plane scans for skills."""
    return target.parent.parent / "skill-backups" / target.name


def install(source: Path, target: Path, *, run_checks: bool) -> dict[str, object]:
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".witsoc-stage-", dir=target.parent))
    stage.rmdir()
    backup: Path | None = None
    promoted = False
    try:
        built = copy_tree(source, stage)
        report = verify(stage, run_checks=run_checks)
        if not report["ok"]:
            raise RuntimeError("staged verification failed: " + "; ".join(report["problems"]))
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = backup_root(target)
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{target.name}.backup-{stamp}"
            if backup.exists():
                raise RuntimeError(f"backup path already exists: {backup}")
            target.rename(backup)
        stage.rename(target)
        promoted = True
        return {
            "target": str(target),
            "backup": str(backup) if backup else None,
            "tree_sha256": built["tree_sha256"],
            "verified": True,
        }
    except Exception:
        if not promoted and backup is not None and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--out", type=Path, required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--run-checks", action="store_true")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--left", type=Path, default=SOURCE_ROOT)
    compare_parser.add_argument("--right", type=Path, default=DEFAULT_TARGET)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    install_parser.add_argument("--run-checks", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "build":
            output = args.out.expanduser().resolve()
            built = copy_tree(SOURCE_ROOT, output)
            result = {
                "out": str(output),
                "tree_sha256": built["tree_sha256"],
                "file_count": len(built["files"]),
            }
        elif args.command == "verify":
            result = verify(args.root.expanduser().resolve(), run_checks=args.run_checks)
        elif args.command == "compare":
            result = compare(args.left.expanduser().resolve(), args.right.expanduser().resolve())
        else:
            result = install(SOURCE_ROOT, args.target, run_checks=args.run_checks)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
