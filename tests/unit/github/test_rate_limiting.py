"""
Unit tests for GitHub rate limiting module.

Why: Ensure rate limiting works correctly to prevent API limit violations
     and that circuit breaker protects against cascading failures.

What: Tests RateLimitInfo, RateLimitManager, and CircuitBreaker classes
      for proper rate limit tracking and failure handling.

How: Uses mocked headers and timing to test rate limit calculations,
     threshold enforcement, and circuit breaker state transitions.
"""

import asyncio
import time
from typing import Any
from unittest.mock import patch

import pytest

from src.github.exceptions import GitHubRateLimitError
from src.github.rate_limiting import (
    CircuitBreaker,
    RateLimitInfo,
    RateLimitManager,
)


class TestRateLimitInfo:
    """Test RateLimitInfo data class."""

    def test_rate_limit_info_creation(self) -> None:
        """Test basic RateLimitInfo creation."""
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=4500,
            reset=int(time.time()) + 3600,
            used=500,
            resource="core",
        )

        assert rate_limit.limit == 5000
        assert rate_limit.remaining == 4500
        assert rate_limit.used == 500
        assert rate_limit.resource == "core"

    def test_reset_datetime_property(self) -> None:
        """Test reset_datetime property."""
        reset_time = int(time.time()) + 3600
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=4500,
            reset=reset_time,
        )

        assert rate_limit.reset_datetime.timestamp() == reset_time

    def test_seconds_until_reset(self) -> None:
        """Test seconds_until_reset calculation."""
        reset_time = int(time.time()) + 300  # 5 minutes from now
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=4500,
            reset=reset_time,
        )

        seconds_until = rate_limit.seconds_until_reset
        assert 295 <= seconds_until <= 305  # Allow for small timing differences

    def test_seconds_until_reset_past(self) -> None:
        """Test seconds_until_reset for past reset time."""
        reset_time = int(time.time()) - 300  # 5 minutes ago
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=4500,
            reset=reset_time,
        )

        assert rate_limit.seconds_until_reset == 0

    def test_is_exceeded_property(self) -> None:
        """Test is_exceeded property."""
        # Not exceeded
        rate_limit = RateLimitInfo(limit=5000, remaining=100, reset=0)
        assert not rate_limit.is_exceeded

        # Exceeded
        rate_limit = RateLimitInfo(limit=5000, remaining=0, reset=0)
        assert rate_limit.is_exceeded

    def test_usage_percentage(self) -> None:
        """Test usage_percentage calculation."""
        rate_limit = RateLimitInfo(limit=5000, remaining=4000, reset=0)
        assert rate_limit.usage_percentage == 20.0

        rate_limit = RateLimitInfo(limit=5000, remaining=0, reset=0)
        assert rate_limit.usage_percentage == 100.0

        # Edge case: zero limit
        rate_limit = RateLimitInfo(limit=0, remaining=0, reset=0)
        assert rate_limit.usage_percentage == 0.0


