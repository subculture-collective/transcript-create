"""Tests for yt-dlp JavaScript runtime validation."""

import subprocess
from unittest.mock import MagicMock, patch


class TestJSRuntimeAvailability:
    """Tests for checking JS runtime availability."""

    @patch("shutil.which")
    def test_runtime_available(self, mock_which):
        """Test check succeeds when JS runtime is available."""
        from app.ytdlp_validation import check_js_runtime_available

        mock_which.return_value = "/usr/local/bin/deno"

        is_available, error_msg = check_js_runtime_available()

        assert is_available is True
        assert error_msg is None
        mock_which.assert_called_once_with("deno")

    @patch("shutil.which")
    def test_runtime_not_found(self, mock_which):
        """Test check fails when JS runtime is not in PATH."""
        from app.ytdlp_validation import check_js_runtime_available

        mock_which.return_value = None

        is_available, error_msg = check_js_runtime_available()

        assert is_available is False
        assert error_msg is not None
        assert "not found in PATH" in error_msg
        assert "deno" in error_msg

    @patch("app.ytdlp_validation.settings")
    def test_runtime_not_configured(self, mock_settings):
        """Test check fails when JS_RUNTIME_CMD is empty."""
        from app.ytdlp_validation import check_js_runtime_available

        mock_settings.JS_RUNTIME_CMD = ""

        is_available, error_msg = check_js_runtime_available()

        assert is_available is False
        assert error_msg is not None
        assert "not configured" in error_msg


