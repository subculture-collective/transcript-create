"""Focused contracts for the fail-closed production release path."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "release_preflight.py"
SPEC = importlib.util.spec_from_file_location("release_preflight", SCRIPT_PATH)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)

REQUIRED_DOCKER_EXCLUDES = {
    ".env",
    ".env.*",
    "*.local",
    ".pypirc",
    ".streamlit/secrets.toml",
    "cookies*.txt",
    "*.cookies",
    ".blacktower/",
    "release-images.json",
    ".release-commit",
    "deploy-backups/",
}
IMAGE_VARIABLES = {
    "HASANARA_API_IMAGE",
    "HASANARA_INGEST_IMAGE",
    "HASANARA_ML_IMAGE",
    "HASANARA_FRONTEND_IMAGE",
    "HASANARA_POSTGRES_IMAGE",
    "HASANARA_REDIS_IMAGE",
}
DATABASE_URL = "postgresql+psycopg://postgres:inert@db:5432/transcripts"


def test_api_packages_and_smokes_enrichment_maintenance_entrypoint():
    dockerfile = (ROOT / "Dockerfile.api").read_text()
    assert "COPY scripts/approve_archive_enrichment.py ./scripts/approve_archive_enrichment.py" in dockerfile
    assert "RUN python scripts/approve_archive_enrichment.py --help > /dev/null" in dockerfile


def digest(name: str) -> str:
    return f"registry.invalid/hasanara/{name}@sha256:{'a' * 64}"


def manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_commit": "b" * 40,
        "images": {role: digest(role) for role in preflight.IMAGE_ROLES},
        "services": preflight.SERVICE_ROLES,
    }


def rendered_service(service: str, image: str) -> dict[str, Any]:
    environment: dict[str, str] = {}
    if service == "db":
        environment["POSTGRES_PASSWORD"] = "inert"
    if service in preflight.DATABASE_CLIENTS:
        environment.update(
            {
                "DATABASE_URL": DATABASE_URL,
                "ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION": "false",
                "ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION": "false",
            }
        )
    if service == "backup":
        environment["PGPASSWORD"] = "inert"
    if service in preflight.APPLICATION_SERVICES:
        environment.update({"ENVIRONMENT": "production", "LOG_LEVEL": "INFO"})
    if service == "api":
        environment.update(
            {
                "REDIS_URL": "redis://redis:6379/0",
                "RATE_LIMIT_REQUESTS": "100",
                "RATE_LIMIT_WINDOW_SECONDS": "60",
                "OPENSEARCH_TLS_VERIFY": "true",
            }
        )
    rendered: dict[str, Any] = {"image": image, "environment": environment}
    if service == "archive-enrichment-queue":
        rendered["restart"] = "no"
        rendered["command"] = preflight.ENRICHMENT_QUEUE_COMMAND
        environment.update(
            {
                "ARCHIVE_ENRICHMENT_ENABLED": "false",
                "ARCHIVE_ENRICHMENT_PUBLISH": "false",
            }
        )
    if service == "diarization-worker":
        environment.update(
            {
                "HF_TOKEN": "inert",
                "DATABASE_URL": "postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts",
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
                "DIARIZATION_MODEL": preflight.DIARIZATION_SNAPSHOT,
                "DIARIZATION_FALLBACK_MODEL": "",
                "DIARIZATION_STRICT": "true",
                "DIARIZATION_REQUIRE_ALLOWLIST": "true",
                "DIARIZATION_EXIT_WHEN_IDLE": "true",
                "DIARIZATION_MAX_DURATION_SECONDS": "600",
                "DIARIZATION_MAX_JOBS_PER_PROCESS": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "INFO",
                "ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION": "false",
                "ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION": "false",
            }
        )
        rendered.update(
            {
                "restart": "no",
                "cpus": "2.0",
                "mem_limit": "4g",
                "memswap_limit": "4g",
                "pids_limit": 256,
                "volumes": [
                    {"source": "./data", "target": "/data", "read_only": True},
                    {"source": "./cache/hf", "target": "/root/.cache/hf", "read_only": True},
                ],
            }
        )
    return rendered


def test_dockerignore_excludes_secret_and_local_state() -> None:
    patterns = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert REQUIRED_DOCKER_EXCLUDES <= patterns


def test_release_manifest_is_ignored_by_git_and_docker() -> None:
    assert {"release-images.json", ".release-commit", "deploy-backups/", ".release-venv/"} <= set(
        (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    assert {"release-images.json", ".release-venv/"} <= set(
        (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )


def test_patched_runtime_dependency_pins_match_all_release_inputs() -> None:
    required = {
        "Authlib==1.7.2",
        "python-dotenv==1.2.2",
        "requests==2.34.2",
        "yt-dlp==2026.7.4",
    }
    for dependency_file in ("requirements.txt", "requirements-api.txt", "constraints.txt"):
        pins = set((ROOT / dependency_file).read_text(encoding="utf-8").splitlines())
        assert required <= pins, f"{dependency_file} is missing a patched runtime pin"


def test_ingest_image_applies_available_base_security_updates() -> None:
    dockerfile = (ROOT / "Dockerfile.ingest.cuda").read_text(encoding="utf-8")
    assert "apt-get-retry update" in dockerfile
    assert "apt-get-retry upgrade -y --no-install-recommends" in dockerfile


def test_ingest_image_retries_transient_cuda_repository_fetches() -> None:
    dockerfile = (ROOT / "Dockerfile.ingest.cuda").read_text(encoding="utf-8")
    assert 'Acquire::Retries "2";' in dockerfile
    assert 'Acquire::https::Timeout "60";' in dockerfile
    assert 'while ! apt-get "$@"; do' in dockerfile
    assert '[ "$attempt" -ge 12 ]' in dockerfile
    assert dockerfile.count("apt-get-retry install") >= 8


def test_ingest_image_splits_cuda_upgrades_for_registry_uploads() -> None:
    dockerfile = (ROOT / "Dockerfile.ingest.cuda").read_text(encoding="utf-8")
    assert dockerfile.count("--only-upgrade --no-install-recommends") >= 7
    for package in (
        "cuda-compat-12-8",
        "libcufft-12-8",
        "libcusolver-12-8",
        "libcusparse-12-8",
        "libnpp-12-8",
    ):
        assert package in dockerfile


def test_ingest_image_splits_api_and_gpu_dependencies_for_registry_uploads() -> None:
    dockerfile = (ROOT / "Dockerfile.ingest.cuda").read_text(encoding="utf-8")
    assert "pip3 install -c constraints.txt -r requirements-api.txt" in dockerfile
    assert "pip3 install -c constraints.txt ctranslate2==4.6.0" in dockerfile
    assert "pip3 install -c constraints.txt faster-whisper==1.2.0" in dockerfile
    assert dockerfile.count("RUN pip3 install") >= 3


def test_release_overlay_is_last_and_requires_immutable_images() -> None:
    helper = (ROOT / "scripts" / "compose_prod.sh").read_text(encoding="utf-8")
    assert helper.rfind("docker-compose.release.yml") > helper.rfind("docker-compose.pitr.yml")
    overlay = (ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    for variable in IMAGE_VARIABLES:
        assert f"${{{variable}:?{variable} is required}}" in overlay
    assert overlay.count("build: !reset null") == 12
    assert "POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD is required}" in overlay
    assert (
        overlay.count(
            "DATABASE_URL: postgresql+psycopg://postgres:${DB_PASSWORD:?DB_PASSWORD is required}@db:5432/transcripts"
        )
        == 8
    )
    assert "PGPASSWORD: ${DB_PASSWORD:?DB_PASSWORD is required}" in overlay
    assert overlay.count("ENVIRONMENT: production") == len(preflight.APPLICATION_SERVICES) + 1
    assert overlay.count("LOG_LEVEL: INFO") == len(preflight.APPLICATION_SERVICES) + 1
    assert 'ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION: "false"' in overlay
    assert overlay.count('ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION: "false"') == 9


def test_overlay_forces_env_file_and_diarization_is_opt_in() -> None:
    overlay = (ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    assert overlay.count('env_file: !override ["${HASANARA_ENV_FILE:?HASANARA_ENV_FILE is required}"]') == 8
    assert (
        'env_file: !override ["${HASANARA_DIARIZATION_ENV_FILE:?HASANARA_DIARIZATION_ENV_FILE is required}"]' in overlay
    )
    assert "gpus: !reset null" in overlay
    host = (ROOT / "docker-compose.hasanara.yml").read_text(encoding="utf-8")
    assert "profiles: [diarization]" in host
    assert "REDIS_URL: redis://redis:6379/0" in host
    assert "RATE_LIMIT_REQUESTS: '100'" in host
    assert "RATE_LIMIT_WINDOW_SECONDS: '60'" in host
    assert "OPENSEARCH_TLS_VERIFY: 'true'" in host
    enrichment = overlay.split("archive-enrichment-queue:", 1)[1].split("diarization-worker:", 1)[0]
    assert "run_archive_enrichment_queue.py', '${ARCHIVE_ENRICHMENT_QUEUE_MODE:---once}'" in enrichment
    assert "restart: '${ARCHIVE_ENRICHMENT_QUEUE_RESTART_POLICY:-no}'" in enrichment


def test_example_documents_required_url_safe_production_database_password() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DB_PASSWORD=" in example
    assert "openssl rand -hex 32" in example
    assert "release overlay's internal DATABASE_URL" in example
    assert "overriding the development example URL" in example


def test_manifest_requires_exact_schema_and_digests(tmp_path: Path) -> None:
    path = tmp_path / "release-images.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    assert preflight.load_manifest(path)["services"] == preflight.SERVICE_ROLES
    broken = manifest()
    broken["images"] = {**broken["images"], "api": "hasanara-api:latest"}
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="invalid image reference"):
        preflight.load_manifest(path)


def test_manifest_head_mismatch_fails_without_value_leak(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "release-images.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    monkeypatch.setattr(preflight, "ensure_clean_tree", lambda *_: None)
    monkeypatch.setattr(preflight, "repository_head", lambda _: "c" * 40)
    with pytest.raises(preflight.PreflightError, match="does not match HEAD"):
        preflight.validate(tmp_path, path, False)


def test_service_mapping_and_profile_filtering() -> None:
    data = manifest()
    rendered = {
        "services": {
            service: rendered_service(service, data["images"][role])
            for service, role in preflight.SERVICE_ROLES.items()
        }
    }
    preflight.validate_rendered_services(rendered, set(preflight.SERVICE_ROLES), data)
    rendered["services"]["api"]["image"] = digest("wrong")
    with pytest.raises(preflight.PreflightError, match="does not match"):
        preflight.validate_rendered_services(rendered, {"api"}, data)
    rendered["services"]["api"] = {
        "image": data["images"]["api"],
        "build": ".",
        "environment": {"ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION": "false"},
    }
    with pytest.raises(preflight.PreflightError, match="does not match"):
        preflight.validate_rendered_services(rendered, {"api"}, data)
    assert preflight.BASE_SERVICES == set(preflight.SERVICE_ROLES) - {"diarization-worker"}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REDIS_URL", ""),
        ("RATE_LIMIT_REQUESTS", "101"),
        ("RATE_LIMIT_WINDOW_SECONDS", "30"),
        ("OPENSEARCH_TLS_VERIFY", "false"),
    ],
)
def test_api_security_environment_is_fail_closed(name: str, value: str) -> None:
    data = manifest()
    api = rendered_service("api", data["images"]["api"])
    api["environment"][name] = value
    db = rendered_service("db", data["images"]["postgres-walg"])
    with pytest.raises(preflight.PreflightError, match="API security environment"):
        preflight.validate_rendered_services({"services": {"api": api, "db": db}}, {"api"}, data)


@pytest.mark.parametrize(
    "service, key, value",
    [
        ("db", "POSTGRES_PASSWORD", "postgres"),
        ("db", "POSTGRES_PASSWORD", "contains:reserved"),
        ("api", "DATABASE_URL", "postgresql+psycopg://postgres:wrong@db:5432/transcripts"),
        ("backup", "PGPASSWORD", "wrong"),
        ("worker", "ENVIRONMENT", "development"),
        ("migrations", "LOG_LEVEL", "DEBUG"),
    ],
)
def test_rendered_production_contract_fails_closed(service: str, key: str, value: str) -> None:
    data = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, data["images"][role]) for name, role in preflight.SERVICE_ROLES.items()
        }
    }
    rendered["services"][service]["environment"][key] = value
    with pytest.raises(preflight.PreflightError):
        preflight.validate_rendered_services(rendered, set(preflight.SERVICE_ROLES), data)


def test_archive_enrichment_queue_restart_contract_is_fail_closed() -> None:
    data = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, data["images"][role]) for name, role in preflight.SERVICE_ROLES.items()
        }
    }
    rendered["services"]["archive-enrichment-queue"]["restart"] = "unless-stopped"
    with pytest.raises(preflight.PreflightError, match="archive enrichment queue restart"):
        preflight.validate_rendered_services(rendered, set(preflight.SERVICE_ROLES), data)


def test_archive_enrichment_queue_command_contract_is_fail_closed() -> None:
    data = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, data["images"][role]) for name, role in preflight.SERVICE_ROLES.items()
        }
    }
    rendered["services"]["archive-enrichment-queue"]["command"] = [
        "python3",
        "/app/scripts/run_archive_enrichment_queue.py",
    ]
    with pytest.raises(preflight.PreflightError, match="archive enrichment queue command"):
        preflight.validate_rendered_services(rendered, set(preflight.SERVICE_ROLES), data)


@pytest.mark.parametrize("key", ["ARCHIVE_ENRICHMENT_ENABLED", "ARCHIVE_ENRICHMENT_PUBLISH"])
def test_archive_enrichment_queue_safety_flags_are_fail_closed(key: str) -> None:
    data = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, data["images"][role]) for name, role in preflight.SERVICE_ROLES.items()
        }
    }
    rendered["services"]["archive-enrichment-queue"]["environment"][key] = "true"
    with pytest.raises(preflight.PreflightError, match="archive enrichment queue"):
        preflight.validate_rendered_services(rendered, set(preflight.SERVICE_ROLES), data)


@pytest.mark.parametrize("unsafe", [None, "publish", "model", "budget", "window", "restart", "command"])
def test_explicit_continuous_enrichment_contract(unsafe):
    release = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, release["images"][role]) for name, role in release["services"].items()
        }
    }
    queue = rendered["services"]["archive-enrichment-queue"]
    queue.update(command=[*preflight.ENRICHMENT_QUEUE_COMMAND[:2], "--continuous"], restart="unless-stopped")
    queue["environment"].update(
        ARCHIVE_ENRICHMENT_ENABLED="true",
        ARCHIVE_ENRICHMENT_MODEL="deepseek/deepseek-v4-pro",
        ARCHIVE_ENRICHMENT_MAX_WINDOW_MINUTES="90",
        ARCHIVE_ENRICHMENT_MAX_COST_USD_PER_VIDEO="1.00",
    )
    if unsafe in {"publish", "model", "budget", "window"}:
        key = {
            "publish": "PUBLISH",
            "model": "MODEL",
            "budget": "MAX_COST_USD_PER_VIDEO",
            "window": "MAX_WINDOW_MINUTES",
        }[unsafe]
        queue["environment"][f"ARCHIVE_ENRICHMENT_{key}"] = "unsafe"
    elif unsafe == "restart":
        queue["restart"] = "no"
    elif unsafe == "command":
        queue["command"] = preflight.ENRICHMENT_QUEUE_COMMAND
    if unsafe:
        with pytest.raises(preflight.PreflightError, match="archive enrichment queue"):
            preflight.validate_rendered_services(rendered, set(release["services"]), release)
    else:
        preflight.validate_rendered_services(rendered, set(release["services"]), release)


def test_diarization_profile_contract_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight,
        "validate_diarization_env_file",
        lambda: "postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts",
    )
    data = manifest()
    rendered = {
        "services": {
            name: rendered_service(name, data["images"][role]) for name, role in preflight.SERVICE_ROLES.items()
        }
    }
    preflight.validate_diarization_contract(rendered, data)
    rendered["services"]["diarization-worker"]["environment"]["DIARIZATION_DEVICE"] = "cuda"
    with pytest.raises(preflight.PreflightError, match="diarization environment"):
        preflight.validate_diarization_contract(rendered, data)
    rendered["services"]["diarization-worker"]["environment"]["DIARIZATION_DEVICE"] = "cpu"
    rendered["services"]["diarization-worker"]["gpus"] = "all"
    with pytest.raises(preflight.PreflightError, match="diarization runtime"):
        preflight.validate_diarization_contract(rendered, data)
    rendered["services"]["diarization-worker"]["gpus"] = None
    rendered["services"]["diarization-worker"]["devices"] = ["/dev/nvidia0"]
    with pytest.raises(preflight.PreflightError, match="diarization runtime"):
        preflight.validate_diarization_contract(rendered, data)
    rendered["services"]["diarization-worker"]["devices"] = []
    rendered["services"]["diarization-worker"]["group_add"] = ["video"]
    with pytest.raises(preflight.PreflightError, match="diarization runtime"):
        preflight.validate_diarization_contract(rendered, data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("HF_HOME", "/tmp/hf"),
        ("HF_HUB_CACHE", "/tmp/hub"),
        ("TRANSFORMERS_CACHE", "/tmp/transformers"),
        ("SEARCH_BACKEND", "opensearch"),
        ("OPENSEARCH_URL", "http://opensearch:9200"),
        ("REDIS_URL", "redis://redis:6379/0"),
        ("ROCM", "true"),
        ("HF_TOKEN", ""),
    ],
)
def test_diarization_contract_rejects_noncanonical_rendered_runtime_values(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setattr(
        preflight,
        "validate_diarization_env_file",
        lambda: "postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts",
    )
    data = manifest()
    rendered = {"services": {"diarization-worker": rendered_service("diarization-worker", data["images"]["ml-cuda"])}}
    rendered["services"]["diarization-worker"]["environment"][key] = value
    with pytest.raises(preflight.PreflightError, match="diarization environment"):
        preflight.validate_diarization_contract(rendered, data)


def test_diarization_contract_rejects_wrong_image_extra_environment_and_noncanonical_mounts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        preflight,
        "validate_diarization_env_file",
        lambda: "postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts",
    )
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "cache" / "hf").mkdir(parents=True)
    data = manifest()
    service = rendered_service("diarization-worker", data["images"]["ml-cuda"])
    service["volumes"] = [
        {"source": str(tmp_path / "data"), "target": "/data", "read_only": True},
        {"source": str(tmp_path / "cache" / "hf"), "target": "/root/.cache/hf", "read_only": True},
    ]
    rendered = {"services": {"diarization-worker": service}}
    preflight.validate_diarization_contract(rendered, data)
    service["image"] = digest("wrong")
    with pytest.raises(preflight.PreflightError, match="image"):
        preflight.validate_diarization_contract(rendered, data)
    service["image"] = data["images"]["ml-cuda"]
    service["environment"]["FUTURE_EXTRA"] = "no"
    with pytest.raises(preflight.PreflightError, match="environment"):
        preflight.validate_diarization_contract(rendered, data)
    del service["environment"]["FUTURE_EXTRA"]
    link = tmp_path / "linked-data"
    link.symlink_to(tmp_path / "data", target_is_directory=True)
    service["volumes"][0]["source"] = str(link)
    with pytest.raises(preflight.PreflightError, match="mount"):
        preflight.validate_diarization_contract(rendered, data)


@pytest.mark.parametrize("symlinked_path", ("data", "cache", "cache/hf"))
def test_diarization_contract_rejects_symlinked_mount_ancestors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, symlinked_path: str
) -> None:
    monkeypatch.setattr(
        preflight,
        "validate_diarization_env_file",
        lambda: "postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts",
    )
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    external = tmp_path / "external"
    (external / "data").mkdir(parents=True)
    (external / "cache" / "hf").mkdir(parents=True)
    if symlinked_path == "data":
        (tmp_path / "data").symlink_to(external / "data", target_is_directory=True)
        (tmp_path / "cache" / "hf").mkdir(parents=True)
    elif symlinked_path == "cache":
        (tmp_path / "data").mkdir()
        (tmp_path / "cache").symlink_to(external / "cache", target_is_directory=True)
    else:
        (tmp_path / "data").mkdir()
        (tmp_path / "cache").mkdir()
        (tmp_path / "cache" / "hf").symlink_to(external / "cache" / "hf", target_is_directory=True)
    data = manifest()
    service = rendered_service("diarization-worker", data["images"]["ml-cuda"])
    service["volumes"] = [
        {"source": str(tmp_path / "data"), "target": "/data", "read_only": True},
        {"source": str(tmp_path / "cache" / "hf"), "target": "/root/.cache/hf", "read_only": True},
    ]
    with pytest.raises(preflight.PreflightError, match="mount"):
        preflight.validate_diarization_contract({"services": {"diarization-worker": service}}, data)


def test_diarization_env_file_rejects_extra_keys_symlinks_and_unsafe_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "diarization.env"
    env_file.write_text(
        "HF_TOKEN=inert\nDATABASE_URL=postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    operator_env = tmp_path / "operator.env"
    operator_env.write_text(f"HASANARA_DIARIZATION_ENV_FILE={env_file}\n", encoding="utf-8")
    monkeypatch.setenv("HASANARA_ENV_FILE", str(operator_env))
    preflight.validate_diarization_env_file()
    env_file.write_text(env_file.read_text(encoding="utf-8") + "EXTRA=value\n", encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="environment file"):
        preflight.validate_diarization_env_file()
    env_file.write_text(
        "HF_TOKEN=inert\nDATABASE_URL=postgresql+psycopg://postgres:strong-password@db:5432/transcripts\n"
    )
    with pytest.raises(preflight.PreflightError, match="database URL"):
        preflight.validate_diarization_env_file()
    env_file.chmod(0o644)
    with pytest.raises(preflight.PreflightError, match="environment file"):
        preflight.validate_diarization_env_file()
    link = tmp_path / "diarization-link.env"
    link.symlink_to(env_file)
    operator_env.write_text(f"HASANARA_DIARIZATION_ENV_FILE={link}\n", encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="environment file"):
        preflight.validate_diarization_env_file()


def test_preflight_uses_dedicated_environment_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / "inert-release.env"
    monkeypatch.setenv("HASANARA_ENV_FILE", str(env_file))

    assert preflight.compose_command()[5] == str(env_file)


def test_diarization_env_path_is_read_from_selected_operator_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    operator_env = tmp_path / "operator.env"
    operator_env.write_text("HASANARA_DIARIZATION_ENV_FILE=credentials/diarization.env\n", encoding="utf-8")
    monkeypatch.setenv("HASANARA_ENV_FILE", str(operator_env))
    monkeypatch.delenv("HASANARA_DIARIZATION_ENV_FILE", raising=False)

    assert preflight.diarization_env_path_from_operator_file() == tmp_path / "credentials" / "diarization.env"


def test_full_profile_service_set_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight,
        "checked",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, "\n".join([*preflight.BASE_SERVICES, "opensearch"]), ""
        ),
    )
    with pytest.raises(preflight.PreflightError, match="unsupported Compose profile"):
        preflight.active_services(ROOT)


def test_existing_project_services_reject_profile_transitions_except_retirement_allowance() -> None:
    desired = preflight.BASE_SERVICES
    for actual in (
        desired | {"opensearch", "dashboards", "prometheus", "grafana"},
        desired | {"diarization-worker"},
        desired | {"opensearch", "dashboards", "prometheus", "grafana", "diarization-worker"},
    ):
        with pytest.raises(preflight.PreflightError, match="existing project containers"):
            preflight.validate_project_services(actual, desired, False)
        preflight.validate_project_services(actual, desired, True)
    with pytest.raises(preflight.PreflightError, match="existing project containers"):
        preflight.validate_project_services(desired | {"unknown-stale-service"}, desired, True)


def test_project_service_labels_are_captured_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    command: list[str] = []
    monkeypatch.setattr(
        preflight,
        "checked",
        lambda args, **_kwargs: (
            command.extend(args),
            subprocess.CompletedProcess([], 0, "api\x1fFalse\nbackup\x1f\n", ""),
        )[1],
    )
    assert preflight.project_services(ROOT) == {"api", "backup"}
    assert command == [
        "docker",
        "ps",
        "--all",
        "--filter",
        "label=com.docker.compose.project=hasanara",
        "--format",
        '{{.Label "com.docker.compose.service"}}\x1f{{.Label "com.docker.compose.oneoff"}}',
    ]
    monkeypatch.setattr(
        preflight, "checked", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "bad label\x1fFalse\n", "")
    )
    with pytest.raises(preflight.PreflightError, match="invalid service labels"):
        preflight.project_services(ROOT)


@pytest.mark.parametrize("output", ["api\x1fFalse\napi\x1fFalse\n", "api\x1fTrue\n"])
def test_project_services_reject_duplicate_or_oneoff_containers(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    monkeypatch.setattr(preflight, "checked", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, output, ""))
    with pytest.raises(preflight.PreflightError, match="not safe for release"):
        preflight.project_services(ROOT)


def test_dirty_tree_requires_explicit_local_rehearsal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, " M source.py\n", "")
    )
    with pytest.raises(preflight.PreflightError, match="--allow-dirty"):
        preflight.ensure_clean_tree(ROOT, False)
    preflight.ensure_clean_tree(ROOT, True)


def test_ignored_manifest_keeps_tree_clean_but_untracked_file_fails(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("release-images.json\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (tmp_path / "release-images.json").write_text("{}", encoding="utf-8")
    preflight.ensure_clean_tree(tmp_path, False)
    (tmp_path / "untracked.txt").write_text("not ignored", encoding="utf-8")
    with pytest.raises(preflight.PreflightError, match="source tree is dirty"):
        preflight.ensure_clean_tree(tmp_path, False)


def test_mount_validation_requires_active_bind_sources(tmp_path: Path) -> None:
    for relative in ("docker-volumes", "backups", "data", "cache"):
        (tmp_path / relative).mkdir(parents=True)
    with pytest.raises(preflight.PreflightError, match=r"docker-volumes/dbdata"):
        preflight.verify_mount_parents(tmp_path)
    for relative in ("docker-volumes/dbdata", "docker-volumes/redis-data"):
        (tmp_path / relative).mkdir()
    with pytest.raises(preflight.PreflightError, match=r"cache/hf"):
        preflight.verify_mount_parents(tmp_path)
    (tmp_path / "cache" / "hf").mkdir()
    preflight.verify_mount_parents(tmp_path)


def test_deploy_runs_strict_preflight_in_a_clean_operator_tree(tmp_path: Path) -> None:
    """Exercise the operator path without Docker, rendered secrets, or dirty-tree bypasses."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for source in ("release_preflight.py", "compose_prod.sh"):
        shutil.copy2(ROOT / "scripts" / source, scripts / source)
    for compose_file in preflight.COMPOSE_FILES:
        (tmp_path / compose_file).write_text("services: {}\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(
        ".env.prod\n.env.diarization\nrelease-images.json\ndocker-volumes/\nbackups/\ndata/\ncache/\nfake-bin/\ndocker-calls\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "release source"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    release_manifest = manifest()
    release_manifest["source_commit"] = head
    (tmp_path / "release-images.json").write_text(json.dumps(release_manifest), encoding="utf-8")
    diarization_env = tmp_path / ".env.diarization"
    diarization_env.write_text(
        "HF_TOKEN=inert\nDATABASE_URL=postgresql+psycopg://hasanara_diarization:strong-password@db:5432/transcripts\n",
        encoding="utf-8",
    )
    diarization_env.chmod(0o600)
    (tmp_path / ".env.prod").write_text(
        f"INERT_OPERATOR_VALUE=1\nHASANARA_DIARIZATION_ENV_FILE={diarization_env}\n", encoding="utf-8"
    )
    for relative in ("docker-volumes/dbdata", "docker-volumes/redis-data", "backups", "data", "cache/hf"):
        (tmp_path / relative).mkdir(parents=True)

    rendered = {
        "services": {
            service: rendered_service(service, release_manifest["images"][role])
            for service, role in preflight.SERVICE_ROLES.items()
        }
    }
    docker_dir = tmp_path / "fake-bin"
    docker_dir.mkdir()
    docker_log = tmp_path / "docker-calls"
    docker = docker_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(docker_log))}\n"
        'case "$*" in\n'
        "  *'config --quiet') exit 0 ;;\n"
        "  *'config --environment') exit 0 ;;\n"
        f"  *'config --services') printf '%s\\n' {shlex.quote(chr(10).join(sorted(preflight.BASE_SERVICES)))}; exit 0 ;;\n"
        f"  *'config --format json') printf '%s\\n' {shlex.quote(json.dumps(rendered))}; exit 0 ;;\n"
        "  *'ps --all --filter label=com.docker.compose.project=hasanara --format'*) exit 0 ;;\n"
        "  'network inspect '*|'compose '*' up -d --no-build --pull always') exit 0 ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    environment = {
        "PATH": f"{docker_dir}:{os.environ['PATH']}",
        "HOME": os.environ.get("HOME", ""),
        "USER": "test",
    }
    result = subprocess.run(
        ["bash", "scripts/compose_prod.sh", "deploy"],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr
    assert "release preflight passed" in result.stdout
    calls = docker_log.read_text(encoding="utf-8").splitlines()
    expected_deploy = " ".join(
        [
            "compose",
            "--project-name",
            "hasanara",
            "--env-file",
            ".env.prod",
            *[item for compose_file in preflight.COMPOSE_FILES for item in ("--file", compose_file)],
            "up",
            "-d",
            "--no-build",
            "--pull",
            "always",
        ]
    )
    assert calls[-1] == expected_deploy
    assert [call for call in calls if " up -d --no-build --pull always" in call] == [expected_deploy]
    assert next(index for index, call in enumerate(calls) if "ps --all --filter" in call) < calls.index(expected_deploy)


def test_retire_disabled_profiles_uses_limited_preflight_and_authoritative_compose_command(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    python_log = tmp_path / "python-calls"
    docker_log = tmp_path / "docker-calls"
    (fake_bin / "python3").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {shlex.quote(str(python_log))}\n",
        encoding="utf-8",
    )
    (fake_bin / "docker").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {shlex.quote(str(docker_log))}\n",
        encoding="utf-8",
    )
    for executable in (fake_bin / "python3", fake_bin / "docker"):
        executable.chmod(0o755)

    environment = {"PATH": f"{fake_bin}:{os.environ['PATH']}", "HOME": os.environ.get("HOME", ""), "USER": "test"}
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "compose_prod.sh"), "maintenance", "retire-disabled-profiles", "--approved"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert python_log.read_text(encoding="utf-8").splitlines() == [
        "scripts/release_preflight.py --allow-disabled-profile-services"
    ]
    expected = " ".join(
        [
            "compose",
            "--project-name",
            "hasanara",
            "--env-file",
            ".env.prod",
            *[item for compose_file in preflight.COMPOSE_FILES for item in ("--file", compose_file)],
            "--profile",
            "full",
            "--profile",
            "diarization",
            "rm",
            "--stop",
            "--force",
            "opensearch",
            "dashboards",
            "prometheus",
            "grafana",
            "diarization-worker",
        ]
    )
    assert docker_log.read_text(encoding="utf-8").splitlines() == [expected]


