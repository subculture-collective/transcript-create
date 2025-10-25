"""Custom exceptions for the transcript-create application."""

from typing import Any, Dict, Optional


class AppError(Exception):
    """Base exception for all application errors.

    Provides a consistent error format:
    {
        "error": "error_code",
        "message": "Human-readable message",
        "details": {...}
    }
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        result = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class JobNotFoundError(AppError):
    """Raised when a job cannot be found."""

    def __init__(self, job_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="job_not_found",
            message=f"Job {job_id} not found",
            status_code=404,
            details=details or {"job_id": job_id},
        )


class VideoNotFoundError(AppError):
    """Raised when a video cannot be found."""

    def __init__(self, video_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="video_not_found",
            message=f"Video {video_id} not found",
            status_code=404,
            details=details or {"video_id": video_id},
        )


class InvalidURLError(AppError):
    """Raised when a URL is invalid or not supported."""

    def __init__(self, url: str, reason: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        message = f"Invalid URL: {url}"
        if reason:
            message += f" - {reason}"
        default_details = {"url": url}
        if reason is not None:
            default_details["reason"] = reason
        super().__init__(
            error_code="invalid_url",
            message=message,
            status_code=400,
            details=details or default_details,
        )


class QuotaExceededError(AppError):
    """Raised when a user exceeds their quota."""

    def __init__(
        self,
        resource: str,
        limit: int,
        used: int,
        plan: str = "free",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_code="quota_exceeded",
            message=f"Daily {resource} limit reached. Upgrade to Pro for unlimited {resource}.",
            status_code=402,
            details=details
            or {
                "resource": resource,
                "limit": limit,
                "used": used,
                "plan": plan,
            },
        )


class TranscriptNotReadyError(AppError):
    """Raised when a transcript is requested but not ready."""

    def __init__(self, video_id: str, state: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="transcript_not_ready",
            message=f"Transcript for video {video_id} is not ready (current state: {state})",
            status_code=409,
            details=details or {"video_id": video_id, "state": state},
        )


class DatabaseError(AppError):
    """Raised when a database operation fails."""

    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="database_error",
            message=message,
            status_code=500,
            details=details,
        )


class ExternalServiceError(AppError):
    """Raised when an external service fails."""

    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="external_service_error",
            message=f"{service} error: {message}",
            status_code=503,
            details=details or {"service": service},
        )


class AuthenticationError(AppError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="authentication_required",
            message=message,
            status_code=401,
            details=details,
        )


class AuthorizationError(AppError):
    """Raised when user lacks permission."""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code="insufficient_permissions",
            message=message,
            status_code=403,
            details=details,
        )


class ValidationError(AppError):
    """Raised when validation fails."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(
            error_code="validation_error",
            message=message,
            status_code=422,
            details=error_details,
        )


class RateLimitError(AppError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        if retry_after:
            error_details["retry_after"] = retry_after
        super().__init__(
            error_code="rate_limit_exceeded",
            message=message,
            status_code=429,
            details=error_details,
        )


class DuplicateJobError(AppError):
    """Raised when attempting to create a duplicate job."""

    def __init__(self, url: str, existing_job_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {"url": url}
        if existing_job_id:
            error_details["existing_job_id"] = existing_job_id
        super().__init__(
            error_code="duplicate_job",
            message=f"A job for URL {url} already exists",
            status_code=409,
            details=error_details,
        )
