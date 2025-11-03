"""
E2E tests for API transcript modes (raw/cleaned/formatted).

Tests cover:
- GET /videos/{id}/transcript?mode=raw
- GET /videos/{id}/transcript?mode=cleaned with stats validation
- GET /videos/{id}/transcript?mode=formatted with paragraph structure
- Caching headers (ETag per mode)
- Error responses (404, 503)
"""

import uuid
import pytest
from sqlalchemy import text


@pytest.fixture
def setup_test_video(db_session):
    """Create a test video with transcript segments."""
    video_id = uuid.uuid4()
    youtube_id = "test_video_123"
    
    # Insert test video
    db_session.execute(
        text("""
            INSERT INTO videos (id, youtube_id, title, duration_seconds, status, job_id)
            VALUES (:id, :youtube_id, :title, :duration, 'completed', :job_id)
        """),
        {
            "id": video_id,
            "youtube_id": youtube_id,
            "title": "Test Video",
            "duration": 120,
            "job_id": uuid.uuid4(),
        }
    )
    
    # Insert test transcript
    transcript_id = uuid.uuid4()
    db_session.execute(
        text("""
            INSERT INTO transcripts (id, video_id, model, backend, language)
            VALUES (:id, :video_id, :model, :backend, :language)
        """),
        {
            "id": transcript_id,
            "video_id": video_id,
            "model": "base",
            "backend": "faster-whisper",
            "language": "en",
        }
    )
    
    # Insert test segments
    segments_data = [
        (0, 2000, "um hello world", None),
        (2000, 4000, "this is like a test", None),
        (4000, 6000, "TESTING ALL CAPS", None),
        (6000, 8000, "[MUSIC] some music here [MUSIC]", None),
    ]
    
    for start, end, text, speaker in segments_data:
        db_session.execute(
            text("""
                INSERT INTO segments (id, transcript_id, start_ms, end_ms, text, speaker_label)
                VALUES (:id, :transcript_id, :start_ms, :end_ms, :text, :speaker_label)
            """),
            {
                "id": uuid.uuid4(),
                "transcript_id": transcript_id,
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "speaker_label": speaker,
            }
        )
    
    db_session.commit()
    
    return video_id


@pytest.fixture
def setup_test_video_with_speakers(db_session):
    """Create a test video with speaker labels."""
    video_id = uuid.uuid4()
    
    db_session.execute(
        text("""
            INSERT INTO videos (id, youtube_id, title, duration_seconds, status, job_id)
            VALUES (:id, :youtube_id, :title, :duration, 'completed', :job_id)
        """),
        {
            "id": video_id,
            "youtube_id": "test_speakers_456",
            "title": "Test Video with Speakers",
            "duration": 60,
            "job_id": uuid.uuid4(),
        }
    )
    
    transcript_id = uuid.uuid4()
    db_session.execute(
        text("""
            INSERT INTO transcripts (id, video_id, model, backend, language)
            VALUES (:id, :video_id, :model, :backend, :language)
        """),
        {
            "id": transcript_id,
            "video_id": video_id,
            "model": "base",
            "backend": "faster-whisper",
            "language": "en",
        }
    )
    
    # Segments with speaker labels
    segments_data = [
        (0, 2000, "Hello everyone", "Speaker 1"),
        (2000, 4000, "Nice to meet you", "Speaker 2"),
        (4000, 6000, "How are you", "Speaker 1"),
    ]
    
    for start, end, text, speaker in segments_data:
        db_session.execute(
            text("""
                INSERT INTO segments (id, transcript_id, start_ms, end_ms, text, speaker_label)
                VALUES (:id, :transcript_id, :start_ms, :end_ms, :text, :speaker_label)
            """),
            {
                "id": uuid.uuid4(),
                "transcript_id": transcript_id,
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "speaker_label": speaker,
            }
        )
    
    db_session.commit()
    
    return video_id


