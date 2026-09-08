"""Discover, install, verify, and activate versioned Witsoc domain packs."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .canonical import atomic_write_json, digest_value, load_json


REGISTRY_SCHEMA = "witsoc.domain-package-registry.v1"
PACK_SCHEMA = "witsoc.domain-package.v1"
CORE_API = 1
REGISTRY_PATH = Path("contracts/domain-packages.json")
FALSE_VALUES = {"0", "false", "no", "off"}
INSTALLERS = {"auto", "pip", "curl"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[A-Za-z0-9._-]*)$")
MAX_WHEEL_FILES = 4096
MAX_WHEEL_BYTES = 64 * 1024 * 1024
ACTIVATION_MARKER = ".witsoc-domain-pack.json"
INSTALL_RECEIPT_V1 = "witsoc.domain-install-receipt.v1"
INSTALL_RECEIPT_V2 = "witsoc.domain-install-receipt.v2"


class DomainPackageError(ValueError):
    pass


def _closed(value: Mapping[str, Any], required: set[str], label: str) -> None:
    missing, extra = required - set(value), set(value) - required
    if missing or extra:
        raise DomainPackageError(
            f"{label} shape mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _truthy_environment(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in FALSE_VALUES


def load_registry(root: Path) -> dict[str, Any]:
    try:
        value = load_json(root / REGISTRY_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"cannot read domain package registry: {exc}") from exc
    _closed(value, {"schema", "version", "core_api", "packages"}, "package registry")
    if value["schema"] != REGISTRY_SCHEMA or value["version"] != 1:
        raise DomainPackageError("unsupported domain package registry")
    if value["core_api"] != CORE_API:
        raise DomainPackageError("domain package registry targets a different core API")
    if not isinstance(value["packages"], list) or not value["packages"]:
        raise DomainPackageError("domain package registry is empty")
    expected = {
        "domain", "distribution", "version", "import_package", "payload_subdir",
        "core_api", "domain_contract_version", "payload_sha256", "payload_files",
        "payload_bytes", "selection", "source_projection",
    }
    seen_domains: set[str] = set()
    seen_distributions: set[str] = set()
    for index, entry in enumerate(value["packages"]):
        label = f"package registry packages[{index}]"
        if not isinstance(entry, dict):
            raise DomainPackageError(f"{label} must be an object")
        _closed(entry, expected, label)
        domain = entry["domain"]
        distribution = entry["distribution"]
        if not isinstance(domain, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", domain):
            raise DomainPackageError(f"{label} has an invalid domain")
        if not isinstance(distribution, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", distribution):
            raise DomainPackageError(f"{label} has an invalid distribution")
        if domain in seen_domains or distribution in seen_distributions:
            raise DomainPackageError(f"{label} duplicates a domain or distribution")
        seen_domains.add(domain)
        seen_distributions.add(distribution)
        if not isinstance(entry["version"], str) or not VERSION.fullmatch(entry["version"]):
            raise DomainPackageError(f"{label} has an invalid version")
        if not isinstance(entry["import_package"], str) or not entry["import_package"].isidentifier():
            raise DomainPackageError(f"{label} has an invalid import package")
        if entry["payload_subdir"] != "domain":
            raise DomainPackageError(f"{label} has an unsupported payload subdirectory")
        if entry["core_api"] != {"minimum": CORE_API, "maximum": CORE_API}:
            raise DomainPackageError(f"{label} is incompatible with core API {CORE_API}")
        if not isinstance(entry["domain_contract_version"], int) or entry["domain_contract_version"] < 1:
            raise DomainPackageError(f"{label} has an invalid domain contract version")
        if not isinstance(entry["payload_sha256"], str) or not SHA256.fullmatch(entry["payload_sha256"]):
            raise DomainPackageError(f"{label} has an invalid payload digest")
        if not isinstance(entry["payload_files"], int) or entry["payload_files"] < 1:
            raise DomainPackageError(f"{label} has an invalid payload file count")
        if not isinstance(entry["payload_bytes"], int) or entry["payload_bytes"] < 1:
            raise DomainPackageError(f"{label} has an invalid payload byte count")
        projection = entry["source_projection"]
        projection_fields = {
            "exclude_parts", "exclude_part_prefixes", "exclude_suffixes",
            "exclude_root_paths", "include_eval_prefixes",
        }
        if not isinstance(projection, dict):
            raise DomainPackageError(f"{label} source projection must be an object")
        _closed(projection, projection_fields, f"{label} source projection")
        for key in projection_fields:
            if not isinstance(projection[key], list) or any(
                not isinstance(item, str) or not item for item in projection[key]
            ):
                raise DomainPackageError(f"{label} source projection.{key} is invalid")
        selection = entry["selection"]
        required_selection = {
            "signals", "strong_signals", "excludes", "examples", "counter_examples",
            "min_score", "priority",
        }
        if not isinstance(selection, dict):
            raise DomainPackageError(f"{label} selection must be an object")
        _closed(selection, required_selection, f"{label} selection")
        for key in ("signals", "strong_signals", "excludes", "examples", "counter_examples"):
            if not isinstance(selection[key], list) or any(
                not isinstance(term, str) or not term.strip() for term in selection[key]
            ):
                raise DomainPackageError(f"{label} selection.{key} is invalid")
        if not isinstance(selection["min_score"], (int, float)) or isinstance(selection["min_score"], bool):
            raise DomainPackageError(f"{label} selection.min_score is invalid")
        if not isinstance(selection["priority"], int) or isinstance(selection["priority"], bool):
            raise DomainPackageError(f"{label} selection.priority is invalid")
    return value


def routing_packs(root: Path) -> list[dict[str, Any]]:
    """Return compact resolver inputs without loading a domain payload."""
    return [
        {
            "domain": entry["domain"],
            "selection": entry["selection"],
            "contract_version": str(entry["domain_contract_version"]),
            "description": f"Installable {entry['distribution']} domain distribution",
            "_dir": root / "domains" / entry["domain"],
            "_package": entry,
        }
        for entry in load_registry(root)["packages"]
    ]


def _cache_root() -> Path:
    configured = os.environ.get("WITSOC_PACK_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".openscientist" / "strings" / "domain-packs" / "witsoc").resolve()


def _cache_release(entry: Mapping[str, Any], cache_root: Path | None = None) -> Path:
    base = cache_root or _cache_root()
    return base / entry["domain"] / entry["version"]


def _installed_paths(entry: Mapping[str, Any], release: Path) -> tuple[Path, Path]:
    package = release / "site" / entry["import_package"]
    return package / "pack.json", package / entry["payload_subdir"]


def _payload_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise DomainPackageError(f"installed payload contains a symbolic link: {relative}")
        if (
            not path.is_file()
            or relative == Path(ACTIVATION_MARKER)
            or "__pycache__" in relative.parts
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        records.append({
            "path": relative.as_posix(),
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        })
    return sorted(records, key=lambda item: item["path"])


def _source_payload_records(
    root: Path, projection: Mapping[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    eval_prefixes = {
        tuple(Path(item).parts) for item in projection["include_eval_prefixes"]
    }
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        in_runtime_eval = any(
            relative.parts[:len(prefix)] == prefix for prefix in eval_prefixes
        )
        if (
            not path.is_file()
            or any(part in projection["exclude_parts"] for part in relative.parts)
            or any(
                part.startswith(prefix)
                for part in relative.parts
                for prefix in projection["exclude_part_prefixes"]
            )
            or path.suffix in projection["exclude_suffixes"]
            or relative.as_posix() in projection["exclude_root_paths"]
            or ("evals" in relative.parts and not in_runtime_eval)
        ):
            continue
        records.append({
            "path": relative.as_posix(),
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        })
    return sorted(records, key=lambda item: item["path"])


def _validate_payload(
    entry: Mapping[str, Any], payload: Path, *, development_source: bool = False
) -> dict[str, Any]:
    if not payload.is_dir():
        raise DomainPackageError("installed pack has no domain payload")
    actual = (
        _source_payload_records(payload, entry["source_projection"])
        if development_source else _payload_records(payload)
    )
    digest = hashlib.sha256(_canonical_json(actual)).hexdigest()
    byte_count = sum(item["size"] for item in actual)
    if (
        digest != entry["payload_sha256"]
        or len(actual) != entry["payload_files"]
        or byte_count != entry["payload_bytes"]
    ):
        raise DomainPackageError("domain payload differs from the pinned registry")
    try:
        domain_manifest = load_json(payload / "domain.json")
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"installed domain manifest is unreadable: {exc}") from exc
    if domain_manifest.get("domain") != entry["domain"]:
        raise DomainPackageError("installed domain identity differs from the registry")
    try:
        installed_contract = int(domain_manifest.get("contract_version"))
    except (TypeError, ValueError) as exc:
        raise DomainPackageError("installed domain contract version is invalid") from exc
    if installed_contract != entry["domain_contract_version"]:
        raise DomainPackageError("installed domain contract version differs from the registry")
    return {
        "domain_root": str(payload),
        "payload_sha256": digest,
        "payload_files": len(actual),
        "payload_bytes": byte_count,
    }


def _install_receipt(entry: Mapping[str, Any], source: str, installer: str) -> dict[str, Any]:
    body = {
        "schema": INSTALL_RECEIPT_V2,
        "domain": entry["domain"],
        "distribution": entry["distribution"],
        "version": entry["version"],
        "core_api": CORE_API,
        "domain_contract_version": entry["domain_contract_version"],
        "source": source,
        "installer": installer,
        "payload_sha256": entry["payload_sha256"],
    }
    return {**body, "receipt_sha256": digest_value(body)}


def _validate_install_receipt(entry: Mapping[str, Any], release: Path) -> str:
    try:
        receipt = load_json(release / "receipt.json")
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"installed pack receipt is unreadable: {exc}") from exc
    schema = receipt.get("schema")
    if schema == INSTALL_RECEIPT_V1:
        required = {
            "schema", "domain", "distribution", "version", "source",
            "payload_sha256", "installer",
        }
        _closed(receipt, required, "legacy install receipt")
    elif schema == INSTALL_RECEIPT_V2:
        required = {
            "schema", "domain", "distribution", "version", "core_api",
            "domain_contract_version", "source", "installer", "payload_sha256",
            "receipt_sha256",
        }
        _closed(receipt, required, "install receipt")
        expected = digest_value({
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        })
        if receipt["receipt_sha256"] != expected:
            raise DomainPackageError("installed pack receipt seal is invalid")
        if (
            receipt["core_api"] != CORE_API
            or receipt["domain_contract_version"] != entry["domain_contract_version"]
        ):
            raise DomainPackageError("installed pack receipt targets an incompatible contract")
    else:
        raise DomainPackageError("installed pack receipt schema is unsupported")
    for key in ("domain", "distribution", "version", "payload_sha256"):
        if receipt.get(key) != entry[key]:
            raise DomainPackageError(f"installed pack receipt {key} differs from the registry")
    if receipt.get("installer") not in INSTALLERS or not str(receipt.get("source", "")).strip():
        raise DomainPackageError("installed pack receipt source or installer is invalid")
    return digest_value(receipt)


def validate_release(
    entry: Mapping[str, Any], release: Path, *, require_receipt: bool = True
) -> dict[str, Any]:
    metadata_path, payload = _installed_paths(entry, release)
    try:
        metadata = load_json(metadata_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"cannot read installed pack metadata: {exc}") from exc
    required = {
        "schema", "domain", "distribution", "version", "import_package",
        "payload_subdir", "core_api", "domain_contract_version", "payload_sha256",
        "payload_files", "payload_bytes", "files",
    }
    if not isinstance(metadata, dict):
        raise DomainPackageError("installed pack metadata must be an object")
    _closed(metadata, required, "installed pack metadata")
    if metadata["schema"] != PACK_SCHEMA:
        raise DomainPackageError("installed pack metadata has an unsupported schema")
    for key in (
        "domain", "distribution", "version", "import_package", "payload_subdir",
        "core_api", "domain_contract_version", "payload_sha256", "payload_files",
        "payload_bytes",
    ):
        if metadata[key] != entry[key]:
            raise DomainPackageError(f"installed pack {key} differs from the pinned registry")
    actual = _payload_records(payload)
    if metadata["files"] != actual:
        raise DomainPackageError("installed domain files differ from the signed pack manifest")
    digest = hashlib.sha256(_canonical_json(actual)).hexdigest()
    if digest != entry["payload_sha256"]:
        raise DomainPackageError("installed domain payload digest differs from the pinned registry")
    validated = _validate_payload(entry, payload)
    receipt_sha256 = _validate_install_receipt(entry, release) if require_receipt else None
    return {
        "release": str(release),
        **validated,
        "install_receipt_sha256": receipt_sha256,
    }


def _normalized_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "_", value).casefold()


def _wheel_from_directory(entry: Mapping[str, Any], wheelhouse: Path) -> Path | None:
    if not wheelhouse.is_dir():
        return None
    prefix = f"{_normalized_distribution(entry['distribution'])}-{entry['version']}-"
    matches = [
        path for path in wheelhouse.glob("*.whl")
        if path.name.casefold().startswith(prefix) and path.name.endswith("-py3-none-any.whl")
    ]
    if len(matches) > 1:
        raise DomainPackageError(
            f"wheelhouse has multiple matching wheels for {entry['distribution']}=={entry['version']}"
        )
    return matches[0] if matches else None


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr).strip()[-1600:]
        raise DomainPackageError(f"command failed ({command[0]}): {detail}")
    return completed


def _pip_install(entry: Mapping[str, Any], site: Path, wheel: Path | None) -> str:
    if importlib.util.find_spec("pip") is None:
        raise DomainPackageError("pip is unavailable")
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-deps",
        "--only-binary=:all:",
        "--no-compile",
        "--target",
        str(site),
    ]
    if wheel is not None:
        command.extend(["--no-index", str(wheel)])
        source = str(wheel)
    else:
        command.extend([
            "--index-url",
            "https://pypi.org/simple",
            f"{entry['distribution']}=={entry['version']}",
        ])
        source = f"pypi:{entry['distribution']}=={entry['version']}"
    _run(command)
    return source


def _safe_extract_wheel(wheel: Path, site: Path) -> None:
    try:
        with zipfile.ZipFile(wheel) as archive:
            members = archive.infolist()
            total = sum(item.file_size for item in members)
            if len(members) > MAX_WHEEL_FILES or total > MAX_WHEEL_BYTES:
                raise DomainPackageError("wheel exceeds the domain-pack extraction limits")
            for item in members:
                relative = PurePosixPath(item.filename)
                mode = (item.external_attr >> 16) & 0o170000
                if (
                    relative.is_absolute()
                    or not relative.parts
                    or ".." in relative.parts
                    or stat.S_ISLNK(mode)
                ):
                    raise DomainPackageError(f"wheel contains an unsafe member: {item.filename}")
                target = site.joinpath(*relative.parts)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)
    except zipfile.BadZipFile as exc:
        raise DomainPackageError(f"downloaded wheel is invalid: {exc}") from exc


def _curl_download(entry: Mapping[str, Any], temporary: Path) -> tuple[Path, str]:
    curl = shutil.which("curl")
    if not curl:
        raise DomainPackageError("curl is unavailable")
    distribution = urllib.parse.quote(str(entry["distribution"]), safe="")
    version = urllib.parse.quote(str(entry["version"]), safe="")
    metadata_url = f"https://pypi.org/pypi/{distribution}/{version}/json"
    metadata_path = temporary / "pypi.json"
    common = [curl, "--fail", "--silent", "--show-error", "--location", "--proto", "=https", "--tlsv1.2"]
    _run([*common, "--output", str(metadata_path), metadata_url])
    try:
        response = load_json(metadata_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"PyPI returned invalid package metadata: {exc}") from exc
    expected_prefix = f"{_normalized_distribution(entry['distribution'])}-{entry['version']}-"
    choices = [
        item for item in response.get("urls", [])
        if isinstance(item, dict)
        and item.get("packagetype") == "bdist_wheel"
        and not item.get("yanked")
        and str(item.get("filename", "")).casefold().startswith(expected_prefix)
        and str(item.get("filename", "")).endswith("-py3-none-any.whl")
    ]
    if len(choices) != 1:
        raise DomainPackageError(
            f"PyPI exposes {len(choices)} compatible wheels for "
            f"{entry['distribution']}=={entry['version']}; expected one"
        )
    choice = choices[0]
    url = str(choice.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise DomainPackageError("PyPI wheel URL is outside files.pythonhosted.org")
    expected_digest = ((choice.get("digests") or {}).get("sha256"))
    if not isinstance(expected_digest, str) or not SHA256.fullmatch(expected_digest):
        raise DomainPackageError("PyPI wheel metadata has no valid SHA256 digest")
    wheel = temporary / str(choice["filename"])
    _run([*common, "--output", str(wheel), url])
    if _sha256(wheel) != expected_digest:
        raise DomainPackageError("downloaded wheel differs from PyPI's SHA256 digest")
    return wheel, url


def _install_into_stage(
    entry: Mapping[str, Any],
    stage: Path,
    *,
    installer: str,
    wheelhouse: Path | None,
    offline: bool,
) -> str:
    site = stage / "site"
    site.mkdir(parents=True)
    wheel = _wheel_from_directory(entry, wheelhouse) if wheelhouse else None
    if wheel is not None:
        if installer == "curl" or importlib.util.find_spec("pip") is None:
            _safe_extract_wheel(wheel, site)
            return str(wheel)
        return _pip_install(entry, site, wheel)
    if offline:
        raise DomainPackageError("offline mode requires a matching wheel in WITSOC_PACK_WHEELHOUSE")
    if installer in {"auto", "pip"}:
        try:
            return _pip_install(entry, site, None)
        except DomainPackageError:
            if installer == "pip":
                raise
            shutil.rmtree(site)
            site.mkdir()
    wheel, source = _curl_download(entry, stage)
    _safe_extract_wheel(wheel, site)
    wheel.unlink(missing_ok=True)
    (stage / "pypi.json").unlink(missing_ok=True)
    return source


def _attestation(
    entry: Mapping[str, Any], validated: Mapping[str, Any], status: str
) -> dict[str, Any]:
    body = {
        "domain": entry["domain"],
        "distribution": entry["distribution"],
        "version": entry["version"],
        "core_api": CORE_API,
        "domain_contract_version": entry["domain_contract_version"],
        "payload_sha256": validated["payload_sha256"],
        "payload_files": validated["payload_files"],
        "payload_bytes": validated["payload_bytes"],
        "install_receipt_sha256": validated.get("install_receipt_sha256"),
        "status": status,
    }
    return {**body, "activation_sha256": digest_value(body)}


def _activation_metadata(
    entry: Mapping[str, Any], validated: Mapping[str, Any]
) -> dict[str, Any]:
    body = {
        "schema": "witsoc.domain-activation.v2",
        "domain": entry["domain"],
        "distribution": entry["distribution"],
        "version": entry["version"],
        "core_api": CORE_API,
        "domain_contract_version": entry["domain_contract_version"],
        "payload_sha256": entry["payload_sha256"],
        "payload_files": validated["payload_files"],
        "payload_bytes": validated["payload_bytes"],
        "install_receipt_sha256": validated.get("install_receipt_sha256"),
    }
    return {**body, "activation_sha256": digest_value(body)}


def _validate_activation(entry: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    try:
        marker = load_json(destination / ACTIVATION_MARKER)
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainPackageError(f"active domain marker is unreadable: {exc}") from exc
    validated = _validate_payload(entry, destination)
    expected = _activation_metadata(entry, {
        **validated,
        "install_receipt_sha256": marker.get("install_receipt_sha256"),
    })
    if marker != expected:
        raise DomainPackageError("active domain marker differs from the pinned registry")
    return {
        **validated,
        "install_receipt_sha256": marker["install_receipt_sha256"],
        "activation_sha256": marker["activation_sha256"],
    }


def _activate(
    root: Path,
    entry: Mapping[str, Any],
    payload: Path,
    validated: Mapping[str, Any],
) -> bool:
    domains = root / "domains"
    domains.mkdir(parents=True, exist_ok=True)
    destination = domains / entry["domain"]
    if destination.is_dir() and (destination / ACTIVATION_MARKER).is_file():
        try:
            _validate_activation(entry, destination)
            return False
        except DomainPackageError:
            pass
    elif destination.exists() or destination.is_symlink():
        raise DomainPackageError(
            f"domain activation target exists without a valid marker: {destination}"
        )
    temporary = Path(tempfile.mkdtemp(prefix=f".{entry['domain']}.activate-", dir=domains))
    temporary.rmdir()
    backup: Path | None = None
    try:
        shutil.copytree(payload, temporary, copy_function=shutil.copy2)
        atomic_write_json(
            temporary / ACTIVATION_MARKER, _activation_metadata(entry, validated)
        )
        _validate_activation(entry, temporary)
        if destination.exists() or destination.is_symlink():
            backup = Path(tempfile.mkdtemp(prefix=f".{entry['domain']}.retired-", dir=domains))
            backup.rmdir()
            destination.rename(backup)
        temporary.rename(destination)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return True


def _source_domain(root: Path, entry: Mapping[str, Any]) -> Path | None:
    path = root / "domains" / entry["domain"]
    return (
        path
        if path.is_dir()
        and not (path / ACTIVATION_MARKER).is_file()
        and (path / "domain.json").is_file()
        else None
    )


def _entry_map(root: Path) -> dict[str, dict[str, Any]]:
    return {entry["domain"]: entry for entry in load_registry(root)["packages"]}


def ensure_domains(
    root: Path,
    domains: Iterable[str],
    *,
    installer: str | None = None,
    wheelhouse: Path | None = None,
    offline: bool | None = None,
    allow_install: bool | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    entries = _entry_map(root)
    requested = sorted(set(domains))
    unknown = [domain for domain in requested if domain not in entries]
    if unknown:
        raise DomainPackageError(f"no installable domain package is registered for {unknown}")
    selected_installer = (installer or os.environ.get("WITSOC_PACK_INSTALLER") or "auto").casefold()
    if selected_installer not in INSTALLERS:
        raise DomainPackageError(f"unsupported domain package installer {selected_installer!r}")
    if wheelhouse is None and os.environ.get("WITSOC_PACK_WHEELHOUSE"):
        wheelhouse = Path(os.environ["WITSOC_PACK_WHEELHOUSE"])
    wheelhouse = wheelhouse.expanduser().resolve() if wheelhouse else None
    selected_offline = _truthy_environment("WITSOC_PACK_OFFLINE", False) if offline is None else offline
    selected_allow = (
        _truthy_environment("WITSOC_PACK_AUTO_INSTALL", True)
        if allow_install is None else allow_install
    )
    cache_root = _cache_root()
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_root.chmod(0o700)
    actions: list[dict[str, Any]] = []
    side_effects: list[str] = []
    problems: list[str] = []
    for domain in requested:
        entry = entries[domain]
        source = _source_domain(root, entry)
        if source is not None:
            validated_source = _validate_payload(entry, source, development_source=True)
            attestation = _attestation(
                entry, {**validated_source, "install_receipt_sha256": None},
                "DEVELOPMENT_SOURCE",
            )
            actions.append({
                **attestation,
                "domain_root": str(source),
                "transaction_id": f"domain:{domain}:{attestation['activation_sha256'][:16]}",
            })
            continue
        release = _cache_release(entry, cache_root)
        lock_dir = release.parent
        lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with (lock_dir / ".install.lock").open("a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                valid: dict[str, Any] | None = None
                if release.is_dir():
                    try:
                        valid = validate_release(entry, release, require_receipt=True)
                    except DomainPackageError:
                        shutil.rmtree(release)
                installed_from: str | None = None
                if valid is None:
                    if not selected_allow:
                        raise DomainPackageError(
                            f"{entry['distribution']}=={entry['version']} is required but automatic installation is disabled"
                        )
                    stage = Path(tempfile.mkdtemp(prefix=".install-", dir=lock_dir))
                    try:
                        installed_from = _install_into_stage(
                            entry,
                            stage,
                            installer=selected_installer,
                            wheelhouse=wheelhouse,
                            offline=selected_offline,
                        )
                        valid = validate_release(entry, stage, require_receipt=False)
                        atomic_write_json(
                            stage / "receipt.json",
                            _install_receipt(entry, installed_from, selected_installer),
                        )
                        stage.rename(release)
                        valid = validate_release(entry, release, require_receipt=True)
                        side_effects.append(f"INSTALL:{entry['distribution']}=={entry['version']}")
                    finally:
                        if stage.exists():
                            shutil.rmtree(stage, ignore_errors=True)
                payload = Path(valid["domain_root"])
                activated = _activate(root, entry, payload, valid)
                if activated:
                    side_effects.append(f"ACTIVATE:{domain}")
                active = _validate_activation(entry, root / "domains" / domain)
                attestation = _attestation(entry, active, "ACTIVE")
                actions.append({
                    **attestation,
                    "transaction_status": "INSTALLED" if installed_from else "READY",
                    "domain_root": str(root / "domains" / domain),
                    "cache_domain_root": str(payload),
                    "activated": activated,
                    "source": installed_from,
                    "transaction_id": f"domain:{domain}:{attestation['activation_sha256'][:16]}",
                })
        except (OSError, DomainPackageError, subprocess.SubprocessError) as exc:
            problems.append(f"{domain}: {exc}")
            actions.append({
                "domain": domain,
                "distribution": entry["distribution"],
                "version": entry["version"],
                "status": "FAILED",
                "error": str(exc),
            })
    return {
        "schema": "witsoc.domain-package-activation.v1",
        "ok": not problems,
        "requested": requested,
        "installer": selected_installer,
        "offline": selected_offline,
        "wheelhouse": str(wheelhouse) if wheelhouse else None,
        "cache_root": str(cache_root),
        "actions": actions,
        "side_effects": side_effects,
        "problems": problems,
    }


def status(root: Path, *, verify: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    result: list[dict[str, Any]] = []
    for entry in load_registry(root)["packages"]:
        source = _source_domain(root, entry)
        release = _cache_release(entry)
        domain_path = root / "domains" / entry["domain"]
        state = "DEVELOPMENT_SOURCE" if source else "MISSING"
        problem: str | None = None
        details: dict[str, Any] = {}
        if source is not None and verify:
            try:
                validated = _validate_payload(entry, source, development_source=True)
                details = {
                    **validated,
                    **_attestation(
                        entry,
                        {**validated, "install_receipt_sha256": None},
                        "DEVELOPMENT_SOURCE",
                    ),
                }
            except (OSError, DomainPackageError) as exc:
                state, problem = "INVALID", str(exc)
        elif source is None and release.is_dir():
            state = "CACHED"
            if verify:
                try:
                    details = validate_release(entry, release, require_receipt=True)
                    if (domain_path / ACTIVATION_MARKER).is_file():
                        details["activation"] = _validate_activation(entry, domain_path)
                        if (
                            details["activation"]["install_receipt_sha256"]
                            != details["install_receipt_sha256"]
                        ):
                            raise DomainPackageError(
                                "active domain and cached release have different install receipts"
                            )
                        state = "ACTIVE"
                        details.update(_attestation(entry, details["activation"], state))
                    else:
                        state = "CACHED"
                except (OSError, DomainPackageError) as exc:
                    state, problem = "INVALID", str(exc)
            elif (domain_path / ACTIVATION_MARKER).is_file():
                state = "ACTIVE"
        result.append({
            "domain": entry["domain"],
            "distribution": entry["distribution"],
            "version": entry["version"],
            "status": state,
            "payload_sha256": entry["payload_sha256"],
            "problem": problem,
            **details,
        })
    return {
        "schema": "witsoc.domain-package-status.v1",
        "core_api": CORE_API,
        "cache_root": str(_cache_root()),
        "packages": result,
        "ok": not any(item["status"] == "INVALID" for item in result),
    }
