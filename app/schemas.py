import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobCreate(BaseModel):
    url: HttpUrl
    kind: Literal["single", "channel"] = "single"

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
    id: uuid.UUID
    kind: str
    state: str
    error: Optional[str]
    created_at: datetime
    updated_at: datetime


class Segment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker_label: Optional[str]


class TranscriptResponse(BaseModel):
    video_id: uuid.UUID
    segments: List[Segment]


class YTSegment(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class YouTubeTranscriptResponse(BaseModel):
    video_id: uuid.UUID
    language: Optional[str] = None
    kind: Optional[str] = None
    full_text: Optional[str] = None
    segments: List[YTSegment]


class SearchHit(BaseModel):
    id: int
    video_id: uuid.UUID
    start_ms: int
    end_ms: int
    snippet: str


class SearchResponse(BaseModel):
    total: Optional[int] = None  # optional for now
    hits: List[SearchHit]


class VideoInfo(BaseModel):
    id: uuid.UUID
    youtube_id: str
    title: Optional[str] = None
    duration_seconds: Optional[int] = None


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


class SearchQuery(BaseModel):
    """Query parameters for search endpoint."""

    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    source: Literal["native", "youtube"] = "native"
    video_id: Optional[uuid.UUID] = None
    limit: int = Field(50, ge=1, le=200, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")
