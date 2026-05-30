from unittest.mock import patch

from worker.video_pipeline import (
    ProcessVideoCommand,
    ProcessVideoResult,
    VideoProcessingPipeline,
    default_video_processing_pipeline,
)


class FakePipeline:
    def __init__(self):
        self.commands = []

    def process_video(self, command: ProcessVideoCommand) -> ProcessVideoResult:
        self.commands.append(command)
        return ProcessVideoResult(video_id=command.video_id, segment_count=3)


def test_video_pipeline_interface_uses_fake_dependency():
    pipeline: VideoProcessingPipeline = FakePipeline()

    result = pipeline.process_video(ProcessVideoCommand(video_id="video-123"))

    assert result == ProcessVideoResult(video_id="video-123", segment_count=3)


def test_default_pipeline_delegates_to_current_process_video():
    engine = object()
    pipeline = default_video_processing_pipeline(engine)

    with patch("worker.pipeline.process_video", return_value=7) as process_video:
        result = pipeline.process_video(ProcessVideoCommand(video_id="video-456"))

    process_video.assert_called_once_with(engine, "video-456")
    assert result == ProcessVideoResult(video_id="video-456", segment_count=7)
