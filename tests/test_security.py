"""Tests for security features including RBAC, API keys, and audit logging."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.audit import ACTION_API_KEY_CREATED, ACTION_API_KEY_REVOKED
from app.security import ROLE_ADMIN, ROLE_PRO, ROLE_USER, generate_api_key, get_user_role, has_role


class TestRBAC:
    """Tests for Role-Based Access Control."""

    def test_get_user_role_unauthenticated(self):
        """Test role for unauthenticated user."""
        assert get_user_role(None) == ROLE_USER

    def test_get_user_role_regular_user(self):
        """Test role for regular user."""
        user = {"id": str(uuid.uuid4()), "plan": "free", "email": "user@example.com"}
        assert get_user_role(user) == ROLE_USER

    def test_get_user_role_pro_user(self):
        """Test role for pro plan user."""
        user = {"id": str(uuid.uuid4()), "plan": "pro", "email": "user@example.com"}
        assert get_user_role(user) == ROLE_PRO

    def test_has_role_hierarchy(self):
        """Test role hierarchy."""
        user = {"id": str(uuid.uuid4()), "plan": "free", "email": "user@example.com"}
        assert has_role(user, ROLE_USER) is True
        assert has_role(user, ROLE_PRO) is False
        assert has_role(user, ROLE_ADMIN) is False

        pro_user = {"id": str(uuid.uuid4()), "plan": "pro", "email": "pro@example.com"}
        assert has_role(pro_user, ROLE_USER) is True
        assert has_role(pro_user, ROLE_PRO) is True
        assert has_role(pro_user, ROLE_ADMIN) is False


class TestAPIKeyGeneration:
    """Tests for API key generation and verification."""

    def test_generate_api_key(self):
        """Test API key generation."""
        api_key, api_key_hash = generate_api_key()

        # Check format
        assert api_key.startswith("tc_")
        assert len(api_key) > 10

        # Check hash
        assert len(api_key_hash) == 64  # SHA-256 hex digest

        # Verify hash matches
        # SHA-256 is appropriate for hashing random API keys (not passwords)
        expected_hash = hashlib.sha256(api_key.encode()).hexdigest()  # nosec B324
        assert api_key_hash == expected_hash

    def test_generate_api_key_uniqueness(self):
        """Test that generated API keys are unique."""
        key1, hash1 = generate_api_key()
        key2, hash2 = generate_api_key()

        assert key1 != key2
        assert hash1 != hash2


class TestAPIKeyEndpoints:
    """Tests for API key management endpoints."""

    def test_list_api_keys_unauthenticated(self, client: TestClient):
        """Test listing API keys without authentication."""
        response = client.get("/api-keys")
        assert response.status_code == 401

    def test_list_api_keys_empty(self, client: TestClient, db_session):
        """Test listing API keys when none exist."""
        # Create user and session
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :name, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "test@example.com", "name": "Test User"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/api-keys", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_create_api_key(self, client: TestClient, db_session):
        """Test creating a new API key."""
        # Create user and session
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :name, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "test@example.com", "name": "Test User"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        # Create API key
        response = client.post(
            "/api-keys",
            json={"name": "Test Key", "expires_days": 30},
            cookies={"tc_session": session_token},
        )

        assert response.status_code == 201
        data = response.json()

        # Check response structure
        assert "api_key" in data
        assert "key" in data
        assert data["api_key"].startswith("tc_")
        assert data["key"]["name"] == "Test Key"
        assert data["key"]["key_prefix"].startswith("tc_")

        # Verify key was stored in database
        stored = (
            db_session.execute(text("SELECT * FROM api_keys WHERE user_id = :uid"), {"uid": str(user_id)})
            .mappings()
            .first()
        )

        assert stored is not None
        assert stored["name"] == "Test Key"

        # Verify audit log
        audit = (
            db_session.execute(
                text(
                    """
                    SELECT * FROM audit_logs
                    WHERE action = :action AND user_id = :uid
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"action": ACTION_API_KEY_CREATED, "uid": str(user_id)},
            )
            .mappings()
            .first()
        )

        assert audit is not None
        assert audit["success"] is True

    def test_revoke_api_key(self, client: TestClient, db_session):
        """Test revoking an API key."""
        # Create user and session
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)
        api_key, api_key_hash = generate_api_key()
        key_id = uuid.uuid4()

        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :name, 'google', 'test123')"
            ),
            {"id": str(user_id), "email": "test@example.com", "name": "Test User"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.execute(
            text(
                "INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix) "
                "VALUES (:id, :uid, :name, :hash, :prefix)"
            ),
            {
                "id": str(key_id),
                "uid": str(user_id),
                "name": "Test Key",
                "hash": api_key_hash,
                "prefix": api_key[:10] + "...",
            },
        )
        db_session.commit()

        # Revoke the key
        response = client.delete(
            f"/api-keys/{key_id}",
            cookies={"tc_session": session_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify key was revoked
        revoked = (
            db_session.execute(text("SELECT revoked_at FROM api_keys WHERE id = :id"), {"id": str(key_id)})
            .mappings()
            .first()
        )

        assert revoked is not None
        assert revoked["revoked_at"] is not None

        # Verify audit log
        audit = (
            db_session.execute(
                text(
                    """
                    SELECT * FROM audit_logs
                    WHERE action = :action AND user_id = :uid
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"action": ACTION_API_KEY_REVOKED, "uid": str(user_id)},
            )
            .mappings()
            .first()
        )

        assert audit is not None
        assert audit["success"] is True

    def test_revoke_api_key_unauthorized(self, client: TestClient, db_session):
        """Test revoking someone else's API key."""
        # Create two users
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)
        api_key, api_key_hash = generate_api_key()
        key_id = uuid.uuid4()

        # User 1 owns the key
        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :name, 'google', 'user1')"
            ),
            {"id": str(user1_id), "email": "user1@example.com", "name": "User 1"},
        )

        # User 2 tries to revoke it
        db_session.execute(
            text(
                "INSERT INTO users (id, email, name, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :name, 'google', 'user2')"
            ),
            {"id": str(user2_id), "email": "user2@example.com", "name": "User 2"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user2_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.execute(
            text(
                "INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix) "
                "VALUES (:id, :uid, :name, :hash, :prefix)"
            ),
            {
                "id": str(key_id),
                "uid": str(user1_id),  # Belongs to user1
                "name": "Test Key",
                "hash": api_key_hash,
                "prefix": api_key[:10] + "...",
            },
        )
        db_session.commit()

        # Try to revoke
        response = client.delete(
            f"/api-keys/{key_id}",
            cookies={"tc_session": session_token},
        )

        assert response.status_code == 403
        data = response.json()
        assert "permission" in data["message"].lower()


class TestSessionSecurity:
    """Tests for session security features."""

    def test_session_cookie_attributes(self, client: TestClient, db_session):
        """Test that session cookies have secure attributes."""
        # This test would need to inspect Set-Cookie headers
        # For now, we verify the logic in session.py
        from fastapi.responses import Response

        from app.common.session import set_session_cookie

        resp = Response()
        set_session_cookie(resp, "test_token")

        # Check that the cookie is set
        set_cookie_header = resp.headers.get("set-cookie", "")
        assert "tc_session" in set_cookie_header
        assert "HttpOnly" in set_cookie_header
        assert "SameSite=lax" in set_cookie_header


class TestAuditLogging:
    """Tests for audit logging functionality."""

    def test_audit_log_creation(self, db_session):
        """Test creating audit log entries."""
        from app.audit import log_audit_event

        user_id = uuid.uuid4()
        log_audit_event(
            db_session,
            action="test_action",
            user_id=user_id,
            success=True,
            details={"test": "data"},
        )

        # Verify log was created
        log = (
            db_session.execute(text("SELECT * FROM audit_logs WHERE user_id = :uid"), {"uid": str(user_id)})
            .mappings()
            .first()
        )

        assert log is not None
        assert log["action"] == "test_action"
        assert log["success"] is True
        assert log["details"]["test"] == "data"
