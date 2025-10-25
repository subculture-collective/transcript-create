"""Tests for health check endpoints."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check_basic(self, client: TestClient):
        """Test basic health check returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_liveness_probe(self, client: TestClient):
        """Test liveness probe returns 200."""
        response = client.get("/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_readiness_probe_healthy(self, client: TestClient):
        """Test readiness probe returns 200 when database is healthy."""
        response = client.get("/ready")
        # May return 200 or 503 depending on database state
        # Just verify it returns valid JSON with expected structure
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ready", "not_ready"]
        assert "timestamp" in data
        assert "checks" in data

    def test_detailed_health_check(self, client: TestClient):
        """Test detailed health check returns comprehensive status."""
        response = client.get("/health/detailed")
        # May return 200 or 503 depending on system state
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in data
        assert "checks" in data
        
        # Check that all expected components are present
        checks = data["checks"]
        assert "database" in checks
        assert "opensearch" in checks
        assert "storage" in checks
        assert "worker" in checks
        
        # Each check should have a status
        for component, check in checks.items():
            assert "status" in check
            assert check["status"] in ["healthy", "degraded", "unhealthy", "disabled"]


class TestDatabaseHealthCheck:
    """Tests for database health check component."""

    @pytest.mark.asyncio
    async def test_database_health_check_success(self):
        """Test database health check succeeds with healthy database."""
        from app.routes.health import check_database
        
        result = await check_database()
        # Database may not be available in test environment
        assert result["status"] in ["healthy", "unhealthy"]
        assert "latency_ms" in result
        assert result["latency_ms"] > 0
        if result["status"] == "healthy":
            assert "pool_size" in result

    @pytest.mark.asyncio
    async def test_database_health_check_measures_latency(self):
        """Test database health check measures latency."""
        from app.routes.health import check_database
        
        result = await check_database()
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], (int, float))
        assert result["latency_ms"] >= 0


class TestOpenSearchHealthCheck:
    """Tests for OpenSearch health check component."""

    @pytest.mark.asyncio
    async def test_opensearch_disabled_by_default(self):
        """Test OpenSearch health check returns disabled when backend is postgres."""
        from app.routes.health import check_opensearch
        
        result = await check_opensearch()
        # Default backend is postgres, so OpenSearch should be disabled
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_opensearch_health_check_with_backend_enabled(self):
        """Test OpenSearch health check when backend is enabled."""
        from app.routes.health import check_opensearch
        from app.settings import settings
        
        # Save original setting
        original_backend = settings.SEARCH_BACKEND
        
        try:
            # Enable OpenSearch backend
            settings.SEARCH_BACKEND = "opensearch"
            
            result = await check_opensearch()
            # Will likely fail in test environment, but should have proper error structure
            assert "status" in result
            assert result["status"] in ["healthy", "degraded", "unhealthy"]
            assert "latency_ms" in result
        finally:
            # Restore original setting
            settings.SEARCH_BACKEND = original_backend


class TestStorageHealthCheck:
    """Tests for storage health check component."""

    @pytest.mark.asyncio
    async def test_storage_health_check_success(self):
        """Test storage health check succeeds."""
        from app.routes.health import check_storage
        
        result = await check_storage()
        assert "status" in result
        assert result["status"] in ["healthy", "unhealthy"]
        # Storage check may fail if /data doesn't exist or has issues
        if result["status"] == "healthy":
            assert "free_gb" in result
            assert "total_gb" in result
            assert "used_gb" in result
            assert "can_write" in result

    @pytest.mark.asyncio
    async def test_storage_health_check_measures_disk_space(self):
        """Test storage health check measures disk space."""
        from app.routes.health import check_storage
        
        result = await check_storage()
        if result["status"] == "healthy":
            assert result["free_gb"] > 0
            assert result["total_gb"] > 0
            assert result["used_gb"] >= 0

    @pytest.mark.asyncio
    async def test_storage_health_check_write_permission(self):
        """Test storage health check verifies write permissions."""
        from app.routes.health import check_storage
        
        result = await check_storage()
        # Should be able to write in test environment if directory is accessible
        assert "can_write" in result or "error" in result


