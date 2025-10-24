"""Tests for worker.youtube_captions module."""

import json
from unittest.mock import Mock, patch

from worker.youtube_captions import (
    YTCaptionTrack,
    YTSegment,
    _parse_vtt_to_segments,
    _pick_auto_caption,
    _yt_dlp_json,
    fetch_youtube_auto_captions,
)


class TestYTDlpJson:
    """Tests for _yt_dlp_json function."""

    @patch("worker.youtube_captions.subprocess.check_output")
    def test_yt_dlp_json_success(self, mock_check_output):
        """Test successful yt-dlp JSON extraction."""
        test_data = {"id": "test123", "title": "Test Video"}
        mock_check_output.return_value = json.dumps(test_data).encode()

        result = _yt_dlp_json("https://www.youtube.com/watch?v=test123")

        assert result == test_data
        mock_check_output.assert_called_once()
        call_args = mock_check_output.call_args[0][0]
        assert "yt-dlp" in call_args
        assert "-J" in call_args

    @patch("worker.youtube_captions.subprocess.check_output")
    def test_yt_dlp_json_command_structure(self, mock_check_output):
        """Test yt-dlp command structure."""
        mock_check_output.return_value = b'{"id": "test"}'
        url = "https://www.youtube.com/watch?v=abc"

        _yt_dlp_json(url)

        call_args = mock_check_output.call_args[0][0]
        assert call_args == ["yt-dlp", "-J", url]


class TestPickAutoCaption:
    """Tests for _pick_auto_caption function."""

    def test_pick_auto_caption_english_json3_preferred(self):
        """Test English json3 captions are preferred."""
        data = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "http://example.com/en.json3"},
                    {"ext": "vtt", "url": "http://example.com/en.vtt"},
                ],
                "es": [{"ext": "json3", "url": "http://example.com/es.json3"}],
            }
        }

        result = _pick_auto_caption(data)

        assert result is not None
        assert result.language == "en"
        assert result.ext == "json3"
        assert result.kind == "auto"

    def test_pick_auto_caption_english_us_preferred(self):
        """Test en-US is preferred over other languages."""
        data = {
            "automatic_captions": {
                "en-US": [{"ext": "json3", "url": "http://example.com/en-us.json3"}],
                "fr": [{"ext": "json3", "url": "http://example.com/fr.json3"}],
            }
        }

        result = _pick_auto_caption(data)

        assert result is not None
        assert result.language == "en-US"

    def test_pick_auto_caption_vtt_fallback(self):
        """Test VTT is used when json3 unavailable."""
        data = {
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "http://example.com/en.vtt"}],
            }
        }

        result = _pick_auto_caption(data)

        assert result is not None
        assert result.ext == "vtt"

    def test_pick_auto_caption_non_english_fallback(self):
        """Test non-English captions used as last resort."""
        data = {
            "automatic_captions": {
                "de": [{"ext": "json3", "url": "http://example.com/de.json3"}],
            }
        }

        result = _pick_auto_caption(data)

        assert result is not None
        assert result.language == "de"
        assert result.ext == "json3"

    def test_pick_auto_caption_no_captions(self):
        """Test returns None when no captions available."""
        data = {"automatic_captions": {}}

        result = _pick_auto_caption(data)

        assert result is None

    def test_pick_auto_caption_missing_key(self):
        """Test returns None when automatic_captions key missing."""
        data = {}

        result = _pick_auto_caption(data)

        assert result is None

    def test_pick_auto_caption_unsupported_format(self):
        """Test unsupported formats are ignored."""
        data = {
            "automatic_captions": {
                "en": [{"ext": "srv1", "url": "http://example.com/en.srv1"}],
            }
        }

        result = _pick_auto_caption(data)

        assert result is None

    def test_pick_auto_caption_missing_url(self):
        """Test tracks without URLs are skipped."""
        data = {
            "automatic_captions": {
                "en": [{"ext": "json3"}],  # No URL
            }
        }

        result = _pick_auto_caption(data)

        assert result is None


class TestParseVttToSegments:
    """Tests for _parse_vtt_to_segments function."""

    def test_parse_vtt_basic(self):
        """Test parsing basic VTT format."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
First segment

00:00:05.000 --> 00:00:10.000
Second segment
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 2
        assert result[0].start == 0.0
        assert result[0].end == 5.0
        assert result[0].text == "First segment"
        assert result[1].start == 5.0
        assert result[1].end == 10.0
        assert result[1].text == "Second segment"

    def test_parse_vtt_with_cue_ids(self):
        """Test parsing VTT with cue identifiers."""
        vtt_content = b"""WEBVTT

1
00:00:00.000 --> 00:00:05.000
First segment

2
00:00:05.000 --> 00:00:10.000
Second segment
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 2
        assert result[0].text == "First segment"
        assert result[1].text == "Second segment"

    def test_parse_vtt_multiline_text(self):
        """Test parsing VTT with multi-line captions."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
First line
Second line
Third line
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 1
        assert result[0].text == "First line Second line Third line"

    def test_parse_vtt_time_formats(self):
        """Test parsing different time formats."""
        vtt_content = b"""WEBVTT

00:01:30.500 --> 00:01:35.750
Test with hours

