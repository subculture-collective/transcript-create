"""Retry logic with exponential backoff."""

import asyncio
import random
from typing import Any, Callable, Optional, Set, TypeVar

from httpx import HTTPStatusError, RequestError

from .exceptions import NetworkError, RateLimitError, ServerError, TimeoutError

T = TypeVar("T")


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_status_codes: Optional[Set[int]] = None,
    ) -> None:
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_status_codes: HTTP status codes that should trigger retry
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_status_codes = retryable_status_codes or {408, 429, 500, 502, 503, 504}

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = min(self.initial_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            # Add "equal jitter" (aka half jitter): random value between 50% and 100% of delay
            # See: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
            delay = delay * (0.5 + random.random() * 0.5)

        return delay

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """Determine if request should be retried.

        Args:
            attempt: Current attempt number (0-indexed)
            error: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_retries:
            return False

        # Always retry network errors and timeouts
        if isinstance(error, (NetworkError, TimeoutError)):
            return True

        # Retry rate limit errors
        if isinstance(error, RateLimitError):
            return True

        # Retry server errors (5xx)
        if isinstance(error, ServerError):
            return True

        # Check HTTP status codes
        if isinstance(error, HTTPStatusError):
            return error.response.status_code in self.retryable_status_codes

        # Don't retry other errors
        return False


async def retry_async(
    func: Callable[..., Any],
    config: Optional[RetryConfig] = None,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute async function with retry logic.

    Args:
        func: Async function to execute
        config: Retry configuration
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        Last exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()

    last_error: Optional[Exception] = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e

            if not config.should_retry(attempt, e):
                raise

            if attempt < config.max_retries:
                delay = config.calculate_delay(attempt)

                # For rate limit errors, use Retry-After header if available
                if isinstance(e, RateLimitError) and e.retry_after:
                    delay = max(delay, e.retry_after)

                await asyncio.sleep(delay)

    # Should never reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Retry logic failed unexpectedly")