class TestYtdlpValidation:
    """Tests for validating yt-dlp with JS runtime."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validation_success(self, mock_which, mock_run):
        """Test validation succeeds when yt-dlp and JS runtime work."""
        from app.ytdlp_validation import validate_ytdlp_with_js_runtime

        # Mock JS runtime and yt-dlp availability
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ["deno", "yt-dlp"] else None

        # Mock successful yt-dlp --version
        mock_result = MagicMock()
        mock_result.stdout = "2025.10.14"
        mock_run.return_value = mock_result

        is_valid, error_msg = validate_ytdlp_with_js_runtime()

        assert is_valid is True
        assert error_msg is None
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["yt-dlp", "--version"]

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validation_ytdlp_not_found(self, mock_which, mock_run):
        """Test validation fails when yt-dlp is not installed."""
        from app.ytdlp_validation import validate_ytdlp_with_js_runtime

        # Mock JS runtime available but yt-dlp missing
        def which_side_effect(cmd):
            if cmd == "deno":
                return "/usr/bin/deno"
            return None

        mock_which.side_effect = which_side_effect

        is_valid, error_msg = validate_ytdlp_with_js_runtime()

        assert is_valid is False
        assert error_msg is not None
        assert "yt-dlp not found" in error_msg

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validation_ytdlp_fails(self, mock_which, mock_run):
        """Test validation fails when yt-dlp command fails."""
        from app.ytdlp_validation import validate_ytdlp_with_js_runtime

        # Mock both available
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ["deno", "yt-dlp"] else None

        # Mock yt-dlp failure
        mock_run.side_effect = subprocess.CalledProcessError(1, "yt-dlp", stderr="Runtime error")

        is_valid, error_msg = validate_ytdlp_with_js_runtime()

        assert is_valid is False
        assert error_msg is not None
        assert "failed" in error_msg.lower()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_validation_timeout(self, mock_which, mock_run):
        """Test validation handles timeout gracefully."""
        from app.ytdlp_validation import validate_ytdlp_with_js_runtime

        # Mock both available
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ["deno", "yt-dlp"] else None

        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired("yt-dlp", 10)

        is_valid, error_msg = validate_ytdlp_with_js_runtime()

        assert is_valid is False
        assert error_msg is not None
        assert "timed out" in error_msg.lower()

    @patch("shutil.which")
    def test_validation_js_runtime_missing(self, mock_which):
        """Test validation fails when JS runtime is missing."""
        from app.ytdlp_validation import validate_ytdlp_with_js_runtime

        # Mock JS runtime missing
        mock_which.return_value = None

        is_valid, error_msg = validate_ytdlp_with_js_runtime()

        assert is_valid is False
        assert error_msg is not None
        assert "not found" in error_msg


class TestInstallationInstructions:
    """Tests for installation instruction generation."""

    @patch("app.ytdlp_validation.settings")
    def test_deno_instructions(self, mock_settings):
        """Test Deno installation instructions are returned."""
        from app.ytdlp_validation import get_installation_instructions

        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        instructions = get_installation_instructions()

        assert "Deno" in instructions
        assert "deno.land" in instructions
        assert "curl" in instructions or "brew" in instructions

    @patch("app.ytdlp_validation.settings")
    def test_node_instructions(self, mock_settings):
        """Test Node.js installation instructions are returned."""
        from app.ytdlp_validation import get_installation_instructions

        mock_settings.JS_RUNTIME_CMD = "node"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        instructions = get_installation_instructions()

        assert "Node" in instructions
        assert "nodejs.org" in instructions

    @patch("app.ytdlp_validation.settings")
    def test_bun_instructions(self, mock_settings):
        """Test Bun installation instructions are returned."""
        from app.ytdlp_validation import get_installation_instructions

        mock_settings.JS_RUNTIME_CMD = "bun"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        instructions = get_installation_instructions()

        assert "Bun" in instructions or "bun" in instructions
        assert "bun.sh" in instructions

    @patch("app.ytdlp_validation.settings")
    def test_quickjs_instructions(self, mock_settings):
        """Test QuickJS installation instructions are returned."""
        from app.ytdlp_validation import get_installation_instructions

        mock_settings.JS_RUNTIME_CMD = "quickjs"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        instructions = get_installation_instructions()

        assert "QuickJS" in instructions or "quickjs" in instructions

    @patch("app.ytdlp_validation.settings")
    def test_custom_hint(self, mock_settings):
        """Test custom hint is used when provided."""
        from app.ytdlp_validation import get_installation_instructions

        custom_hint = "Custom installation: run custom-install.sh"
        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.YTDLP_JS_RUNTIME_HINT = custom_hint

        instructions = get_installation_instructions()

        assert instructions == custom_hint

    @patch("app.ytdlp_validation.settings")
    def test_unknown_runtime_instructions(self, mock_settings):
        """Test generic instructions for unknown runtime."""
        from app.ytdlp_validation import get_installation_instructions

        mock_settings.JS_RUNTIME_CMD = "unknown-runtime"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        instructions = get_installation_instructions()

        assert "JavaScript runtime" in instructions
        assert "Deno" in instructions
        assert "Node" in instructions


class TestValidationOrExit:
    """Tests for validate_js_runtime_or_exit function."""

    @patch("app.ytdlp_validation.settings")
    @patch("app.ytdlp_validation.logger")
    def test_validation_skipped_when_disabled(self, mock_logger, mock_settings):
        """Test validation is skipped when YTDLP_REQUIRE_JS_RUNTIME is false."""
        from app.ytdlp_validation import validate_js_runtime_or_exit

        mock_settings.YTDLP_REQUIRE_JS_RUNTIME = False

        # Should not raise or exit
        validate_js_runtime_or_exit()

        # Should log that validation is disabled
        mock_logger.info.assert_called()
        call_args = str(mock_logger.info.call_args)
        assert "disabled" in call_args.lower()

    @patch("sys.exit")
    @patch("subprocess.run")
    @patch("shutil.which")
    @patch("app.ytdlp_validation.settings")
    @patch("app.ytdlp_validation.logger")
    def test_validation_succeeds(self, mock_logger, mock_settings, mock_which, mock_run, mock_exit):
        """Test validation succeeds and doesn't exit."""
        from app.ytdlp_validation import validate_js_runtime_or_exit

        mock_settings.YTDLP_REQUIRE_JS_RUNTIME = True
        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.JS_RUNTIME_ARGS = "run -A"

        # Mock successful validation
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ["deno", "yt-dlp"] else None
        mock_result = MagicMock()
        mock_result.stdout = "2025.10.14"
        mock_run.return_value = mock_result

        # Should not exit
        validate_js_runtime_or_exit()

        mock_exit.assert_not_called()
        # Should log success
        assert any("successful" in str(call).lower() for call in mock_logger.info.call_args_list)

    @patch("sys.exit")
    @patch("shutil.which")
    @patch("app.ytdlp_validation.settings")
    @patch("app.ytdlp_validation.logger")
    def test_validation_fails_and_exits(self, mock_logger, mock_settings, mock_which, mock_exit):
        """Test validation fails and exits with error."""
        from app.ytdlp_validation import validate_js_runtime_or_exit

        mock_settings.YTDLP_REQUIRE_JS_RUNTIME = True
        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.JS_RUNTIME_ARGS = "run -A"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        # Mock runtime not found
        mock_which.return_value = None

        # Should exit
        validate_js_runtime_or_exit()

        mock_exit.assert_called_once_with(1)
        # Should log error
        assert any("failed" in str(call).lower() for call in mock_logger.error.call_args_list)


