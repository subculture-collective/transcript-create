import secrets
import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.csrf import csrf_token
from app.settings import settings


def _auth_client(client, db_session):
    user_id, token = uuid.uuid4(), secrets.token_urlsafe(32)
    db_session.execute(
        text("INSERT INTO users (id, email, name, role) VALUES (:id, :email, :name, 'user')"),
        {"id": str(user_id), "email": "account@example.com", "name": "Account User"},
    )
    db_session.execute(
        text(
            "INSERT INTO user_identities (user_id, provider, subject, provider_email, provider_name) VALUES (:user_id, 'google', 'account-subject', 'account@example.com', 'Account User')"
        ),
        {"user_id": str(user_id)},
    )
    db_session.execute(
        text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, :expires_at)"),
        {
            "user_id": str(user_id),
            "hash": sha256(token.encode()).hexdigest(),
            "expires_at": datetime.utcnow() + timedelta(days=1),
        },
    )
    db_session.commit()
    client.cookies.set("tc_session", token)
    return user_id, token


def _headers(token):
    return {"origin": settings.FRONTEND_ORIGIN, "x-csrf-token": csrf_token(token)}


def test_get_account_returns_safe_profile_identities_and_sessions(client, db_session):
    _, token = _auth_client(client, db_session)
    response = client.get("/account")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "user"
    assert body["identities"][0]["provider"] == "google"
    assert "subject" not in body["identities"][0]
    assert body["sessions"][0]["current"] is True
    assert "token_hash" not in body["sessions"][0]


def test_account_patch_and_csrf_contract(client, db_session):
    user_id, token = _auth_client(client, db_session)
    assert client.patch("/account", json={"name": "Blocked"}).status_code == 403
    assert client.patch("/account", json={"name": "  "}, headers=_headers(token)).status_code == 422
    assert client.patch("/account", json={"name": "x" * 101}, headers=_headers(token)).status_code == 422
    assert (
        client.patch(
            "/account", json={"name": "Viewer", "avatar_url": "https:///missing-host"}, headers=_headers(token)
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/account", json={"name": "Viewer", "avatar_url": "https://@"}, headers=_headers(token)
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/account", json={"name": "Viewer", "avatar_url": "http://example.com/avatar"}, headers=_headers(token)
        ).status_code
        == 422
    )
    response = client.patch(
        "/account",
        json={"name": "Archive Viewer", "avatar_url": "  https://example.com/avatar  "},
        headers=_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["user"]["name"] == "Archive Viewer"
    assert response.json()["user"]["avatar_url"] == "https://example.com/avatar"
    audit = (
        db_session.execute(
            text(
                "SELECT action, resource_type, resource_id, details FROM audit_logs WHERE user_id=:user_id ORDER BY created_at DESC LIMIT 1"
            ),
            {"user_id": str(user_id)},
        )
        .mappings()
        .one()
    )
    assert audit == {
        "action": "profile_updated",
        "resource_type": "user",
        "resource_id": str(user_id),
        "details": {"fields": ["name", "avatar_url"]},
    }


def test_csrf_endpoint_and_session_revoke_ownership(client, db_session):
    user_id, token = _auth_client(client, db_session)
    other_token = secrets.token_urlsafe(32)
    db_session.execute(
        text(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, now() + interval '1 day')"
        ),
        {"user_id": str(user_id), "hash": sha256(other_token.encode()).hexdigest()},
    )
    db_session.commit()
    assert client.get("/auth/csrf").json()["csrf_token"] == csrf_token(token)
    response = client.delete("/account/sessions", params={"keep_current": "true"}, headers=_headers(token))
    assert response.status_code == 200
    assert response.json()["revoked"] == 1


