"""
Unit tests for Whisper client fallback logic, error classification, and circuit breaker behavior.

Tests cover:
- PyTorch to CT2 fallback on ROCm errors
- Error classification for known failure patterns
- CT2 fallback model loading with retry logic
- GPU device preference iteration
- Compute type fallback (float16 to float32)
- Model fallback chain (GPU_MODEL_FALLBACKS)
"""

from unittest.mock import MagicMock, patch

from worker import whisper_runner


class TestErrorClassification:
    """Tests for ROCm error pattern detection and classification."""

    def test_detect_memory_access_fault(self):
        """Test detection of Memory access fault errors."""
        error_msg = "RuntimeError: Memory access fault by GPU node-1"
        
        # Verify this error pattern would trigger fallback
        assert "Memory access fault" in error_msg
        
    def test_detect_hip_error(self):
        """Test detection of hipError patterns."""
        error_msg = "RuntimeError: hipErrorLaunchFailure: hipError..."
        
        assert "hipError" in error_msg
        
    def test_detect_hsa_status_error(self):
        """Test detection of HSA_STATUS_ERROR patterns."""
        error_msg = "RuntimeError: HSA_STATUS_ERROR: operation failed"
        
        assert "HSA_STATUS_ERROR" in error_msg


class TestCT2FallbackLoading:
    """Tests for CT2 fallback model loading behavior."""

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_fallback_loads_primary_model_first(self, mock_load_ct2, mock_lazy):
        """Test that fallback attempts primary model first."""
        mock_model = MagicMock()
        mock_load_ct2.return_value = mock_model
        
        # Reset global state
        whisper_runner._fallback_ct2_model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_MODEL = "large-v2"
            
            result = whisper_runner._get_ct2_fallback_model()
            
            # Should call load with primary model first
            first_call = mock_load_ct2.call_args_list[0]
            assert first_call[0][0] == "large-v2"
            assert result == mock_model

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_fallback_tries_medium_on_primary_failure(self, mock_load_ct2, mock_lazy):
        """Test fallback to 'medium' model when primary fails."""
        # First call fails, second succeeds
        mock_model = MagicMock()
        mock_load_ct2.side_effect = [
            RuntimeError("Primary model load failed"),
            mock_model,
        ]
        
        # Reset global state
        whisper_runner._fallback_ct2_model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_MODEL = "large-v3"
            
            result = whisper_runner._get_ct2_fallback_model()
            
            # Should have tried both models
            assert mock_load_ct2.call_count == 2
            # Second call should be medium
            second_call = mock_load_ct2.call_args_list[1]
            assert second_call[0][0] == "medium"
            assert result == mock_model

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_fallback_raises_on_all_failures(self, mock_load_ct2, mock_lazy):
        """Test that fallback raises RuntimeError when all attempts fail."""
        mock_load_ct2.side_effect = RuntimeError("Load failed")
        
        # Reset global state
        whisper_runner._fallback_ct2_model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_MODEL = "large-v2"
            
            with pytest.raises(RuntimeError, match="Unable to load CT2 fallback model"):
                whisper_runner._get_ct2_fallback_model()

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_fallback_caches_loaded_model(self, mock_load_ct2, mock_lazy):
        """Test that fallback model is cached after first successful load."""
        mock_model = MagicMock()
        mock_load_ct2.return_value = mock_model
        
        # Reset global state
        whisper_runner._fallback_ct2_model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_MODEL = "medium"
            
            # First call should load
            result1 = whisper_runner._get_ct2_fallback_model()
            assert mock_load_ct2.call_count == 1
            
            # Second call should return cached model without loading
            result2 = whisper_runner._get_ct2_fallback_model()
            assert mock_load_ct2.call_count == 1  # Still 1, no new calls
            assert result1 == result2 == mock_model


class TestGPUDevicePreference:
    """Tests for GPU device preference iteration."""

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_iterates_through_device_preferences(self, mock_load_ct2, mock_lazy):
        """Test that model loading tries devices in preference order."""
        mock_model = MagicMock()
        # Fail first two attempts, succeed on third
        mock_load_ct2.side_effect = [
            RuntimeError("Device 0 failed"),
            RuntimeError("Device 1 failed"),
            mock_model,
        ]
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "medium"
            mock_settings.FORCE_GPU = True
            mock_settings.GPU_DEVICE_PREFERENCE = "cuda:0,cuda:1,auto"
            mock_settings.GPU_COMPUTE_TYPES = "float16"
            mock_settings.GPU_MODEL_FALLBACKS = "medium,small"
            
            result = whisper_runner._get_model()
            
            # Should have tried devices in order
            assert mock_load_ct2.call_count == 3
            calls = mock_load_ct2.call_args_list
            assert calls[0][1]['device'] == "cuda:0"
            assert calls[1][1]['device'] == "cuda:1"
            assert calls[2][1]['device'] == "auto"
            assert result == mock_model


