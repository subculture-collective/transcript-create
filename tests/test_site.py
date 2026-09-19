from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def test_site_config_is_explicit_public_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "SITE_NAME", "Creator library")
    monkeypatch.setattr(settings, "SITE_CREATOR_NAME", "Demo creator")
    monkeypatch.setattr(settings, "PUBLIC_PASSAGES_ENABLED", False)
    response = TestClient(app).get("/site")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Creator library"
    assert data["creator_name"] == "Demo creator"
    assert data["public_passages_enabled"] is False
    assert set(data) == {
        "name",
        "creator_name",
        "description",
        "community_enabled",
        "atproto_enabled",
        "public_passages_enabled",
    }
