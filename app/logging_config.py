"""Structured logging configuration for transcript-create.

This module provides JSON-based structured logging with:
- Request ID tracking for API calls
- User ID tracking for authenticated requests
- Job/video context for worker operations
- Sensitive data protection
- Configurable log levels
- Support for centralized log aggregation
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variables for request/worker tracking
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
job_id_ctx: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
video_id_ctx: ContextVar[Optional[str]] = ContextVar("video_id", default=None)


class SensitiveDataFilter:
    """Filter to prevent sensitive data from being logged."""

    # Patterns to redact
    PATTERNS = [
        (re.compile(r"password[\"']?\s*[:=]\s*[\"']?([^\"'\s,}]+)", re.IGNORECASE), "password=***"),
        (re.compile(r"token[\"']?\s*[:=]\s*[\"']?([^\"'\s,}]+)", re.IGNORECASE), "token=***"),
        (re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?([^\"'\s,}]+)", re.IGNORECASE), "api_key=***"),
        (re.compile(r"secret[\"']?\s*[:=]\s*[\"']?([^\"'\s,}]+)", re.IGNORECASE), "secret=***"),
        (re.compile(r"authorization:\s*bearer\s+([^\s]+)", re.IGNORECASE), "authorization: bearer ***"),
        (re.compile(r"cookie:\s*([^\r\n]+)", re.IGNORECASE), "cookie: ***"),
        # Credit card patterns (basic)
        (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "****-****-****-****"),
    ]

    @classmethod
    def mask_email(cls, email: str) -> str:
        """Mask email address (show first 2 chars + domain)."""
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            return f"**@{domain}"
        return f"{local[:2]}***@{domain}"

    @classmethod
    def sanitize(cls, message: str) -> str:
        """Remove sensitive data from log messages."""
        for pattern, replacement in cls.PATTERNS:
            message = pattern.sub(replacement, message)
        return message


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, service: str = "api", include_extra: bool = True):
        super().__init__()
        self.service = service
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Build base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": SensitiveDataFilter.sanitize(record.getMessage()),
        }

        # Add context from contextvars
        request_id = request_id_ctx.get()
        if request_id:
            log_entry["request_id"] = request_id

        user_id = user_id_ctx.get()
        if user_id:
            log_entry["user_id"] = user_id

        job_id = job_id_ctx.get()
        if job_id:
            log_entry["job_id"] = job_id

        video_id = video_id_ctx.get()
        if video_id:
            log_entry["video_id"] = video_id

        # Add extra fields from record
        if self.include_extra:
            extra = {}
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "taskName",
                ]:
                    extra[key] = value
            if extra:
                log_entry["extra"] = extra

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            log_entry["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None

        # Add file location for non-INFO logs
        if record.levelno != logging.INFO:
            log_entry["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_entry, default=str)


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that adds context to log messages."""

    def process(self, msg: Any, kwargs: Any) -> tuple:
        """Add context fields to log records."""
        # Get current context
        extra = kwargs.get("extra", {})

        # Add context vars if not already present
        if "request_id" not in extra:
            request_id = request_id_ctx.get()
            if request_id:
                extra["request_id"] = request_id

        if "user_id" not in extra:
            user_id = user_id_ctx.get()
            if user_id:
                extra["user_id"] = user_id

        if "job_id" not in extra:
            job_id = job_id_ctx.get()
            if job_id:
                extra["job_id"] = job_id

        if "video_id" not in extra:
            video_id = video_id_ctx.get()
            if video_id:
                extra["video_id"] = video_id

        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(
    service: str = "api",
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure logging for the service.

    Args:
        service: Service name ("api", "worker", "script")
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON formatting (True) or plain text (False)
    """
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler()

    if json_format:
        formatter = JSONFormatter(service=service)
    else:
        # Fallback to plain text format
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(service)s] %(name)s - %(message)s",
            defaults={"service": service},
        )

    handler.setFormatter(formatter)

    # Configure root logger
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Set third-party loggers to WARNING to reduce noise
    for logger_name in ["urllib3", "asyncio", "multipart", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance with context support
    """
    logger = logging.getLogger(name)
    return StructuredLogger(logger, {})
