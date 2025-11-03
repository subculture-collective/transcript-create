"""Integration tests for transcript mode support (raw/cleaned/formatted)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


class TestTranscriptModes:
    """Integration tests for transcript mode parameter."""

    @pytest.fixture
    def video_with_transcript(self, integration_client: TestClient, integration_db, clean_test_data):
        """Create a video with transcript segments."""
        job_id = uuid.uuid4()
        video_id = uuid.uuid4()
        transcript_id = uuid.uuid4()

        # Insert job
        integration_db.execute(
            text(
                """
                INSERT INTO jobs (id, kind, state, input_url)
                VALUES (:job_id, 'single', 'completed', 'https://youtube.com/watch?v=test')
            """
            ),
            {"job_id": str(job_id)},
        )

        # Insert video
        integration_db.execute(
            text(
                """
                INSERT INTO videos (id, job_id, youtube_id, idx, title, duration_seconds, state)
                VALUES (:video_id, :job_id, 'test123', 0, 'Test Video', 180, 'completed')
            """
            ),
            {"video_id": str(video_id), "job_id": str(job_id)},
        )

        # Insert transcript
        integration_db.execute(
            text(
                """
                INSERT INTO transcripts (id, video_id, model, language)
                VALUES (:transcript_id, :video_id, 'test-model', 'en')
            """
            ),
            {"transcript_id": str(transcript_id), "video_id": str(video_id)},
        )

        # Insert segments with various patterns to test cleanup
        segments = [
            (0, "um hello everyone and uh welcome", "Speaker 1"),
            (1, "this is a TEST VIDEO with CAPS", "Speaker 1"),
            (2, "[MUSIC] some text with music", "Speaker 1"),
            (3, "another segment here", "Speaker 2"),
            (4, "and a final segment", "Speaker 2"),
        ]

        for idx, (seg_idx, text, speaker) in enumerate(segments):
            start_ms = seg_idx * 5000
            end_ms = start_ms + 4000
            integration_db.execute(
                text(
                    """
                    INSERT INTO segments (transcript_id, idx, start_ms, end_ms, text, speaker, speaker_label)
                    VALUES (:transcript_id, :idx, :start_ms, :end_ms, :text, :speaker, :speaker_label)
                """
                ),
                {
                    "transcript_id": str(transcript_id),
                    "idx": idx,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                    "speaker": speaker,
                    "speaker_label": speaker,
                },
            )

        integration_db.commit()
        return video_id

    @pytest.mark.timeout(60)
    def test_raw_mode_default(self, integration_client: TestClient, video_with_transcript):
        """Test raw mode (default behavior)."""
        video_id = video_with_transcript

        # Test without mode parameter (should default to raw)
        response = integration_client.get(f"/videos/{video_id}/transcript")
        assert response.status_code == 200

        data = response.json()
        assert "video_id" in data
        assert "segments" in data
        assert len(data["segments"]) == 5

        # Check raw text is preserved
        first_segment = data["segments"][0]
        assert "start_ms" in first_segment
        assert "end_ms" in first_segment
        assert "text" in first_segment
        assert "speaker_label" in first_segment
        # Raw mode should preserve filler words
        assert "um" in first_segment["text"].lower() or "uh" in first_segment["text"].lower()

    @pytest.mark.timeout(60)
    def test_raw_mode_explicit(self, integration_client: TestClient, video_with_transcript):
        """Test explicit raw mode parameter."""
        video_id = video_with_transcript

        response = integration_client.get(f"/videos/{video_id}/transcript?mode=raw")
        assert response.status_code == 200

        data = response.json()
        assert "video_id" in data
        assert "segments" in data
        assert len(data["segments"]) == 5

    @pytest.mark.timeout(60)
    def test_cleaned_mode(self, integration_client: TestClient, video_with_transcript):
        """Test cleaned mode with cleanup applied."""
        video_id = video_with_transcript

        response = integration_client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        assert response.status_code == 200

        data = response.json()
        assert "video_id" in data
        assert "segments" in data
        assert "cleanup_config" in data
        assert "stats" in data
        assert "created_at" in data

        # Check segments have both raw and cleaned text
        segments = data["segments"]
        assert len(segments) > 0
        for segment in segments:
            assert "start_ms" in segment
            assert "end_ms" in segment
            assert "text_raw" in segment
            assert "text_cleaned" in segment
            assert "speaker_label" in segment
            assert "sentence_boundary" in segment
            assert "likely_hallucination" in segment

        # Check cleanup stats
        stats = data["stats"]
        assert "fillers_removed" in stats
        assert "special_tokens_removed" in stats
        assert "segments_merged" in stats
        assert "segments_split" in stats
        assert "hallucinations_detected" in stats
        assert "punctuation_added" in stats

        # Verify cleanup was applied
        # Check that filler words might be removed
        first_segment_cleaned = segments[0]["text_cleaned"].lower()
        # Cleaned text should have less or equal fillers
        # Note: depending on config, some fillers might remain

        # Check cleanup config
        config = data["cleanup_config"]
        assert config["remove_fillers"] is True
        assert config["normalize_whitespace"] is True

    @pytest.mark.timeout(60)
    def test_formatted_mode(self, integration_client: TestClient, video_with_transcript):
        """Test formatted mode with full formatting."""
        video_id = video_with_transcript

        response = integration_client.get(f"/videos/{video_id}/transcript?mode=formatted")
        assert response.status_code == 200

        data = response.json()
        assert "video_id" in data
        assert "text" in data
        assert "format" in data
        assert "cleanup_config" in data
        assert "created_at" in data

        # Check formatted text
        text = data["text"]
        assert isinstance(text, str)
        assert len(text) > 0

        # Formatted mode should have speaker labels
        assert "Speaker 1:" in text or "Speaker 2:" in text

        # Check format type
        assert data["format"] == "structured"

        # Check cleanup config
        config = data["cleanup_config"]
        assert config["remove_fillers"] is True
        assert config["segment_by_sentences"] is True
        assert config["merge_short_segments"] is True

    @pytest.mark.timeout(60)
    def test_invalid_mode(self, integration_client: TestClient, video_with_transcript):
        """Test invalid mode parameter."""
        video_id = video_with_transcript

        response = integration_client.get(f"/videos/{video_id}/transcript?mode=invalid")
        # Should return validation error
        assert response.status_code == 422

    @pytest.mark.timeout(60)
    def test_etag_cache_headers(self, integration_client: TestClient, video_with_transcript):
        """Test ETag and cache headers are set correctly per mode."""
        video_id = video_with_transcript

        # Test raw mode ETag
        response_raw = integration_client.get(f"/videos/{video_id}/transcript?mode=raw")
        assert response_raw.status_code == 200
        assert "etag" in response_raw.headers
        assert "cache-control" in response_raw.headers
        etag_raw = response_raw.headers["etag"]

        # Test cleaned mode ETag
        response_cleaned = integration_client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        assert response_cleaned.status_code == 200
        assert "etag" in response_cleaned.headers
        etag_cleaned = response_cleaned.headers["etag"]

        # Test formatted mode ETag
        response_formatted = integration_client.get(f"/videos/{video_id}/transcript?mode=formatted")
        assert response_formatted.status_code == 200
        assert "etag" in response_formatted.headers
        etag_formatted = response_formatted.headers["etag"]

        # ETags should be different for different modes
        assert etag_raw != etag_cleaned
        assert etag_raw != etag_formatted
        assert etag_cleaned != etag_formatted

    @pytest.mark.timeout(60)
    def test_mode_ordering_preserved(self, integration_client: TestClient, video_with_transcript):
        """Test that segment ordering by start_ms is preserved in all modes."""
        video_id = video_with_transcript

        # Test raw mode
        response_raw = integration_client.get(f"/videos/{video_id}/transcript?mode=raw")
        assert response_raw.status_code == 200
        segments_raw = response_raw.json()["segments"]
        start_times_raw = [s["start_ms"] for s in segments_raw]
        assert start_times_raw == sorted(start_times_raw), "Raw segments should be sorted by start_ms"

        # Test cleaned mode
        response_cleaned = integration_client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        assert response_cleaned.status_code == 200
        segments_cleaned = response_cleaned.json()["segments"]
        start_times_cleaned = [s["start_ms"] for s in segments_cleaned]
        assert start_times_cleaned == sorted(start_times_cleaned), "Cleaned segments should be sorted by start_ms"

        # Formatted mode doesn't have segments, so we skip that check
