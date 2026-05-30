import uuid

from app.transcripts.service import TranscriptPresentationService
from worker.formatter import TranscriptFormatter


def test_raw_mode_preserves_whitespace_and_speaker():
    service = TranscriptPresentationService()
    seg = service.from_db_row((10, 20, "  hello\t world  ", "Speaker 1"))

    response = service.present_raw(uuid.uuid4(), [seg])

    assert response.segments[0].text == "  hello\t world  "
    assert response.segments[0].speaker_label == "Speaker 1"


def test_cleaned_mode_normalizes_whitespace_and_preserves_speaker():
    service = TranscriptPresentationService()
    seg = service.from_db_row((0, 1000, "  hello   world  ", "Speaker 2"))

    response = service.present_cleaned(uuid.uuid4(), [seg])

    assert response.segments[0].speaker_label == "Speaker 2"
    assert response.segments[0].text_cleaned.startswith("Hello world")
    assert "  " not in response.segments[0].text_cleaned


def test_cleaned_config_matches_expected_boundary_settings():
    service = TranscriptPresentationService()
    response = service.present_cleaned(uuid.uuid4(), [service.from_db_row((0, 1, "hello", None))])

    assert response.cleanup_config.segment_sentences is False
    assert response.cleanup_config.merge_short_segments is False
    assert response.cleanup_config.speaker_format == "structured"


def test_cleaned_config_reports_formatter_internal_punctuation_setting():
    formatter = TranscriptFormatter(
        config={
            "enabled": True,
            "add_internal_punctuation": True,
        }
    )
    service = TranscriptPresentationService(formatter=formatter)

    response = service.present_cleaned(uuid.uuid4(), [service.from_db_row((0, 1, "hello", None))])

    assert response.cleanup_config.add_internal_punctuation is True
