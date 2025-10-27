"""Tests for search routes."""

import secrets
import uuid
from datetime import datetime, timedelta
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
        # FastAPI validates min_length at pydantic level, returns 422
        assert response.status_code == 422

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

    def test_search_with_filters(self, client: TestClient):
        """Test search with advanced filters."""
        response = client.get("/search?q=test&min_duration=60&max_duration=300&language=en&sort_by=date_desc")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert "query_time_ms" in data

    def test_search_with_speaker_filter(self, client: TestClient):
        """Test search with speaker labels filter."""
        response = client.get("/search?q=test&has_speaker_labels=true")
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data

    def test_search_invalid_sort_by(self, client: TestClient):
        """Test search with invalid sort_by parameter."""
        response = client.get("/search?q=test&sort_by=invalid")
        assert response.status_code == 400
        assert "Invalid sort_by" in response.json()["detail"]

    def test_search_query_time_tracking(self, client: TestClient):
        """Test that search returns query time."""
        response = client.get("/search?q=test")
        assert response.status_code == 200
        data = response.json()
        assert "query_time_ms" in data
        assert isinstance(data["query_time_ms"], int)


class TestSearchSuggestions:
    """Tests for /search/suggestions endpoint."""

    def test_suggestions_missing_query(self, client: TestClient):
        """Test suggestions without query parameter."""
        response = client.get("/search/suggestions")
        assert response.status_code == 422

    def test_suggestions_success(self, client: TestClient, db_session):
        """Test getting search suggestions."""
        # Insert some test suggestions
        db_session.execute(
            text("INSERT INTO search_suggestions (term, frequency) VALUES (:term, :freq)"),
            {"term": "artificial intelligence", "freq": 10},
        )
        db_session.commit()

        response = client.get("/search/suggestions?q=artif")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_suggestions_limit(self, client: TestClient):
        """Test suggestions limit parameter."""
        response = client.get("/search/suggestions?q=test&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) <= 5


class TestSearchHistory:
    """Tests for /search/history endpoint."""

    def test_history_unauthenticated(self, client: TestClient):
        """Test search history without authentication."""
        response = client.get("/search/history")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 0

    def test_history_with_data(self, client: TestClient, db_session):
        """Test search history with user data."""
        # Create a test user and search history
        user_id = uuid.uuid4()
        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject) "
                "VALUES (:id, :email, :provider, :subject)"
            ),
            {
                "id": str(user_id),
                "email": "test@example.com",
                "provider": "google",
                "subject": "test123",
            },
        )
        db_session.execute(
            text("INSERT INTO user_searches (user_id, query, result_count) VALUES (:uid, :query, :count)"),
            {"uid": str(user_id), "query": "test query", "count": 5},
        )
        db_session.commit()

        # Note: This test would need proper authentication setup to work fully
        response = client.get("/search/history")
        assert response.status_code == 200


class TestPopularSearches:
    """Tests for /search/popular endpoint."""

    def test_popular_searches_success(self, client: TestClient):
        """Test getting popular searches."""
        response = client.get("/search/popular")
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_popular_searches_limit(self, client: TestClient):
        """Test popular searches limit parameter."""
        response = client.get("/search/popular?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) <= 10


class TestSearchExport:
    """Tests for /search/export endpoint."""

    def test_export_csv_format(self, client: TestClient):
        """Test exporting search results as CSV."""
        response = client.get("/search/export?q=test&format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_json_format(self, client: TestClient):
        """Test exporting search results as JSON."""
        response = client.get("/search/export?q=test&format=json")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "query" in data
        assert "count" in data

    def test_export_invalid_format(self, client: TestClient):
        """Test export with invalid format."""
        response = client.get("/search/export?q=test&format=xml")
        assert response.status_code == 400
        assert "Invalid format" in response.json()["detail"]

    def test_export_with_filters(self, client: TestClient):
        """Test export with filters."""
        response = client.get("/search/export?q=test&format=json&min_duration=60&max_duration=300")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


class TestSearchAnalytics:
    """Tests for /admin/search/analytics endpoint."""

    def test_analytics_unauthenticated(self, client: TestClient):
        """Test analytics without authentication."""
        response = client.get("/admin/search/analytics")
        assert response.status_code == 403  # Not admin

    def test_analytics_non_admin(self, client: TestClient, db_session):
        """Test analytics with non-admin user."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'user')"
            ),
            {"id": str(user_id), "email": "user@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/admin/search/analytics", cookies={"tc_session": session_token})
        assert response.status_code == 403

    def test_analytics_admin_success(self, client: TestClient, db_session):
        """Test analytics with admin user."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'admin')"
            ),
            {"id": str(user_id), "email": "admin@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/admin/search/analytics?days=30", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        assert "popular_terms" in data
        assert "zero_result_searches" in data
        assert "search_volume" in data
        assert "avg_results_per_query" in data
        assert "total_searches" in data

    def test_analytics_avg_results_none_when_no_data(self, client: TestClient, db_session):
        """Test that avg_results_per_query is None when there's no search data."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'admin')"
            ),
            {"id": str(user_id), "email": "admin2@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        # Clear any existing user_searches data
        db_session.execute(text("DELETE FROM user_searches"))
        db_session.commit()

        response = client.get("/admin/search/analytics?days=30", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        # When there's no data, avg_results_per_query should be None, not 0
        assert data["avg_results_per_query"] is None
        assert data["total_searches"] == 0

    def test_analytics_avg_results_zero_vs_none(self, client: TestClient, db_session):
        """Test that avg_results_per_query correctly distinguishes between 0 and None."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'admin')"
            ),
            {"id": str(user_id), "email": "admin3@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )

        # Create a search with 0 results
        db_session.execute(
            text(
                "INSERT INTO user_searches (user_id, query, filters, result_count, query_time_ms) "
                "VALUES (:uid, 'test query', '{}', 0, 100)"
            ),
            {"uid": str(user_id)},
        )
        db_session.commit()

        response = client.get("/admin/search/analytics?days=30", cookies={"tc_session": session_token})
        assert response.status_code == 200
        data = response.json()
        # When there are searches with 0 results, avg should be 0.0, not None
        assert data["avg_results_per_query"] == 0.0
        assert data["total_searches"] >= 1

    def test_analytics_invalid_days_too_low(self, client: TestClient, db_session):
        """Test analytics with days parameter below minimum."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'admin')"
            ),
            {"id": str(user_id), "email": "admin4@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/admin/search/analytics?days=0", cookies={"tc_session": session_token})
        # FastAPI validation should reject this with 422
        assert response.status_code == 422

    def test_analytics_invalid_days_too_high(self, client: TestClient, db_session):
        """Test analytics with days parameter above maximum."""
        user_id = uuid.uuid4()
        session_token = secrets.token_urlsafe(32)

        db_session.execute(
            text(
                "INSERT INTO users (id, email, oauth_provider, oauth_subject, role) "
                "VALUES (:id, :email, 'google', 'test123', 'admin')"
            ),
            {"id": str(user_id), "email": "admin5@example.com"},
        )
        db_session.execute(
            text("INSERT INTO sessions (user_id, token, expires_at) VALUES (:uid, :token, :exp)"),
            {"uid": str(user_id), "token": session_token, "exp": datetime.utcnow() + timedelta(days=1)},
        )
        db_session.commit()

        response = client.get("/admin/search/analytics?days=1000", cookies={"tc_session": session_token})
        # FastAPI validation should reject this with 422
        assert response.status_code == 422
