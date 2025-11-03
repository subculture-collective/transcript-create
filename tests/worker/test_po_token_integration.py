"""Tests for PO token integration in audio downloads and caption fetching."""

import json
import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from worker.po_token_manager import TokenType


class TestAudioTokenIntegration:
    """Tests for PO token integration in audio downloads."""

    @patch("worker.audio.subprocess.run")
    @patch("worker.audio.get_token_manager")
    @patch("worker.audio.settings")
    def test_audio_download_with_tokens(self, mock_settings, mock_get_manager, mock_run, tmp_path):
        """Test that audio download includes PO tokens when available."""
        from worker.audio import download_audio

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_AUDIO = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1

        # Mock token manager to return tokens
        mock_manager = MagicMock()
        mock_manager.get_token.side_effect = lambda token_type: {
            TokenType.PLAYER: "player_token_123",
            TokenType.GVS: "gvs_token_456",
        }.get(token_type)
        mock_get_manager.return_value = mock_manager

        # Mock successful download
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        dest_dir = tmp_path / "video"
        dest_dir.mkdir()
        url = "https://www.youtube.com/watch?v=test123"

        result = download_audio(url, dest_dir)

        # Verify download succeeded
        assert result == dest_dir / "raw.m4a"

        # Verify subprocess was called
        assert mock_run.call_count >= 1
        call_args = mock_run.call_args_list[0][0][0]

        # Verify command includes PO tokens
        cmd_str = " ".join(call_args)
        assert "--extractor-args" in call_args
        # Find extractor args values (there may be multiple)
        found_token_args = False
        for i, arg in enumerate(call_args):
            if arg == "--extractor-args" and i + 1 < len(call_args):
                extractor_value = call_args[i + 1]
                if "po_token=" in extractor_value:
                    assert "po_token=player:player_token_123" in extractor_value
                    assert "po_token=gvs:gvs_token_456" in extractor_value
                    found_token_args = True
                    break
        assert found_token_args, "Token args not found in command"

    @patch("worker.audio.subprocess.run")
    @patch("worker.audio.get_token_manager")
    @patch("worker.audio.settings")
    def test_audio_download_without_tokens_when_disabled(self, mock_settings, mock_get_manager, mock_run, tmp_path):
        """Test that audio download skips tokens when feature flag is disabled."""
        from worker.audio import download_audio

        # Disable token usage
        mock_settings.PO_TOKEN_USE_FOR_AUDIO = False
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1

        # Mock token manager (should not be called)
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        # Mock successful download
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        dest_dir = tmp_path / "video"
        dest_dir.mkdir()
        url = "https://www.youtube.com/watch?v=test123"

        result = download_audio(url, dest_dir)

        # Verify download succeeded
        assert result == dest_dir / "raw.m4a"

        # Verify token manager was not called
        mock_manager.get_token.assert_not_called()

    @patch("worker.audio.subprocess.run")
    @patch("worker.audio.get_token_manager")
    @patch("worker.audio.settings")
    def test_audio_download_marks_token_invalid_on_error(self, mock_settings, mock_get_manager, mock_run, tmp_path):
        """Test that failed downloads mark tokens as invalid when appropriate."""
        from worker.audio import download_audio

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_AUDIO = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1
        mock_settings.YTDLP_RETRY_SLEEP = 0.1

        # Mock token manager
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = "player_token_123"
        mock_get_manager.return_value = mock_manager

        # Mock failed download with token error
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["yt-dlp"],
            stderr="ERROR: 403 Forbidden - po_token invalid or expired",
        )

        dest_dir = tmp_path / "video"
        dest_dir.mkdir()
        url = "https://www.youtube.com/watch?v=test123"

        with pytest.raises(subprocess.CalledProcessError):
            download_audio(url, dest_dir)

        # Verify token was marked invalid
        assert mock_manager.mark_token_invalid.call_count >= 1


