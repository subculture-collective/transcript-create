"""PO Token Manager for YouTube token management.

This module provides:
- Token type abstractions (player, gvs, subs)
- Caching with TTL and cooldown logic
- Provider plugin interface
- Metrics for token operations
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol
from urllib.parse import quote

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)


class TokenType(str, Enum):
    """YouTube PO token types."""

    PLAYER = "player"  # Player API token
    GVS = "gvs"  # GetVideoStream API token
    SUBS = "subs"  # Subtitles API token


@dataclass
class POToken:
    """Represents a PO token with metadata."""

    value: str
    token_type: TokenType
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"  # manual, provider, etc.
    context: Optional[dict] = None  # session/client/region metadata

    def is_expired(self, ttl: int) -> bool:
        """Check if token has exceeded TTL."""
        return (time.time() - self.timestamp) > ttl

    def age_seconds(self) -> float:
        """Get age of token in seconds."""
        return time.time() - self.timestamp


class POTokenProvider(Protocol):
    """Protocol for PO token providers.

    Providers can be:
    - External services (HTTP API)
    - JavaScript runtime execution
    - Manual injection from settings
    - Custom plugins
    """

    def get_token(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[str]:
        """Retrieve a token for the given type and context.

        Args:
            token_type: Type of token needed (player, gvs, subs)
            context: Optional context (session, client, region, etc.)

        Returns:
            Token string or None if unavailable
        """

    def is_available(self) -> bool:
        """Check if provider is available and ready to provide tokens."""


@dataclass
class TokenCacheEntry:
    """Cache entry with cooldown tracking."""

    token: POToken
    failed_at: Optional[float] = None  # Last failure timestamp
    failure_count: int = 0

    def is_in_cooldown(self, cooldown_seconds: int) -> bool:
        """Check if entry is in cooldown period after failure."""
        if self.failed_at is None:
            return False
        return (time.time() - self.failed_at) < cooldown_seconds

    def mark_failure(self):
        """Mark this token as failed."""
        self.failed_at = time.time()
        self.failure_count += 1

    def reset_failure(self):
        """Reset failure tracking."""
        self.failed_at = None
        self.failure_count = 0


class POTokenCache:
    """Token cache with TTL and cooldown logic."""

    def __init__(self, ttl: int, cooldown_seconds: int):
        """Initialize cache.

        Args:
            ttl: Token time-to-live in seconds
            cooldown_seconds: Cooldown period after token failure
        """
        self._cache: dict[str, TokenCacheEntry] = {}
        self._ttl = ttl
        self._cooldown_seconds = cooldown_seconds
        self._hits = 0
        self._misses = 0

    def _make_key(self, token_type: TokenType, context: Optional[dict] = None) -> str:
        """Generate cache key from token type and context.
        
        Uses URL encoding to handle special characters in context values.
        """
        if context is None:
            return f"{token_type.value}"
        # Sort context keys for consistent cache keys and URL-encode values
        context_str = ":".join(f"{quote(str(k))}={quote(str(v))}" for k, v in sorted(context.items()))
        return f"{token_type.value}:{context_str}"

    def get(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[POToken]:
        """Get token from cache if valid and not in cooldown.

        Args:
            token_type: Type of token
            context: Optional context

        Returns:
            Cached token or None if not available/valid
        """
        key = self._make_key(token_type, context)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            logger.debug("Token cache miss", extra={"token_type": token_type.value, "key": key})
            return None

        # Check cooldown
        if entry.is_in_cooldown(self._cooldown_seconds):
            self._misses += 1
            logger.debug(
                "Token in cooldown period",
                extra={
                    "token_type": token_type.value,
                    "key": key,
                    "cooldown_remaining": self._cooldown_seconds - (time.time() - (entry.failed_at or 0)),
                },
            )
            return None

        # Check expiration
        if entry.token.is_expired(self._ttl):
            self._misses += 1
            logger.debug(
                "Token expired",
                extra={"token_type": token_type.value, "key": key, "age_seconds": entry.token.age_seconds()},
            )
            del self._cache[key]
            return None

        self._hits += 1
        logger.debug(
            "Token cache hit",
            extra={
                "token_type": token_type.value,
                "key": key,
                "age_seconds": entry.token.age_seconds(),
                "source": entry.token.source,
            },
        )
        return entry.token

    def set(self, token: POToken, context: Optional[dict] = None):
        """Store token in cache.

        Args:
            token: Token to cache
            context: Optional context
        """
        key = self._make_key(token.token_type, context)
        self._cache[key] = TokenCacheEntry(token=token)
        logger.debug(
            "Token cached", extra={"token_type": token.token_type.value, "key": key, "source": token.source}
        )

    def mark_failure(self, token_type: TokenType, context: Optional[dict] = None):
        """Mark a token as failed to trigger cooldown.

        Args:
            token_type: Type of token
            context: Optional context
        """
        key = self._make_key(token_type, context)
        entry = self._cache.get(key)

        if entry:
            entry.mark_failure()
            logger.warning(
                "Token marked as failed",
                extra={
                    "token_type": token_type.value,
                    "key": key,
                    "failure_count": entry.failure_count,
                    "cooldown_seconds": self._cooldown_seconds,
                },
            )
        else:
            logger.debug("Token failure marked but not in cache", extra={"token_type": token_type.value, "key": key})

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate": hit_rate,
            "cached_tokens": len(self._cache),
            "ttl_seconds": self._ttl,
            "cooldown_seconds": self._cooldown_seconds,
        }

    def clear(self):
        """Clear all cached tokens."""
        self._cache.clear()
        logger.info("Token cache cleared")


class POTokenManager:
    """Main PO token manager coordinating providers and caching."""

    def __init__(
        self,
        providers: Optional[list[POTokenProvider]] = None,
        ttl: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
    ):
        """Initialize token manager.

        Args:
            providers: List of token providers (checked in order)
            ttl: Token cache TTL in seconds (defaults to settings)
            cooldown_seconds: Cooldown after failure (defaults to settings)
        """
        self._providers = providers or []
        self._cache = POTokenCache(
            ttl=ttl or settings.PO_TOKEN_CACHE_TTL,
            cooldown_seconds=cooldown_seconds or settings.PO_TOKEN_COOLDOWN_SECONDS,
        )

        # Metrics
        self._retrievals_total = 0
        self._retrievals_success = 0
        self._retrievals_failed = 0
        self._provider_attempts: dict[str, int] = {}
        self._provider_successes: dict[str, int] = {}

    def add_provider(self, provider: POTokenProvider):
        """Add a token provider to the chain.

        Args:
            provider: Provider to add
        """
        self._providers.append(provider)
        logger.info("Token provider added", extra={"provider": type(provider).__name__})

    def get_token(self, token_type: TokenType, context: Optional[dict] = None) -> Optional[str]:
        """Get a token from cache or providers.

        Args:
            token_type: Type of token needed
            context: Optional context for token request

        Returns:
            Token string or None if unavailable
        """
        self._retrievals_total += 1

        # Try cache first
        cached_token = self._cache.get(token_type, context)
        if cached_token:
            self._retrievals_success += 1
            logger.info(
                "Token retrieved from cache",
                extra={
                    "token_type": token_type.value,
                    "source": cached_token.source,
                    "age_seconds": cached_token.age_seconds(),
                },
            )
            return cached_token.value

        # Try providers in order
        for provider in self._providers:
            provider_name = type(provider).__name__
            self._provider_attempts[provider_name] = self._provider_attempts.get(provider_name, 0) + 1

            if not provider.is_available():
                logger.debug("Provider not available", extra={"provider": provider_name, "token_type": token_type.value})
                continue

            try:
                start_time = time.time()
                token_value = provider.get_token(token_type, context)
                latency = time.time() - start_time

                if token_value:
                    # Success - cache and return
                    token = POToken(
                        value=token_value,
                        token_type=token_type,
                        source=provider_name,
                        context=context,
                    )
                    self._cache.set(token, context)
                    self._provider_successes[provider_name] = self._provider_successes.get(provider_name, 0) + 1
                    self._retrievals_success += 1

                    logger.info(
                        "Token retrieved from provider",
                        extra={
                            "token_type": token_type.value,
                            "provider": provider_name,
                            "latency_ms": int(latency * 1000),
                        },
                    )
                    return token_value
                else:
                    logger.debug(
                        "Provider returned no token",
                        extra={"provider": provider_name, "token_type": token_type.value},
                    )

            except Exception as e:
                logger.warning(
                    "Provider failed to retrieve token",
                    extra={
                        "provider": provider_name,
                        "token_type": token_type.value,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        # All providers failed
        self._retrievals_failed += 1
        logger.warning(
            "Failed to retrieve token from any provider",
            extra={
                "token_type": token_type.value,
                "providers_tried": len(self._providers),
            },
        )
        return None

    def mark_token_invalid(self, token_type: TokenType, context: Optional[dict] = None, reason: str = "unknown"):
        """Mark a token as invalid to trigger cooldown.

        Args:
            token_type: Type of token
            context: Optional context
            reason: Reason for invalidation
        """
        self._cache.mark_failure(token_type, context)
        logger.info(
            "Token marked invalid",
            extra={
                "token_type": token_type.value,
                "reason": reason,
            },
        )

    def get_stats(self) -> dict:
        """Get token manager statistics."""
        cache_stats = self._cache.get_stats()

        return {
            "cache": cache_stats,
            "retrievals": {
                "total": self._retrievals_total,
                "success": self._retrievals_success,
                "failed": self._retrievals_failed,
                "success_rate": (
                    self._retrievals_success / self._retrievals_total if self._retrievals_total > 0 else 0.0
                ),
            },
            "providers": {
                "count": len(self._providers),
                "attempts": self._provider_attempts,
                "successes": self._provider_successes,
            },
        }

    def clear_cache(self):
        """Clear token cache."""
        self._cache.clear()


# Global singleton instance (lazy initialization)
_token_manager: Optional[POTokenManager] = None


def get_token_manager() -> POTokenManager:
    """Get or create global token manager instance.

    Returns:
        Global POTokenManager instance
    """
    global _token_manager

    if _token_manager is None:
        _token_manager = POTokenManager()
        logger.info("PO token manager initialized")

    return _token_manager
