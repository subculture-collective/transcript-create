"""Transcript Create Python Client Library.

A comprehensive async Python client for the Transcript Create API.
"""

__version__ = "0.1.0"

from .client import TranscriptClient
from .exceptions import (
    APIError,
    AuthenticationError,
    InvalidAPIKeyError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    TranscriptNotFoundError,
    ValidationError,
)
from .models import (
    Job,
    JobCreate,
    JobStatus,
    SearchHit,
    SearchResponse,
    Segment,
    TranscriptResponse,
    VideoInfo,
    YouTubeTranscriptResponse,
)

__all__ = [
    "TranscriptClient",
    # Exceptions
    "APIError",
    "AuthenticationError",
    "InvalidAPIKeyError",
    "NotFoundError",
    "QuotaExceededError",
    "RateLimitError",
    "TranscriptNotFoundError",
    "ValidationError",
    # Models
    "Job",
    "JobCreate",
    "JobStatus",
    "SearchHit",
    "SearchResponse",
    "Segment",
    "TranscriptResponse",
    "VideoInfo",
    "YouTubeTranscriptResponse",
]
