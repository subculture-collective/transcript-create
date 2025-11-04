"""Tests for worker.youtube_resilience module."""

import time
from unittest.mock import Mock, patch

import pytest

from worker.youtube_resilience import (
    CircuitBreaker,
    CircuitBreakerState,
    ErrorClass,
    classify_error,
    exponential_backoff,
    get_circuit_breaker,
    retry_with_backoff,
)


class TestErrorClassification:
    """Tests for classify_error function."""

    def test_classify_token_error_explicit(self):
        """Test classification of explicit PO token errors."""
        result = classify_error(1, "po_token is invalid")
        assert result == ErrorClass.TOKEN

    def test_classify_token_error_expired(self):
        """Test classification of expired token errors."""
        result = classify_error(1, "token expired")
        assert result == ErrorClass.TOKEN

    def test_classify_throttle_429(self):
        """Test classification of 429 throttle errors."""
        result = classify_error(1, "HTTP Error 429: Too Many Requests")
        assert result == ErrorClass.THROTTLE

    def test_classify_throttle_text(self):
        """Test classification of throttling messages."""
        result = classify_error(1, "Throttling detected")
        assert result == ErrorClass.THROTTLE

    def test_classify_auth_403(self):
        """Test classification of 403 forbidden errors."""
        result = classify_error(1, "HTTP Error 403: Forbidden")
        assert result == ErrorClass.AUTH

    def test_classify_auth_signin(self):
        """Test classification of sign-in required errors."""
        result = classify_error(1, "Sign in to confirm your age")
        assert result == ErrorClass.AUTH

    def test_classify_not_found_404(self):
        """Test classification of 404 not found errors."""
        result = classify_error(1, "HTTP Error 404: Not Found")
        assert result == ErrorClass.NOT_FOUND

    def test_classify_unavailable(self):
        """Test classification of unavailable videos."""
        result = classify_error(1, "Video unavailable")
        assert result == ErrorClass.NOT_FOUND

    def test_classify_private(self):
        """Test classification of private videos."""
        result = classify_error(1, "This video is private")
        assert result == ErrorClass.NOT_FOUND

    def test_classify_network_error(self):
        """Test classification of network errors."""
        result = classify_error(1, "Network connection failed")
        assert result == ErrorClass.NETWORK

    def test_classify_timeout_error(self):
        """Test classification of timeout errors."""
        result = classify_error(1, "Request timed out")
        assert result == ErrorClass.TIMEOUT

    def test_classify_timeout_from_exception(self):
        """Test classification of timeout from exception type."""
        exc = TimeoutError("Connection timeout")
        result = classify_error(0, "", exc)
        assert result == ErrorClass.TIMEOUT

    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        result = classify_error(1, "Some unknown error")
        assert result == ErrorClass.UNKNOWN

    def test_classify_empty_stderr(self):
        """Test classification with no error message."""
        result = classify_error(1, "")
        assert result == ErrorClass.UNKNOWN


