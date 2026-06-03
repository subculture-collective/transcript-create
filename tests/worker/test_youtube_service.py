from __future__ import annotations

from unittest.mock import patch

import pytest

from worker.youtube.service import YouTubeCaptionResult, YouTubeService
from worker.youtube_captions import YTCaptionTrack, YTSegment, YouTubeCaptionRateLimitError


def test_service_fetch_metadata_wraps_existing_helper():
    payload = {"id": "abc123"}

    with patch("worker.youtube.service._fetch_ytdlp_metadata", return_value=payload) as mock_fetch:
        result = YouTubeService().fetch_metadata("https://example.com/watch?v=abc123")

    assert result == payload
    mock_fetch.assert_called_once_with("https://example.com/watch?v=abc123", flat_playlist=False)


def test_service_fetch_auto_captions_wraps_legacy_result():
    track = YTCaptionTrack(url="https://example.com/captions.json3", language="en", kind="auto", ext="json3")
    segments = [YTSegment(start=0.0, end=1.0, text="hello")]

    with patch("worker.youtube.service._fetch_legacy_auto_captions", return_value=(track, segments)):
        result = YouTubeService().fetch_auto_captions("abc123")

    assert result == YouTubeCaptionResult(track=track, segments=segments, source="direct")


def test_service_fetch_auto_captions_passes_rate_limit_through():
    with patch(
        "worker.youtube.service._fetch_legacy_auto_captions",
        side_effect=YouTubeCaptionRateLimitError("rate limited"),
    ):
        with pytest.raises(YouTubeCaptionRateLimitError):
            YouTubeService().fetch_auto_captions("abc123")