class TestRateLimitManager:
    """Test RateLimitManager class."""

    def test_rate_limit_manager_creation(self) -> None:
        """Test RateLimitManager creation with default values."""
        manager = RateLimitManager()
        assert manager.buffer == 100
        assert manager.retry_after_reset is True
        assert manager.max_retry_wait == 3600

    def test_rate_limit_manager_custom_config(self) -> None:
        """Test RateLimitManager with custom configuration."""
        manager = RateLimitManager(
            buffer=50,
            retry_after_reset=False,
            max_retry_wait=1800,
        )
        assert manager.buffer == 50
        assert manager.retry_after_reset is False
        assert manager.max_retry_wait == 1800

    def test_update_rate_limit_valid_headers(self) -> None:
        """Test updating rate limit info from valid headers."""
        manager = RateLimitManager()
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4500",
            "X-RateLimit-Reset": str(int(time.time()) + 3600),
            "X-RateLimit-Used": "500",
            "X-RateLimit-Resource": "core",
        }

        manager.update_rate_limit(headers)
        rate_limit = manager.get_rate_limit("core")

        assert rate_limit is not None
        assert rate_limit.limit == 5000
        assert rate_limit.remaining == 4500
        assert rate_limit.used == 500
        assert rate_limit.resource == "core"

    def test_update_rate_limit_missing_headers(self) -> None:
        """Test updating rate limit with missing headers."""
        manager = RateLimitManager()
        headers: dict[str, str] = {}  # No rate limit headers

        manager.update_rate_limit(headers)
        rate_limit = manager.get_rate_limit("core")

        assert rate_limit is None

    def test_update_rate_limit_invalid_headers(self) -> None:
        """Test updating rate limit with invalid header values."""
        manager = RateLimitManager()
        headers = {
            "X-RateLimit-Limit": "invalid",
            "X-RateLimit-Remaining": "not_a_number",
        }

        # Should not raise exception, just ignore invalid headers
        manager.update_rate_limit(headers)
        rate_limit = manager.get_rate_limit("core")

        assert rate_limit is None

    async def test_check_rate_limit_no_info(self) -> None:
        """Test checking rate limit with no stored info."""
        manager = RateLimitManager()

        # Should not raise exception when no rate limit info available
        await manager.check_rate_limit("core")

    async def test_check_rate_limit_within_buffer(self) -> None:
        """Test checking rate limit when within buffer zone."""
        manager = RateLimitManager(buffer=100, retry_after_reset=False)

        # Set rate limit info that's within buffer
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "50",  # Below buffer of 100
            "X-RateLimit-Reset": str(int(time.time()) + 300),
        }
        manager.update_rate_limit(headers)

        # Should not raise exception when retry_after_reset is False
        await manager.check_rate_limit("core")

    async def test_check_rate_limit_buffer_with_retry(self) -> None:
        """Test checking rate limit with retry enabled."""
        manager = RateLimitManager(buffer=100, retry_after_reset=True)

        # Set rate limit info that's within buffer
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "50",  # Below buffer of 100
            "X-RateLimit-Reset": str(int(time.time()) + 10),  # Short wait
        }
        manager.update_rate_limit(headers)

        # Should raise GitHubRateLimitError when retry_after_reset is True
        with pytest.raises(GitHubRateLimitError) as exc_info:
            await manager.check_rate_limit("core")

        assert "Rate limit approaching" in str(exc_info.value)
        assert exc_info.value.remaining == 50

    async def test_wait_for_reset_no_info(self) -> None:
        """Test waiting for reset with no rate limit info."""
        manager = RateLimitManager()

        # Should return immediately when no rate limit info
        start_time = time.time()
        await manager.wait_for_reset("core")
        elapsed = time.time() - start_time

        assert elapsed < 0.1  # Should be nearly instantaneous

    async def test_wait_for_reset_not_exceeded(self) -> None:
        """Test waiting for reset when not exceeded."""
        manager = RateLimitManager()

        # Set rate limit info that's not exceeded
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "1000",
            "X-RateLimit-Reset": str(int(time.time()) + 300),
        }
        manager.update_rate_limit(headers)

        # Should return immediately when not exceeded
        start_time = time.time()
        await manager.wait_for_reset("core")
        elapsed = time.time() - start_time

        assert elapsed < 0.1

    @patch("asyncio.sleep")
    async def test_wait_for_reset_exceeded(self, mock_sleep: Any) -> None:
        """Test waiting for reset when exceeded."""
        manager = RateLimitManager()

        # Set rate limit info that's exceeded
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 10),  # 10 seconds
        }
        manager.update_rate_limit(headers)

        await manager.wait_for_reset("core")

        # Should have called sleep with approximately 11 seconds (reset + 1)
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 10 <= sleep_time <= 12

    def test_should_backoff_no_info(self) -> None:
        """Test should_backoff with no rate limit info."""
        manager = RateLimitManager()
        assert not manager.should_backoff("core")

    def test_should_backoff_below_threshold(self) -> None:
        """Test should_backoff below 80% usage."""
        manager = RateLimitManager()

        # 70% usage (1500 used out of 5000)
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "3500",
            "X-RateLimit-Reset": str(int(time.time()) + 300),
        }
        manager.update_rate_limit(headers)

        assert not manager.should_backoff("core")

    def test_should_backoff_above_threshold(self) -> None:
        """Test should_backoff above 80% usage."""
        manager = RateLimitManager()

        # 90% usage (4500 used out of 5000)
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "500",
            "X-RateLimit-Reset": str(int(time.time()) + 300),
        }
        manager.update_rate_limit(headers)

        assert manager.should_backoff("core")

    def test_get_backoff_time_usage_levels(self) -> None:
        """Test backoff time calculation for different usage levels."""
        manager = RateLimitManager()

        # 70% usage - no backoff
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "1500",
            "X-RateLimit-Reset": str(int(time.time()) + 300),
        }
        manager.update_rate_limit(headers)
        assert manager.get_backoff_time("core") == 0

        # 85% usage - 1 second backoff
        headers["X-RateLimit-Remaining"] = "750"
        manager.update_rate_limit(headers)
        assert manager.get_backoff_time("core") == 1

        # 92% usage - 5 seconds backoff
        headers["X-RateLimit-Remaining"] = "400"
        manager.update_rate_limit(headers)
        assert manager.get_backoff_time("core") == 5

        # 98% usage - progressive backoff
        headers["X-RateLimit-Remaining"] = "100"
        manager.update_rate_limit(headers)
        backoff_time = manager.get_backoff_time("core")
        assert backoff_time > 5


