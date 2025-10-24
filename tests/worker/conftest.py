"""Pytest configuration for worker tests."""

import sys
from unittest.mock import MagicMock, Mock

# Mock heavy dependencies for worker unit tests
# These should be mocked before the modules are imported

# Create context manager mock for sdpa_kernel
mock_ctx = MagicMock()
mock_ctx.__enter__ = Mock(return_value=mock_ctx)
mock_ctx.__exit__ = Mock(return_value=False)

mock_sdpa_kernel = Mock(return_value=mock_ctx)
mock_attention = MagicMock()
mock_attention.sdpa_kernel = mock_sdpa_kernel
mock_attention.SDPBackend = Mock()

sys.modules["torch"] = Mock()
sys.modules["torch.nn"] = Mock()
sys.modules["torch.nn.attention"] = mock_attention
sys.modules["torch.backends"] = Mock()
sys.modules["torch.backends.cuda"] = Mock()
sys.modules["torch.cuda"] = Mock()
sys.modules["faster_whisper"] = Mock()
sys.modules["whisper"] = Mock()
sys.modules["pyannote"] = Mock()
sys.modules["pyannote.audio"] = Mock()

