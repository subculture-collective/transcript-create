"""Tests for PO token manager."""

import time
from unittest.mock import MagicMock

from worker.po_token_manager import POToken, POTokenCache, POTokenManager, TokenType


class TestPOToken:
    """Tests for POToken dataclass."""

    def test_token_creation(self):
        """Test creating a PO token."""
        token = POToken(
            value="test_token_123",
            token_type=TokenType.PLAYER,
            source="manual",
        )
        assert token.value == "test_token_123"
        assert token.token_type == TokenType.PLAYER
        assert token.source == "manual"
        assert token.timestamp > 0

    def test_token_expiration(self):
        """Test token expiration checking."""
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            timestamp=time.time() - 3700,  # 1 hour + 100 seconds ago
        )
        # Token with TTL of 3600 seconds should be expired
        assert token.is_expired(3600) is True
        # Token with TTL of 4000 seconds should not be expired
        assert token.is_expired(4000) is False

    def test_token_age(self):
        """Test token age calculation."""
        past_time = time.time() - 100
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            timestamp=past_time,
        )
        age = token.age_seconds()
        # Allow small margin for test execution time
        assert 99 <= age <= 102


class TestPOTokenCache:
    """Tests for POTokenCache."""

    def test_cache_set_and_get(self):
        """Test basic cache set and get operations."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=60)
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            source="manual",
        )

        cache.set(token)
        retrieved = cache.get(TokenType.PLAYER)

        assert retrieved is not None
        assert retrieved.value == "test_token"
        assert retrieved.source == "manual"

    def test_cache_miss(self):
        """Test cache miss for non-existent token."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=60)
        retrieved = cache.get(TokenType.GVS)
        assert retrieved is None

    def test_cache_expiration(self):
        """Test that expired tokens are not returned."""
        cache = POTokenCache(ttl=1, cooldown_seconds=60)  # 1 second TTL
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            source="manual",
            timestamp=time.time() - 2,  # 2 seconds ago
        )

        cache.set(token)
        time.sleep(0.1)  # Brief pause
        retrieved = cache.get(TokenType.PLAYER)
        
        # Should return None because token is expired
        assert retrieved is None

    def test_cache_cooldown(self):
        """Test that tokens in cooldown are not returned."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=2)
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            source="manual",
        )

        cache.set(token)
        cache.mark_failure(TokenType.PLAYER)

        # Should return None because token is in cooldown
        retrieved = cache.get(TokenType.PLAYER)
        assert retrieved is None

        # Wait for cooldown to expire
        time.sleep(2.1)
        retrieved = cache.get(TokenType.PLAYER)
        # Should be available again after cooldown
        assert retrieved is not None

    def test_cache_with_context(self):
        """Test cache with context keys."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=60)
        
        # Same token type but different contexts
        token1 = POToken(
            value="token_region_us",
            token_type=TokenType.PLAYER,
            source="manual",
            context={"region": "us"},
        )
        token2 = POToken(
            value="token_region_eu",
            token_type=TokenType.PLAYER,
            source="manual",
            context={"region": "eu"},
        )

        cache.set(token1, context={"region": "us"})
        cache.set(token2, context={"region": "eu"})

        retrieved_us = cache.get(TokenType.PLAYER, context={"region": "us"})
        retrieved_eu = cache.get(TokenType.PLAYER, context={"region": "eu"})

        assert retrieved_us.value == "token_region_us"
        assert retrieved_eu.value == "token_region_eu"

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=60)
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            source="manual",
        )

        # One miss (no token cached)
        cache.get(TokenType.PLAYER)
        
        # Set token
        cache.set(token)
        
        # One hit (token is cached)
        cache.get(TokenType.PLAYER)
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_requests"] == 2
        assert stats["hit_rate"] == 0.5
        assert stats["cached_tokens"] == 1

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = POTokenCache(ttl=3600, cooldown_seconds=60)
        token = POToken(
            value="test_token",
            token_type=TokenType.PLAYER,
            source="manual",
        )

        cache.set(token)
        assert cache.get(TokenType.PLAYER) is not None

        cache.clear()
        assert cache.get(TokenType.PLAYER) is None
        stats = cache.get_stats()
        assert stats["cached_tokens"] == 0


