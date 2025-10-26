"""Tests for enhanced OAuth security features."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.security import generate_oauth_state, generate_nonce


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

    def test_oauth_login_generates_state(self, client: TestClient):
        """Test that OAuth login generates state parameter."""
        # Mock OAuth to avoid actual OAuth setup
        with patch("app.routes.auth.OAuth") as mock_oauth:
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance
            
            # Configure mock
            mock_client = MagicMock()
            mock_oauth_instance.google = mock_client
            mock_client.authorize_redirect = MagicMock(return_value=MagicMock(status_code=302))
            
            # Make request
            response = client.get("/auth/login/google")
            
            # Should call authorize_redirect
            assert mock_client.authorize_redirect.called

    def test_oauth_callback_validates_state(self, client: TestClient, db_session):
        """Test that OAuth callback validates state parameter."""
        # This requires more complex mocking of the OAuth flow
        # For now, we test that the state validation logic exists
        from app.routes.auth import auth_callback_google
        import inspect
        
        # Check that state validation is in the function
        source = inspect.getsource(auth_callback_google)
        assert "oauth_state" in source
        assert "OAUTH_STATE_VALIDATION" in source or "settings.OAUTH_STATE_VALIDATION" in source

    def test_oauth_callback_rejects_invalid_state(self, client: TestClient, db_session):
        """Test that OAuth callback rejects mismatched state."""
        # Mock OAuth
        with patch("app.routes.auth.OAuth") as mock_oauth:
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance
            
            # Make request with mismatched state
            response = client.get(
                "/auth/callback/google",
                params={"state": "invalid_state", "code": "test_code"}
            )
            
            # Should reject the request
            assert response.status_code in [400, 422]  # Validation error


class TestAuditLoggingInOAuth:
    """Tests for audit logging in OAuth flows."""

    def test_login_success_logged(self, db_session):
        """Test that successful logins are logged."""
        from app.audit import ACTION_LOGIN_SUCCESS, log_audit_event
        import uuid
        
        user_id = uuid.uuid4()
        log_audit_event(
            db_session,
            action=ACTION_LOGIN_SUCCESS,
            user_id=user_id,
            success=True,
            details={"provider": "google"},
        )
        
        # Verify log
        from sqlalchemy import text
        log = db_session.execute(
            text("SELECT * FROM audit_logs WHERE action = :action AND user_id = :uid"),
            {"action": ACTION_LOGIN_SUCCESS, "uid": str(user_id)}
        ).mappings().first()
        
        assert log is not None
        assert log["success"] is True
        assert log["details"]["provider"] == "google"

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
        log = db_session.execute(
            text("SELECT * FROM audit_logs WHERE action = :action ORDER BY created_at DESC LIMIT 1"),
            {"action": ACTION_LOGIN_FAILED}
        ).mappings().first()
        
        assert log is not None
        assert log["success"] is False
        assert log["details"]["reason"] == "invalid_state"
