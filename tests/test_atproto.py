import pytest
from fastapi import HTTPException

from app.routes.atproto import metadata
from app.settings import settings


def test_at_metadata_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "ATPROTO_ENABLED", False)
    assert client.get("/atproto/config").status_code == 404
    assert client.get("/atproto/client-metadata.json").status_code == 404


def test_metadata_uses_configured_origin_minimal_scopes_and_no_host_trust(client, monkeypatch):
    monkeypatch.setattr(settings, "ATPROTO_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "https://archive.example")
    response = client.get("/atproto/client-metadata.json", headers={"Host": "attacker.example"})
    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == "https://archive.example/api/atproto/client-metadata.json"
    assert data["redirect_uris"] == ["https://archive.example/at.html"]
    assert data["scope"] == "atproto repo:app.bsky.feed.post?action=create"
    assert data["token_endpoint_auth_method"] == "none"
    assert data["dpop_bound_access_tokens"] is True
    assert "attacker.example" not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://archive.example",
        "https://archive.example:8443",
        "https://user:password@archive.example",
        "https://archive.example/path",
    ],
)
def test_invalid_client_origin_fails_closed(client, monkeypatch, origin):
    monkeypatch.setattr(settings, "ATPROTO_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", origin)
    assert client.get("/atproto/config").status_code == 503


def test_loopback_is_only_allowed_outside_production(client, monkeypatch):
    monkeypatch.setattr(settings, "ATPROTO_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "http://127.0.0.1:5178")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    assert client.get("/atproto/config").json()["client_id"].startswith("http://localhost?")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as caught:
        metadata()
    assert caught.value.status_code == 503