class TestPOTokenManager:
    """Tests for POTokenManager."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = POTokenManager()
        assert manager is not None
        stats = manager.get_stats()
        assert stats["providers"]["count"] == 0

    def test_manager_with_manual_provider(self):
        """Test manager with manual token provider."""
        from worker.po_token_providers import ManualTokenProvider

        provider = ManualTokenProvider(player_token="manual_player_token_123")
        manager = POTokenManager(providers=[provider])

        token = manager.get_token(TokenType.PLAYER)
        assert token == "manual_player_token_123"

        # Second call should hit cache
        token2 = manager.get_token(TokenType.PLAYER)
        assert token2 == "manual_player_token_123"

        stats = manager.get_stats()
        assert stats["retrievals"]["success"] == 2
        assert stats["cache"]["hits"] == 1

    def test_manager_provider_fallback(self):
        """Test manager falls back to next provider on failure."""
        # Create mock providers
        provider1 = MagicMock()
        provider1.is_available.return_value = True
        provider1.get_token.return_value = None  # First provider returns nothing

        provider2 = MagicMock()
        provider2.is_available.return_value = True
        provider2.get_token.return_value = "token_from_provider2"

        manager = POTokenManager(providers=[provider1, provider2])
        token = manager.get_token(TokenType.PLAYER)

        assert token == "token_from_provider2"
        assert provider1.get_token.called
        assert provider2.get_token.called

    def test_manager_no_token_available(self):
        """Test manager when no provider can return a token."""
        provider = MagicMock()
        provider.is_available.return_value = True
        provider.get_token.return_value = None

        manager = POTokenManager(providers=[provider])
        token = manager.get_token(TokenType.PLAYER)

        assert token is None
        stats = manager.get_stats()
        assert stats["retrievals"]["failed"] == 1

    def test_manager_mark_token_invalid(self):
        """Test marking a token as invalid triggers cooldown."""
        from worker.po_token_providers import ManualTokenProvider

        provider = ManualTokenProvider(player_token="test_token")
        manager = POTokenManager(
            providers=[provider],
            cooldown_seconds=2,
        )

        # Get token to cache it
        token = manager.get_token(TokenType.PLAYER)
        assert token == "test_token"

        # Mark as invalid
        manager.mark_token_invalid(TokenType.PLAYER, reason="test_failure")

        # Token should not be returned during cooldown
        token2 = manager.get_token(TokenType.PLAYER)
        # Due to cooldown, should get fresh token from provider again
        assert token2 == "test_token"

        stats = manager.get_stats()
        # First retrieval was success, second was also success but went to provider
        assert stats["retrievals"]["success"] == 2

    def test_manager_add_provider(self):
        """Test dynamically adding providers."""
        manager = POTokenManager()
        stats = manager.get_stats()
        assert stats["providers"]["count"] == 0

        provider = MagicMock()
        provider.is_available.return_value = True
        manager.add_provider(provider)

        stats = manager.get_stats()
        assert stats["providers"]["count"] == 1

    def test_manager_clear_cache(self):
        """Test clearing manager cache."""
        from worker.po_token_providers import ManualTokenProvider

        provider = ManualTokenProvider(player_token="test_token")
        manager = POTokenManager(providers=[provider])

        # Get token to cache it
        manager.get_token(TokenType.PLAYER)
        
        # Clear cache
        manager.clear_cache()
        
        # Next get should go to provider again (cache miss)
        manager.get_token(TokenType.PLAYER)
        
        stats = manager.get_stats()
        assert stats["cache"]["cached_tokens"] == 1  # Only current token
        assert stats["cache"]["hits"] == 0  # No hits after clear


class TestTokenTypeEnum:
    """Tests for TokenType enum."""

    def test_token_types(self):
        """Test all token types are defined."""
        assert TokenType.PLAYER.value == "player"
        assert TokenType.GVS.value == "gvs"
        assert TokenType.SUBS.value == "subs"

    def test_token_type_iteration(self):
        """Test iterating over token types."""
        types = list(TokenType)
        assert len(types) == 3
        assert TokenType.PLAYER in types
        assert TokenType.GVS in types
        assert TokenType.SUBS in types
