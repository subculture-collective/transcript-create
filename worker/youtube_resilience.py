"""YouTube request resilience: retry with exponential backoff, jitter, and circuit breaker.

This module provides utilities to handle YouTube's aggressive throttling:
- Exponential backoff with jitter for retry delays
- Error classification (network, auth, throttle, token, not found)
- Circuit breaker to prevent hot loops during outages
- Configurable retry wrapper for yt-dlp operations
"""

import random
import time
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Callable, Optional, TypeVar

from app.logging_config import get_logger
from app.settings import settings

logger = get_logger(__name__)

# Import metrics at module level, but handle gracefully if not available
try:
    from worker.metrics import youtube_circuit_breaker_state, youtube_circuit_breaker_transitions_total

    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

T = TypeVar("T")


class ErrorClass(Enum):
    """Classification of YouTube/yt-dlp errors."""

    NETWORK = "network"  # Network connectivity issues
    THROTTLE = "throttle"  # Rate limiting / 429 errors
    AUTH = "auth"  # Authentication required / 403 errors
    TOKEN = "token"  # PO token issues (invalid/expired)
    NOT_FOUND = "not_found"  # Video unavailable / 404
    TIMEOUT = "timeout"  # Request timeout
    UNKNOWN = "unknown"  # Unclassified error


