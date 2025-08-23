"""API resource manager for GitHub rate limit management.

This module implements the RateLimitStrategy interface to manage GitHub API
rate limits with priority-based scheduling and backpressure mechanisms.
"""

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .interfaces import RateLimitStrategy

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket implementation for rate limiting.

    Provides smooth rate limiting with burst capacity and automatic refill.
    """

    def __init__(
        self, capacity: int, refill_rate: float, initial_tokens: int | None = None
    ):
        """Initialize token bucket.

        Args:
            capacity: Maximum number of tokens in bucket
            refill_rate: Tokens added per second
            initial_tokens: Initial token count (defaults to capacity)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens: float = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self, count: int = 1) -> bool:
        """Try to acquire tokens from bucket.

        Args:
            count: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise
        """
        async with self.lock:
            await self._refill()

            if self.tokens >= count:
                self.tokens -= count
                return True
            return False

    async def wait_for_tokens(
        self, count: int = 1, timeout: float | None = None
    ) -> bool:
        """Wait until tokens are available.

        Args:
            count: Number of tokens needed
            timeout: Maximum time to wait in seconds

        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()

        while True:
            if await self.acquire(count):
                return True

            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                return False

            # Calculate wait time for next refill
            async with self.lock:
                await self._refill()
                tokens_needed = max(0, count - self.tokens)
                wait_time = min(tokens_needed / self.refill_rate, 1.0)

            await asyncio.sleep(wait_time)

    async def get_available_tokens(self) -> int:
        """Get current number of available tokens."""
        async with self.lock:
            await self._refill()
            return int(self.tokens)

    async def _refill(self) -> None:
        """Refill bucket based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        if elapsed > 0:
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now

    def get_status(self) -> dict[str, float]:
        """Get bucket status."""
        return {
            "capacity": self.capacity,
            "current_tokens": self.tokens,
            "refill_rate": self.refill_rate,
            "utilization": (self.capacity - self.tokens) / self.capacity,
        }


