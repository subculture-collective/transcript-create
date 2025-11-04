"""Tests for yt-dlp client fallback strategy in worker.audio module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from worker.audio import (
    ClientStrategy,
    _build_client_strategies,
    _classify_error,
    _get_user_agent,
    _yt_dlp_cmd,
    download_audio,
)


class TestUserAgent:
    """Tests for _get_user_agent function."""

    def test_web_safari_user_agent(self):
        """Test web_safari user agent string."""
        ua = _get_user_agent("web_safari")
        assert "Safari" in ua
        assert "Macintosh" in ua

    def test_ios_user_agent(self):
        """Test iOS user agent string."""
        ua = _get_user_agent("ios")
        assert "iPhone" in ua or "iOS" in ua

    def test_android_user_agent(self):
        """Test Android user agent string."""
        ua = _get_user_agent("android")
        assert "Android" in ua

    def test_tv_user_agent(self):
        """Test TV user agent string."""
        ua = _get_user_agent("tv")
        assert "Cobalt" in ua or "ChromiumStylePlatform" in ua

    def test_default_user_agent(self):
        """Test default user agent falls back to web_safari."""
        ua = _get_user_agent("unknown")
        assert "Safari" in ua


class TestBuildClientStrategies:
    """Tests for _build_client_strategies function."""

    @patch("worker.audio.settings")
    def test_default_order(self, mock_settings):
        """Test default client order."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios,android,tv"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        strategies = _build_client_strategies()

        assert len(strategies) == 4
        assert strategies[0].name == "web_safari"
        assert strategies[1].name == "ios"
        assert strategies[2].name == "android"
        assert strategies[3].name == "tv"

    @patch("worker.audio.settings")
    def test_custom_order(self, mock_settings):
        """Test custom client order."""
        mock_settings.YTDLP_CLIENT_ORDER = "tv,android,ios"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        strategies = _build_client_strategies()

        assert len(strategies) == 3
        assert strategies[0].name == "tv"
        assert strategies[1].name == "android"
        assert strategies[2].name == "ios"

    @patch("worker.audio.settings")
    def test_disabled_clients(self, mock_settings):
        """Test disabling specific clients."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios,android,tv"
        mock_settings.YTDLP_CLIENTS_DISABLED = "ios,android"
        strategies = _build_client_strategies()

        assert len(strategies) == 2
        assert strategies[0].name == "web_safari"
        assert strategies[1].name == "tv"

    @patch("worker.audio.settings")
    def test_empty_order_fallback(self, mock_settings):
        """Test fallback when order is empty."""
        mock_settings.YTDLP_CLIENT_ORDER = ""
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        strategies = _build_client_strategies()

        assert len(strategies) == 1
        assert strategies[0].name == "web_safari"

    @patch("worker.audio.settings")
    def test_web_safari_has_hls_args(self, mock_settings):
        """Test web_safari strategy includes correct extractor args."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        strategies = _build_client_strategies()

        assert len(strategies) == 1
        strategy = strategies[0]
        assert "youtube:player_client=web_safari" in " ".join(strategy.extractor_args)
        assert "Referer" in " ".join(strategy.headers)

    @patch("worker.audio.settings")
    def test_tv_client_uses_tv_embedded(self, mock_settings):
        """Test TV client uses tv_embedded extractor."""
        mock_settings.YTDLP_CLIENT_ORDER = "tv"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        strategies = _build_client_strategies()

        assert len(strategies) == 1
        strategy = strategies[0]
        assert "youtube:player_client=tv_embedded" in " ".join(strategy.extractor_args)