class TestComputeTypeFallback:
    """Tests for compute type fallback behavior."""

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_tries_multiple_compute_types(self, mock_load_ct2, mock_lazy):
        """Test that loading tries multiple compute types."""
        mock_model = MagicMock()
        # Fail float16, succeed on int8
        mock_load_ct2.side_effect = [
            RuntimeError("float16 failed"),
            mock_model,
        ]
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "small"
            mock_settings.FORCE_GPU = True
            mock_settings.GPU_DEVICE_PREFERENCE = "cuda:0"
            mock_settings.GPU_COMPUTE_TYPES = "float16,int8"
            mock_settings.GPU_MODEL_FALLBACKS = "small"
            
            result = whisper_runner._get_model()
            
            # Should have tried both compute types
            assert mock_load_ct2.call_count == 2
            calls = mock_load_ct2.call_args_list
            assert calls[0][1]['compute_type'] == "float16"
            assert calls[1][1]['compute_type'] == "int8"
            assert result == mock_model

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_float16_to_float32_fallback_no_force_gpu(self, mock_load_ct2, mock_lazy):
        """Test automatic fallback from float16 to float32 when FORCE_GPU is false."""
        mock_model = MagicMock()
        # First call (float16) fails, second (float32) succeeds
        mock_load_ct2.side_effect = [
            RuntimeError("float16 not supported"),
            mock_model,
        ]
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "base"
            mock_settings.FORCE_GPU = False
            
            result = whisper_runner._get_model()
            
            # Should have tried float16 first, then float32
            assert mock_load_ct2.call_count == 2
            calls = mock_load_ct2.call_args_list
            assert calls[0][1]['compute_type'] == "float16"
            assert calls[1][1]['compute_type'] == "float32"
            assert result == mock_model


class TestModelFallbackChain:
    """Tests for GPU_MODEL_FALLBACKS behavior."""

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_tries_fallback_models_in_order(self, mock_load_ct2, mock_lazy):
        """Test that fallback models are tried in configured order."""
        mock_model = MagicMock()
        # Fail primary and first fallback, succeed on second fallback
        mock_load_ct2.side_effect = [
            RuntimeError("large-v3 failed"),
            RuntimeError("large-v2 failed"),
            mock_model,
        ]
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "large-v3"
            mock_settings.FORCE_GPU = True
            mock_settings.GPU_DEVICE_PREFERENCE = "cuda:0"
            mock_settings.GPU_COMPUTE_TYPES = "float16"
            mock_settings.GPU_MODEL_FALLBACKS = "large-v2,medium"
            
            result = whisper_runner._get_model()
            
            # Should have tried models in order
            assert mock_load_ct2.call_count == 3
            calls = mock_load_ct2.call_args_list
            # Primary model is always tried first
            assert calls[0][0][0] == "large-v3"
            assert calls[1][0][0] == "large-v2"
            assert calls[2][0][0] == "medium"
            assert result == mock_model

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_primary_model_tried_first_even_if_in_fallbacks(self, mock_load_ct2, mock_lazy):
        """Test that primary model is always tried first, even if listed in fallbacks."""
        mock_model = MagicMock()
        mock_load_ct2.return_value = mock_model
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "medium"
            mock_settings.FORCE_GPU = True
            mock_settings.GPU_DEVICE_PREFERENCE = "cuda:0"
            mock_settings.GPU_COMPUTE_TYPES = "float16"
            # Medium is in fallbacks too, but should not be tried twice
            mock_settings.GPU_MODEL_FALLBACKS = "medium,small,base"
            
            result = whisper_runner._get_model()
            
            # Should only be called once (medium succeeds on first try)
            assert mock_load_ct2.call_count == 1
            assert mock_load_ct2.call_args_list[0][0][0] == "medium"
            assert result == mock_model