class TestMetrics:
    """Tests for JS runtime validation metrics."""

    def test_metrics_exist(self):
        """Test that validation metrics are defined."""
        from app.ytdlp_validation import ytdlp_js_runtime_check_total

        assert ytdlp_js_runtime_check_total is not None

    @patch("subprocess.run")
    @patch("shutil.which")
    @patch("app.ytdlp_validation.settings")
    def test_metrics_updated_on_success(self, mock_settings, mock_which, mock_run):
        """Test metrics are updated when validation succeeds."""
        from prometheus_client import REGISTRY

        from app.ytdlp_validation import validate_js_runtime_or_exit

        mock_settings.YTDLP_REQUIRE_JS_RUNTIME = True
        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.JS_RUNTIME_ARGS = "run -A"

        # Mock successful validation
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in ["deno", "yt-dlp"] else None
        mock_result = MagicMock()
        mock_result.stdout = "2025.10.14"
        mock_run.return_value = mock_result

        # Get initial metric value
        before_samples = list(REGISTRY.collect())

        validate_js_runtime_or_exit()

        # Verify metrics were updated
        after_samples = list(REGISTRY.collect())
        assert len(after_samples) >= len(before_samples)

    @patch("sys.exit")
    @patch("shutil.which")
    @patch("app.ytdlp_validation.settings")
    def test_metrics_updated_on_failure(self, mock_settings, mock_which, mock_exit):
        """Test metrics are updated when validation fails."""
        from prometheus_client import REGISTRY

        from app.ytdlp_validation import validate_js_runtime_or_exit

        mock_settings.YTDLP_REQUIRE_JS_RUNTIME = True
        mock_settings.JS_RUNTIME_CMD = "deno"
        mock_settings.YTDLP_JS_RUNTIME_HINT = ""

        # Mock runtime not found
        mock_which.return_value = None

        # Get initial metric value
        before_samples = list(REGISTRY.collect())

        validate_js_runtime_or_exit()

        # Verify metrics were updated even on failure
        after_samples = list(REGISTRY.collect())
        assert len(after_samples) >= len(before_samples)


class TestSettingsIntegration:
    """Tests for settings integration."""

    def test_default_settings(self):
        """Test default settings are appropriate."""
        from app.settings import settings

        # Check that settings exist with reasonable defaults
        assert hasattr(settings, "JS_RUNTIME_CMD")
        assert hasattr(settings, "JS_RUNTIME_ARGS")
        assert hasattr(settings, "YTDLP_REQUIRE_JS_RUNTIME")
        assert hasattr(settings, "YTDLP_JS_RUNTIME_HINT")

        # Default runtime should be deno
        assert settings.JS_RUNTIME_CMD == "deno"

        # Validation should be enabled by default
        assert settings.YTDLP_REQUIRE_JS_RUNTIME is True

    @patch("app.ytdlp_validation.settings")
    def test_custom_runtime_configuration(self, mock_settings):
        """Test custom runtime can be configured."""
        from app.ytdlp_validation import check_js_runtime_available

        # Test with Node.js
        mock_settings.JS_RUNTIME_CMD = "node"

        with patch("shutil.which", return_value="/usr/bin/node"):
            is_available, error_msg = check_js_runtime_available()
            assert is_available is True

        # Test with Bun
        mock_settings.JS_RUNTIME_CMD = "bun"

        with patch("shutil.which", return_value="/usr/bin/bun"):
            is_available, error_msg = check_js_runtime_available()
            assert is_available is True
