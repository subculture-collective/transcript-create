from __future__ import annotations

from enum import Enum
from typing import Iterable


class JobState(str, Enum):
    PENDING = "pending"
    EXPANDED = "expanded"
    DOWNLOADING = "downloading"
    TRANSCODING = "transcoding"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoState(str, Enum):
    PENDING = "pending"
    EXPANDED = "expanded"
    DOWNLOADING = "downloading"
    TRANSCODING = "transcoding"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"


class CaptionIngestState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    SKIPPED = "skipped"


class DiarizationState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


ACTIVE_VIDEO_STATES = tuple(
    state.value
    for state in (
        VideoState.PENDING,
        VideoState.DOWNLOADING,
        VideoState.TRANSCODING,
        VideoState.TRANSCRIBING,
        VideoState.DIARIZING,
        VideoState.PERSISTING,
    )
)
IN_PROGRESS_VIDEO_STATES = tuple(
    state.value
    for state in (
        VideoState.DOWNLOADING,
        VideoState.TRANSCODING,
        VideoState.TRANSCRIBING,
        VideoState.DIARIZING,
        VideoState.PERSISTING,
    )
)
TERMINAL_VIDEO_STATES = tuple(state.value for state in (VideoState.COMPLETED, VideoState.FAILED))
TERMINAL_CAPTION_INGEST_STATES = tuple(
    state.value
    for state in (
        CaptionIngestState.COMPLETED,
        CaptionIngestState.UNAVAILABLE,
        CaptionIngestState.FAILED,
        CaptionIngestState.SKIPPED,
    )
)
OPEN_CAPTION_INGEST_STATES = tuple(state.value for state in (CaptionIngestState.PENDING, CaptionIngestState.RUNNING))


def sql_string_list(values: Iterable[str]) -> str:
    """Render trusted enum values for static raw SQL fragments."""
    return ",".join(f"'{value}'" for value in values)


def job_state_from_video_states(video_states: Iterable[VideoState]) -> JobState:
    states = list(video_states)
    if not states:
        return JobState.PENDING
    if all(state == VideoState.COMPLETED for state in states):
        return JobState.COMPLETED
    active_states = {
        VideoState.PENDING,
        VideoState.DOWNLOADING,
        VideoState.TRANSCODING,
        VideoState.TRANSCRIBING,
        VideoState.DIARIZING,
        VideoState.PERSISTING,
    }
    if any(state == VideoState.FAILED for state in states) and not any(state in active_states for state in states):
        return JobState.FAILED
    if any(state == VideoState.DOWNLOADING for state in states):
        return JobState.DOWNLOADING
    return JobState.DOWNLOADING if any(state in active_states for state in states) else JobState.PENDING


def can_start_native_transcription(
    *,
    staged: bool,
    own_caption_state: CaptionIngestState,
    batch_job_count: int,
    expected_batch_jobs: int,
    batch_has_open_caption_work: bool,
) -> bool:
    if not staged:
        return True
    if own_caption_state.value not in TERMINAL_CAPTION_INGEST_STATES:
        return False
    if batch_job_count < expected_batch_jobs:
        return False
    return not batch_has_open_caption_work