def test_sessions_only_list_active_and_revoke_contracts(client, db_session):
    user_id, token = _auth_client(client, db_session)
    other_token = secrets.token_urlsafe(32)
    other_session_id = db_session.execute(
        text(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, now() + interval '1 day') RETURNING id"
        ),
        {"user_id": str(user_id), "hash": sha256(other_token.encode()).hexdigest()},
    ).scalar_one()
    expired_id = db_session.execute(
        text(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, now() - interval '1 day') RETURNING id"
        ),
        {"user_id": str(user_id), "hash": sha256(secrets.token_urlsafe(32).encode()).hexdigest()},
    ).scalar_one()
    non_expiring_id = db_session.execute(
        text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, NULL) RETURNING id"),
        {"user_id": str(user_id), "hash": sha256(secrets.token_urlsafe(32).encode()).hexdigest()},
    ).scalar_one()
    other_user_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO users (id, email, name, role) VALUES (:id, :email, :name, 'user')"),
        {"id": str(other_user_id), "email": "other@example.com", "name": "Other User"},
    )
    foreign_session_id = db_session.execute(
        text(
            "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:user_id, :hash, now() + interval '1 day') RETURNING id"
        ),
        {"user_id": str(other_user_id), "hash": sha256(secrets.token_urlsafe(32).encode()).hexdigest()},
    ).scalar_one()
    db_session.commit()

    response = client.get("/account/sessions")
    assert response.status_code == 200
    assert str(expired_id) not in {session["id"] for session in response.json()["sessions"]}
    assert str(non_expiring_id) in {session["id"] for session in response.json()["sessions"]}
    assert client.delete("/account/sessions/not-a-uuid", headers=_headers(token)).status_code == 422
    assert client.delete(f"/account/sessions/{foreign_session_id}", headers=_headers(token)).status_code == 404

    response = client.delete(f"/account/sessions/{other_session_id}", headers=_headers(token))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "set-cookie" not in response.headers
    assert (
        db_session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action='session_revoked' AND resource_id=:id"),
            {"id": str(other_session_id)},
        ).scalar_one()
        == 1
    )

    response = client.delete("/account/sessions", params={"keep_current": "true"}, headers=_headers(token))
    assert response.status_code == 200
    assert response.json()["revoked"] == 2
    assert "set-cookie" not in response.headers
    assert db_session.execute(
        text("SELECT details FROM audit_logs WHERE action='sessions_revoked' ORDER BY created_at DESC LIMIT 1")
    ).scalar_one() == {"keep_current": True, "revoked": 2}

    response = client.delete("/account/sessions", params={"keep_current": "false"}, headers=_headers(token))
    assert response.status_code == 200
    assert response.json()["revoked"] == 1
    assert "tc_session=" in response.headers["set-cookie"]
    assert db_session.execute(
        text("SELECT details FROM audit_logs WHERE action='sessions_revoked' AND details->>'keep_current' = 'false'")
    ).scalar_one() == {"keep_current": False, "revoked": 1}


def test_current_session_revoke_clears_cookie(client, db_session):
    _, token = _auth_client(client, db_session)
    session_id = db_session.execute(
        text("SELECT id FROM sessions WHERE token_hash=:hash"), {"hash": sha256(token.encode()).hexdigest()}
    ).scalar_one()
    response = client.delete(f"/account/sessions/{session_id}", headers=_headers(token))
    assert response.status_code == 200
    assert "tc_session=" in response.headers["set-cookie"]
    assert (
        db_session.execute(
            text("SELECT count(*) FROM audit_logs WHERE action='session_revoked' AND resource_id=:id"),
            {"id": str(session_id)},
        ).scalar_one()
        == 1
    )


def test_profile_update_rolls_back_when_audit_write_fails(client, test_engine, monkeypatch):
    user_id, token = uuid.uuid4(), "profile-audit-failure-token"
    from app.db import SessionLocal, get_db
    from app.main import app

    with test_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, name, role) VALUES (:id, :email, 'Original', 'user')"),
            {"id": str(user_id), "email": "profile-audit@example.com"},
        )
        connection.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :token_hash, now() + interval '1 day')"
            ),
            {"id": str(user_id), "token_hash": sha256(token.encode()).hexdigest()},
        )

    original_override = app.dependency_overrides[get_db]

    def committed_db():
        session = SessionLocal(bind=test_engine)
        try:
            yield session
        finally:
            session.close()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    app.dependency_overrides[get_db] = committed_db
    try:
        monkeypatch.setattr("app.routes.account.write_audit_event", fail_audit)
        response = client.patch(
            "/account", json={"name": "Changed"}, cookies={"tc_session": token}, headers=_headers(token)
        )
        assert response.status_code == 500
        assert response.json() == {"error": "database_error", "message": "Profile could not be updated"}
        with test_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT name FROM users WHERE id=:id"), {"id": str(user_id)}).scalar_one()
                == "Original"
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM audit_logs WHERE user_id=:id AND action='profile_updated'"),
                    {"id": str(user_id)},
                ).scalar_one()
                == 0
            )
    finally:
        app.dependency_overrides[get_db] = original_override
        with test_engine.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": str(user_id)})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": str(user_id)})


