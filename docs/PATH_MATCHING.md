# Path Matching Utilities

This module provides precise path matching utilities for FastAPI middleware, replacing fragile string-based path matching with compiled regular expressions.

## Problem

String-based path matching like `"/videos/" in path` is fragile and can match unintended routes:

```python
# ❌ FRAGILE: String-based matching
if "/videos/" in path and not path.endswith("/transcript"):
    # Problem: This matches:
    # - /videos/123e4567...  ✓ intended
    # - /videos/meta         ✗ unintended!
    # - /api/videos/data     ✗ unintended!
    response.headers["Cache-Control"] = "public, max-age=300"
```

## Solution

Use the `path_utils` module for precise, regex-based matching:

```python
# ✅ PRECISE: Regex-based matching
from app.path_utils import CommonMatchers

if CommonMatchers.VIDEO_METADATA.matches(path):
    # This ONLY matches:
    # - /videos/123e4567...  ✓ video with UUID
    # - /videos              ✓ list endpoint
    # Does NOT match:
    # - /videos/meta         ✗
    # - /api/videos/data     ✗
    response.headers["Cache-Control"] = "public, max-age=300"
```

## Usage

### Pre-configured Matchers

The `CommonMatchers` class provides ready-to-use matchers for common API patterns:

```python
from app.path_utils import CommonMatchers

# Video endpoints
CommonMatchers.VIDEO_INFO          # /videos/{uuid}
CommonMatchers.VIDEO_LIST          # /videos
CommonMatchers.VIDEO_TRANSCRIPT    # /videos/{uuid}/transcript
CommonMatchers.VIDEO_YOUTUBE_TRANSCRIPT  # /videos/{uuid}/youtube-transcript

# Combined matchers
CommonMatchers.VIDEO_METADATA      # /videos and /videos/{uuid} (NOT transcripts)
CommonMatchers.VIDEO_TRANSCRIPTS   # Both transcript types

# Search endpoints
CommonMatchers.SEARCH              # /search
CommonMatchers.SEARCH_SUGGESTIONS  # /search/suggestions

# Health checks
CommonMatchers.HEALTH_CHECKS       # /health, /live, /ready, /metrics

# Static assets
CommonMatchers.STATIC_ASSETS       # /static/*
```

### Custom Matchers

Build custom matchers using `PathMatcherBuilder`:

```python
from app.path_utils import PathMatcherBuilder, PathMatcher, MultiPathMatcher

# Exact path matching
health_matcher = PathMatcherBuilder.exact("/health")

# Path with UUID parameter
video_matcher = PathMatcherBuilder.with_uuid_param("/videos/{video_id}")

# Path with UUID and suffix
transcript_matcher = PathMatcherBuilder.with_suffix(
    "/videos/{video_id}", 
    "/transcript"
)

# Multiple patterns
multi_matcher = MultiPathMatcher(
    r"^/search$",
    r"^/search/suggestions$"
)

# Raw regex for complex patterns
custom_matcher = PathMatcher(r"^/videos/[0-9a-f-]{36}/export\.(json|pdf)$")
```

### Complete Middleware Example

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.path_utils import CommonMatchers, MultiPathMatcher

class CacheControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        
        # Pre-compile matchers for performance
        self.video_metadata_matcher = CommonMatchers.VIDEO_METADATA
        self.transcript_matcher = CommonMatchers.VIDEO_TRANSCRIPTS
        self.search_matcher = MultiPathMatcher(
            r"^/search$",
            r"^/search/suggestions$"
        )
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        
        # Don't cache errors
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
            return response
        
        # Apply caching based on precise path matching
        if self.video_metadata_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=300"
        elif self.transcript_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif self.search_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=600"
        
        return response
```

## API Reference

### PathMatcher

Match a single regex pattern:

```python
matcher = PathMatcher(r"^/videos/[0-9a-f-]{36}$")
matcher.matches("/videos/123e4567-e89b-12d3-a456-426614174000")  # True
matcher.matches("/videos/meta")  # False
```

### MultiPathMatcher

Match multiple patterns (OR logic):

```python
matcher = MultiPathMatcher(
    r"^/videos$",
    r"^/videos/[0-9a-f-]{36}$"
)
matcher.matches("/videos")  # True
matcher.matches("/videos/123e4567...")  # True
matcher.matches("/videos/meta")  # False
```

### PathMatcherBuilder

Helper methods for common patterns:

- `PathMatcherBuilder.exact(path)` - Exact path match
- `PathMatcherBuilder.with_uuid_param(path)` - Path with UUID parameter
- `PathMatcherBuilder.with_suffix(path, suffix)` - Path + suffix

### CommonMatchers

Pre-configured matchers for the API's common endpoints. See Usage section above.

## Benefits

1. **Precision**: Only matches intended routes, preventing accidental matches
2. **Performance**: Regex patterns are compiled once and reused
3. **Readability**: Clear intent with descriptive matcher names
4. **Testability**: Easy to unit test with concrete examples
5. **Maintainability**: Centralized pattern definitions

## Testing

Run the test suite:

```bash
pytest tests/test_path_utils.py -v
```

See the example demonstration:

```bash
PYTHONPATH=. python examples/cache_control_middleware.py
```

## Migration Guide

To migrate from string-based matching to precise matching:

**Before:**
```python
# Fragile string matching
if "/videos/" in path and not path.endswith("/transcript"):
    apply_video_cache(response)
```

**After:**
```python
# Precise regex matching
from app.path_utils import CommonMatchers

if CommonMatchers.VIDEO_METADATA.matches(path):
    apply_video_cache(response)
```

## See Also

- `examples/cache_control_middleware.py` - Complete example implementation
- `tests/test_path_utils.py` - Comprehensive test suite showing all features
- PR #101 - Original issue that motivated this solution