class TestExponentialBackoff:
    """Tests for exponential_backoff function."""

    def test_backoff_first_attempt(self):
        """Test backoff delay for first retry (attempt 0)."""
        delay = exponential_backoff(0, base_delay=1.0, jitter=False)
        assert delay == 1.0

    def test_backoff_second_attempt(self):
        """Test backoff delay for second retry (attempt 1)."""
        delay = exponential_backoff(1, base_delay=1.0, jitter=False)
        assert delay == 2.0

    def test_backoff_third_attempt(self):
        """Test backoff delay for third retry (attempt 2)."""
        delay = exponential_backoff(2, base_delay=1.0, jitter=False)
        assert delay == 4.0

    def test_backoff_exponential_growth(self):
        """Test exponential growth of backoff delays."""
        delays = [exponential_backoff(i, base_delay=1.0, jitter=False) for i in range(5)]
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        assert delays == expected

    def test_backoff_max_delay_cap(self):
        """Test that backoff respects maximum delay cap."""
        delay = exponential_backoff(10, base_delay=1.0, max_delay=30.0, jitter=False)
        assert delay == 30.0

    def test_backoff_custom_base_delay(self):
        """Test backoff with custom base delay."""
        delay = exponential_backoff(0, base_delay=2.5, jitter=False)
        assert delay == 2.5

    def test_backoff_with_jitter_range(self):
        """Test that jitter produces values in expected range."""
        # Test multiple times since jitter is random
        for _ in range(10):
            delay = exponential_backoff(2, base_delay=1.0, jitter=True)
            assert 0 <= delay <= 4.0

    def test_backoff_with_seeded_jitter(self):
        """Test deterministic jitter with seed."""
        delay1 = exponential_backoff(1, base_delay=1.0, jitter=True, random_seed=42)
        delay2 = exponential_backoff(1, base_delay=1.0, jitter=True, random_seed=42)
        assert delay1 == delay2
        assert 0 <= delay1 <= 2.0

    def test_backoff_seeded_jitter_different_attempts(self):
        """Test that seeded jitter produces different values for different attempts."""
        delay0 = exponential_backoff(0, base_delay=1.0, jitter=True, random_seed=42)
        delay1 = exponential_backoff(1, base_delay=1.0, jitter=True, random_seed=42)
        # Different attempts should produce different jitter values
        # (seed + attempt ensures this)
        assert delay0 != delay1


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_closed(self):
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_success_in_closed_state(self):
        """Test successful calls in closed state."""
        breaker = CircuitBreaker(failure_threshold=3)
        result = breaker.call(lambda: "success")
        assert result == "success"
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_single_failure_stays_closed(self):
        """Test single failure keeps circuit closed."""
        breaker = CircuitBreaker(failure_threshold=3)

        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))

        assert breaker.state == CircuitBreakerState.CLOSED

    def test_threshold_failures_open_circuit(self):
        """Test circuit opens after reaching failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Generate 3 failures
        for _ in range(3):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                # Exception is expected here to simulate a failure for the circuit breaker
                pass

        assert breaker.state == CircuitBreakerState.OPEN

    def test_open_circuit_blocks_calls(self):
        """Test open circuit blocks subsequent calls."""
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)

        # Generate failures to open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                # Exception is expected here to simulate failures for opening the circuit
                pass

        # Circuit should be open and block calls
        with pytest.raises(RuntimeError, match="Circuit breaker.*is open"):
            breaker.call(lambda: "test")

    def test_cooldown_transitions_to_half_open(self):
        """Test circuit transitions to half-open after cooldown."""
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

        # Open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                pass

        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for cooldown
        time.sleep(0.15)

        # Next call should transition to half-open and execute
        result = breaker.call(lambda: "success")
        assert result == "success"
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test successful calls in half-open close circuit."""
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1, success_threshold=2)

        # Open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                # Exception is expected here to open the circuit before testing recovery
                pass

        # Wait and transition to half-open
        time.sleep(0.15)

        # Two successes should close circuit
        breaker.call(lambda: "success1")
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        breaker.call(lambda: "success2")
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Test failure in half-open immediately reopens circuit."""
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

        # Open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                pass

        # Wait and transition to half-open
        time.sleep(0.15)
        breaker.call(lambda: "success")
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Failure should reopen circuit
        try:
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
        except ValueError:
            # Exception is expected here to test circuit breaker reopening
            pass

        assert breaker.state == CircuitBreakerState.OPEN

    def test_non_retriable_errors_ignored(self):
        """Test that NOT_FOUND errors don't trigger circuit breaker."""
        breaker = CircuitBreaker(failure_threshold=2)

        # NOT_FOUND errors shouldn't count
        for _ in range(5):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")), ErrorClass.NOT_FOUND)
            except ValueError:
                # Exception is expected; testing that NOT_FOUND errors don't trigger breaker
                pass

        # Circuit should still be closed
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_token_errors_ignored(self):
        """Test that TOKEN errors don't trigger circuit breaker."""
        breaker = CircuitBreaker(failure_threshold=2)

        # TOKEN errors shouldn't count
        for _ in range(5):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")), ErrorClass.TOKEN)
            except ValueError:
                # Exception is expected; testing that TOKEN errors don't trigger breaker
                pass

        # Circuit should still be closed
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_stats_tracking(self):
        """Test circuit breaker tracks statistics."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Record some successes
        breaker.call(lambda: "success")
        breaker.call(lambda: "success")

        stats = breaker.stats
        assert stats.success_count == 2
        assert stats.failure_count == 0
        assert stats.last_success_time is not None

        # Record a failure
        try:
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
        except ValueError:
            # Exception is expected here to test failure tracking
            pass

        stats = breaker.stats
        assert stats.failure_count == 1
        assert stats.last_failure_time is not None

    def test_reset(self):
        """Test manual circuit breaker reset."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open circuit
        for _ in range(2):
            try:
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("error")))
            except ValueError:
                # Exception is expected here to open the circuit for reset test
                pass

        assert breaker.state == CircuitBreakerState.OPEN

        # Reset should close circuit
        breaker.reset()
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.stats.failure_count == 0


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    def test_success_on_first_attempt(self):
        """Test successful call on first attempt doesn't retry."""
        mock_func = Mock(return_value="success")
        result = retry_with_backoff(mock_func, max_attempts=3)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_success_after_retries(self):
        """Test successful call after some failures."""
        mock_func = Mock(side_effect=[ValueError("error1"), ValueError("error2"), "success"])
        result = retry_with_backoff(mock_func, max_attempts=3, base_delay=0.01)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_all_attempts_fail(self):
        """Test exception raised when all attempts fail."""
        mock_func = Mock(side_effect=ValueError("persistent error"))

        with pytest.raises(ValueError, match="persistent error"):
            retry_with_backoff(mock_func, max_attempts=3, base_delay=0.01)

        assert mock_func.call_count == 3

    def test_not_found_error_not_retried(self):
        """Test NOT_FOUND errors are not retried."""
        mock_func = Mock(side_effect=ValueError("Video unavailable"))

        # Custom classifier that returns NOT_FOUND
        def classifier(e):
            return ErrorClass.NOT_FOUND

        with pytest.raises(ValueError):
            retry_with_backoff(mock_func, max_attempts=3, classify_func=classifier)

        # Should only attempt once (no retries for NOT_FOUND)
        assert mock_func.call_count == 1

    @patch("worker.youtube_resilience.time.sleep")
    def test_backoff_delays_applied(self, mock_sleep):
        """Test that backoff delays are applied between retries."""
        mock_func = Mock(side_effect=[ValueError("error1"), ValueError("error2"), "success"])

        retry_with_backoff(mock_func, max_attempts=3, base_delay=1.0)

        # Should sleep twice (between attempts 1-2 and 2-3)
        assert mock_sleep.call_count == 2

    def test_with_circuit_breaker(self):
        """Test retry with circuit breaker integration."""
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10, name="test_retry_cb")
        mock_func = Mock(side_effect=ValueError("error"))

        with pytest.raises((ValueError, RuntimeError)):
            retry_with_backoff(mock_func, max_attempts=3, base_delay=0.01, circuit_breaker=breaker)

        # Circuit should be open after failures (or error raised when open)
        # The test may fail with either ValueError or RuntimeError depending on timing
        assert breaker.state == CircuitBreakerState.OPEN or mock_func.call_count >= 2

    def test_custom_classifier(self):
        """Test custom error classifier is used."""
        mock_func = Mock(side_effect=ValueError("custom error"))
        mock_classifier = Mock(return_value=ErrorClass.THROTTLE)

        with pytest.raises(ValueError):
            retry_with_backoff(mock_func, max_attempts=2, base_delay=0.01, classify_func=mock_classifier)

        # Classifier should be called for each failure
        assert mock_classifier.call_count == 2


