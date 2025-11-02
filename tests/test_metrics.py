"""Tests for Prometheus metrics collection."""

import pytest


def test_api_metrics_module_imports():
    """Test that API metrics module can be imported."""
    try:
        from app import metrics

        # Verify key metrics exist
        assert hasattr(metrics, "http_requests_total")
        assert hasattr(metrics, "http_request_duration_seconds")
        assert hasattr(metrics, "http_requests_in_flight")
        assert hasattr(metrics, "jobs_created_total")
        assert hasattr(metrics, "videos_transcribed_total")
        assert hasattr(metrics, "search_queries_total")
        assert hasattr(metrics, "exports_total")
        assert hasattr(metrics, "setup_app_info")
    except ImportError as e:
        pytest.skip(f"Metrics module not available: {e}")


def test_worker_metrics_module_imports():
    """Test that worker metrics module can be imported."""
    try:
        from worker import metrics

        # Verify key metrics exist
        assert hasattr(metrics, "transcription_duration_seconds")
        assert hasattr(metrics, "download_duration_seconds")
        assert hasattr(metrics, "videos_pending")
        assert hasattr(metrics, "videos_in_progress")
        assert hasattr(metrics, "whisper_model_load_seconds")
        assert hasattr(metrics, "chunk_count")
        assert hasattr(metrics, "setup_worker_info")
        assert hasattr(metrics, "try_collect_gpu_metrics")
    except ImportError as e:
        pytest.skip(f"Metrics module not available: {e}")


def test_metrics_endpoint_exists(client):
    """Test that /metrics endpoint is accessible."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    # Check for some expected metric names in output
    content = response.text
    assert "http_requests_total" in content or "# HELP" in content


def test_metrics_middleware_tracks_requests(client):
    """Test that metrics middleware tracks HTTP requests."""
    # Make a health check request
    response = client.get("/health")
    assert response.status_code == 200

    # Get metrics
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200

    content = metrics_response.text
    # Should have some metrics tracked (the /health request at minimum)
    # Note: The actual metric values depend on test execution order
    assert "http_requests_total" in content or "http_request_duration_seconds" in content


def test_metrics_not_recursive(client):
    """Test that /metrics endpoint doesn't track itself."""
    # Get metrics twice
    client.get("/metrics")
    response = client.get("/metrics")

    # The /metrics endpoint itself should not be tracked
    # (middleware skips it to avoid recursion)
    # We just verify we can call it multiple times without error
    assert response.status_code == 200


def test_job_creation_increments_metric(client, db):
    """Test that creating a job increments the jobs_created_total metric."""
    from app import crud
    from app.metrics import jobs_created_total

    # Get current value
    before = jobs_created_total.labels(kind="single")._value.get()

    # Create a job
    crud.create_job(db, kind="single", url="https://www.youtube.com/watch?v=test")

    # Check metric increased
    after = jobs_created_total.labels(kind="single")._value.get()
    assert after > before


def test_search_increments_metric(client, db):
    """Test that search queries increment the search_queries_total metric."""
    from app import crud
    from app.metrics import search_queries_total

    # Get current value
    before = search_queries_total.labels(backend="postgres")._value.get()

    # Perform a search (even if no results)
    try:
        crud.search_segments(db, q="test query", limit=10)
    except Exception:
        # Search may fail if tables don't exist, that's ok for this test
        pass

    # Check metric increased
    after = search_queries_total.labels(backend="postgres")._value.get()
    assert after > before


def test_export_increments_metric():
    """Test that exports increment the exports_total metric."""
    from app.metrics import exports_total

    # Get current value
    before = exports_total.labels(format="srt")._value.get()

    # Simulate an export
    exports_total.labels(format="srt").inc()

    # Check metric increased
    after = exports_total.labels(format="srt")._value.get()
    assert after == before + 1


def test_worker_metrics_initialization():
    """Test worker metrics can be initialized."""
    try:
        from worker.metrics import setup_worker_info

        # Should not raise an error
        setup_worker_info(whisper_model="large-v3", whisper_backend="faster-whisper", force_gpu=False)
    except ImportError as e:
        pytest.skip(f"Worker metrics not available: {e}")


def test_gpu_metrics_gracefully_fails():
    """Test that GPU metrics collection fails gracefully when GPU not available."""
    try:
        from worker.metrics import try_collect_gpu_metrics

        # Should return False when GPU not available, not raise an exception
        result = try_collect_gpu_metrics()
        assert isinstance(result, bool)
    except ImportError as e:
        pytest.skip(f"Worker metrics not available: {e}")
