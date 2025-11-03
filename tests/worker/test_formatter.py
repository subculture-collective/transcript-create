"""
Unit tests for the transcript formatter module.

Tests cover:
- Text normalization
- Punctuation restoration
- Filler word removal
- Segmentation
- Speaker formatting
- Configuration toggles
- Edge cases and multilingual support
"""

import pytest

from worker.formatter import TranscriptFormatter, format_transcript


class TestTextNormalization:
    """Tests for text normalization features."""

    def test_unicode_normalization(self):
        """Test Unicode NFC normalization."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "normalize_whitespace": False,
            "merge_short_segments": False,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        # Test combining characters (é vs e + combining acute)
        # Using NFD form (decomposed) which will be normalized to NFC
        import unicodedata

        text_nfd = unicodedata.normalize("NFD", "café")  # Decomposed form
        segments = [{"text": text_nfd, "start": 0, "end": 1000}]
        result = formatter.format_segments(segments)

        assert len(result) == 1
        # Result should be NFC normalized (case gets capitalized by other defaults)
        expected = unicodedata.normalize("NFC", "café")
        assert expected.lower() in result[0]["text"].lower()

    def test_whitespace_normalization(self):
        """Test whitespace cleanup."""
        config = {
            "enabled": True,
            "normalize_unicode": False,
            "normalize_whitespace": True,
            "remove_special_tokens": False,
            "merge_short_segments": False,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello  \t  world  \n  test", "start": 0, "end": 1000},
            {"text": "Multiple   spaces   here", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world test"
        assert result[1]["text"] == "Multiple spaces here"

    def test_special_token_removal(self):
        """Test removal of sound event tokens."""
        config = {
            "enabled": True,
            "remove_special_tokens": True,
            "preserve_sound_events": False,
            "normalize_whitespace": True,
            "merge_short_segments": False,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "[MUSIC] Hello world [APPLAUSE]", "start": 0, "end": 1000},
            {"text": "Some text ♪ with music ♫", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world"
        assert result[1]["text"] == "Some text with music"

    def test_preserve_sound_events(self):
        """Test preserving sound event tokens when configured."""
        config = {
            "enabled": True,
            "remove_special_tokens": True,
            "preserve_sound_events": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "[MUSIC] Hello world [APPLAUSE]", "start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        assert "[MUSIC]" in result[0]["text"]
        assert "[APPLAUSE]" in result[0]["text"]


class TestFillerRemoval:
    """Tests for filler word removal."""

    def test_conservative_filler_removal(self):
        """Test level 1 (conservative) filler removal."""
        config = {
            "enabled": True,
            "remove_fillers": True,
            "filler_level": 1,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Um, hello there uh I think", "start": 0, "end": 1000},
            {"text": "Er, this is hmm interesting", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert "um" not in result[0]["text"].lower()
        assert "uh" not in result[0]["text"].lower()
        assert "I think" in result[0]["text"]

    def test_moderate_filler_removal(self):
        """Test level 2 (moderate) filler removal."""
        config = {
            "enabled": True,
            "remove_fillers": True,
            "filler_level": 2,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Like, you know, I mean it's good", "start": 0, "end": 1000},
            {"text": "So basically it's literally amazing", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        # Check that moderate fillers are removed
        assert "like" not in result[0]["text"].lower()
        assert "you know" not in result[0]["text"].lower()
        assert "good" in result[0]["text"]

    def test_aggressive_filler_removal(self):
        """Test level 3 (aggressive) filler removal."""
        config = {
            "enabled": True,
            "remove_fillers": True,
            "filler_level": 3,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "Well, okay, kind of sort of you see right", "start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        # Most fillers should be gone
        assert "well" not in result[0]["text"].lower()
        assert "okay" not in result[0]["text"].lower()

    def test_no_filler_removal(self):
        """Test filler removal disabled."""
        config = {
            "enabled": True,
            "remove_fillers": False,
            "filler_level": 0,
        }
        formatter = TranscriptFormatter(config=config)

        original_text = "Um hello uh there"
        segments = [{"text": original_text, "start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        assert "Um" in result[0]["text"]
        assert "uh" in result[0]["text"]


class TestPunctuation:
    """Tests for punctuation restoration."""

    def test_add_sentence_punctuation(self):
        """Test adding terminal punctuation."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
            "add_internal_punctuation": False,
            "capitalize_sentences": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello world", "start": 0, "end": 1000},
            {"text": "How are you", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world."
        assert result[1]["text"] == "How are you."

    def test_preserve_existing_punctuation(self):
        """Test that existing punctuation is preserved."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello world!", "start": 0, "end": 1000},
            {"text": "How are you?", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world!"
        assert result[1]["text"] == "How are you?"

    def test_capitalize_sentences(self):
        """Test sentence capitalization."""
        config = {
            "enabled": True,
            "capitalize_sentences": True,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "hello world", "start": 0, "end": 1000},
            {"text": "this is a test", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world"
        assert result[1]["text"] == "This is a test"

    def test_fix_all_caps(self):
        """Test fixing inappropriate all-caps text."""
        config = {
            "enabled": True,
            "fix_all_caps": True,
            "add_sentence_punctuation": False,
            "merge_short_segments": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "HELLO WORLD", "start": 0, "end": 1000},
            {"text": "THIS IS A TEST", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello world"
        assert result[1]["text"] == "This is a test"

    def test_internal_punctuation(self):
        """Test adding internal punctuation."""
        config = {
            "enabled": True,
            "add_internal_punctuation": True,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "however this is good", "start": 0, "end": 1000},
            {"text": "I like it and you should too", "start": 1000, "end": 2000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        # Check that commas are added appropriately
        assert "however," in result[0]["text"].lower()


class TestSegmentation:
    """Tests for sentence segmentation."""

    def test_segment_by_sentences(self):
        """Test splitting segments on sentence boundaries."""
        config = {
            "enabled": True,
            "segment_by_sentences": True,
            "merge_short_segments": False,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "Hello world. How are you? I am fine.", "start": 0, "end": 3000}]

        result = formatter.format_segments(segments)

        # Should split into 3 segments
        assert len(result) == 3
        assert "Hello world." in result[0]["text"]
        assert "How are you?" in result[1]["text"]
        assert "I am fine." in result[2]["text"]

        # Check timing is distributed
        assert result[0]["start"] == 0
        # Allow small rounding error in timing
        assert abs(result[2]["end"] - 3000) < 200

    def test_merge_short_segments(self):
        """Test merging short segments."""
        config = {
            "enabled": True,
            "merge_short_segments": True,
            "min_segment_length_ms": 2000,
            "max_gap_for_merge_ms": 500,
            "segment_by_sentences": False,
            "add_sentence_punctuation": False,  # Disable punctuation for this test
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Short", "start": 0, "end": 500},
            {"text": "Also short", "start": 600, "end": 1100},
            {"text": "Longer segment here", "start": 5000, "end": 8000},
        ]

        result = formatter.format_segments(segments)

        # First two should merge due to being short and having small gap
        assert len(result) == 2
        assert "Short Also short" in result[0]["text"]
        assert result[0]["end"] == 1100

    def test_dont_merge_different_speakers(self):
        """Test that segments with different speakers are not merged."""
        config = {
            "enabled": True,
            "merge_short_segments": True,
            "min_segment_length_ms": 2000,
            "max_gap_for_merge_ms": 500,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello", "start": 0, "end": 500, "speaker": "Speaker 1"},
            {"text": "Hi there", "start": 600, "end": 1100, "speaker": "Speaker 2"},
        ]

        result = formatter.format_segments(segments)

        # Should not merge due to different speakers
        assert len(result) == 2
        assert result[0]["speaker"] == "Speaker 1"
        assert result[1]["speaker"] == "Speaker 2"


class TestSpeakerFormatting:
    """Tests for speaker label formatting."""

    def test_inline_format(self):
        """Test inline speaker format (no changes)."""
        config = {
            "enabled": True,
            "speaker_format": "inline",
            "add_sentence_punctuation": False,
            "merge_short_segments": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello", "start": 0, "end": 1000, "speaker": "Speaker 1"},
            {"text": "Hi there", "start": 1000, "end": 2000, "speaker": "Speaker 2"},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        assert result[1]["text"] == "Hi there"

    def test_dialogue_format(self):
        """Test dialogue format with speaker prefixes."""
        config = {
            "enabled": True,
            "speaker_format": "dialogue",
            "add_sentence_punctuation": False,
            "merge_short_segments": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello", "start": 0, "end": 1000, "speaker": "Speaker 1"},
            {"text": "Hi there", "start": 1000, "end": 2000, "speaker": "Speaker 2"},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 2
        assert result[0]["text"] == "Speaker 1: Hello"
        assert result[1]["text"] == "Speaker 2: Hi there"

    def test_structured_format(self):
        """Test structured format with deduplicated speaker labels."""
        config = {
            "enabled": True,
            "speaker_format": "structured",
            "add_sentence_punctuation": False,
            "merge_short_segments": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello", "start": 0, "end": 1000, "speaker": "Speaker 1"},
            {"text": "How are you", "start": 1000, "end": 2000, "speaker": "Speaker 1"},
            {"text": "Fine thanks", "start": 2000, "end": 3000, "speaker": "Speaker 2"},
            {"text": "Good to hear", "start": 3000, "end": 4000, "speaker": "Speaker 2"},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 4
        # First occurrence of each speaker should have prefix
        assert result[0]["text"] == "Speaker 1: Hello"
        assert result[1]["text"] == "How are you"  # Same speaker, no prefix
        assert result[2]["text"] == "Speaker 2: Fine thanks"
        assert result[3]["text"] == "Good to hear"  # Same speaker, no prefix

    def test_speaker_label_fallback(self):
        """Test using speaker_label when speaker is not present."""
        config = {
            "enabled": True,
            "speaker_format": "dialogue",
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "Hello", "start": 0, "end": 1000, "speaker_label": "John"}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        assert result[0]["text"] == "John: Hello"


class TestHallucinationDetection:
    """Tests for hallucination detection."""

    def test_detect_empty_segments(self):
        """Test filtering out empty or too-short segments."""
        config = {
            "enabled": True,
            "detect_hallucinations": True,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Valid text", "start": 0, "end": 1000},
            {"text": "  ", "start": 1000, "end": 2000},
            {"text": "x", "start": 2000, "end": 3000},
        ]

        result = formatter.format_segments(segments)

        # Should only include first valid segment
        assert len(result) == 1
        assert result[0]["text"] == "Valid text"

    def test_detect_repeated_patterns(self):
        """Test detecting repeated word patterns."""
        config = {
            "enabled": True,
            "detect_hallucinations": True,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello world", "start": 0, "end": 1000},
            {"text": "the the the the", "start": 1000, "end": 2000},
            {"text": "Valid text here", "start": 2000, "end": 3000},
        ]

        result = formatter.format_segments(segments)

        # Should filter out repeated pattern
        assert len(result) == 2
        assert "Valid text" in result[1]["text"]

    def test_detect_common_hallucinations(self):
        """Test detecting common Whisper hallucinations."""
        config = {
            "enabled": True,
            "detect_hallucinations": True,
            "add_sentence_punctuation": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Real content", "start": 0, "end": 1000},
            {"text": "Thank you.", "start": 1000, "end": 2000},
            {"text": "Thanks for watching.", "start": 2000, "end": 3000},
            {"text": "More real content", "start": 3000, "end": 4000},
        ]

        result = formatter.format_segments(segments)

        # Should filter out hallucinations
        assert len(result) == 2
        assert result[0]["text"] == "Real content"
        assert result[1]["text"] == "More real content"


class TestConfigurationToggles:
    """Tests for configuration flag toggling."""

    def test_disabled_formatter(self):
        """Test that formatter is no-op when disabled."""
        config = {"enabled": False}
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "um hello WORLD", "start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        assert result[0]["text"] == "um hello WORLD"  # No changes

    def test_selective_transformations(self):
        """Test enabling only specific transformations."""
        config = {
            "enabled": True,
            "normalize_unicode": False,
            "normalize_whitespace": True,
            "remove_special_tokens": False,
            "remove_fillers": False,
            "add_sentence_punctuation": True,
            "capitalize_sentences": False,
            "segment_by_sentences": False,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [{"text": "um  hello   world  ", "start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        assert len(result) == 1
        # Should normalize whitespace and add punctuation, but keep "um"
        assert "um" in result[0]["text"]
        assert result[0]["text"] == "um hello world."


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_segment_list(self):
        """Test handling empty segment list."""
        formatter = TranscriptFormatter()

        result = formatter.format_segments([])

        assert result == []

    def test_segment_with_no_text(self):
        """Test handling segment with missing text field."""
        config = {"enabled": True}
        formatter = TranscriptFormatter(config=config)

        segments = [{"start": 0, "end": 1000}]

        result = formatter.format_segments(segments)

        # Should handle gracefully
        assert len(result) == 0 or result[0]["text"] == ""

    def test_multilingual_text(self):
        """Test handling multilingual text."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Hello world", "start": 0, "end": 1000},
            {"text": "Bonjour le monde", "start": 1000, "end": 2000},
            {"text": "こんにちは世界", "start": 2000, "end": 3000},
            {"text": "Привет мир", "start": 3000, "end": 4000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 4
        # All should have punctuation added
        for seg in result:
            assert seg["text"].endswith(".")

    def test_special_characters(self):
        """Test handling special characters."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)

        segments = [
            {"text": "Price: $19.99", "start": 0, "end": 1000},
            {"text": "Email: test@example.com", "start": 1000, "end": 2000},
            {"text": "Math: 2 + 2 = 4", "start": 2000, "end": 3000},
        ]

        result = formatter.format_segments(segments)

        assert len(result) == 3
        # Special chars should be preserved
        assert "$" in result[0]["text"]
        assert "@" in result[1]["text"]
        assert "+" in result[2]["text"]


class TestConvenienceFunction:
    """Tests for the format_transcript convenience function."""

    def test_format_transcript_with_defaults(self):
        """Test format_transcript function with default config."""
        segments = [
            {"text": "hello world", "start": 0, "end": 1000},
            {"text": "how are you", "start": 1000, "end": 2000},
        ]

        result = format_transcript(segments)

        # Should apply default formatting
        assert len(result) == 2
        assert isinstance(result, list)

    def test_format_transcript_with_custom_config(self):
        """Test format_transcript function with custom config."""
        segments = [{"text": "um hello world", "start": 0, "end": 1000}]

        config = {
            "enabled": True,
            "remove_fillers": True,
            "filler_level": 1,
            "normalize_whitespace": True,
        }

        result = format_transcript(segments, config=config)

        assert len(result) == 1
        assert "um" not in result[0]["text"].lower()

    def test_format_transcript_with_language(self):
        """Test format_transcript function with language parameter."""
        segments = [{"text": "hello world", "start": 0, "end": 1000}]

        result = format_transcript(segments, language="en")

        # Should complete without error
        assert len(result) == 1


class TestRegressionFixtures:
    """Baseline fixture outputs for regression testing."""

    @pytest.fixture
    def sample_whisper_output(self):
        """Sample Whisper transcript output."""
        return [
            {"text": "um hello everyone", "start": 0, "end": 2000},
            {"text": "today we're going to talk about", "start": 2000, "end": 5000},
            {"text": "ARTIFICIAL INTELLIGENCE", "start": 5000, "end": 7000},
            {"text": "[MUSIC] it's really interesting [MUSIC]", "start": 7000, "end": 10000},
            {"text": "like you know i think it's the future", "start": 10000, "end": 13000},
        ]

    @pytest.fixture
    def expected_formatted_output(self):
        """Expected formatted output with default settings."""
        return [
            {"text": "Hello everyone.", "start": 0, "end": 2000},
            {"text": "Today we're going to talk about.", "start": 2000, "end": 5000},
            {"text": "Artificial intelligence.", "start": 5000, "end": 7000},
            {"text": "It's really interesting.", "start": 7000, "end": 10000},
            {"text": "I think it's the future.", "start": 10000, "end": 13000},
        ]

    def test_full_pipeline_formatting(self, sample_whisper_output, expected_formatted_output):
        """Test complete formatting pipeline produces expected output."""
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

        result = format_transcript(sample_whisper_output, config=config)

        assert len(result) == len(expected_formatted_output)

        for i, (actual, expected) in enumerate(zip(result, expected_formatted_output)):
            # Check text is formatted correctly
            assert actual["text"] == expected["text"], f"Mismatch at segment {i}"
            # Check timing is preserved
            assert actual["start"] == expected["start"]
            assert actual["end"] == expected["end"]

    @pytest.fixture
    def youtube_caption_sample(self):
        """Sample YouTube caption output."""
        return [
            {"text": "Hello world", "start": 0, "end": 2000},
            {"text": "this is a test", "start": 2000, "end": 4000},
            {"text": "with youtube captions", "start": 4000, "end": 6000},
        ]

    def test_youtube_caption_formatting(self, youtube_caption_sample):
        """Test formatting YouTube captions."""
        config = {
            "enabled": True,
            "capitalize_sentences": True,
            "add_sentence_punctuation": True,
        }

        result = format_transcript(youtube_caption_sample, config=config)

        assert len(result) == 3
        assert result[0]["text"] == "Hello world."
        assert result[1]["text"] == "This is a test."
        assert result[2]["text"] == "With youtube captions."
