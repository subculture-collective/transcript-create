"""
Unit tests for YouTube caption ingestion and parsing.

Tests cover:
- Caption track selection logic with language preferences
- JSON3 caption format parsing
- VTT caption format parsing
- Fallback behavior when captions unavailable
- Error handling for malformed responses
"""

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from worker.youtube_captions import (
    YTCaptionTrack,
    YTSegment,
    _parse_vtt_to_segments,
    _pick_auto_caption,
    fetch_youtube_auto_captions,
)


class TestCaptionTrackSelection:
    """Tests for caption track selection with language preferences."""

    def test_prefers_english_json3(self):
        """Test that English json3 captions are preferred."""
        data = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/en.json3"},
                    {"ext": "vtt", "url": "https://example.com/en.vtt"},
                ],
                "es": [
                    {"ext": "json3", "url": "https://example.com/es.json3"},
                ],
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is not None
        assert track.language == "en"
        assert track.ext == "json3"
        assert "en.json3" in track.url

    def test_prefers_json3_over_vtt(self):
        """Test that json3 is preferred over vtt."""
        data = {
            "automatic_captions": {
                "fr": [
                    {"ext": "vtt", "url": "https://example.com/fr.vtt"},
                    {"ext": "json3", "url": "https://example.com/fr.json3"},
                ]
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is not None
        assert track.ext == "json3"

    def test_english_us_variant_preferred(self):
        """Test that en-US is in preferred list."""
        data = {
            "automatic_captions": {
                "en-US": [
                    {"ext": "json3", "url": "https://example.com/en-us.json3"},
                ],
                "de": [
                    {"ext": "json3", "url": "https://example.com/de.json3"},
                ],
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is not None
        assert track.language == "en-US"

    def test_falls_back_to_any_language(self):
        """Test fallback to any available language when English not available."""
        data = {
            "automatic_captions": {
                "ja": [
                    {"ext": "json3", "url": "https://example.com/ja.json3"},
                ]
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is not None
        assert track.language == "ja"
        assert track.ext == "json3"

    def test_returns_none_when_no_captions(self):
        """Test returns None when no automatic captions available."""
        data = {"automatic_captions": {}}
        
        track = _pick_auto_caption(data)
        
        assert track is None

    def test_returns_none_when_no_supported_formats(self):
        """Test returns None when only unsupported formats available."""
        data = {
            "automatic_captions": {
                "en": [
                    {"ext": "srv1", "url": "https://example.com/en.srv1"},
                    {"ext": "srv2", "url": "https://example.com/en.srv2"},
                ]
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is None

    def test_returns_vtt_if_no_json3(self):
        """Test that VTT is used if json3 is not available."""
        data = {
            "automatic_captions": {
                "en": [
                    {"ext": "vtt", "url": "https://example.com/en.vtt"},
                ]
            }
        }
        
        track = _pick_auto_caption(data)
        
        assert track is not None
        assert track.ext == "vtt"


class TestJSON3Parsing:
    """Tests for JSON3 caption format parsing."""

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_parses_json3_events(self, mock_urlopen, mock_yt_dlp):
        """Test parsing of json3 events into segments."""
        # Mock yt-dlp metadata
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"},
                ]
            }
        }
        
        # Mock json3 response
        json3_data = {
            "events": [
                {
                    "tStartMs": 0,
                    "dDurationMs": 2000,
                    "segs": [
                        {"utf8": "Hello "},
                        {"utf8": "world"},
                    ]
                },
                {
                    "tStartMs": 2500,
                    "dDurationMs": 1500,
                    "segs": [
                        {"utf8": "How are you"},
                    ]
                },
            ]
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(json3_data).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is not None
        track, segments = result
        
        assert track.ext == "json3"
        assert len(segments) == 2
        
        # First segment
        assert segments[0].start == 0.0
        assert segments[0].end == 2.0
        assert segments[0].text == "Hello world"
        
        # Second segment
        assert segments[1].start == 2.5
        assert segments[1].end == 4.0
        assert segments[1].text == "How are you"

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_skips_empty_events(self, mock_urlopen, mock_yt_dlp):
        """Test that empty events are skipped."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"},
                ]
            }
        }
        
        json3_data = {
            "events": [
                {
                    "tStartMs": 0,
                    "dDurationMs": 2000,
                    "segs": []  # Empty
                },
                {
                    "tStartMs": None,  # Missing start time
                    "dDurationMs": 1000,
                    "segs": [{"utf8": "Text"}]
                },
                {
                    "tStartMs": 2000,
                    "dDurationMs": 1000,
                    "segs": [{"utf8": "Valid"}]
                },
            ]
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(json3_data).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is not None
        _, segments = result
        
        # Only valid segment should be included
        assert len(segments) == 1
        assert segments[0].text == "Valid"

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_handles_malformed_json3(self, mock_urlopen, mock_yt_dlp):
        """Test handling of malformed json3 data."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"},
                ]
            }
        }
        
        # Invalid JSON
        mock_response = MagicMock()
        mock_response.read.return_value = b"invalid json {"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        # Should return None on parse error
        assert result is None


class TestVTTParsing:
    """Tests for VTT caption format parsing."""

    def test_parses_basic_vtt(self):
        """Test parsing of basic VTT format."""
        vtt_content = b"""WEBVTT

1
00:00:00.000 --> 00:00:02.000
Hello world

2
00:00:02.500 --> 00:00:04.000
How are you

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        assert len(segments) == 2
        assert segments[0].start == 0.0
        assert segments[0].end == 2.0
        assert segments[0].text == "Hello world"
        assert segments[1].start == 2.5
        assert segments[1].end == 4.0
        assert segments[1].text == "How are you"

    def test_parses_vtt_without_cue_ids(self):
        """Test parsing VTT without cue identifiers."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:02.000
First segment

00:00:02.000 --> 00:00:04.000
Second segment

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        assert len(segments) == 2
        assert segments[0].text == "First segment"
        assert segments[1].text == "Second segment"

    def test_handles_multiline_cues(self):
        """Test handling of multiline cue text."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:03.000
This is a
multiline cue
with three lines

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        assert len(segments) == 1
        # Lines should be joined with spaces
        assert segments[0].text == "This is a multiline cue with three lines"

    def test_parses_mm_ss_format(self):
        """Test parsing MM:SS.mmm timestamp format."""
        vtt_content = b"""WEBVTT

00:30.000 --> 01:15.500
Text with minutes only

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        assert len(segments) == 1
        assert segments[0].start == 30.0
        assert segments[0].end == 75.5

    def test_skips_empty_cues(self):
        """Test that empty cues are skipped."""
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:02.000


00:00:02.000 --> 00:00:04.000
Valid text

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        assert len(segments) == 1
        assert segments[0].text == "Valid text"

    def test_handles_malformed_timing_lines(self):
        """Test handling of malformed timing lines."""
        vtt_content = b"""WEBVTT

invalid timing line
Some text here

00:00:02.000 --> 00:00:04.000
Valid segment

"""
        
        segments = _parse_vtt_to_segments(vtt_content)
        
        # Should skip malformed segment and parse valid one
        assert len(segments) == 1
        assert segments[0].text == "Valid segment"

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_integration_vtt_parsing(self, mock_urlopen, mock_yt_dlp):
        """Test full integration of VTT caption fetching and parsing."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "vtt", "url": "https://example.com/captions.vtt"},
                ]
            }
        }
        
        vtt_content = b"""WEBVTT

00:00:00.000 --> 00:00:02.000
First line

00:00:02.000 --> 00:00:04.000
Second line

"""
        
        mock_response = MagicMock()
        mock_response.read.return_value = vtt_content
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is not None
        track, segments = result
        
        assert track.ext == "vtt"
        assert len(segments) == 2
        assert segments[0].text == "First line"


class TestErrorHandling:
    """Tests for error handling in caption fetching."""

    @patch('worker.youtube_captions._yt_dlp_json')
    def test_returns_none_when_no_auto_captions(self, mock_yt_dlp):
        """Test returns None when video has no automatic captions."""
        mock_yt_dlp.return_value = {
            "automatic_captions": None
        }
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is None

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_handles_network_errors(self, mock_urlopen, mock_yt_dlp):
        """Test handling of network errors when downloading captions."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"},
                ]
            }
        }
        
        # Simulate network error
        mock_urlopen.side_effect = URLError("Network unreachable")
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        # Should return None on network error
        assert result is None

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_handles_http_errors(self, mock_urlopen, mock_yt_dlp):
        """Test handling of HTTP errors (404, 403, etc.)."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/captions.json3"},
                ]
            }
        }
        
        # Simulate 404
        mock_urlopen.side_effect = HTTPError(
            "https://example.com/captions.json3", 
            404, 
            "Not Found", 
            {}, 
            None
        )
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is None

    @patch('worker.youtube_captions._yt_dlp_json')
    @patch('worker.youtube_captions.urlopen')
    def test_handles_timeout(self, mock_urlopen, mock_yt_dlp):
        """Test handling of request timeout."""
        mock_yt_dlp.return_value = {
            "automatic_captions": {
                "en": [
                    {"ext": "vtt", "url": "https://example.com/captions.vtt"},
                ]
            }
        }
        
        # Simulate timeout
        import socket
        mock_urlopen.side_effect = socket.timeout("Request timed out")
        
        result = fetch_youtube_auto_captions("test_video_id")
        
        assert result is None


class TestDataclasses:
    """Tests for dataclass structures."""

    def test_yt_segment_creation(self):
        """Test YTSegment dataclass creation."""
        segment = YTSegment(start=1.5, end=3.5, text="Test text")
        
        assert segment.start == 1.5
        assert segment.end == 3.5
        assert segment.text == "Test text"

    def test_yt_caption_track_creation(self):
        """Test YTCaptionTrack dataclass creation."""
        track = YTCaptionTrack(
            url="https://example.com/test.json3",
            language="en",
            kind="auto",
            ext="json3"
        )
        
        assert track.url == "https://example.com/test.json3"
        assert track.language == "en"
        assert track.kind == "auto"
        assert track.ext == "json3"
