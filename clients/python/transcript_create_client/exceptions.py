"""Custom exceptions for the Transcript Create client."""

from typing import Any, Dict, Optional


class APIError(Exception):
    """Base exception for all API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize API error.

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: API error code
            details: Additional error details
        """
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of error."""
        parts = [self.message]
        if self.status_code:
            parts.append(f"(status: {self.status_code})")
        if self.error_code:
            parts.append(f"(code: {self.error_code})")
        return " ".join(parts)


class AuthenticationError(APIError):
    """Authentication failed."""

    pass


class InvalidAPIKeyError(AuthenticationError):
    """Invalid or missing API key."""

    pass


class NotFoundError(APIError):
    """Resource not found."""

    pass


class TranscriptNotFoundError(NotFoundError):
    """Transcript not found for the specified video."""

    pass


class ValidationError(APIError):
    """Request validation failed."""

    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Seconds to wait before retrying
            status_code: HTTP status code
            error_code: API error code
            details: Additional error details
        """
        super().__init__(message, status_code, error_code, details)
        self.retry_after = retry_after


class QuotaExceededError(APIError):
    """API quota exceeded."""

    pass


class ServerError(APIError):
    """Server error (5xx)."""

    pass


class NetworkError(APIError):
    """Network connection error."""

    pass


class TimeoutError(APIError):
    """Request timeout."""

    pass
