"""Basic smoke tests to verify the application starts and core endpoints respond."""

from fastapi.testclient import TestClient


def test_app_imports():
    """Test that the app can be imported."""
    from app.main import app

    assert app is not None


def test_health_check(client: TestClient):
    """Test that the API is responsive (basic connectivity)."""
    # FastAPI auto-generates /openapi.json and /docs endpoints
    response = client.get("/docs")
    assert response.status_code in [200, 307]  # 200 for docs, 307 if redirected


def test_cors_configured(client: TestClient):
    """Test that CORS middleware is configured."""
    from app.main import app

    # Check middleware exists
    middlewares = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middlewares
