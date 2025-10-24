"""Tests for search routes."""

import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text


class TestSearchRoutes:
    """Tests for /search endpoint."""

    def test_search_missing_query(self, client: TestClient):
        """Test search without query parameter."""
        response = client.get("/search")
        assert response.status_code == 422  # Missing required parameter

    def test_search_empty_query(self, client: TestClient):
        """Test search with empty query string."""
        response = client.get("/search?q=")
        assert response.status_code == 400
        assert "Missing query parameter" in response.json()["detail"]

    def test_search_whitespace_query(self, client: TestClient):
        """Test search with whitespace-only query."""
        response = client.get("/search?q=%20%20%20")
        assert response.status_code == 400

    def test_search_invalid_source(self, client: TestClient):
        """Test search with invalid source parameter."""
        response = client.get("/search?q=test&source=invalid")
        assert response.status_code == 400
        assert "Invalid source" in response.json()["detail"]

    def test_search_invalid_limit_too_low(self, client: TestClient):
        """Test search with limit below minimum."""
        response = client.get("/search?q=test&limit=0")
        assert response.status_code == 400
        assert "limit must be between" in response.json()["detail"]

    def test_search_invalid_limit_too_high(self, client: TestClient):
        """Test search with limit above maximum."""
        response = client.get("/search?q=test&limit=300")
        assert response.status_code == 400
        assert "limit must be between" in response.json()["detail"]

    def test_search_native_source_success(self, client: TestClient):
        """Test search with native source (Postgres FTS)."""
        response = client.get("/search?q=test&source=native")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert isinstance(data["hits"], list)

    def test_search_youtube_source_success(self, client: TestClient):
        """Test search with youtube source."""
        response = client.get("/search?q=test&source=youtube")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert isinstance(data["hits"], list)

    def test_search_default_source(self, client: TestClient):
        """Test search with default source (native)."""
        response = client.get("/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

    def test_search_with_video_filter(self, client: TestClient):
        """Test search with video_id filter."""
        video_id = uuid.uuid4()
        response = client.get(f"/search?q=test&video_id={video_id}")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

    def test_search_with_pagination(self, client: TestClient):
        """Test search with pagination parameters."""
        response = client.get("/search?q=test&limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert len(data["hits"]) <= 10

    def test_search_returns_proper_structure(self, client: TestClient, db_session):
        """Test that search returns properly structured results."""
        # Create test data with searchable content
        job_response = client.post("/jobs", json={"url": "https://youtube.com/watch?v=testsearch"})
        job_id = job_response.json()["id"]

        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        db_session.execute(
            text("INSERT INTO videos (id, job_id, youtube_id, idx) VALUES (:id, :job_id, :yt_id, 0)"),
            {"id": str(video_id), "job_id": job_id, "yt_id": "search123"},
        )
        db_session.execute(
            text("INSERT INTO transcripts (id, video_id, model) VALUES (:id, :vid, 'base')"),
            {"id": str(transcript_id), "vid": str(video_id)},
        )
        db_session.execute(
            text(
                "INSERT INTO segments (video_id, start_ms, end_ms, text, speaker_label) "
                "VALUES (:vid, :start, :end, :text, :speaker)"
            ),
            {"vid": str(video_id), "start": 0, "end": 1000, "text": "searchable content here", "speaker": None},
        )
        db_session.commit()

        # Search for the content
        response = client.get("/search?q=searchable&source=native")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

        # If we found results, check structure
        if len(data["hits"]) > 0:
            hit = data["hits"][0]
            assert "id" in hit
            assert "video_id" in hit
            assert "start_ms" in hit
            assert "end_ms" in hit
            assert "snippet" in hit

    @patch("app.settings.settings.SEARCH_BACKEND", "opensearch")
    @patch("requests.post")
    def test_search_opensearch_backend(self, mock_post, client: TestClient):
        """Test search with OpenSearch backend (mocked)."""
        # Mock OpenSearch response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "id": 123,
                            "video_id": str(uuid.uuid4()),
                            "start_ms": 0,
                            "end_ms": 1000,
                            "text": "test content",
                        },
                        "highlight": {"text": ["<em>test</em> content"]},
                    }
                ],
            }
        }
        mock_post.return_value = mock_response

        response = client.get("/search?q=test&source=native")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

    @patch("app.settings.settings.SEARCH_BACKEND", "opensearch")
    @patch("requests.post")
    def test_search_opensearch_failure(self, mock_post, client: TestClient):
        """Test search when OpenSearch fails."""
        mock_post.side_effect = Exception("OpenSearch connection failed")

        response = client.get("/search?q=test")
        assert response.status_code == 500
        assert "OpenSearch query failed" in response.json()["detail"]

    def test_search_unauthenticated_allowed(self, client: TestClient):
        """Test that unauthenticated users can search (within limits)."""
        response = client.get("/search?q=test")
        # Should work for unauthenticated users
        assert response.status_code == 200

    def test_search_result_limit_respected(self, client: TestClient):
        """Test that the limit parameter is respected."""
        response = client.get("/search?q=test&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["hits"]) <= 3

    def test_search_with_complex_query(self, client: TestClient):
        """Test search with a complex query string."""
        response = client.get("/search?q=artificial+intelligence+machine+learning")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

    def test_search_special_characters(self, client: TestClient):
        """Test search with special characters."""
        # Test that special characters don't break the search
        response = client.get("/search?q=test%20%26%20data")
        assert response.status_code == 200

    def test_search_unicode_query(self, client: TestClient):
        """Test search with Unicode characters."""
        response = client.get("/search?q=café")
        assert response.status_code == 200
