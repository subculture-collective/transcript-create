"""Tests for structured logging configuration."""

import json
import logging
from io import StringIO

import pytest

from app.logging_config import (
    JSONFormatter,
    SensitiveDataFilter,
    configure_logging,
    get_logger,
    job_id_ctx,
    request_id_ctx,
    user_id_ctx,
    video_id_ctx,
)


class TestSensitiveDataFilter:
    """Test sensitive data filtering."""

    def test_mask_email(self):
        """Test email masking."""
        assert SensitiveDataFilter.mask_email("john@example.com") == "jo***@example.com"
        assert SensitiveDataFilter.mask_email("a@test.org") == "**@test.org"
        assert SensitiveDataFilter.mask_email("invalid-email") == "invalid-email"

    def test_sanitize_passwords(self):
        """Test password redaction."""
        message = 'user login with password="secret123"'
        sanitized = SensitiveDataFilter.sanitize(message)
        assert "secret123" not in sanitized
        assert "password=***" in sanitized

    def test_sanitize_tokens(self):
        """Test token redaction."""
        message = "Authorization token=abc123def456"
        sanitized = SensitiveDataFilter.sanitize(message)
        assert "abc123def456" not in sanitized
        assert "token=***" in sanitized

    def test_sanitize_api_keys(self):
        """Test API key redaction."""
        message = "Using api_key=sk_live_12345"
        sanitized = SensitiveDataFilter.sanitize(message)
        assert "sk_live_12345" not in sanitized
        assert "api_key=***" in sanitized

    def test_sanitize_cookies(self):
        """Test cookie redaction."""
        message = "cookie: session_id=abcd1234"
        sanitized = SensitiveDataFilter.sanitize(message)
        # Cookie values are redacted but cookie header remains
        assert "abcd1234" not in sanitized
        assert "cookie: ***" in sanitized

    def test_sanitize_credit_cards(self):
        """Test credit card number redaction."""
        message = "Payment with card 4532-1234-5678-9010"
        sanitized = SensitiveDataFilter.sanitize(message)
        assert "4532" not in sanitized
        assert "****-****-****-****" in sanitized


class TestJSONFormatter:
    """Test JSON log formatting."""

    def test_basic_formatting(self):
        """Test basic log record formatting."""
        formatter = JSONFormatter(service="test")
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["service"] == "test"
        assert data["message"] == "Test message"
        assert data["logger"] == "test_logger"
        assert "timestamp" in data

    def test_context_vars(self):
        """Test context variable inclusion."""
        formatter = JSONFormatter(service="test")
        
        # Set context
        request_id_ctx.set("req-123")
        user_id_ctx.set("user-456")
        job_id_ctx.set("job-789")
        video_id_ctx.set("video-012")

        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test.py",
            lineno=10,
            msg="Test with context",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["request_id"] == "req-123"
        assert data["user_id"] == "user-456"
        assert data["job_id"] == "job-789"
        assert data["video_id"] == "video-012"

        # Clean up context
        request_id_ctx.set(None)
        user_id_ctx.set(None)
        job_id_ctx.set(None)
        video_id_ctx.set(None)

    def test_exception_info(self):
        """Test exception info formatting."""
        formatter = JSONFormatter(service="test")
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert data["exc_type"] == "ValueError"

    def test_sensitive_data_redaction(self):
        """Test that sensitive data is redacted in logs."""
        formatter = JSONFormatter(service="test")
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test.py",
            lineno=10,
            msg='Login with password="secret" and token=abc123',
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        assert "secret" not in data["message"]
        assert "abc123" not in data["message"]
        assert "password=***" in data["message"]
        assert "token=***" in data["message"]


class TestStructuredLogger:
    """Test structured logger adapter."""

    def test_logger_with_context(self):
        """Test that logger includes context variables."""
        # Configure logging for test
        configure_logging(service="test", level="INFO", json_format=True)
        logger = get_logger("test_module")

        # Set context
        request_id_ctx.set("test-request-123")

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter(service="test"))
        logging.root.handlers = [handler]

        logger.info("Test message")

        # Parse output
        stream.seek(0)
        output = stream.read()
        data = json.loads(output)

        assert data["message"] == "Test message"
        assert data["request_id"] == "test-request-123"

        # Clean up
        request_id_ctx.set(None)

    def test_extra_fields(self):
        """Test that extra fields are included."""
        configure_logging(service="test", level="INFO", json_format=True)
        logger = get_logger("test_module")

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter(service="test"))
        logging.root.handlers = [handler]

        logger.info("Test message", extra={"custom_field": "custom_value", "count": 42})

        stream.seek(0)
        output = stream.read()
        data = json.loads(output)

        assert "extra" in data
        assert data["extra"]["custom_field"] == "custom_value"
        assert data["extra"]["count"] == 42


def test_configure_logging():
    """Test logging configuration."""
    # Test JSON format
    configure_logging(service="test", level="DEBUG", json_format=True)
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
    assert len(root_logger.handlers) > 0
    
    # Test plain text format
    configure_logging(service="test2", level="INFO", json_format=False)
    assert root_logger.level == logging.INFO


def test_get_logger():
    """Test logger factory."""
    logger = get_logger("test_module")
    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "debug")
