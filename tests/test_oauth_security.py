"""Tests for enhanced OAuth security features."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from app.audit import write_audit_event
from app.auth.providers import exchange_and_normalize_profile, get_provider, normalize_profile, register_provider
from app.db import engine
from app.exceptions import ValidationError
from app.security import generate_nonce, generate_oauth_state
from app.settings import settings


class TestOAuthSecurity:
    """Tests for OAuth security enhancements."""

    def test_generate_oauth_state(self):
        """Test OAuth state generation."""
        state1 = generate_oauth_state()
        state2 = generate_oauth_state()

        # Should be unique
        assert state1 != state2

        # Should be URL-safe
        assert "/" not in state1
        assert "+" not in state1

        # Should be long enough for security
        assert len(state1) > 32

    def test_generate_nonce(self):
        """Test OAuth nonce generation."""
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()

        # Should be unique
        assert nonce1 != nonce2

        # Should be URL-safe
        assert "/" not in nonce1
        assert "+" not in nonce1

    def test_google_profile_uses_sub_as_subject(self):
        profile = normalize_profile(
            "google",
            {
                "sub": "g-123",
                "email": "a@example.com",
                "email_verified": True,
                "name": "A",
                "picture": "https://example.com/a.png",
            },
        )
        assert profile.provider == "google"
        assert profile.subject == "g-123"
        assert profile.email_verified is True

    def test_provider_profiles_require_subjects(self):
        for provider, data in (("google", {"email": "a@example.com"}), ("twitch", {"login": "tester"})):
            try:
                normalize_profile(provider, data)
            except ValidationError:
                pass
            else:
                raise AssertionError(f"{provider} accepted a missing subject")

    def test_google_parsed_id_token_userinfo_with_nonce_is_accepted(self):
        client = MagicMock()
        client.authorize_access_token = AsyncMock(
            return_value={
                "id_token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJnb29nbGUtaWQifQ.signature",
                "userinfo": {"sub": "google-id", "nonce": "nonce"},
            }
        )

        profile = asyncio.run(
            exchange_and_normalize_profile(client, get_provider("google"), MagicMock(), sha256(b"nonce").hexdigest())
        )

        assert profile.subject == "google-id"
        client.get.assert_not_called()

    def test_google_missing_parsed_nonce_bearing_profile_fails_closed(self):
        import pytest

        client = MagicMock()
        for token, error in (
            ({}, "Missing validated OAuth identity claims"),
            ({"userinfo": {"sub": "google-id", "nonce": "nonce"}}, "Missing ID token from OAuth provider"),
            ({"id_token": "id-token", "userinfo": {"sub": "google-id"}}, "Invalid OAuth nonce"),
        ):
            client.authorize_access_token = AsyncMock(return_value=token)
            with pytest.raises(ValidationError, match=error):
                asyncio.run(
                    exchange_and_normalize_profile(
                        client, get_provider("google"), MagicMock(), sha256(b"nonce").hexdigest()
                    )
                )
        client.get.assert_not_called()

    def test_twitch_requests_users_with_required_headers_and_rejects_non_success(self):
        provider = get_provider("twitch")
        client = MagicMock()
        client.authorize_access_token = AsyncMock(return_value={"access_token": "secret-token"})
        client.get = AsyncMock(return_value=MagicMock(status_code=401, json=lambda: {"data": []}))

        import pytest

        from app.exceptions import ExternalServiceError

        with pytest.raises(ExternalServiceError):
            asyncio.run(exchange_and_normalize_profile(client, provider, MagicMock(), "unused"))
        client.get.assert_awaited_once_with(
            "users",
            token={"access_token": "secret-token"},
            headers={"Client-ID": provider.client_id, "Authorization": "Bearer secret-token"},
        )

    def test_twitch_provider_registration_and_enabled_configuration(self):
        with (
            patch.object(settings, "OAUTH_TWITCH_CLIENT_ID", "client-id"),
            patch.object(settings, "OAUTH_TWITCH_CLIENT_SECRET", "client-secret"),
        ):
            provider = get_provider("twitch")
            oauth = MagicMock()
            assert provider.enabled
            register_provider(oauth, provider)
        oauth.register.assert_called_once_with(
            name="twitch",
            client_id="client-id",
            client_secret="client-secret",
            client_kwargs={"scope": "user:read:email", "token_endpoint_auth_method": "client_secret_post"},
            authorize_url="https://id.twitch.tv/oauth2/authorize",
            access_token_url="https://id.twitch.tv/oauth2/token",
            api_base_url="https://api.twitch.tv/helix/",
        )

    def test_sqlalchemy_hides_bound_parameters_in_engine_and_exception(self):
        assert engine.hide_parameters is True
        from sqlalchemy import create_engine

        sql_engine = create_engine("sqlite://", hide_parameters=True)
        sentinel = "SQL-PARAMETER-MUST-NOT-LEAK"
        try:
            with sql_engine.connect() as connection:
                connection.execute(text("SELECT :secret FROM missing_table"), {"secret": sentinel})
        except Exception as exc:
            assert sentinel not in str(exc)
            assert "[SQL parameters hidden due to hide_parameters=True]" in str(exc)
        else:
            raise AssertionError("expected SQLAlchemy execution failure")

    def test_oauth_login_stores_only_hashes_and_is_visible_to_an_independent_connection_before_redirect(
        self, client: TestClient, db_session, test_engine
    ):
        """The durable binding is hashed and visible before redirect construction."""
        state, nonce = "state-raw-security-test", "nonce-raw-security-test"
        from app.db import SessionLocal, get_db
        from app.main import app

        original_override = app.dependency_overrides[get_db]

        def committed_db():
            session = SessionLocal(bind=test_engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = committed_db
        # Mock OAuth to avoid actual OAuth setup
        try:
            with (
                patch("app.routes.auth.OAuth") as mock_oauth,
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "test-client"),
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "test-secret"),
                patch("app.routes.auth.generate_oauth_state", return_value=state),
                patch("app.routes.auth.generate_nonce", return_value=nonce),
            ):
                mock_oauth_instance = MagicMock()
                mock_oauth.return_value = mock_oauth_instance
                mock_client = MagicMock()
                mock_oauth_instance.google = mock_client

                def redirect_after_commit(*args, **kwargs):
                    with test_engine.connect() as independent_connection:
                        row = (
                            independent_connection.execute(
                                text("SELECT state_hash, nonce_hash FROM oauth_requests WHERE state_hash=:state"),
                                {"state": sha256(state.encode()).hexdigest()},
                            )
                            .mappings()
                            .one()
                        )
                    assert row["state_hash"] == sha256(state.encode()).hexdigest()
                    assert row["nonce_hash"] == sha256(nonce.encode()).hexdigest()
                    return RedirectResponse("https://accounts.example.invalid/authorize")

                mock_client.authorize_redirect = AsyncMock(side_effect=redirect_after_commit)
                response = client.get("/auth/login/google", follow_redirects=False)
                assert response.status_code == 307
                assert mock_client.authorize_redirect.called
                kwargs = mock_client.authorize_redirect.await_args.kwargs
                assert kwargs["state"] == state
                assert kwargs["nonce"] == nonce
        finally:
            app.dependency_overrides[get_db] = original_override
            with test_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM oauth_requests WHERE state_hash=:state"),
                    {"state": sha256(state.encode()).hexdigest()},
                )

    def test_oauth_login_cleans_expired_requests_with_new_binding(self, client: TestClient, db_session):
        db_session.execute(
            text("""INSERT INTO oauth_requests
            (state_hash, nonce_hash, provider, intent, expires_at)
            VALUES (:state, :nonce, 'google', 'login', now() - interval '1 minute')"""),
            {"state": "a" * 64, "nonce": "b" * 64},
        )
        with (
            patch("app.routes.auth.OAuth") as oauth,
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            oauth.return_value.google.authorize_redirect = AsyncMock(
                return_value=RedirectResponse("https://example.invalid")
            )
            assert client.get("/auth/login/google", follow_redirects=False).status_code == 307
        assert db_session.execute(text("SELECT count(*) FROM oauth_requests WHERE expires_at <= now()")).scalar() == 0

    def test_disabled_provider_returns_503(self, client: TestClient):
        with (
            patch("app.routes.auth.OAuth", MagicMock()),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", ""),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", ""),
        ):
            response = client.get("/auth/login/google")
        assert response.status_code == 503

    def test_oauth_initiation_failure_is_sanitized(self, client: TestClient, db_session, caplog):
        sentinel = "https://provider.invalid/authorize?state=RAW-STATE&nonce=RAW-NONCE"
        oauth = MagicMock()
        oauth.google.authorize_redirect = AsyncMock(side_effect=RuntimeError(sentinel))
        caplog.set_level(logging.ERROR)

        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/login/google")

        audit = db_session.execute(
            text("SELECT details FROM audit_logs WHERE action='login_failed' ORDER BY created_at DESC LIMIT 1")
        ).scalar()
        assert response.status_code == 503
        assert response.json()["details"]["code"] == "oauth_initiation_failed"
        assert sentinel not in response.text
        assert sentinel not in caplog.text
        assert sentinel not in str(audit)
        assert audit["reason"] == "provider_initiation_failed"

    @staticmethod
    def _binding(db_session, state, nonce, provider="google", intent="login", link_user_id=None, expired=False):
        db_session.execute(
            text("""INSERT INTO oauth_requests
            (state_hash, nonce_hash, provider, intent, link_user_id, expires_at)
            VALUES (:state, :nonce, :provider, :intent, :link_user_id, :expires_at)"""),
            {
                "state": sha256(state.encode()).hexdigest(),
                "nonce": sha256(nonce.encode()).hexdigest(),
                "provider": provider,
                "intent": intent,
                "link_user_id": str(link_user_id) if link_user_id else None,
                "expires_at": datetime.utcnow() + timedelta(minutes=-1 if expired else 10),
            },
        )

    @staticmethod
    def _google_oauth(token):
        oauth = MagicMock()
        oauth.google.authorize_access_token = AsyncMock(return_value=token)
        return oauth

    def test_oauth_callback_rejects_invalid_state(self, client: TestClient, db_session):
        """Test that OAuth callback rejects mismatched state."""
        # Mock OAuth
        with (
            patch("app.routes.auth.OAuth") as mock_oauth,
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "test-client"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "test-secret"),
        ):
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance

            # Make request with mismatched state
            response = client.get("/auth/callback/google", params={"state": "invalid_state", "code": "test_code"})

            # Should reject the request
            assert response.status_code == 422

    def test_oauth_state_database_failure_returns_sanitized_500(self, client: TestClient, db_session, monkeypatch):
        sentinel = "OAUTH-STATE-DB-DETAIL-MUST-NOT-LEAK"
        original_execute = db_session.execute

        def fail_state_consume(statement, *args, **kwargs):
            if "UPDATE oauth_requests SET consumed_at" in str(statement):
                raise RuntimeError(sentinel)
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db_session, "execute", fail_state_consume)
        with (
            patch("app.routes.auth.OAuth", MagicMock()),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/callback/google", params={"state": "state-that-must-not-leak"})
        assert response.status_code == 500
        assert response.json() == {"error": "database_error", "message": "Authentication state could not be verified"}
        assert sentinel not in response.text

    def test_oauth_callbacks_reject_missing_subject_for_both_providers(self, client: TestClient, db_session):
        self._binding(db_session, "google-missing-subject", "google-nonce")
        google = self._google_oauth({"id_token": "id-token", "userinfo": {"nonce": "google-nonce"}})
        with (
            patch("app.routes.auth.OAuth", return_value=google),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            assert client.get("/auth/callback/google", params={"state": "google-missing-subject"}).status_code == 422

        self._binding(db_session, "twitch-missing-subject", "unused", provider="twitch")
        twitch = MagicMock()
        twitch.twitch.authorize_access_token = AsyncMock(return_value={"access_token": "provider-access-token"})
        twitch.twitch.get = AsyncMock(
            return_value=MagicMock(status_code=200, json=lambda: {"data": [{"login": "tester"}]})
        )
        with (
            patch("app.routes.auth.OAuth", return_value=twitch),
            patch.object(settings, "OAUTH_TWITCH_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_TWITCH_CLIENT_SECRET", "secret"),
        ):
            assert client.get("/auth/callback/twitch", params={"state": "twitch-missing-subject"}).status_code == 422

    def test_oauth_callback_rejects_provider_mismatch_and_expiry(self, client: TestClient, db_session):
        for state, provider, expired in (("wrong-provider", "twitch", False), ("expired", "google", True)):
            self._binding(db_session, state, "nonce", provider=provider, expired=expired)
            with (
                patch("app.routes.auth.OAuth", MagicMock()),
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
            ):
                assert client.get("/auth/callback/google", params={"state": state}).status_code == 422

    def test_oauth_callback_rejects_replay_after_successful_exchange(self, client: TestClient, db_session):
        state, nonce = "successful-then-replayed", "nonce"
        self._binding(db_session, state, nonce)
        oauth = self._google_oauth({"id_token": "id-token", "userinfo": {"sub": "replay-subject", "nonce": nonce}})
        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            assert (
                client.get("/auth/callback/google", params={"state": state}, follow_redirects=False).status_code == 307
            )
            assert client.get("/auth/callback/google", params={"state": state}).status_code == 422
        assert oauth.google.authorize_access_token.await_count == 1

    def test_successful_callback_persists_identity_and_hashed_session_then_sets_cookie(
        self, client: TestClient, db_session
    ):
        state, nonce = "durable-login", "nonce"
        self._binding(db_session, state, nonce)
        oauth = self._google_oauth(
            {
                "id_token": "id-token",
                "userinfo": {
                    "sub": "durable-subject",
                    "email": "durable@example.com",
                    "nonce": nonce,
                },
            }
        )

        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/callback/google", params={"state": state}, follow_redirects=False)

        token = response.cookies.get("tc_session")
        identity = db_session.execute(text("""
            SELECT ui.subject, s.token_hash
            FROM user_identities ui JOIN sessions s ON s.user_id=ui.user_id
            WHERE ui.provider='google' AND ui.subject='durable-subject'
        """)).mappings().one()
        assert response.status_code == 307
        assert "HttpOnly" in response.headers["set-cookie"]
        assert token
        assert identity["token_hash"] == sha256(token.encode()).hexdigest()

    def test_link_collision_callback_redirects_without_creating_an_identity(self, client: TestClient, db_session):
        owner_id, linker_id = uuid.uuid4(), uuid.uuid4()
        session_token = "link-collision-session"
        for user_id, email, subject in (
            (owner_id, "owner@example.com", "owner"),
            (linker_id, "linker@example.com", "linker"),
        ):
            db_session.execute(
                text(
                    "INSERT INTO users (id, email, oauth_provider, oauth_subject) VALUES (:id, :email, 'twitch', :subject)"
                ),
                {"id": str(user_id), "email": email, "subject": subject},
            )
        db_session.execute(
            text("INSERT INTO user_identities (user_id, provider, subject) VALUES (:id, 'google', 'already-linked')"),
            {"id": str(owner_id)},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :token_hash, :expires)"),
            {
                "id": str(linker_id),
                "token_hash": sha256(session_token.encode()).hexdigest(),
                "expires": datetime.utcnow() + timedelta(hours=1),
            },
        )
        self._binding(db_session, "link-collision", "nonce", intent="link", link_user_id=linker_id)
        oauth = self._google_oauth({"id_token": "id-token", "userinfo": {"sub": "already-linked", "nonce": "nonce"}})

        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get(
                "/auth/callback/google",
                params={"state": "link-collision"},
                cookies={"tc_session": session_token},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"].endswith(
            "/account?error=identity_conflict&provider=google"
        )
        assert (
            db_session.execute(
                text("SELECT count(*) FROM user_identities WHERE user_id=:id AND provider='google'"),
                {"id": str(linker_id)},
            ).scalar_one()
            == 0
        )

    def test_merge_callback_combines_separate_provider_accounts_and_rotates_session(
        self, client: TestClient, db_session
    ):
        source_id, target_id = uuid.uuid4(), uuid.uuid4()
        old_token = "pre-merge-target-session"
        db_session.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, 'source@example.com', 'user')"),
            {"id": str(source_id)},
        )
        db_session.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, 'target@example.com', 'user')"),
            {"id": str(target_id)},
        )
        db_session.execute(
            text("INSERT INTO user_identities (user_id, provider, subject) VALUES (:id, 'google', 'merge-google')"),
            {"id": str(source_id)},
        )
        db_session.execute(
            text("INSERT INTO user_identities (user_id, provider, subject) VALUES (:id, 'twitch', 'merge-twitch')"),
            {"id": str(target_id)},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :hash, now() + interval '1 hour')"),
            {"id": str(target_id), "hash": sha256(old_token.encode()).hexdigest()},
        )
        self._binding(db_session, "merge-callback", "nonce", intent="merge", link_user_id=target_id)
        oauth = self._google_oauth(
            {"id_token": "id-token", "userinfo": {"sub": "merge-google", "nonce": "nonce"}}
        )

        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get(
                "/auth/callback/google",
                params={"state": "merge-callback"},
                cookies={"tc_session": old_token},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"].endswith("/account?merged=google")
        assert response.cookies.get("tc_session") not in {None, old_token}
        assert db_session.execute(
            text("SELECT count(*) FROM users WHERE id=:id"), {"id": str(source_id)}
        ).scalar_one() == 0
        assert db_session.execute(
            text("SELECT count(*) FROM user_identities WHERE user_id=:id"), {"id": str(target_id)}
        ).scalar_one() == 2
        assert db_session.execute(
            text("SELECT count(*) FROM sessions WHERE user_id=:id"), {"id": str(target_id)}
        ).scalar_one() == 1

    def test_successful_link_callback_persists_identity(self, client: TestClient, db_session):
        user_id, session_token = uuid.uuid4(), "successful-link-session"
        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) VALUES (:id, 'link@example.com', 'twitch', 'linker')"
            ),
            {"id": str(user_id)},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :token_hash, :expires)"),
            {
                "id": str(user_id),
                "token_hash": sha256(session_token.encode()).hexdigest(),
                "expires": datetime.utcnow() + timedelta(hours=1),
            },
        )
        self._binding(db_session, "successful-link", "nonce", intent="link", link_user_id=user_id)
        oauth = self._google_oauth({"id_token": "id-token", "userinfo": {"sub": "new-link", "nonce": "nonce"}})

        with (
            patch("app.routes.auth.OAuth", return_value=oauth),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get(
                "/auth/callback/google",
                params={"state": "successful-link"},
                cookies={"tc_session": session_token},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert response.headers["location"].endswith("/account?linked=google")
        assert (
            db_session.execute(
                text("SELECT user_id FROM user_identities WHERE provider='google' AND subject='new-link'")
            ).scalar_one()
            == user_id
        )

    def test_oauth_callback_rejects_link_for_different_user(self, client: TestClient, db_session):
        linked_user, current_user, token = uuid.uuid4(), uuid.uuid4(), "different-user-session"
        for user_id, subject in ((linked_user, "linked"), (current_user, "current")):
            db_session.execute(
                text(
                    "INSERT INTO users (id, email, oauth_provider, oauth_subject) VALUES (:id, :email, 'google', :subject)"
                ),
                {"id": str(user_id), "email": f"{subject}@example.com", "subject": subject},
            )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (:id, :token_hash, :expires)"),
            {
                "id": str(current_user),
                "token_hash": sha256(token.encode()).hexdigest(),
                "expires": datetime.utcnow() + timedelta(hours=1),
            },
        )
        self._binding(db_session, "link-mismatch", "nonce", intent="link", link_user_id=linked_user)
        with (
            patch("app.routes.auth.OAuth", MagicMock()),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            assert (
                client.get(
                    "/auth/callback/google", params={"state": "link-mismatch"}, cookies={"tc_session": token}
                ).status_code
                == 422
            )

    def test_oauth_request_consumption_is_visible_before_and_after_provider_failure(
        self, client: TestClient, db_session, test_engine
    ):
        state = "exchange-failure"
        state_hash = sha256(state.encode()).hexdigest()
        with test_engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO oauth_requests
                (state_hash, nonce_hash, provider, intent, expires_at)
                VALUES (:state, :nonce, 'google', 'login', now() + interval '10 minutes')"""),
                {"state": state_hash, "nonce": sha256(b"nonce").hexdigest()},
            )
        with test_engine.connect() as independent_connection:
            assert (
                independent_connection.execute(
                    text("SELECT consumed_at FROM oauth_requests WHERE state_hash=:state"), {"state": state_hash}
                ).scalar()
                is None
            )

        from app.db import SessionLocal, get_db
        from app.main import app

        original_override = app.dependency_overrides[get_db]

        def committed_db():
            session = SessionLocal(bind=test_engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = committed_db
        oauth = self._google_oauth({})
        oauth.google.authorize_access_token.side_effect = RuntimeError("provider unavailable")
        try:
            with (
                patch("app.routes.auth.OAuth", return_value=oauth),
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
                patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
            ):
                assert client.get("/auth/callback/google", params={"state": state}).status_code == 503
            assert oauth.google.authorize_access_token.await_count == 1
            with test_engine.connect() as independent_connection:
                assert (
                    independent_connection.execute(
                        text("SELECT consumed_at FROM oauth_requests WHERE state_hash=:state"), {"state": state_hash}
                    ).scalar()
                    is not None
                )
        finally:
            app.dependency_overrides[get_db] = original_override
            with test_engine.begin() as connection:
                connection.execute(text("DELETE FROM oauth_requests WHERE state_hash=:state"), {"state": state_hash})

    def test_google_rejects_nonce_mismatch_and_twitch_allows_no_nonce_claim(self, client: TestClient, db_session):
        self._binding(db_session, "bad-nonce", "expected")
        google = self._google_oauth({"id_token": "id-token", "userinfo": {"sub": "google-subject", "nonce": "wrong"}})
        with (
            patch("app.routes.auth.OAuth", return_value=google),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            assert client.get("/auth/callback/google", params={"state": "bad-nonce"}).status_code == 422

        self._binding(db_session, "twitch-no-nonce", "unused", provider="twitch")
        twitch = MagicMock()
        twitch.twitch.authorize_access_token = AsyncMock(return_value={"access_token": "provider-access-token"})
        twitch.twitch.get = AsyncMock(
            return_value=MagicMock(
                status_code=200, json=lambda: {"data": [{"id": "twitch-subject", "login": "tester"}]}
            )
        )
        with (
            patch("app.routes.auth.OAuth", return_value=twitch),
            patch.object(settings, "OAUTH_TWITCH_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_TWITCH_CLIENT_SECRET", "secret"),
        ):
            assert (
                client.get(
                    "/auth/callback/twitch", params={"state": "twitch-no-nonce"}, follow_redirects=False
                ).status_code
                == 307
            )

    def test_session_insert_failure_is_sanitized_without_token_leak(
        self, client: TestClient, db_session, caplog, monkeypatch
    ):
        sentinel = "SESSION-TOKEN-MUST-NOT-LEAK"
        self._binding(db_session, "session-write-failure", "nonce")
        google = self._google_oauth({"id_token": "id-token", "userinfo": {"sub": "session-failure", "nonce": "nonce"}})
        original_execute = db_session.execute

        def fail_session_insert(statement, *args, **kwargs):
            if "INSERT INTO sessions" in str(statement):
                raise StatementError(
                    "session insert failed", str(statement), {"token": sentinel}, RuntimeError("db failure")
                )
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db_session, "execute", fail_session_insert)
        caplog.set_level(logging.ERROR)
        with (
            patch("app.routes.auth.OAuth", return_value=google),
            patch("app.accounts.secrets.token_urlsafe", return_value=sentinel),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_ID", "id"),
            patch.object(settings, "OAUTH_GOOGLE_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/callback/google", params={"state": "session-write-failure"})
        audit = original_execute(
            text("SELECT details FROM audit_logs WHERE action='login_failed' ORDER BY created_at DESC LIMIT 1")
        ).scalar()
        assert response.status_code == 500
        assert response.json()["error"] == "database_error"
        assert sentinel not in response.text
        assert sentinel not in caplog.text
        assert sentinel not in str(audit)


class TestAuditLoggingInOAuth:
    """Tests for audit logging in OAuth flows."""

    def test_login_success_logged(self, db_session, test_engine):
        """Test that successful logins are logged."""
        import uuid

        from app.audit import ACTION_LOGIN_SUCCESS, log_audit_event

        user_id = uuid.uuid4()
        # log_audit_event deliberately uses a separate transaction, so its
        # referenced user must be visible before it is called.
        with test_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                    "VALUES (:id, :email, 'google', :subject)"
                ),
                {"id": user_id, "email": f"audit-{user_id}@example.com", "subject": f"audit-{user_id}"},
            )
        log_audit_event(
            db_session,
            action=ACTION_LOGIN_SUCCESS,
            user_id=user_id,
            success=True,
            details={"provider": "google"},
        )

        # Verify log
        with test_engine.connect() as connection:
            log = (
                connection.execute(
                    text("SELECT * FROM audit_logs WHERE action = :action AND user_id = :uid"),
                    {"action": ACTION_LOGIN_SUCCESS, "uid": str(user_id)},
                )
                .mappings()
                .one()
            )

        assert log is not None
        assert log["success"] is True
        assert log["details"]["provider"] == "google"
        with test_engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": str(user_id)})

    def test_login_failure_logged(self, db_session):
        """Test that failed logins are logged."""
        from app.audit import ACTION_LOGIN_FAILED, log_audit_event

        log_audit_event(
            db_session,
            action=ACTION_LOGIN_FAILED,
            success=False,
            details={"provider": "twitch", "reason": "invalid_state"},
        )

        # Verify log
        from sqlalchemy import text

        log = (
            db_session.execute(
                text("SELECT * FROM audit_logs WHERE action = :action ORDER BY created_at DESC LIMIT 1"),
                {"action": ACTION_LOGIN_FAILED},
            )
            .mappings()
            .first()
        )

        assert log is not None
        assert log["success"] is False
        assert log["details"]["reason"] == "invalid_state"

    def test_write_audit_event_uses_callers_transaction(self):
        db = MagicMock()

        write_audit_event(db, action="login_success", details={"provider": "google"})

        db.execute.assert_called_once()
        db.commit.assert_not_called()
        db.rollback.assert_not_called()