class TestRawMode:
    """Tests for raw transcript mode."""

    def test_raw_mode_returns_unprocessed_segments(self, client, setup_test_video):
        """Test that raw mode returns segments without any processing."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "video_id" in data
        assert "segments" in data
        assert len(data["segments"]) == 4
        
        # Check first segment is unprocessed
        first_seg = data["segments"][0]
        assert first_seg["text"] == "um hello world"
        assert first_seg["start_ms"] == 0
        assert first_seg["end_ms"] == 2000

    def test_raw_mode_preserves_fillers(self, client, setup_test_video):
        """Test that raw mode preserves filler words."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        data = response.json()
        
        # Check that fillers are present
        texts = [seg["text"] for seg in data["segments"]]
        assert any("um" in text for text in texts)
        assert any("like" in text for text in texts)

    def test_raw_mode_preserves_special_tokens(self, client, setup_test_video):
        """Test that raw mode preserves special tokens."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        data = response.json()
        
        # Check that special tokens are present
        texts = [seg["text"] for seg in data["segments"]]
        assert any("[MUSIC]" in text for text in texts)

    def test_raw_mode_preserves_all_caps(self, client, setup_test_video):
        """Test that raw mode preserves all-caps text."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        data = response.json()
        
        # Find all caps segment
        texts = [seg["text"] for seg in data["segments"]]
        assert any("TESTING ALL CAPS" == text for text in texts)


class TestCleanedMode:
    """Tests for cleaned transcript mode."""

    def test_cleaned_mode_returns_cleanup_config(self, client, setup_test_video):
        """Test that cleaned mode returns cleanup configuration."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "cleanup_config" in data
        config = data["cleanup_config"]
        
        # Verify config keys
        assert "normalize_unicode" in config
        assert "remove_fillers" in config
        assert "filler_level" in config
        assert "add_punctuation" in config

    def test_cleaned_mode_returns_stats(self, client, setup_test_video):
        """Test that cleaned mode returns cleanup statistics."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        assert "stats" in data
        stats = data["stats"]
        
        # Verify stats keys
        assert "fillers_removed" in stats
        assert "special_tokens_removed" in stats
        assert "segments_merged" in stats
        assert "segments_split" in stats
        assert "hallucinations_detected" in stats
        assert "punctuation_added" in stats
        
        # Stats should be non-negative
        assert stats["fillers_removed"] >= 0
        assert stats["special_tokens_removed"] >= 0

    def test_cleaned_mode_removes_fillers(self, client, setup_test_video):
        """Test that cleaned mode removes filler words."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        
        # Check that fillers are removed from cleaned text
        for seg in segments:
            cleaned_text = seg["text_cleaned"].lower()
            # Conservative fillers (level 1) should be removed
            assert "um" not in cleaned_text

    def test_cleaned_mode_provides_raw_and_cleaned_text(self, client, setup_test_video):
        """Test that cleaned mode provides both raw and cleaned text."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        
        for seg in segments:
            assert "text_raw" in seg
            assert "text_cleaned" in seg
            # Raw and cleaned should be different for segments with fillers/caps
            # (but may be same for already clean segments)

    def test_cleaned_mode_removes_special_tokens(self, client, setup_test_video):
        """Test that cleaned mode removes special tokens."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        cleaned_texts = [seg["text_cleaned"] for seg in segments]
        
        # Special tokens should be removed from cleaned text
        assert not any("[MUSIC]" in text for text in cleaned_texts)

    def test_cleaned_mode_fixes_all_caps(self, client, setup_test_video):
        """Test that cleaned mode fixes all-caps text."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        
        # Find segment that was all caps in raw
        for seg in segments:
            if "testing" in seg["text_cleaned"].lower():
                # Should be capitalized properly, not all caps
                assert seg["text_cleaned"] != "TESTING ALL CAPS"
                # Should start with capital
                assert seg["text_cleaned"][0].isupper()

    def test_cleaned_mode_adds_punctuation(self, client, setup_test_video):
        """Test that cleaned mode adds terminal punctuation."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        
        # Most segments should have punctuation
        with_punctuation = sum(1 for seg in segments if seg["text_cleaned"].rstrip().endswith((".", "!", "?")))
        assert with_punctuation >= len(segments) * 0.8  # At least 80%

    def test_cleaned_mode_sentence_boundary_flag(self, client, setup_test_video):
        """Test that sentence_boundary flag is set correctly."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        data = response.json()
        
        segments = data["segments"]
        
        for seg in segments:
            assert "sentence_boundary" in seg
            # Should be boolean
            assert isinstance(seg["sentence_boundary"], bool)


