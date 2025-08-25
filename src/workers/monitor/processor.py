"""Main PR Processor Orchestration for the PR Monitor Worker.

This module implements the main PRProcessor class that orchestrates the entire
PR discovery and processing workflow. It coordinates between discovery, change
detection, and synchronization components while managing performance, error
handling, and monitoring.

The processor supports:
- Repository-level processing with intelligent parallelization
- Full and incremental processing modes
- Comprehensive error handling and recovery mechanisms
- Performance monitoring and metrics collection
- Graceful shutdown and resource cleanup
- Dry-run mode for testing and validation
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import psutil
from sqlalchemy.ext.asyncio import AsyncSession

from ...cache.cache_manager import CacheManager
from ...github.client import GitHubClient
from ...github.exceptions import (
    GitHubNotFoundError,
)
from ...repositories import RepositoryRepository
from .change_detection import StateChangeDetector
from .discovery import (
    CheckRunDiscoveryEngine,
    DiscoveryConfig,
    PRDiscoveryEngine,
    RepositoryContext,
)
from .models import (
    CheckRunDiscovery,
    DiscoveryResult,
    ProcessingMetrics,
    StateChangeEvent,
    SyncOperation,
)
from .synchronization import DataSynchronizer

logger = logging.getLogger(__name__)


class ProcessingMode(str, Enum):
    """Processing modes for the PR processor."""

    FULL = "full"  # Process all repositories regardless of last check time
    INCREMENTAL = "incremental"  # Only process repositories with recent activity
    DRY_RUN = "dry_run"  # Execute discovery and change detection only


class ProcessingPhase(str, Enum):
    """Processing phases for orchestration."""

    INITIALIZATION = "initialization"
    DISCOVERY = "discovery"
    CHANGE_DETECTION = "change_detection"
    SYNCHRONIZATION = "synchronization"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessorConfig:
    """Configuration for the PR processor orchestration."""

    # Concurrency limits
    max_concurrent_repos: int = 10
    max_concurrent_api_calls: int = 50
    max_concurrent_check_discoveries: int = 20

    # Performance tuning
    batch_size: int = 25
    api_timeout: int = 30
    db_batch_size: int = 100
    memory_limit_mb: int = 2048

    # Processing behavior
    incremental_window_hours: int = 24
    enable_dry_run: bool = False
    stop_on_first_error: bool = False
    enable_recovery_mode: bool = True

    # Monitoring and debugging
    enable_metrics: bool = True
    enable_detailed_logging: bool = False
    log_level: str = "INFO"
    metrics_collection_interval: int = 10

    # Resource management
    max_processing_time_minutes: int = 30
    resource_check_interval: int = 5
    auto_cleanup: bool = True

    def validate(self) -> None:
        """Validate configuration parameters."""
        if self.max_concurrent_repos < 1:
            raise ValueError("max_concurrent_repos must be positive")

        if self.max_concurrent_api_calls < self.max_concurrent_repos:
            raise ValueError("max_concurrent_api_calls must be >= max_concurrent_repos")

        if self.batch_size < 1 or self.batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000")

        if self.incremental_window_hours < 1:
            raise ValueError("incremental_window_hours must be positive")

        if self.memory_limit_mb < 256:
            raise ValueError("memory_limit_mb must be at least 256MB")


@dataclass
class ProcessingSession:
    """Context for a processing session with metrics and state tracking."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: ProcessingMode = ProcessingMode.INCREMENTAL
    phase: ProcessingPhase = ProcessingPhase.INITIALIZATION
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    # Repository tracking
    total_repositories: int = 0
    processed_repositories: int = 0
    failed_repositories: int = 0
    skipped_repositories: int = 0

    # Processing results
    total_prs_discovered: int = 0
    total_check_runs_discovered: int = 0
    total_state_changes: int = 0
    total_sync_operations: int = 0

    # Error tracking
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recovery_attempts: int = 0

    # Performance metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    processing_rate_repos_per_minute: float = 0.0

    # Component metrics
    discovery_metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)
    aggregated_metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)

    @property
    def duration_seconds(self) -> float:
        """Get processing duration in seconds."""
        end_time = self.completed_at or datetime.now(UTC)
        return (end_time - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        """Calculate repository processing success rate."""
        if self.total_repositories == 0:
            return 100.0
        return (self.processed_repositories / self.total_repositories) * 100

    @property
    def is_completed(self) -> bool:
        """Check if session is completed."""
        return self.phase in (ProcessingPhase.COMPLETED, ProcessingPhase.FAILED)

    def update_phase(self, phase: ProcessingPhase) -> None:
        """Update processing phase with timestamp."""
        self.phase = phase
        if phase in (ProcessingPhase.COMPLETED, ProcessingPhase.FAILED):
            self.completed_at = datetime.now(UTC)

    def add_error(self, error: str) -> None:
        """Add error to tracking."""
        self.errors.append(f"[{datetime.now(UTC).isoformat()}] {error}")
        logger.error(error)

    def add_warning(self, warning: str) -> None:
        """Add warning to tracking."""
        self.warnings.append(f"[{datetime.now(UTC).isoformat()}] {warning}")
        logger.warning(warning)


@dataclass
class RepositoryProcessingResult:
    """Result of processing a single repository."""

    repository_id: uuid.UUID
    repository_name: str
    success: bool
    processing_time_seconds: float

    # Discovery results
    prs_discovered: int = 0
    check_runs_discovered: int = 0
    state_changes_detected: int = 0

    # Synchronization results
    sync_operation: SyncOperation | None = None
    sync_success: bool = False

    # Error information
    error: str | None = None
    warning: str | None = None

    # Performance metrics
    api_calls_made: int = 0
    cache_hits: int = 0
    memory_peak_mb: float = 0.0

    def __str__(self) -> str:
        """Return human-readable representation."""
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"RepositoryProcessingResult({self.repository_name}: {status}, "
            f"PRs={self.prs_discovered}, Checks={self.check_runs_discovered}, "
            f"Changes={self.state_changes_detected}, "
            f"Time={self.processing_time_seconds:.2f}s)"
        )


