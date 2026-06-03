from __future__ import annotations

import uuid
from unittest.mock import Mock, patch

from app.settings import settings
from worker.caption_ingest import CaptionIngestionResult, ingest_available_captions
from worker.youtube.service import YouTubeCaptionResult, YouTubeService
from worker.youtube_captions import YouTubeCaptionRateLimitError


def test_caption_ingestion_result_dataclass_fields():
    result = CaptionIngestionResult(1, 2, 3, 4, True, 9)

    assert result.attempted == 1
    assert result.completed == 2
    assert result.unavailable == 3
    assert result.failed == 4
    assert result.rate_limited is True
    assert result.cooldown_seconds == 9


@patch("worker.caption_ingest.VideoRepository")
@patch("worker.caption_ingest.fetch_youtube_auto_captions")
def test_ingest_available_captions_returns_rate_limit_result(mock_fetch, mock_video_repo_cls):
    video_id = uuid.uuid4()
    db = Mock()
    db.execute.return_value.all.return_value = [(video_id, "yt-123")]

    mock_fetch.side_effect = YouTubeCaptionRateLimitError("rate limited")
    repo = Mock()
    mock_video_repo_cls.return_value = repo

    result = ingest_available_captions(db, limit=1)

    assert result == CaptionIngestionResult(
        attempted=1,
        completed=0,
        unavailable=0,
        failed=0,
        rate_limited=True,
        cooldown_seconds=settings.YTDLP_RATE_LIMIT_COOLDOWN_SECONDS,
    )
    repo.mark_caption_running.assert_called_once_with(str(video_id))
    repo.mark_caption_pending_with_error.assert_called_once()
    mock_fetch.assert_called_once_with("yt-123")


@patch("worker.caption_ingest.VideoRepository")
def test_ingest_available_captions_can_use_service_seam(mock_video_repo_cls):
    video_id = uuid.uuid4()
    db = Mock()
    db.execute.return_value.all.return_value = [(video_id, "yt-456")]

    repo = Mock()
    mock_video_repo_cls.return_value = repo

    fake_service = Mock(spec=YouTubeService)
    fake_service.fetch_auto_captions.return_value = YouTubeCaptionResult(
        track=Mock(language="en", kind="auto", url="http://example.com/captions.json3"),
        segments=[Mock(start=0.0, end=5.0, text="Test caption")],
        source="direct",
    )

    result = ingest_available_captions(db, limit=1, youtube_service=fake_service)

    assert result == CaptionIngestionResult(
        attempted=1,
        completed=1,
        unavailable=0,
        failed=0,
        rate_limited=False,
        cooldown_seconds=None,
    )
    fake_service.fetch_auto_captions.assert_called_once_with("yt-456")
