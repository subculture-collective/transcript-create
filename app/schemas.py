import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class JobCreate(BaseModel):
    url: HttpUrl
    kind: str = "single"  # or "channel"


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
