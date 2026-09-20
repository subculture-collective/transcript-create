import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.branding import BrandProfile, load_brand_profile
from app.settings import Settings
from scripts.plan_client_updates import plan_updates
from scripts.release_preflight import IMAGE_ROLES, SERVICE_ROLES, PreflightError


def test_neutral_defaults_and_profile_identity_override(tmp_path):
    neutral = Settings(_env_file=None)
    assert neutral.SITE_NAME == "Transcript Archive"
    assert neutral.WHISPER_INITIAL_PROMPT == ""
    assert neutral.ARCHIVE_EDITORIAL_PRESET == "generic"
    path = tmp_path / "brand.json"
    path.write_text(json.dumps({"schema_version": 1, "name": "Northstar", "creator_name": "Studio"}))
    config = Settings(_env_file=None, SITE_PROFILE_PATH=str(path))
    assert config.SITE_NAME == "Northstar"
    assert config.SITE_CREATOR_NAME == "Studio"
    assert Settings(_env_file=None, SITE_PROFILE_PATH=str(path), SITE_NAME="Override").SITE_NAME == "Override"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2},
        {"name": " "},
        {"SESSION_SECRET": "not-public"},
        {"logo_url": "javascript:alert(1)"},
        {"logo_url": "//evil.example/logo"},
        {"operator_url": "https://user:password@example.org"},
        {"favicon_url": "/\\evil.example/logo"},
        {"theme": {"dark": {"accent": "red; background:url(evil)"}}},
        {"theme": {"light": {"unknown-token": "#ffffff"}}},
        {"theme": {"font": "arbitrary-font"}},
    ],
)
def test_profile_rejects_unsafe_or_unsupported_configuration(payload):
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(payload)


def test_missing_and_invalid_profiles_fail_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        Settings(_env_file=None, SITE_PROFILE_PATH=str(tmp_path / "missing.json"))
    path = tmp_path / "invalid.json"
    path.write_text("{")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SITE_PROFILE_PATH=str(path))


def test_shipped_example_is_valid():
    profile = load_brand_profile("config/branding/northstar.json")
    assert profile.name == "Northstar Archive"
    assert profile.theme.dark["accent"] != profile.theme.light["accent"]


def fleet_files(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    manifest = tmp_path / "release.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_commit": "a" * 40,
                "images": {role: f"registry.example/{role}@sha256:{'b' * 64}" for role in IMAGE_ROLES},
                "services": SERVICE_ROLES,
            }
        )
    )
    clients = []
    for name in ("north", "south"):
        (tmp_path / f"{name}.json").write_text(json.dumps({"name": name}))
        clients.append(
            {
                "id": name,
                "profile": f"{name}.json",
                "assets": "assets",
                "services": ["api", "frontend", "migrations", "worker"],
            }
        )
    fleet = tmp_path / "fleet.json"
    fleet.write_text(json.dumps({"schema_version": 1, "clients": clients}))
    return manifest, fleet


def test_one_release_updates_multiple_clients_without_editing_profiles(tmp_path):
    manifest, fleet = fleet_files(tmp_path)
    before = (tmp_path / "north.json").read_bytes()
    result = plan_updates(manifest, fleet, tmp_path / "plan")
    assert [client["id"] for client in result["clients"]] == ["north", "south"]
    for name in ("north", "south"):
        compose = json.loads((tmp_path / "plan" / f"{name}.compose.json").read_text())
        assert "@sha256:" in compose["services"]["api"]["image"]
        mount = compose["services"]["api"]["volumes"][0]
        assert Path(mount["source"]).name == f"{name}.json"
        assert mount["read_only"] is True
        assert compose["services"]["worker"]["environment"]["SITE_PROFILE_PATH"] == mount["target"]
    assert (tmp_path / "north.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        plan_updates(manifest, fleet, tmp_path / "plan")


def test_invalid_last_client_creates_no_partial_plan(tmp_path):
    manifest, fleet = fleet_files(tmp_path)
    (tmp_path / "south.json").write_text('{"schema_version": 99}')
    with pytest.raises(ValidationError):
        plan_updates(manifest, fleet, tmp_path / "plan")
    assert not (tmp_path / "plan").exists()


def test_mutable_images_cannot_be_planned(tmp_path):
    manifest, fleet = fleet_files(tmp_path)
    data = json.loads(manifest.read_text())
    data["images"]["api"] = "registry.example/api:latest"
    manifest.write_text(json.dumps(data))
    with pytest.raises(PreflightError):
        plan_updates(manifest, fleet, tmp_path / "plan")


def test_missing_asset_cannot_be_planned(tmp_path):
    manifest, fleet = fleet_files(tmp_path)
    (tmp_path / "north.json").write_text('{"logo_url": "/branding/missing.svg"}')
    with pytest.raises(ValueError, match="asset"):
        plan_updates(manifest, fleet, tmp_path / "plan")
