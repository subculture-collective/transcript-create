#!/usr/bin/env python3
"""Validate a HasanAra release without exposing rendered Compose secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_ROLES = {"api", "ingest-cuda", "ml-cuda", "frontend", "postgres-walg", "redis"}
SERVICE_ROLES = {
    "db": "postgres-walg",
    "backup": "postgres-walg",
    "migrations": "api",
    "api": "api",
    "analytics-retention": "api",
    "summary-refresher": "api",
    "archive-intelligence-refresher": "api",
    "archive-enrichment-queue": "api",
    "worker": "ingest-cuda",
    "diarization-worker": "ml-cuda",
    "frontend": "frontend",
    "redis": "redis",
}
RETIRABLE_SERVICES = {"opensearch", "dashboards", "prometheus", "grafana", "diarization-worker"}
BASE_SERVICES = set(SERVICE_ROLES) - {"diarization-worker"}
DATABASE_CLIENTS = {
    "migrations",
    "api",
    "worker",
    "analytics-retention",
    "summary-refresher",
    "archive-intelligence-refresher",
    "archive-enrichment-queue",
    "backup",
}
APPLICATION_SERVICES = DATABASE_CLIENTS - {"backup"}
SERVICE_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
COMPOSE_ROW_DELIMITER = "\x1f"
COMPOSE_ONEOFF_LABELS = {"", "false", "0", "no"}
URL_UNRESERVED_RE = re.compile(r"^[A-Za-z0-9._~-]+$")
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.gtx1080.yml",
    "docker-compose.hasanara.yml",
    "docker-compose.storage.yml",
    "docker-compose.pitr.yml",
    "docker-compose.release.yml",
)
DIARIZATION_SNAPSHOT = "/root/.cache/hf/hub/models--pyannote--speaker-diarization-community-1/snapshots/3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
DIARIZATION_ENV_KEYS = {"HF_TOKEN", "DATABASE_URL"}
DIARIZATION_RENDERED_ENVIRONMENT = {
    "HF_TOKEN",
    "DATABASE_URL",
    "HF_HOME",
    "HF_HUB_CACHE",
    "TRANSFORMERS_CACHE",
    "SEARCH_BACKEND",
    "OPENSEARCH_URL",
    "REDIS_URL",
    "ROCM",
    "ENABLE_DIARIZATION",
    "DIARIZATION_INLINE",
    "DIARIZATION_DEVICE",
    "DIARIZATION_MODEL",
    "DIARIZATION_FALLBACK_MODEL",
    "DIARIZATION_STRICT",
    "DIARIZATION_REQUIRE_ALLOWLIST",
    "DIARIZATION_EXIT_WHEN_IDLE",
    "DIARIZATION_MAX_DURATION_SECONDS",
    "DIARIZATION_MAX_JOBS_PER_PROCESS",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION",
    "ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION",
}
FOUR_GIB_VALUES = {"4g", "4G", 4_294_967_296, "4294967296"}
ENRICHMENT_QUEUE_COMMAND = ["python3", "/app/scripts/run_archive_enrichment_queue.py", "--once"]
FALSE_ENV_VALUES = {"false", "False", "FALSE", "0", False}


class PreflightError(Exception):
    """An intentionally non-sensitive validation error."""


class SafeArgumentParser(argparse.ArgumentParser):
    """Avoid argparse repeating arbitrary operator input in an error message."""

    def error(self, message: str) -> NoReturn:
        del message
        raise PreflightError("invalid arguments")


def fail(message: str) -> NoReturn:
    raise PreflightError(message)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("release manifest is missing or invalid")
    if not isinstance(data, dict) or set(data) != {"schema_version", "source_commit", "images", "services"}:
        fail("release manifest has an invalid schema")
    if (
        data["schema_version"] != 1
        or not isinstance(data["source_commit"], str)
        or not COMMIT_RE.fullmatch(data["source_commit"])
    ):
        fail("release manifest has an invalid schema")
    if not isinstance(data["images"], dict) or set(data["images"]) != IMAGE_ROLES:
        fail("release manifest has an invalid schema")
    if not all(isinstance(value, str) and DIGEST_RE.fullmatch(value) for value in data["images"].values()):
        fail("release manifest has an invalid image reference")
    if data["services"] != SERVICE_ROLES:
        fail("release manifest has an invalid service mapping")
    return data


def run(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def checked(command: Sequence[str], *, cwd: Path, error: str) -> subprocess.CompletedProcess[str]:
    result = run(command, cwd=cwd)
    if result.returncode:
        fail(error)
    return result


def compose_command() -> list[str]:
    # The operator wrapper fixes this to .env.prod. Honoring the same variable
    # here lets isolated tests render with an inert temporary env file.
    env_file = os.environ.get("HASANARA_ENV_FILE", ".env.prod")
    command = ["docker", "compose", "--project-name", "hasanara", "--env-file", env_file]
    for compose_file in COMPOSE_FILES:
        command.extend(("--file", compose_file))
    return command


def repository_head(root: Path) -> str:
    result = checked(("git", "rev-parse", "HEAD"), cwd=root, error="cannot determine source commit")
    head = result.stdout.strip()
    if not COMMIT_RE.fullmatch(head):
        fail("cannot determine source commit")
    return head


def ensure_clean_tree(root: Path, allow_dirty: bool) -> None:
    result = checked(
        ("git", "status", "--porcelain", "--untracked-files=all"), cwd=root, error="cannot inspect source tree"
    )
    if result.stdout and not allow_dirty:
        fail("source tree is dirty; use --allow-dirty only for a local rehearsal")


def active_services(root: Path) -> set[str]:
    result = checked([*compose_command(), "config", "--services"], cwd=root, error="Compose service validation failed")
    services = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    validate_active_service_set(services)
    return services


def validate_active_service_set(services: set[str]) -> None:
    if not BASE_SERVICES <= services or not services <= set(SERVICE_ROLES):
        fail("unsupported Compose profile or active service set")


def project_services(root: Path) -> set[str]:
    result = checked(
        (
            "docker",
            "ps",
            "--all",
            "--filter",
            "label=com.docker.compose.project=hasanara",
            "--format",
            '{{.Label "com.docker.compose.service"}}\x1f{{.Label "com.docker.compose.oneoff"}}',
        ),
        cwd=root,
        error="cannot inspect existing project containers",
    )
    rows = [row.split(COMPOSE_ROW_DELIMITER) for row in result.stdout.splitlines()]
    if any(len(row) != 2 or not SERVICE_LABEL_RE.fullmatch(row[0]) for row in rows):
        fail("existing project containers have invalid service labels")
    services = [row[0] for row in rows]
    if len(services) != len(set(services)) or any(row[1].strip().lower() not in COMPOSE_ONEOFF_LABELS for row in rows):
        fail("existing project containers are not safe for release")
    return set(services)


def validate_project_services(actual: set[str], desired: set[str], allow_disabled_profile_services: bool) -> None:
    allowed = desired | RETIRABLE_SERVICES if allow_disabled_profile_services else desired
    if not actual <= allowed:
        fail("existing project containers do not match desired active services")


def parse_compose_profiles(environment: str) -> None:
    """Accept only Compose's default profile selection."""
    values = [
        line.partition("=")[2] for line in environment.splitlines() if line.partition("=")[0] == "COMPOSE_PROFILES"
    ]
    if len(values) > 1:
        fail("unsupported Compose profile selection")
    value = values[0].strip() if values else ""
    profiles = [] if not value else [profile.strip() for profile in value.split(",")]
    if profiles:
        fail("unsupported Compose profile selection")


