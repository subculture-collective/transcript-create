"""Shared utilities for yt-dlp client strategies."""

from typing import List, Optional


def get_client_extractor_args(client: str) -> Optional[List[str]]:
    """Get extractor args for a given client type.

    Args:
        client: Client type (web_safari, ios, android, tv)

    Returns:
        List of extractor args or None if client is unknown
    """
    client_args = {
        "web_safari": ["--extractor-args", "youtube:player_client=web_safari"],
        "ios": ["--extractor-args", "youtube:player_client=ios"],
        "android": ["--extractor-args", "youtube:player_client=android"],
        "tv": ["--extractor-args", "youtube:player_client=tv_embedded"],
    }
    return client_args.get(client)
