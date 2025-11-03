"""
Extended tests for transcript formatter with multilingual and edge case coverage.

Tests cover:
- Multilingual text handling (CJK, Arabic, Cyrillic, RTL languages)
- Edge cases: very long text, emoji, mixed scripts
- Deterministic behavior with reproducible outputs
- Performance with large segment lists
- Corner cases in punctuation and capitalization
"""

from worker.formatter import TranscriptFormatter, format_transcript


class TestMultilingualSupport:
    """Tests for handling different languages and scripts."""

    def test_chinese_text_handling(self):
        """Test handling of Chinese (CJK) characters."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "你好世界", "start": 0, "end": 1000},
            {"text": "这是一个测试", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        # Chinese text should have punctuation added
        assert result[0]["text"].endswith(".")
        assert result[1]["text"].endswith(".")
        # Original text preserved
        assert "你好世界" in result[0]["text"]

    def test_japanese_text_handling(self):
        """Test handling of Japanese text (hiragana, katakana, kanji)."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "こんにちは", "start": 0, "end": 1000},
            {"text": "カタカナテスト", "start": 1000, "end": 2000},
            {"text": "漢字のテスト", "start": 2000, "end": 3000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 3
        for seg in result:
            assert seg["text"].endswith(".")

    def test_arabic_rtl_text_handling(self):
        """Test handling of Arabic (RTL) text."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "مرحبا بك", "start": 0, "end": 1000},
            {"text": "هذا اختبار", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        # RTL text should be preserved correctly
        assert "مرحبا" in result[0]["text"]
        assert result[0]["text"].endswith(".")

    def test_cyrillic_text_handling(self):
        """Test handling of Cyrillic script (Russian, Ukrainian, etc.)."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "capitalize_sentences": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "привет мир", "start": 0, "end": 1000},
            {"text": "это тест", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        # First letter should be capitalized
        assert result[0]["text"][0].isupper()
        assert result[1]["text"][0].isupper()

    def test_mixed_script_text(self):
        """Test handling of mixed scripts in same segment."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "Hello 你好 مرحبا", "start": 0, "end": 1000},
            {"text": "Test テスト тест", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        # All scripts should be preserved
        assert "Hello" in result[0]["text"]
        assert "你好" in result[0]["text"]
        assert "مرحبا" in result[0]["text"]

    def test_hindi_devanagari_script(self):
        """Test handling of Hindi/Devanagari script."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "नमस्ते दुनिया", "start": 0, "end": 1000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 1
        assert "नमस्ते" in result[0]["text"]


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_segment_text(self):
        """Test handling of very long segment text."""
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        # Create a very long text (2000+ words)
        long_text = " ".join(["word"] * 2000)
        segments = [
            {"text": long_text, "start": 0, "end": 10000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 1
        # Should handle without error
        assert len(result[0]["text"]) > 1000

    def test_emoji_handling(self):
        """Test that emojis are preserved correctly."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "Hello world 😀 👍", "start": 0, "end": 1000},
            {"text": "Testing 🎉 🎊 🎈", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        # Emojis should be preserved
        assert "😀" in result[0]["text"]
        assert "👍" in result[0]["text"]
        assert "🎉" in result[1]["text"]

    def test_numbers_and_symbols(self):
        """Test handling of numbers and mathematical symbols."""
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "The price is $19.99", "start": 0, "end": 1000},
            {"text": "2 + 2 = 4", "start": 1000, "end": 2000},
            {"text": "Temperature: -5°C", "start": 2000, "end": 3000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 3
        # Numbers and symbols should be preserved
        assert "$19.99" in result[0]["text"]
        assert "2 + 2 = 4" in result[1]["text"]
        assert "-5°C" in result[2]["text"]

    def test_url_and_email_handling(self):
        """Test that URLs and emails are preserved."""
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "Visit https://example.com", "start": 0, "end": 1000},
            {"text": "Email me at test@example.com", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 2
        assert "https://example.com" in result[0]["text"]
        assert "test@example.com" in result[1]["text"]

    def test_consecutive_punctuation(self):
        """Test handling of consecutive punctuation marks."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "What?!", "start": 0, "end": 1000},
            {"text": "Really...?", "start": 1000, "end": 2000},
            {"text": "No!!!", "start": 2000, "end": 3000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 3
        # Should not add extra punctuation when already present
        assert not result[0]["text"].endswith("?!.")
        assert not result[1]["text"].endswith("...?.")

    def test_single_character_segments(self):
        """Test handling of single character segments."""
        config = {
            "enabled": True,
            "detect_hallucinations": False,  # Don't filter short segments
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "a", "start": 0, "end": 100},
            {"text": "I", "start": 100, "end": 200},
            {"text": "?", "start": 200, "end": 300},
        ]
        
        result = formatter.format_segments(segments)
        
        # Should preserve all single-character segments when detect_hallucinations is False
        assert len(result) == 3
        assert [seg["text"] for seg in result] == ["a", "I", "?"]

    def test_whitespace_only_segments(self):
        """Test filtering of whitespace-only segments."""
        config = {
            "enabled": True,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "   ", "start": 0, "end": 1000},
            {"text": "\t\n\r", "start": 1000, "end": 2000},
            {"text": "Valid text", "start": 2000, "end": 3000},
            {"text": "     ", "start": 3000, "end": 4000},
        ]
        
        result = formatter.format_segments(segments)
        
        # Only valid segment should remain
        assert len(result) == 1
        assert result[0]["text"] == "Valid text"


class TestDeterministicBehavior:
    """Tests for deterministic and reproducible behavior."""

    def test_consistent_output_multiple_runs(self):
        """Test that same input produces same output across runs."""
        config = {
            "enabled": True,
            "normalize_unicode": True,
            "normalize_whitespace": True,
            "remove_fillers": True,
            "filler_level": 2,
            "add_sentence_punctuation": True,
            "capitalize_sentences": True,
        }
        
        segments = [
            {"text": "um hello like you know", "start": 0, "end": 1000},
            {"text": "this is basically a test", "start": 1000, "end": 2000},
        ]
        
        # Run formatting multiple times
        results = []
        for _ in range(5):
            formatter = TranscriptFormatter(config=config)
            result = formatter.format_segments(segments.copy())
            results.append(result)
        
        # All results should be identical
        for i, result in enumerate(results[1:], start=1):
            assert len(results[0]) == len(result)
            for j in range(len(results[0])):
                assert results[0][j]["text"] == result[j]["text"]
                assert results[0][j]["start"] == result[j]["start"]
                assert results[0][j]["end"] == result[j]["end"]

    def test_segment_timing_deterministic(self):
        """Test that segment splitting produces deterministic timings."""
        config = {
            "enabled": True,
            "segment_by_sentences": True,
        }
        
        segments = [
            {"text": "First sentence. Second sentence. Third sentence.", "start": 0, "end": 3000},
        ]
        
        # Run multiple times
        results = []
        for _ in range(3):
            formatter = TranscriptFormatter(config=config)
            result = formatter.format_segments(segments.copy())
            results.append(result)
        
        # Timings should be identical
        for i, result in enumerate(results[1:], start=1):
            assert len(results[0]) == len(result)
            for j in range(len(results[0])):
                assert results[0][j]["start"] == result[j]["start"]
                assert results[0][j]["end"] == result[j]["end"]


class TestPerformance:
    """Tests for performance with large datasets."""

    def test_handles_large_segment_list(self):
        """Test that formatter handles large number of segments efficiently."""
        config = {
            "enabled": True,
            "normalize_whitespace": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        # Create 1000 segments
        segments = [
            {"text": f"Segment number {i}", "start": i * 1000, "end": (i + 1) * 1000}
            for i in range(1000)
        ]
        
        result = formatter.format_segments(segments)
        
        # Should complete without timeout or error
        assert len(result) == 1000

    def test_handles_merge_with_many_short_segments(self):
        """Test merging with many short segments."""
        config = {
            "enabled": True,
            "merge_short_segments": True,
            "min_segment_length_ms": 2000,
            "max_gap_for_merge_ms": 500,
        }
        formatter = TranscriptFormatter(config=config)
        
        # Create 100 short segments with small gaps
        segments = [
            {"text": f"Short {i}", "start": i * 600, "end": i * 600 + 300}
            for i in range(100)
        ]
        
        result = formatter.format_segments(segments)
        
        # Should merge many segments
        assert len(result) < len(segments)


class TestCornerCasesPunctuation:
    """Tests for punctuation edge cases."""

    def test_already_has_multiple_punctuation(self):
        """Test text that already has proper punctuation."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "Hello! How are you? I'm fine.", "start": 0, "end": 3000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert len(result) == 1
        # Should not add extra punctuation
        assert not result[0]["text"].endswith("..")

    def test_exclamation_and_question_marks(self):
        """Test that ! and ? are treated as terminal punctuation."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "What", "start": 0, "end": 1000},
            {"text": "Amazing", "start": 1000, "end": 2000},
            {"text": "Really", "start": 2000, "end": 3000},
        ]
        
        result = formatter.format_segments(segments)
        
        # All should get terminal punctuation
        for seg in result:
            assert seg["text"][-1] in ".!?"


class TestCornerCasesCapitalization:
    """Tests for capitalization edge cases."""

    def test_all_lowercase_sentence(self):
        """Test capitalizing all lowercase sentence."""
        config = {
            "enabled": True,
            "capitalize_sentences": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "this is all lowercase", "start": 0, "end": 1000},
        ]
        
        result = formatter.format_segments(segments)
        
        assert result[0]["text"][0].isupper()

    def test_preserves_acronyms_in_all_caps(self):
        """Test that acronyms are preserved when fixing all caps."""
        config = {
            "enabled": True,
            "fix_all_caps": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "NASA AND FBI ARE HERE", "start": 0, "end": 1000},
            {"text": "THE USA IS GREAT", "start": 1000, "end": 2000},
        ]
        
        result = formatter.format_segments(segments)
        
        # Acronyms should be preserved
        assert "NASA" in result[0]["text"]
        assert "FBI" in result[0]["text"]
        assert "USA" in result[1]["text"]

    def test_mixed_case_not_affected(self):
        """Test that mixed case text is not changed."""
        config = {
            "enabled": True,
            "fix_all_caps": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "This is Mixed Case", "start": 0, "end": 1000},
        ]
        
        result = formatter.format_segments(segments)
        
        # Should remain unchanged
        assert result[0]["text"] == "This is Mixed Case"


