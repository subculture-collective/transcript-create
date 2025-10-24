"""Integration tests for job processing workflows."""

import time
import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestJobProcessingFlow:
    """Integration tests for job creation and processing."""

    @pytest.mark.timeout(60)
    def test_create_job_single_video(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test creating a single video job through the API."""
        # Create job via API
        response = integration_client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "kind": "single"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["kind"] == "single"
        assert data["state"] in ["pending", "expanded"]

        job_id = data["id"]

        # Verify job exists in database
        result = integration_db.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id})
        job = result.mappings().first()

        assert job is not None
        assert str(job["id"]) == job_id
        assert job["kind"] == "single"

    @pytest.mark.timeout(60)
    def test_get_job_status(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test retrieving job status through the API."""
        # Create job
        response = integration_client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=test123", "kind": "single"},
        )
        assert response.status_code == 200
        job_id = response.json()["id"]

        # Get job status
        response = integration_client.get(f"/jobs/{job_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == job_id
        assert data["kind"] == "single"
        assert "state" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.timeout(60)
    def test_get_nonexistent_job(self, integration_client: TestClient, clean_test_data):
        """Test retrieving a job that doesn't exist."""
        fake_id = str(uuid.uuid4())
        response = integration_client.get(f"/jobs/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.timeout(60)
    def test_create_job_channel(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test creating a channel job through the API."""
        response = integration_client.post(
            "/jobs",
            json={"url": "https://youtube.com/channel/UCtest123", "kind": "channel"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["kind"] == "channel"
        assert data["state"] == "pending"

    @pytest.mark.timeout(60)
    def test_create_job_invalid_url(self, integration_client: TestClient, clean_test_data):
        """Test creating a job with an invalid URL."""
        response = integration_client.post(
            "/jobs",
            json={"url": "not-a-valid-url", "kind": "single"},
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.timeout(60)
    def test_create_job_missing_url(self, integration_client: TestClient, clean_test_data):
        """Test creating a job without a URL."""
        response = integration_client.post(
            "/jobs",
            json={"kind": "single"},
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.timeout(60)
    def test_job_default_kind(self, integration_client: TestClient, clean_test_data):
        """Test that jobs default to 'single' kind when not specified."""
        response = integration_client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=test456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["kind"] == "single"


class TestConcurrentJobs:
    """Tests for concurrent job creation."""

    @pytest.mark.timeout(120)
    def test_concurrent_job_creation(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test creating multiple jobs concurrently."""
        job_urls = [f"https://youtube.com/watch?v=test{i}" for i in range(10)]

        # Create jobs concurrently (simulated by rapid sequential creation)
        job_ids = []
        for url in job_urls:
            response = integration_client.post(
                "/jobs",
                json={"url": url, "kind": "single"},
            )
            assert response.status_code == 200
            job_ids.append(response.json()["id"])

        # Verify all jobs exist in database
        result = integration_db.execute(text("SELECT COUNT(*) as count FROM jobs"))
        count = result.scalar()
        assert count == 10

        # Verify all jobs have unique IDs
        assert len(set(job_ids)) == 10


class TestJobErrorHandling:
    """Tests for job error handling."""

    @pytest.mark.timeout(60)
    def test_invalid_youtube_url_format(self, integration_client: TestClient, clean_test_data):
        """Test handling of invalid YouTube URL format."""
        invalid_urls = [
            "https://example.com/video",
            "not-a-url",
            "ftp://invalid-protocol.com",
            "",
        ]

        for url in invalid_urls:
            response = integration_client.post(
                "/jobs",
                json={"url": url, "kind": "single"},
            )
            # Should return validation error
            assert response.status_code in [400, 422]
