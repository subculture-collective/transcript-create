"""Tests for worker.audio module."""

from pathlib import Path
from unittest.mock import patch

from worker.audio import Chunk, chunk_audio, download_audio, ensure_wav_16k, get_duration_seconds


class TestDownloadAudio:
    """Tests for download_audio function."""

    @patch("worker.audio.subprocess.check_call")
    def test_download_audio_success(self, mock_check_call, tmp_path):
        """Test successful audio download."""
        url = "https://www.youtube.com/watch?v=test123"
        dest_dir = tmp_path / "test_video"
        dest_dir.mkdir()

        result = download_audio(url, dest_dir)

        # Verify the command was called correctly
        expected_out = dest_dir / "raw.m4a"
        expected_cmd = ["yt-dlp", "-v", "-f", "bestaudio", "-o", str(expected_out), url]
        mock_check_call.assert_called_once_with(expected_cmd)

        # Verify return path
        assert result == expected_out

    @patch("worker.audio.subprocess.check_call")
    def test_download_audio_command_structure(self, mock_check_call, tmp_path):
        """Test that download command includes required flags."""
        url = "https://www.youtube.com/watch?v=abc"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        download_audio(url, dest_dir)

        call_args = mock_check_call.call_args[0][0]
        assert call_args[0] == "yt-dlp"
        assert "-f" in call_args
        assert "bestaudio" in call_args
        assert "-o" in call_args
        assert url in call_args


class TestEnsureWav16k:
    """Tests for ensure_wav_16k function."""

    @patch("worker.audio.subprocess.check_call")
    def test_ensure_wav_16k_conversion(self, mock_check_call, tmp_path):
        """Test successful WAV conversion to 16kHz mono."""
        src = tmp_path / "raw.m4a"
        src.touch()

        result = ensure_wav_16k(src)

        # Verify output path
        expected_wav = tmp_path / "audio_16k.wav"
        assert result == expected_wav

        # Verify ffmpeg command
        call_args = mock_check_call.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-i" in call_args
        assert str(src) in call_args
        assert "-ac" in call_args
        assert "1" in call_args  # mono
        assert "-ar" in call_args
        assert "16000" in call_args  # 16kHz
        assert str(expected_wav) in call_args

    @patch("worker.audio.subprocess.check_call")
    def test_ensure_wav_16k_parameters(self, mock_check_call, tmp_path):
        """Test that conversion includes all required parameters."""
        src = tmp_path / "input.mp3"
        src.touch()

        ensure_wav_16k(src)

        call_args = mock_check_call.call_args[0][0]
        # Check for critical parameters
        assert "-ac" in call_args
        assert "-ar" in call_args
        assert "-c:a" in call_args
        assert "pcm_s16le" in call_args


class TestGetDurationSeconds:
    """Tests for get_duration_seconds function."""

    @patch("worker.audio.subprocess.check_output")
    def test_get_duration_seconds_success(self, mock_check_output, tmp_path):
        """Test successful duration extraction."""
        test_file = tmp_path / "test.wav"
        test_file.touch()
        mock_check_output.return_value = b"123.456\n"

        duration = get_duration_seconds(test_file)

        assert duration == 123.456
        # Verify ffprobe command structure
        call_args = mock_check_output.call_args[0][0]
        assert call_args[0] == "ffprobe"
        assert "format=duration" in call_args
        assert str(test_file) in call_args

    @patch("worker.audio.subprocess.check_output")
    def test_get_duration_seconds_integer(self, mock_check_output, tmp_path):
        """Test duration with integer value."""
        test_file = tmp_path / "test.wav"
        test_file.touch()
        mock_check_output.return_value = b"60\n"

        duration = get_duration_seconds(test_file)

        assert duration == 60.0

    @patch("worker.audio.subprocess.check_output")
    def test_get_duration_seconds_whitespace(self, mock_check_output, tmp_path):
        """Test duration parsing with extra whitespace."""
        test_file = tmp_path / "test.wav"
        test_file.touch()
        mock_check_output.return_value = b"  42.5  \n"

        duration = get_duration_seconds(test_file)

        assert duration == 42.5


