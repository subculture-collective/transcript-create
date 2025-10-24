"""Tests for auth routes."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text


class TestAuthRoutes:
    """Tests for /auth endpoints."""

    def test_auth_me_unauthenticated(self, client: TestClient):
        """Test /auth/me endpoint without authentication."""
        response = client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["user"] is None

    def test_auth_me_authenticated(self, client: TestClient, db_session):
        """Test /auth/me endpoint with authenticated user."""
        # Create a test user and session
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, :name, 'google', 'test123', 'free')"
            ),
            {"id": str(user_id), "email": "test@example.com", "name": "Test User"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        # Make request with session cookie
        response = client.get("/auth/me", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert data["user"] is not None
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["name"] == "Test User"
        assert data["user"]["plan"] == "free"

    def test_auth_me_expired_session(self, client: TestClient, db_session):
        """Test /auth/me with expired session."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) " "VALUES (:id, :email, 'google', 'test')"
            ),
            {"id": str(user_id), "email": "test@example.com"},
        )
        # Create expired session
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() - timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/auth/me", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        # Should return no user for expired session
        assert data["user"] is None

    def test_auth_logout(self, client: TestClient, db_session):
        """Test logout endpoint."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) " "VALUES (:id, :email, 'google', 'test')"
            ),
            {"id": str(user_id), "email": "test@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        # Logout
        response = client.post("/auth/logout", cookies={"tc_session": session_token})
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify session is deleted
        result = db_session.execute(text("SELECT * FROM sessions WHERE token = :t"), {"t": session_token}).first()
        assert result is None

    def test_auth_logout_no_session(self, client: TestClient):
        """Test logout without a session."""
        response = client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    @patch("app.routes.auth.OAuth", None)
    def test_auth_login_google_no_oauth(self, client: TestClient):
        """Test Google login when OAuth is not available."""
        response = client.get("/auth/login/google")
        assert response.status_code == 501
        assert "Authlib not installed" in response.json()["detail"]

    @patch("app.routes.auth.OAuth", None)
    def test_auth_login_twitch_no_oauth(self, client: TestClient):
        """Test Twitch login when OAuth is not available."""
        response = client.get("/auth/login/twitch")
        assert response.status_code == 501

    @patch("app.routes.auth.OAuth")
    def test_auth_login_google_redirect(self, mock_oauth_class, client: TestClient):
        """Test Google login redirect (mocked)."""
        mock_oauth = MagicMock()
        mock_oauth_class.return_value = mock_oauth
        mock_google = MagicMock()
        mock_oauth.google = mock_google

        # Mock the authorize_redirect to return a redirect response
        from fastapi.responses import RedirectResponse

        mock_google.authorize_redirect.return_value = RedirectResponse(url="https://accounts.google.com/o/oauth2/auth")

        response = client.get("/auth/login/google", follow_redirects=False)
        # Should redirect to Google OAuth
        assert response.status_code in [307, 302, 200]  # Redirect or success

    @patch("app.routes.auth.OAuth")
    @patch("app.routes.auth._new_oauth")
    def test_auth_login_twitch_redirect(self, mock_new_oauth, mock_oauth_class, client: TestClient):
        """Test Twitch login redirect (mocked)."""
        mock_oauth = MagicMock()
        mock_new_oauth.return_value = mock_oauth
        mock_twitch = MagicMock()
        mock_oauth.twitch = mock_twitch

        from fastapi.responses import RedirectResponse

        mock_twitch.authorize_redirect.return_value = RedirectResponse(url="https://id.twitch.tv/oauth2/authorize")

        response = client.get("/auth/login/twitch", follow_redirects=False)
        assert response.status_code in [307, 302, 200]

    def test_auth_me_free_plan_search_limit(self, client: TestClient, db_session):
        """Test that free plan users see search limit information."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, plan) "
                "VALUES (:id, :email, 'google', 'test', 'free')"
            ),
            {"id": str(user_id), "email": "free@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/auth/me", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["plan"] == "free"
        assert "search_limit" in data["user"]
        assert data["user"]["search_limit"] is not None

    def test_auth_callback_missing_state(self, client: TestClient):
        """Test OAuth callback without state parameter."""
        # OAuth callbacks typically require state for CSRF protection
        # This test just ensures the endpoint exists and handles missing params
        response = client.get("/auth/callback/google")
        # Will likely fail due to missing OAuth token, but endpoint should exist
        assert response.status_code in [400, 401, 500, 501]

    def test_multiple_sessions_same_user(self, client: TestClient, db_session):
        """Test that a user can have multiple active sessions."""
        import secrets
        import uuid
        from datetime import datetime, timedelta

        user_id = uuid.uuid4()
        session_token1 = secrets.token_urlsafe(32)
        session_token2 = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) " "VALUES (:id, :email, 'google', 'test')"
            ),
            {"id": str(user_id), "email": "multi@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token1, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token2, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        # Both sessions should work
        response1 = client.get("/auth/me", cookies={"tc_session": session_token1})
        assert response1.status_code == 200
        assert response1.json()["user"]["email"] == "multi@example.com"

        response2 = client.get("/auth/me", cookies={"tc_session": session_token2})
        assert response2.status_code == 200
        assert response2.json()["user"]["email"] == "multi@example.com"
