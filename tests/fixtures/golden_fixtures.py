"""
Golden fixtures for regression testing.

These fixtures provide reference inputs and expected outputs for:
- Whisper transcription output
- YouTube caption output
- Formatted transcript output
- API response structures

Used to detect unintended changes in formatting behavior.
"""

import pytest


@pytest.fixture
def golden_whisper_output():
    """Reference Whisper transcription output."""
    return [
        {
            "text": "um hello everyone",
            "start": 0,
            "end": 2000,
            "speaker": None,
        },
        {
            "text": "today we're going to talk about",
            "start": 2000,
            "end": 5000,
            "speaker": None,
        },
        {
            "text": "ARTIFICIAL INTELLIGENCE",
            "start": 5000,
            "end": 7000,
            "speaker": None,
        },
        {
            "text": "[MUSIC] it's really interesting [MUSIC]",
            "start": 7000,
            "end": 10000,
            "speaker": None,
        },
        {
            "text": "like you know i think it's the future",
            "start": 10000,
            "end": 13000,
            "speaker": None,
        },
    ]


@pytest.fixture
def golden_formatted_output():
    """Expected formatted output from golden Whisper input."""
    return [
        {
            "text": "Hello everyone.",
            "start": 0,
            "end": 2000,
        },
        {
            "text": "Today we're going to talk about.",
            "start": 2000,
            "end": 5000,
        },
        {
            "text": "Artificial intelligence.",
            "start": 5000,
            "end": 7000,
        },
        {
            "text": "It's really interesting.",
            "start": 7000,
            "end": 10000,
        },
        {
            "text": "I think it's the future.",
            "start": 10000,
            "end": 13000,
        },
    ]


@pytest.fixture
def golden_youtube_captions():
    """Reference YouTube caption output (JSON3 format)."""
    return {
        "events": [
            {
                "tStartMs": 0,
                "dDurationMs": 3000,
                "segs": [
                    {"utf8": "Welcome to "},
                    {"utf8": "this tutorial"},
                ]
            },
            {
                "tStartMs": 3000,
                "dDurationMs": 2500,
                "segs": [
                    {"utf8": "Today we will "},
                    {"utf8": "learn about Python"},
                ]
            },
            {
                "tStartMs": 5500,
                "dDurationMs": 2000,
                "segs": [
                    {"utf8": "Let's get started"},
                ]
            },
        ]
    }


@pytest.fixture
def golden_youtube_captions_parsed():
    """Expected parsed output from golden YouTube captions."""
    return [
        {
            "text": "Welcome to this tutorial",
            "start": 0.0,
            "end": 3.0,
        },
        {
            "text": "Today we will learn about Python",
            "start": 3.0,
            "end": 5.5,
        },
        {
            "text": "Let's get started",
            "start": 5.5,
            "end": 7.5,
        },
    ]


@pytest.fixture
def golden_vtt_captions():
    """Reference VTT caption content."""
    return """WEBVTT

1
00:00:00.000 --> 00:00:03.000
Welcome to this tutorial

2
00:00:03.000 --> 00:00:05.500
Today we will learn about Python

3
00:00:05.500 --> 00:00:07.500
Let's get started
"""


@pytest.fixture
def golden_speaker_diarization():
    """Reference output with speaker diarization."""
    return [
        {
            "text": "Hello, my name is John",
            "start": 0,
            "end": 2000,
            "speaker": "Speaker 1",
            "speaker_label": "Speaker 1",
        },
        {
            "text": "Nice to meet you, I'm Jane",
            "start": 2500,
            "end": 4500,
            "speaker": "Speaker 2",
            "speaker_label": "Speaker 2",
        },
        {
            "text": "Pleased to meet you too",
            "start": 5000,
            "end": 7000,
            "speaker": "Speaker 1",
            "speaker_label": "Speaker 1",
        },
    ]


@pytest.fixture
def golden_formatted_speakers():
    """Expected formatted output with speaker labels (structured format)."""
    return [
        {
            "text": "Speaker 1: Hello, my name is John.",
            "start": 0,
            "end": 2000,
            "speaker": "Speaker 1",
        },
        {
            "text": "Speaker 2: Nice to meet you, I'm Jane.",
            "start": 2500,
            "end": 4500,
            "speaker": "Speaker 2",
        },
        {
            "text": "Speaker 1: Pleased to meet you too.",
            "start": 5000,
            "end": 7000,
            "speaker": "Speaker 1",
        },
    ]