@pytest.mark.parametrize("environment", ["", "COMPOSE_PROFILES=", "OTHER=inert\n"])
def test_requested_profiles_allow_only_default(environment: str) -> None:
    preflight.parse_compose_profiles(environment)


@pytest.mark.parametrize(
    "environment",
    [
        "COMPOSE_PROFILES=full",
        "COMPOSE_PROFILES=unknown",
        "COMPOSE_PROFILES=diarization,full",
        "COMPOSE_PROFILES=full,diarization",
        "COMPOSE_PROFILES=diarization,unknown",
        "COMPOSE_PROFILES=diarization",
    ],
)
def test_requested_profiles_reject_nondefault_selection(environment: str) -> None:
    with pytest.raises(preflight.PreflightError, match="unsupported Compose profile selection"):
        preflight.parse_compose_profiles(environment)


def test_profile_command_failure_does_not_leak_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "SENTINEL_PROFILE_SECRET_MUST_NOT_LEAK"
    monkeypatch.setattr(
        preflight, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, sentinel, sentinel)
    )
    with pytest.raises(preflight.PreflightError, match="Compose profile validation failed"):
        preflight.validate_requested_profiles(ROOT)
    monkeypatch.setattr(
        preflight,
        "validate",
        lambda *_: (_ for _ in ()).throw(preflight.PreflightError("Compose profile validation failed")),
    )
    assert preflight.main([]) == 1
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err


