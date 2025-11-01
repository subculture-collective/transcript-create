"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class JobCreate(BaseModel):
    """Request to create a new transcription job."""

    url: HttpUrl = Field(..., description="YouTube video or channel URL")
    kind: Literal["single", "channel"] = Field("single", description="Job type")


class Job(BaseModel):
    """Job information."""

    id: UUID = Field(..., description="Job ID")
    kind: str = Field(..., description="Job type")
    state: str = Field(..., description="Job state")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class JobStatus(BaseModel):
    """Detailed job status."""

    id: UUID
    kind: str
    state: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Segment(BaseModel):
    """A transcript segment with timing."""

    start_ms: int = Field(..., ge=0, description="Start time in milliseconds")
    end_ms: int = Field(..., ge=0, description="End time in milliseconds")
    text: str = Field(..., description="Transcript text")
    speaker_label: Optional[str] = Field(None, description="Speaker label")


class TranscriptResponse(BaseModel):
    """Complete transcript with segments."""

    video_id: UUID = Field(..., description="Video ID")
    segments: List[Segment] = Field(..., description="Transcript segments")


class YTSegment(BaseModel):
    """YouTube caption segment."""

    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    text: str


class YouTubeTranscriptResponse(BaseModel):
    """YouTube captions response."""

    video_id: UUID
    language: Optional[str] = None
    kind: Optional[str] = None
    full_text: Optional[str] = None
    segments: List[YTSegment]


class VideoInfo(BaseModel):
    """Video information."""

    id: UUID
    youtube_id: str
    title: Optional[str] = None
    duration_seconds: Optional[int] = Field(None, ge=0)


class SearchHit(BaseModel):
    """A search result."""

    id: int
    video_id: UUID
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    snippet: str


class SearchResponse(BaseModel):
    """Search results."""

    total: Optional[int] = None
    hits: List[SearchHit]
    query_time_ms: Optional[int] = None


class ErrorResponse(BaseModel):
    """API error response."""

    error: str
    message: str
    details: Optional[dict] = None