class TestFormattedMode:
    """Tests for formatted transcript mode."""

    def test_formatted_mode_returns_text_field(self, client, setup_test_video):
        """Test that formatted mode returns formatted text."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=formatted")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "text" in data
        assert isinstance(data["text"], str)
        assert len(data["text"]) > 0

    def test_formatted_mode_with_speakers(self, client, setup_test_video_with_speakers):
        """Test formatted mode includes speaker labels."""
        video_id = setup_test_video_with_speakers
        
        response = client.get(f"/videos/{video_id}/transcript?mode=formatted")
        data = response.json()
        
        text = data["text"]
        
        # Should include speaker labels
        assert "Speaker 1" in text
        assert "Speaker 2" in text


class TestCachingHeaders:
    """Tests for caching and ETag headers."""

    def test_etag_header_present(self, client, setup_test_video):
        """Test that ETag header is present in response."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        
        assert "etag" in response.headers

    def test_etag_differs_by_mode(self, client, setup_test_video):
        """Test that ETag is different for different modes."""
        video_id = setup_test_video
        
        raw_response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        cleaned_response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        
        raw_etag = raw_response.headers.get("etag")
        cleaned_etag = cleaned_response.headers.get("etag")
        
        assert raw_etag != cleaned_etag

    def test_cache_control_header_present(self, client, setup_test_video):
        """Test that Cache-Control header is present."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        
        assert "cache-control" in response.headers
        assert "max-age" in response.headers["cache-control"]


class TestErrorResponses:
    """Tests for error handling."""

    def test_404_for_nonexistent_video(self, client):
        """Test 404 error for non-existent video."""
        fake_id = uuid.uuid4()
        
        response = client.get(f"/videos/{fake_id}/transcript?mode=raw")
        
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data

    def test_503_for_video_without_transcript(self, client, db_session):
        """Test 503 error for video still processing."""
        # Create video without transcript
        video_id = uuid.uuid4()
        db_session.execute(
            text("""
                INSERT INTO videos (id, youtube_id, title, duration_seconds, status, job_id)
                VALUES (:id, :youtube_id, :title, :duration, 'processing', :job_id)
            """),
            {
                "id": video_id,
                "youtube_id": "processing_video",
                "title": "Processing Video",
                "duration": 120,
                "job_id": uuid.uuid4(),
            }
        )
        db_session.commit()
        
        response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        
        assert response.status_code == 503
        data = response.json()
        assert "error" in data or "detail" in data

    def test_invalid_mode_parameter(self, client, setup_test_video):
        """Test error for invalid mode parameter."""
        video_id = setup_test_video
        
        response = client.get(f"/videos/{video_id}/transcript?mode=invalid")
        
        # Should return 422 for invalid parameter
        assert response.status_code == 422


class TestModeConsistency:
    """Tests for consistency across different modes."""

    def test_segment_count_consistency(self, client, setup_test_video):
        """Test that segment count is roughly consistent across modes."""
        video_id = setup_test_video
        
        raw_response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        cleaned_response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        
        raw_count = len(raw_response.json()["segments"])
        cleaned_count = len(cleaned_response.json()["segments"])
        
        # Cleaned may filter hallucinations but should be similar
        # Allow up to 50% difference (some segments may be filtered)
        assert cleaned_count <= raw_count
        assert cleaned_count >= raw_count * 0.5

    def test_timing_preservation(self, client, setup_test_video):
        """Test that timing information is preserved across modes."""
        video_id = setup_test_video
        
        raw_response = client.get(f"/videos/{video_id}/transcript?mode=raw")
        cleaned_response = client.get(f"/videos/{video_id}/transcript?mode=cleaned")
        
        raw_segments = raw_response.json()["segments"]
        cleaned_segments = cleaned_response.json()["segments"]
        
        # First segment timing should be preserved
        if len(raw_segments) > 0 and len(cleaned_segments) > 0:
            assert raw_segments[0]["start_ms"] == cleaned_segments[0]["start_ms"]
