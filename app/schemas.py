import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobCreate(BaseModel):
    """Request body for creating a new transcription job."""

    url: HttpUrl = Field(
        ...,
        description="YouTube video or channel URL to transcribe",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
    )
    kind: Literal["single", "channel"] = Field(
        "single",
        description="Type of job: 'single' for one video, 'channel' for all videos in a channel",
    )

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate that the URL is a YouTube URL."""
        url_str = str(v)
        youtube_patterns = [
            r"^https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://(www\.)?youtube\.com/channel/[\w-]+",
            r"^https?://(www\.)?youtube\.com/@[\w-]+",
            r"^https?://youtu\.be/[\w-]+",
        ]
        if not any(re.match(pattern, url_str) for pattern in youtube_patterns):
            raise ValueError("URL must be a valid YouTube video or channel URL")
        return v


class JobStatus(BaseModel):
    """Status information for a transcription job."""

    id: uuid.UUID = Field(..., description="Unique identifier for the job")
    kind: str = Field(..., description="Job type: 'single' or 'channel'")
    state: str = Field(
        ...,
        description="Current state: 'pending', 'expanded', 'completed', 'failed'",
    )
    error: Optional[str] = Field(None, description="Error message if job failed")
    created_at: datetime = Field(..., description="Timestamp when job was created")
    updated_at: datetime = Field(..., description="Timestamp when job was last updated")

    model_config = {"json_schema_extra": {"example": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "kind": "single",
        "state": "completed",
        "error": None,
        "created_at": "2025-10-25T10:30:00Z",
        "updated_at": "2025-10-25T10:35:00Z",
    }}}


class Segment(BaseModel):
    """A single segment of transcribed text with timing information."""

    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    text: str = Field(..., description="Transcribed text content")
    speaker_label: Optional[str] = Field(
        None, description="Speaker label from diarization (e.g., 'Speaker 1')"
    )

    model_config = {"json_schema_extra": {"example": {
        "start_ms": 1000,
        "end_ms": 3500,
        "text": "Hello and welcome to this video",
        "speaker_label": "Speaker 1",
    }}}


class TranscriptResponse(BaseModel):
    """Complete transcript for a video with all segments."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    segments: List[Segment] = Field(
        ..., description="List of transcript segments in chronological order"
    )

    model_config = {"json_schema_extra": {"example": {
        "video_id": "123e4567-e89b-12d3-a456-426614174000",
        "segments": [
            {
                "start_ms": 1000,
                "end_ms": 3500,
                "text": "Hello and welcome to this video",
                "speaker_label": "Speaker 1",
            }
        ],
    }}}


class YTSegment(BaseModel):
    """A segment from YouTube's native closed captions."""

    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    text: str = Field(..., description="Caption text content")


class YouTubeTranscriptResponse(BaseModel):
    """YouTube's native closed captions for a video."""

    video_id: uuid.UUID = Field(..., description="Unique identifier for the video")
    language: Optional[str] = Field(None, description="Language code of captions (e.g., 'en')")
    kind: Optional[str] = Field(None, description="Caption type: 'asr' (auto-generated) or manual")
    full_text: Optional[str] = Field(None, description="Full transcript text concatenated")
    segments: List[YTSegment] = Field(..., description="List of caption segments")


class SearchHit(BaseModel):
    """A single search result matching the query."""

    id: int = Field(..., description="Segment ID")
    video_id: uuid.UUID = Field(..., description="Video containing this segment")
    start_ms: int = Field(..., description="Start time in milliseconds", ge=0)
    end_ms: int = Field(..., description="End time in milliseconds", ge=0)
    snippet: str = Field(..., description="Text snippet with search term highlighted")

    model_config = {"json_schema_extra": {"example": {
        "id": 12345,
        "video_id": "123e4567-e89b-12d3-a456-426614174000",
        "start_ms": 45000,
        "end_ms": 48500,
        "snippet": "This is an example of <em>search term</em> in context",
    }}}


class SearchResponse(BaseModel):
    """Search results from full-text search."""

    total: Optional[int] = Field(
        None, description="Total number of matching results (only with OpenSearch backend)"
    )
    hits: List[SearchHit] = Field(..., description="List of search results")


class VideoInfo(BaseModel):
    """Basic information about a video."""

    id: uuid.UUID = Field(..., description="Unique identifier for the video")
    youtube_id: str = Field(..., description="YouTube video ID")
    title: Optional[str] = Field(None, description="Video title")
    duration_seconds: Optional[int] = Field(None, description="Video duration in seconds", ge=0)

    model_config = {"json_schema_extra": {"example": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Example Video Title",
        "duration_seconds": 212,
    }}}


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error code identifying the error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details and context"
    )

    model_config = {"json_schema_extra": {"example": {
        "error": "validation_error",
        "message": "Request validation failed",
        "details": {"errors": [{"field": "url", "message": "Invalid URL format"}]},
    }}}


class SearchQuery(BaseModel):
    """Query parameters for search endpoint."""

    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    source: Literal["native", "youtube"] = "native"
    video_id: Optional[uuid.UUID] = None
    limit: int = Field(50, ge=1, le=200, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")
