"""PR Discovery Engine - main orchestrator for the discovery process.

This module implements the main discovery engine that coordinates all discovery
components to efficiently process multiple repositories with parallel processing,
state change detection, and data synchronization.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.repository import RepositoryRepository

from .interfaces import (
    CacheStrategy,
    CheckDiscoveryStrategy,
    DataSynchronizationStrategy,
    DiscoveryConfig,
    DiscoveryError,
    DiscoveryOrchestrator,
    DiscoveryPriority,
    EventPublisher,
    PRDiscoveryResult,
    PRDiscoveryStrategy,
    RateLimitStrategy,
    StateChangeDetector,
    SynchronizationResult,
)
from .state_manager import RepositoryStateManager

logger = logging.getLogger(__name__)


class DiscoveryState:
    """Internal state for tracking discovery progress."""

    def __init__(self) -> None:
        """Initialize discovery state tracking."""
        self.repositories_processed: int = 0
        self.repositories_total: int = 0
        self.repositories_successful: int = 0
        self.repositories_failed: int = 0
        self.prs_discovered: int = 0
        self.checks_discovered: int = 0
        self.state_changes_detected: int = 0
        self.errors: list[DiscoveryError] = []
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.batch_stats: list[dict[str, Any]] = []

    @property
    def processing_time(self) -> float:
        """Calculate total processing time in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.repositories_total == 0:
            return 0.0
        return (self.repositories_processed / self.repositories_total) * 100

    def add_batch_stats(self, batch_num: int, stats: dict[str, Any]) -> None:
        """Add statistics for a completed batch."""
        stats_entry = {
            "batch_number": batch_num,
            "timestamp": datetime.now(UTC).isoformat(),
            **stats,
        }
        self.batch_stats.append(stats_entry)


