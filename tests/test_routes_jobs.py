"""Tests for job routes."""

import uuid

import pytest
from fastapi.testclient import TestClient


class TestJobsRoutes:
    """Tests for /jobs endpoints."""

    def test_create_job_single_success(self, client: TestClient):
        """Test creating a single video job successfully."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "kind": "single"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["kind"] == "single"
        assert data["state"] in ["pending", "expanded"]

    def test_create_job_channel_success(self, client: TestClient):
        """Test creating a channel job successfully."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/channel/UCtest123", "kind": "channel"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "channel"

    def test_create_job_default_kind(self, client: TestClient):
        """Test creating a job with default kind (single)."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=test456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "single"

    def test_create_job_invalid_url(self, client: TestClient):
        """Test creating a job with an invalid URL."""
        response = client.post(
            "/jobs",
            json={"url": "not-a-valid-url", "kind": "single"},
        )
        assert response.status_code == 422  # Validation error

    def test_create_job_missing_url(self, client: TestClient):
        """Test creating a job without a URL."""
        response = client.post(
            "/jobs",
            json={"kind": "single"},
        )
        assert response.status_code == 422  # Validation error

    def test_get_job_success(self, client: TestClient):
        """Test getting a job by ID successfully."""
        # First create a job
        create_response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=test789", "kind": "single"},
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]

        # Then fetch it
        get_response = client.get(f"/jobs/{job_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == job_id
        assert data["kind"] == "single"
        assert "state" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_job_not_found(self, client: TestClient):
        """Test getting a non-existent job."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/jobs/{non_existent_id}")
        assert response.status_code == 404

    def test_get_job_invalid_uuid(self, client: TestClient):
        """Test getting a job with an invalid UUID."""
        response = client.get("/jobs/not-a-uuid")
        assert response.status_code == 422  # Validation error

    def test_job_has_required_fields(self, client: TestClient):
        """Test that a created job has all required fields."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=testfields", "kind": "single"},
        )
        assert response.status_code == 200
        data = response.json()

        # Check all required fields from JobStatus schema
        required_fields = ["id", "kind", "state", "created_at", "updated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_job_error_field_nullable(self, client: TestClient):
        """Test that the error field is nullable for successful jobs."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=testerror", "kind": "single"},
        )
        assert response.status_code == 200
        data = response.json()
        # Error field should be null or not present for new jobs
        assert data.get("error") is None or "error" not in data

    def test_multiple_jobs_different_urls(self, client: TestClient):
        """Test creating multiple jobs with different URLs."""
        urls = [
            "https://youtube.com/watch?v=test1",
            "https://youtube.com/watch?v=test2",
            "https://youtube.com/watch?v=test3",
        ]
        job_ids = []

        for url in urls:
            response = client.post("/jobs", json={"url": url, "kind": "single"})
            assert response.status_code == 200
            job_ids.append(response.json()["id"])

        # All job IDs should be unique
        assert len(job_ids) == len(set(job_ids))