class PRProcessor:
    """Main orchestrator for PR discovery and processing workflow.

    The PRProcessor coordinates the entire monitoring pipeline:
    1. Repository discovery and prioritization
    2. PR and check run discovery from GitHub
    3. Change detection against stored state
    4. Database synchronization with transaction support
    5. Performance monitoring and error recovery

    Designed for high throughput and reliability with comprehensive
    error handling, resource management, and monitoring capabilities.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        session: AsyncSession,
        cache_manager: CacheManager,
        config: ProcessorConfig | None = None,
    ) -> None:
        """Initialize the PR processor.

        Args:
            github_client: GitHub API client for API interactions
            session: Database session for persistence operations
            cache_manager: Cache manager for performance optimization
            config: Processor configuration options
        """
        self.github_client = github_client
        self.session = session
        self.cache_manager = cache_manager
        self.config = config or ProcessorConfig()
        self.config.validate()

        # Initialize core components
        self._initialize_components()

        # Processing state
        self._current_session: ProcessingSession | None = None
        self._shutdown_requested = False
        self._resource_monitor_task: asyncio.Task[None] | None = None

        # Performance tracking
        self._start_time: float | None = None
        self._last_metrics_collection = time.time()
        self._repository_results: dict[uuid.UUID, RepositoryProcessingResult] = {}

        # Concurrency management
        self._repo_semaphore = asyncio.Semaphore(self.config.max_concurrent_repos)
        self._api_semaphore = asyncio.Semaphore(self.config.max_concurrent_api_calls)
        self._check_semaphore = asyncio.Semaphore(
            self.config.max_concurrent_check_discoveries
        )

        logger.info(f"PRProcessor initialized with config: {self.config}")

    def _initialize_components(self) -> None:
        """Initialize discovery, change detection, and synchronization components."""
        # Create discovery config from processor config
        discovery_config = DiscoveryConfig(
            per_page=min(100, self.config.batch_size),
            max_concurrent_repos=self.config.max_concurrent_repos,
            batch_size=self.config.batch_size,
            request_delay=0.1,  # Be respectful to GitHub API
        )

        # Initialize engines
        self.pr_discovery = PRDiscoveryEngine(
            self.github_client, self.cache_manager, discovery_config
        )

        self.check_discovery = CheckRunDiscoveryEngine(
            self.github_client, self.cache_manager, discovery_config
        )

        self.state_detector = StateChangeDetector(
            enable_detailed_logging=self.config.enable_detailed_logging
        )

        self.data_synchronizer = DataSynchronizer(
            self.session,
            batch_size=self.config.db_batch_size,
            enable_audit_log=self.config.enable_detailed_logging,
        )

        # Initialize repositories
        self.repo_repository = RepositoryRepository(self.session)

    async def process_repositories(
        self,
        repositories: list[uuid.UUID] | None = None,
        mode: ProcessingMode = ProcessingMode.INCREMENTAL,
        dry_run: bool | None = None,
    ) -> ProcessingSession:
        """Main entry point for bulk processing across multiple repositories.

        Args:
            repositories: List of repository IDs to process (None for all active)
            mode: Processing mode (full, incremental, or dry_run)
            dry_run: Enable dry-run mode (overrides config)

        Returns:
            Processing session with results and metrics
        """
        # Override config with parameter if provided
        if dry_run is not None:
            mode = ProcessingMode.DRY_RUN if dry_run else mode

        session = ProcessingSession(mode=mode)
        self._current_session = session
        self._start_time = time.time()

        try:
            logger.info(
                f"Starting bulk repository processing (mode={mode}, "
                f"session_id={session.session_id[:8]})"
            )

            # Start resource monitoring
            if self.config.enable_metrics:
                self._resource_monitor_task = asyncio.create_task(
                    self._monitor_resources()
                )

            # Phase 1: Initialize and discover repositories
            await self._phase_initialize_repositories(session, repositories)

            # Phase 2: Process repositories
            await self._phase_process_repositories(session)

            # Mark as completed
            session.update_phase(ProcessingPhase.COMPLETED)

            # Collect final metrics
            await self._collect_final_metrics(session)

            logger.info(
                f"Repository processing completed successfully: "
                f"{session.processed_repositories}/{session.total_repositories} "
                f"repositories processed in {session.duration_seconds:.1f}s"
            )

            return session

        except Exception as e:
            session.add_error(f"Processing failed with error: {e}")
            session.update_phase(ProcessingPhase.FAILED)
            logger.error(f"Repository processing failed: {e}", exc_info=True)

            # Attempt recovery if enabled
            if self.config.enable_recovery_mode and session.recovery_attempts < 2:
                logger.info("Attempting recovery from processing failure")
                session.recovery_attempts += 1
                try:
                    # Simplified recovery - just cleanup and report partial results
                    await self._phase_cleanup(session)
                    session.add_warning("Partial recovery completed")
                except Exception as recovery_error:
                    session.add_error(f"Recovery failed: {recovery_error}")

            raise

        finally:
            # Cleanup resources
            await self._cleanup_session(session)

    async def process_single_repository(
        self,
        repository_id: uuid.UUID,
        since: datetime | None = None,
        dry_run: bool | None = None,
    ) -> RepositoryProcessingResult:
        """Process a single repository with full orchestration.

        Args:
            repository_id: ID of repository to process
            since: Only process PRs modified since this datetime
            dry_run: Enable dry-run mode (no database changes)

        Returns:
            Processing result for the repository
        """
        start_time = time.time()
        dry_run = dry_run if dry_run is not None else self.config.enable_dry_run

        # Get repository information
        repo = await self.repo_repository.get_by_id(repository_id)
        if repo is None:
            raise ValueError(f"Repository {repository_id} not found")

        repo_name = repo.full_name or repo.name

        logger.info(
            f"Starting single repository processing: {repo_name} (dry_run={dry_run})"
        )

        result = RepositoryProcessingResult(
            repository_id=repository_id,
            repository_name=repo_name,
            success=False,
            processing_time_seconds=0.0,
        )

        try:
            async with self._api_semaphore:
                # Create repository context
                repo_context = RepositoryContext(
                    repository_id=repository_id,
                    repository_owner=repo.full_name.split("/")[0]
                    if repo.full_name
                    else repo.name,
                    repository_name=repo.full_name.split("/")[1]
                    if repo.full_name and "/" in repo.full_name
                    else repo.name,
                    last_updated=repo.last_polled_at,
                    processing_priority=1,
                )

                # Phase 1: Discovery
                (
                    discovered_prs,
                    check_runs,
                    discovery_metrics,
                ) = await self._coordinate_discovery(repo_context, since)

                result.prs_discovered = len(discovered_prs)
                result.check_runs_discovered = len(check_runs)
                result.api_calls_made = discovery_metrics.github_api_calls_made

                # Phase 2: Change Detection
                state_changes = await self._coordinate_change_detection(
                    discovered_prs, check_runs, repository_id
                )

                result.state_changes_detected = len(state_changes)

                # Phase 3: Synchronization (skip if dry run)
                if not dry_run:
                    sync_operation = await self._coordinate_synchronization(
                        discovered_prs, check_runs, state_changes
                    )
                    result.sync_operation = sync_operation
                    result.sync_success = sync_operation.is_successful

                result.success = True
                result.processing_time_seconds = time.time() - start_time

                logger.info(f"Repository processing completed: {repo_name} - {result}")

        except Exception as e:
            result.error = str(e)
            result.processing_time_seconds = time.time() - start_time
            logger.error(f"Failed to process repository {repo_name}: {e}")

            # Don't re-raise - return the result with error information

        return result

    async def _phase_initialize_repositories(
        self,
        session: ProcessingSession,
        repository_ids: list[uuid.UUID] | None,
    ) -> None:
        """Initialize repositories for processing."""
        session.update_phase(ProcessingPhase.INITIALIZATION)

        try:
            if repository_ids:
                # Load specific repositories
                repositories = []
                for repo_id in repository_ids:
                    repo = await self.repo_repository.get_by_id(repo_id)
                    if repo:
                        repositories.append(repo)
                    else:
                        session.add_warning(f"Repository {repo_id} not found")
            else:
                # Get repositories that need processing based on mode
                if session.mode == ProcessingMode.FULL:
                    repositories = await self.repo_repository.get_active_repositories()
                else:  # INCREMENTAL or DRY_RUN
                    repositories = (
                        await self.repo_repository.get_repositories_needing_poll()
                    )

            session.total_repositories = len(repositories)

            # Convert to repository contexts for processing
            self._repository_contexts = []
            for repo in repositories:
                if repo.full_name:
                    owner, name = repo.full_name.split("/", 1)
                else:
                    owner = name = repo.name

                context = RepositoryContext(
                    repository_id=repo.id,
                    repository_owner=owner,
                    repository_name=name,
                    last_updated=repo.last_polled_at,
                    processing_priority=1,  # Could be based on repo importance
                )
                self._repository_contexts.append(context)

            logger.info(
                f"Initialized {len(self._repository_contexts)} repositories "
                f"for processing"
            )

        except Exception as e:
            session.add_error(f"Failed to initialize repositories: {e}")
            raise

    async def _phase_process_repositories(self, session: ProcessingSession) -> None:
        """Process all repositories with parallel execution."""
        session.update_phase(ProcessingPhase.DISCOVERY)

        try:
            # Process repositories in batches for memory management
            batch_size = max(
                1, min(self.config.max_concurrent_repos, len(self._repository_contexts))
            )

            for batch_start in range(0, len(self._repository_contexts), batch_size):
                batch_end = min(
                    batch_start + batch_size, len(self._repository_contexts)
                )
                batch = self._repository_contexts[batch_start:batch_end]

                logger.info(
                    f"Processing repository batch {batch_start + 1}-{batch_end} "
                    f"of {len(self._repository_contexts)}"
                )

                # Process batch concurrently
                batch_results = await self._process_repository_batch(batch, session)

                # Update session metrics
                for result in batch_results:
                    self._repository_results[result.repository_id] = result

                    if result.success:
                        session.processed_repositories += 1
                        session.total_prs_discovered += result.prs_discovered
                        session.total_check_runs_discovered += (
                            result.check_runs_discovered
                        )
                        session.total_state_changes += result.state_changes_detected
                    else:
                        session.failed_repositories += 1
                        if result.error:
                            session.add_error(
                                f"Repository {result.repository_name}: {result.error}"
                            )

                # Stop processing on first error if configured
                if self.config.stop_on_first_error and session.failed_repositories > 0:
                    session.add_warning(
                        "Stopping processing due to stop_on_first_error=True"
                    )
                    break

                # Check for shutdown request
                if self._shutdown_requested:
                    session.add_warning("Processing stopped due to shutdown request")
                    break

                # Small delay between batches to prevent resource exhaustion
                await asyncio.sleep(0.1)

        except Exception as e:
            session.add_error(f"Failed to process repositories: {e}")
            raise

    async def _process_repository_batch(
        self,
        repositories: list[RepositoryContext],
        session: ProcessingSession,
    ) -> list[RepositoryProcessingResult]:
        """Process a batch of repositories concurrently."""

        async def process_single(repo: RepositoryContext) -> RepositoryProcessingResult:
            async with self._repo_semaphore:
                try:
                    # Determine incremental window
                    since = None
                    if session.mode == ProcessingMode.INCREMENTAL:
                        since = datetime.now(UTC) - timedelta(
                            hours=self.config.incremental_window_hours
                        )

                    return await self.process_single_repository(
                        repo.repository_id,
                        since=since,
                        dry_run=(session.mode == ProcessingMode.DRY_RUN),
                    )

                except Exception as e:
                    # Return failed result instead of raising
                    return RepositoryProcessingResult(
                        repository_id=repo.repository_id,
                        repository_name=f"{repo.repository_owner}/{repo.repository_name}",
                        success=False,
                        processing_time_seconds=0.0,
                        error=str(e),
                    )

        # Execute all repositories in batch concurrently
        tasks = [process_single(repo) for repo in repositories]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return results

    async def _coordinate_discovery(
        self,
        repo_context: RepositoryContext,
        since: datetime | None,
    ) -> tuple[list[DiscoveryResult], list[CheckRunDiscovery], ProcessingMetrics]:
        """Orchestrate PR and check run discovery for a repository."""

        # Discover PRs
        discovered_prs, pr_metrics = await self.pr_discovery.discover_prs(
            repositories=[repo_context],
            since=since,
        )

        # Discover check runs for all PRs
        all_check_runs = []

        for pr in discovered_prs:
            try:
                async with self._check_semaphore:
                    # Use head SHA as the ref for check run discovery
                    check_runs = await self.check_discovery.discover_check_runs(
                        repo_context.repository_owner,
                        repo_context.repository_name,
                        pr.pr_number,
                        pr.head_sha,
                    )

                    # Update PR context in check runs
                    updated_check_runs = []
                    for check_run in check_runs:
                        updated_check_run = replace(
                            check_run,
                            pr_id=uuid.UUID(
                                str(pr.repository_id)
                            ),  # Will be actual PR ID
                            pr_number=pr.pr_number,
                        )
                        updated_check_runs.append(updated_check_run)
                    check_runs = updated_check_runs

                    all_check_runs.extend(check_runs)

            except GitHubNotFoundError:
                # PR or commit might not exist, skip check runs
                logger.debug(
                    f"No check runs found for PR #{pr.pr_number} "
                    f"(commit {pr.head_sha[:8]})"
                )
                continue
            except Exception as e:
                logger.warning(f"Failed to get check runs for PR #{pr.pr_number}: {e}")
                continue

        # Get check run metrics
        check_metrics = await self.check_discovery.get_metrics()

        # Combine metrics
        combined_metrics = replace(
            pr_metrics,
            check_run_discovery_duration=check_metrics.check_run_discovery_duration,
            check_runs_discovered=len(all_check_runs),
            check_runs_processed_successfully=check_metrics.check_runs_processed_successfully,
        )

        return discovered_prs, all_check_runs, combined_metrics

    async def _coordinate_change_detection(
        self,
        discovered_prs: list[DiscoveryResult],
        discovered_checks: list[CheckRunDiscovery],
        repository_id: uuid.UUID,
    ) -> list[StateChangeEvent]:
        """Orchestrate state change detection for discovered data."""

        all_changes = []

        try:
            # Detect PR changes
            for pr in discovered_prs:
                # Get existing PR from database
                # This would be a proper query to get PR by repo_id and number
                # For now, simulate by passing None (treating as new PR)
                existing_pr_data: DiscoveryResult | None = None

                # Detect changes
                pr_changes = await self.state_detector.detect_pr_changes(
                    existing_pr_data, pr
                )
                all_changes.extend(pr_changes)

            # Detect check run changes
            if discovered_checks:
                # Group check runs by PR for efficient comparison
                checks_by_pr = defaultdict(list)
                for check in discovered_checks:
                    checks_by_pr[check.pr_number].append(check)

                for pr_number, checks in checks_by_pr.items():
                    # Get existing check runs from database
                    existing_checks: list[
                        CheckRunDiscovery
                    ] = []  # Would query from database

                    # Detect changes
                    check_changes = await self.state_detector.detect_check_run_changes(
                        existing_checks,
                        checks,
                        uuid.UUID(str(repository_id)),  # PR ID would be looked up
                        pr_number,
                    )
                    all_changes.extend(check_changes)

            # Analyze change significance
            analyzed_changes = await self.state_detector.analyze_significance(
                all_changes
            )

            # Filter for actionable changes
            actionable_changes = await self.state_detector.filter_actionable_changes(
                analyzed_changes
            )

            logger.debug(
                f"Change detection completed: {len(all_changes)} total changes, "
                f"{len(actionable_changes)} actionable"
            )

            return actionable_changes

        except Exception as e:
            logger.error(f"Change detection failed: {e}")
            raise

    async def _coordinate_synchronization(
        self,
        discovered_prs: list[DiscoveryResult],
        discovered_checks: list[CheckRunDiscovery],
        state_changes: list[StateChangeEvent],
    ) -> SyncOperation:
        """Orchestrate database synchronization for discovered changes."""

        try:
            # Create and execute sync operation
            sync_operation = await self.data_synchronizer.synchronize_changes(
                discovered_prs,
                discovered_checks,
                state_changes,
            )

            logger.debug(
                f"Synchronization completed: {sync_operation.total_operations} "
                f"operations, status={sync_operation.status}"
            )

            return sync_operation

        except Exception as e:
            logger.error(f"Synchronization failed: {e}")
            raise

    async def _collect_final_metrics(self, session: ProcessingSession) -> None:
        """Collect final metrics for the processing session."""

        try:
            # Update performance metrics
            if session.duration_seconds > 0:
                session.processing_rate_repos_per_minute = (
                    session.processed_repositories / session.duration_seconds * 60
                )

            # Aggregate component metrics

            for _result in self._repository_results.values():
                # Would collect metrics from each repository result
                pass

            # Update resource usage
            process = psutil.Process()
            memory_info = process.memory_info()
            session.memory_usage_mb = memory_info.rss / (1024 * 1024)

            with contextlib.suppress(Exception):
                session.cpu_usage_percent = process.cpu_percent()

            logger.info(
                f"Final metrics collected: "
                f"success_rate={session.success_rate:.1f}%, "
                f"rate={session.processing_rate_repos_per_minute:.1f} repos/min, "
                f"memory={session.memory_usage_mb:.1f}MB"
            )

        except Exception as e:
            session.add_warning(f"Failed to collect final metrics: {e}")

    async def _phase_cleanup(self, session: ProcessingSession) -> None:
        """Cleanup resources and finalize session."""
        session.update_phase(ProcessingPhase.CLEANUP)

        try:
            if self.config.auto_cleanup:
                # Clear caches
                await self.pr_discovery.clear_cache()
                await self.check_discovery.clear_cache()
                self.state_detector.clear_cache()

                # Clear internal state
                self._repository_results.clear()
                self._repository_contexts = []

                logger.debug("Resource cleanup completed")

        except Exception as e:
            session.add_warning(f"Cleanup failed: {e}")

    async def _cleanup_session(self, session: ProcessingSession) -> None:
        """Cleanup session resources."""
        try:
            # Stop resource monitoring
            if self._resource_monitor_task and not self._resource_monitor_task.done():
                self._resource_monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._resource_monitor_task

            # Final cleanup
            await self._phase_cleanup(session)

            self._current_session = None
            self._start_time = None

        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")

    async def _monitor_resources(self) -> None:
        """Monitor resource usage during processing."""
        while not self._shutdown_requested:
            try:
                if not self._current_session:
                    break

                process = psutil.Process()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)

                # Update session metrics
                self._current_session.memory_usage_mb = memory_mb

                with contextlib.suppress(Exception):
                    self._current_session.cpu_usage_percent = process.cpu_percent()

                # Check memory limit
                if memory_mb > self.config.memory_limit_mb:
                    self._current_session.add_warning(
                        f"Memory usage ({memory_mb:.1f}MB) exceeded limit "
                        f"({self.config.memory_limit_mb}MB)"
                    )

                # Log resource usage periodically
                if self.config.enable_detailed_logging:
                    logger.debug(
                        f"Resource usage: memory={memory_mb:.1f}MB, "
                        f"cpu={self._current_session.cpu_usage_percent:.1f}%"
                    )

                await asyncio.sleep(self.config.resource_check_interval)

            except Exception as e:
                logger.error(f"Resource monitoring failed: {e}")
                break

    async def request_shutdown(self) -> None:
        """Request graceful shutdown of processing."""
        logger.info("Graceful shutdown requested")
        self._shutdown_requested = True

        # Wait a moment for current operations to complete
        await asyncio.sleep(1.0)

    async def get_processing_status(self) -> dict[str, Any]:
        """Get current processing status and metrics."""
        if not self._current_session:
            return {"status": "idle", "last_session": None}

        return {
            "status": "active",
            "session_id": self._current_session.session_id,
            "phase": self._current_session.phase.value,
            "mode": self._current_session.mode.value,
            "progress": {
                "processed": self._current_session.processed_repositories,
                "total": self._current_session.total_repositories,
                "success_rate": self._current_session.success_rate,
            },
            "metrics": {
                "duration_seconds": self._current_session.duration_seconds,
                "processing_rate": (
                    self._current_session.processing_rate_repos_per_minute
                ),
                "memory_usage_mb": self._current_session.memory_usage_mb,
                "cpu_usage_percent": self._current_session.cpu_usage_percent,
                "prs_discovered": self._current_session.total_prs_discovered,
                "check_runs_discovered": (
                    self._current_session.total_check_runs_discovered
                ),
                "state_changes": self._current_session.total_state_changes,
            },
            "errors": len(self._current_session.errors),
            "warnings": len(self._current_session.warnings),
        }

    async def __aenter__(self) -> "PRProcessor":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit with cleanup."""
        await self.request_shutdown()

        # Final cleanup
        if self._current_session:
            await self._cleanup_session(self._current_session)
