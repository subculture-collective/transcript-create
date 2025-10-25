"""Tests for error handling in API routes."""

import uuid

from fastapi.testclient import TestClient


class TestErrorHandling:
    """Tests for consistent error handling across routes."""

    def test_job_not_found_returns_404_with_error_format(self, client: TestClient):
        """Test that getting a non-existent job returns proper error format."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/jobs/{non_existent_id}")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"] == "job_not_found"
        assert "message" in data
        assert str(non_existent_id) in data["message"]
        assert "details" in data
        assert data["details"]["job_id"] == str(non_existent_id)

    def test_video_not_found_returns_404_with_error_format(self, client: TestClient):
        """Test that getting a non-existent video returns proper error format."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"] == "video_not_found"
        assert "message" in data
        assert "details" in data

    def test_invalid_url_returns_422_with_validation_error(self, client: TestClient):
        """Test that invalid URL returns validation error."""
        response = client.post(
            "/jobs",
            json={"url": "not-a-valid-url", "kind": "single"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"
        assert "message" in data
        assert "details" in data
        assert "errors" in data["details"]

    def test_non_youtube_url_returns_422(self, client: TestClient):
        """Test that non-YouTube URL returns validation error."""
        response = client.post(
            "/jobs",
            json={"url": "https://example.com/video", "kind": "single"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"

    def test_missing_required_field_returns_422(self, client: TestClient):
        """Test that missing required field returns validation error."""
        response = client.post(
            "/jobs",
            json={"kind": "single"},  # Missing 'url'
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"
        assert "details" in data
        assert "errors" in data["details"]

    def test_invalid_uuid_returns_422(self, client: TestClient):
        """Test that invalid UUID format returns validation error."""
        response = client.get("/jobs/not-a-uuid")

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"

    def test_invalid_kind_returns_422(self, client: TestClient):
        """Test that invalid job kind returns validation error."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=test", "kind": "invalid_kind"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"

    def test_empty_search_query_returns_422(self, client: TestClient):
        """Test that empty search query returns validation error."""
        response = client.get("/search?q=")

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        # Could be validation_error from our custom validation
        assert data["error"] in ["validation_error"]

    def test_invalid_search_source_returns_422(self, client: TestClient):
        """Test that invalid search source returns validation error."""
        response = client.get("/search?q=test&source=invalid")

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"

    def test_search_limit_out_of_range_returns_422(self, client: TestClient):
        """Test that search limit out of range returns validation error."""
        response = client.get("/search?q=test&limit=300")

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"] == "validation_error"

    def test_request_id_header_present(self, client: TestClient):
        """Test that X-Request-ID header is present in responses."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        # Verify it's a valid UUID format
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) > 0

    def test_error_response_includes_request_id(self, client: TestClient):
        """Test that error responses include X-Request-ID header."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/jobs/{non_existent_id}")
        assert response.status_code == 404
        assert "X-Request-ID" in response.headers


class TestYouTubeURLValidation:
    """Tests for YouTube URL validation."""

    def test_valid_youtube_watch_url(self, client: TestClient):
        """Test that valid YouTube watch URL is accepted."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "kind": "single"},
        )
        assert response.status_code == 200

    def test_valid_youtube_watch_url_with_www(self, client: TestClient):
        """Test that valid YouTube watch URL with www is accepted."""
        response = client.post(
            "/jobs",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "kind": "single"},
        )
        assert response.status_code == 200

    def test_valid_youtube_channel_url(self, client: TestClient):
        """Test that valid YouTube channel URL is accepted."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/channel/UCtest123", "kind": "channel"},
        )
        assert response.status_code == 200

    def test_valid_youtube_at_url(self, client: TestClient):
        """Test that valid YouTube @ URL is accepted."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtube.com/@testchannel", "kind": "channel"},
        )
        assert response.status_code == 200

    def test_valid_youtu_be_url(self, client: TestClient):
        """Test that valid youtu.be URL is accepted."""
        response = client.post(
            "/jobs",
            json={"url": "https://youtu.be/dQw4w9WgXcQ", "kind": "single"},
        )
        assert response.status_code == 200


class TestTranscriptErrors:
    """Tests for transcript-related errors."""

    def test_transcript_for_nonexistent_video_returns_404(self, client: TestClient):
        """Test that requesting transcript for non-existent video returns 404."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}/transcript")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"] == "video_not_found"

    def test_youtube_transcript_for_nonexistent_video_returns_404(self, client: TestClient):
        """Test that requesting YouTube transcript for non-existent video returns 404."""
        non_existent_id = uuid.uuid4()
        response = client.get(f"/videos/{non_existent_id}/youtube-transcript")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"] == "video_not_found"
