#!/usr/bin/env python3
"""Plan, check, and atomically publish the witsoc candidate to the active runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import release


SOURCE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME = Path.home() / ".openscientist" / "strings" / "skills" / "witsoc"
POLICY_PATH = SOURCE_ROOT / "references" / "runtime_sync.json"
PLACEHOLDER_DESCRIPTIONS = {">", ">-", ">+", "|", "|-", "|+"}
REQUIRED_ACTIVATION_TERMS = (
    "use automatically",
    "even when not named",
    "witosc",
    "stack",
    "activation is sticky",
    "never deselects Witsoc",
)


class SyncError(RuntimeError):
    """The candidate and active runtime cannot be reconciled safely."""


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot read sync policy {path}: {exc}") from exc
    required = {
        "schema", "source_of_truth", "active_runtime", "mode",
        "runtime_only_disposition", "candidate_only_disposition",
        "divergent_disposition", "excluded_patterns", "required_entrypoints",
        "post_publish_resolution",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise SyncError("runtime sync policy has an invalid shape")
    if value["schema"] != "witsoc.runtime-sync-policy.v1":
        raise SyncError("runtime sync policy schema is unsupported")
    if value["mode"] != "verified-atomic-replacement":
        raise SyncError("runtime sync policy must use verified atomic replacement")
    return value


def plane_frontmatter_scalar(content: str, key: str) -> str | None:
    """Mirror Plane's frontmatter extraction rather than a fuller YAML parser."""
    frontmatter = re.match(r"^---\n([\s\S]*?)\n---", content)
    if not frontmatter:
        return None
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter.group(1), re.MULTILINE)
    if not match:
        return None
    return re.sub(r"^[\"']|[\"']$", "", match.group(1).strip())


def extract_plane_description(skill_path: Path) -> str | None:
    return plane_frontmatter_scalar(skill_path.read_text(encoding="utf-8"), "description")


def description_problems(description: str | None) -> list[str]:
    if description is None or not description.strip():
        return ["catalog description is absent or empty"]
    if description in PLACEHOLDER_DESCRIPTIONS:
        return [
            f"catalog description is a block scalar marker {description!r}; "
            "Plane will expose the marker instead of the description"
        ]
    normalized = description.casefold()
    return [
        f"catalog description is missing durable activation term {term!r}"
        for term in REQUIRED_ACTIVATION_TERMS
        if term.casefold() not in normalized
    ]


def validate_catalog(payload: Any, runtime: Path) -> dict[str, Any]:
    """Require one unambiguous catalog entry bound to the published bytes."""
    problems: list[str] = []
    skills = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(skills, list):
        return {
            "status": "FAIL",
            "problems": ["skills-list did not return an object with a skills array"],
            "skill_count": 0,
        }

    entries = [entry for entry in skills if isinstance(entry, dict)]
    canonical = [entry for entry in entries if entry.get("name") == "witsoc"]
    collisions = sorted(
        str(entry.get("name"))
        for entry in entries
        if isinstance(entry.get("name"), str)
        and entry.get("name") != "witsoc"
        and (
            entry["name"].casefold() == "witosc"
            or entry["name"].casefold().startswith("witsoc-")
            or entry["name"].casefold().startswith("witsoc.")
        )
    )
    if len(canonical) != 1:
        problems.append(f"skills-list contains {len(canonical)} canonical witsoc entries, expected 1")
    if collisions:
        problems.append(
            "skills-list contains competing Witsoc-like entries: " + ", ".join(collisions)
        )

    try:
        expected_description = extract_plane_description(runtime / "SKILL.md")
    except OSError as exc:
        expected_description = None
        problems.append(f"cannot read published SKILL.md: {exc}")
    problems.extend(description_problems(expected_description))

    if len(canonical) == 1:
        entry = canonical[0]
        if entry.get("path") != "witsoc":
            problems.append(f"catalog path is {entry.get('path')!r}, expected 'witsoc'")
        actual_description = entry.get("description")
        if actual_description in PLACEHOLDER_DESCRIPTIONS:
            problems.append(
                f"catalog description is a block scalar marker {actual_description!r}"
            )
        if actual_description != expected_description:
            problems.append("catalog description does not match the published SKILL.md bytes")

    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "skill_count": len(entries),
        "canonical_count": len(canonical),
        "collisions": collisions,
        "description": canonical[0].get("description") if len(canonical) == 1 else None,
    }


