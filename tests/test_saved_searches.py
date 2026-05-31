"""Tests for saved searches routes."""

import secrets
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text


def _create_session_user(db_session):
    user_id = uuid.uuid4()
    session_token = secrets.token_urlsafe(32)
    db_session.execute(
        text(
            "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) VALUES (:id, :email, 'google', :subject, 'user')"
        ),
        {"id": str(user_id), "email": "saved@example.com", "subject": "saved-user"},
    )
    db_session.execute(
        text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
        {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
    )
    db_session.commit()
    return user_id, session_token


def _ensure_saved_searches_table(db_session):
    db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS saved_searches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                filters JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT saved_searches_user_query_key UNIQUE (user_id, query)
            )
            """
        )
    )
    db_session.execute(
        text("CREATE INDEX IF NOT EXISTS saved_searches_user_id_created_at_idx ON saved_searches (user_id, created_at)")
    )
    db_session.commit()


class TestSavedSearchesRoutes:
    def test_saved_searches_require_auth(self, client: TestClient):
        response = client.get("/users/me/saved-searches")
        assert response.status_code == 401

    def test_saved_searches_crud(self, client: TestClient, db_session):
        _ensure_saved_searches_table(db_session)
        user_id, session_token = _create_session_user(db_session)
        cookies = {"tc_session": session_token}

        create_response = client.post(
            "/users/me/saved-searches",
            json={"query": "creator archive", "filters": {"source": "best", "language": "en"}},
            cookies=cookies,
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["query"] == "creator archive"
        assert created["filters"]["source"] == "best"

        list_response = client.get("/users/me/saved-searches", cookies=cookies)
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert len(items) == 1
        assert items[0]["query"] == "creator archive"

        delete_response = client.delete(f"/users/me/saved-searches/{created['id']}", cookies=cookies)
        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is True

        final_response = client.get("/users/me/saved-searches", cookies=cookies)
        assert final_response.status_code == 200
        assert final_response.json()["items"] == []

        row_count = db_session.execute(text("SELECT COUNT(*) FROM saved_searches WHERE user_id = :uid"), {"uid": str(user_id)}).scalar_one()
        assert row_count == 0