class GitHubAPIResourceManager(RateLimitStrategy):
    """GitHub API rate limit manager with priority scheduling.

    Manages multiple API resources (core, search, etc.) with intelligent
    token allocation and backpressure mechanisms.
    """

    def __init__(
        self,
        core_limit: int = 5000,
        search_limit: int = 30,
        graphql_limit: int = 5000,
        buffer_percentage: float = 0.1,
        priority_weights: dict[str, float] | None = None,
    ):
        """Initialize resource manager.

        Args:
            core_limit: Core API hourly limit
            search_limit: Search API hourly limit
            graphql_limit: GraphQL API hourly limit
            buffer_percentage: Reserve this percentage as buffer
            priority_weights: Weights for priority-based allocation
        """
        self.buffer_percentage = buffer_percentage

        # Calculate effective limits with buffer
        core_effective = int(core_limit * (1 - buffer_percentage))
        search_effective = int(search_limit * (1 - buffer_percentage))
        graphql_effective = int(graphql_limit * (1 - buffer_percentage))

        # Initialize token buckets for each resource
        # Refill rates are per hour / 3600 seconds
        self.buckets = {
            "core": TokenBucket(
                capacity=core_effective, refill_rate=core_effective / 3600.0
            ),
            "search": TokenBucket(
                capacity=search_effective, refill_rate=search_effective / 3600.0
            ),
            "graphql": TokenBucket(
                capacity=graphql_effective, refill_rate=graphql_effective / 3600.0
            ),
        }

        # Priority weights for resource allocation
        self.priority_weights = priority_weights or {
            "critical": 1.0,
            "high": 0.8,
            "normal": 0.6,
            "low": 0.3,
        }

        # Track actual API limits from GitHub responses
        self.api_limits: dict[str, dict[str, Any]] = {}
        self.last_limit_update: dict[str, float] = {}

        # Request queue for priority scheduling
        self.request_queues: dict[str, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in self.priority_weights
        }

        # Background task for processing priority queue
        self._queue_processor_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the resource manager background tasks."""
        if self._queue_processor_task is None:
            self._queue_processor_task = asyncio.create_task(
                self._process_priority_queues()
            )

    async def stop(self) -> None:
        """Stop the resource manager background tasks."""
        self._shutdown_event.set()
        if self._queue_processor_task:
            try:
                await asyncio.wait_for(self._queue_processor_task, timeout=5.0)
            except TimeoutError:
                self._queue_processor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._queue_processor_task
            self._queue_processor_task = None

    async def _process_priority_queues(self) -> None:
        """Background task to process priority-based request queues."""
        try:
            while not self._shutdown_event.is_set():
                # Process queues in priority order
                processed = False

                for priority in sorted(
                    self.priority_weights.keys(),
                    key=lambda p: self.priority_weights[p],
                    reverse=True,
                ):
                    queue = self.request_queues[priority]

                    if not queue.empty():
                        try:
                            # Get request from queue (non-blocking)
                            resource, count, future = queue.get_nowait()

                            # Try to acquire tokens
                            if await self.buckets[resource].acquire(count):
                                future.set_result(True)
                                processed = True
                            else:
                                # Put back in queue if tokens not available
                                await queue.put((resource, count, future))

                        except asyncio.QueueEmpty:
                            continue
                        except Exception as e:
                            logger.error(f"Error processing priority queue: {e}")

                # Sleep briefly if no requests processed
                if not processed:
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Priority queue processor cancelled")
        except Exception as e:
            logger.error(f"Error in priority queue processor: {e}")

    async def acquire_tokens(self, resource: str, count: int = 1) -> bool:
        """Acquire rate limit tokens immediately.

        Args:
            resource: Resource identifier (core, search, graphql)
            count: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise
        """
        if resource not in self.buckets:
            logger.warning(f"Unknown resource type: {resource}")
            return False

        return await self.buckets[resource].acquire(count)

    async def acquire_tokens_with_priority(
        self,
        resource: str,
        priority: str = "normal",
        count: int = 1,
        timeout: float | None = None,
    ) -> bool:
        """Acquire tokens with priority-based queuing.

        Args:
            resource: Resource identifier
            priority: Request priority (critical, high, normal, low)
            count: Number of tokens to acquire
            timeout: Maximum time to wait

        Returns:
            True if tokens acquired, False if timeout
        """
        if resource not in self.buckets:
            logger.warning(f"Unknown resource type: {resource}")
            return False

        if priority not in self.priority_weights:
            logger.warning(f"Unknown priority: {priority}, using 'normal'")
            priority = "normal"

        # Ensure queue processor is running
        await self.start()

        # For immediate acquisition, try direct first
        if await self.buckets[resource].acquire(count):
            return True

        # If immediate acquisition fails, use priority queue
        future: asyncio.Future[bool] = asyncio.Future()
        await self.request_queues[priority].put((resource, count, future))

        try:
            if timeout:
                await asyncio.wait_for(future, timeout=timeout)
            else:
                await future
            return future.result()
        except TimeoutError:
            logger.warning(
                f"Token acquisition timeout for {resource} (priority: {priority})"
            )
            return False
        except Exception as e:
            logger.error(f"Error acquiring tokens: {e}")
            return False

    async def get_available_tokens(self, resource: str) -> int:
        """Get available rate limit tokens.

        Args:
            resource: Resource identifier

        Returns:
            Number of available tokens
        """
        if resource not in self.buckets:
            return 0

        return await self.buckets[resource].get_available_tokens()

    async def wait_for_tokens(
        self, resource: str, count: int = 1, timeout: float | None = None
    ) -> bool:
        """Wait until tokens are available.

        Args:
            resource: Resource identifier
            count: Number of tokens needed
            timeout: Maximum time to wait in seconds

        Returns:
            True if tokens acquired, False if timeout
        """
        if resource not in self.buckets:
            return False

        return await self.buckets[resource].wait_for_tokens(count, timeout)

    async def update_limit_info(
        self, resource: str, limit: int, remaining: int, reset_time: datetime
    ) -> None:
        """Update rate limit information from API response.

        Args:
            resource: Resource identifier
            limit: Total rate limit
            remaining: Remaining requests
            reset_time: When the limit resets
        """
        self.api_limits[resource] = {
            "limit": limit,
            "remaining": remaining,
            "reset_time": reset_time,
            "updated_at": datetime.now(UTC),
        }
        self.last_limit_update[resource] = time.time()

        # Adjust token bucket if actual limit differs significantly
        if resource in self.buckets:
            bucket = self.buckets[resource]
            effective_limit = int(limit * (1 - self.buffer_percentage))

            # Update bucket capacity if limit changed significantly
            if abs(bucket.capacity - effective_limit) > (limit * 0.1):
                logger.info(
                    f"Updating {resource} bucket capacity: "
                    f"{bucket.capacity} -> {effective_limit}"
                )
                async with bucket.lock:
                    bucket.capacity = effective_limit
                    bucket.refill_rate = effective_limit / 3600.0
                    # Adjust current tokens proportionally
                    bucket.tokens = min(bucket.tokens, effective_limit)

        logger.debug(
            f"Updated {resource} limits: {remaining}/{limit} "
            f"(resets at {reset_time.isoformat()})"
        )

    def get_resource_status(self) -> dict[str, dict]:
        """Get status of all managed resources.

        Returns:
            Dictionary with status of each resource
        """
        status = {}

        for resource, bucket in self.buckets.items():
            bucket_status: dict[str, Any] = bucket.get_status()

            # Add API limit info if available
            if resource in self.api_limits:
                limit_info = self.api_limits[resource]
                reset_time = limit_info["reset_time"]
                updated_at = limit_info["updated_at"]
                bucket_status.update(
                    {
                        "api_limit": limit_info["limit"],
                        "api_remaining": limit_info["remaining"],
                        "api_reset_time": (
                            reset_time.isoformat()
                            if isinstance(reset_time, datetime)
                            else str(reset_time)
                        ),
                        "last_updated": (
                            updated_at.isoformat()
                            if isinstance(updated_at, datetime)
                            else str(updated_at)
                        ),
                    }
                )

            # Add queue status
            if resource in ["core", "search", "graphql"]:  # Only for known resources
                queue_sizes = {
                    f"{priority}_queue_size": self.request_queues[priority].qsize()
                    for priority in self.priority_weights
                }
                bucket_status.update(queue_sizes)

            status[resource] = bucket_status

        return status

    def estimate_wait_time(self, resource: str, tokens_needed: int) -> float:
        """Estimate wait time for acquiring tokens.

        Args:
            resource: Resource identifier
            tokens_needed: Number of tokens needed

        Returns:
            Estimated wait time in seconds
        """
        if resource not in self.buckets:
            return float("inf")

        bucket = self.buckets[resource]
        current_tokens = int(bucket.tokens)

        if current_tokens >= tokens_needed:
            return 0.0

        tokens_to_wait = tokens_needed - current_tokens
        return tokens_to_wait / bucket.refill_rate

    async def get_optimal_batch_size(self, resource: str) -> int:
        """Get optimal batch size based on current token availability.

        Args:
            resource: Resource identifier

        Returns:
            Recommended batch size
        """
        available = await self.get_available_tokens(resource)

        # Reserve some tokens for other operations
        usable = max(1, int(available * 0.8))

        # Cap at reasonable batch sizes
        if resource == "search":
            return min(usable, 10)  # Search API is more limited
        else:
            return min(usable, 50)  # Core API can handle larger batches
