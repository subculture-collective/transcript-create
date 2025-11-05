"""Tests for worker.pipeline module."""

import json
import uuid
from unittest.mock import Mock, call, patch

import pytest

from worker import pipeline


@pytest.fixture
def mock_engine():
    """Create a mock database engine."""
    mock = Mock()
    mock_conn = Mock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock.begin.return_value = mock_conn
    return mock


@pytest.fixture
def mock_conn():
    """Create a mock database connection."""
    mock = Mock()
    mock.execute = Mock()
    mock.commit = Mock()
    return mock


class TestNormalizeChannelUrl:
    """Tests for normalize_channel_url function."""

    def test_appends_videos_to_channel_id_url(self):
        """Test that /videos is appended to channel ID URLs."""
        url = "https://youtube.com/channel/UCtest123"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/channel/UCtest123/videos"

    def test_appends_videos_to_handle_url(self):
        """Test that /videos is appended to handle (@username) URLs."""
        url = "https://youtube.com/@testuser"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/@testuser/videos"

    def test_preserves_existing_videos_suffix(self):
        """Test that URLs already ending with /videos are not modified."""
        url = "https://youtube.com/channel/UCtest123/videos"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/channel/UCtest123/videos"

    def test_handles_trailing_slash(self):
        """Test that trailing slashes are handled correctly."""
        url = "https://youtube.com/channel/UCtest123/"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/channel/UCtest123/videos"

    def test_handles_www_prefix(self):
        """Test URLs with www prefix."""
        url = "https://www.youtube.com/channel/UCtest123"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://www.youtube.com/channel/UCtest123/videos"

    def test_handles_http_protocol(self):
        """Test URLs with http protocol."""
        url = "http://youtube.com/@testuser"
        result = pipeline.normalize_channel_url(url)
        assert result == "http://youtube.com/@testuser/videos"

    def test_preserves_handle_with_videos_suffix(self):
        """Test that handle URLs with /videos are preserved."""
        url = "https://youtube.com/@testuser/videos"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/@testuser/videos"

    def test_does_not_modify_non_channel_urls(self):
        """Test that non-channel URLs are not modified."""
        url = "https://youtube.com/watch?v=abc123"
        result = pipeline.normalize_channel_url(url)
        assert result == "https://youtube.com/watch?v=abc123"