class TestChunkAudio:
    """Tests for chunk_audio function."""

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_single_no_chunking(self, mock_check_call, mock_duration, tmp_path):
        """Test audio shorter than chunk size returns single chunk."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 600.0  # 10 minutes
        chunk_seconds = 900  # 15 minutes

        chunks = chunk_audio(wav, chunk_seconds)

        # Should return single chunk without splitting
        assert len(chunks) == 1
        assert chunks[0].path == wav
        assert chunks[0].offset == 0.0
        # Should not call ffmpeg for splitting
        mock_check_call.assert_not_called()

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_multiple_chunks(self, mock_check_call, mock_duration, tmp_path):
        """Test audio longer than chunk size gets split."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 1800.0  # 30 minutes
        chunk_seconds = 900  # 15 minutes

        chunks = chunk_audio(wav, chunk_seconds)

        # Should create 2 chunks
        assert len(chunks) == 2
        assert chunks[0].path == tmp_path / "chunk_0000.wav"
        assert chunks[0].offset == 0.0
        assert chunks[1].path == tmp_path / "chunk_0001.wav"
        assert chunks[1].offset == 900.0
        # Should call ffmpeg twice
        assert mock_check_call.call_count == 2

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_offset_calculation(self, mock_check_call, mock_duration, tmp_path):
        """Test correct offset calculation for chunks."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 2700.0  # 45 minutes
        chunk_seconds = 900  # 15 minutes

        chunks = chunk_audio(wav, chunk_seconds)

        # Should create 3 chunks with correct offsets
        assert len(chunks) == 3
        assert chunks[0].offset == 0.0
        assert chunks[1].offset == 900.0
        assert chunks[2].offset == 1800.0

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_ffmpeg_commands(self, mock_check_call, mock_duration, tmp_path):
        """Test ffmpeg commands for chunking."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 1000.0
        chunk_seconds = 600

        chunk_audio(wav, chunk_seconds)

        # Verify ffmpeg was called with correct parameters
        calls = mock_check_call.call_args_list
        assert len(calls) == 2

        # First chunk: 0-600s
        first_call = calls[0][0][0]
        assert "ffmpeg" in first_call
        assert "-ss" in first_call
        assert "-to" in first_call
        assert str(wav) in first_call

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_boundary_case(self, mock_check_call, mock_duration, tmp_path):
        """Test chunking at exact boundary."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 900.0  # Exactly chunk size
        chunk_seconds = 900

        chunks = chunk_audio(wav, chunk_seconds)

        # Should return single chunk (not > chunk_seconds)
        assert len(chunks) == 1
        assert chunks[0].offset == 0.0
        mock_check_call.assert_not_called()

    @patch("worker.audio.get_duration_seconds")
    @patch("worker.audio.subprocess.check_call")
    def test_chunk_audio_small_remainder(self, mock_check_call, mock_duration, tmp_path):
        """Test chunking with small remainder."""
        wav = tmp_path / "audio_16k.wav"
        wav.touch()
        mock_duration.return_value = 950.0  # 15:50
        chunk_seconds = 900  # 15:00

        chunks = chunk_audio(wav, chunk_seconds)

        # Should create 2 chunks: 0-900, 900-950
        assert len(chunks) == 2
        assert chunks[0].offset == 0.0
        assert chunks[1].offset == 900.0


class TestChunkDataclass:
    """Tests for Chunk dataclass."""

    def test_chunk_creation(self, tmp_path):
        """Test Chunk dataclass creation."""
        path = tmp_path / "test.wav"
        chunk = Chunk(path=path, offset=123.45)

        assert chunk.path == path
        assert chunk.offset == 123.45

    def test_chunk_fields(self):
        """Test Chunk has expected fields."""
        chunk = Chunk(path=Path("/test/path.wav"), offset=0.0)

        assert hasattr(chunk, "path")
        assert hasattr(chunk, "offset")
        assert isinstance(chunk.path, Path)
        assert isinstance(chunk.offset, float)
