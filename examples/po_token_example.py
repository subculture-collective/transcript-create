#!/usr/bin/env python3
"""Example usage of PO Token Manager.

This script demonstrates how to use the PO Token Manager
for obtaining and managing YouTube PO tokens.
"""

from worker.po_token_manager import POTokenManager, TokenType
from worker.po_token_providers import ManualTokenProvider, HTTPTokenProvider


def example_basic_usage():
    """Example: Basic token retrieval."""
    print("=" * 60)
    print("Example 1: Basic Token Retrieval")
    print("=" * 60)

    # Create manual provider with test tokens
    provider = ManualTokenProvider(
        player_token="manual_player_token_abc123",
        gvs_token="manual_gvs_token_def456",
    )

    # Initialize manager with provider
    manager = POTokenManager(providers=[provider])

    # Request tokens
    player_token = manager.get_token(TokenType.PLAYER)
    gvs_token = manager.get_token(TokenType.GVS)
    subs_token = manager.get_token(TokenType.SUBS)  # Not configured, returns None

    print(f"Player token: {player_token}")
    print(f"GVS token: {gvs_token}")
    print(f"Subs token: {subs_token}")
    print()


def example_caching():
    """Example: Token caching behavior."""
    print("=" * 60)
    print("Example 2: Token Caching")
    print("=" * 60)

    provider = ManualTokenProvider(player_token="cached_token_123")
    manager = POTokenManager(providers=[provider], ttl=3600, cooldown_seconds=60)

    # First request - cache miss, goes to provider
    print("First request (cache miss):")
    token1 = manager.get_token(TokenType.PLAYER)
    print(f"  Token: {token1}")

    # Second request - cache hit
    print("Second request (cache hit):")
    token2 = manager.get_token(TokenType.PLAYER)
    print(f"  Token: {token2}")

    # Get stats
    stats = manager.get_stats()
    print(f"\nCache stats:")
    print(f"  Hits: {stats['cache']['hits']}")
    print(f"  Misses: {stats['cache']['misses']}")
    print(f"  Hit rate: {stats['cache']['hit_rate']:.1%}")
    print()


def example_context():
    """Example: Token caching with context."""
    print("=" * 60)
    print("Example 3: Context-based Caching")
    print("=" * 60)

    provider = ManualTokenProvider(player_token="context_token")
    manager = POTokenManager(providers=[provider])

    # Different contexts create separate cache entries
    context_us = {"region": "us"}
    context_eu = {"region": "eu"}

    token_us = manager.get_token(TokenType.PLAYER, context=context_us)
    token_eu = manager.get_token(TokenType.PLAYER, context=context_eu)

    print(f"Token for US region: {token_us}")
    print(f"Token for EU region: {token_eu}")
    print(f"Both contexts cached separately")
    print()


def example_failure_handling():
    """Example: Token failure and cooldown."""
    print("=" * 60)
    print("Example 4: Failure Handling and Cooldown")
    print("=" * 60)

    provider = ManualTokenProvider(player_token="test_token")
    manager = POTokenManager(providers=[provider], cooldown_seconds=2)

    # Get token
    token = manager.get_token(TokenType.PLAYER)
    print(f"Initial token: {token}")

    # Mark token as invalid (e.g., after 403 error)
    print("Marking token as invalid...")
    manager.mark_token_invalid(TokenType.PLAYER, reason="forbidden_error")

    # During cooldown, token won't be returned from cache
    print("Requesting token during cooldown:")
    token2 = manager.get_token(TokenType.PLAYER)
    print(f"  Token (fetched from provider again): {token2}")
    print()


def example_provider_chain():
    """Example: Multiple providers with fallback."""
    print("=" * 60)
    print("Example 5: Provider Chain with Fallback")
    print("=" * 60)

    # First provider with only player token
    provider1 = ManualTokenProvider(player_token="provider1_player")

    # Second provider with different tokens
    provider2 = ManualTokenProvider(
        gvs_token="provider2_gvs",
        subs_token="provider2_subs",
    )

    # Manager tries providers in order
    manager = POTokenManager(providers=[provider1, provider2])

    # Player token from provider1
    player = manager.get_token(TokenType.PLAYER)
    print(f"Player token (from provider1): {player}")

    # GVS token from provider2 (provider1 doesn't have it)
    gvs = manager.get_token(TokenType.GVS)
    print(f"GVS token (from provider2): {gvs}")

    # Check provider stats
    stats = manager.get_stats()
    print(f"\nProvider attempts: {stats['providers']['attempts']}")
    print(f"Provider successes: {stats['providers']['successes']}")
    print()


def example_http_provider():
    """Example: HTTP provider (mock)."""
    print("=" * 60)
    print("Example 6: HTTP Provider Configuration")
    print("=" * 60)

    # Note: This example assumes you have a token service running
    # at http://localhost:8080 that implements the token API
    provider = HTTPTokenProvider(
        base_url="http://localhost:8080",
        timeout=5.0,
    )

    print(f"HTTP provider configured: {provider.is_available()}")
    print(f"Base URL: http://localhost:8080")
    print(f"Timeout: 5.0 seconds")
    print()
    print("Note: HTTP provider requires external service to be running.")
    print("Expected API endpoint: GET /token?type=<player|gvs|subs>")
    print("Expected response: {\"token\": \"value\"}")
    print()


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("PO Token Manager Examples")
    print("=" * 60 + "\n")

    example_basic_usage()
    example_caching()
    example_context()
    example_failure_handling()
    example_provider_chain()
    example_http_provider()

    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