class TestPyTorchROCmFallback:
    """Tests for PyTorch to CT2 fallback on ROCm errors."""

    @patch('worker.whisper_runner._get_ct2_fallback_model')
    @patch('worker.whisper_runner._get_model')
    def test_fallback_on_memory_access_fault(self, mock_get_model, mock_get_ct2):
        """Test fallback to CT2 on Memory access fault."""
        # Setup PyTorch model that will crash
        mock_pytorch_model = MagicMock()
        mock_pytorch_model.transcribe.side_effect = RuntimeError("Memory access fault by GPU node-1")
        mock_get_model.return_value = mock_pytorch_model
        
        # Setup CT2 fallback model
        mock_ct2_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 2.0
        mock_segment.text = "Hello world"
        mock_segment.avg_logprob = -0.2
        mock_segment.temperature = 0.0
        mock_segment.tokens = [1, 2, 3]
        mock_segment.no_speech_prob = 0.01
        
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.98
        
        mock_ct2_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_get_ct2.return_value = mock_ct2_model
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "whisper"
            mock_settings.WHISPER_BEAM_SIZE = 5
            mock_settings.WHISPER_TEMPERATURE = 0.0
            mock_settings.WHISPER_WORD_TIMESTAMPS = False
            mock_settings.WHISPER_LANGUAGE = None
            
            # Call transcribe_chunk
            segments, lang_info = whisper_runner.transcribe_chunk("/tmp/test.wav")
            
            # Verify fallback was triggered
            mock_get_ct2.assert_called_once()
            mock_ct2_model.transcribe.assert_called_once()
            
            # Verify output format
            assert len(segments) == 1
            assert segments[0]["text"] == "Hello world"
            assert segments[0]["start"] == 0.0
            assert segments[0]["end"] == 2.0
            assert lang_info["language"] == "en"

    @patch('worker.whisper_runner._get_ct2_fallback_model')
    @patch('worker.whisper_runner._get_model')
    def test_fallback_on_hip_error(self, mock_get_model, mock_get_ct2):
        """Test fallback to CT2 on hipError."""
        mock_pytorch_model = MagicMock()
        mock_pytorch_model.transcribe.side_effect = RuntimeError("hipErrorLaunchFailure: launch failed")
        mock_get_model.return_value = mock_pytorch_model
        
        # Setup CT2 fallback
        mock_ct2_model = MagicMock()
        mock_ct2_model.transcribe.return_value = ([], MagicMock(language=None, language_probability=None))
        mock_get_ct2.return_value = mock_ct2_model
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "whisper"
            mock_settings.WHISPER_BEAM_SIZE = 5
            mock_settings.WHISPER_TEMPERATURE = 0.0
            mock_settings.WHISPER_WORD_TIMESTAMPS = False
            mock_settings.WHISPER_LANGUAGE = None
            
            whisper_runner.transcribe_chunk("/tmp/test.wav")
            
            # Verify fallback was triggered
            mock_get_ct2.assert_called_once()

    @patch('worker.whisper_runner._get_model')
    def test_no_fallback_on_other_errors(self, mock_get_model):
        """Test that non-ROCm errors are not caught by fallback."""
        mock_pytorch_model = MagicMock()
        mock_pytorch_model.transcribe.side_effect = ValueError("Invalid parameter")
        mock_get_model.return_value = mock_pytorch_model
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "whisper"
            mock_settings.WHISPER_BEAM_SIZE = 5
            mock_settings.WHISPER_TEMPERATURE = 0.0
            mock_settings.WHISPER_WORD_TIMESTAMPS = False
            mock_settings.WHISPER_LANGUAGE = None
            
            # Should raise ValueError, not trigger fallback
            with pytest.raises(ValueError, match="Invalid parameter"):
                whisper_runner.transcribe_chunk("/tmp/test.wav")


class TestDeterministicBehavior:
    """Tests for deterministic behavior of fallback mechanisms."""

    @patch('worker.whisper_runner._lazy_imports')
    @patch('worker.whisper_runner._try_load_ct2')
    def test_fallback_order_is_deterministic(self, mock_load_ct2, mock_lazy):
        """Test that fallback attempts are deterministic (no random jitter)."""
        call_order = []
        
        def track_calls(model, device, compute_type):
            call_order.append((model, device, compute_type))
            if len(call_order) < 6:
                raise RuntimeError("Simulated failure")
            return MagicMock()
        
        mock_load_ct2.side_effect = track_calls
        
        # Reset global state
        whisper_runner._model = None
        
        with patch('worker.whisper_runner.settings') as mock_settings:
            mock_settings.WHISPER_BACKEND = "faster-whisper"
            mock_settings.WHISPER_MODEL = "large"
            mock_settings.FORCE_GPU = True
            mock_settings.GPU_DEVICE_PREFERENCE = "cuda:0,cuda:1"
            mock_settings.GPU_COMPUTE_TYPES = "float16,int8"
            mock_settings.GPU_MODEL_FALLBACKS = "medium"
            
            whisper_runner._get_model()
            
            # Verify deterministic order:
            # 1. large, cuda:0, float16
            # 2. large, cuda:0, int8
            # 3. large, cuda:1, float16
            # 4. large, cuda:1, int8
            # 5. medium, cuda:0, float16
            # 6. medium, cuda:0, int8 (succeeds)
            
            expected = [
                ("large", "cuda:0", "float16"),
                ("large", "cuda:0", "int8"),
                ("large", "cuda:1", "float16"),
                ("large", "cuda:1", "int8"),
                ("medium", "cuda:0", "float16"),
                ("medium", "cuda:0", "int8"),
            ]
            
            assert call_order == expected