def classify_error(returncode: int, stderr: str = "", exception: Optional[Exception] = None) -> ErrorClass:
    """Classify error from yt-dlp or YouTube request.

    Args:
        returncode: Process return code (0 = success)
        stderr: Error output from yt-dlp
        exception: Optional exception that was raised

    Returns:
        ErrorClass enum value
    """
    stderr_lower = stderr.lower() if stderr else ""

    # Check exception type first
    if exception:
        exc_name = type(exception).__name__.lower()
        if "timeout" in exc_name:
            return ErrorClass.TIMEOUT
        if "connection" in exc_name or "network" in exc_name:
            return ErrorClass.NETWORK

    # Token-related errors
    if "po_token" in stderr_lower and ("invalid" in stderr_lower or "expired" in stderr_lower):
        return ErrorClass.TOKEN
    if "token" in stderr_lower and ("expired" in stderr_lower or "invalid" in stderr_lower):
        return ErrorClass.TOKEN

    # Throttling errors
    if "429" in stderr_lower or "too many requests" in stderr_lower:
        return ErrorClass.THROTTLE
    if "throttl" in stderr_lower:
        return ErrorClass.THROTTLE

    # Authentication / authorization errors
    if "403" in stderr_lower or "forbidden" in stderr_lower:
        return ErrorClass.AUTH
    if "sign in" in stderr_lower or "bot" in stderr_lower:
        return ErrorClass.AUTH

    # Not found / unavailable
    if "404" in stderr_lower or "not found" in stderr_lower:
        return ErrorClass.NOT_FOUND
    if "unavailable" in stderr_lower or "private" in stderr_lower:
        return ErrorClass.NOT_FOUND

    # Network errors
    if "network" in stderr_lower or "connection" in stderr_lower:
        return ErrorClass.NETWORK
    if "timeout" in stderr_lower or "timed out" in stderr_lower:
        return ErrorClass.TIMEOUT

    return ErrorClass.UNKNOWN


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    random_seed: Optional[int] = None,
) -> float:
    """Calculate delay for exponential backoff with optional jitter.

    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Whether to add random jitter (recommended)
        random_seed: Optional seed for deterministic jitter (testing only)

    Returns:
        Delay in seconds
    """
    # Calculate exponential delay: base_delay * 2^attempt
    delay = min(base_delay * (2**attempt), max_delay)

    if jitter:
        # Add full jitter: random value between 0 and delay
        if random_seed is not None:
            # Use seeded random for tests
            rng = random.Random(random_seed + attempt)
            delay = rng.uniform(0, delay)
        else:
            delay = random.uniform(0, delay)

    return delay


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker state."""

    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changed_at: float = 0.0


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests after failures
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent hot loops during YouTube outages.

    Tracks failures and opens circuit after threshold is reached.
    After cooldown period, enters half-open state to test recovery.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        success_threshold: int = 2,
        name: str = "youtube",
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening
            cooldown_seconds: Time to wait before testing recovery
            success_threshold: Successes in half-open to close circuit
            name: Identifier for logging
        """
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitBreakerState.CLOSED
        self._stats = CircuitBreakerStats(state_changed_at=time.time())
        self._lock = Lock()

        logger.info(
            f"Circuit breaker '{name}' initialized",
            extra={
                "failure_threshold": failure_threshold,
                "cooldown_seconds": cooldown_seconds,
                "success_threshold": success_threshold,
            },
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit state."""
        with self._lock:
            return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        with self._lock:
            return CircuitBreakerStats(
                failure_count=self._stats.failure_count,
                success_count=self._stats.success_count,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
                state_changed_at=self._stats.state_changed_at,
            )

    def is_retriable_error(self, error_class: ErrorClass) -> bool:
        """Determine if error should count towards circuit breaker.

        Args:
            error_class: Classified error type

        Returns:
            True if error should trigger circuit breaker logic
        """
        # Don't count NOT_FOUND errors (video unavailable is not a service issue)
        # Don't count TOKEN errors (token manager handles these separately)
        return error_class not in (ErrorClass.NOT_FOUND, ErrorClass.TOKEN)

    def call(self, func: Callable[[], T], error_class: Optional[ErrorClass] = None) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Function to execute
            error_class: Optional pre-classified error for failure recording

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails
        """
        with self._lock:
            current_state = self._state

            # Check if circuit is open
            if current_state == CircuitBreakerState.OPEN:
                time_since_open = time.time() - self._stats.state_changed_at
                if time_since_open >= self.cooldown_seconds:
                    # Transition to half-open
                    self._transition_to(CircuitBreakerState.HALF_OPEN)
                    logger.info(
                        f"Circuit breaker '{self.name}' entering half-open state",
                        extra={"cooldown_elapsed": round(time_since_open, 2)},
                    )
                else:
                    # Circuit still open
                    raise RuntimeError(
                        f"Circuit breaker '{self.name}' is open. "
                        f"Cooldown remaining: {self.cooldown_seconds - time_since_open:.1f}s"
                    )

        # Execute function
        try:
            result = func()
            self._record_success()
            return result
        except Exception as e:
            # Use provided error_class or classify from exception
            err_class = error_class or classify_error(0, str(e), e)
            self._record_failure(err_class)
            raise

    def _record_success(self):
        """Record successful operation."""
        with self._lock:
            now = time.time()
            self._stats.last_success_time = now
            self._stats.success_count += 1

            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._stats.success_count >= self.success_threshold:
                    self._transition_to(CircuitBreakerState.CLOSED)
                    logger.info(
                        f"Circuit breaker '{self.name}' closed after recovery",
                        extra={"success_count": self._stats.success_count},
                    )

    def _record_failure(self, error_class: ErrorClass):
        """Record failed operation.

        Args:
            error_class: Classification of the error
        """
        if not self.is_retriable_error(error_class):
            logger.debug(
                f"Circuit breaker '{self.name}' ignoring non-retriable error",
                extra={"error_class": error_class.value},
            )
            return

        with self._lock:
            now = time.time()
            self._stats.last_failure_time = now
            self._stats.failure_count += 1

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open immediately reopens circuit
                self._transition_to(CircuitBreakerState.OPEN)
                logger.warning(
                    f"Circuit breaker '{self.name}' reopened after half-open failure",
                    extra={"error_class": error_class.value},
                )
            elif self._state == CircuitBreakerState.CLOSED:
                if self._stats.failure_count >= self.failure_threshold:
                    self._transition_to(CircuitBreakerState.OPEN)
                    logger.error(
                        f"Circuit breaker '{self.name}' opened after threshold reached",
                        extra={
                            "failure_count": self._stats.failure_count,
                            "threshold": self.failure_threshold,
                        },
                    )

    def _transition_to(self, new_state: CircuitBreakerState):
        """Transition to new state.

        Args:
            new_state: Target state
        """
        old_state = self._state
        self._state = new_state
        self._stats.state_changed_at = time.time()

        # Reset counters on state transition
        if new_state == CircuitBreakerState.CLOSED:
            self._stats.failure_count = 0
            self._stats.success_count = 0
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self._stats.success_count = 0

        # Update Prometheus metrics if available
        if _METRICS_AVAILABLE:
            # Map state to numeric value for gauge
            state_values = {
                CircuitBreakerState.CLOSED: 0,
                CircuitBreakerState.HALF_OPEN: 1,
                CircuitBreakerState.OPEN: 2,
            }
            youtube_circuit_breaker_state.labels(name=self.name).set(state_values[new_state])
            youtube_circuit_breaker_transitions_total.labels(
                name=self.name, from_state=old_state.value, to_state=new_state.value
            ).inc()

        logger.info(
            f"Circuit breaker '{self.name}' transitioned",
            extra={"from": old_state.value, "to": new_state.value},
        )

    def reset(self):
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._stats = CircuitBreakerStats(state_changed_at=time.time())
            logger.info(f"Circuit breaker '{self.name}' manually reset")


# Global circuit breaker instances
_circuit_breakers: dict[str, CircuitBreaker] = {}
_breaker_lock = Lock()


def get_circuit_breaker(name: str = "youtube") -> CircuitBreaker:
    """Get or create circuit breaker instance.

    Args:
        name: Circuit breaker identifier

    Returns:
        CircuitBreaker instance
    """
    with _breaker_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(
                failure_threshold=settings.YTDLP_CIRCUIT_BREAKER_THRESHOLD,
                cooldown_seconds=settings.YTDLP_CIRCUIT_BREAKER_COOLDOWN,
                success_threshold=settings.YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                name=name,
            )
        return _circuit_breakers[name]


def retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout_per_attempt: Optional[float] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    classify_func: Optional[Callable[[Exception], ErrorClass]] = None,
) -> T:
    """Retry function with exponential backoff and optional circuit breaker.

    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        base_delay: Initial backoff delay in seconds
        max_delay: Maximum backoff delay in seconds
        timeout_per_attempt: Optional timeout for each attempt
        circuit_breaker: Optional circuit breaker to use
        classify_func: Optional function to classify exceptions

    Returns:
        Function result

    Raises:
        Last exception if all attempts fail
    """
    last_exception: Optional[Exception] = None
    last_error_class: ErrorClass

    for attempt in range(max_attempts):
        try:
            if circuit_breaker:
                # Use circuit breaker for execution
                # Let circuit breaker classify errors internally for consistency
                return circuit_breaker.call(func)
            else:
                # Direct execution without circuit breaker
                return func()

        except Exception as e:
            last_exception = e

            # Classify error
            if classify_func:
                last_error_class = classify_func(e)
            else:
                stderr = str(e)
                last_error_class = classify_error(getattr(e, "returncode", 0), stderr, e)

            # Log failure
            logger.warning(
                "Retry attempt failed",
                extra={
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                    "error_class": last_error_class.value,
                    "error": str(e)[:200],
                },
            )

            # Don't retry certain error types
            if last_error_class == ErrorClass.NOT_FOUND:
                logger.info("Not retrying NOT_FOUND error")
                raise

            # Check if we have more attempts
            if attempt < max_attempts - 1:
                delay = exponential_backoff(attempt, base_delay, max_delay)
                logger.info(
                    "Backing off before retry",
                    extra={
                        "delay_seconds": round(delay, 2),
                        "next_attempt": attempt + 2,
                    },
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All retry attempts exhausted",
                    extra={
                        "attempts": max_attempts,
                        "last_error_class": last_error_class.value,
                    },
                )

    # All attempts failed
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic failed with no captured exception")
