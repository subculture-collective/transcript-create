"""Tests for worker.diarize module."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from worker import diarize


class TestDiarizeAndAlign:
    """Tests for diarize_and_align function."""

    @patch("worker.diarize._get_pipeline")
    def test_diarize_and_align_success(self, mock_get_pipeline, tmp_path):
        """Test successful diarization and alignment."""
        # Create mock pyannote pipeline
        mock_segment1 = Mock()
        mock_segment1.start = 0.0
        mock_segment1.end = 5.0

        mock_segment2 = Mock()
        mock_segment2.start = 5.0
        mock_segment2.end = 10.0

        mock_diar = Mock()
        mock_diar.itertracks.return_value = [
            (mock_segment1, "track1", "SPEAKER_00"),
            (mock_segment2, "track2", "SPEAKER_01"),
        ]

        mock_pipeline = Mock()
        mock_pipeline.return_value = mock_diar
        mock_get_pipeline.return_value = mock_pipeline

        # Input whisper segments
        whisper_segments = [
            {"start": 1.0, "end": 4.0, "text": "First segment"},
            {"start": 6.0, "end": 9.0, "text": "Second segment"},
        ]

        wav_path = tmp_path / "audio.wav"
        wav_path.touch()

        result = diarize.diarize_and_align(wav_path, whisper_segments)

        # Should have assigned speakers
        assert len(result) == 2
        assert result[0]["speaker"] == "Speaker 1"
        assert result[0]["speaker_label"] == "Speaker 1"
        assert result[0]["text"] == "First segment"
        assert result[1]["speaker"] == "Speaker 2"
        assert result[1]["speaker_label"] == "Speaker 2"
        assert result[1]["text"] == "Second segment"

    @patch("worker.diarize._get_pipeline")
    def test_speaker_label_assignment_ordered_by_appearance(self, mock_get_pipeline, tmp_path):
        """Test speaker labels are assigned based on first appearance."""
        mock_seg1 = Mock()
        mock_seg1.start = 5.0
        mock_seg1.end = 10.0

        mock_seg2 = Mock()
        mock_seg2.start = 0.0
        mock_seg2.end = 5.0

        mock_diar = Mock()
        # SPEAKER_01 appears first at t=0, SPEAKER_00 appears later at t=5
        mock_diar.itertracks.return_value = [
            (mock_seg2, "track1", "SPEAKER_01"),
            (mock_seg1, "track2", "SPEAKER_00"),
        ]

        mock_pipeline = Mock()
        mock_pipeline.return_value = mock_diar
        mock_get_pipeline.return_value = mock_pipeline

        whisper_segments = [
            {"start": 2.0, "end": 4.0, "text": "First"},
            {"start": 7.0, "end": 9.0, "text": "Second"},
        ]

        wav_path = tmp_path / "audio.wav"
        wav_path.touch()

        result = diarize.diarize_and_align(wav_path, whisper_segments)

        # SPEAKER_01 (appears at 0s) should be "Speaker 1"
        # SPEAKER_00 (appears at 5s) should be "Speaker 2"
        assert result[0]["speaker"] == "Speaker 1"
        assert result[1]["speaker"] == "Speaker 2"

    @patch("worker.diarize._get_pipeline")
    def test_diarize_and_align_no_speaker_match(self, mock_get_pipeline, tmp_path):
        """Test segments without matching speaker get None."""
        mock_seg1 = Mock()
        mock_seg1.start = 0.0
        mock_seg1.end = 5.0

        mock_diar = Mock()
        mock_diar.itertracks.return_value = [(mock_seg1, "track1", "SPEAKER_00")]

        mock_pipeline = Mock()
        mock_pipeline.return_value = mock_diar
        mock_get_pipeline.return_value = mock_pipeline

        # Whisper segment outside diarization range
        whisper_segments = [{"start": 10.0, "end": 15.0, "text": "Outside"}]

        wav_path = tmp_path / "audio.wav"
        wav_path.touch()

        result = diarize.diarize_and_align(wav_path, whisper_segments)

        assert len(result) == 1
        assert result[0]["speaker"] is None
        assert result[0]["speaker_label"] is None

    @patch("worker.diarize._get_pipeline")
    def test_no_hf_token_fallback(self, mock_get_pipeline):
        """Test graceful fallback when HF_TOKEN is missing."""
        mock_get_pipeline.return_value = None

        whisper_segments = [{"start": 0.0, "end": 5.0, "text": "Test"}]

        result = diarize.diarize_and_align(Path("/fake/path.wav"), whisper_segments)

        # Should return original segments unchanged
        assert result == whisper_segments
        assert "speaker" not in result[0]

    @patch("worker.diarize._get_pipeline")
    def test_pyannote_unavailable_fallback(self, mock_get_pipeline):
        """Test graceful fallback when pyannote.audio is not available."""
        mock_get_pipeline.return_value = None

        whisper_segments = [{"start": 0.0, "end": 5.0, "text": "Test"}]

        result = diarize.diarize_and_align(Path("/fake/path.wav"), whisper_segments)

        assert result == whisper_segments

    @patch("worker.diarize._get_pipeline")
    def test_diarization_error_handling(self, mock_get_pipeline):
        """Test diarization errors return original segments."""
        mock_pipeline = Mock()
        mock_pipeline.side_effect = RuntimeError("Diarization failed")
        mock_get_pipeline.return_value = mock_pipeline

        whisper_segments = [{"start": 0.0, "end": 5.0, "text": "Test"}]

        result = diarize.diarize_and_align(Path("/fake/path.wav"), whisper_segments)

        # Should return original segments on error
        assert result == whisper_segments

    @patch("worker.diarize._get_pipeline")
    def test_diarize_and_align_midpoint_matching(self, mock_get_pipeline, tmp_path):
        """Test speaker assignment uses segment midpoint."""
        mock_seg1 = Mock()
        mock_seg1.start = 0.0
        mock_seg1.end = 10.0

        mock_seg2 = Mock()
        mock_seg2.start = 10.0
        mock_seg2.end = 20.0

        mock_diar = Mock()
        mock_diar.itertracks.return_value = [
            (mock_seg1, "track1", "SPEAKER_00"),
            (mock_seg2, "track2", "SPEAKER_01"),
        ]

        mock_pipeline = Mock()
        mock_pipeline.return_value = mock_diar
        mock_get_pipeline.return_value = mock_pipeline

        # Segment with midpoint at 5.0 (within first speaker range)
        whisper_segments = [
            {"start": 2.0, "end": 8.0, "text": "First"},  # midpoint = 5.0
            {"start": 12.0, "end": 18.0, "text": "Second"},  # midpoint = 15.0
        ]

        wav_path = tmp_path / "audio.wav"
        wav_path.touch()

        result = diarize.diarize_and_align(wav_path, whisper_segments)

        assert result[0]["speaker"] == "Speaker 1"
        assert result[1]["speaker"] == "Speaker 2"

    @patch("worker.diarize._get_pipeline")
    def test_diarize_multiple_speakers_same_segment(self, mock_get_pipeline, tmp_path):
        """Test first matching speaker is assigned."""
        mock_seg1 = Mock()
        mock_seg1.start = 0.0
        mock_seg1.end = 10.0

        mock_seg2 = Mock()
        mock_seg2.start = 0.0
        mock_seg2.end = 10.0

        mock_diar = Mock()
        mock_diar.itertracks.return_value = [
            (mock_seg1, "track1", "SPEAKER_00"),
            (mock_seg2, "track2", "SPEAKER_01"),
        ]

        mock_pipeline = Mock()
        mock_pipeline.return_value = mock_diar
        mock_get_pipeline.return_value = mock_pipeline

        whisper_segments = [{"start": 2.0, "end": 8.0, "text": "Test"}]  # midpoint = 5.0

        wav_path = tmp_path / "audio.wav"
        wav_path.touch()

        result = diarize.diarize_and_align(wav_path, whisper_segments)

        assert result[0]["speaker"] == "Speaker 1"


class TestGetPipeline:
    """Tests for _get_pipeline function."""

    @patch("worker.diarize.settings")
    def test_get_pipeline_disabled(self, mock_settings):
        """Test returns None when diarization is disabled."""
        mock_settings.ENABLE_DIARIZATION = False
        mock_settings.HF_TOKEN = "test_token"
        diarize._pipeline = None

        result = diarize._get_pipeline()

        assert result is None

    @patch("worker.diarize.settings")
    def test_get_pipeline_no_hf_token(self, mock_settings):
        """Test returns None when HF_TOKEN is missing."""
        mock_settings.ENABLE_DIARIZATION = True
        mock_settings.HF_TOKEN = ""
        diarize._pipeline = None

        result = diarize._get_pipeline()

        assert result is None

    @patch("worker.diarize.settings")
    def test_get_pipeline_import_error(self, mock_settings):
        """Test returns None when pyannote.audio import fails."""
        mock_settings.ENABLE_DIARIZATION = True
        mock_settings.HF_TOKEN = "test_token"
        mock_settings.DIARIZATION_STRICT = False
        diarize._pipeline = None

        with patch.dict("sys.modules", {"pyannote.audio": None}):
            assert diarize._get_pipeline() is None

    @patch("worker.diarize.settings")
    def test_get_pipeline_caches_result(self, mock_settings):
        """Test pipeline is cached after first load."""
        mock_settings.ENABLE_DIARIZATION = True
        mock_settings.HF_TOKEN = "test_token"

        # Set pre-loaded pipeline
        mock_pipeline = Mock()
        diarize._pipeline = mock_pipeline

        result1 = diarize._get_pipeline()
        result2 = diarize._get_pipeline()

        # Should return same cached instance
        assert result1 is result2
        assert result1 is mock_pipeline

    @patch("worker.diarize.settings")
    def test_get_pipeline_sets_env_vars(self, mock_settings):
        """Test pipeline sets required environment variables."""
        mock_settings.ENABLE_DIARIZATION = True
        mock_settings.HF_TOKEN = "my_token"
        mock_settings.DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
        mock_settings.DIARIZATION_FALLBACK_MODEL = "pyannote/speaker-diarization"
        mock_settings.DIARIZATION_DEVICE = "auto"
        mock_settings.DIARIZATION_STRICT = False
        diarize._pipeline = None
        pipeline_instance = Mock()
        pipeline = Mock(from_pretrained=Mock(return_value=pipeline_instance))

        with (
            patch.dict("sys.modules", {"pyannote.audio": Mock(Pipeline=pipeline)}),
            patch.dict(os.environ, {}, clear=True),
        ):
            assert diarize._get_pipeline() is pipeline_instance
            assert os.environ["HUGGINGFACE_HUB_TOKEN"] == "my_token"
            assert os.environ["HF_TOKEN"] == "my_token"
        pipeline.from_pretrained.assert_called_once_with("pyannote/speaker-diarization-community-1", token="my_token")


def test_strict_audio_preload_failure_does_not_fall_back_to_path(monkeypatch):
    monkeypatch.setattr(diarize.settings, "DIARIZATION_STRICT", True)
    with patch.dict("sys.modules", {"torchaudio": Mock(load=Mock(side_effect=OSError("decode failed")))}):
        with pytest.raises(RuntimeError, match="audio preload"):
            diarize._build_audio_input(Path("missing.wav"))


def test_strict_primary_load_failure_does_not_attempt_fallback(monkeypatch):
    pipeline = Mock(from_pretrained=Mock(side_effect=RuntimeError("primary failed")))
    monkeypatch.setattr(diarize.settings, "ENABLE_DIARIZATION", True)
    monkeypatch.setattr(diarize.settings, "DIARIZATION_STRICT", True)
    monkeypatch.setattr(diarize.settings, "HF_TOKEN", "test-token")
    diarize._pipeline = None
    with patch.dict("sys.modules", {"pyannote.audio": Mock(Pipeline=pipeline)}):
        with pytest.raises(RuntimeError, match="primary model load"):
            diarize._get_pipeline()
    assert pipeline.from_pretrained.call_count == 1


def test_strict_cpu_placement_failure_is_fatal(monkeypatch):
    pipeline_instance = Mock()
    pipeline_instance.to.side_effect = RuntimeError("placement failed")
    pipeline = Mock(from_pretrained=Mock(return_value=pipeline_instance))
    torch = Mock(device=Mock(return_value="cpu-device"))
    monkeypatch.setattr(diarize.settings, "ENABLE_DIARIZATION", True)
    monkeypatch.setattr(diarize.settings, "DIARIZATION_STRICT", True)
    monkeypatch.setattr(diarize.settings, "HF_TOKEN", "test-token")
    monkeypatch.setattr(diarize.settings, "DIARIZATION_MODEL", "primary")
    monkeypatch.setattr(diarize.settings, "DIARIZATION_DEVICE", "cpu")
    diarize._pipeline = None
    with patch.dict("sys.modules", {"pyannote.audio": Mock(Pipeline=pipeline), "torch": torch}):
        with pytest.raises(RuntimeError, match="device placement"):
            diarize._get_pipeline()