class ConcurrencyController:
    """Controls concurrent processing of repositories."""

    def __init__(self, max_concurrent: int):
        """Initialize concurrency controller.

        Args:
            max_concurrent: Maximum concurrent operations
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: set = set()
        self.max_concurrent = max_concurrent

    async def run_with_limit(self, coro: Coroutine, task_name: str = "task") -> Any:
        """Run coroutine with concurrency limit.

        Args:
            coro: Coroutine to run
            task_name: Name for tracking

        Returns:
            Result of coroutine
        """
        async with self.semaphore:
            task = asyncio.create_task(coro)
            task.set_name(task_name)
            self.active_tasks.add(task)

            try:
                result = await task
                return result
            except Exception as e:
                logger.error(f"Task {task_name} failed: {e}")
                raise
            finally:
                self.active_tasks.discard(task)

    def get_stats(self) -> dict[str, Any]:
        """Get concurrency statistics."""
        return {
            "max_concurrent": self.max_concurrent,
            "available_slots": self.semaphore._value,
            "active_tasks": len(self.active_tasks),
            "task_names": [task.get_name() for task in self.active_tasks],
        }


class PRDiscoveryEngine(DiscoveryOrchestrator):
    """Main discovery engine orchestrating the entire discovery process.

    Coordinates parallel repository processing, state change detection,
    data synchronization, and event publishing with comprehensive
    error handling and performance monitoring.
    """

    def __init__(
        self,
        config: DiscoveryConfig,
        pr_discovery: PRDiscoveryStrategy,
        check_discovery: CheckDiscoveryStrategy,
        state_detector: StateChangeDetector,
        data_sync: DataSynchronizationStrategy,
        rate_limiter: RateLimitStrategy,
        cache: CacheStrategy,
        event_publisher: EventPublisher,
        repository_repo: RepositoryRepository,
        pr_repository: PullRequestRepository,
        check_repository: CheckRunRepository,
        state_manager: RepositoryStateManager | None = None,
    ):
        """Initialize discovery engine with all dependencies.

        Args:
            config: Discovery configuration
            pr_discovery: PR discovery strategy
            check_discovery: Check discovery strategy
            state_detector: State change detector
            data_sync: Data synchronization strategy
            rate_limiter: Rate limiting strategy
            cache: Cache strategy
            event_publisher: Event publisher
            repository_repo: Repository repository
            pr_repository: Pull request repository
            check_repository: Check run repository
            state_manager: Optional state manager (will create if not provided)
        """
        self.config = config
        self.pr_discovery = pr_discovery
        self.check_discovery = check_discovery
        self.state_detector = state_detector
        self.data_sync = data_sync
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.event_publisher = event_publisher
        self.repository_repo = repository_repo
        self.pr_repository = pr_repository
        self.check_repository = check_repository

        # State manager
        if state_manager is None:
            # Create state manager using the provided repositories
            self.state_manager = RepositoryStateManager(
                pr_repository=self.pr_repository,
                check_repository=self.check_repository,
                cache=self.cache,
            )
        else:
            self.state_manager = state_manager

        # Concurrency control
        self.concurrency_controller = ConcurrencyController(
            config.max_concurrent_repositories
        )

        # Current discovery state
        self.current_state = DiscoveryState()
        self.last_cycle_timestamp: datetime | None = None

        # Performance metrics
        self.metrics = {
            "total_cycles": 0,
            "total_repositories": 0,
            "total_prs": 0,
            "total_checks": 0,
            "total_errors": 0,
            "avg_cycle_time": 0.0,
            "cache_hit_rate": 0.0,
        }

    async def run_discovery_cycle(
        self, repository_ids: list[uuid.UUID]
    ) -> list[PRDiscoveryResult]:
        """Run a complete discovery cycle for repositories.

        Args:
            repository_ids: List of repository IDs to process

        Returns:
            List of discovery results
        """
        if not repository_ids:
            logger.info("No repositories to process")
            return []

        # Initialize discovery state
        self.current_state = DiscoveryState()
        self.current_state.repositories_total = len(repository_ids)
        self.current_state.start_time = datetime.now(UTC)

        logger.info(
            f"Starting discovery cycle for {len(repository_ids)} repositories "
            f"(max concurrent: {self.config.max_concurrent_repositories})"
        )

        try:
            # Step 1: Sort repositories by priority
            sorted_repository_ids = await self._sort_by_priority(repository_ids)

            # Step 2: Process repositories in batches
            all_results = []
            batch_size = max(1, self.config.max_concurrent_repositories)

            for i in range(0, len(sorted_repository_ids), batch_size):
                batch = sorted_repository_ids[i : i + batch_size]
                batch_num = (i // batch_size) + 1

                logger.info(f"Processing batch {batch_num}: {len(batch)} repositories")

                # Process batch
                batch_results = await self._process_batch(batch, batch_num)
                all_results.extend(batch_results)

                # Update progress
                self.current_state.repositories_processed += len(batch)

                # Log batch completion
                successful_in_batch = len([r for r in batch_results if not r.errors])
                logger.info(
                    f"Batch {batch_num} completed: {successful_in_batch}/{len(batch)} "
                    f"successful (Progress: "
                    f"{self.current_state.progress_percentage:.1f}%)"
                )

            # Step 3: Detect state changes
            logger.info("Detecting state changes...")
            state_changes = await self._detect_all_state_changes(all_results)
            self.current_state.state_changes_detected = len(state_changes)

            # Step 4: Synchronize data
            logger.info("Synchronizing data with database...")
            sync_result = await self.data_sync.synchronize(all_results, state_changes)

            # Step 5: Publish events
            logger.info("Publishing discovery events...")
            await self._publish_discovery_events(all_results, state_changes)

            # Step 6: Update metrics
            await self._update_metrics(all_results)

            # Mark cycle complete
            self.current_state.end_time = datetime.now(UTC)
            self.last_cycle_timestamp = self.current_state.end_time

            # Log summary
            self._log_cycle_summary(all_results, sync_result)

            return all_results

        except Exception as e:
            self.current_state.end_time = datetime.now(UTC)
            logger.error(f"Discovery cycle failed: {e}")

            error = DiscoveryError(
                error_type="discovery_cycle_error",
                message=f"Discovery cycle failed: {e!s}",
                context={"repository_count": len(repository_ids)},
                timestamp=datetime.now(UTC),
                recoverable=True,
            )
            self.current_state.errors.append(error)

            raise

    async def _sort_by_priority(
        self, repository_ids: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        """Sort repositories by discovery priority.

        Args:
            repository_ids: Repository IDs to sort

        Returns:
            Sorted repository IDs (highest priority first)
        """
        if not self.config.priority_scheduling:
            return repository_ids

        logger.debug("Determining repository priorities...")

        try:
            # Get priorities for all repositories
            priority_tasks = [
                self.pr_discovery.get_priority(repo_id) for repo_id in repository_ids
            ]

            priorities = await asyncio.gather(*priority_tasks, return_exceptions=True)

            # Create priority tuples, handling exceptions
            repo_priority_pairs = []
            for repo_id, priority_result in zip(
                repository_ids, priorities, strict=False
            ):
                if isinstance(priority_result, BaseException):
                    logger.warning(
                        f"Error getting priority for {repo_id}: {priority_result}"
                    )
                    priority = DiscoveryPriority.NORMAL  # Default
                else:
                    # priority_result should be DiscoveryPriority at this point
                    priority = priority_result

                repo_priority_pairs.append((priority.value, repo_id))

            # Sort by priority value (lower value = higher priority)
            repo_priority_pairs.sort(key=lambda x: x[0])

            sorted_ids = [repo_id for _, repo_id in repo_priority_pairs]

            # Log priority distribution
            priority_counts: dict[str, int] = {}
            for priority_val, _ in repo_priority_pairs:
                priority_name = DiscoveryPriority(priority_val).name
                priority_counts[priority_name] = (
                    priority_counts.get(priority_name, 0) + 1
                )

            logger.info(f"Repository priority distribution: {priority_counts}")

            return sorted_ids

        except Exception as e:
            logger.warning(f"Error sorting by priority: {e}")
            return repository_ids

    async def _process_batch(
        self, repository_batch: list[uuid.UUID], batch_num: int
    ) -> list[PRDiscoveryResult]:
        """Process a batch of repositories concurrently.

        Args:
            repository_batch: Repository IDs to process
            batch_num: Batch number for logging

        Returns:
            List of discovery results
        """
        batch_start_time = time.time()

        # Create processing tasks for each repository
        tasks = []
        for repo_id in repository_batch:
            task_coro = self.process_repository(repo_id)
            task_name = f"repo-{str(repo_id)[:8]}"

            limited_task = self.concurrency_controller.run_with_limit(
                task_coro, task_name
            )
            tasks.append(limited_task)

        # Execute all tasks with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        batch_results = []
        successful_count = 0
        error_count = 0

        for repo_id, result in zip(repository_batch, results, strict=False):
            if isinstance(result, BaseException):
                logger.error(f"Repository {repo_id} processing failed: {result}")

                # Create error result
                error_result = PRDiscoveryResult(
                    repository_id=repo_id,
                    repository_url="unknown",
                    discovered_prs=[],
                    discovery_timestamp=datetime.now(UTC),
                    api_calls_used=0,
                    cache_hits=0,
                    cache_misses=0,
                    processing_time_ms=0.0,
                    errors=[
                        DiscoveryError(
                            error_type="repository_processing_error",
                            message=str(result),
                            context={"repository_id": str(repo_id)},
                            timestamp=datetime.now(UTC),
                            recoverable=True,
                        )
                    ],
                )
                batch_results.append(error_result)
                error_count += 1
                self.current_state.repositories_failed += 1
            else:
                # result is PRDiscoveryResult at this point
                batch_results.append(result)
                if not result.errors:
                    successful_count += 1
                    self.current_state.repositories_successful += 1
                else:
                    self.current_state.repositories_failed += 1
                    error_count += 1

                # Update discovery stats
                self.current_state.prs_discovered += len(result.discovered_prs)
                self.current_state.checks_discovered += sum(
                    len(pr.check_runs) for pr in result.discovered_prs
                )

        # Record batch statistics
        batch_time = time.time() - batch_start_time
        batch_stats = {
            "repositories_count": len(repository_batch),
            "successful_count": successful_count,
            "error_count": error_count,
            "processing_time_seconds": batch_time,
            "total_prs": sum(len(r.discovered_prs) for r in batch_results),
            "total_checks": sum(
                sum(len(pr.check_runs) for pr in r.discovered_prs)
                for r in batch_results
            ),
            "total_api_calls": sum(r.api_calls_used for r in batch_results),
            "total_cache_hits": sum(r.cache_hits for r in batch_results),
        }

        self.current_state.add_batch_stats(batch_num, batch_stats)

        logger.info(
            f"Batch {batch_num} processing completed in {batch_time:.2f}s: "
            f"{successful_count}/{len(repository_batch)} successful, "
            f"{batch_stats['total_prs']} PRs, {batch_stats['total_checks']} checks"
        )

        return batch_results

    async def process_repository(self, repository_id: uuid.UUID) -> PRDiscoveryResult:
        """Process a single repository.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Discovery result for the repository
        """
        try:
            # Load repository information
            repository = await self.repository_repo.get_by_id(repository_id)
            if not repository:
                raise ValueError(f"Repository {repository_id} not found")

            if not repository.is_active:
                raise ValueError(f"Repository {repository_id} is not active")

            logger.debug(f"Processing repository: {repository.name} ({repository_id})")

            # Check rate limits before proceeding
            core_tokens = await self.rate_limiter.get_available_tokens("core")
            if core_tokens < 10:  # Reserve minimum tokens
                await self.rate_limiter.wait_for_tokens("core", 10, timeout=30)

            # Discover PRs
            discovery_result = await self.pr_discovery.discover_prs(
                repository_id=repository_id,
                repository_url=repository.url,
                since=None,  # Could be made configurable
                max_prs=self.config.max_prs_per_repository,
            )

            # Enhance PRs with check runs
            if discovery_result.discovered_prs:
                logger.debug(
                    f"Discovering check runs for "
                    f"{len(discovery_result.discovered_prs)} PRs"
                )

                check_runs_map = await self.check_discovery.batch_discover_checks(
                    discovery_result.discovered_prs, repository.url
                )

                # Assign check runs to PRs
                for pr in discovery_result.discovered_prs:
                    pr.check_runs = check_runs_map.get(pr.pr_number, [])

                # Update check count in result
                total_checks = sum(
                    len(pr.check_runs) for pr in discovery_result.discovered_prs
                )
                logger.debug(f"Discovered {total_checks} check runs total")

            # Update repository last polled timestamp
            await self.repository_repo.update_last_polled(repository_id)

            # Reset failure count on successful processing
            if repository.failure_count > 0:
                await self.repository_repo.reset_failure_count(repository_id)

            logger.debug(
                f"Repository {repository.name} processing completed: "
                f"{len(discovery_result.discovered_prs)} PRs, "
                f"{len(discovery_result.errors)} errors"
            )

            return discovery_result

        except Exception as e:
            logger.error(f"Error processing repository {repository_id}: {e}")

            # Increment failure count
            try:
                await self.repository_repo.increment_failure_count(
                    repository_id, str(e)
                )
            except Exception as repo_error:
                logger.error(f"Error updating repository failure count: {repo_error}")

            # Return error result
            return PRDiscoveryResult(
                repository_id=repository_id,
                repository_url="unknown",
                discovered_prs=[],
                discovery_timestamp=datetime.now(UTC),
                api_calls_used=0,
                cache_hits=0,
                cache_misses=0,
                processing_time_ms=0.0,
                errors=[
                    DiscoveryError(
                        error_type="repository_processing_error",
                        message=str(e),
                        context={"repository_id": str(repository_id)},
                        timestamp=datetime.now(UTC),
                        recoverable=True,
                    )
                ],
            )

    async def _detect_all_state_changes(
        self, discovery_results: list[PRDiscoveryResult]
    ) -> list:
        """Detect state changes for all discovery results.

        Args:
            discovery_results: All discovery results

        Returns:
            List of detected state changes
        """
        all_changes = []

        # Load current states for all repositories
        repository_ids = [result.repository_id for result in discovery_results]
        current_states = await self.state_manager.batch_get_repository_states(
            repository_ids
        )

        # Detect changes for each repository
        for result in discovery_results:
            try:
                current_state = current_states.get(result.repository_id)
                if current_state:
                    changes = await self.state_detector.detect_changes(
                        result, current_state
                    )
                    all_changes.extend(changes)

            except Exception as e:
                logger.error(
                    f"Error detecting changes for repository "
                    f"{result.repository_id}: {e}"
                )

        logger.info(
            f"Detected {len(all_changes)} state changes across all repositories"
        )
        return all_changes

    async def _publish_discovery_events(
        self, discovery_results: list[PRDiscoveryResult], state_changes: list
    ) -> None:
        """Publish events for discovery completion and state changes.

        Args:
            discovery_results: All discovery results
            state_changes: All detected state changes
        """
        try:
            # Publish discovery completion
            await self.event_publisher.publish_discovery_complete(discovery_results)

            # Publish individual state changes
            for change in state_changes:
                await self.event_publisher.publish_state_change(change)

            # Publish failed check events
            for result in discovery_results:
                for pr in result.discovered_prs:
                    for check in pr.check_runs:
                        if check.is_failed:
                            await self.event_publisher.publish_failed_check(
                                result.repository_id, pr.pr_number, check
                            )

        except Exception as e:
            logger.error(f"Error publishing discovery events: {e}")

    async def _update_metrics(self, discovery_results: list[PRDiscoveryResult]) -> None:
        """Update performance metrics.

        Args:
            discovery_results: All discovery results
        """
        try:
            self.metrics["total_cycles"] += 1
            self.metrics["total_repositories"] += len(discovery_results)

            total_prs = sum(len(result.discovered_prs) for result in discovery_results)
            total_checks = sum(
                sum(len(pr.check_runs) for pr in result.discovered_prs)
                for result in discovery_results
            )
            total_errors = sum(len(result.errors) for result in discovery_results)

            self.metrics["total_prs"] += total_prs
            self.metrics["total_checks"] += total_checks
            self.metrics["total_errors"] += total_errors

            # Calculate average cycle time
            if self.current_state.processing_time > 0:
                total_time = (
                    self.metrics["avg_cycle_time"] * (self.metrics["total_cycles"] - 1)
                    + self.current_state.processing_time
                )
                self.metrics["avg_cycle_time"] = (
                    total_time / self.metrics["total_cycles"]
                )

            # Calculate cache hit rate
            total_requests = sum(
                result.cache_hits + result.cache_misses for result in discovery_results
            )
            total_hits = sum(result.cache_hits for result in discovery_results)

            if total_requests > 0:
                current_hit_rate = total_hits / total_requests
                # Weighted average with previous cycles
                weight = 0.7  # Give more weight to recent performance
                self.metrics["cache_hit_rate"] = (
                    weight * current_hit_rate
                    + (1 - weight) * self.metrics["cache_hit_rate"]
                )

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def _log_cycle_summary(
        self,
        discovery_results: list[PRDiscoveryResult],
        sync_result: SynchronizationResult,
    ) -> None:
        """Log summary of discovery cycle.

        Args:
            discovery_results: All discovery results
            sync_result: Synchronization result
        """
        cycle_time = self.current_state.processing_time

        # Calculate totals
        total_prs = sum(len(result.discovered_prs) for result in discovery_results)
        total_checks = sum(
            sum(len(pr.check_runs) for pr in result.discovered_prs)
            for result in discovery_results
        )
        total_api_calls = sum(result.api_calls_used for result in discovery_results)
        total_cache_hits = sum(result.cache_hits for result in discovery_results)
        total_cache_requests = sum(
            result.cache_hits + result.cache_misses for result in discovery_results
        )

        cache_hit_rate = (
            (total_cache_hits / total_cache_requests * 100)
            if total_cache_requests > 0
            else 0
        )

        logger.info(
            f"Discovery cycle completed in {cycle_time:.2f}s:\n"
            f"  Repositories: {self.current_state.repositories_successful}/"
            f"{self.current_state.repositories_total} successful\n"
            f"  PRs discovered: {total_prs}\n"
            f"  Check runs discovered: {total_checks}\n"
            f"  State changes: {self.current_state.state_changes_detected}\n"
            f"  API calls: {total_api_calls}\n"
            f"  Cache hit rate: {cache_hit_rate:.1f}%\n"
            f"  DB operations: {sync_result.prs_created} PRs created, "
            f"{sync_result.prs_updated} PRs updated, "
            f"{sync_result.checks_created} checks created, "
            f"{sync_result.checks_updated} checks updated\n"
            f"  Errors: {len(self.current_state.errors)}"
        )

    async def get_discovery_status(self) -> dict[str, Any]:
        """Get current discovery status.

        Returns:
            Status information including progress and metrics
        """
        # Check if discovery is currently running
        is_running = (
            self.current_state.start_time is not None
            and self.current_state.end_time is None
        )

        # Get rate limit status
        rate_limits = {}
        with contextlib.suppress(Exception):
            rate_limits = {
                "core_remaining": await self.rate_limiter.get_available_tokens("core"),
                "search_remaining": await self.rate_limiter.get_available_tokens(
                    "search"
                ),
            }

        # Get cache stats
        cache_stats = {}
        try:
            if hasattr(self.cache, "get_stats"):
                cache_stats = self.cache.get_stats()
        except Exception as e:
            logger.debug(f"Failed to retrieve cache statistics: {e}")

        # Get concurrency stats
        concurrency_stats = self.concurrency_controller.get_stats()

        status = {
            "status": "running"
            if is_running
            else ("healthy" if not self._is_degraded() else "degraded"),
            "current_cycle": {
                "is_running": is_running,
                "repositories_processed": self.current_state.repositories_processed,
                "repositories_total": self.current_state.repositories_total,
                "progress_percentage": self.current_state.progress_percentage,
                "prs_discovered": self.current_state.prs_discovered,
                "checks_discovered": self.current_state.checks_discovered,
                "state_changes_detected": self.current_state.state_changes_detected,
                "processing_time_seconds": self.current_state.processing_time,
                "errors_count": len(self.current_state.errors),
            },
            "overall_metrics": self.metrics,
            "rate_limits": rate_limits,
            "cache_stats": cache_stats,
            "concurrency": concurrency_stats,
            "last_cycle_completed": self.last_cycle_timestamp.isoformat()
            if self.last_cycle_timestamp
            else None,
            "recent_errors": [
                {
                    "type": e.error_type,
                    "message": e.message,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in self.current_state.errors[-5:]  # Last 5 errors
            ],
            "batch_stats": self.current_state.batch_stats[-10:],  # Last 10 batches
        }

        return status

    def _is_degraded(self) -> bool:
        """Check if discovery system is in degraded state."""
        # Check if error rate is too high
        recent_errors = len(
            [
                e
                for e in self.current_state.errors
                if (datetime.now(UTC) - e.timestamp).total_seconds() < 3600
            ]
        )

        return recent_errors > 10  # More than 10 errors in last hour
