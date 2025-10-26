# Path Matching Fix for PR #101

This document explains how to integrate the precise path matching utilities into PR #101's `CacheControlMiddleware`.

## Problem in PR #101

The current implementation uses fragile string-based path matching:

```python
# From PR #101 - app/middleware.py
class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        
        # ❌ PROBLEM: This is fragile and matches unintended routes
        if "/videos/" in path and not path.endswith("/transcript") and not path.endswith("/youtube-transcript"):
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
            return response
```

**Issues:**
- `"/videos/" in path` would match `/videos/meta`, `/api/videos/data`, etc.
- Multiple `and not path.endswith(...)` conditions are error-prone
- Hard to maintain as new endpoints are added

## Solution

Replace with the precise path matchers from `app/path_utils.py`:

```python
# Improved version using path_utils
from app.path_utils import CommonMatchers, MultiPathMatcher

class CacheControlMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        
        # Pre-compile matchers for performance
        self.video_metadata_matcher = CommonMatchers.VIDEO_METADATA
        self.transcript_matcher = CommonMatchers.VIDEO_TRANSCRIPTS
        self.search_matcher = MultiPathMatcher(
            r"^/search$",
            r"^/search/suggestions$",
            r"^/search/history$"
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Don't cache error responses
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
            return response

        path = request.url.path

        # Static assets (if any) - long cache
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        # Health check - no cache
        if path in ["/health", "/metrics"]:
            response.headers["Cache-Control"] = "no-store"
            return response

        # ✅ IMPROVED: Precise matching for video metadata
        if self.video_metadata_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
            return response

        # ✅ IMPROVED: Precise matching for transcripts
        if self.transcript_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=300"
            return response

        # ✅ IMPROVED: Precise matching for search
        if self.search_matcher.matches(path):
            response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=60"
            return response

        # Default: no explicit cache control
        return response
```

## Migration Steps for PR #101

### 1. Update the import in `app/middleware.py`

Add the import at the top:
```python
from app.path_utils import CommonMatchers, MultiPathMatcher
```

### 2. Add `__init__` method to `CacheControlMiddleware`

```python
def __init__(self, app):
    super().__init__(app)
    # Pre-compile matchers for performance
    self.video_metadata_matcher = CommonMatchers.VIDEO_METADATA
    self.transcript_matcher = CommonMatchers.VIDEO_TRANSCRIPTS
    self.search_matcher = MultiPathMatcher(
        r"^/search$",
        r"^/search/suggestions$",
        r"^/search/history$"
    )
```

### 3. Replace string matching with matcher calls

**Before:**
```python
if "/videos/" in path and not path.endswith("/transcript") and not path.endswith("/youtube-transcript"):
```

**After:**
```python
if self.video_metadata_matcher.matches(path):
```

**Before:**
```python
if path.endswith("/transcript") or path.endswith("/youtube-transcript"):
```

**After:**
```python
if self.transcript_matcher.matches(path):
```

## Benefits

1. **No false positives**: Won't match `/videos/meta` or other unintended paths
2. **Better performance**: Regex patterns are compiled once at middleware initialization
3. **More maintainable**: Clear, explicit pattern definitions
4. **Easier to test**: Can unit test pattern matching separately
5. **More readable**: Intent is clear from matcher names

## Testing

The path matching utilities include comprehensive tests:

```bash
# Run the path matching tests
pytest tests/test_path_utils.py -v

# Run the example to see it in action
PYTHONPATH=. python examples/cache_control_middleware.py
```

Expected output shows precise matching:
```
VIDEO_METADATA matcher:
  ✓ MATCH      /videos/123e4567-e89b-12d3-a456-426614174000
  ✗ no match   /videos/123e4567-e89b-12d3-a456-426614174000/transcript
  ✗ no match   /videos/meta
  ✗ no match   /videos/metadata
  ✓ MATCH      /videos
```

## Performance Impact

- **Initialization**: Minimal one-time cost to compile regex patterns
- **Per-request**: Faster than multiple string operations
- **Memory**: Negligible - compiled patterns are reused

## See Also

- `app/path_utils.py` - Complete implementation
- `tests/test_path_utils.py` - 28 tests covering all functionality
- `examples/cache_control_middleware.py` - Complete example
- `docs/PATH_MATCHING.md` - Full documentation
