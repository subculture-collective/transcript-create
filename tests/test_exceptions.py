"""Tests for custom exceptions."""

from app.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    DatabaseError,
    DuplicateJobError,
    ExternalServiceError,
    InvalidURLError,
    JobNotFoundError,
    QuotaExceededError,
    RateLimitError,
    TranscriptNotReadyError,
    ValidationError,
    VideoNotFoundError,
)


class TestAppError:
    """Tests for base AppError."""

    def test_app_error_basic(self):
        """Test basic AppError initialization."""
        error = AppError("test_error", "Test message", 400)
        assert error.error_code == "test_error"
        assert error.message == "Test message"
        assert error.status_code == 400
        assert error.details == {}

    def test_app_error_with_details(self):
        """Test AppError with details."""
        details = {"key": "value", "number": 42}
        error = AppError("test_error", "Test message", 400, details)
        assert error.details == details

    def test_app_error_to_dict(self):
        """Test AppError to_dict method."""
        error = AppError("test_error", "Test message", 400, {"key": "value"})
        result = error.to_dict()
        assert result == {
            "error": "test_error",
            "message": "Test message",
            "details": {"key": "value"},
        }

    def test_app_error_to_dict_no_details(self):
        """Test AppError to_dict without details."""
        error = AppError("test_error", "Test message", 400)
        result = error.to_dict()
        assert result == {
            "error": "test_error",
            "message": "Test message",
        }


class TestJobNotFoundError:
    """Tests for JobNotFoundError."""

    def test_job_not_found_error(self):
        """Test JobNotFoundError initialization."""
        error = JobNotFoundError("abc123")
        assert error.error_code == "job_not_found"
        assert "abc123" in error.message
        assert error.status_code == 404
        assert error.details["job_id"] == "abc123"


class TestVideoNotFoundError:
    """Tests for VideoNotFoundError."""

    def test_video_not_found_error(self):
        """Test VideoNotFoundError initialization."""
        error = VideoNotFoundError("vid456")
        assert error.error_code == "video_not_found"
        assert "vid456" in error.message
        assert error.status_code == 404
        assert error.details["video_id"] == "vid456"


class TestInvalidURLError:
    """Tests for InvalidURLError."""

    def test_invalid_url_error_basic(self):
        """Test InvalidURLError without reason."""
        error = InvalidURLError("http://example.com")
        assert error.error_code == "invalid_url"
        assert "http://example.com" in error.message
        assert error.status_code == 400
        assert error.details["url"] == "http://example.com"

    def test_invalid_url_error_with_reason(self):
        """Test InvalidURLError with reason."""
        error = InvalidURLError("http://example.com", "Not a YouTube URL")
        assert "Not a YouTube URL" in error.message
        assert error.details["reason"] == "Not a YouTube URL"


class TestQuotaExceededError:
    """Tests for QuotaExceededError."""

    def test_quota_exceeded_error(self):
        """Test QuotaExceededError initialization."""
        error = QuotaExceededError("searches", 5, 5, "free")
        assert error.error_code == "quota_exceeded"
        assert "searches" in error.message
        assert error.status_code == 402
        assert error.details["resource"] == "searches"
        assert error.details["limit"] == 5
        assert error.details["used"] == 5
        assert error.details["plan"] == "free"


class TestTranscriptNotReadyError:
    """Tests for TranscriptNotReadyError."""

    def test_transcript_not_ready_error(self):
        """Test TranscriptNotReadyError initialization."""
        error = TranscriptNotReadyError("vid789", "processing")
        assert error.error_code == "transcript_not_ready"
        assert "vid789" in error.message
        assert "processing" in error.message
        assert error.status_code == 409
        assert error.details["video_id"] == "vid789"
        assert error.details["state"] == "processing"


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_database_error_default(self):
        """Test DatabaseError with default message."""
        error = DatabaseError()
        assert error.error_code == "database_error"
        assert error.message == "Database operation failed"
        assert error.status_code == 500

    def test_database_error_custom_message(self):
        """Test DatabaseError with custom message."""
        error = DatabaseError("Connection timeout")
        assert error.message == "Connection timeout"


class TestExternalServiceError:
    """Tests for ExternalServiceError."""

    def test_external_service_error(self):
        """Test ExternalServiceError initialization."""
        error = ExternalServiceError("Stripe", "API key invalid")
        assert error.error_code == "external_service_error"
        assert "Stripe" in error.message
        assert "API key invalid" in error.message
        assert error.status_code == 503
        assert error.details["service"] == "Stripe"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_authentication_error_default(self):
        """Test AuthenticationError with default message."""
        error = AuthenticationError()
        assert error.error_code == "authentication_required"
        assert error.message == "Authentication required"
        assert error.status_code == 401

    def test_authentication_error_custom_message(self):
        """Test AuthenticationError with custom message."""
        error = AuthenticationError("Session expired")
        assert error.message == "Session expired"


class TestAuthorizationError:
    """Tests for AuthorizationError."""

    def test_authorization_error_default(self):
        """Test AuthorizationError with default message."""
        error = AuthorizationError()
        assert error.error_code == "insufficient_permissions"
        assert error.message == "Insufficient permissions"
        assert error.status_code == 403

    def test_authorization_error_custom_message(self):
        """Test AuthorizationError with custom message."""
        error = AuthorizationError("Admin access required")
        assert error.message == "Admin access required"


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_basic(self):
        """Test ValidationError without field."""
        error = ValidationError("Invalid input")
        assert error.error_code == "validation_error"
        assert error.message == "Invalid input"
        assert error.status_code == 422

    def test_validation_error_with_field(self):
        """Test ValidationError with field."""
        error = ValidationError("Must be a positive number", field="limit")
        assert error.message == "Must be a positive number"
        assert error.details["field"] == "limit"


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_rate_limit_error_default(self):
        """Test RateLimitError with default message."""
        error = RateLimitError()
        assert error.error_code == "rate_limit_exceeded"
        assert "Too many requests" in error.message
        assert error.status_code == 429

    def test_rate_limit_error_with_retry_after(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert error.details["retry_after"] == 60


class TestDuplicateJobError:
    """Tests for DuplicateJobError."""

    def test_duplicate_job_error_basic(self):
        """Test DuplicateJobError without existing_job_id."""
        error = DuplicateJobError("https://youtube.com/watch?v=test")
        assert error.error_code == "duplicate_job"
        assert "https://youtube.com/watch?v=test" in error.message
        assert error.status_code == 409
        assert error.details["url"] == "https://youtube.com/watch?v=test"

    def test_duplicate_job_error_with_existing_job(self):
        """Test DuplicateJobError with existing_job_id."""
        error = DuplicateJobError("https://youtube.com/watch?v=test", existing_job_id="job123")
        assert error.details["existing_job_id"] == "job123"