class TestCircuitBreaker:
    """Test CircuitBreaker class."""

    def test_circuit_breaker_creation(self) -> None:
        """Test CircuitBreaker creation with default values."""
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 60
        assert cb.expected_exception is Exception
        assert cb.is_closed
        assert not cb.is_open

    def test_circuit_breaker_custom_config(self) -> None:
        """Test CircuitBreaker with custom configuration."""
        cb = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=ValueError,
        )
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 30
        assert cb.expected_exception is ValueError

    def test_record_success(self) -> None:
        """Test recording successful calls."""
        cb = CircuitBreaker(failure_threshold=2)

        # Record some failures first
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        # Success should reset and close circuit
        cb.record_success()
        assert cb.is_closed
        assert cb._failure_count == 0

    def test_record_failure_threshold(self) -> None:
        """Test circuit opening at failure threshold."""
        cb = CircuitBreaker(failure_threshold=2)

        # First failure - should stay closed
        cb.record_failure()
        assert cb.is_closed
        assert cb._failure_count == 1

        # Second failure - should open circuit
        cb.record_failure()
        assert cb.is_open
        assert cb._failure_count == 2

    def test_can_attempt_request_closed(self) -> None:
        """Test request attempts when circuit is closed."""
        cb = CircuitBreaker()
        assert cb.can_attempt_request()

    def test_can_attempt_request_open(self) -> None:
        """Test request attempts when circuit is open."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        # Open the circuit
        cb.record_failure()
        assert cb.is_open
        assert not cb.can_attempt_request()

    def test_can_attempt_request_recovery(self) -> None:
        """Test request attempts during recovery period."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1)

        # Open the circuit
        cb.record_failure()
        assert cb.is_open

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should allow attempt and transition to half-open
        assert cb.can_attempt_request()
        assert cb._state == "half_open"

    def test_get_wait_time_closed(self) -> None:
        """Test wait time when circuit is closed."""
        cb = CircuitBreaker()
        assert cb.get_wait_time() == 0

    def test_get_wait_time_open(self) -> None:
        """Test wait time when circuit is open."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        # Open the circuit
        cb.record_failure()

        wait_time = cb.get_wait_time()
        assert 55 <= wait_time <= 60  # Should be close to recovery_timeout

    def test_get_wait_time_no_failure_time(self) -> None:
        """Test wait time when circuit is open but no failure time recorded."""
        cb = CircuitBreaker()
        cb._state = "open"  # Manually set to open
        cb._last_failure_time = None

        assert cb.get_wait_time() == 0
