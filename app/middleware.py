"""Security middleware for headers, rate limiting, and request validation."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .logging_config import get_logger
from .settings import settings

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS protection (legacy but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Enforce HTTPS (only in production)
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        # Adjust based on your frontend needs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Adjust for production
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Remove server identification
        if "server" in response.headers:
            del response.headers["server"]
        
        # Permissions Policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting middleware.
    
    For production, consider using Redis-backed rate limiting with slowapi.
    This is a basic implementation for demonstration.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self._request_counts = {}  # Simple in-memory store
        self._last_cleanup = None
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Get client identifier (IP or user ID)
        client_id = self._get_client_id(request)
        
        # Check rate limit
        if self._is_rate_limited(client_id, request):
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_id": client_id,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                },
                headers={"Retry-After": "60"}
            )
        
        # Record request
        self._record_request(client_id)
        
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from session
        # For now, use IP address
        if request.client:
            return request.client.host
        return "unknown"
    
    def _is_rate_limited(self, client_id: str, request: Request) -> bool:
        """Check if client has exceeded rate limit."""
        # Simple implementation: allow 100 requests per minute
        # In production, use Redis with sliding window
        
        import time
        current_minute = int(time.time() / 60)
        key = f"{client_id}:{current_minute}"
        
        count = self._request_counts.get(key, 0)
        return count >= 100
    
    def _record_request(self, client_id: str):
        """Record a request for rate limiting."""
        import time
        current_minute = int(time.time() / 60)
        key = f"{client_id}:{current_minute}"
        
        self._request_counts[key] = self._request_counts.get(key, 0) + 1
        
        # Cleanup old entries periodically
        self._cleanup_old_entries()
    
    def _cleanup_old_entries(self):
        """Remove old rate limit entries to prevent memory leak."""
        import time
        current_minute = int(time.time() / 60)
        
        # Only cleanup once per minute
        if self._last_cleanup == current_minute:
            return
        
        self._last_cleanup = current_minute
        
        # Remove entries older than 2 minutes
        keys_to_delete = []
        for key in self._request_counts:
            try:
                key_minute = int(key.split(":")[-1])
                if current_minute - key_minute > 2:
                    keys_to_delete.append(key)
            except (ValueError, IndexError):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._request_counts[key]


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
    # Add security headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Add rate limiting (optional, can be disabled for development)
    if settings.ENABLE_RATE_LIMITING:
        app.add_middleware(RateLimitMiddleware)
    
    # Setup session middleware for OAuth
    setup_session_middleware(app)
    
    logger.info("Security middleware configured", extra={
        "rate_limiting": settings.ENABLE_RATE_LIMITING,
        "environment": settings.ENVIRONMENT,
    })