def _entries(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        return {}
    return {
        item["path"]: item
        for item in release.manifest(root)["files"]
    }


def classify(source: Path, runtime: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    runtime = runtime.expanduser().resolve()
    if not source.is_dir():
        raise SyncError(f"source does not exist: {source}")
    left = _entries(source)
    right = _entries(runtime)
    common = set(left) & set(right)
    identical = sorted(path for path in common if left[path] == right[path])
    divergent = sorted(path for path in common if left[path] != right[path])
    candidate_only = sorted(set(left) - set(right))
    runtime_only = sorted(set(right) - set(left))
    retired = [
        {
            "path": path,
            "sha256": right[path]["sha256"],
            "reason": "runtime-only legacy surface; retained in the atomic backup, not in the candidate release",
        }
        for path in runtime_only
    ]
    return {
        "schema": "witsoc.runtime-sync-plan.v1",
        "source": str(source),
        "runtime": str(runtime),
        "source_tree_sha256": release.manifest(source)["tree_sha256"],
        "runtime_tree_sha256": release.manifest(runtime)["tree_sha256"] if runtime.is_dir() else None,
        "identical": identical,
        "candidate_only": candidate_only,
        "runtime_only": runtime_only,
        "divergent": divergent,
        "retired_runtime_files": retired,
        "in_sync": bool(runtime.is_dir()) and not candidate_only and not runtime_only and not divergent,
        "summary": {
            "identical": len(identical),
            "candidate_only": len(candidate_only),
            "runtime_only": len(runtime_only),
            "divergent": len(divergent),
        },
    }


def check_source(source: Path, *, run_checks: bool) -> dict[str, Any]:
    source = source.expanduser().resolve()
    policy = load_policy(source / "references" / "runtime_sync.json")
    problems: list[str] = []
    for relative in policy["required_entrypoints"]:
        path = source / relative
        if not path.is_file():
            problems.append(f"missing required entrypoint {relative}")
    skill = source / "SKILL.md"
    if skill.is_file():
        content = skill.read_text(encoding="utf-8")
        if plane_frontmatter_scalar(content, "name") != "witsoc":
            problems.append("SKILL.md does not expose name: witsoc to Plane")
        problems.extend(
            f"SKILL.md {problem}" for problem in description_problems(
                plane_frontmatter_scalar(content, "description")
            )
        )
    generated = [
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() and ("__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"})
    ]
    check_result: dict[str, Any] = {"status": "NOT_RUN"}
    if run_checks and not problems:
        completed = subprocess.run(
            ["bash", str(source / "scripts" / "check.sh")],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        check_result = {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "exit_code": completed.returncode,
            "tail": (completed.stdout + completed.stderr)[-2000:],
        }
        if completed.returncode != 0:
            problems.append("candidate check.sh failed")
    return {
        "source": str(source),
        "tree_sha256": release.manifest(source)["tree_sha256"],
        "policy": policy,
        "checks": check_result,
        "excluded_generated_files": len(generated),
        "problems": problems,
        "ok": not problems,
    }


def resolve_active(runtime: Path) -> dict[str, Any]:
    configured = os.environ.get("WITSOC_PLANE_TOOL")
    command = Path(configured).expanduser() if configured else None
    if command is None:
        found = shutil.which("plane-tool")
        command = Path(found) if found else None
    if command is None:
        local_plane = Path.home() / "Extra" / "Intern" / "frontend" / "electron" / "plane-server" / "plane-tool.cjs"
        command = local_plane if local_plane.is_file() else None
    if command is None or not command.is_file():
        return {
            "status": "NOT_RUN",
            "reason": "plane-tool is unavailable",
            "problems": ["plane-tool is unavailable; published discovery cannot be verified"],
        }

    prefix = [str(command)]
    if command.suffix == ".cjs":
        node = shutil.which("node")
        if not node:
            return {
                "status": "NOT_RUN",
                "reason": "Plane tool exists but node is unavailable",
                "problems": ["node is unavailable; published discovery cannot be verified"],
            }
        prefix.insert(0, node)

    problems: list[str] = []
    resolutions: dict[str, dict[str, Any]] = {}
    for relative in (
        "SKILL.md",
        "scripts/route.py",
        "explorer/SKILL.md",
        "researcher/SKILL.md",
    ):
        argv = [*prefix, "skill-which", f"witsoc/{relative}"]
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (result.stdout or result.stderr).strip()
        expected = (runtime / relative).resolve()
        try:
            actual = Path(output).expanduser().resolve()
        except (OSError, RuntimeError):
            actual = Path(output)
        if result.returncode != 0:
            problems.append(
                f"skill-which {relative} exited {result.returncode}: {output[-300:]}"
            )
        elif actual != expected:
            problems.append(
                f"skill-which {relative} resolved {output!r}, expected {str(expected)!r}"
            )
        resolutions[relative] = {
            "command": argv,
            "expected": str(expected),
            "actual": output,
            "exit_code": result.returncode,
        }

    list_argv = [*prefix, "skills-list"]
    list_result = subprocess.run(
        list_argv,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    catalog: dict[str, Any]
    if list_result.returncode != 0:
        detail = (list_result.stdout or list_result.stderr).strip()
        problems.append(f"skills-list exited {list_result.returncode}: {detail[-300:]}")
        catalog = {"status": "FAIL", "problems": ["skills-list command failed"]}
    else:
        try:
            payload = json.loads(list_result.stdout)
        except json.JSONDecodeError as exc:
            problems.append(f"skills-list returned invalid JSON: {exc}")
            catalog = {"status": "FAIL", "problems": ["skills-list returned invalid JSON"]}
        else:
            catalog = validate_catalog(payload, runtime)
            problems.extend(catalog["problems"])

    return {
        "status": "PASS" if not problems else "FAIL",
        "commands": {
            "skill_which": resolutions["SKILL.md"]["command"],
            "skills_list": list_argv,
        },
        "expected": resolutions["SKILL.md"]["expected"],
        "actual": resolutions["SKILL.md"]["actual"],
        "exit_code": resolutions["SKILL.md"]["exit_code"],
        "resolutions": resolutions,
        "catalog": catalog,
        "problems": problems,
    }


def rollback_publication(runtime: Path, backup_value: object) -> str:
    """Restore the pre-publish runtime when Plane cannot discover the release."""
    backup = Path(str(backup_value)) if backup_value else None
    if runtime.is_symlink() or runtime.is_file():
        runtime.unlink()
    elif runtime.exists():
        shutil.rmtree(runtime)
    if backup is not None and backup.exists():
        backup.rename(runtime)
        return f"restored {runtime} from {backup}"
    return f"removed unverified publication at {runtime}; there was no prior runtime"


def apply(source: Path, runtime: Path, *, run_checks: bool) -> dict[str, Any]:
    source = source.expanduser().resolve()
    runtime = runtime.expanduser().resolve()
    before = classify(source, runtime)
    preflight = check_source(source, run_checks=run_checks)
    if not preflight["ok"]:
        raise SyncError("candidate preflight failed: " + "; ".join(preflight["problems"]))
    installed = release.install(source, runtime, run_checks=False)
    after = classify(source, runtime)
    if not after["in_sync"]:
        raise SyncError("published runtime differs from the candidate after atomic install")
    verification = release.verify(runtime, run_checks=False)
    if not verification["ok"]:
        raise SyncError("published runtime failed manifest verification")
    resolution = resolve_active(runtime)
    if resolution["status"] != "PASS":
        try:
            rollback = rollback_publication(runtime, installed.get("backup"))
        except OSError as exc:
            rollback = f"rollback failed: {exc}"
        detail = "; ".join(resolution.get("problems") or [resolution.get("reason", "unknown failure")])
        raise SyncError(f"Plane discovery validation failed: {detail}; {rollback}")
    return {
        "schema": "witsoc.runtime-sync-receipt.v1",
        "source": str(source),
        "runtime": str(runtime),
        "tree_sha256": after["source_tree_sha256"],
        "backup": installed["backup"],
        "preflight": preflight["checks"],
        "before_summary": before["summary"],
        "retired_runtime_files": before["retired_runtime_files"],
        "after_summary": after["summary"],
        "manifest_verified": True,
        "resolution": resolution,
        "ok": True,
    }


def self_test() -> dict[str, Any]:
    cases: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="witsoc-sync-selftest-") as raw:
        root = Path(raw)
        source = root / "source"
        runtime = root / "strings" / "skills" / "witsoc"
        (source / "scripts").mkdir(parents=True)
        (source / "references").mkdir(parents=True)
        runtime.mkdir(parents=True)
        test_description = (
            "Open-problem work. Use automatically, even when not named. Activation is sticky "
            "and never deselects Witsoc. Treat witosc as Witsoc and stack with orchestration skills."
        )
        (source / "SKILL.md").write_text(
            f"---\nname: witsoc\ndescription: {test_description}\n---\n", encoding="utf-8"
        )
        policy = load_policy()
        (source / "references" / "runtime_sync.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )
        for name in ("witsoc.sh", "check.sh", "resolve.sh", "campaign.sh", "scaffold.sh", "release.sh"):
            path = source / "scripts" / name
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        for name in ("witsoc.py", "sync_runtime.py", "release.py", "route.py"):
            path = source / "scripts" / name
            path.write_text("#!/usr/bin/env python3\n# test\n", encoding="utf-8")
            if name == "route.py":
                path.chmod(0o755)
        (source / "same.txt").write_text("same", encoding="utf-8")
        (source / "candidate.txt").write_text("candidate", encoding="utf-8")
        (source / "changed.txt").write_text("new", encoding="utf-8")
        (runtime / "same.txt").write_text("same", encoding="utf-8")
        (runtime / "legacy.txt").write_text("legacy", encoding="utf-8")
        (runtime / "changed.txt").write_text("old", encoding="utf-8")
        plan = classify(source, runtime)
        cases.extend([
            ("identical files classified", "same.txt" in plan["identical"]),
            ("candidate-only files classified", "candidate.txt" in plan["candidate_only"]),
            ("runtime-only files explicitly retired", any(item["path"] == "legacy.txt" for item in plan["retired_runtime_files"])),
            ("divergent files classified", "changed.txt" in plan["divergent"]),
        ])
        installed = release.install(source, runtime, run_checks=False)
        after = classify(source, runtime)
        cases.append(("atomic publication reaches exact sync", after["in_sync"]))
        installed_backup = Path(str(installed["backup"])) if installed["backup"] else None
        cases.append(("replaced runtime retained as backup", bool(installed_backup and installed_backup.is_dir())))
        cases.append((
            "backup is outside Plane's discoverable skills directory",
            bool(installed_backup and runtime.parent not in installed_backup.parents),
        ))
        valid_catalog = {
            "skills": [
                {"name": "witsoc", "path": "witsoc", "description": test_description}
            ]
        }
        cases.append((
            "one canonical catalog entry is accepted",
            validate_catalog(valid_catalog, runtime)["status"] == "PASS",
        ))
        marker_catalog = {
            "skills": [{"name": "witsoc", "path": "witsoc", "description": ">"}]
        }
        cases.append((
            "block scalar catalog description is rejected",
            validate_catalog(marker_catalog, runtime)["status"] == "FAIL",
        ))
        backup_catalog = {
            "skills": [
                {"name": "witsoc", "path": "witsoc", "description": test_description},
                {"name": "witsoc.backup-20260902T000000Z", "path": "witsoc.backup-20260902T000000Z", "description": test_description},
            ]
        }
        cases.append((
            "discoverable backup entry is rejected",
            validate_catalog(backup_catalog, runtime)["status"] == "FAIL",
        ))
        alias_catalog = {
            "skills": [
                {"name": "witsoc", "path": "witsoc", "description": test_description},
                {"name": "witosc", "path": "witosc", "description": test_description},
            ]
        }
        cases.append((
            "competing misspelled alias is rejected",
            validate_catalog(alias_catalog, runtime)["status"] == "FAIL",
        ))
        drift_catalog = {
            "skills": [{"name": "witsoc", "path": "witsoc", "description": "stale"}]
        }
        cases.append((
            "catalog description drift is rejected",
            validate_catalog(drift_catalog, runtime)["status"] == "FAIL",
        ))
    return {
        "schema": "witsoc.runtime-sync-selftest.v1",
        "cases": [{"name": name, "ok": ok} for name, ok in cases],
        "ok": all(ok for _, ok in cases),
    }


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--summary", action="store_true")
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--run-checks", action="store_true")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--run-checks", action="store_true")
    apply_parser.add_argument("--receipt", type=Path)
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = classify(args.source, args.runtime)
            if args.summary:
                result = {
                    "schema": result["schema"],
                    "source": result["source"],
                    "runtime": result["runtime"],
                    "source_tree_sha256": result["source_tree_sha256"],
                    "runtime_tree_sha256": result["runtime_tree_sha256"],
                    "summary": result["summary"],
                    "retired_runtime_file_count": len(result["retired_runtime_files"]),
                    "in_sync": result["in_sync"],
                }
        elif args.command == "check":
            result = check_source(args.source, run_checks=args.run_checks)
            result["sync"] = classify(args.source, args.runtime)
        elif args.command == "apply":
            result = apply(args.source, args.runtime, run_checks=args.run_checks)
            if args.receipt:
                args.receipt.parent.mkdir(parents=True, exist_ok=True)
                args.receipt.write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
        else:
            result = self_test()
    except (OSError, SyncError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