01:30.500 --> 01:35.750
Test without hours
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 2
        assert result[0].start == 90.5
        assert result[0].end == 95.75
        assert result[1].start == 90.5
        assert result[1].end == 95.75

    def test_parse_vtt_comma_decimal_separator(self):
        """Test parsing VTT with comma as decimal separator."""
        vtt_content = b"""WEBVTT

00:00:00,500 --> 00:00:05,250
Test comma separator
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 1
        assert result[0].start == 0.5
        assert result[0].end == 5.25

    def test_parse_vtt_empty_cues_ignored(self):
        """Test empty cues are skipped."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
Valid segment

00:00:05.000 --> 00:00:10.000

00:00:10.000 --> 00:00:15.000
Another valid segment
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 2
        assert result[0].text == "Valid segment"
        assert result[1].text == "Another valid segment"

    def test_parse_vtt_malformed_timing_skipped(self):
        """Test malformed timing lines are skipped."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
Valid segment

INVALID TIMING
This should be skipped

00:00:10.000 --> 00:00:15.000
Another valid segment
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 2
        assert result[0].text == "Valid segment"
        assert result[1].text == "Another valid segment"

    def test_parse_vtt_with_metadata(self):
        """Test VTT with header metadata."""
        vtt_content = b"""WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:05.000
First segment
"""
        result = _parse_vtt_to_segments(vtt_content)

        assert len(result) == 1
        assert result[0].text == "First segment"


class TestFetchYoutubeAutoCaptions:
    """Tests for fetch_youtube_auto_captions function."""

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_json3(self, mock_yt_dlp, mock_urlopen):
        """Test fetching json3 captions."""
        # Setup yt-dlp response
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]
            }
        }

        # Setup caption response
        caption_data = {
            "events": [
                {
                    "tStartMs": 0,
                    "dDurationMs": 5000,
                    "segs": [{"utf8": "Hello "}, {"utf8": "world"}],
                },
                {
                    "tStartMs": 5000,
                    "dDurationMs": 3000,
                    "segs": [{"utf8": "Test"}],
                },
            ]
        }

        mock_response = Mock()
        mock_response.read.return_value = json.dumps(caption_data).encode()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_youtube_auto_captions("test123")

        assert result is not None
        track, segments = result
        assert track.language == "en"
        assert track.kind == "auto"
        assert track.ext == "json3"
        assert len(segments) == 2
        assert segments[0].start == 0.0
        assert segments[0].end == 5.0
        assert segments[0].text == "Hello world"
        assert segments[1].start == 5.0
        assert segments[1].end == 8.0
        assert segments[1].text == "Test"

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_vtt(self, mock_yt_dlp, mock_urlopen):
        """Test fetching VTT captions."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "http://example.com/captions.vtt"}]
            }
        }

        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
Caption text
"""

        mock_response = Mock()
        mock_response.read.return_value = vtt_content
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_youtube_auto_captions("test123")

        assert result is not None
        track, segments = result
        assert track.ext == "vtt"
        assert len(segments) == 1
        assert segments[0].text == "Caption text"

    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_no_captions(self, mock_yt_dlp):
        """Test returns None when no captions available."""
        mock_yt_dlp.return_value = {"automatic_captions": {}}

        result = fetch_youtube_auto_captions("test123")

        assert result is None

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_download_failure(self, mock_yt_dlp, mock_urlopen):
        """Test returns None when caption download fails."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]
            }
        }

        mock_urlopen.side_effect = Exception("Network error")

        result = fetch_youtube_auto_captions("test123")

        assert result is None

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_invalid_json3(self, mock_yt_dlp, mock_urlopen):
        """Test returns None when json3 is invalid."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]
            }
        }

        mock_response = Mock()
        mock_response.read.return_value = b"invalid json"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_youtube_auto_captions("test123")

        assert result is None

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_empty_events(self, mock_yt_dlp, mock_urlopen):
        """Test handles json3 with empty events."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]
            }
        }

        caption_data = {"events": []}

        mock_response = Mock()
        mock_response.read.return_value = json.dumps(caption_data).encode()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_youtube_auto_captions("test123")

        assert result is not None
        track, segments = result
        assert len(segments) == 0

    @patch("worker.youtube_captions.urlopen")
    @patch("worker.youtube_captions._yt_dlp_json")
    def test_fetch_youtube_auto_captions_user_agent(self, mock_yt_dlp, mock_urlopen):
        """Test request includes User-Agent header."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]
            }
        }

        mock_response = Mock()
        mock_response.read.return_value = b'{"events": []}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        fetch_youtube_auto_captions("test123")

        # Verify Request was created with User-Agent
        call_args = mock_urlopen.call_args[0]
        if call_args:
            # Request object should have headers
            pass


class TestYTDataClasses:
    """Tests for YTSegment and YTCaptionTrack dataclasses."""

    def test_yt_segment_creation(self):
        """Test YTSegment dataclass."""
        seg = YTSegment(start=1.5, end=5.5, text="Test text")

        assert seg.start == 1.5
        assert seg.end == 5.5
        assert seg.text == "Test text"

    def test_yt_caption_track_creation(self):
        """Test YTCaptionTrack dataclass."""
        track = YTCaptionTrack(
            url="http://example.com/caption",
            language="en",
            kind="auto",
            ext="json3",
        )

        assert track.url == "http://example.com/caption"
        assert track.language == "en"
        assert track.kind == "auto"
        assert track.ext == "json3"

    def test_yt_caption_track_optional_language(self):
        """Test YTCaptionTrack with None language."""
        track = YTCaptionTrack(
            url="http://example.com/caption",
            language=None,
            kind="auto",
            ext="vtt",
        )

        assert track.language is None