class TestCaptionTokenIntegration:
    """Tests for PO token integration in caption fetching."""

    @patch("worker.youtube_captions.subprocess.run")
    @patch("worker.youtube_captions.get_token_manager")
    @patch("worker.youtube_captions.settings")
    def test_caption_fetch_with_subs_token(self, mock_settings, mock_get_manager, mock_run):
        """Test that caption metadata fetch includes Subs token when available."""
        from worker.youtube_captions import _yt_dlp_json

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_CAPTIONS = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""

        # Mock token manager to return Subs token
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = "subs_token_789"
        mock_get_manager.return_value = mock_manager

        # Mock successful metadata fetch
        metadata = {"id": "test123", "title": "Test Video", "automatic_captions": {}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(metadata), stderr="")

        url = "https://www.youtube.com/watch?v=test123"
        result = _yt_dlp_json(url)

        # Verify metadata was returned
        assert result["id"] == "test123"

        # Verify token manager was called
        mock_manager.get_token.assert_called_with(TokenType.SUBS)

        # Verify subprocess was called with token
        assert mock_run.call_count >= 1
        call_args = mock_run.call_args_list[0][0][0]

        # Verify command includes Subs token (may have multiple extractor-args)
        assert "--extractor-args" in call_args
        found_subs_token = False
        for i, arg in enumerate(call_args):
            if arg == "--extractor-args" and i + 1 < len(call_args):
                extractor_value = call_args[i + 1]
                if "po_token=subs:" in extractor_value:
                    assert "po_token=subs:subs_token_789" in extractor_value
                    found_subs_token = True
                    break
        assert found_subs_token, "Subs token not found in command"

    @patch("worker.youtube_captions.subprocess.run")
    @patch("worker.youtube_captions.get_token_manager")
    @patch("worker.youtube_captions.settings")
    def test_caption_fetch_without_token_when_disabled(self, mock_settings, mock_get_manager, mock_run):
        """Test that caption fetch skips Subs token when feature flag is disabled."""
        from worker.youtube_captions import _yt_dlp_json

        # Disable token usage
        mock_settings.PO_TOKEN_USE_FOR_CAPTIONS = False
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""

        # Mock token manager (should not be called for tokens)
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        # Mock successful metadata fetch
        metadata = {"id": "test123", "automatic_captions": {}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(metadata), stderr="")

        url = "https://www.youtube.com/watch?v=test123"
        result = _yt_dlp_json(url)

        # Verify metadata was returned
        assert result["id"] == "test123"

        # Verify token manager was not called
        mock_manager.get_token.assert_not_called()

    @patch("worker.youtube_captions.subprocess.run")
    @patch("worker.youtube_captions.get_token_manager")
    @patch("worker.youtube_captions.settings")
    def test_caption_fetch_marks_token_invalid_on_error(self, mock_settings, mock_get_manager, mock_run):
        """Test that failed caption fetches mark Subs token as invalid when appropriate."""
        from worker.youtube_captions import _yt_dlp_json

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_CAPTIONS = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""

        # Mock token manager
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = "subs_token_789"
        mock_get_manager.return_value = mock_manager

        # Mock failed fetch with token error
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["yt-dlp"],
            stderr="ERROR: po_token expired or invalid",
        )

        url = "https://www.youtube.com/watch?v=test123"

        with pytest.raises(subprocess.CalledProcessError):
            _yt_dlp_json(url)

        # Verify token was marked invalid
        mock_manager.mark_token_invalid.assert_called_with(TokenType.SUBS, reason="metadata_fetch_failed")

    @patch("worker.youtube_captions.subprocess.run")
    @patch("worker.youtube_captions.get_token_manager")
    @patch("worker.youtube_captions.settings")
    def test_caption_fetch_fallback_without_token(self, mock_settings, mock_get_manager, mock_run):
        """Test that caption fetch works when no token is available."""
        from worker.youtube_captions import _yt_dlp_json

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_CAPTIONS = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""

        # Mock token manager to return no token
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = None
        mock_get_manager.return_value = mock_manager

        # Mock successful metadata fetch
        metadata = {"id": "test123", "automatic_captions": {}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(metadata), stderr="")

        url = "https://www.youtube.com/watch?v=test123"
        result = _yt_dlp_json(url)

        # Verify metadata was returned
        assert result["id"] == "test123"

        # Verify command does not include token args when no token available
        call_args = mock_run.call_args_list[0][0][0]
        cmd_str = " ".join(call_args)
        # Count extractor-args occurrences (may have client strategy args)
        extractor_count = call_args.count("--extractor-args")
        # If there are extractor args, they should not contain po_token=subs
        for i, arg in enumerate(call_args):
            if arg == "--extractor-args" and i + 1 < len(call_args):
                assert "po_token=subs:" not in call_args[i + 1]


class TestTokenLoggingSafety:
    """Tests to ensure token values are never logged."""

    @patch("worker.audio.logger")
    @patch("worker.audio.subprocess.run")
    @patch("worker.audio.get_token_manager")
    @patch("worker.audio.settings")
    def test_audio_logs_do_not_contain_token_values(
        self, mock_settings, mock_get_manager, mock_run, mock_logger, tmp_path
    ):
        """Test that audio download logs do not expose token values."""
        from worker.audio import download_audio

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_AUDIO = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1

        # Mock token manager with sensitive tokens
        secret_token = "very_secret_player_token_abc123xyz"
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = secret_token
        mock_get_manager.return_value = mock_manager

        # Mock successful download
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        dest_dir = tmp_path / "video"
        dest_dir.mkdir()
        url = "https://www.youtube.com/watch?v=test123"

        download_audio(url, dest_dir)

        # Check all log calls to ensure token value is not exposed
        for call in mock_logger.info.call_args_list + mock_logger.debug.call_args_list:
            args, kwargs = call
            # Check all arguments and extra fields
            for arg in args:
                if isinstance(arg, str):
                    assert secret_token not in arg, "Token value leaked in log message"
            if "extra" in kwargs:
                extra_str = str(kwargs["extra"])
                assert secret_token not in extra_str, "Token value leaked in log extra fields"

    @patch("worker.youtube_captions.logger")
    @patch("worker.youtube_captions.subprocess.run")
    @patch("worker.youtube_captions.get_token_manager")
    @patch("worker.youtube_captions.settings")
    def test_caption_logs_do_not_contain_token_values(
        self, mock_settings, mock_get_manager, mock_run, mock_logger
    ):
        """Test that caption fetch logs do not expose token values."""
        from worker.youtube_captions import _yt_dlp_json

        # Enable token usage
        mock_settings.PO_TOKEN_USE_FOR_CAPTIONS = True
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_COOKIES_PATH = ""

        # Mock token manager with sensitive token
        secret_token = "very_secret_subs_token_def456uvw"
        mock_manager = MagicMock()
        mock_manager.get_token.return_value = secret_token
        mock_get_manager.return_value = mock_manager

        # Mock successful metadata fetch
        metadata = {"id": "test123", "automatic_captions": {}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(metadata), stderr="")

        url = "https://www.youtube.com/watch?v=test123"
        _yt_dlp_json(url)

        # Check all log calls to ensure token value is not exposed
        for call in mock_logger.info.call_args_list + mock_logger.debug.call_args_list:
            args, kwargs = call
            # Check all arguments
            for arg in args:
                if isinstance(arg, str):
                    assert secret_token not in arg, "Token value leaked in log message"
            # Check extra fields
            if "extra" in kwargs:
                extra_str = str(kwargs["extra"])
                assert secret_token not in extra_str, "Token value leaked in log extra fields"
