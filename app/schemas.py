from pydantic import BaseModel, HttpUrl
from typing import List, Optional
import uuid
from datetime import datetime

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