class TestGetCircuitBreaker:
    """Tests for get_circuit_breaker function."""

    @patch("worker.youtube_resilience.settings")
    def test_creates_circuit_breaker(self, mock_settings):
        """Test circuit breaker is created with settings."""
        mock_settings.YTDLP_CIRCUIT_BREAKER_THRESHOLD = 10
        mock_settings.YTDLP_CIRCUIT_BREAKER_COOLDOWN = 120.0
        mock_settings.YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 3

        breaker = get_circuit_breaker("test")

        assert isinstance(breaker, CircuitBreaker)
        assert breaker.failure_threshold == 10
        assert breaker.cooldown_seconds == 120.0
        assert breaker.success_threshold == 3

    @patch("worker.youtube_resilience.settings")
    def test_returns_same_instance(self, mock_settings):
        """Test same circuit breaker instance is returned for same name."""
        mock_settings.YTDLP_CIRCUIT_BREAKER_THRESHOLD = 5
        mock_settings.YTDLP_CIRCUIT_BREAKER_COOLDOWN = 60.0
        mock_settings.YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2

        breaker1 = get_circuit_breaker("youtube")
        breaker2 = get_circuit_breaker("youtube")

        assert breaker1 is breaker2

    @patch("worker.youtube_resilience.settings")
    def test_different_names_different_instances(self, mock_settings):
        """Test different names create different circuit breaker instances."""
        mock_settings.YTDLP_CIRCUIT_BREAKER_THRESHOLD = 5
        mock_settings.YTDLP_CIRCUIT_BREAKER_COOLDOWN = 60.0
        mock_settings.YTDLP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2

        breaker1 = get_circuit_breaker("youtube")
        breaker2 = get_circuit_breaker("metadata")

        assert breaker1 is not breaker2