def test_session_revoke_rolls_back_and_keeps_cookie_when_audit_write_fails(client, test_engine, monkeypatch):
    user_id, token = uuid.uuid4(), "session-audit-failure-token"
    from app.db import SessionLocal, get_db
    from app.main import app

    with test_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
            {"id": str(user_id), "email": "session-audit@example.com"},
        )
        session_id = connection.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :token_hash, now() + interval '1 day') RETURNING id"
            ),
            {"id": str(user_id), "token_hash": sha256(token.encode()).hexdigest()},
        ).scalar_one()

    original_override = app.dependency_overrides[get_db]

    def committed_db():
        session = SessionLocal(bind=test_engine)
        try:
            yield session
        finally:
            session.close()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    app.dependency_overrides[get_db] = committed_db
    try:
        monkeypatch.setattr("app.routes.account.write_audit_event", fail_audit)
        response = client.delete(
            f"/account/sessions/{session_id}", cookies={"tc_session": token}, headers=_headers(token)
        )
        assert response.status_code == 500
        assert not any(
            cookie.startswith("tc_session=") and "max-age=0" in cookie.lower()
            for cookie in response.headers.get_list("set-cookie")
        )
        with test_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM sessions WHERE id=:id"), {"id": str(session_id)}
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM audit_logs WHERE user_id=:id AND action='session_revoked'"),
                    {"id": str(user_id)},
                ).scalar_one()
                == 0
            )
    finally:
        app.dependency_overrides[get_db] = original_override
        with test_engine.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": str(user_id)})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": str(user_id)})


def test_identity_link_returns_url_and_persists_link_binding(client, db_session):
    user_id, token = _auth_client(client, db_session)
    oauth = MagicMock()
    oauth.google.authorize_redirect = AsyncMock(
        return_value=RedirectResponse("https://accounts.example.invalid/authorize")
    )
    with (
        patch("app.routes.auth.OAuth", return_value=oauth),
        patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
        patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
    ):
        response = client.post("/account/identities/google/link", headers=_headers(token))

    assert response.status_code == 200
    assert response.json() == {"authorization_url": "https://accounts.example.invalid/authorize"}
    binding = (
        db_session.execute(text("SELECT intent, link_user_id FROM oauth_requests ORDER BY expires_at DESC LIMIT 1"))
        .mappings()
        .one()
    )
    assert binding == {"intent": "link", "link_user_id": user_id}


def test_identity_merge_returns_url_and_persists_merge_binding(client, db_session):
    user_id, token = _auth_client(client, db_session)
    oauth = MagicMock()
    oauth.twitch.authorize_redirect = AsyncMock(
        return_value=RedirectResponse("https://twitch.example.invalid/authorize")
    )
    with (
        patch("app.routes.auth.OAuth", return_value=oauth),
        patch.object(settings, "OAUTH_TWITCH_CLIENT_ID", "id"),
        patch.object(settings, "OAUTH_TWITCH_CLIENT_SECRET", "secret"),
    ):
        response = client.post("/account/identities/twitch/merge", headers=_headers(token))

    assert response.status_code == 200
    assert response.json() == {"authorization_url": "https://twitch.example.invalid/authorize"}
    binding = (
        db_session.execute(text("SELECT intent, link_user_id FROM oauth_requests ORDER BY expires_at DESC LIMIT 1"))
        .mappings()
        .one()
    )
    assert binding == {"intent": "merge", "link_user_id": user_id}


def test_unlink_last_identity_is_rejected(client, db_session):
    _, token = _auth_client(client, db_session)
    response = client.delete("/account/identities/google", headers=_headers(token))
    assert response.status_code == 409
    assert response.json()["error"] == "last_identity"