@pytest.fixture
def golden_multilingual_segments():
    """Reference multilingual transcript segments."""
    return [
        {
            "text": "Hello world",
            "start": 0,
            "end": 2000,
            "language": "en",
        },
        {
            "text": "Bonjour le monde",
            "start": 2000,
            "end": 4000,
            "language": "fr",
        },
        {
            "text": "こんにちは世界",
            "start": 4000,
            "end": 6000,
            "language": "ja",
        },
        {
            "text": "مرحبا بالعالم",
            "start": 6000,
            "end": 8000,
            "language": "ar",
        },
        {
            "text": "Привет мир",
            "start": 8000,
            "end": 10000,
            "language": "ru",
        },
    ]


@pytest.fixture
def golden_api_raw_response():
    """Reference API response for raw mode."""
    return {
        "video_id": "12345678-1234-1234-1234-123456789012",
        "segments": [
            {
                "start_ms": 0,
                "end_ms": 2000,
                "text": "um hello world",
                "speaker_label": None,
            },
            {
                "start_ms": 2000,
                "end_ms": 4000,
                "text": "this is like a test",
                "speaker_label": None,
            },
        ],
    }


@pytest.fixture
def golden_api_cleaned_response():
    """Reference API response for cleaned mode."""
    return {
        "video_id": "12345678-1234-1234-1234-123456789012",
        "segments": [
            {
                "start_ms": 0,
                "end_ms": 2000,
                "text_raw": "um hello world",
                "text_cleaned": "Hello world.",
                "speaker_label": None,
                "sentence_boundary": True,
                "likely_hallucination": False,
            },
            {
                "start_ms": 2000,
                "end_ms": 4000,
                "text_raw": "this is like a test",
                "text_cleaned": "This is a test.",
                "speaker_label": None,
                "sentence_boundary": True,
                "likely_hallucination": False,
            },
        ],
        "cleanup_config": {
            "normalize_unicode": True,
            "normalize_whitespace": True,
            "remove_special_tokens": True,
            "preserve_sound_events": False,
            "add_punctuation": True,
            "punctuation_mode": "rule-based",
            "add_internal_punctuation": False,
            "capitalize": True,
            "fix_all_caps": True,
            "remove_fillers": True,
            "filler_level": 1,
            "segment_sentences": False,
            "merge_short_segments": False,
            "min_segment_length_ms": 1000,
            "max_gap_for_merge_ms": 500,
            "speaker_format": "structured",
            "detect_hallucinations": True,
            "language_specific_rules": True,
        },
        "stats": {
            "fillers_removed": 2,
            "special_tokens_removed": 0,
            "segments_merged": 0,
            "segments_split": 0,
            "hallucinations_detected": 0,
            "punctuation_added": 2,
        },
    }


@pytest.fixture
def golden_edge_cases():
    """Collection of edge case inputs for testing."""
    return {
        "empty_segment": {
            "text": "",
            "start": 0,
            "end": 1000,
        },
        "whitespace_only": {
            "text": "   \t\n   ",
            "start": 0,
            "end": 1000,
        },
        "very_short": {
            "text": "a",
            "start": 0,
            "end": 100,
        },
        "only_punctuation": {
            "text": "...",
            "start": 0,
            "end": 500,
        },
        "hallucination_repeated": {
            "text": "the the the the",
            "start": 0,
            "end": 1000,
        },
        "hallucination_common": {
            "text": "Thank you.",
            "start": 0,
            "end": 500,
        },
        "all_caps_short": {
            "text": "NASA",
            "start": 0,
            "end": 500,
        },
        "all_caps_long": {
            "text": "THIS IS SHOUTING",
            "start": 0,
            "end": 1000,
        },
        "emoji": {
            "text": "Hello 😀 👍 world",
            "start": 0,
            "end": 1000,
        },
        "url": {
            "text": "Visit https://example.com for more",
            "start": 0,
            "end": 2000,
        },
        "email": {
            "text": "Contact us at info@example.com",
            "start": 0,
            "end": 2000,
        },
    }


