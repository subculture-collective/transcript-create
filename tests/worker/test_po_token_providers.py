"""Tests for PO token providers."""

from unittest.mock import MagicMock, patch

import pytest

from worker.po_token_manager import TokenType
from worker.po_token_providers import HTTPTokenProvider, ManualTokenProvider, initialize_default_providers


class TestManualTokenProvider:
    """Tests for ManualTokenProvider."""

    def test_manual_provider_with_tokens(self):
        """Test manual provider with configured tokens."""
        provider = ManualTokenProvider(
            player_token="player_123",
            gvs_token="gvs_456",
            subs_token="subs_789",
        )

        assert provider.is_available() is True
        assert provider.get_token(TokenType.PLAYER) == "player_123"
        assert provider.get_token(TokenType.GVS) == "gvs_456"
        assert provider.get_token(TokenType.SUBS) == "subs_789"

    def test_manual_provider_partial_tokens(self):
        """Test manual provider with only some tokens configured."""
        provider = ManualTokenProvider(player_token="player_123")

        assert provider.is_available() is True
        assert provider.get_token(TokenType.PLAYER) == "player_123"
        assert provider.get_token(TokenType.GVS) is None
        assert provider.get_token(TokenType.SUBS) is None

    def test_manual_provider_no_tokens(self):
        """Test manual provider with no tokens configured."""
        provider = ManualTokenProvider()
        assert provider.is_available() is False

    @patch("worker.po_token_providers.settings")
    def test_manual_provider_from_settings(self, mock_settings):
        """Test manual provider loads from settings."""
        mock_settings.PO_TOKEN_PLAYER = "settings_player_token"
        mock_settings.PO_TOKEN_GVS = ""
        mock_settings.PO_TOKEN_SUBS = ""

        provider = ManualTokenProvider()
        assert provider.get_token(TokenType.PLAYER) == "settings_player_token"


class TestHTTPTokenProvider:
    """Tests for HTTPTokenProvider."""

    def test_http_provider_disabled(self):
        """Test HTTP provider when disabled."""
        with patch("worker.po_token_providers.settings") as mock_settings:
            mock_settings.PO_TOKEN_PROVIDER_ENABLED = False
            mock_settings.PO_TOKEN_PROVIDER_URL = ""
            mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

            provider = HTTPTokenProvider()
            assert provider.is_available() is False

    @patch("worker.po_token_providers.settings")
    def test_http_provider_enabled(self, mock_settings):
        """Test HTTP provider when enabled."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        provider = HTTPTokenProvider()
        assert provider.is_available() is True

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_success(self, mock_settings, mock_get):
        """Test successful token retrieval from HTTP provider."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "http_token_123"}
        mock_get.return_value = mock_response

        provider = HTTPTokenProvider()
        token = provider.get_token(TokenType.PLAYER)

        assert token == "http_token_123"
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "http://localhost:8080/token" in str(call_args)
        assert call_args.kwargs.get("timeout") == 5.0

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_with_context(self, mock_settings, mock_get):
        """Test HTTP provider passes context in request."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "context_token"}
        mock_get.return_value = mock_response

        provider = HTTPTokenProvider()
        context = {"region": "us", "session_id": "abc123"}
        token = provider.get_token(TokenType.PLAYER, context=context)

        assert token == "context_token"
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("type") == "player"
        assert "context" in params

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_no_token_in_response(self, mock_settings, mock_get):
        """Test HTTP provider when response has no token."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "No token available"}
        mock_get.return_value = mock_response

        provider = HTTPTokenProvider()
        token = provider.get_token(TokenType.PLAYER)

        assert token is None

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_error_status(self, mock_settings, mock_get):
        """Test HTTP provider handles error status codes."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_get.return_value = mock_response

        provider = HTTPTokenProvider()
        token = provider.get_token(TokenType.PLAYER)

        assert token is None

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_timeout(self, mock_settings, mock_get):
        """Test HTTP provider handles timeouts."""
        import requests

        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        mock_get.side_effect = requests.Timeout("Request timeout")

        provider = HTTPTokenProvider()
        token = provider.get_token(TokenType.PLAYER)

        assert token is None

    @patch("worker.po_token_providers.requests.get")
    @patch("worker.po_token_providers.settings")
    def test_http_provider_exception(self, mock_settings, mock_get):
        """Test HTTP provider handles exceptions gracefully."""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        mock_get.side_effect = Exception("Network error")

        provider = HTTPTokenProvider()
        token = provider.get_token(TokenType.PLAYER)

        assert token is None


class TestInitializeDefaultProviders:
    """Tests for initialize_default_providers function."""

    @patch("worker.po_token_providers.settings")
    def test_initialize_with_manual_tokens(self, mock_settings):
        """Test initialization with manual tokens configured."""
        mock_settings.PO_TOKEN_PLAYER = "manual_player"
        mock_settings.PO_TOKEN_GVS = ""
        mock_settings.PO_TOKEN_SUBS = ""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = False
        mock_settings.PO_TOKEN_PROVIDER_URL = ""

        providers = initialize_default_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], ManualTokenProvider)

    @patch("worker.po_token_providers.settings")
    def test_initialize_with_http_provider(self, mock_settings):
        """Test initialization with HTTP provider enabled."""
        mock_settings.PO_TOKEN_PLAYER = ""
        mock_settings.PO_TOKEN_GVS = ""
        mock_settings.PO_TOKEN_SUBS = ""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        providers = initialize_default_providers()
        assert len(providers) == 1
        assert isinstance(providers[0], HTTPTokenProvider)

    @patch("worker.po_token_providers.settings")
    def test_initialize_with_both_providers(self, mock_settings):
        """Test initialization with both manual and HTTP providers."""
        mock_settings.PO_TOKEN_PLAYER = "manual_player"
        mock_settings.PO_TOKEN_GVS = ""
        mock_settings.PO_TOKEN_SUBS = ""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = True
        mock_settings.PO_TOKEN_PROVIDER_URL = "http://localhost:8080"
        mock_settings.PO_TOKEN_PROVIDER_TIMEOUT = 5.0

        providers = initialize_default_providers()
        assert len(providers) == 2
        # Manual provider should be first (higher priority)
        assert isinstance(providers[0], ManualTokenProvider)
        assert isinstance(providers[1], HTTPTokenProvider)

    @patch("worker.po_token_providers.settings")
    def test_initialize_with_no_providers(self, mock_settings):
        """Test initialization with no providers configured."""
        mock_settings.PO_TOKEN_PLAYER = ""
        mock_settings.PO_TOKEN_GVS = ""
        mock_settings.PO_TOKEN_SUBS = ""
        mock_settings.PO_TOKEN_PROVIDER_ENABLED = False
        mock_settings.PO_TOKEN_PROVIDER_URL = ""

        providers = initialize_default_providers()
        assert len(providers) == 0
