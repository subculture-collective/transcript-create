"""Security middleware for headers, rate limiting, and request validation."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .analytics_identity import AnalyticsIdentityMiddleware
from .common.session import SESSION_COOKIE
from .logging_config import get_logger
from .settings import settings

logger = get_logger(__name__)
_rate_limit_backend_healthy = True


def rate_limit_backend_health() -> dict[str, str]:
    """Return the process-local status observed by the rate limiter."""
    return {"status": "healthy" if _rate_limit_backend_healthy else "degraded"}


PRIVATE_NO_STORE = "private, no-store"
PUBLIC_CACHE_POLICIES = {
    ("GET", "/search"): "public, max-age=60, stale-while-revalidate=30",
    ("GET", "/search/grouped"): "public, max-age=60, stale-while-revalidate=30",
    ("GET", "/search/mention-map"): "public, max-age=60, stale-while-revalidate=30",
    ("GET", "/search/suggestions"): "public, max-age=30, stale-while-revalidate=15",
    ("GET", "/search/popular"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/videos"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/videos/{video_id}"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/videos/{video_id}/chapters"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/videos/{video_id}/transcript"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/videos/{video_id}/youtube-transcript"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/archive/summary"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/archive/timeline"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/archive/intelligence"): "public, max-age=300, stale-while-revalidate=60",
    ("GET", "/archive/intelligence/periods"): "public, max-age=300, stale-while-revalidate=60",
}
_CREDENTIAL_COOKIES = frozenset((SESSION_COOKIE, "tc_oauth_state"))
_PUBLIC_VARY_HEADERS = ("Cookie", "Authorization", "X-API-Key")

API_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    )
)


def apply_security_headers(response: Response) -> Response:
    """Apply the standard API security headers to a response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers.setdefault("Content-Security-Policy", API_CONTENT_SECURITY_POLICY)
    if "server" in response.headers:
        del response.headers["server"]
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["API-Version"] = "1"
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        return apply_security_headers(response)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Atomic, process-shared fixed-window rate limiting backed by Redis."""

    _INCREMENT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return {count, redis.call('TTL', KEYS[1])}
    """

    def __init__(self, app, redis_client=None, requests_limit=None, window_seconds=None):
        super().__init__(app)
        self.redis = redis_client or (Redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None)
        self.requests_limit = requests_limit or settings.RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/live", "/ready", "/metrics"]:
            return await call_next(request)

        # Get client identifier (IP or user ID)
        client_id = self._get_client_id(request)

        # Check rate limit
        limited, retry_after = await self._is_rate_limited(client_id)
        if limited:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_id": client_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from session
        # For now, use IP address
        if request.client:
            return request.client.host
        return "unknown"

    async def _is_rate_limited(self, client_id: str) -> tuple[bool, int]:
        if self.redis is None:
            self._record_backend_failure("REDIS_URL is not configured")
            return False, self.window_seconds

        key = f"rate-limit:{client_id}"
        try:
            count, ttl = await self.redis.eval(self._INCREMENT_SCRIPT, 1, key, self.window_seconds)
            global _rate_limit_backend_healthy
            _rate_limit_backend_healthy = True
            return int(count) > self.requests_limit, max(int(ttl), 1)
        except Exception as exc:
            self._record_backend_failure(str(exc))
            return False, self.window_seconds

    @staticmethod
    def _record_backend_failure(error: str) -> None:
        from app.metrics import rate_limit_backend_failures_total

        global _rate_limit_backend_healthy
        _rate_limit_backend_healthy = False
        rate_limit_backend_failures_total.inc()
        logger.error("Rate limiter Redis backend unavailable; failing open", extra={"error": error})


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Fail closed unless a safe anonymous GET route is explicitly public."""

    @staticmethod
    def _merge_vary(response: Response) -> None:
        existing = [part.strip() for part in response.headers.get("Vary", "").split(",") if part.strip()]
        seen = {part.casefold() for part in existing}
        for header in _PUBLIC_VARY_HEADERS:
            if header.casefold() not in seen:
                existing.append(header)
                seen.add(header.casefold())
        response.headers["Vary"] = ", ".join(existing)

    @staticmethod
    def _request_has_credentials(request: Request) -> bool:
        return (
            "authorization" in request.headers
            or "x-api-key" in request.headers
            or any(cookie in request.cookies for cookie in _CREDENTIAL_COOKIES)
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        downstream_policy = response.headers.get("Cache-Control", "")
        must_be_private = (
            response.status_code >= 400
            or request.method != "GET"
            or self._request_has_credentials(request)
            or "set-cookie" in response.headers
            or "no-store" in downstream_policy.casefold()
            or "private" in downstream_policy.casefold()
        )
        if must_be_private:
            response.headers["Cache-Control"] = PRIVATE_NO_STORE
            return response

        route = request.scope.get("route")
        route_template = getattr(route, "path", None)
        if not isinstance(route_template, str):
            route_template = ""
        public_policy = PUBLIC_CACHE_POLICIES.get((request.method, route_template))
        if public_policy is None:
            response.headers["Cache-Control"] = PRIVATE_NO_STORE
            return response

        response.headers["Cache-Control"] = public_policy
        self._merge_vary(response)

        return response


def setup_session_middleware(app):
    """
    Configure session middleware for state management in OAuth flows.

    Args:
        app: FastAPI application instance
    """
    # Add session middleware for OAuth state tracking
    # Use a secure secret key from settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET,
        session_cookie="tc_oauth_state",
        max_age=600,  # 10 minutes - only for OAuth flow
        same_site="lax",
        https_only=settings.ENVIRONMENT == "production",
    )


def setup_security_middleware(app):
    """
    Configure all security middleware for the application.

    Args:
        app: FastAPI application instance
    """
    # Add compression middleware
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

    # Add security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Add rate limiting (optional, can be disabled for development)
    if settings.ENABLE_RATE_LIMITING:
        app.add_middleware(RateLimitMiddleware)

    # Setup session middleware for OAuth
    setup_session_middleware(app)

    # Establish a pseudonymous analytics identity independently from login
    # sessions. This middleware never exposes or persists the login token.
    app.add_middleware(AnalyticsIdentityMiddleware)

    logger.info(
        "Security middleware configured",
        extra={
            "rate_limiting": settings.ENABLE_RATE_LIMITING,
            "environment": settings.ENVIRONMENT,
            "compression": True,
            "cache_control": True,
        },
    )
