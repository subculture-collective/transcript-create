"""Tests for worker.whisper_runner module."""

from unittest.mock import Mock, patch

import pytest

from worker import whisper_runner


class TestTranscribeChunkFasterWhisper:
    """Tests for transcribe_chunk with faster-whisper backend."""

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_faster_whisper_success(self, mock_settings, mock_get_model, tmp_path):
        """Test successful transcription with faster-whisper."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"

        # Create mock model and segments
        mock_segment = Mock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " Hello world"
        mock_segment.avg_logprob = -0.5
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1, 2, 3, 4]
        mock_segment.no_speech_prob = 0.01

        mock_model = Mock()
        mock_model.transcribe.return_value = ([mock_segment], Mock())
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 5.0
        assert result[0]["text"] == "Hello world"
        assert result[0]["avg_logprob"] == -0.5
        assert result[0]["temperature"] == 0.0
        assert result[0]["token_count"] == 4
        assert result[0]["confidence"] == 0.01

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_faster_whisper_multiple_segments(self, mock_settings, mock_get_model, tmp_path):
        """Test transcription with multiple segments."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"

        # Create multiple mock segments
        segments = []
        for i in range(3):
            seg = Mock()
            seg.start = float(i * 5)
            seg.end = float((i + 1) * 5)
            seg.text = f" Segment {i}"
            seg.avg_logprob = -0.3
            seg.temperature = 0.0
            seg.tokens = [1, 2]
            seg.no_speech_prob = 0.02
            segments.append(seg)

        mock_model = Mock()
        mock_model.transcribe.return_value = (segments, Mock())
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        assert len(result) == 3
        for i, seg in enumerate(result):
            assert seg["text"] == f"Segment {i}"
            assert seg["start"] == i * 5
            assert seg["end"] == (i + 1) * 5

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_faster_whisper_strips_whitespace(self, mock_settings, mock_get_model, tmp_path):
        """Test that text is stripped of leading/trailing whitespace."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"

        mock_segment = Mock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = "  Text with spaces  "
        mock_segment.avg_logprob = -0.5
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1, 2]
        mock_segment.no_speech_prob = None

        mock_model = Mock()
        mock_model.transcribe.return_value = ([mock_segment], Mock())
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        assert result[0]["text"] == "Text with spaces"


class TestTranscribeChunkPyTorch:
    """Tests for transcribe_chunk with PyTorch whisper backend."""

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_pytorch_success(self, mock_settings, mock_get_model, tmp_path):
        """Test successful transcription with PyTorch whisper."""
        mock_settings.WHISPER_BACKEND = "whisper"

        mock_model = Mock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": " Hello PyTorch",
                    "avg_logprob": -0.4,
                    "temperature": 0.0,
                    "tokens": [1, 2, 3],
                }
            ]
        }
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 5.0
        assert result[0]["text"] == "Hello PyTorch"
        assert result[0]["avg_logprob"] == -0.4
        assert result[0]["token_count"] == 3
        assert result[0]["confidence"] is None  # PyTorch doesn't provide confidence

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_pytorch_sdp_context(self, mock_settings, mock_get_model, tmp_path):
        """Test PyTorch transcription uses SDP kernel context."""
        mock_settings.WHISPER_BACKEND = "whisper"

        mock_model = Mock()
        mock_model.transcribe.return_value = {"segments": []}
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        whisper_runner.transcribe_chunk(wav_path)

        # Verify transcribe was called with fp16=False
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs.get("fp16") is False

    @patch("worker.whisper_runner._get_ct2_fallback_model")
    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_pytorch_rocm_fault_fallback(
        self, mock_settings, mock_get_model, mock_ct2_fallback, tmp_path
    ):
        """Test fallback to CT2 on ROCm memory fault."""
        mock_settings.WHISPER_BACKEND = "whisper"

        # Simulate ROCm fault
        mock_model = Mock()
        mock_model.transcribe.side_effect = RuntimeError("Memory access fault by GPU node")
        mock_get_model.return_value = mock_model

        # Setup CT2 fallback
        mock_segment = Mock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " Fallback text"
        mock_segment.avg_logprob = -0.3
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1, 2]

        mock_ct2 = Mock()
        mock_ct2.transcribe.return_value = ([mock_segment], Mock())
        mock_ct2_fallback.return_value = mock_ct2

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        # Should have fallen back to CT2
        assert len(result) == 1
        assert result[0]["text"] == "Fallback text"
        mock_ct2_fallback.assert_called_once()

    @patch("worker.whisper_runner._get_ct2_fallback_model")
    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_pytorch_hip_error_fallback(
        self, mock_settings, mock_get_model, mock_ct2_fallback, tmp_path
    ):
        """Test fallback to CT2 on hipError."""
        mock_settings.WHISPER_BACKEND = "whisper"

        mock_model = Mock()
        mock_model.transcribe.side_effect = RuntimeError("hipErrorInvalidValue")
        mock_get_model.return_value = mock_model

        mock_segment = Mock()
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " HIP fallback"
        mock_segment.avg_logprob = -0.3
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1]

        mock_ct2 = Mock()
        mock_ct2.transcribe.return_value = ([mock_segment], Mock())
        mock_ct2_fallback.return_value = mock_ct2

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        assert len(result) == 1
        assert result[0]["text"] == "HIP fallback"

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_transcribe_chunk_pytorch_non_rocm_error_raises(self, mock_settings, mock_get_model, tmp_path):
        """Test non-ROCm errors are re-raised."""
        mock_settings.WHISPER_BACKEND = "whisper"

        mock_model = Mock()
        mock_model.transcribe.side_effect = RuntimeError("Some other error")
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        with pytest.raises(RuntimeError, match="Some other error"):
            whisper_runner.transcribe_chunk(wav_path)


class TestSegmentFormatting:
    """Tests for segment output schema validation."""

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_segment_formatting_all_fields(self, mock_settings, mock_get_model, tmp_path):
        """Test segment includes all expected fields."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"

        mock_segment = Mock()
        mock_segment.start = 10.5
        mock_segment.end = 15.25
        mock_segment.text = " Test"
        mock_segment.avg_logprob = -0.6
        mock_segment.temperature = 0.2
        mock_segment.tokens = [1, 2, 3, 4, 5]
        mock_segment.no_speech_prob = 0.05

        mock_model = Mock()
        mock_model.transcribe.return_value = ([mock_segment], Mock())
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        segment = result[0]
        assert "start" in segment
        assert "end" in segment
        assert "text" in segment
        assert "avg_logprob" in segment
        assert "temperature" in segment
        assert "token_count" in segment
        assert "confidence" in segment

    @patch("worker.whisper_runner._get_model")
    @patch("worker.whisper_runner.settings")
    def test_segment_formatting_missing_no_speech_prob(self, mock_settings, mock_get_model, tmp_path):
        """Test segment handles missing no_speech_prob gracefully."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"

        mock_segment = Mock(spec=["start", "end", "text", "avg_logprob", "temperature", "tokens"])
        mock_segment.start = 0.0
        mock_segment.end = 5.0
        mock_segment.text = " Test"
        mock_segment.avg_logprob = -0.5
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1, 2]
        # Explicitly ensure no_speech_prob doesn't exist by not adding it to spec

        mock_model = Mock()
        mock_model.transcribe.return_value = ([mock_segment], Mock())
        mock_get_model.return_value = mock_model

        wav_path = tmp_path / "test.wav"
        wav_path.touch()

        result = whisper_runner.transcribe_chunk(wav_path)

        # Should handle gracefully - getattr with None default
        assert "confidence" in result[0]


class TestModelLoading:
    """Tests for model loading logic."""

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_model_faster_whisper_auto(self, mock_settings, mock_try_load):
        """Test loading faster-whisper model with auto device."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"
        mock_settings.WHISPER_MODEL = "medium"
        mock_settings.FORCE_GPU = False

        # Reset global model
        whisper_runner._model = None

        mock_model = Mock()
        mock_try_load.return_value = mock_model

        result = whisper_runner._get_model()

        assert result == mock_model
        # Should try float16 first
        mock_try_load.assert_called()

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_model_force_gpu_fallback(self, mock_settings, mock_try_load):
        """Test GPU model fallback logic."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"
        mock_settings.WHISPER_MODEL = "large-v3"
        mock_settings.FORCE_GPU = True
        mock_settings.GPU_DEVICE_PREFERENCE = "cuda,hip"
        mock_settings.GPU_COMPUTE_TYPES = "float16,float32"
        mock_settings.GPU_MODEL_FALLBACKS = "medium,small"

        whisper_runner._model = None

        # First attempts fail, last succeeds
        mock_try_load.side_effect = [
            RuntimeError("Failed"),
            RuntimeError("Failed"),
            RuntimeError("Failed"),
            Mock(),  # Success on 4th try
        ]

        result = whisper_runner._get_model()

        assert result is not None
        assert mock_try_load.call_count == 4

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_model_force_gpu_all_fail(self, mock_settings, mock_try_load):
        """Test FORCE_GPU raises when all configs fail."""
        mock_settings.WHISPER_BACKEND = "faster-whisper"
        mock_settings.WHISPER_MODEL = "large-v3"
        mock_settings.FORCE_GPU = True
        mock_settings.GPU_DEVICE_PREFERENCE = "cuda"
        mock_settings.GPU_COMPUTE_TYPES = "float16"
        mock_settings.GPU_MODEL_FALLBACKS = "large-v3"

        whisper_runner._model = None

        mock_try_load.side_effect = RuntimeError("GPU not available")

        with pytest.raises(RuntimeError, match="no GPU configuration succeeded"):
            whisper_runner._get_model()

    @patch("worker.whisper_runner._try_load_torch")
    @patch("worker.whisper_runner.settings")
    def test_get_model_pytorch_backend(self, mock_settings, mock_try_load):
        """Test loading PyTorch whisper model."""
        mock_settings.WHISPER_BACKEND = "whisper"
        mock_settings.WHISPER_MODEL = "base"
        mock_settings.FORCE_GPU = False

        whisper_runner._model = None

        mock_model = Mock()
        mock_try_load.return_value = mock_model

        result = whisper_runner._get_model()

        assert result == mock_model
        mock_try_load.assert_called_once_with("base", False)


class TestCT2FallbackModel:
    """Tests for CT2 fallback model loading."""

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_ct2_fallback_model_success(self, mock_settings, mock_try_load):
        """Test successful CT2 fallback model loading."""
        mock_settings.WHISPER_MODEL = "large-v3"

        whisper_runner._fallback_ct2_model = None

        mock_model = Mock()
        mock_try_load.return_value = mock_model

        result = whisper_runner._get_ct2_fallback_model()

        assert result == mock_model
        mock_try_load.assert_called_once_with("large-v3", device="auto", compute_type="float32")

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_ct2_fallback_model_medium_fallback(self, mock_settings, mock_try_load):
        """Test fallback to medium model."""
        mock_settings.WHISPER_MODEL = "large-v3"

        whisper_runner._fallback_ct2_model = None

        # First load fails, second succeeds
        mock_model = Mock()
        mock_try_load.side_effect = [RuntimeError("Failed"), mock_model]

        result = whisper_runner._get_ct2_fallback_model()

        assert result == mock_model
        assert mock_try_load.call_count == 2
        # Second call should be for medium model
        second_call = mock_try_load.call_args_list[1]
        assert second_call[0][0] == "medium"

    @patch("worker.whisper_runner._try_load_ct2")
    @patch("worker.whisper_runner.settings")
    def test_get_ct2_fallback_model_all_fail(self, mock_settings, mock_try_load):
        """Test exception when all fallback attempts fail."""
        mock_settings.WHISPER_MODEL = "large-v3"

        whisper_runner._fallback_ct2_model = None

        mock_try_load.side_effect = RuntimeError("Failed")

        with pytest.raises(RuntimeError, match="Unable to load CT2 fallback"):
            whisper_runner._get_ct2_fallback_model()
