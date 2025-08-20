"""GitHub API rate limiting management."""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime

from .exceptions import GitHubRateLimitError


@dataclass
class RateLimitInfo:
    """Rate limit information from GitHub API."""

    limit: int
    remaining: int
    reset: int
    used: int = 0
    resource: str = "core"

    @property
    def reset_datetime(self) -> datetime:
        """Get reset time as datetime."""
        return datetime.fromtimestamp(self.reset)

    @property
    def seconds_until_reset(self) -> float:
        """Get seconds until rate limit resets."""
        return max(0, self.reset - time.time())

    @property
    def is_exceeded(self) -> bool:
        """Check if rate limit is exceeded."""
        return self.remaining <= 0

    @property
    def usage_percentage(self) -> float:
        """Get percentage of rate limit used."""
        if self.limit == 0:
            return 0.0
        return ((self.limit - self.remaining) / self.limit) * 100


@dataclass
class RateLimitManager:
    """Manages GitHub API rate limiting."""

    buffer: int = 100  # Reserve buffer before hitting limits
    retry_after_reset: bool = True
    max_retry_wait: int = 3600  # Maximum wait time in seconds

    _rate_limits: dict[str, RateLimitInfo] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def get_rate_limit(self, resource: str = "core") -> RateLimitInfo | None:
        """Get current rate limit info for resource."""
        return self._rate_limits.get(resource)

    def update_rate_limit(self, headers: dict[str, str]) -> None:
        """Update rate limit info from response headers.

        Args:
            headers: HTTP response headers from GitHub API
        """
        if "X-RateLimit-Limit" not in headers:
            return

        try:
            rate_limit = RateLimitInfo(
                limit=int(headers.get("X-RateLimit-Limit", 5000)),
                remaining=int(headers.get("X-RateLimit-Remaining", 0)),
                reset=int(headers.get("X-RateLimit-Reset", 0)),
                used=int(headers.get("X-RateLimit-Used", 0)),
                resource=headers.get("X-RateLimit-Resource", "core"),
            )
            self._rate_limits[rate_limit.resource] = rate_limit
        except (ValueError, TypeError):
            # Ignore invalid rate limit headers
            pass

    async def check_rate_limit(self, resource: str = "core") -> None:
        """Check if rate limit allows request.

        Args:
            resource: GitHub API resource type

        Raises:
            GitHubRateLimitError: If rate limit is exceeded
        """
        rate_limit = self.get_rate_limit(resource)
        if not rate_limit:
            return  # No rate limit info available

        # Check if we're within the buffer zone
        if (
            rate_limit.remaining <= self.buffer
            and self.retry_after_reset
            and rate_limit.seconds_until_reset > 0
        ):
            wait_time = min(rate_limit.seconds_until_reset, self.max_retry_wait)
            if wait_time > 0:
                raise GitHubRateLimitError(
                    f"Rate limit approaching for {resource}. "
                    f"Remaining: {rate_limit.remaining}, "
                    f"Reset in {wait_time:.0f} seconds",
                    reset_time=rate_limit.reset,
                    remaining=rate_limit.remaining,
                    limit=rate_limit.limit,
                )

    async def wait_for_reset(self, resource: str = "core") -> None:
        """Wait for rate limit to reset.

        Args:
            resource: GitHub API resource type
        """
        rate_limit = self.get_rate_limit(resource)
        if not rate_limit or not rate_limit.is_exceeded:
            return

        wait_time = min(rate_limit.seconds_until_reset + 1, self.max_retry_wait)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

    def should_backoff(self, resource: str = "core") -> bool:
        """Check if we should backoff due to rate limits.

        Args:
            resource: GitHub API resource type

        Returns:
            True if we should backoff
        """
        rate_limit = self.get_rate_limit(resource)
        if not rate_limit:
            return False

        # Backoff if we're using more than 80% of rate limit
        return rate_limit.usage_percentage > 80

    def get_backoff_time(self, resource: str = "core") -> float:
        """Calculate backoff time based on rate limit usage.

        Args:
            resource: GitHub API resource type

        Returns:
            Backoff time in seconds
        """
        rate_limit = self.get_rate_limit(resource)
        if not rate_limit:
            return 0

        usage = rate_limit.usage_percentage
        if usage < 80:
            return 0
        elif usage < 90:
            return 1  # 1 second backoff
        elif usage < 95:
            return 5  # 5 seconds backoff
        else:
            # Progressive backoff as we approach limit
            return min(30, rate_limit.seconds_until_reset / 10)


class CircuitBreaker:
    """Circuit breaker for GitHub API failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to track
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = "closed"  # closed, open, half_open

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._state == "open"

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed."""
        return self._state == "closed"

    def record_success(self) -> None:
        """Record successful call."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = "open"

    def can_attempt_request(self) -> bool:
        """Check if request can be attempted."""
        if self.is_closed:
            return True

        if (
            self.is_open
            and self._last_failure_time
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = "half_open"
            return True

        return False

    def get_wait_time(self) -> float:
        """Get time to wait before next attempt."""
        if not self.is_open or not self._last_failure_time:
            return 0

        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)
