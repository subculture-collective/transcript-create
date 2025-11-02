"""Tests for advanced transcription features."""

import pytest

from worker.quality_presets import QUALITY_PRESETS, get_quality_settings, merge_quality_settings
from worker.vocabulary import VocabularyProcessor


class TestQualityPresets:
    """Test quality preset functionality."""

    def test_all_presets_defined(self):
        """Test that all expected presets are defined."""
        assert "fast" in QUALITY_PRESETS
        assert "balanced" in QUALITY_PRESETS
        assert "accurate" in QUALITY_PRESETS

    def test_fast_preset_config(self):
        """Test fast preset configuration."""
        settings = get_quality_settings("fast")
        assert settings.model == "base"
        assert settings.beam_size == 1
        assert settings.word_timestamps is False
        assert settings.vad_filter is True

    def test_balanced_preset_config(self):
        """Test balanced preset configuration."""
        settings = get_quality_settings("balanced")
        assert settings.model == "large-v3"
        assert settings.beam_size == 5
        assert settings.word_timestamps is True

    def test_accurate_preset_config(self):
        """Test accurate preset configuration."""
        settings = get_quality_settings("accurate")
        assert settings.model == "large-v3"
        assert settings.beam_size == 10
        assert settings.patience == 2.0
        assert settings.word_timestamps is True

    def test_invalid_preset_raises_error(self):
        """Test that invalid preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown quality preset"):
            get_quality_settings("invalid")

    def test_merge_quality_settings(self):
        """Test merging preset with custom overrides."""
        settings = merge_quality_settings("balanced", {"beam_size": 8, "temperature": 0.2})
        assert settings.model == "large-v3"  # from preset
        assert settings.beam_size == 8  # overridden
        assert settings.temperature == 0.2  # overridden
        assert settings.word_timestamps is True  # from preset


class TestVocabularyProcessor:
    """Test custom vocabulary processing."""

    def test_simple_replacement(self):
        """Test basic vocabulary replacement."""
        vocab = {
            "terms": [
                {"pattern": "API", "replacement": "API", "case_sensitive": True},
                {"pattern": "kubernetes", "replacement": "Kubernetes", "case_sensitive": False},
            ]
        }
        processor = VocabularyProcessor([vocab])

        assert processor.process_text("The API is ready") == "The API is ready"
        assert processor.process_text("Using kubernetes cluster") == "Using Kubernetes cluster"
        assert processor.process_text("KUBERNETES is cool") == "Kubernetes is cool"

    def test_case_sensitive_replacement(self):
        """Test case-sensitive vocabulary replacement."""
        vocab = {
            "terms": [{"pattern": "API", "replacement": "Application Programming Interface", "case_sensitive": True}]
        }
        processor = VocabularyProcessor([vocab])

        assert processor.process_text("The API works") == "The Application Programming Interface works"
        assert processor.process_text("The api works") == "The api works"  # lowercase not matched

    def test_word_boundary_matching(self):
        """Test that replacements respect word boundaries."""
        vocab = {"terms": [{"pattern": "test", "replacement": "TEST", "case_sensitive": False}]}
        processor = VocabularyProcessor([vocab])

        assert processor.process_text("This is a test") == "This is a TEST"
        assert processor.process_text("Testing is fun") == "Testing is fun"  # no match due to word boundary

    def test_multiple_vocabularies(self):
        """Test applying multiple vocabularies."""
        vocab1 = {"terms": [{"pattern": "API", "replacement": "API", "case_sensitive": True}]}
        vocab2 = {"terms": [{"pattern": "DB", "replacement": "database", "case_sensitive": True}]}
        processor = VocabularyProcessor([vocab1, vocab2])

        text = "Connect API to DB"
        result = processor.process_text(text)
        assert result == "Connect API to database"

    def test_process_segments(self):
        """Test processing transcript segments."""
        vocab = {
            "terms": [{"pattern": "API", "replacement": "Application Programming Interface", "case_sensitive": True}]
        }
        processor = VocabularyProcessor([vocab])

        segments = [
            {"start": 0, "end": 1000, "text": "The API is ready"},
            {"start": 1000, "end": 2000, "text": "Call the API endpoint"},
        ]

        result = processor.process_segments(segments)
        assert result[0]["text"] == "The Application Programming Interface is ready"
        assert result[1]["text"] == "Call the Application Programming Interface endpoint"
        assert result[0]["start"] == 0  # timing preserved
        assert result[1]["end"] == 2000  # timing preserved

    def test_empty_vocabulary(self):
        """Test that empty vocabulary does nothing."""
        processor = VocabularyProcessor([])
        text = "Original text"
        assert processor.process_text(text) == text

    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns."""
        vocab = {"terms": [{"pattern": "[invalid", "replacement": "valid", "case_sensitive": False}]}
        # Should not raise exception, just skip invalid patterns
        processor = VocabularyProcessor([vocab])
        text = "Some text"
        # Should return text unchanged since pattern is invalid
        assert text in processor.process_text(text)


class TestSchemas:
    """Test schema validation for advanced features."""

    def test_quality_settings_input_validation(self):
        """Test QualitySettingsInput schema validation."""
        from pydantic import ValidationError

        from app.schemas import QualitySettingsInput

        # Valid input
        valid = QualitySettingsInput(preset="balanced", language="en", beam_size=7)
        assert valid.preset == "balanced"
        assert valid.language == "en"
        assert valid.beam_size == 7

        # Invalid beam size (out of range)
        with pytest.raises(ValidationError):
            QualitySettingsInput(beam_size=20)  # > 10

        # Invalid temperature
        with pytest.raises(ValidationError):
            QualitySettingsInput(temperature=2.0)  # > 1.0

    def test_vocabulary_term_schema(self):
        """Test VocabularyTerm schema."""
        from app.schemas import VocabularyTerm

        term = VocabularyTerm(pattern="API", replacement="Application Programming Interface", case_sensitive=True)
        assert term.pattern == "API"
        assert term.replacement == "Application Programming Interface"
        assert term.case_sensitive is True

        # Default case_sensitive is False
        term2 = VocabularyTerm(pattern="test", replacement="TEST")
        assert term2.case_sensitive is False

    def test_vocabulary_create_schema(self):
        """Test VocabularyCreate schema."""
        from app.schemas import VocabularyCreate, VocabularyTerm

        terms = [
            VocabularyTerm(pattern="API", replacement="API"),
            VocabularyTerm(pattern="DB", replacement="database"),
        ]
        vocab = VocabularyCreate(name="Tech Terms", terms=terms, is_global=False)
        assert vocab.name == "Tech Terms"
        assert len(vocab.terms) == 2
        assert vocab.is_global is False