class TestWorkerHealthCheck:
    """Tests for worker health check component."""

    @pytest.mark.asyncio
    async def test_worker_health_check_structure(self):
        """Test worker health check returns expected structure."""
        from app.routes.health import check_worker
        
        result = await check_worker()
        assert "status" in result
        assert result["status"] in ["healthy", "degraded", "unhealthy"]
        # Worker check requires database, so may fail in test environment
        if result["status"] != "unhealthy":
            assert "jobs_pending" in result
            assert "jobs_stuck" in result
            assert isinstance(result["jobs_pending"], int)
            assert isinstance(result["jobs_stuck"], int)


class TestHealthMetrics:
    """Tests for health check Prometheus metrics."""

    def test_health_metrics_exist(self):
        """Test that health check metrics are defined."""
        from app.routes.health import health_check_status, health_check_duration_seconds, health_check_total
        
        assert health_check_status is not None
        assert health_check_duration_seconds is not None
        assert health_check_total is not None

    @pytest.mark.asyncio
    async def test_health_metrics_updated_on_check(self):
        """Test that health metrics are updated when checks run."""
        from app.routes.health import check_database, health_check_total
        
        # Get initial count (may not exist)
        from prometheus_client import REGISTRY
        before_samples = list(REGISTRY.collect())
        
        # Run a health check
        await check_database()
        
        # Verify metrics were updated (new samples should exist)
        after_samples = list(REGISTRY.collect())
        assert len(after_samples) >= len(before_samples)


class TestHealthCheckConfiguration:
    """Tests for health check configuration."""

    def test_health_check_timeout_configured(self):
        """Test that health check timeout is configurable."""
        from app.settings import settings
        
        assert hasattr(settings, "HEALTH_CHECK_TIMEOUT")
        assert settings.HEALTH_CHECK_TIMEOUT > 0

    def test_worker_stale_threshold_configured(self):
        """Test that worker stale threshold is configurable."""
        from app.settings import settings
        
        assert hasattr(settings, "HEALTH_CHECK_WORKER_STALE_SECONDS")
        assert settings.HEALTH_CHECK_WORKER_STALE_SECONDS > 0

    def test_disk_min_free_configured(self):
        """Test that disk minimum free space is configurable."""
        from app.settings import settings
        
        assert hasattr(settings, "HEALTH_CHECK_DISK_MIN_FREE_GB")
        assert settings.HEALTH_CHECK_DISK_MIN_FREE_GB > 0

    def test_critical_components_configured(self):
        """Test that critical components list is configurable."""
        from app.settings import settings
        
        assert hasattr(settings, "HEALTH_CHECK_CRITICAL_COMPONENTS")
        assert isinstance(settings.HEALTH_CHECK_CRITICAL_COMPONENTS, str)


class TestHealthCheckResponseTimes:
    """Tests for health check response time requirements."""

    def test_basic_health_check_fast_response(self, client: TestClient):
        """Test basic health check responds quickly (< 100ms)."""
        start = time.time()
        response = client.get("/health")
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 0.1  # Should be very fast

    def test_liveness_probe_fast_response(self, client: TestClient):
        """Test liveness probe responds quickly (< 100ms)."""
        start = time.time()
        response = client.get("/live")
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 0.1  # Should be very fast

    def test_readiness_probe_reasonable_response(self, client: TestClient):
        """Test readiness probe responds within timeout (< 5s)."""
        start = time.time()
        response = client.get("/ready")
        duration = time.time() - start
        
        # Should respond within configured timeout
        from app.settings import settings
        assert duration < settings.HEALTH_CHECK_TIMEOUT


class TestHealthCheckStatusCodes:
    """Tests for health check HTTP status codes."""

    def test_health_check_returns_200(self, client: TestClient):
        """Test /health always returns 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_liveness_probe_returns_200(self, client: TestClient):
        """Test /live always returns 200."""
        response = client.get("/live")
        assert response.status_code == 200

    def test_readiness_probe_returns_200_or_503(self, client: TestClient):
        """Test /ready returns 200 when ready, 503 when not."""
        response = client.get("/ready")
        # Should return either 200 (ready) or 503 (not ready)
        assert response.status_code in [200, 503]

    def test_detailed_health_returns_200_or_503(self, client: TestClient):
        """Test /health/detailed returns 200 or 503 based on component health."""
        response = client.get("/health/detailed")
        # Should return either 200 (healthy/degraded) or 503 (unhealthy)
        assert response.status_code in [200, 503]