class TestGoldenFixtures:
    """Regression tests using golden fixtures."""

    def test_whisper_to_formatted_regression(self, golden_whisper_output, golden_formatted_output):
        """Test that formatting produces expected output (regression test)."""
        from worker.formatter import format_transcript
        
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "remove_special_tokens": True,
            "remove_fillers": True,
            "filler_level": 2,
            "fix_all_caps": True,
            "add_sentence_punctuation": True,
            "capitalize_sentences": True,
            "segment_by_sentences": False,
            "merge_short_segments": False,
        }
        
        result = format_transcript(golden_whisper_output, config=config)
        
        assert len(result) == len(golden_formatted_output)
        
        for i, (actual, expected) in enumerate(zip(result, golden_formatted_output, strict=True)):
            assert actual["text"] == expected["text"], f"Text mismatch at segment {i}"
            assert actual["start"] == expected["start"], f"Start time mismatch at segment {i}"
            assert actual["end"] == expected["end"], f"End time mismatch at segment {i}"

    def test_youtube_captions_parsing_regression(self, golden_youtube_captions, golden_youtube_captions_parsed):
        """Test that YouTube caption parsing produces expected output."""
        import json
        from unittest.mock import MagicMock, patch
        
        with patch('worker.youtube_captions._yt_dlp_json') as mock_yt_dlp:
            mock_yt_dlp.return_value = {
                "automatic_captions": {
                    "en": [
                        {"ext": "json3", "url": "https://example.com/captions.json3"}
                    ]
                }
            }
            
            with patch('worker.youtube_captions.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = json.dumps(golden_youtube_captions).encode()
                mock_response.__enter__.return_value = mock_response
                mock_response.__exit__.return_value = False
                mock_urlopen.return_value = mock_response
                
                from worker.youtube_captions import fetch_youtube_auto_captions
                
                result = fetch_youtube_auto_captions("test_video")
                
                assert result is not None
                track, segments = result
                
                assert len(segments) == len(golden_youtube_captions_parsed)
                
                for i, (actual, expected) in enumerate(zip(segments, golden_youtube_captions_parsed, strict=True)):
                    assert actual.text == expected["text"]
                    assert actual.start == expected["start"]
                    assert actual.end == expected["end"]

    def test_speaker_formatting_regression(self, golden_speaker_diarization, golden_formatted_speakers):
        """Test that speaker formatting produces expected output."""
        from worker.formatter import format_transcript
        
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
            "speaker_format": "structured",
        }
        
        result = format_transcript(golden_speaker_diarization, config=config)
        
        assert len(result) == len(golden_formatted_speakers)
        
        # First occurrence of each speaker should have label
        for i, (actual, expected) in enumerate(zip(result, golden_formatted_speakers, strict=True)):
            assert actual["text"] == expected["text"], f"Text mismatch at segment {i}"
            assert actual["speaker"] == expected["speaker"], f"Speaker mismatch at segment {i}"

    def test_edge_cases_handled(self, golden_edge_cases):
        """Test that edge cases are handled without errors."""
        from worker.formatter import format_transcript
        
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "detect_hallucinations": True,
        }
        
        for case_name, segment in golden_edge_cases.items():
            # Should not raise exception
            try:
                result = format_transcript([segment], config=config)
                # Result may be empty or filtered, but should not crash
                assert isinstance(result, list)
            except Exception as e:
                pytest.fail(f"Edge case '{case_name}' raised exception: {e}")

    def test_multilingual_preservation(self, golden_multilingual_segments):
        """Test that multilingual text is preserved correctly."""
        from worker.formatter import format_transcript
        
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        
        result = format_transcript(golden_multilingual_segments, config=config)
        
        assert len(result) == len(golden_multilingual_segments)
        
        # Verify each language's text is preserved
        for i, (actual, expected) in enumerate(zip(result, golden_multilingual_segments, strict=True)):
            # Remove punctuation for comparison
            actual_text = actual["text"].rstrip(".")
            expected_text = expected["text"]
            assert expected_text in actual_text, f"Language text not preserved at segment {i}"
