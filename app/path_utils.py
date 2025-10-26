"""Utilities for precise URL path matching in middleware.

This module provides utilities for matching URL paths against patterns,
avoiding fragile string-based matching that could match unintended routes.
"""

import re
from typing import Callable, Pattern


class PathMatcher:
    """Matcher for URL paths using compiled regex patterns."""

    def __init__(self, pattern: str):
        """Initialize the path matcher with a regex pattern.

        Args:
            pattern: Regular expression pattern for matching paths.
                    Use ^ and $ anchors for exact matching.

        Examples:
            # Match /videos/{uuid} but not /videos/{uuid}/transcript
            PathMatcher(r"^/videos/[0-9a-f-]{36}$")

            # Match any transcript endpoint
            PathMatcher(r"^/videos/[0-9a-f-]{36}/(transcript|youtube-transcript)$")

            # Match /search or /search/suggestions
            PathMatcher(r"^/search(/suggestions)?$")
        """
        self._pattern: Pattern = re.compile(pattern)
        self._pattern_str = pattern

    def matches(self, path: str) -> bool:
        """Check if the path matches the pattern.

        Args:
            path: URL path to check

        Returns:
            True if path matches, False otherwise
        """
        return bool(self._pattern.match(path))

    def __repr__(self) -> str:
        return f"PathMatcher({self._pattern_str!r})"


class MultiPathMatcher:
    """Matcher that combines multiple path patterns."""

    def __init__(self, *patterns: str):
        """Initialize with multiple regex patterns.

        Args:
            *patterns: One or more regex patterns to match against

        Examples:
            # Match either video info or list endpoint
            MultiPathMatcher(
                r"^/videos/[0-9a-f-]{36}$",
                r"^/videos$"
            )
        """
        self._matchers = [PathMatcher(p) for p in patterns]

    def matches(self, path: str) -> bool:
        """Check if path matches any of the patterns.

        Args:
            path: URL path to check

        Returns:
            True if path matches any pattern, False otherwise
        """
        return any(matcher.matches(path) for matcher in self._matchers)

    def __repr__(self) -> str:
        patterns = [m._pattern_str for m in self._matchers]
        return f"MultiPathMatcher({', '.join(repr(p) for p in patterns)})"


class PathMatcherBuilder:
    """Builder for common path matching patterns with FastAPI path parameters."""

    # UUID pattern for path parameters
    UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

    @staticmethod
    def exact(path: str) -> PathMatcher:
        """Create a matcher for an exact path.

        Args:
            path: Exact path to match (e.g., "/health", "/videos")

        Returns:
            PathMatcher for the exact path

        Example:
            >>> matcher = PathMatcherBuilder.exact("/health")
            >>> matcher.matches("/health")
            True
            >>> matcher.matches("/health/detailed")
            False
        """
        return PathMatcher(f"^{re.escape(path)}$")

    @staticmethod
    def with_uuid_param(base_path: str, param_name: str = "id") -> PathMatcher:
        """Create a matcher for a path with a single UUID parameter.

        Args:
            base_path: Base path with {param_name} placeholder
            param_name: Name of the UUID parameter (default: "id")

        Returns:
            PathMatcher for the path with UUID parameter

        Example:
            >>> matcher = PathMatcherBuilder.with_uuid_param("/videos/{video_id}")
            >>> matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
            True
            >>> matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
            False
        """
        # Replace any {param} with UUID pattern
        # First escape the entire path, then replace escaped placeholder
        pattern = re.escape(base_path)
        # Match escaped curly braces with content: \{anything\}
        pattern = re.sub(r'\\{[^}]+\\}', PathMatcherBuilder.UUID_PATTERN, pattern)
        return PathMatcher(f"^{pattern}$")

    @staticmethod
    def with_suffix(base_path: str, suffix: str) -> PathMatcher:
        """Create a matcher for a path with a specific suffix.

        Args:
            base_path: Base path with {param} placeholder (e.g., "/videos/{video_id}")
            suffix: Suffix to append (e.g., "/transcript")

        Returns:
            PathMatcher for the path with suffix

        Example:
            >>> matcher = PathMatcherBuilder.with_suffix("/videos/{video_id}", "/transcript")
            >>> matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
            True
            >>> matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
            False
        """
        # Replace {param} with UUID pattern and add suffix
        pattern = re.escape(base_path)
        # Match escaped curly braces with content: \{anything\}
        pattern = re.sub(r'\\{[^}]+\\}', PathMatcherBuilder.UUID_PATTERN, pattern)
        pattern += re.escape(suffix)
        return PathMatcher(f"^{pattern}$")


# Pre-built matchers for common API patterns
class CommonMatchers:
    """Pre-configured matchers for common API endpoint patterns."""

    # Video-related endpoints
    VIDEO_INFO = PathMatcherBuilder.with_uuid_param("/videos/{video_id}")
    VIDEO_LIST = PathMatcherBuilder.exact("/videos")
    VIDEO_TRANSCRIPT = PathMatcherBuilder.with_suffix("/videos/{video_id}", "/transcript")
    VIDEO_YOUTUBE_TRANSCRIPT = PathMatcherBuilder.with_suffix("/videos/{video_id}", "/youtube-transcript")

    # Transcript endpoints (both types)
    VIDEO_TRANSCRIPTS = MultiPathMatcher(
        r"^/videos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(transcript|youtube-transcript)$"
    )

    # Video metadata (info and list, excluding transcripts)
    VIDEO_METADATA = MultiPathMatcher(
        r"^/videos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        r"^/videos$"
    )

    # Search endpoints
    SEARCH = PathMatcherBuilder.exact("/search")
    SEARCH_SUGGESTIONS = PathMatcherBuilder.exact("/search/suggestions")

    # Health check endpoints
    HEALTH_CHECKS = MultiPathMatcher(
        r"^/health$",
        r"^/live$",
        r"^/ready$",
        r"^/metrics$"
    )

    # Static assets (if any)
    STATIC_ASSETS = PathMatcher(r"^/static/.*$")
