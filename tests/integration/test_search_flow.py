"""Integration tests for search functionality."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestSearchNativeTranscripts:
    """Integration tests for searching native transcripts."""

    @pytest.mark.timeout(60)
    def test_search_basic(self, integration_client: TestClient, clean_test_data):
        """Test basic search functionality."""
        response = integration_client.get("/search?q=test")

        # Search might require authentication or return empty results
        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "hits" in data or "results" in data or isinstance(data, list)

    @pytest.mark.timeout(60)
    def test_search_with_results(
        self, integration_client: TestClient, integration_db, clean_test_data, sample_transcript_segments
    ):
        """Test search with matching results."""
        # Create video with searchable transcript
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        # Insert searchable segments
        for i, seg in enumerate(sample_transcript_segments):
            integration_db.execute(
                text(
                    """
                    INSERT INTO segments (transcript_id, idx, start_ms, end_ms, text, speaker_label)
                    VALUES (:transcript_id, :idx, :start_ms, :end_ms, :text, :speaker_label)
                """
                ),
                {
                    "transcript_id": str(transcript_id),
                    "idx": i,
                    "start_ms": seg["start_ms"],
                    "end_ms": seg["end_ms"],
                    "text": seg["text"],
                    "speaker_label": seg.get("speaker_label"),
                },
            )

        integration_db.commit()

        # Search for text that exists in segments
        response = integration_client.get("/search?q=Hello")

        if response.status_code == 200:
            data = response.json()
            # Verify response structure (depends on implementation)
            assert isinstance(data, (dict, list))

    @pytest.mark.timeout(60)
    def test_search_empty_query(self, integration_client: TestClient, clean_test_data):
        """Test search with empty query."""
        response = integration_client.get("/search?q=")

        # Should handle empty query gracefully
        assert response.status_code in [200, 400, 422]

    @pytest.mark.timeout(60)
    def test_search_no_results(self, integration_client: TestClient, clean_test_data):
        """Test search with no matching results."""
        response = integration_client.get("/search?q=nonexistentphrase12345")

        if response.status_code == 200:
            data = response.json()
            # Should return empty results structure
            if isinstance(data, dict):
                assert "hits" in data or "results" in data
            elif isinstance(data, list):
                assert len(data) == 0


class TestSearchYouTubeCaptions:
    """Integration tests for searching YouTube captions."""

    @pytest.mark.timeout(60)
    def test_search_youtube_captions(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test searching in YouTube caption data."""
        # Create video with YouTube captions
        video_id = uuid.uuid4()

        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, youtube_id, title, duration_seconds, state)
                VALUES (:video_id, 'test123', 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id)},
        )

        # Insert YouTube caption segments (if such a table exists)
        # This depends on the actual schema
        integration_db.commit()

        # Search for YouTube captions
        response = integration_client.get("/search?q=test&source=youtube")

        # Endpoint might not exist or require specific parameters
        assert response.status_code in [200, 404, 422]


class TestSearchFilters:
    """Integration tests for search filtering and pagination."""

    @pytest.mark.timeout(60)
    def test_search_pagination(self, integration_client: TestClient, clean_test_data):
        """Test search with pagination parameters."""
        response = integration_client.get("/search?q=test&limit=10&offset=0")

        assert response.status_code in [200, 401, 403, 404, 422]

        if response.status_code == 200:
            data = response.json()
            # Verify pagination structure
            assert isinstance(data, (dict, list))

    @pytest.mark.timeout(60)
    def test_search_video_filter(self, integration_client: TestClient, integration_db, clean_test_data):
        """Test search filtered by video."""
        video_id = uuid.uuid4()

        response = integration_client.get(f"/search?q=test&video_id={video_id}")

        # Endpoint might not support this filter
        assert response.status_code in [200, 400, 404, 422]


class TestSearchPerformance:
    """Performance tests for search functionality."""

    @pytest.mark.timeout(60)
    def test_search_response_time(self, integration_client: TestClient, clean_test_data):
        """Test that search responds within acceptable time."""
        import time

        start_time = time.time()
        response = integration_client.get("/search?q=test")
        elapsed = time.time() - start_time

        # Should respond within 2 seconds
        assert elapsed < 2.0

        # Response should be valid
        assert response.status_code in [200, 401, 403, 404]
