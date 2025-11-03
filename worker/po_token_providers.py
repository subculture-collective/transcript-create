"""Built-in PO token providers.

This module provides:
- ManualTokenProvider: Manual token injection from settings
- HTTPTokenProvider: External HTTP service for token generation
"""

import json
from typing import Optional

import requests

from app.logging_config import get_logger
from app.settings import settings
from worker.po_token_manager import POTokenProvider, TokenType

logger = get_logger(__name__)


class ManualTokenProvider:
    """Provides tokens from manual configuration (settings/env)."""

    def __init__(
        self,
        player_token: Optional[str] = None,
        gvs_token: Optional[str] = None,
        subs_token: Optional[str] = None,
    ):
        """Initialize manual token provider.

        Args:
            player_token: Manual player token (defaults to settings)
            gvs_token: Manual GVS token (defaults to settings)
            subs_token: Manual subs token (defaults to settings)
        """
        self._tokens = {
            TokenType.PLAYER: player_token or settings.PO_TOKEN_PLAYER,
            TokenType.GVS: gvs_token or settings.PO_TOKEN_GVS,
            TokenType.SUBS: subs_token or settings.PO_TOKEN_SUBS,
        }

        # Log which tokens are configured
        configured = [k.value for k, v in self._tokens.items() if v]
        if configured:
            logger.info("Manual tokens configured", extra={"token_types": configured})

    def get_token(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[str]:
        """Get token from manual configuration.

        Args:
            token_type: Type of token
            context: Ignored for manual provider

        Returns:
            Configured token or None
        """
        token = self._tokens.get(token_type)
        # Return None if token is empty string
        if token:
            logger.debug("Manual token returned", extra={"token_type": token_type.value})
            return token
        return None

    def is_available(self) -> bool:
        """Check if any manual tokens are configured."""
        return any(v for v in self._tokens.values())


class HTTPTokenProvider:
    """Provides tokens from external HTTP service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """Initialize HTTP token provider.

        Args:
            base_url: Base URL for token service (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
        """
        self._base_url = (base_url or settings.PO_TOKEN_PROVIDER_URL).rstrip("/")
        self._timeout = timeout or settings.PO_TOKEN_PROVIDER_TIMEOUT
        self._enabled = bool(self._base_url) and settings.PO_TOKEN_PROVIDER_ENABLED

        if self._enabled:
            logger.info("HTTP token provider enabled", extra={"base_url": self._base_url, "timeout": self._timeout})

    def get_token(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[str]:
        """Get token from HTTP service.

        Expected API contract:
            GET {base_url}/token?type={token_type}&context={json_context}
            Response: {"token": "value"} or {"error": "message"}

        Args:
            token_type: Type of token
            context: Optional context for token request

        Returns:
            Token from service or None
        """
        if not self._enabled:
            return None

        try:
            params = {"type": token_type.value}
            if context:
                params["context"] = json.dumps(context)

            url = f"{self._base_url}/token"
            logger.debug(
                "Requesting token from HTTP provider",
                extra={"url": url, "token_type": token_type.value},
            )

            response = requests.get(
                url,
                params=params,
                timeout=self._timeout,
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("token")

                if token:
                    logger.info(
                        "Token received from HTTP provider",
                        extra={"token_type": token_type.value, "status_code": response.status_code},
                    )
                    return token
                else:
                    error = data.get("error", "No token in response")
                    logger.warning(
                        "HTTP provider returned no token",
                        extra={"token_type": token_type.value, "error": error},
                    )
                    return None
            else:
                logger.warning(
                    "HTTP provider request failed",
                    extra={
                        "token_type": token_type.value,
                        "status_code": response.status_code,
                        "response": response.text[:200],
                    },
                )
                return None

        except requests.Timeout:
            logger.warning(
                "HTTP provider timeout",
                extra={"token_type": token_type.value, "timeout": self._timeout},
            )
            return None
        except Exception as e:
            logger.error(
                "HTTP provider error",
                extra={
                    "token_type": token_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None

    def is_available(self) -> bool:
        """Check if HTTP provider is enabled and configured."""
        return self._enabled


def initialize_default_providers() -> list[POTokenProvider]:
    """Initialize default providers based on settings.

    Returns:
        List of configured providers in priority order
    """
    providers: list[POTokenProvider] = []

    # Manual provider (highest priority)
    manual_provider = ManualTokenProvider()
    if manual_provider.is_available():
        providers.append(manual_provider)

    # HTTP provider (if enabled)
    if settings.PO_TOKEN_PROVIDER_ENABLED:
        http_provider = HTTPTokenProvider()
        if http_provider.is_available():
            providers.append(http_provider)

    if providers:
        logger.info("Default token providers initialized", extra={"count": len(providers)})
    else:
        logger.info("No token providers configured")

    return providers