class TestClassifyError:
    """Tests for _classify_error function."""

    def test_video_unavailable(self):
        """Test classification of unavailable videos."""
        classification = _classify_error(1, "Video unavailable")
        assert classification == "video_unavailable"

    def test_private_video(self):
        """Test classification of private videos."""
        classification = _classify_error(1, "This video is private")
        assert classification == "video_unavailable"

    def test_authentication_required(self):
        """Test classification of sign-in required errors."""
        classification = _classify_error(1, "Sign in to confirm your age")
        assert classification == "authentication_required"

    def test_bot_detection(self):
        """Test classification of bot detection."""
        classification = _classify_error(1, "Sorry, you have been blocked by bot detection")
        assert classification == "authentication_required"

    def test_throttling(self):
        """Test classification of throttling errors."""
        classification = _classify_error(1, "Throttling detected")
        assert classification == "throttling"

    def test_forbidden_error(self):
        """Test classification of 403 errors."""
        classification = _classify_error(1, "HTTP Error 403: Forbidden")
        assert classification == "forbidden"

    def test_generic_error(self):
        """Test classification of generic errors."""
        classification = _classify_error(1, "Some unknown error")
        assert classification == "generic_error"

    def test_specific_error_code(self):
        """Test classification of specific error codes."""
        classification = _classify_error(5, "")
        assert classification == "error_code_5"


class TestYtDlpCmd:
    """Tests for _yt_dlp_cmd function."""

    @patch("worker.audio.settings")
    def test_basic_command_structure(self, mock_settings, tmp_path):
        """Test basic command structure without strategy."""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""

        out = tmp_path / "raw.m4a"
        url = "https://www.youtube.com/watch?v=test"
        cmd = _yt_dlp_cmd(out, url)

        assert cmd[0] == "yt-dlp"
        assert "-f" in cmd
        assert "bestaudio" in cmd
        assert "-o" in cmd
        assert str(out) in cmd
        assert url in cmd

    @patch("worker.audio.settings")
    def test_command_with_strategy(self, mock_settings, tmp_path):
        """Test command includes strategy extractor args and headers."""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""

        strategy = ClientStrategy(
            name="test",
            extractor_args=["--extractor-args", "youtube:player_client=test"],
            headers=["--user-agent", "TestAgent"],
            description="Test strategy",
        )

        out = tmp_path / "raw.m4a"
        url = "https://www.youtube.com/watch?v=test"
        cmd = _yt_dlp_cmd(out, url, strategy)

        assert "--extractor-args" in cmd
        assert "youtube:player_client=test" in cmd
        assert "--user-agent" in cmd
        assert "TestAgent" in cmd

    @patch("worker.audio.settings")
    def test_command_with_cookies(self, mock_settings, tmp_path):
        """Test command includes cookies when configured."""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")

        mock_settings.YTDLP_COOKIES_PATH = str(cookies_file)
        mock_settings.YTDLP_EXTRA_ARGS = ""

        out = tmp_path / "raw.m4a"
        url = "https://www.youtube.com/watch?v=test"
        cmd = _yt_dlp_cmd(out, url)

        assert "--cookies" in cmd
        assert str(cookies_file) in cmd

    @patch("worker.audio.settings")
    def test_command_with_extra_args(self, mock_settings, tmp_path):
        """Test command includes extra args from settings."""
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = "--proxy http://proxy:8080 --geo-bypass"

        out = tmp_path / "raw.m4a"
        url = "https://www.youtube.com/watch?v=test"
        cmd = _yt_dlp_cmd(out, url)

        assert "--proxy" in cmd
        assert "http://proxy:8080" in cmd
        assert "--geo-bypass" in cmd