def validate_requested_profiles(root: Path) -> None:
    result = checked(
        [*compose_command(), "config", "--environment"], cwd=root, error="Compose profile validation failed"
    )
    parse_compose_profiles(result.stdout)


def validate_rendered_services(rendered: dict[str, Any], services: set[str], manifest: dict[str, Any]) -> None:
    configured = rendered.get("services")
    if not isinstance(configured, dict):
        fail("Compose rendered an invalid service configuration")
    db = configured.get("db")
    db_environment = db.get("environment", {}) if isinstance(db, dict) else {}
    password = db_environment.get("POSTGRES_PASSWORD") if isinstance(db_environment, dict) else None
    if not isinstance(password, str) or password in {"", "postgres"} or not URL_UNRESERVED_RE.fullmatch(password):
        fail("Compose database password contract is invalid")
    expected_database_url = f"postgresql+psycopg://postgres:{password}@db:5432/transcripts"
    for service in services:
        details = configured.get(service)
        expected = manifest["images"][manifest["services"][service]]
        if not isinstance(details, dict) or details.get("image") != expected or "build" in details:
            fail("Compose image does not match the release manifest")
        environment = details.get("environment", {})
        if service in DATABASE_CLIENTS:
            if (
                not isinstance(environment, dict)
                or environment.get("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION") != "false"
                or environment.get("ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION") != "false"
            ):
                fail("Compose migration safety contract is invalid")
            if environment.get("DATABASE_URL") != expected_database_url:
                fail("Compose database URL contract is invalid")
        if service == "backup" and environment.get("PGPASSWORD") != password:
            fail("Compose backup password contract is invalid")
        if service in APPLICATION_SERVICES and (
            environment.get("ENVIRONMENT") != "production" or environment.get("LOG_LEVEL") != "INFO"
        ):
            fail("Compose application environment contract is invalid")
        if service == "archive-enrichment-queue":
            if details.get("restart") not in ("no", False):
                fail("Compose archive enrichment queue restart contract is invalid")
            if details.get("command") != ENRICHMENT_QUEUE_COMMAND:
                fail("Compose archive enrichment queue command contract is invalid")
            if (
                environment.get("ARCHIVE_ENRICHMENT_ENABLED") not in FALSE_ENV_VALUES
                or environment.get("ARCHIVE_ENRICHMENT_PUBLISH") not in FALSE_ENV_VALUES
            ):
                fail("Compose archive enrichment queue safety flags are invalid")
        if service == "api" and (
            environment.get("REDIS_URL") != "redis://redis:6379/0"
            or environment.get("RATE_LIMIT_REQUESTS") != "100"
            or environment.get("RATE_LIMIT_WINDOW_SECONDS") != "60"
            or environment.get("OPENSEARCH_TLS_VERIFY") != "true"
        ):
            fail("Compose API security environment contract is invalid")


