"""Tests for exception classes."""

from transcript_create_client.exceptions import (
    APIError,
    AuthenticationError,
    InvalidAPIKeyError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    TranscriptNotFoundError,
    ValidationError,
)


class TestAPIError:
    """Tests for APIError base class."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = APIError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.status_code is None
        assert error.error_code is None

    def test_error_with_details(self) -> None:
        """Test error with all details."""
        error = APIError(
            "Test error",
            status_code=400,
            error_code="test_error",
            details={"field": "value"},
        )
        assert "Test error" in str(error)
        assert "400" in str(error)
        assert "test_error" in str(error)
        assert error.details == {"field": "value"}


class TestSpecificErrors:
    """Tests for specific error types."""

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError("Auth failed", status_code=401)
        assert isinstance(error, APIError)
        assert error.status_code == 401

    def test_invalid_api_key_error(self) -> None:
        """Test InvalidAPIKeyError."""
        error = InvalidAPIKeyError("Invalid key")
        assert isinstance(error, AuthenticationError)
        assert isinstance(error, APIError)

    def test_not_found_error(self) -> None:
        """Test NotFoundError."""
        error = NotFoundError("Resource not found", status_code=404)
        assert isinstance(error, APIError)
        assert error.status_code == 404

    def test_transcript_not_found_error(self) -> None:
        """Test TranscriptNotFoundError."""
        error = TranscriptNotFoundError("Transcript not found")
        assert isinstance(error, NotFoundError)
        assert isinstance(error, APIError)

    def test_validation_error(self) -> None:
        """Test ValidationError."""
        error = ValidationError(
            "Validation failed",
            status_code=422,
            details={"errors": [{"field": "url", "message": "Invalid"}]},
        )
        assert isinstance(error, APIError)
        assert error.status_code == 422
        assert "errors" in error.details

    def test_quota_exceeded_error(self) -> None:
        """Test QuotaExceededError."""
        error = QuotaExceededError("Quota exceeded", status_code=402)
        assert isinstance(error, APIError)
        assert error.status_code == 402


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_without_retry_after(self) -> None:
        """Test rate limit error without retry_after."""
        error = RateLimitError("Rate limit exceeded", status_code=429)
        assert isinstance(error, APIError)
        assert error.status_code == 429
        assert error.retry_after is None

    def test_rate_limit_with_retry_after(self) -> None:
        """Test rate limit error with retry_after."""
        error = RateLimitError("Rate limit exceeded", retry_after=60, status_code=429)
        assert error.retry_after == 60
        assert error.status_code == 429