class TestDownloadAudio:
    """Tests for download_audio function with client fallback."""

    @patch("worker.audio.settings")
    @patch("worker.audio.subprocess.run")
    def test_success_on_first_client(self, mock_run, mock_settings, tmp_path):
        """Test successful download on first client attempt."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios,android,tv"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 2
        mock_settings.YTDLP_RETRY_SLEEP = 0.1
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""

        # Mock successful subprocess run
        mock_run.return_value = MagicMock(returncode=0)

        url = "https://www.youtube.com/watch?v=test"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        result = download_audio(url, dest_dir)

        assert result == dest_dir / "raw.m4a"
        # Should only call once (first attempt succeeds)
        assert mock_run.call_count == 1

    @patch("worker.audio.settings")
    @patch("worker.audio.subprocess.run")
    def test_fallback_to_second_client(self, mock_run, mock_settings, tmp_path):
        """Test fallback to second client after first fails."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios,android"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1
        mock_settings.YTDLP_RETRY_SLEEP = 0.1
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""

        # First client fails, second succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "yt-dlp", stderr="Error"),
            MagicMock(returncode=0),
        ]

        url = "https://www.youtube.com/watch?v=test"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        result = download_audio(url, dest_dir)

        assert result == dest_dir / "raw.m4a"
        # Should call twice (first fails, second succeeds)
        assert mock_run.call_count == 2

    @patch("worker.audio.settings")
    @patch("worker.audio.subprocess.run")
    def test_all_clients_fail(self, mock_run, mock_settings, tmp_path):
        """Test exception raised when all clients fail."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1
        mock_settings.YTDLP_RETRY_SLEEP = 0.1
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""

        # All clients fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "yt-dlp", stderr="Error")

        url = "https://www.youtube.com/watch?v=test"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        with pytest.raises(subprocess.CalledProcessError):
            download_audio(url, dest_dir)

        # Should try both clients once each
        assert mock_run.call_count == 2

    @patch("worker.audio.settings")
    @patch("worker.audio.subprocess.run")
    def test_retry_within_client(self, mock_run, mock_settings, tmp_path):
        """Test retries within same client strategy."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari"
        mock_settings.YTDLP_CLIENTS_DISABLED = ""
        mock_settings.YTDLP_TRIES_PER_CLIENT = 3
        mock_settings.YTDLP_BACKOFF_BASE_DELAY = 0.01
        mock_settings.YTDLP_BACKOFF_MAX_DELAY = 0.1
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_CIRCUIT_BREAKER_ENABLED = False  # Disable circuit breaker for this test
        mock_settings.YTDLP_REQUEST_TIMEOUT = 30.0

        # First two attempts fail, third succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "yt-dlp", stderr="Error"),
            subprocess.CalledProcessError(1, "yt-dlp", stderr="Error"),
            MagicMock(returncode=0),
        ]

        url = "https://www.youtube.com/watch?v=test"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        result = download_audio(url, dest_dir)

        assert result == dest_dir / "raw.m4a"
        # Should call three times (two failures, one success)
        assert mock_run.call_count == 3

    @patch("worker.audio.settings")
    @patch("worker.audio.subprocess.run")
    def test_respects_disabled_clients(self, mock_run, mock_settings, tmp_path):
        """Test that disabled clients are skipped."""
        mock_settings.YTDLP_CLIENT_ORDER = "web_safari,ios,android,tv"
        mock_settings.YTDLP_CLIENTS_DISABLED = "ios,android"
        mock_settings.YTDLP_TRIES_PER_CLIENT = 1
        mock_settings.YTDLP_BACKOFF_BASE_DELAY = 0.01
        mock_settings.YTDLP_BACKOFF_MAX_DELAY = 0.1
        mock_settings.YTDLP_COOKIES_PATH = ""
        mock_settings.YTDLP_EXTRA_ARGS = ""
        mock_settings.YTDLP_CIRCUIT_BREAKER_ENABLED = False  # Disable circuit breaker for this test
        mock_settings.YTDLP_REQUEST_TIMEOUT = 30.0

        # First (web_safari) fails, second (tv, since ios/android disabled) succeeds
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "yt-dlp", stderr="Error"),
            MagicMock(returncode=0),
        ]

        url = "https://www.youtube.com/watch?v=test"
        dest_dir = tmp_path / "video"
        dest_dir.mkdir()

        result = download_audio(url, dest_dir)

        assert result == dest_dir / "raw.m4a"
        # Should only try web_safari and tv (ios and android are disabled)
        assert mock_run.call_count == 2


class TestClientStrategy:
    """Tests for ClientStrategy dataclass."""

    def test_client_strategy_creation(self):
        """Test ClientStrategy dataclass creation."""
        strategy = ClientStrategy(
            name="test",
            extractor_args=["--arg1", "value1"],
            headers=["--header1", "value1"],
            description="Test description",
        )

        assert strategy.name == "test"
        assert strategy.extractor_args == ["--arg1", "value1"]
        assert strategy.headers == ["--header1", "value1"]
        assert strategy.description == "Test description"