def diarization_env_path_from_operator_file() -> Path:
    """Read the diarization env-file path from the selected Compose env file."""
    operator_env_file = Path(os.environ.get("HASANARA_ENV_FILE", ".env.prod"))
    try:
        values: dict[str, str] = {}
        for line in operator_env_file.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if key == "HASANARA_DIARIZATION_ENV_FILE":
                if not separator or key in values:
                    fail("diarization environment file contract is invalid")
                values[key] = value
    except (OSError, UnicodeDecodeError):
        fail("diarization environment file contract is invalid")
    raw_path = values.get("HASANARA_DIARIZATION_ENV_FILE", "")
    if not raw_path:
        fail("diarization environment file contract is invalid")
    path = Path(raw_path)
    return path if path.is_absolute() else operator_env_file.parent / path


def validate_diarization_env_file() -> str:
    """Check the ignored credential file without exposing its path or contents."""
    path = diarization_env_path_from_operator_file()
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_mode & 0o077:
            fail("diarization environment file contract is invalid")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        fail("diarization environment file contract is invalid")
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in DIARIZATION_ENV_KEYS or key in values:
            fail("diarization environment file contract is invalid")
        values[key] = value
    if set(values) != DIARIZATION_ENV_KEYS or not values["HF_TOKEN"]:
        fail("diarization environment file contract is invalid")
    try:
        parsed = urlparse(values["DATABASE_URL"])
        valid_url = (
            parsed.scheme == "postgresql+psycopg"
            and parsed.username == "hasanara_diarization"
            and parsed.hostname == "db"
            and parsed.port == 5432
            and parsed.path == "/transcripts"
            and bool(parsed.password)
            and parsed.password not in {"postgres", "change-me", "change-me-in-production"}
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        fail("diarization database URL contract is invalid")
    return values["DATABASE_URL"]


def validate_diarization_contract(rendered: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Validate the opt-in worker even when its Compose profile is disabled."""
    diarization_url = validate_diarization_env_file()
    service = rendered.get("services", {}).get("diarization-worker")
    if not isinstance(service, dict):
        fail("Compose diarization contract is invalid")
    environment = service.get("environment")
    required_environment = {
        "HF_HOME": "/root/.cache/hf",
        "HF_HUB_CACHE": "/root/.cache/hf/hub",
        "TRANSFORMERS_CACHE": "/root/.cache/hf/transformers",
        "SEARCH_BACKEND": "postgres",
        "OPENSEARCH_URL": "",
        "REDIS_URL": "",
        "ROCM": "false",
        "ENABLE_DIARIZATION": "true",
        "DIARIZATION_INLINE": "false",
        "DIARIZATION_DEVICE": "cpu",
        "DIARIZATION_MODEL": DIARIZATION_SNAPSHOT,
        "DIARIZATION_FALLBACK_MODEL": "",
        "DIARIZATION_STRICT": "true",
        "DIARIZATION_REQUIRE_ALLOWLIST": "true",
        "DIARIZATION_EXIT_WHEN_IDLE": "true",
        "DIARIZATION_MAX_DURATION_SECONDS": "600",
        "DIARIZATION_MAX_JOBS_PER_PROCESS": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    if (
        not isinstance(environment, dict)
        or set(environment) != DIARIZATION_RENDERED_ENVIRONMENT
        or any(environment.get(key) != value for key, value in required_environment.items())
        or not isinstance(environment.get("HF_TOKEN"), str)
        or not environment["HF_TOKEN"]
        or environment.get("ENVIRONMENT") != "production"
        or environment.get("LOG_LEVEL") != "INFO"
        or environment.get("ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION") != "false"
        or environment.get("ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION") != "false"
    ):
        fail("Compose diarization environment contract is invalid")
    if environment.get("DATABASE_URL") != diarization_url:
        fail("Compose diarization database URL contract is invalid")
    if service.get("image") != manifest["images"]["ml-cuda"] or "build" in service:
        fail("Compose diarization image does not match the release manifest")
    if (
        service.get("gpus") not in (None, [])
        or service.get("devices") not in (None, [])
        or service.get("group_add") not in (None, [])
        or service.get("restart") not in ("no", False)
    ):
        fail("Compose diarization runtime contract is invalid")
    if (
        service.get("cpus") not in ("2.0", 2, 2.0)
        or service.get("mem_limit") not in FOUR_GIB_VALUES
        or service.get("memswap_limit") not in FOUR_GIB_VALUES
        or service.get("pids_limit") != 256
    ):
        fail("Compose diarization resource contract is invalid")
    volumes = service.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != 2:
        fail("Compose diarization mount contract is invalid")
    mounts = {
        (item.get("target"), item.get("source"), item.get("read_only")) for item in volumes if isinstance(item, dict)
    }
    expected_sources = {"/data": ROOT / "data", "/root/.cache/hf": ROOT / "cache" / "hf"}
    actual_sources = {target: source for target, source, read_only in mounts if read_only is True}
    if (
        len(mounts) != 2
        or set(actual_sources) != set(expected_sources)
        or any(not isinstance(actual_sources[target], str) for target in expected_sources)
    ):
        fail("Compose diarization mount contract is invalid")
    for target, expected in expected_sources.items():
        source_value = actual_sources[target]
        if not isinstance(source_value, str):
            fail("Compose diarization mount contract is invalid")
        source = Path(source_value)
        source = source if source.is_absolute() else ROOT / source
        try:
            ancestor = ROOT
            for part in expected.relative_to(ROOT).parts:
                ancestor /= part
                if ancestor.is_symlink():
                    fail("Compose diarization mount contract is invalid")
            if source.resolve() != expected.resolve() or source.is_symlink():
                fail("Compose diarization mount contract is invalid")
        except OSError:
            fail("Compose diarization mount contract is invalid")


def verify_networks(root: Path) -> None:
    for network in ("management", "dev"):
        checked(
            ("docker", "network", "inspect", network),
            cwd=root,
            error=f"required external network is missing: {network}",
        )


def verify_mount_parents(root: Path) -> None:
    # Docker Compose otherwise creates these host paths silently and can deploy to
    # empty storage after an operator typo.
    for relative in ("docker-volumes/dbdata", "docker-volumes/redis-data", "backups", "data", "cache", "cache/hf"):
        if not (root / relative).is_dir():
            fail(f"required mount parent is missing: {relative}")


def validate(root: Path, manifest_path: Path, allow_dirty: bool, allow_disabled_profile_services: bool = False) -> None:
    manifest = load_manifest(manifest_path)
    ensure_clean_tree(root, allow_dirty)
    if repository_head(root) != manifest["source_commit"]:
        fail("release manifest source commit does not match HEAD")
    checked([*compose_command(), "config", "--quiet"], cwd=root, error="Compose configuration validation failed")
    validate_requested_profiles(root)
    services = active_services(root)
    rendered_result = checked(
        [*compose_command(), "config", "--format", "json"], cwd=root, error="Compose rendering failed"
    )
    try:
        rendered = json.loads(rendered_result.stdout)
    except json.JSONDecodeError:
        fail("Compose rendered invalid JSON")
    validate_rendered_services(rendered, services, manifest)
    diarization_result = checked(
        [*compose_command(), "--profile", "diarization", "config", "--format", "json"],
        cwd=root,
        error="Compose diarization rendering failed",
    )
    try:
        validate_diarization_contract(json.loads(diarization_result.stdout), manifest)
    except json.JSONDecodeError:
        fail("Compose diarization rendered invalid JSON")
    validate_project_services(project_services(root), services, allow_disabled_profile_services)
    verify_networks(root)
    verify_mount_parents(root)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = SafeArgumentParser(description="Validate a release without printing Compose configuration.")
    parser.add_argument("--manifest", type=Path, default=ROOT / "release-images.json")
    parser.add_argument("--allow-dirty", action="store_true", help="allow a dirty tree for a local rehearsal only")
    parser.add_argument("--allow-disabled-profile-services", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        validate(ROOT, args.manifest, args.allow_dirty, args.allow_disabled_profile_services)
    except PreflightError as error:
        print(f"release preflight failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        # Do not expose values from subprocesses, environment interpolation, or
        # Python tracebacks during a release check.
        print("release preflight failed: internal validation error", file=sys.stderr)
        return 1
    print("release preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