def test_delete_account_requires_exact_confirmation_and_revokes_access(client, db_session):
    user_id, token = _auth_client(client, db_session)
    job_id = uuid.uuid4()
    db_session.execute(
        text("""
        INSERT INTO jobs (id, kind, input_url, owner_user_id, meta)
        VALUES (:id, 'single', 'https://example.com/account-delete', :user_id, CAST(:meta AS jsonb))
    """),
        {
            "id": str(job_id),
            "user_id": str(user_id),
            "meta": '{"owner_user_id": "' + str(user_id) + '", "api_key_id": "key"}',
        },
    )
    db_session.commit()

    assert (
        client.request("DELETE", "/account", json={"confirmation": "delete"}, headers=_headers(token)).status_code
        == 422
    )
    response = client.request("DELETE", "/account", json={"confirmation": "DELETE"}, headers=_headers(token))

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert "tc_session=" in response.headers["set-cookie"]
    assert client.get("/account").status_code == 401
    assert (
        db_session.execute(text("SELECT count(*) FROM sessions WHERE user_id=:id"), {"id": str(user_id)}).scalar_one()
        == 0
    )
    assert db_session.execute(
        text("SELECT owner_user_id, meta FROM jobs WHERE id=:id"), {"id": str(job_id)}
    ).mappings().one() == {"owner_user_id": None, "meta": {}}
    audit = (
        db_session.execute(
            text("SELECT user_id, ip_address, user_agent, details FROM audit_logs WHERE action='user_data_deletion'")
        )
        .mappings()
        .one()
    )
    assert audit == {"user_id": None, "ip_address": None, "user_agent": None, "details": {}}


def test_delete_account_rejects_final_admin_and_keeps_session(client, db_session):
    user_id, token = _auth_client(client, db_session)
    db_session.execute(text("UPDATE users SET role='admin' WHERE id=:id"), {"id": str(user_id)})
    db_session.commit()

    response = client.request("DELETE", "/account", json={"confirmation": "DELETE"}, headers=_headers(token))

    assert response.status_code == 409
    assert response.json()["error"] == "final_admin"
    # The route rollback is deliberately transaction-wide.  The fixture owns
    # that outer transaction, so the function-level regression test verifies
    # persisted session state while this route test verifies the public result.
    assert client.cookies.get("tc_session") == token


def test_delete_account_rolls_back_audit_and_keeps_cookie_when_scrub_fails(client, test_engine, monkeypatch):
    """Use committed seed/verification so the route rollback is observable."""
    user_id, token = uuid.uuid4(), "account-scrub-failure-token"
    from app.db import SessionLocal, get_db
    from app.main import app

    with test_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
            {"id": str(user_id), "email": "scrub-failure@example.com"},
        )
        connection.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :hash, now() + interval '1 day')"
            ),
            {"id": str(user_id), "hash": sha256(token.encode()).hexdigest()},
        )

    original_override = app.dependency_overrides[get_db]

    def committed_db():
        session = SessionLocal(bind=test_engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = committed_db
    monkeypatch.setattr(
        "app.routes.account.delete_prepared_account",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )
    try:
        response = client.request(
            "DELETE",
            "/account",
            json={"confirmation": "DELETE"},
            cookies={"tc_session": token},
            headers=_headers(token),
        )
        assert response.status_code == 500
        assert not any(
            cookie.startswith("tc_session=") and "max-age=0" in cookie.lower()
            for cookie in response.headers.get_list("set-cookie")
        )
        with test_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT count(*) FROM users WHERE id=:id"), {"id": str(user_id)}).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM sessions WHERE user_id=:id"), {"id": str(user_id)}
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM audit_logs WHERE action='user_data_deletion' AND user_id=:id"),
                    {"id": str(user_id)},
                ).scalar_one()
                == 0
            )
    finally:
        app.dependency_overrides[get_db] = original_override
        with test_engine.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": str(user_id)})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": str(user_id)})


def test_delete_account_discards_prepared_capability_when_audit_fails(client, test_engine, monkeypatch):
    """A committed request session makes the failed deletion's capability observable."""
    user_id, token = uuid.uuid4(), "account-audit-failure-token"
    from app.accounts import _prepared_deletions
    from app.db import SessionLocal, get_db
    from app.main import app

    with test_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
            {"id": str(user_id), "email": "audit-failure@example.com"},
        )
        connection.execute(
            text(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :hash, now() + interval '1 day')"
            ),
            {"id": str(user_id), "hash": sha256(token.encode()).hexdigest()},
        )

    baseline = len(_prepared_deletions)
    original_override = app.dependency_overrides[get_db]

    def committed_db():
        session = SessionLocal(bind=test_engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = committed_db
    monkeypatch.setattr(
        "app.routes.account.write_audit_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    try:
        response = client.request(
            "DELETE",
            "/account",
            json={"confirmation": "DELETE"},
            cookies={"tc_session": token},
            headers=_headers(token),
        )
        assert response.status_code == 500
        assert len(_prepared_deletions) == baseline
    finally:
        app.dependency_overrides[get_db] = original_override
        with test_engine.begin() as connection:
            connection.execute(text("DELETE FROM sessions WHERE user_id=:id"), {"id": str(user_id)})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": str(user_id)})