def test_preflight_redacts_subprocess_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "SENTINEL_SECRET_MUST_NOT_LEAK"
    monkeypatch.setattr(
        preflight,
        "validate",
        lambda *_: (_ for _ in ()).throw(preflight.PreflightError("Compose configuration validation failed")),
    )
    assert preflight.main([]) == 1
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    assert preflight.main(["--not-an-option", sentinel]) == 1
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    monkeypatch.setattr(
        preflight, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, sentinel, sentinel)
    )
    with pytest.raises(preflight.PreflightError, match="Compose rendering failed"):
        preflight.checked(["docker"], cwd=ROOT, error="Compose rendering failed")


def test_deploy_and_config_rejection_paths_do_not_invoke_compose() -> None:
    script = ROOT / "scripts" / "compose_prod.sh"
    for arguments in (
        ("deploy", "--allow-dirty"),
        ("config",),
        ("config", "--environment"),
        ("config", "--format", "json"),
    ):
        result = subprocess.run(
            ["bash", str(script), *arguments], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        assert result.returncode == 64
        assert "docker" not in result.stdout
    helper = script.read_text(encoding="utf-8")
    assert "if (($# != 0)); then" in helper
    assert helper.index("run_preflight\n        run_compose up -d --no-build --pull always") > helper.index("deploy)")


def test_config_safe_selectors_reach_only_the_fake_compose(tmp_path: Path) -> None:
    marker = tmp_path / "compose-args"
    docker = tmp_path / "docker"
    docker.write_text(f"#!/bin/sh\nprintf '%s' \"$*\" > {marker}\n", encoding="utf-8")
    docker.chmod(0o755)
    environment = {"PATH": f"{tmp_path}:/usr/bin:/bin", "HOME": os.environ.get("HOME", "")}
    script = ROOT / "scripts" / "compose_prod.sh"
    for selector in ("--quiet", "--services", "--profiles", "--images"):
        result = subprocess.run(
            ["bash", str(script), "config", selector],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert result.returncode == 0
        assert marker.read_text(encoding="utf-8").endswith(f"config {selector}")


def test_config_safe_selectors_are_exact_and_maintenance_is_fixed() -> None:
    helper = (ROOT / "scripts" / "compose_prod.sh").read_text(encoding="utf-8")
    for selector in ("--quiet", "--services", "--profiles", "--images"):
        assert selector in helper
    for selector in ("--environment", "--format"):
        assert selector not in helper.split("config)", 1)[1].split("ps|logs", 1)[0]
    actions = {
        "session-token-contract-drain",
        "session-token-contract-inspect",
        "session-token-contract-migration",
        "session-token-contract-verify",
        "pitr-base-backup",
        "pitr-switch-wal",
        "pitr-archive-status",
        "pitr-list-backups",
        "retire-disabled-profiles",
    }
    for action in actions:
        assert f"{action})" in helper
    assert "${2:-} != --approved || $# -ne 2" not in helper
    assert "if (($# != 2)) || [[ ${2:-} != --approved ]]; then" in helper
    assert (
        "run_compose stop api worker analytics-retention summary-refresher archive-intelligence-refresher archive-enrichment-queue diarization-worker"
        in helper
    )
    assert "run_compose exec backup /scripts/walg_base_backup.sh" in helper
    assert "diarization-canary requires exactly one UUID and --approved" in helper
    assert "pg_advisory_xact_lock(hashtext('hasanara-diarization-canary'))" in helper
    assert "duration_seconds <= 600" in helper
    assert "timeout --signal=TERM --kill-after=30s 20m" in helper
    assert "run -d --no-deps" in helper
    assert "DIARIZATION_ALLOWED_VIDEO_IDS=$canary_video_id" in helper
    assert "WHERE id=:'video_id'::uuid AND diarization_state='running'" in helper
    assert "SELECT pg_switch_wal();" in helper
    assert "SELECT archived_count, failed_count, last_archived_wal" in helper
    assert "run_compose exec backup wal-g backup-list" in helper
    assert "recover-attention-backlog requires cohort alignment|yt-dlp, limit 1..5" in helper
    assert 'python -m scripts.recover_attention_backlog --cohort "$2" --limit "$3"' in helper
    assert "--confirm RECOVER" in helper
    canary = helper.split("run_diarization_canary() {", 1)[1].split("\n}\n\nassert_exact_token_container_absent", 1)[0]
    assert "compose() {" in helper and 'exec "${CLEAN_ENV[@]}" "${COMPOSE[@]}" "$@"' in helper
    assert "run_compose" not in canary
    assert (
        canary.index("run_preflight")
        < canary.index("check_diarization_role")
        < canary.index("timeout --signal=TERM")
        < canary.index("finalize_canary_success")
    )
    assert "acquire_canary" in canary
    assert "canary-finalizing" in helper
    role_check = helper.split("diarization-role-check)", 1)[1].split("*)", 1)[0]
    assert "check_diarization_role" in role_check
    role_sql = (ROOT / "scripts" / "check_diarization_role.sql").read_text(encoding="utf-8")
    for required_role_check in (
        "rolcanlogin",
        "rolcreaterole",
        "rolcreatedb",
        "rolreplication",
        "rolbypassrls",
        "has_schema_privilege",
        "has_database_privilege",
        "required_grants",
    ):
        assert required_role_check in role_sql
    assert "CREATE ROLE" not in helper
    script = ROOT / "scripts" / "compose_prod.sh"
    for arguments in (
        ("maintenance", "session-token-contract-migration"),
        ("maintenance", "session-token-contract-migration", "--approved", "extra"),
        ("maintenance", "retire-disabled-profiles", "--approved", "extra"),
        ("maintenance", "retire-disabled-profiles", "not-approved"),
        ("maintenance", "recover-attention-backlog", "alignment", "6"),
        ("maintenance", "recover-attention-backlog", "unknown", "1"),
        ("maintenance", "recover-attention-backlog", "yt-dlp", "1", "--confirm", "wrong"),
    ):
        result = subprocess.run(
            ["bash", str(script), *arguments], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        assert result.returncode == 64


def test_backup_scheduler_dependencies_are_built_into_the_image() -> None:
    dockerfile = (ROOT / "Dockerfile.postgres-walg").read_text(encoding="utf-8")
    scheduler = (ROOT / "scripts" / "start_backup_scheduler.sh").read_text(encoding="utf-8")
    assert "cron rsync" in dockerfile
    assert "apt-get" not in scheduler


def test_release_images_use_clean_python_packages_and_pinned_go_sources() -> None:
    api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    postgres_walg = (ROOT / "Dockerfile.postgres-walg").read_text(encoding="utf-8")

    cleanup = "RUN python -m pip uninstall --yes pip setuptools wheel"
    assert cleanup in api
    assert api.index(cleanup) < api.index("COPY --from=dependencies /usr/local/lib/python3.11/site-packages")

    for value in (
        "FROM golang:1.26.6-bookworm@sha256:116d58cbd88c1297624acc6e967a060012422bacf9930927e23fb719189c6f36 AS gosu-builder",
        "ARG GOSU_VERSION=1.19",
        "ARG GOSU_REVISION=6456aaa0f3c854d199d0f037f068eb97515b7513",
        "github.com/tianon/gosu",
        'git checkout --detach "${GOSU_REVISION}"',
        'git rev-parse HEAD)" = "${GOSU_REVISION}"',
        'git describe --exact-match --tags HEAD)" = "${GOSU_VERSION}"',
        "CGO_ENABLED=0 go build -trimpath -ldflags='-s -w'",
        "FROM golang:1.26.6-bookworm@sha256:116d58cbd88c1297624acc6e967a060012422bacf9930927e23fb719189c6f36 AS walg-builder",
        "ARG WALG_VERSION=v3.0.9-dev.0c3efc9",
        "ARG WALG_REVISION=0c3efc982dccb6f25e5fcdf713ef037a86d62b49",
        "ARG WALG_BUILD_DATE=2026-07-23T00:00:00Z",
        'git checkout --detach "${WALG_REVISION}"',
        'git rev-parse HEAD)" = "${WALG_REVISION}"',
        "GOEXPERIMENT=jsonv2 CGO_ENABLED=0 go build -mod=readonly -trimpath",
        "-s -w -X github.com/wal-g/wal-g/cmd/pg.buildDate=${WALG_BUILD_DATE}",
        "github.com/wal-g/wal-g/cmd/pg.gitRevision=${WALG_REVISION}",
        "github.com/wal-g/wal-g/cmd/pg.walgVersion=${WALG_VERSION}",
        "-o /out/wal-g ./main/pg",
        "COPY --from=gosu-builder /out/gosu /usr/local/bin/gosu",
        "COPY --from=walg-builder /out/wal-g /usr/local/bin/wal-g",
        "RUN gosu nobody true && wal-g --version",
    ):
        assert value in postgres_walg
    assert "releases/download" not in postgres_walg
    assert "--ignore" not in postgres_walg


def test_walg_build_overrides_and_verifies_patched_x_crypto() -> None:
    dockerfile = (ROOT / "Dockerfile.postgres-walg").read_text(encoding="utf-8")
    assert "ARG WALG_X_CRYPTO_VERSION=v0.55.0" in dockerfile
    assert 'go mod edit -require="golang.org/x/crypto@${WALG_X_CRYPTO_VERSION}"' in dockerfile
    assert "go mod tidy" in dockerfile
    assert 'go list -mod=mod -m -f "{{.Version}}" golang.org/x/crypto' in dockerfile
    assert '"${WALG_X_CRYPTO_VERSION}"' in dockerfile
    assert "GOEXPERIMENT=jsonv2 CGO_ENABLED=0 go build -mod=readonly -trimpath" in dockerfile


def test_cuda_constraints_override_networkx_for_python_310() -> None:
    dockerfile = (ROOT / "Dockerfile.cuda").read_text(encoding="utf-8")
    assert "libpython3.10" in dockerfile
    assert "grep -Ev '^(contourpy|scipy|networkx)==' constraints.txt" in dockerfile
    assert "printf 'scipy==1.15.3\\nnetworkx==3.4.2\\n' >> /tmp/constraints-worker.txt" in dockerfile
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert "networkx==3.5" in constraints
    assert "networkx==3.4.2" not in constraints


def _assert_cuda_bootstrap_contract_specs() -> None:
    bootstrap = (ROOT / "requirements-cuda-bootstrap.txt").read_text(encoding="utf-8")
    package_specs = [line for line in bootstrap.splitlines() if line and not line.startswith("#")]
    assert package_specs == [
        "cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==12.6.3",
        "cuda-bindings==12.9.8",
        "nvidia-cudnn-cu12==9.10.2.21",
        "nvidia-cusparselt-cu12==0.7.1",
        "nvidia-nccl-cu12==2.29.3",
        "nvidia-nvshmem-cu12==3.4.5",
    ]
    extras = package_specs[0].split("[", 1)[1].split("]", 1)[0].split(",")
    assert extras == [
        "cublas",
        "cudart",
        "cufft",
        "cufile",
        "cupti",
        "curand",
        "cusolver",
        "cusparse",
        "nvjitlink",
        "nvrtc",
        "nvtx",
    ]


def test_cuda_bootstrap_uses_canonical_pypi_before_torch() -> None:
    _assert_cuda_bootstrap_contract_specs()
    dockerfile = (ROOT / "Dockerfile.cuda").read_text(encoding="utf-8")
    bootstrap_install = "pip3 install --no-cache-dir --only-binary=:all: " "--index-url https://pypi.org/simple"
    torch_install = "pip3 install --no-cache-dir --index-url ${CUDA_WHEEL_INDEX}"
    assert (
        "COPY requirements.txt requirements-ml-runtime.txt "
        "requirements-cuda-bootstrap.txt constraints.txt ./" in dockerfile
    )
    assert bootstrap_install in dockerfile
    bootstrap_requirements = dockerfile.index("-r requirements-cuda-bootstrap.txt", dockerfile.index(bootstrap_install))
    assert dockerfile.index(bootstrap_install) < bootstrap_requirements < dockerfile.index(torch_install)


def test_release_workflow_contracts() -> None:
    release_path = ROOT / ".gitea" / "workflows" / "release.yaml"
    assert release_path.is_file()
    assert (ROOT / "e2e" / "package-lock.json").is_file()
    assert "package-lock.json" not in (ROOT / "e2e" / ".gitignore").read_text(encoding="utf-8")
    assert "!e2e/package-lock.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert not (ROOT / ".gitea" / "workflows" / "release.yml").exists()
    assert not (ROOT / ".github" / "workflows" / "release.yml").exists()
    workflow = release_path.read_text(encoding="utf-8")
    verify_script = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert 'export TEST_SERVICE_HOST="${TEST_SERVICE_HOST:-localhost}"' in verify_script
    assert (
        'VERIFY_RUN_TOKEN="${HASANARA_TEST_RUN_TOKEN:-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$$}"'
        in verify_script
    )
    assert 'COMPOSE_PROJECT="hasanara-test-${VERIFY_RUN_TOKEN}"' in verify_script
    assert 'docker compose -p "${COMPOSE_PROJECT}"' in verify_script
    assert 'export TEST_POSTGRES_PORT="${TEST_POSTGRES_PORT:-0}"' in verify_script
    assert '"${COMPOSE[@]}" port "${service}" "${container_port}"' in verify_script
    assert "published_port postgres 5432" in verify_script
    assert "published_port redis 6379" in verify_script
    assert "published_port opensearch 9200" in verify_script
    assert "@${TEST_SERVICE_HOST}:${TEST_POSTGRES_PORT}/hasanara_test" in verify_script
    assert "redis://${TEST_SERVICE_HOST}:${TEST_REDIS_PORT}/0" in verify_script
    assert "http://${TEST_SERVICE_HOST}:${TEST_OPENSEARCH_PORT}" in verify_script

    uses_references = re.findall(r"^\s*uses:\s*([^\s@]+)@([^\s#]+)", workflow, flags=re.MULTILINE)
    assert uses_references
    for action, revision in uses_references:
        if not action.startswith("./"):
            assert re.fullmatch(r"[0-9a-f]{40}", revision), f"{action} must be pinned to a commit SHA"

    def job_section(name: str) -> str:
        match = re.search(
            rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)",
            workflow,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert match, f"missing {name} job"
        return match.group(1)

    assert ".gitea" in set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert re.search(r"^permissions:\n  contents: read\n", workflow, flags=re.MULTILINE)
    verify = job_section("verify")
    cross_browser = job_section("cross-browser")
    verification_step = re.search(
        r"^      - name: Run canonical verification\n(.*?)(?=^      - name:|\Z)",
        verify,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert verification_step
    verification_text = verification_step.group(0)
    setup_step = re.search(
        r"^      - name: Create isolated Python verification environment\n(.*?)(?=^      - name:|\Z)",
        verify,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert setup_step
    setup_text = setup_step.group(0)
    assert "rm -rf -- .release-venv" in setup_text
    assert '"${{ steps.python.outputs.python-path }}" -m venv .release-venv' in setup_text
    assert ".release-venv/bin/python -m pip install --upgrade pip" in setup_text
    assert ".release-venv/bin/python -m pip install setuptools==83.0.0" in setup_text
    assert ".release-venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt" in setup_text
    assert '${{ steps.python.outputs.python-path }}" -m pip install' not in setup_text
    assert "PYTHON_BIN: ${{ steps.python.outputs.python-path }}" not in verification_text
    assert (
        "docker inspect --format '{{range .NetworkSettings.Networks}}{{println .Gateway}}{{end}}' \"$(hostname)\""
        in verification_text
    )
    assert '[[ -n "$candidate" ]]' in verification_text
    assert re.search(
        r'\[\[ "\$gateway" =~ \^\(\(25\[0-5\]\|2\[0-4\]\[0-9\]\|1\[0-9\]\{2\}\|\[1-9\]\?\[0-9\]\)\\\.\)\{3\}',
        verification_text,
    )
    assert 'PYTHON_BIN="$PWD/.release-venv/bin/python" TEST_SERVICE_HOST="$gateway" make verify' in verification_text
    assert "${{ github.workspace }}" not in verification_text
    assert '"${PYTHON_BIN}" -m pip_audit --local --desc --skip-editable' in verify_script
    assert "pip_audit" not in setup_text
    assert "host.docker.internal" not in verification_text
    assert "echo" not in verification_text and "printf" not in verification_text.replace(
        "printf '%s\\n' \"$candidate\"", ""
    )
    dev_requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "msgpack==1.2.1" in dev_requirements
    assert "CacheControl" in dev_requirements
    assert "PyPDF2" not in dev_requirements
    images = job_section("images")
    release = job_section("release")
    assert re.search(r"^    runs-on: switchyard-production$", images, flags=re.MULTILINE)
    assert re.search(r"^    needs: verify$", cross_browser, flags=re.MULTILINE)
    for name, job in (("cross-browser", cross_browser), ("images", images)):
        strategy = re.search(
            r"^    strategy:\n(.*?)(?=^    [a-z][\w-]*:|\Z)",
            job,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert strategy, f"missing {name} strategy"
        assert re.search(
            r"^      max-parallel: 1$", strategy.group(1), flags=re.MULTILINE
        ), f"{name} matrix must serialize runner use"
    assert re.search(r"^      contents: read$", release, flags=re.MULTILINE)
    assert re.search(r"^      releases: write$", release, flags=re.MULTILINE)
    manifest_generation = re.search(
        r"^      - name: Generate immutable release manifest\n(.*?)(?=^      - name:|\Z)",
        release,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert manifest_generation
    manifest_text = manifest_generation.group(0)
    expected_roles = ("api", "ingest-cuda", "ml-cuda", "frontend", "postgres-walg")
    assert 'roles = ("api", "ingest-cuda", "ml-cuda", "frontend", "postgres-walg")' in manifest_text
    assert all(f'"{role}"' in manifest_text for role in expected_roles)
    assert "for role in roles:" in manifest_text
    assert 'path = Path("image-evidence") / role / f"{role}.json"' in manifest_text
    assert "path.is_symlink() or not path.is_file()" in manifest_text
    assert 'json.loads(path.read_text(encoding="utf-8"))' in manifest_text
    assert "except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:" in manifest_text
    for validation in (
        "not isinstance(item, dict)",
        'set(item) != {"role", "image"}',
        'not isinstance(item["role"], str)',
        'not isinstance(item["image"], str)',
        'item["role"] != role',
        'item["role"] in images',
        'not ref.fullmatch(item["image"])',
    ):
        assert validation in manifest_text
    assert 'Path("image-evidence").glob("*/*.json")' not in manifest_text
    assert ".glob(" not in manifest_text
    assert "set(images) != set(roles)" in manifest_text

    library_scan = re.search(
        r"^      - name: Block digest high and critical application-library vulnerabilities\n(.*?)(?=^      - name:|\Z)",
        images,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert library_scan
    assert "--scanners vuln --format sarif" in library_scan.group(0)
    assert "--severity CRITICAL,HIGH --pkg-types library --exit-code 1" in library_scan.group(0)
    assert '> "trivy-${{ matrix.role }}-library.sarif"' in library_scan.group(0)
    assert workflow.index("Block digest high and critical application-library vulnerabilities") < workflow.index(
        "Install Cosign"
    )
    assert "IMAGE_REF: ${{ matrix.image }}@${{ steps.publish.outputs.digest }}" in workflow
    publish_match = re.search(
        r"^      - name: Push scanned local image and resolve digest\n(.*?)(?=^      - name:|\Z)",
        images,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert publish_match
    publish = publish_match.group(0)
    assert 'docker push "$IMAGE:$TAG"' not in workflow
    assert "quay.io/skopeo/stable@sha256:47853bb9fb24202af9110531ebd6e43c5f97701254ca290596640290d17942f4" in publish
    assert "https://git.subcult.tv/v2/token" in publish
    assert '--data-urlencode "service=container_registry"' in publish
    assert '--data-urlencode "scope=repository:${repository}:pull,push"' in publish
    assert 'repository="${IMAGE#git.subcult.tv/}"' in publish
    assert 'destination="docker://${IMAGE}:${TAG}"' in publish
    assert "destination_tls_verify=true" in publish
    assert "if docker container inspect gitea >/dev/null 2>&1; then" in publish
    assert 'docker network create --internal "$network"' in publish
    assert 'docker network connect --alias registry-origin "$network" gitea' in publish
    assert "-v /var/run/docker.sock:/var/run/docker.sock" in publish
    assert 'destination="docker://registry-origin:3000/${repository}:${TAG}"' in publish
    assert '"docker-daemon:${IMAGE}:${TAG}" "$DESTINATION"' in publish
    assert '--dest-tls-verify="$DESTINATION_TLS_VERIFY"' in publish
    assert '--dest-registry-token "$REGISTRY_BEARER_TOKEN"' in publish
    assert "--digestfile /evidence/pushed.digest" in publish
    assert 'REGISTRY_BEARER_TOKEN="$registry_token" docker run' in publish
    assert "-e REGISTRY_BEARER_TOKEN" in publish
    assert '-e DESTINATION="$destination"' in publish
    assert '-e DESTINATION_TLS_VERIFY="$destination_tls_verify"' in publish
    assert "--entrypoint /bin/sh" in publish
    assert "auth.json" not in publish
    assert "identitytoken" not in publish
    assert 'evidence_volume="hasanara-push-evidence-${{ gitea.run_id }}-${{ matrix.role }}"' in publish
    assert 'docker volume create "$evidence_volume" >/dev/null' in publish
    assert '-v "$evidence_volume:/evidence"' in publish
    assert '-v "$evidence_volume:/evidence:ro"' in publish
    assert "cat /evidence/pushed.digest" in publish
    assert 'docker network disconnect "$network" gitea' in publish
    assert 'docker network rm "$network"' in publish
    assert 'docker volume rm --force "$evidence_volume" >/dev/null 2>&1 || true' in publish
    assert "trap cleanup EXIT" in publish
    assert 'docker buildx imagetools inspect "$IMAGE:$TAG"' in publish
    assert '[[ "$canonical_digest" == "$pushed_digest" ]]' in publish
    assert 'docker pull "$IMAGE@$canonical_digest" >/dev/null' in publish
    assert 'printf \'digest=%s\\n\' "$canonical_digest" >> "$GITHUB_OUTPUT"' in publish
    assert "for attempt in 1 2 3; do" in publish
    assert publish.count("https://git.subcult.tv/v2/token") == 1
    assert publish.index("for attempt in 1 2 3; do") < publish.index('registry_token="$(curl')
    assert publish.index('registry_token="$(curl') < publish.index('REGISTRY_BEARER_TOKEN="$registry_token" docker run')
    assert "rm -f /evidence/pushed.digest" in publish
    assert '[[ "$copied" == true ]]' in publish
    assert 'sleep "$((attempt * 2))"' in publish
    assert "--ignore" not in workflow
    assert "load: true" in workflow and "push: false" in workflow
    assert "--type slsaprovenance" in workflow and "--type spdxjson" in workflow
    assert "--key env://COSIGN_PRIVATE_KEY" in workflow
    prerequisites = re.search(
        r"^      - name: Validate release prerequisites\n(.*?)(?=^      - name:|\Z)",
        images,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert prerequisites
    prerequisite_text = prerequisites.group(0)
    for value in (
        "REGISTRY_USER: ${{ vars.REGISTRY_USER }}",
        "REGISTRY_PAT: ${{ secrets.REGISTRY_PAT }}",
        "COSIGN_PUBLIC_KEY_B64: ${{ vars.COSIGN_PUBLIC_KEY_B64 }}",
        "HASANARA_REDIS_IMAGE: ${{ vars.HASANARA_REDIS_IMAGE }}",
        "for required in REGISTRY_USER REGISTRY_PAT COSIGN_PUBLIC_KEY_B64",
        '[[ "$HASANARA_REDIS_IMAGE" =~ ^[^@[:space:]]+@sha256:[0-9a-f]{64}$ ]]',
    ):
        assert value in prerequisite_text
    assert "echo" not in prerequisite_text
    assert workflow.index("Validate release prerequisites") < workflow.index(
        "Checkout code", workflow.index("  images:")
    )

    trivy_image = "docker.io/aquasec/trivy@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"
    assert workflow.count(trivy_image) == 1
    assert "aquasecurity/trivy-action" not in workflow
    assert "docker.io/aquasec/trivy:" not in workflow
    cache_setup = re.search(
        r"^      - name: Prepare pinned Trivy scanner cache\n(.*?)(?=^      - name:|\Z)",
        images,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert cache_setup
    assert '[[ "$trivy_image" =~ ^docker\\.io/aquasec/trivy@sha256:[0-9a-f]{64}$ ]]' in cache_setup.group(0)
    assert 'docker volume create "$cache_volume" >/dev/null' in cache_setup.group(0)
    assert "echo" not in cache_setup.group(0)
    # Runner jobs use the host Docker daemon: inputs travel through the managed
    # volume or stdin, never through workspace bind mounts that arrive empty.
    assert "< security/lightning-2.6.6.vex.json" in cache_setup.group(0)
    assert "/cache/lightning.vex.json" in cache_setup.group(0)

    def scan_step(name: str) -> str:
        match = re.search(
            rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - name:|\Z)", images, re.MULTILINE | re.DOTALL
        )
        assert match, f"missing {name}"
        return match.group(0)

    local_scan = scan_step("Block local high and critical application-library vulnerabilities")
    digest_scan = scan_step("Block digest high and critical application-library vulnerabilities")
    for scan in (local_scan, digest_scan):
        assert "--vex /root/.cache/trivy/lightning.vex.json" in scan
        assert '--entrypoint python3 "$IMAGE_REF" - < scripts/check_lightning_patch.py' in scan
        assert "--network none" in scan
    os_scan = scan_step("Report digest OS vulnerabilities")
    sbom_scan = scan_step("Generate SPDX JSON SBOM for digest")
    cleanup = scan_step("Remove Trivy scanner cache")
    for scan in (local_scan, digest_scan, os_scan, sbom_scan):
        assert "docker run --rm" in scan
        assert "-v /var/run/docker.sock:/var/run/docker.sock" in scan
        assert '-v "$TRIVY_CACHE_VOLUME:/root/.cache/trivy"' in scan
        assert '"$TRIVY_IMAGE" image' in scan
        assert "${{ github.workspace }}" not in scan
        assert "--timeout 15m" in scan
    for scan in (digest_scan, os_scan, sbom_scan):
        assert "-e TRIVY_USERNAME -e TRIVY_PASSWORD" in scan
        assert "TRIVY_USERNAME: ${{ vars.REGISTRY_USER }}" in scan
        assert "TRIVY_PASSWORD: ${{ secrets.REGISTRY_PAT }}" in scan
    assert "/root/.docker" not in images
    assert '-v "$PWD/' not in images
    assert '-v "$HOME/' not in images

    def normalize_command(scan: str) -> str:
        return re.sub(r"\s+", " ", scan.replace("\\\n", " "))

    assert (
        "--scanners vuln --format sarif --severity CRITICAL,HIGH --pkg-types library --exit-code 1"
        in normalize_command(local_scan)
    )
    assert (
        "--scanners vuln --format sarif --severity CRITICAL,HIGH --pkg-types library --exit-code 1"
        in normalize_command(digest_scan)
    )
    assert "--scanners vuln --format sarif --severity CRITICAL,HIGH --pkg-types os --exit-code 0" in normalize_command(
        os_scan
    )
    assert "--format spdx-json --exit-code 0" in sbom_scan
    assert '> "trivy-${{ matrix.role }}-local-library.sarif"' in local_scan
    assert '> "trivy-${{ matrix.role }}-os.sarif"' in os_scan
    assert '> "${{ matrix.role }}.spdx.json"' in sbom_scan
    assert "if: always() && steps.publish.outcome == 'success'" in os_scan
    assert "continue-on-error: true" in os_scan
    assert "if: always()" in cleanup
    assert 'if [[ -n "$TRIVY_CACHE_VOLUME" ]]; then' in cleanup
    assert 'docker volume rm --force "$TRIVY_CACHE_VOLUME" >/dev/null' in cleanup

    registry_logout = scan_step("Log out of Gitea registry")
    assert "if: always()" in registry_logout
    assert "docker logout git.subcult.tv >/dev/null 2>&1 || true" in registry_logout
    assert "docker logout git.subcult.tv" not in cleanup
    assert workflow.index("Upload ${{ matrix.role }} image evidence") < workflow.index("Log out of Gitea registry")
    assert workflow.index("Sign and attest digest") < workflow.index("Log out of Gitea registry")
    assert workflow.index("Verify signed digest evidence") < workflow.index("Log out of Gitea registry")

    login = scan_step("Log in to Gitea registry")
    assert "uses:" not in login
    assert "REGISTRY_USER: ${{ vars.REGISTRY_USER }}" in login
    assert "REGISTRY_PAT: ${{ secrets.REGISTRY_PAT }}" in login
    assert (
        'printf \'%s\' "$REGISTRY_PAT" | docker login git.subcult.tv --username "$REGISTRY_USER" --password-stdin'
        in login
    )
    assert "for attempt in 1 2 3; do" in login
    assert 'sleep "$((attempt * 2))"' in login
    assert (
        workflow.index("Set up Docker Buildx")
        < workflow.index("Log in to Gitea registry")
        < workflow.index("Build ${{ matrix.role }} once for scanning")
    )

    provenance = re.search(
        r'Path\(f"\{os\.environ\[\'ROLE\'\]\}\.provenance\.json"\).*?\n          \}\) \+ "\\n"\)',
        images,
        flags=re.DOTALL,
    )
    assert provenance
    provenance_text = provenance.group(0)
    for value in (
        '"buildType"',
        '"builder"',
        '"invocation"',
        '"metadata"',
        '"materials"',
        '"configSource"',
        '"entryPoint": os.environ["DOCKERFILE"]',
        '"role": os.environ["ROLE"]',
        '"sha1": os.environ["SOURCE_COMMIT"]',
        '"buildInvocationId": os.environ["RUN_ID"]',
        '"buildStartedOn"',
        '"buildFinishedOn"',
        '"completeness"',
        '"reproducible": False',
    ):
        assert value in provenance_text
    for forbidden_predicate_field in ('"_type"', '"predicateType"', '"subject"', '"predicate"'):
        assert forbidden_predicate_field not in provenance_text

    signing = re.search(
        r"^      - name: Sign and attest digest\n(.*?)(?=^      - name:|\Z)", images, flags=re.MULTILINE | re.DOTALL
    )
    verification = re.search(
        r"^      - name: Verify signed digest evidence\n(.*?)(?=^      - name:|\Z)",
        images,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert signing and verification
    assert workflow.index(signing.group(0)) < workflow.index(verification.group(0))
    signing_text = signing.group(0)
    verification_text = verification.group(0)
    for value in (
        "COSIGN_PUBLIC_KEY_B64: ${{ vars.COSIGN_PUBLIC_KEY_B64 }}",
        'base64.b64decode(os.environ["COSIGN_PUBLIC_KEY_B64"], validate=True)',
        "Path(f\"{os.environ['ROLE']}.cosign.pub\").write_bytes(public_key)",
        'cosign verify --key "${ROLE}.cosign.pub" "$IMAGE_REF" > "${ROLE}.signature.verify.json"',
        'cosign verify-attestation --key "${ROLE}.cosign.pub" --type slsaprovenance "$IMAGE_REF" > "${ROLE}.provenance.verify.json"',
        'cosign verify-attestation --key "${ROLE}.cosign.pub" --type spdxjson "$IMAGE_REF" > "${ROLE}.sbom.verify.json"',
        "import base64",
        "import binascii",
        'envelope.get("payloadType") != "application/vnd.in-toto+json"',
        'base64.b64decode(envelope["payload"], validate=True)',
        'statement = json.loads(payload.decode("utf-8"))',
        'statement.get("predicateType") == "https://slsa.dev/provenance/v0.2"',
        'statement.get("predicateType") == "https://spdx.dev/Document"',
        'subject.get("digest") == {"sha256": expected_digest}',
        'config_source.get("uri") == expected_repository',
        'config_source.get("digest") == {"sha1": expected_commit}',
        'config_source.get("entryPoint") == expected_dockerfile',
        'parameters.get("role") == expected_role',
        'material.get("uri") == expected_repository',
        'material.get("digest") == {"sha1": expected_commit}',
    ):
        assert value in verification_text
    assert (
        verification_text.index("write_bytes(public_key)")
        < verification_text.index("cosign verify --key")
        < verification_text.index("--type slsaprovenance")
        < verification_text.index("--type spdxjson")
    )
    for private_value in ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD"):
        assert private_value in signing_text
        assert private_value not in verification_text
        assert private_value not in prerequisite_text
    assert workflow.count("COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}") == 1
    assert workflow.count("COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}") == 1
    assert "print(" not in verification_text
    for evidence in (
        "${{ matrix.role }}.cosign.pub",
        "${{ matrix.role }}.signature.verify.json",
        "${{ matrix.role }}.provenance.verify.json",
        "${{ matrix.role }}.sbom.verify.json",
    ):
        assert evidence in images

    for job in ("verify:", "cross-browser:", "images:", "release:"):
        assert f"  {job}" in workflow
    assert "needs: [verify, cross-browser-gate]" in workflow
    assert "needs: images" in workflow
    for role, dockerfile in (
        ("api", "Dockerfile.api"),
        ("ingest-cuda", "Dockerfile.ingest.cuda"),
        ("ml-cuda", "Dockerfile.cuda"),
        ("frontend", "frontend/Dockerfile"),
        ("postgres-walg", "Dockerfile.postgres-walg"),
    ):
        assert f"- role: {role}" in workflow
        assert f"dockerfile: {dockerfile}" in workflow
    assert "'v*-rc.*'" in workflow and "'v*-beta.*'" in workflow and "workflow_dispatch:" in workflow
    for value in (
        "vars.REGISTRY_USER",
        "vars.RELEASE_OPERATOR",
        "vars.HASANARA_REDIS_IMAGE",
        "vars.COSIGN_PUBLIC_KEY_B64",
        "secrets.REGISTRY_PAT",
        "secrets.COSIGN_PRIVATE_KEY",
        "secrets.COSIGN_PASSWORD",
    ):
        assert value in workflow
    assert '"$ACTOR" == "$RELEASE_OPERATOR"' in workflow
    assert "refs/heads/release/v" in workflow and "workflow_dispatch" in workflow
    for image in (
        "git.subcult.tv/subculture-collective/hasanara-api",
        "git.subcult.tv/subculture-collective/hasanara-ingest-cuda",
        "git.subcult.tv/subculture-collective/hasanara-ml-cuda",
        "git.subcult.tv/subculture-collective/hasanara-frontend",
        "git.subcult.tv/subculture-collective/hasanara-postgres-walg",
    ):
        assert image in workflow
    assert 'schema_version": 1' in workflow and '"redis": "redis"' in workflow
    assert workflow.count("actions/download-artifact@9bc31d5ccc31df68ecc42ccf4149144866c47d8a") == 9
    assert workflow.count("actions/upload-artifact@ff15f0306b3f739f7b6fd43fb5d26cd321bd4de5") >= 3
    assert "gitea.api_url" in workflow and "gitea.token" in workflow and 'prerelease": True' in workflow
    assert '"$API_URL/repos/$REPOSITORY/releases"' in workflow
    assert "gitea.event_name == 'push'" in workflow
    assert "Redis is third-party and is not attested" in workflow
    for forbidden in (
        "github.",
        "GITHUB_TOKEN",
        "ghcr.io",
        "type=gha",
        "actions/attest-build-provenance",
        "codeql-action",
        "packages: write",
        "id-token: write",
        "attestations: write",
        "security-events: write",
        ":latest",
    ):
        assert forbidden not in workflow
    assert ":latest" not in workflow


def test_release_cross_browser_marker_gate_contract() -> None:
    workflow = (ROOT / ".gitea" / "workflows" / "release.yaml").read_text(encoding="utf-8")

    def job_section(name: str) -> str:
        match = re.search(
            rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)",
            workflow,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert match, f"missing {name} job"
        return match.group(1)

    cross_browser = job_section("cross-browser")
    gate = job_section("cross-browser-gate")
    images = job_section("images")
    evidence = ("firefox-desktop", "webkit-desktop", "chromium-mobile", "webkit-mobile")
    download_sha = "actions/download-artifact@9bc31d5ccc31df68ecc42ccf4149144866c47d8a"
    upload_sha = "actions/upload-artifact@ff15f0306b3f739f7b6fd43fb5d26cd321bd4de5"

    for key in evidence:
        assert f"evidence: {key}" in cross_browser
        assert f"name: cross-browser-success-{key}" in gate
        assert f"path: cross-browser-evidence/{key}" in gate
    assert '--project="${{ matrix.project }}" --workers=1' in cross_browser
    marker = re.search(
        r"^      - name: Create cross-browser success marker\n(.*?)(?=^      - name:|\Z)",
        cross_browser,
        flags=re.MULTILINE | re.DOTALL,
    )
    upload = re.search(
        r"^      - name: Upload cross-browser success marker\n(.*?)(?=^      - name:|\Z)",
        cross_browser,
        flags=re.MULTILINE | re.DOTALL,
    )
    report = re.search(
        r"^      - name: Upload browser artifacts\n(.*?)(?=^      - name:|\Z)",
        cross_browser,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert marker and upload and report
    assert "printf '%s' '${{ gitea.sha }}'" in marker.group(0)
    assert "if:" not in marker.group(0)
    assert cross_browser.index(marker.group(0)) > cross_browser.index("Run seeded archive smoke test")
    assert cross_browser.index(marker.group(0)) > cross_browser.index(report.group(0))
    assert cross_browser.index(upload.group(0)) > cross_browser.index(marker.group(0))
    assert cross_browser.rstrip().endswith(upload.group(0).rstrip())
    assert upload_sha in upload.group(0)
    assert "if:" not in upload.group(0)
    assert "name: cross-browser-success-${{ matrix.evidence }}" in upload.group(0)
    assert "path: cross-browser-success/${{ matrix.evidence }}.sha" in upload.group(0)
    assert "if: always()" in report.group(0)
    assert "e2e/test-results" in report.group(0) and "e2e/playwright-report" in report.group(0)

    assert "needs: cross-browser" in gate
    assert "if: always()" not in gate
    assert "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in gate
    assert "ref: ${{ gitea.sha }}" in gate
    assert gate.count(download_sha) == 4
    validation = re.search(
        r"^      - name: Validate cross-browser success markers\n(.*?)(?=^      - name:|\Z)",
        gate,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert validation
    assert (
        "python3 scripts/validate_browser_evidence.py --root cross-browser-evidence --sha '${{ gitea.sha }}'"
        in validation.group(0)
    )
    assert "needs: [verify, cross-browser-gate]" in images
    assert "needs.verify.result == 'success'" in images
    assert "needs.cross-browser-gate.result == 'success'" in images


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is unavailable")
def test_compose_render_with_inert_values_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise Compose parsing only; never print its potentially sensitive output."""
    if subprocess.run(
        ["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode:
        pytest.skip("Docker Compose is unavailable")
    env_file = tmp_path / "release.env"
    values = {
        "DB_PASSWORD": "inert",
        "OAUTH_GOOGLE_REDIRECT_URI": "https://example.invalid/google",
        "OAUTH_TWITCH_REDIRECT_URI": "https://example.invalid/twitch",
        "WALG_S3_PREFIX": "s3://inert/prefix",
        "AWS_ACCESS_KEY_ID": "inert",
        "AWS_SECRET_ACCESS_KEY": "inert",
        "AWS_ENDPOINT": "https://example.invalid",
        "AWS_REGION": "auto",
        **{variable: digest(variable.lower()) for variable in IMAGE_VARIABLES},
    }
    diarization_env = tmp_path / "diarization.env"
    diarization_env.write_text(
        "HF_TOKEN=inert\nDATABASE_URL=postgresql+psycopg://hasanara_diarization:inert@db:5432/transcripts\n",
        encoding="utf-8",
    )
    diarization_env.chmod(0o600)
    values["HASANARA_DIARIZATION_ENV_FILE"] = str(diarization_env)
    env_file.write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
    monkeypatch.setenv("HASANARA_ENV_FILE", str(env_file))
    command = ["docker", "compose", "--env-file", str(env_file)]
    for name in preflight.COMPOSE_FILES:
        command.extend(("--file", name))
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", ""),
        "HASANARA_ENV_FILE": str(env_file),
    }
    result = subprocess.run(
        [*command, "config", "--quiet"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, "Compose config --quiet failed (output intentionally suppressed)"
    default_services = subprocess.run(
        [*command, "config", "--services"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert default_services.returncode == 0
    assert "diarization-worker" not in default_services.stdout.splitlines()
    default_environment = subprocess.run(
        [*command, "config", "--environment"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert default_environment.returncode == 0
    preflight.parse_compose_profiles(default_environment.stdout)
    diarization_file = tmp_path / "release-diarization-profile.env"
    diarization_file.write_text(
        env_file.read_text(encoding="utf-8") + "\nCOMPOSE_PROFILES=diarization\n", encoding="utf-8"
    )
    diarization_command = ["docker", "compose", "--env-file", str(diarization_file)]
    for name in preflight.COMPOSE_FILES:
        diarization_command.extend(("--file", name))
    diarization_services = subprocess.run(
        [*diarization_command, "config", "--services"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert diarization_services.returncode == 0
    assert "diarization-worker" in diarization_services.stdout.splitlines()
    diarization_environment = subprocess.run(
        [*diarization_command, "config", "--environment"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert diarization_environment.returncode == 0
    with pytest.raises(preflight.PreflightError, match="unsupported Compose profile selection"):
        preflight.parse_compose_profiles(diarization_environment.stdout)
    full_services = subprocess.run(
        [*command, "--profile", "full", "config", "--services"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert full_services.returncode == 0
    with pytest.raises(preflight.PreflightError, match="unsupported Compose profile"):
        preflight.validate_active_service_set(set(full_services.stdout.splitlines()))
    rendered = subprocess.run(
        [*diarization_command, "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert rendered.returncode == 0, "Compose JSON rendering failed (output intentionally suppressed)"
    configured = json.loads(rendered.stdout)["services"]
    preflight.validate_diarization_contract(
        {"services": configured}, {"images": {"ml-cuda": configured["diarization-worker"]["image"]}}
    )
    env_file_services = {
        "migrations",
        "api",
        "worker",
        "analytics-retention",
        "summary-refresher",
        "archive-intelligence-refresher",
        "archive-enrichment-queue",
        "diarization-worker",
        "backup",
    }
    role_variables = {
        "api": "HASANARA_API_IMAGE",
        "ingest-cuda": "HASANARA_INGEST_IMAGE",
        "ml-cuda": "HASANARA_ML_IMAGE",
        "frontend": "HASANARA_FRONTEND_IMAGE",
        "postgres-walg": "HASANARA_POSTGRES_IMAGE",
        "redis": "HASANARA_REDIS_IMAGE",
    }
    for service in diarization_services.stdout.splitlines():
        details = configured[service]
        assert details["image"] == values[role_variables[preflight.SERVICE_ROLES[service]]]
        assert "build" not in details
        environment = details.get("environment", {})
        if service == "db":
            assert environment["POSTGRES_PASSWORD"] == "inert"
        if service in env_file_services:
            assert environment["ALLOW_SESSION_TOKEN_CONTRACT_MIGRATION"] == "false"
            assert environment["ALLOW_EVENT_TOKEN_CONTRACT_MIGRATION"] == "false"
        if service in env_file_services - {"diarization-worker"}:
            assert environment["DB_PASSWORD"] == "inert"
        if service in preflight.DATABASE_CLIENTS:
            assert environment["DATABASE_URL"] == DATABASE_URL
        if service == "diarization-worker":
            assert environment["DATABASE_URL"] == (
                "postgresql+psycopg://hasanara_diarization:inert@db:5432/transcripts"
            )
        if service == "backup":
            assert environment["PGPASSWORD"] == "inert"
        if service in preflight.APPLICATION_SERVICES | {"diarization-worker"}:
            assert environment["ENVIRONMENT"] == "production"
            assert environment["LOG_LEVEL"] == "INFO"
