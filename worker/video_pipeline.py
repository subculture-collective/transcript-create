from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.engine import Engine


VideoId = str | UUID


@dataclass(frozen=True)
class ProcessVideoCommand:
    video_id: VideoId


@dataclass(frozen=True)
class ProcessVideoResult:
    video_id: VideoId
    segment_count: int


class VideoProcessingPipeline(Protocol):
    def process_video(self, command: ProcessVideoCommand) -> ProcessVideoResult:
        ...


class _DefaultVideoProcessingPipeline:
    def __init__(self, engine: Engine):
        self._engine = engine

    def process_video(self, command: ProcessVideoCommand) -> ProcessVideoResult:
        from worker.pipeline import process_video

        segment_count = process_video(self._engine, command.video_id)
        return ProcessVideoResult(video_id=command.video_id, segment_count=segment_count)


def default_video_processing_pipeline(engine: Engine) -> VideoProcessingPipeline:
    return _DefaultVideoProcessingPipeline(engine)
