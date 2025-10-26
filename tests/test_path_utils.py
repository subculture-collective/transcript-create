"""Tests for path matching utilities."""

import pytest

from app.path_utils import (
    CommonMatchers,
    MultiPathMatcher,
    PathMatcher,
    PathMatcherBuilder,
)


class TestPathMatcher:
    """Tests for PathMatcher class."""

    def test_exact_match(self):
        """Test exact pattern matching."""
        matcher = PathMatcher(r"^/health$")
        assert matcher.matches("/health")
        assert not matcher.matches("/health/detailed")
        assert not matcher.matches("/healthy")
        assert not matcher.matches("health")

    def test_uuid_pattern(self):
        """Test matching UUID in path."""
        matcher = PathMatcher(r"^/videos/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not matcher.matches("/videos/invalid-uuid")
        assert not matcher.matches("/videos/")

    def test_optional_suffix(self):
        """Test pattern with optional suffix."""
        matcher = PathMatcher(r"^/search(/suggestions)?$")
        assert matcher.matches("/search")
        assert matcher.matches("/search/suggestions")
        assert not matcher.matches("/search/other")
        assert not matcher.matches("/search/suggestions/more")

    def test_wildcard_suffix(self):
        """Test pattern with wildcard."""
        matcher = PathMatcher(r"^/static/.*$")
        assert matcher.matches("/static/css/style.css")
        assert matcher.matches("/static/js/app.js")
        assert not matcher.matches("/static")
        assert not matcher.matches("/public/file.css")

    def test_repr(self):
        """Test string representation."""
        matcher = PathMatcher(r"^/health$")
        assert repr(matcher) == "PathMatcher('^/health$')"


class TestMultiPathMatcher:
    """Tests for MultiPathMatcher class."""

    def test_multiple_patterns(self):
        """Test matching against multiple patterns."""
        matcher = MultiPathMatcher(r"^/videos$", r"^/videos/[0-9a-f-]{36}$")
        assert matcher.matches("/videos")
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not matcher.matches("/jobs")

    def test_empty_patterns(self):
        """Test with no patterns (should never match)."""
        matcher = MultiPathMatcher()
        assert not matcher.matches("/any/path")
        assert not matcher.matches("/")

    def test_repr(self):
        """Test string representation."""
        matcher = MultiPathMatcher(r"^/a$", r"^/b$")
        repr_str = repr(matcher)
        assert "MultiPathMatcher" in repr_str
        assert "^/a$" in repr_str
        assert "^/b$" in repr_str


class TestPathMatcherBuilder:
    """Tests for PathMatcherBuilder helper methods."""

    def test_exact(self):
        """Test exact path matching."""
        matcher = PathMatcherBuilder.exact("/health")
        assert matcher.matches("/health")
        assert not matcher.matches("/health/detailed")
        assert not matcher.matches("/healthy")

    def test_exact_with_special_chars(self):
        """Test exact matching with special regex characters."""
        matcher = PathMatcherBuilder.exact("/search?query=test")
        assert matcher.matches("/search?query=test")
        assert not matcher.matches("/search")

    def test_with_uuid_param(self):
        """Test path with UUID parameter."""
        matcher = PathMatcherBuilder.with_uuid_param("/videos/{video_id}")
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not matcher.matches("/videos/not-a-uuid")

    def test_with_suffix(self):
        """Test path with suffix."""
        matcher = PathMatcherBuilder.with_suffix("/videos/{video_id}", "/transcript")
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/youtube-transcript")


class TestCommonMatchers:
    """Tests for pre-configured common matchers."""

    def test_video_info(self):
        """Test VIDEO_INFO matcher."""
        assert CommonMatchers.VIDEO_INFO.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not CommonMatchers.VIDEO_INFO.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not CommonMatchers.VIDEO_INFO.matches("/videos")

    def test_video_list(self):
        """Test VIDEO_LIST matcher."""
        assert CommonMatchers.VIDEO_LIST.matches("/videos")
        assert not CommonMatchers.VIDEO_LIST.matches("/videos/")
        assert not CommonMatchers.VIDEO_LIST.matches("/videos/123e4567-e89b-12d3-a456-426614174000")

    def test_video_transcript(self):
        """Test VIDEO_TRANSCRIPT matcher."""
        assert CommonMatchers.VIDEO_TRANSCRIPT.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not CommonMatchers.VIDEO_TRANSCRIPT.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not CommonMatchers.VIDEO_TRANSCRIPT.matches(
            "/videos/123e4567-e89b-12d3-a456-426614174000/youtube-transcript"
        )

    def test_video_youtube_transcript(self):
        """Test VIDEO_YOUTUBE_TRANSCRIPT matcher."""
        assert CommonMatchers.VIDEO_YOUTUBE_TRANSCRIPT.matches(
            "/videos/123e4567-e89b-12d3-a456-426614174000/youtube-transcript"
        )
        assert not CommonMatchers.VIDEO_YOUTUBE_TRANSCRIPT.matches(
            "/videos/123e4567-e89b-12d3-a456-426614174000/transcript"
        )
        assert not CommonMatchers.VIDEO_YOUTUBE_TRANSCRIPT.matches("/videos/123e4567-e89b-12d3-a456-426614174000")

    def test_video_transcripts(self):
        """Test VIDEO_TRANSCRIPTS matcher (both transcript types)."""
        assert CommonMatchers.VIDEO_TRANSCRIPTS.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert CommonMatchers.VIDEO_TRANSCRIPTS.matches(
            "/videos/123e4567-e89b-12d3-a456-426614174000/youtube-transcript"
        )
        assert not CommonMatchers.VIDEO_TRANSCRIPTS.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not CommonMatchers.VIDEO_TRANSCRIPTS.matches("/videos")

    def test_video_metadata(self):
        """Test VIDEO_METADATA matcher (info and list, not transcripts)."""
        assert CommonMatchers.VIDEO_METADATA.matches("/videos")
        assert CommonMatchers.VIDEO_METADATA.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not CommonMatchers.VIDEO_METADATA.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not CommonMatchers.VIDEO_METADATA.matches(
            "/videos/123e4567-e89b-12d3-a456-426614174000/youtube-transcript"
        )

    def test_search(self):
        """Test SEARCH matcher."""
        assert CommonMatchers.SEARCH.matches("/search")
        assert not CommonMatchers.SEARCH.matches("/search/suggestions")

    def test_search_suggestions(self):
        """Test SEARCH_SUGGESTIONS matcher."""
        assert CommonMatchers.SEARCH_SUGGESTIONS.matches("/search/suggestions")
        assert not CommonMatchers.SEARCH_SUGGESTIONS.matches("/search")

    def test_health_checks(self):
        """Test HEALTH_CHECKS matcher."""
        assert CommonMatchers.HEALTH_CHECKS.matches("/health")
        assert CommonMatchers.HEALTH_CHECKS.matches("/live")
        assert CommonMatchers.HEALTH_CHECKS.matches("/ready")
        assert CommonMatchers.HEALTH_CHECKS.matches("/metrics")
        assert not CommonMatchers.HEALTH_CHECKS.matches("/health/detailed")

    def test_static_assets(self):
        """Test STATIC_ASSETS matcher."""
        assert CommonMatchers.STATIC_ASSETS.matches("/static/css/style.css")
        assert CommonMatchers.STATIC_ASSETS.matches("/static/js/app.js")
        assert not CommonMatchers.STATIC_ASSETS.matches("/static")
        assert not CommonMatchers.STATIC_ASSETS.matches("/public/file.css")


class TestEdgeCases:
    """Test edge cases and potential issues."""

    def test_no_false_positives_with_similar_paths(self):
        """Ensure /videos/meta doesn't match video info matcher."""
        # This is the case mentioned in the issue
        assert not CommonMatchers.VIDEO_INFO.matches("/videos/meta")
        assert not CommonMatchers.VIDEO_INFO.matches("/videos/metadata")
        assert not CommonMatchers.VIDEO_INFO.matches("/videos/123")  # short ID

    def test_trailing_slash_handling(self):
        """Test that trailing slashes are handled correctly."""
        matcher = PathMatcherBuilder.exact("/videos")
        assert matcher.matches("/videos")
        assert not matcher.matches("/videos/")  # Trailing slash is different

    def test_case_sensitivity(self):
        """Test that matching is case-sensitive."""
        matcher = PathMatcherBuilder.exact("/Videos")
        assert matcher.matches("/Videos")
        assert not matcher.matches("/videos")

    def test_uuid_variations(self):
        """Test various UUID formats."""
        matcher = CommonMatchers.VIDEO_INFO
        # Valid UUIDs with different casing (lowercase required)
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")
        assert not matcher.matches("/videos/123E4567-E89B-12D3-A456-426614174000")  # Uppercase not matched
        # Invalid UUIDs
        assert not matcher.matches("/videos/123e4567")  # Too short
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000-extra")  # Too long
        assert not matcher.matches("/videos/zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz")  # Invalid chars

    def test_query_parameters_not_included(self):
        """Test that query parameters don't affect path matching."""
        # Note: request.url.path in FastAPI doesn't include query params
        matcher = PathMatcherBuilder.exact("/search")
        assert matcher.matches("/search")
        # Query params are part of the URL but not the path
        assert not matcher.matches("/search?q=test")

    def test_path_segments_with_dots(self):
        """Test paths with dots (like export endpoints)."""
        # Export endpoints like /videos/{id}/transcript.srt are different routes
        matcher = CommonMatchers.VIDEO_TRANSCRIPT
        assert matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript")
        assert not matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000/transcript.srt")
