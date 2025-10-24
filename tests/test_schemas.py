"""Tests for Pydantic schemas and models."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    JobCreate,
    JobStatus,
    SearchHit,
    SearchResponse,
    Segment,
    TranscriptResponse,
    VideoInfo,
    YouTubeTranscriptResponse,
    YTSegment,
)


class TestJobSchemas:
    """Tests for job-related schemas."""

    def test_job_create_valid(self):
        """Test creating a valid JobCreate schema."""
        job = JobCreate(url="https://youtube.com/watch?v=test123", kind="single")
        assert job.url == "https://youtube.com/watch?v=test123"
        assert job.kind == "single"

    def test_job_create_default_kind(self):
        """Test JobCreate with default kind."""
        job = JobCreate(url="https://youtube.com/watch?v=test456")
        assert job.kind == "single"

    def test_job_create_invalid_url(self):
        """Test JobCreate with invalid URL."""
        with pytest.raises(ValidationError):
            JobCreate(url="not-a-valid-url", kind="single")

    def test_job_create_channel_kind(self):
        """Test JobCreate with channel kind."""
        job = JobCreate(url="https://youtube.com/channel/UCtest", kind="channel")
        assert job.kind == "channel"

    def test_job_status_valid(self):
        """Test creating a valid JobStatus schema."""
        job_id = uuid.uuid4()
        now = datetime.utcnow()
        status = JobStatus(id=job_id, kind="single", state="pending", error=None, created_at=now, updated_at=now)
        assert status.id == job_id
        assert status.state == "pending"
        assert status.error is None

    def test_job_status_with_error(self):
        """Test JobStatus with error message."""
        status = JobStatus(
            id=uuid.uuid4(),
            kind="single",
            state="failed",
            error="Download failed",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert status.error == "Download failed"


class TestSegmentSchemas:
    """Tests for segment-related schemas."""

    def test_segment_valid(self):
        """Test creating a valid Segment schema."""
        segment = Segment(start_ms=0, end_ms=1000, text="Hello world", speaker_label="Speaker 1")
        assert segment.start_ms == 0
        assert segment.end_ms == 1000
        assert segment.text == "Hello world"
        assert segment.speaker_label == "Speaker 1"

    def test_segment_no_speaker(self):
        """Test Segment without speaker label."""
        segment = Segment(start_ms=1000, end_ms=2000, text="No speaker", speaker_label=None)
        assert segment.speaker_label is None

    def test_segment_missing_required_fields(self):
        """Test Segment with missing required fields."""
        with pytest.raises(ValidationError):
            Segment(start_ms=0, text="Missing end_ms")

    def test_yt_segment_valid(self):
        """Test creating a valid YTSegment schema."""
        segment = YTSegment(start_ms=500, end_ms=1500, text="YouTube segment")
        assert segment.start_ms == 500
        assert segment.text == "YouTube segment"


class TestTranscriptSchemas:
    """Tests for transcript-related schemas."""

    def test_transcript_response_valid(self):
        """Test creating a valid TranscriptResponse schema."""
        video_id = uuid.uuid4()
        segments = [
            Segment(start_ms=0, end_ms=1000, text="First", speaker_label=None),
            Segment(start_ms=1000, end_ms=2000, text="Second", speaker_label="Speaker 1"),
        ]
        response = TranscriptResponse(video_id=video_id, segments=segments)
        assert response.video_id == video_id
        assert len(response.segments) == 2

    def test_transcript_response_empty_segments(self):
        """Test TranscriptResponse with empty segments list."""
        response = TranscriptResponse(video_id=uuid.uuid4(), segments=[])
        assert len(response.segments) == 0

    def test_youtube_transcript_response_valid(self):
        """Test creating a valid YouTubeTranscriptResponse schema."""
        video_id = uuid.uuid4()
        segments = [YTSegment(start_ms=0, end_ms=1000, text="Test")]
        response = YouTubeTranscriptResponse(
            video_id=video_id, language="en", kind="asr", full_text="Full text", segments=segments
        )
        assert response.language == "en"
        assert response.kind == "asr"
        assert response.full_text == "Full text"

    def test_youtube_transcript_response_optional_fields(self):
        """Test YouTubeTranscriptResponse with optional fields as None."""
        response = YouTubeTranscriptResponse(
            video_id=uuid.uuid4(), language=None, kind=None, full_text=None, segments=[]
        )
        assert response.language is None
        assert response.kind is None


class TestSearchSchemas:
    """Tests for search-related schemas."""

    def test_search_hit_valid(self):
        """Test creating a valid SearchHit schema."""
        hit = SearchHit(id=123, video_id=uuid.uuid4(), start_ms=1000, end_ms=2000, snippet="Search <em>result</em>")
        assert hit.id == 123
        assert "result" in hit.snippet

    def test_search_response_valid(self):
        """Test creating a valid SearchResponse schema."""
        hits = [SearchHit(id=1, video_id=uuid.uuid4(), start_ms=0, end_ms=1000, snippet="Test")]
        response = SearchResponse(total=10, hits=hits)
        assert response.total == 10
        assert len(response.hits) == 1

    def test_search_response_no_total(self):
        """Test SearchResponse without total count."""
        response = SearchResponse(total=None, hits=[])
        assert response.total is None


class TestVideoSchemas:
    """Tests for video-related schemas."""

    def test_video_info_valid(self):
        """Test creating a valid VideoInfo schema."""
        video = VideoInfo(id=uuid.uuid4(), youtube_id="test123", title="Test Video", duration_seconds=300)
        assert video.youtube_id == "test123"
        assert video.title == "Test Video"
        assert video.duration_seconds == 300

    def test_video_info_optional_fields(self):
        """Test VideoInfo with optional fields as None."""
        video = VideoInfo(id=uuid.uuid4(), youtube_id="test456", title=None, duration_seconds=None)
        assert video.title is None
        assert video.duration_seconds is None

    def test_video_info_required_fields_only(self):
        """Test VideoInfo with only required fields."""
        video_id = uuid.uuid4()
        video = VideoInfo(id=video_id, youtube_id="required123")
        assert video.id == video_id
        assert video.youtube_id == "required123"


class TestSchemaValidation:
    """Tests for schema validation edge cases."""

    def test_invalid_uuid(self):
        """Test that invalid UUIDs are rejected."""
        with pytest.raises(ValidationError):
            VideoInfo(id="not-a-uuid", youtube_id="test")

    def test_negative_timestamps(self):
        """Test that negative timestamps are allowed (could be valid in some cases)."""
        # Pydantic will accept negative ints unless we add validators
        segment = Segment(start_ms=-100, end_ms=0, text="Negative start", speaker_label=None)
        assert segment.start_ms == -100

    def test_empty_text_segment(self):
        """Test segment with empty text."""
        segment = Segment(start_ms=0, end_ms=1000, text="", speaker_label=None)
        assert segment.text == ""

    def test_long_text_segment(self):
        """Test segment with very long text."""
        long_text = "A" * 10000
        segment = Segment(start_ms=0, end_ms=1000, text=long_text, speaker_label=None)
        assert len(segment.text) == 10000

    def test_special_characters_in_text(self):
        """Test segment with special characters."""
        special_text = "Test with émojis 🎉 and symbols @#$%"
        segment = Segment(start_ms=0, end_ms=1000, text=special_text, speaker_label=None)
        assert segment.text == special_text
