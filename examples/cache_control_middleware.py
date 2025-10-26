"""Example middleware demonstrating precise path matching for cache control headers.

This module shows how to use the path_utils module to implement the
CacheControlMiddleware from PR #101 with precise path matching instead of
fragile string-based matching.

BEFORE (Fragile):
    if "/videos/" in path and not path.endswith("/transcript"):
        # This would match unintended routes like /videos/meta

AFTER (Precise):
    if CommonMatchers.VIDEO_METADATA.matches(path):
        # This only matches /videos and /videos/{uuid}, not /videos/meta
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.path_utils import CommonMatchers, MultiPathMatcher, PathMatcherBuilder


class PreciseCacheControlMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add Cache-Control headers using precise path matching.

    This replaces fragile string-based matching with regex patterns to ensure
    only intended endpoints receive specific cache headers.
    """

    def __init__(self, app):
        super().__init__(app)

        # Define matchers for different caching strategies
        # These are compiled once during initialization for performance

        # Long-term immutable cache for static assets
        self.static_matcher = CommonMatchers.STATIC_ASSETS

        # No cache for health checks and error endpoints
        self.no_cache_matcher = CommonMatchers.HEALTH_CHECKS

        # Moderate cache for video metadata (5 minutes)
        # Matches: /videos, /videos/{uuid}
        # Does NOT match: /videos/meta, /videos/{uuid}/transcript
        self.video_metadata_matcher = CommonMatchers.VIDEO_METADATA

        # Long cache for transcript data (1 hour)
        # Matches: /videos/{uuid}/transcript, /videos/{uuid}/youtube-transcript
        # Does NOT match: /videos/{uuid}, /videos/{uuid}/transcript.srt
        self.transcript_matcher = CommonMatchers.VIDEO_TRANSCRIPTS

        # Medium cache for search results (10 minutes)
        self.search_matcher = MultiPathMatcher(r"^/search$", r"^/search/suggestions$", r"^/search/history$")

        # Short cache for user-specific data
        self.user_data_matcher = PathMatcherBuilder.exact("/auth/me")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Don't cache error responses
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
            return response

        path = request.url.path

        # Static assets - long cache with immutable flag
        if self.static_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        # Health checks and metrics - no cache
        if self.no_cache_matcher.matches(path):
            response.headers["Cache-Control"] = "no-store"
            return response

        # Video metadata - moderate cache with revalidation
        # This precisely matches /videos and /videos/{uuid}
        # WITHOUT matching /videos/meta or other unintended paths
        if self.video_metadata_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
            return response

        # Transcript data - longer cache
        # This precisely matches transcript endpoints only
        if self.transcript_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=300"
            return response

        # Search results - medium cache
        if self.search_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=60"
            return response

        # User-specific data - short private cache
        if self.user_data_matcher.matches(path):
            response.headers["Cache-Control"] = "private, max-age=60"
            return response

        # Default: no explicit cache control (let browser decide)
        return response


# Additional examples of creating custom matchers for specific use cases


def create_export_matchers():
    """Create matchers for export endpoints with file extensions."""
    # Match export endpoints like /videos/{uuid}/transcript.srt
    return MultiPathMatcher(
        r"^/videos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/transcript\.(srt|vtt|json|pdf)$",
        r"^/videos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/youtube-transcript\.(srt|vtt|json)$",
    )


def create_admin_matchers():
    """Create matchers for admin endpoints."""
    # Match admin endpoints starting with /admin/
    return MultiPathMatcher(
        r"^/admin/events$",
        r"^/admin/events\.csv$",
        r"^/admin/events/summary$",
        r"^/admin/users/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/plan$",
    )


# Example usage in tests or documentation
if __name__ == "__main__":
    # Demonstrate the difference between fragile and precise matching

    test_paths = [
        "/videos/123e4567-e89b-12d3-a456-426614174000",  # Video info - should match
        "/videos/123e4567-e89b-12d3-a456-426614174000/transcript",  # Transcript - different matcher
        "/videos/meta",  # NOT a video - should NOT match video_metadata
        "/videos/metadata",  # NOT a video - should NOT match video_metadata
        "/videos",  # List - should match video_metadata
        "/api/videos/something",  # NOT videos endpoint
    ]

    print("Testing path matching precision:\n")

    matcher = CommonMatchers.VIDEO_METADATA
    print("VIDEO_METADATA matcher:")
    for path in test_paths:
        result = "✓ MATCH" if matcher.matches(path) else "✗ no match"
        print(f"  {result:12} {path}")

    print("\nVIDEO_TRANSCRIPTS matcher:")
    matcher = CommonMatchers.VIDEO_TRANSCRIPTS
    for path in test_paths:
        result = "✓ MATCH" if matcher.matches(path) else "✗ no match"
        print(f"  {result:12} {path}")

    print("\n" + "=" * 60)
    print("Note: String-based '/videos/' in path would incorrectly match")
    print("paths like '/videos/meta' and '/api/videos/something'")
    print("=" * 60)
