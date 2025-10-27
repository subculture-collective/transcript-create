"""Client-side rate limiting."""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for client-side rate limiting."""

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: Optional[int] = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second
            burst_size: Maximum burst size (defaults to requests_per_second)
        """
        self.rate = requests_per_second
        self.burst_size = burst_size or int(requests_per_second)
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Add tokens based on elapsed time
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Calculate wait time for next token
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)

    def reset(self) -> None:
        """Reset rate limiter to full capacity."""
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()


class AdaptiveRateLimiter(RateLimiter):
    """Rate limiter that adapts based on 429 responses."""

    def __init__(
        self,
        initial_requests_per_second: float = 10.0,
        min_requests_per_second: float = 1.0,
        max_requests_per_second: float = 100.0,
        increase_factor: float = 1.1,
        decrease_factor: float = 0.5,
    ) -> None:
        """Initialize adaptive rate limiter.

        Args:
            initial_requests_per_second: Starting rate
            min_requests_per_second: Minimum allowed rate
            max_requests_per_second: Maximum allowed rate
            increase_factor: Factor to increase rate on success
            decrease_factor: Factor to decrease rate on 429
        """
        super().__init__(initial_requests_per_second)
        self.min_rate = min_requests_per_second
        self.max_rate = max_requests_per_second
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        self.success_count = 0
        self.success_threshold = 10  # Increase rate after N successes

    async def on_success(self) -> None:
        """Called after successful request."""
        async with self._lock:
            self.success_count += 1

            if self.success_count >= self.success_threshold:
                # Gradually increase rate
                new_rate = min(self.rate * self.increase_factor, self.max_rate)
                if new_rate != self.rate:
                    self.rate = new_rate
                    self.success_count = 0

    async def on_rate_limit(self) -> None:
        """Called when rate limit is hit."""
        async with self._lock:
            # Decrease rate immediately
            self.rate = max(self.rate * self.decrease_factor, self.min_rate)
            self.success_count = 0
