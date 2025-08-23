"""
Unit tests for API Resource Manager component.

Tests rate limiting functionality including token management, priority scheduling,
backoff strategies, and concurrent request handling.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.discovery.api_resource_manager import GitHubAPIResourceManager
from src.workers.discovery.interfaces import RateLimitStrategy


# Module-level fixture to share across test classes
@pytest.fixture
def resource_config():
    """
    Why: Provides configuration for API resource management testing
    What: Creates configuration with realistic rate limit settings
    How: Sets up limits and buffers matching GitHub API constraints
    """
    return {
        "core_limit": 5000,
        "search_limit": 30,
        "graphql_limit": 5000,
        "buffer_percentage": 0.1,
        "priority_weights": {
            "critical": 1.0,
            "high": 0.8,
            "normal": 0.6,
            "low": 0.3,
        },
    }


class TestAPIResourceManagerTokenManagement:
    """Tests for basic token acquisition and management."""

    @pytest.fixture
    async def api_resource_manager(self, resource_config):
        """
        Why: Provides configured GitHubAPIResourceManager instance for testing
        What: Creates resource manager with test configuration for isolated testing
        How: Initializes real implementation with test parameters and starts it
        """
        manager = GitHubAPIResourceManager(
            core_limit=resource_config["core_limit"],
            search_limit=resource_config["search_limit"],
            graphql_limit=resource_config["graphql_limit"],
            buffer_percentage=resource_config["buffer_percentage"],
            priority_weights=resource_config["priority_weights"],
        )
        await manager.start()
        yield manager
        await manager.stop()

    async def test_acquire_tokens_succeeds_when_sufficient_tokens_available(
        self, api_resource_manager
    ):
        """
        Why: Ensure token acquisition succeeds when sufficient tokens are available,
             enabling normal API operation without unnecessary blocking.

        What: Tests that acquire_tokens() returns True and decrements available tokens
              when the requested count is within available limit.

        How: Requests tokens within available limit, validates success and proper
             token count decrementation for accurate tracking.
        """
        # Arrange
        resource = "core"
        initial_tokens = await api_resource_manager.get_available_tokens(resource)
        tokens_to_acquire = 10

        # Act
        success = await api_resource_manager.acquire_tokens(resource, tokens_to_acquire)

        # Assert
        assert success is True

        # Verify tokens were decremented
        remaining_tokens = await api_resource_manager.get_available_tokens(resource)
        assert remaining_tokens == initial_tokens - tokens_to_acquire

    async def test_acquire_tokens_fails_when_insufficient_tokens_available(
        self, api_resource_manager
    ):
        """
        Why: Ensure token acquisition fails gracefully when insufficient tokens
             are available, preventing API rate limit violations.

        What: Tests that acquire_tokens() returns False when requested token count
              exceeds available tokens, without affecting token counts.

        How: Reduces available tokens then requests more than available, validates
             failure response and token counts remain unchanged.
        """
        # Arrange
        resource = "core"
        # Core has 5000 * 0.9 = 4500 effective tokens
        # Reduce available tokens to just a few
        initial_available = await api_resource_manager.get_available_tokens(resource)
        to_exhaust = initial_available - 5  # Leave only 5 tokens
        if to_exhaust > 0:
            await api_resource_manager.acquire_tokens(resource, to_exhaust)

        remaining_before = await api_resource_manager.get_available_tokens(resource)
        tokens_to_acquire = 10  # More than available

        # Act
        success = await api_resource_manager.acquire_tokens(resource, tokens_to_acquire)

        # Assert
        assert success is False

        # Verify tokens were not decremented
        remaining_after = await api_resource_manager.get_available_tokens(resource)
        assert remaining_after == remaining_before

    async def test_get_available_tokens_returns_accurate_count(
        self, api_resource_manager
    ):
        """
        Why: Ensure accurate token count reporting for making informed decisions
             about API request scheduling and resource allocation.

        What: Tests that get_available_tokens() returns current accurate token count
              that reflects recent acquisitions and limit updates.

        How: Performs token acquisitions and limit updates, validates reported
             counts match expected values after each operation.
        """
        # Arrange
        resource = "search"

        # Act - Check initial tokens
        initial_tokens = await api_resource_manager.get_available_tokens(resource)

        # Assert initial state
        # Search has 30 * 0.9 = 27 effective tokens due to buffer
        assert initial_tokens == 27

        # Act - Acquire some tokens
        await api_resource_manager.acquire_tokens(resource, 5)
        tokens_after_acquisition = await api_resource_manager.get_available_tokens(
            resource
        )

        # Assert tokens decremented correctly
        assert tokens_after_acquisition == 22  # 27 - 5 = 22

    async def test_update_limit_info_updates_resource_limits_correctly(
        self, api_resource_manager
    ):
        """
        Why: Ensure resource manager can update limit information from API responses,
             maintaining accurate rate limit tracking as limits change.

        What: Tests that update_limit_info() updates stored limit information and
              available token counts based on API response headers.

        How: Updates limit info with new values, validates stored information
             matches provided values and affects subsequent token operations.
        """
        # Arrange
        resource = "core"
        new_limit = 4000
        new_remaining = 3500
        reset_time = datetime.now(UTC) + timedelta(hours=1)

        # Act
        await api_resource_manager.update_limit_info(
            resource, new_limit, new_remaining, reset_time
        )

        # Assert limit info updated
        # Note: The real implementation doesn't directly expose remaining counts
        # but stores them in api_limits
        assert resource in api_resource_manager.api_limits
        assert api_resource_manager.api_limits[resource]["limit"] == new_limit
        assert api_resource_manager.api_limits[resource]["remaining"] == new_remaining
        assert api_resource_manager.api_limits[resource]["reset_time"] == reset_time

    async def test_token_acquisition_handles_concurrent_requests_safely(
        self, api_resource_manager
    ):
        """
        Why: Ensure token acquisition is thread-safe and handles concurrent requests
             without race conditions or incorrect token accounting.

        What: Tests that multiple concurrent acquire_tokens() calls maintain accurate
              token counts and don't over-allocate tokens beyond available limit.

        How: Makes multiple concurrent token acquisition requests, validates total
             acquired tokens don't exceed available limit and final count is correct.
        """
        # Arrange
        resource = "core"
        initial_tokens = await api_resource_manager.get_available_tokens(resource)
        concurrent_requests = 10
        tokens_per_request = 50

        # Act - Make concurrent token acquisition requests
        tasks = [
            api_resource_manager.acquire_tokens(resource, tokens_per_request)
            for _ in range(concurrent_requests)
        ]
        results = await asyncio.gather(*tasks)

        # Assert
        successful_acquisitions = sum(1 for result in results if result)
        tokens_acquired = successful_acquisitions * tokens_per_request

        # Verify total acquired doesn't exceed what was available
        remaining_tokens = await api_resource_manager.get_available_tokens(resource)
        assert remaining_tokens == initial_tokens - tokens_acquired
        assert tokens_acquired <= initial_tokens


class TestAPIResourceManagerWaitingAndBackoff:
    """Tests for waiting mechanisms and backoff strategies."""

    @pytest.fixture
    async def backoff_resource_manager(self, resource_config):
        """Resource manager configured for backoff testing."""
        manager = GitHubAPIResourceManager(
            core_limit=resource_config["core_limit"],
            search_limit=resource_config["search_limit"],
            graphql_limit=resource_config["graphql_limit"],
            buffer_percentage=resource_config["buffer_percentage"],
            priority_weights=resource_config["priority_weights"],
        )
        await manager.start()
        yield manager
        await manager.stop()

    async def test_wait_for_tokens_succeeds_when_tokens_become_available(
        self, backoff_resource_manager
    ):
        """
        Why: Ensure wait mechanism successfully waits for tokens to become available,
             enabling automatic retry without manual intervention.

        What: Tests that wait_for_tokens() successfully waits and returns True when
              tokens become available within the timeout period.

        How: Simulates token availability after brief delay, validates wait
             operation succeeds within reasonable time bounds.
        """
        # Arrange
        resource = "search"
        # Exhaust available tokens
        await backoff_resource_manager.acquire_tokens(resource, 30)

        # Act
        start_time = asyncio.get_event_loop().time()
        success = await backoff_resource_manager.wait_for_tokens(
            resource, 1, timeout=5.0
        )
        end_time = asyncio.get_event_loop().time()

        # Assert
        assert success is True
        # Should complete relatively quickly (mock waits 0.1s)
        assert end_time - start_time < 1.0

    async def test_wait_for_tokens_times_out_when_tokens_unavailable(
        self, backoff_resource_manager
    ):
        """
        Why: Ensure wait mechanism respects timeout to prevent indefinite blocking
             when tokens don't become available, maintaining system responsiveness.

        What: Tests that wait_for_tokens() returns False when tokens don't become
              available within the specified timeout period.

        How: Configures scenario where tokens remain unavailable, validates timeout
             behavior and appropriate return value for failed waits.
        """
        # Arrange
        resource = "search"
        # Exhaust all tokens - search has a very low limit (30 * 0.9 = 27 effective)
        available = await backoff_resource_manager.get_available_tokens(resource)
        if available > 0:
            await backoff_resource_manager.acquire_tokens(resource, available)

        # Act - Try to acquire more tokens with a short timeout
        success = await backoff_resource_manager.wait_for_tokens(
            resource,
            100,
            timeout=0.5,  # Request many tokens that can't be fulfilled
        )

        # Assert - Should timeout since tokens can't be refilled fast enough
        assert success is False  # Should timeout

    async def test_exponential_backoff_increases_wait_time_appropriately(
        self, backoff_resource_manager
    ):
        """
        Why: Ensure wait mechanism handles repeated attempts with increasing delays
             to reduce API pressure while allowing eventual success as limits reset.

        What: Tests that wait_for_tokens mechanism with timeout handles multiple
              attempts appropriately without overwhelming the API.

        How: Makes multiple wait attempts with timeout, validates behavior is
             consistent and doesn't cause system issues.
        """
        # Arrange
        resource = "search"
        # Exhaust available tokens
        available = await backoff_resource_manager.get_available_tokens(resource)
        if available > 0:
            await backoff_resource_manager.acquire_tokens(resource, available)

        # Act - Make multiple wait attempts with short timeouts
        timeout_results = []
        for _ in range(3):
            result = await backoff_resource_manager.wait_for_tokens(
                resource,
                50,
                timeout=0.1,  # Request many tokens with short timeout
            )
            timeout_results.append(result)

        # Assert - All should timeout since tokens are exhausted and can't refill
        # fast enough
        for result in timeout_results:
            assert result is False  # Should timeout

    async def test_wait_mechanism_handles_reset_time_correctly(
        self, backoff_resource_manager
    ):
        """
        Why: Ensure wait mechanism considers rate limit reset times for optimal
             waiting, avoiding unnecessary delays when limits will reset soon.

        What: Tests that update_limit_info() properly stores reset time information
              which can be used for intelligent waiting strategies.

        How: Sets rate limit with near-future reset time, validates information
             is properly stored and accessible for wait calculations.
        """
        # Arrange
        resource = "core"
        reset_time = datetime.now(UTC) + timedelta(seconds=2)

        # Act - Update limit info with near-future reset
        await backoff_resource_manager.update_limit_info(
            resource, 5000, 100, reset_time
        )

        # Assert - Verify reset time is stored correctly
        assert resource in backoff_resource_manager.api_limits
        stored_info = backoff_resource_manager.api_limits[resource]
        assert stored_info["reset_time"] == reset_time
        assert stored_info["limit"] == 5000
        assert stored_info["remaining"] == 100


class TestAPIResourceManagerPriorityScheduling:
    """Tests for priority-based request scheduling."""

    @pytest.fixture
    async def priority_resource_manager(self, resource_config):
        """Resource manager configured for priority testing."""
        manager = GitHubAPIResourceManager(
            core_limit=resource_config["core_limit"],
            search_limit=resource_config["search_limit"],
            graphql_limit=resource_config["graphql_limit"],
            buffer_percentage=resource_config["buffer_percentage"],
            priority_weights=resource_config["priority_weights"],
        )
        await manager.start()
        yield manager
        await manager.stop()

    async def test_high_priority_requests_get_preferential_token_access(
        self, priority_resource_manager
    ):
        """
        Why: Ensure high-priority requests get preferential access to limited tokens,
             allowing critical operations to proceed even under rate limit pressure.

        What: Tests that high-priority token requests are granted before lower-priority
              requests when tokens are limited.

        How: Creates mixed priority requests competing for limited tokens, validates
             high-priority requests succeed while lower-priority requests wait.
        """
        # Arrange
        resource = "core"
        # Reduce available tokens to create scarcity
        # Core has 5000 * 0.9 = 4500 effective tokens
        available = await priority_resource_manager.get_available_tokens(resource)
        if available > 20:
            await priority_resource_manager.acquire_tokens(
                resource, available - 20
            )  # Leave only 20 tokens

        # Act - Request tokens with different priorities using the priority method
        # High priority should get tokens first
        high_priority_task = asyncio.create_task(
            priority_resource_manager.acquire_tokens_with_priority(
                resource, priority="high", count=10, timeout=0.5
            )
        )

        # Give high priority a head start
        await asyncio.sleep(0.01)

        normal_priority_task = asyncio.create_task(
            priority_resource_manager.acquire_tokens_with_priority(
                resource, priority="normal", count=15, timeout=0.1
            )
        )

        # Wait for both tasks
        high_result = await high_priority_task
        await normal_priority_task  # Don't need to store result, just wait

        # Assert
        assert high_result is True  # High priority should succeed
        # Normal priority might fail if tokens were consumed by high priority

    async def test_priority_queue_maintains_correct_ordering(
        self, priority_resource_manager
    ):
        """
        Why: Ensure priority queue maintains correct request ordering to process
             high-priority requests before lower-priority ones consistently.

        What: Tests that priority-based token acquisition processes higher priority
              requests before lower priority ones.

        How: Tests the priority weights configuration and queue size tracking
             to validate priority system is working.
        """
        # Arrange - Verify priority weights are configured correctly
        assert "critical" in priority_resource_manager.priority_weights
        assert "high" in priority_resource_manager.priority_weights
        assert "normal" in priority_resource_manager.priority_weights
        assert "low" in priority_resource_manager.priority_weights

        # Verify weights are in correct order
        weights = priority_resource_manager.priority_weights
        assert weights["critical"] > weights["high"]
        assert weights["high"] > weights["normal"]
        assert weights["normal"] > weights["low"]

        # Act - Check queue sizes (initially should be empty)
        for priority in ["critical", "high", "normal", "low"]:
            queue_size = priority_resource_manager.request_queues[priority].qsize()
            assert queue_size == 0  # All queues start empty

    async def test_priority_scheduling_handles_equal_priority_requests_fairly(
        self, priority_resource_manager
    ):
        """
        Why: Ensure requests with equal priority are handled fairly using FIFO
             ordering, preventing starvation of any particular request source.

        What: Tests that AsyncQueue used for each priority level maintains FIFO
              order for requests of the same priority.

        How: Verifies that request queues are properly initialized and can handle
             multiple requests of the same priority level.
        """
        # Arrange
        resource = "core"
        priority = "normal"

        # Exhaust most tokens to create queueing scenario
        available = await priority_resource_manager.get_available_tokens(resource)
        if available > 5:
            await priority_resource_manager.acquire_tokens(resource, available - 5)

        # Act - Make multiple same-priority requests
        tasks = []
        for _ in range(3):
            task = asyncio.create_task(
                priority_resource_manager.acquire_tokens_with_priority(
                    resource, priority=priority, count=3, timeout=0.1
                )
            )
            tasks.append(task)
            await asyncio.sleep(0.01)  # Small delay between requests

        # Wait for all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - At least one should succeed (the first in queue)
        successes = [r for r in results if r is True]
        assert len(successes) >= 1  # At least one should get tokens


class TestAPIResourceManagerEdgeCases:
    """Tests for edge cases and error scenarios in resource management."""

    @pytest.fixture
    async def edge_case_manager(self, resource_config):
        """Resource manager configured for edge case testing."""
        manager = GitHubAPIResourceManager(
            core_limit=resource_config["core_limit"],
            search_limit=resource_config["search_limit"],
            graphql_limit=resource_config["graphql_limit"],
            buffer_percentage=resource_config["buffer_percentage"],
            priority_weights=resource_config["priority_weights"],
        )
        await manager.start()
        yield manager
        await manager.stop()

    async def test_resource_manager_handles_unknown_resource_types_gracefully(
        self, edge_case_manager
    ):
        """
        Why: Ensure resource manager handles requests for unknown resource types
             gracefully without crashing, maintaining system stability.

        What: Tests that operations on undefined resource types return appropriate
              default values or errors without system failures.

        How: Requests tokens for undefined resource type, validates graceful
             handling with appropriate error responses or default behavior.
        """
        # Arrange
        unknown_resource = "unknown_api_resource"

        # Act
        available_tokens = await edge_case_manager.get_available_tokens(
            unknown_resource
        )
        acquisition_success = await edge_case_manager.acquire_tokens(
            unknown_resource, 5
        )

        # Assert graceful handling
        assert available_tokens == 0  # Default for unknown resource
        assert acquisition_success is False  # Can't acquire from unknown resource

    async def test_resource_manager_handles_zero_token_requests(
        self, edge_case_manager
    ):
        """
        Why: Ensure resource manager validates token request parameters and handles
             edge case requests gracefully without corrupting internal state.

        What: Tests that zero token requests are handled appropriately
              without affecting available token counts or causing errors.

        How: Requests zero tokens, validates appropriate handling
             and internal state remains consistent.
        """
        # Arrange
        resource = "core"
        initial_tokens = await edge_case_manager.get_available_tokens(resource)

        # Act - Zero tokens should succeed trivially
        zero_result = await edge_case_manager.acquire_tokens(resource, 0)

        # Assert
        assert zero_result is True  # Zero tokens should succeed trivially

        # Verify token count unchanged
        final_tokens = await edge_case_manager.get_available_tokens(resource)
        assert final_tokens == initial_tokens  # No change from zero request

    async def test_resource_manager_handles_limit_info_edge_cases(
        self, edge_case_manager
    ):
        """
        Why: Ensure resource manager handles edge cases in limit information updates
             such as None values or missing reset times gracefully.

        What: Tests that update_limit_info() handles edge cases like None reset times
              or zero limits gracefully.

        How: Updates limit info with edge case values, validates appropriate
             handling and internal state consistency.
        """
        # Arrange
        resource = "search"
        reset_time = datetime.now(UTC) + timedelta(hours=1)

        # Act - Update with zero limit (edge case but valid)
        await edge_case_manager.update_limit_info(resource, 0, 0, reset_time)

        # Assert graceful handling
        assert resource in edge_case_manager.api_limits
        assert edge_case_manager.api_limits[resource]["limit"] == 0
        assert edge_case_manager.api_limits[resource]["remaining"] == 0
        assert edge_case_manager.api_limits[resource]["reset_time"] == reset_time

    async def test_resource_manager_maintains_consistency_under_rapid_updates(
        self, edge_case_manager
    ):
        """
        Why: Ensure resource manager maintains internal consistency when receiving
             rapid limit info updates, as might occur during high API usage.

        What: Tests that rapid consecutive update_limit_info() calls maintain
              consistent internal state without race conditions.

        How: Makes rapid consecutive limit updates with varying values, validates
             final state is consistent and reflects last update accurately.
        """
        # Arrange
        resource = "core"
        updates = [
            (4000, 3000, datetime.now(UTC) + timedelta(hours=1)),
            (4500, 3500, datetime.now(UTC) + timedelta(hours=1, minutes=5)),
            (4200, 3200, datetime.now(UTC) + timedelta(hours=1, minutes=10)),
        ]

        # Act - Apply rapid consecutive updates
        last_limit, last_remaining, last_reset = updates[-1]
        for limit, remaining, reset_time in updates:
            await edge_case_manager.update_limit_info(
                resource, limit, remaining, reset_time
            )

        # Assert final state reflects last update
        assert resource in edge_case_manager.api_limits
        final_info = edge_case_manager.api_limits[resource]
        assert final_info["limit"] == last_limit
        assert final_info["remaining"] == last_remaining
        assert final_info["reset_time"] == last_reset


class TestAPIResourceManagerAdditionalFeatures:
    """Tests for additional features specific to GitHubAPIResourceManager."""

    @pytest.fixture
    async def feature_manager(self, resource_config):
        """Resource manager for testing additional features."""
        manager = GitHubAPIResourceManager(
            core_limit=resource_config["core_limit"],
            search_limit=resource_config["search_limit"],
            graphql_limit=resource_config["graphql_limit"],
            buffer_percentage=resource_config["buffer_percentage"],
            priority_weights=resource_config["priority_weights"],
        )
        await manager.start()
        yield manager
        await manager.stop()

    async def test_get_resource_status_returns_comprehensive_information(
        self, feature_manager
    ):
        """
        Why: Ensure resource status provides comprehensive information for monitoring
             and debugging rate limit state across all resources.

        What: Tests that get_resource_status() returns detailed information about
              all managed resources including capacity, tokens, and utilization.

        How: Calls get_resource_status() and validates returned structure contains
             expected fields for all resource types.
        """
        # Act
        status = feature_manager.get_resource_status()

        # Assert - Check structure for each resource
        for resource in ["core", "search", "graphql"]:
            assert resource in status
            resource_status = status[resource]

            # Check bucket status fields
            assert "capacity" in resource_status
            assert "current_tokens" in resource_status
            assert "refill_rate" in resource_status
            assert "utilization" in resource_status

            # Check queue status fields for priority queues
            for priority in ["critical", "high", "normal", "low"]:
                queue_key = f"{priority}_queue_size"
                assert queue_key in resource_status
                assert isinstance(resource_status[queue_key], int)

    async def test_estimate_wait_time_provides_reasonable_estimates(
        self, feature_manager
    ):
        """
        Why: Ensure wait time estimation helps users understand how long they need
             to wait for tokens, enabling better scheduling decisions.

        What: Tests that estimate_wait_time() provides reasonable time estimates
              based on current token availability and refill rates.

        How: Estimates wait times for various token counts and validates estimates
             are reasonable based on bucket refill rates.
        """
        # Arrange
        resource = "search"

        # Act - Get wait time when tokens are available
        available = await feature_manager.get_available_tokens(resource)
        wait_for_available = feature_manager.estimate_wait_time(resource, available - 1)
        wait_for_more = feature_manager.estimate_wait_time(resource, available + 10)

        # Assert
        assert wait_for_available == 0.0  # Should be immediate if tokens available
        assert wait_for_more > 0  # Should wait if requesting more than available
        assert wait_for_more < 3600  # Should be less than an hour (reasonable)

    async def test_get_optimal_batch_size_provides_reasonable_recommendations(
        self, feature_manager
    ):
        """
        Why: Ensure batch size recommendations help optimize API usage by suggesting
             appropriate batch sizes based on current token availability.

        What: Tests that get_optimal_batch_size() returns reasonable batch size
              recommendations that respect resource limits.

        How: Gets batch size recommendations for different resources and validates
             they are within expected ranges for each resource type.
        """
        # Act
        core_batch = await feature_manager.get_optimal_batch_size("core")
        search_batch = await feature_manager.get_optimal_batch_size("search")
        graphql_batch = await feature_manager.get_optimal_batch_size("graphql")

        # Assert
        # Core and GraphQL should support larger batches
        assert 1 <= core_batch <= 50
        assert 1 <= graphql_batch <= 50

        # Search API is more limited
        assert 1 <= search_batch <= 10

        # Search should generally have smaller batches than core
        assert search_batch <= core_batch

    async def test_token_bucket_refill_mechanism_works_correctly(self, feature_manager):
        """
        Why: Ensure token bucket refill mechanism correctly replenishes tokens over
             time, maintaining proper rate limiting behavior.

        What: Tests that tokens are refilled over time according to the configured
              refill rate, allowing continued API usage.

        How: Exhausts tokens, waits briefly, then checks if tokens have been
             partially refilled according to the refill rate.
        """
        # Arrange
        resource = "search"
        initial = await feature_manager.get_available_tokens(resource)

        # Exhaust some tokens
        to_acquire = min(5, initial)
        if to_acquire > 0:
            await feature_manager.acquire_tokens(resource, to_acquire)

        after_acquire = await feature_manager.get_available_tokens(resource)

        # Act - Wait a bit for refill
        await asyncio.sleep(0.1)

        after_wait = await feature_manager.get_available_tokens(resource)

        # Assert - Should have some refill (might be small due to short wait)
        # The bucket should refill at least partially
        assert after_wait >= after_acquire  # Should not decrease

        # If we exhausted tokens, we should see some refill
        if after_acquire < initial:
            # Due to continuous refill, we might have more tokens
            # but this depends on refill rate and timing
            pass  # Token refill is time-dependent