class TestLanguageSpecificBehavior:
    """Tests for language-specific formatting rules."""

    def test_no_filler_removal_for_non_english(self):
        """Test that filler removal doesn't break non-English text."""
        config = {
            "enabled": True,
            "remove_fillers": True,
            "filler_level": 2,
            "normalize_whitespace": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        # "like" is a filler in English, but might be meaningful in other contexts
        segments = [
            {"text": "我喜欢这个", "start": 0, "end": 1000},  # Chinese: "I like this"
        ]
        
        result = formatter.format_segments(segments)
        
        # Chinese text should be preserved
        assert len(result) == 1
        assert "喜欢" in result[0]["text"]

    def test_punctuation_with_various_scripts(self):
        """Test punctuation addition works with various scripts."""
        config = {
            "enabled": True,
            "add_sentence_punctuation": True,
        }
        formatter = TranscriptFormatter(config=config)
        
        segments = [
            {"text": "English text", "start": 0, "end": 1000},
            {"text": "中文文本", "start": 1000, "end": 2000},
            {"text": "Русский текст", "start": 2000, "end": 3000},
            {"text": "النص العربي", "start": 3000, "end": 4000},
        ]
        
        result = formatter.format_segments(segments)
        
        # All should have punctuation added
        for seg in result:
            assert seg["text"].endswith(".")
