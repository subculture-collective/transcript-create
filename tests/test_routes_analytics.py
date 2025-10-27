"""Tests for admin analytics dashboard endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from unittest.mock import patch


def test_dashboard_metrics_unauthenticated(client: TestClient):
    """Test that unauthenticated users cannot access dashboard."""
    response = client.get("/admin/dashboard/metrics")
    assert response.status_code == 401


def test_jobs_over_time_chart_unauthenticated(client: TestClient):
    """Test jobs over time chart endpoint requires auth."""
    response = client.get(
        "/admin/dashboard/charts/jobs-over-time?period=daily&days=30"
    )
    assert response.status_code == 401


def test_job_status_breakdown_unauthenticated(client: TestClient):
    """Test job status breakdown endpoint requires auth."""
    response = client.get("/admin/dashboard/charts/job-status-breakdown")
    assert response.status_code == 401


def test_export_format_breakdown_unauthenticated(client: TestClient):
    """Test export format breakdown endpoint requires auth."""
    response = client.get(
        "/admin/dashboard/charts/export-format-breakdown?days=30"
    )
    assert response.status_code == 401


def test_search_analytics_unauthenticated(client: TestClient):
    """Test search analytics endpoint requires auth."""
    response = client.get("/admin/dashboard/search-analytics?days=30")
    assert response.status_code == 401


def test_system_health_unauthenticated(client: TestClient):
    """Test system health endpoint requires auth."""
    response = client.get("/admin/dashboard/system-health")
    assert response.status_code == 401


def test_all_endpoints_require_auth(client: TestClient):
    """Test that all dashboard endpoints require authentication."""
    endpoints = [
        "/admin/dashboard/metrics",
        "/admin/dashboard/charts/jobs-over-time",
        "/admin/dashboard/charts/job-status-breakdown",
        "/admin/dashboard/charts/export-format-breakdown",
        "/admin/dashboard/search-analytics",
        "/admin/dashboard/system-health",
    ]
    
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