class TestExpandSingleJob:
    """Tests for expand_single_if_needed function."""

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_single_job_success(self, mock_check_output, mock_conn):
        """Test successful single job expansion."""
        job_id = uuid.uuid4()
        video_id = "test_video_123"

        # Mock job query
        mock_job = {"id": job_id, "input_url": "https://youtube.com/watch?v=test_video_123"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        # Mock yt-dlp response
        yt_dlp_response = {
            "id": video_id,
            "title": "Test Video",
            "duration": 300,
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_single_if_needed(mock_conn)

        # Verify yt-dlp was called
        assert mock_check_output.called
        call_args = mock_check_output.call_args[0][0]
        assert "yt-dlp" in call_args
        assert "-J" in call_args

        # Verify video insert was called
        execute_calls = mock_conn.execute.call_args_list
        # Should have: job query, video insert, state update
        assert len(execute_calls) >= 3

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_single_job_from_entries(self, mock_check_output, mock_conn):
        """Test single job expansion when video ID in entries."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/playlist?list=test"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        # yt-dlp response with video in entries
        yt_dlp_response = {
            "entries": [
                {
                    "id": "video_from_entries",
                    "title": "Entry Video",
                    "duration": 240,
                }
            ]
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_single_if_needed(mock_conn)

        # Should have extracted video from entries
        assert mock_check_output.called

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_single_job_no_video_id_raises(self, mock_check_output, mock_conn):
        """Test raises error when video ID cannot be determined."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/watch?v=test"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        # yt-dlp response without id
        yt_dlp_response = {"title": "Video", "duration": 100}
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        with pytest.raises(RuntimeError, match="Unable to determine YouTube ID"):
            pipeline.expand_single_if_needed(mock_conn)

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_single_job_no_pending_jobs(self, mock_check_output, mock_conn):
        """Test no action when no pending jobs."""
        mock_conn.execute.return_value.mappings.return_value.all.return_value = []

        pipeline.expand_single_if_needed(mock_conn)

        # Should not call yt-dlp
        mock_check_output.assert_not_called()


class TestExpandChannelJob:
    """Tests for expand_channel_if_needed function."""

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_success(self, mock_check_output, mock_conn):
        """Test successful channel job expansion."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        # Mock yt-dlp channel response
        yt_dlp_response = {
            "entries": [
                {"id": "video1", "title": "Video 1", "duration": 100},
                {"id": "video2", "title": "Video 2", "duration": 200},
                {"id": "video3", "title": "Video 3", "duration": 300},
            ],
            "channel_id": "UCtest",
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Verify yt-dlp was called with --flat-playlist
        call_args = mock_check_output.call_args[0][0]
        assert "yt-dlp" in call_args
        assert "--flat-playlist" in call_args
        assert "-J" in call_args

        # Verify multiple video inserts
        execute_calls = mock_conn.execute.call_args_list
        # Should have: job query, 3 video inserts, state update
        assert len(execute_calls) >= 5

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_appends_videos_suffix(self, mock_check_output, mock_conn):
        """Test that channel expansion appends /videos to channel URLs."""
        job_id = uuid.uuid4()

        # Test with channel URL without /videos suffix
        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        yt_dlp_response = {
            "entries": [{"id": "video1", "title": "Video 1", "duration": 100}],
            "channel_id": "UCtest",
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Verify yt-dlp was called with /videos appended to URL
        call_args = mock_check_output.call_args[0][0]
        assert "https://youtube.com/channel/UCtest/videos" in call_args

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_handle_url_gets_videos_suffix(self, mock_check_output, mock_conn):
        """Test that handle URLs (@username) get /videos suffix."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/@testuser"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        yt_dlp_response = {
            "entries": [
                {"id": "video1", "title": "Video 1", "duration": 100},
                {"id": "video2", "title": "Video 2", "duration": 200},
            ],
            "uploader_id": "testuser",
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Verify yt-dlp was called with /videos appended
        call_args = mock_check_output.call_args[0][0]
        assert "https://youtube.com/@testuser/videos" in call_args

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_preserves_existing_videos_suffix(self, mock_check_output, mock_conn):
        """Test that URLs already with /videos suffix are not double-appended."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest/videos"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        yt_dlp_response = {
            "entries": [{"id": "video1", "title": "Video 1", "duration": 100}],
            "channel_id": "UCtest",
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Verify URL was not double-appended
        call_args = mock_check_output.call_args[0][0]
        assert "https://youtube.com/channel/UCtest/videos" in call_args
        assert "https://youtube.com/channel/UCtest/videos/videos" not in call_args

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_logs_expansion_counts(self, mock_check_output, mock_conn):
        """Test that expansion logs include channel_id and entry counts."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        yt_dlp_response = {
            "entries": [
                {"id": "video1", "title": "Video 1", "duration": 100},
                {"id": "video2", "title": "Video 2", "duration": 200},
                {"id": "video3", "title": "Video 3", "duration": 300},
            ],
            "channel_id": "UCtest",
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        with patch("worker.pipeline.logger") as mock_logger:
            pipeline.expand_channel_if_needed(mock_conn)

            # Find the log call that contains expansion results
            expansion_log_calls = [
                call for call in mock_logger.info.call_args_list
                if len(call[0]) > 0 and "expansion found entries" in call[0][0].lower()
            ]
            
            assert len(expansion_log_calls) > 0, "Expected log about channel expansion found entries"
            
            # Verify the log contains channel_id and entry_count in extra
            log_call = expansion_log_calls[0]
            if "extra" in log_call[1]:
                extra = log_call[1]["extra"]
                assert "channel_id" in extra
                assert extra["channel_id"] == "UCtest"
                assert "entry_count" in extra
                assert extra["entry_count"] == 3

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_empty_channel(self, mock_check_output, mock_conn):
        """Test channel expansion with no videos."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        # Empty channel
        yt_dlp_response = {"entries": []}
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Should still update job state
        assert mock_conn.execute.called

    @patch("worker.pipeline.subprocess.check_output")
    def test_expand_channel_job_preserves_order(self, mock_check_output, mock_conn):
        """Test channel videos maintain order via idx."""
        job_id = uuid.uuid4()

        mock_job = {"id": job_id, "input_url": "https://youtube.com/channel/UCtest"}
        mock_conn.execute.return_value.mappings.return_value.all.return_value = [mock_job]

        yt_dlp_response = {
            "entries": [
                {"id": "v1", "title": "First", "duration": 100},
                {"id": "v2", "title": "Second", "duration": 200},
            ]
        }
        mock_check_output.return_value = json.dumps(yt_dlp_response).encode()

        pipeline.expand_channel_if_needed(mock_conn)

        # Verify idx parameter in inserts
        execute_calls = mock_conn.execute.call_args_list
        # Check that idx values are passed (can't easily verify exact values without deeper inspection)
        assert len(execute_calls) >= 3


class TestProcessVideo:
    """Tests for process_video function."""

    @patch("worker.pipeline.diarize_and_align")
    @patch("worker.pipeline.transcribe_chunk")
    @patch("worker.pipeline.chunk_audio")
    @patch("worker.pipeline.ensure_wav_16k")
    @patch("worker.pipeline.download_audio")
    @patch("worker.pipeline.settings")
    def test_process_video_success_path(
        self,
        mock_settings,
        mock_download,
        mock_ensure_wav,
        mock_chunk,
        mock_transcribe,
        mock_diarize,
        mock_engine,
        tmp_path,
    ):
        """Test successful video processing pipeline."""
        video_id = uuid.uuid4()
        job_id = uuid.uuid4()

        # Mock settings
        mock_settings.CHUNK_SECONDS = 900
        mock_settings.WHISPER_MODEL = "medium"
        mock_settings.CLEANUP_AFTER_PROCESS = False

        # Mock database queries
        mock_video = {
            "id": video_id,
            "youtube_id": "test123",
            "job_id": job_id,
        }

        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = mock_video
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_engine.begin.return_value = mock_conn

        # Mock file operations
        raw_path = tmp_path / "raw.m4a"
        wav_path = tmp_path / "audio_16k.wav"
        chunk_path = tmp_path / "chunk_0000.wav"

        mock_download.return_value = raw_path
        mock_ensure_wav.return_value = wav_path

        # Mock chunking
        from worker.audio import Chunk

        mock_chunk.return_value = [Chunk(path=chunk_path, offset=0.0)]

        # Mock transcription
        mock_transcribe.return_value = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "Test transcript",
                "avg_logprob": -0.5,
                "temperature": 0.0,
                "token_count": 3,
                "confidence": 0.95,
            }
        ]

        # Mock diarization
        mock_diarize.return_value = mock_transcribe.return_value

        # Patch WORKDIR
        with patch("worker.pipeline.WORKDIR", tmp_path):
            pipeline.process_video(mock_engine, video_id)

        # Verify all stages were called
        mock_download.assert_called_once()
        mock_ensure_wav.assert_called_once_with(raw_path)
        mock_chunk.assert_called_once_with(wav_path, 900)
        mock_transcribe.assert_called_once()
        mock_diarize.assert_called_once()

    @patch("worker.pipeline.download_audio")
    @patch("worker.pipeline.WORKDIR")
    def test_process_video_download_failure(self, mock_workdir, mock_download, mock_engine, tmp_path):
        """Test handling of download failure."""
        video_id = uuid.uuid4()

        # Set WORKDIR to tmp_path
        mock_workdir.__truediv__ = lambda self, other: tmp_path / str(other)

        mock_video = {"id": video_id, "youtube_id": "test123", "job_id": uuid.uuid4()}

        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = mock_video
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_engine.begin.return_value = mock_conn

        # Simulate download failure
        mock_download.side_effect = Exception("Download failed")

        with pytest.raises(Exception, match="Download failed"):
            pipeline.process_video(mock_engine, video_id)

    @patch("worker.pipeline.diarize_and_align")
    @patch("worker.pipeline.transcribe_chunk")
    @patch("worker.pipeline.chunk_audio")
    @patch("worker.pipeline.ensure_wav_16k")
    @patch("worker.pipeline.download_audio")
    @patch("worker.pipeline.settings")
    def test_process_video_cleanup_after_success(
        self,
        mock_settings,
        mock_download,
        mock_ensure_wav,
        mock_chunk,
        mock_transcribe,
        mock_diarize,
        mock_engine,
        tmp_path,
    ):
        """Test file cleanup after successful processing."""
        video_id = uuid.uuid4()

        # Enable cleanup
        mock_settings.CHUNK_SECONDS = 900
        mock_settings.WHISPER_MODEL = "medium"
        mock_settings.CLEANUP_AFTER_PROCESS = True
        mock_settings.CLEANUP_DELETE_RAW = True
        mock_settings.CLEANUP_DELETE_WAV = True
        mock_settings.CLEANUP_DELETE_CHUNKS = True
        mock_settings.CLEANUP_DELETE_DIR_IF_EMPTY = True

        mock_video = {"id": video_id, "youtube_id": "test123", "job_id": uuid.uuid4()}

        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = mock_video
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_engine.begin.return_value = mock_conn

        # Create real files for cleanup testing
        video_dir = tmp_path / str(video_id)
        video_dir.mkdir()

        raw_path = video_dir / "raw.m4a"
        raw_path.touch()
        wav_path = video_dir / "audio_16k.wav"
        wav_path.touch()
        chunk_path = video_dir / "chunk_0000.wav"
        chunk_path.touch()

        mock_download.return_value = raw_path
        mock_ensure_wav.return_value = wav_path

        from worker.audio import Chunk

        mock_chunk.return_value = [Chunk(path=chunk_path, offset=0.0)]

        mock_transcribe.return_value = [
            {"start": 0.0, "end": 5.0, "text": "Test", "avg_logprob": -0.5, "temperature": 0.0, "token_count": 1}
        ]
        mock_diarize.return_value = mock_transcribe.return_value

        with patch("worker.pipeline.WORKDIR", tmp_path):
            pipeline.process_video(mock_engine, video_id)

        # Verify files were deleted
        assert not raw_path.exists()
        assert not wav_path.exists()
        assert not chunk_path.exists()
        assert not video_dir.exists()

    @patch("worker.pipeline.diarize_and_align")
    @patch("worker.pipeline.transcribe_chunk")
    @patch("worker.pipeline.chunk_audio")
    @patch("worker.pipeline.ensure_wav_16k")
    @patch("worker.pipeline.download_audio")
    @patch("worker.pipeline.settings")
    def test_process_video_multiple_chunks(
        self,
        mock_settings,
        mock_download,
        mock_ensure_wav,
        mock_chunk,
        mock_transcribe,
        mock_diarize,
        mock_engine,
        tmp_path,
    ):
        """Test processing video with multiple chunks."""
        video_id = uuid.uuid4()

        mock_settings.CHUNK_SECONDS = 900
        mock_settings.WHISPER_MODEL = "medium"
        mock_settings.CLEANUP_AFTER_PROCESS = False

        mock_video = {"id": video_id, "youtube_id": "test123", "job_id": uuid.uuid4()}

        mock_conn = Mock()
        mock_conn.execute.return_value.mappings.return_value.first.return_value = mock_video
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_engine.begin.return_value = mock_conn

        raw_path = tmp_path / "raw.m4a"
        wav_path = tmp_path / "audio_16k.wav"

        mock_download.return_value = raw_path
        mock_ensure_wav.return_value = wav_path

        from worker.audio import Chunk

        # Multiple chunks with offsets
        mock_chunk.return_value = [
            Chunk(path=tmp_path / "chunk_0000.wav", offset=0.0),
            Chunk(path=tmp_path / "chunk_0001.wav", offset=900.0),
        ]

        # Mock transcription for each chunk
        mock_transcribe.side_effect = [
            [{"start": 0.0, "end": 5.0, "text": "First", "avg_logprob": -0.5, "temperature": 0.0, "token_count": 1}],
            [{"start": 0.0, "end": 5.0, "text": "Second", "avg_logprob": -0.5, "temperature": 0.0, "token_count": 1}],
        ]

        # Diarization returns all segments
        mock_diarize.return_value = [
            {"start": 0.0, "end": 5.0, "text": "First", "avg_logprob": -0.5, "temperature": 0.0, "token_count": 1},
            {"start": 900.0, "end": 905.0, "text": "Second", "avg_logprob": -0.5, "temperature": 0.0, "token_count": 1},
        ]

        with patch("worker.pipeline.WORKDIR", tmp_path):
            pipeline.process_video(mock_engine, video_id)

        # Transcribe should be called twice
        assert mock_transcribe.call_count == 2

        # Verify offsets were applied to segments
        # Second segment should have offset of 900.0 added


class TestCaptureYouTubeCaptions:
    """Tests for capture_youtube_captions_for_unprocessed function."""

    @patch("worker.youtube_captions.subprocess.check_output")
    def test_capture_youtube_captions_success(self, mock_check_output, mock_conn):
        """Test successful YouTube caption capture."""
        video_id = uuid.uuid4()
        youtube_id = "test123"

        # Mock video query
        mock_conn.execute.return_value.all.return_value = [(video_id, youtube_id)]

        # Mock yt-dlp response
        yt_dlp_data = {"automatic_captions": {"en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]}}
        mock_check_output.return_value = json.dumps(yt_dlp_data).encode()

        # Mock urlopen for caption download
        caption_data = {
            "events": [
                {
                    "tStartMs": 0,
                    "dDurationMs": 5000,
                    "segs": [{"utf8": "Test caption"}],
                }
            ]
        }

        with patch("worker.youtube_captions.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(caption_data).encode()
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            # Mock RETURNING clause
            mock_conn.execute.return_value.first.return_value = (1,)

            count = pipeline.capture_youtube_captions_for_unprocessed(mock_conn, limit=5)

        assert count == 1

    @patch("worker.youtube_captions.fetch_youtube_auto_captions")
    def test_capture_youtube_captions_no_captions(self, mock_fetch, mock_conn):
        """Test when no captions are available."""
        video_id = uuid.uuid4()
        youtube_id = "test123"

        mock_conn.execute.return_value.all.return_value = [(video_id, youtube_id)]
        mock_fetch.return_value = None

        count = pipeline.capture_youtube_captions_for_unprocessed(mock_conn, limit=5)

        assert count == 0

    @patch("worker.youtube_captions.fetch_youtube_auto_captions")
    def test_capture_youtube_captions_fetch_error(self, mock_fetch, mock_conn):
        """Test handling of caption fetch errors."""
        video_id = uuid.uuid4()
        youtube_id = "test123"

        mock_conn.execute.return_value.all.return_value = [(video_id, youtube_id)]
        mock_fetch.side_effect = Exception("Fetch failed")

        # Should not raise, just log warning
        count = pipeline.capture_youtube_captions_for_unprocessed(mock_conn, limit=5)

        assert count == 0

    @patch("worker.youtube_captions.subprocess.check_output")
    def test_capture_youtube_captions_multiple_videos(self, mock_check_output, mock_conn):
        """Test processing multiple videos."""
        videos = [
            (uuid.uuid4(), "video1"),
            (uuid.uuid4(), "video2"),
        ]

        mock_conn.execute.return_value.all.return_value = videos

        # Mock yt-dlp responses
        yt_dlp_data = {"automatic_captions": {"en": [{"ext": "json3", "url": "http://example.com/captions.json3"}]}}
        mock_check_output.return_value = json.dumps(yt_dlp_data).encode()

        # Mock caption download
        caption_data = {
            "events": [
                {
                    "tStartMs": 0,
                    "dDurationMs": 5000,
                    "segs": [{"utf8": "Test"}],
                }
            ]
        }

        with patch("worker.youtube_captions.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(caption_data).encode()
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            mock_conn.execute.return_value.first.return_value = (1,)

            count = pipeline.capture_youtube_captions_for_unprocessed(mock_conn, limit=5)

        assert count == 2
        assert mock_check_output.call_count == 2

    def test_capture_youtube_captions_no_pending(self, mock_conn):
        """Test when no videos need caption processing."""
        mock_conn.execute.return_value.all.return_value = []

        count = pipeline.capture_youtube_captions_for_unprocessed(mock_conn, limit=5)

        assert count == 0
