"""Tests for security middleware including headers and rate limiting."""

import pytest
from fastapi.testclient import TestClient


class TestSecurityHeaders:
    """Tests for security header middleware."""

    def test_security_headers_present(self, client: TestClient):
        """Test that security headers are added to responses."""
        response = client.get("/health")

        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

        # Check CSP header exists
        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

        # Check Permissions-Policy
        assert "Permissions-Policy" in response.headers

    def test_server_header_removed(self, client: TestClient):
        """Test that server identification is removed."""
        response = client.get("/health")

        # Server header should not reveal FastAPI/Uvicorn version
        server_header = response.headers.get("server", "")
        # If server header exists, it shouldn't contain version info
        if server_header:
            assert "fastapi" not in server_header.lower()
            assert "uvicorn" not in server_header.lower()

    def test_request_id_header_added(self, client: TestClient):
        """Test that X-Request-ID header is added."""
        response = client.get("/health")

        # Check that X-Request-ID is present
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]

        # Should be a valid UUID format
        import uuid
        try:
            uuid.UUID(request_id)
        except ValueError:
            pytest.fail("X-Request-ID is not a valid UUID")


class TestRateLimiting:
    """Tests for rate limiting middleware."""

    def test_rate_limit_allows_normal_requests(self, client: TestClient):
        """Test that normal request rates are allowed."""
        # Make a few requests - should all succeed
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_health_endpoint_excluded(self, client: TestClient):
        """Test that health checks are excluded from rate limiting."""
        # Make many requests to health endpoint - should not be rate limited
        for _ in range(150):
            response = client.get("/health")
            assert response.status_code == 200

    def test_cors_headers_present(self, client: TestClient):
        """Test CORS headers are properly configured."""
        # Make an OPTIONS request (preflight)
        response = client.options(
            "/auth/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            }
        )

        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-credentials" in response.headers


class TestSessionMiddleware:
    """Tests for session middleware integration."""

    def test_oauth_state_session_storage(self, client: TestClient):
        """Test that OAuth state can be stored in session."""
        # This would require mocking OAuth flow
        # For now, verify that session middleware is configured
        # by checking that session cookies can be set

        from starlette.middleware.sessions import SessionMiddleware

        from app.main import app

        # Check that SessionMiddleware is in the middleware stack
        # user_middleware contains Middleware wrapper objects with a 'cls' attribute
        has_session_middleware = any(
            hasattr(middleware, "cls") and middleware.cls is SessionMiddleware
            for middleware in getattr(app, "user_middleware", [])
        )

        # Verify that SessionMiddleware is actually configured
        assert has_session_middleware, "SessionMiddleware should be in the middleware stack"

        # Note: This test is limited without running the full app
        # In integration tests, we would verify session functionality


class TestCORSConfiguration:
    """Tests for CORS configuration."""

    def test_cors_allowed_origin(self, client: TestClient):
        """Test that configured origins are allowed."""
        response = client.get(
            "/auth/me",
            headers={"Origin": "http://localhost:5173"}
        )

        # Should allow the request
        assert response.status_code in [200, 401]  # Auth may fail but CORS should pass

    def test_cors_disallowed_origin(self, client: TestClient):
        """Test that non-configured origins are blocked."""
        response = client.get(
            "/auth/me",
            headers={"Origin": "https://evil.com"}
        )

        # CORS should block this
        # FastAPI's CORSMiddleware may still return 200 but without CORS headers
        cors_header = response.headers.get("access-control-allow-origin")
        if cors_header:
            assert cors_header != "https://evil.com"

    def test_cors_methods_restricted(self, client: TestClient):
        """Test that only allowed HTTP methods are permitted."""
        # Make preflight request
        response = client.options(
            "/auth/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "TRACE",
            }
        )

        # TRACE should not be in allowed methods
        allowed_methods = response.headers.get("access-control-allow-methods", "")
        assert "TRACE" not in allowed_methods.upper()
