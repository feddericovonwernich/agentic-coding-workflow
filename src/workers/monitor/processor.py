"""Core PR processing orchestrator for monitoring and synchronization."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Protocol

from src.models.repository import Repository
from src.workers.monitor.models import (
    BatchProcessingResult,
    ChangeSet,
    ProcessingResult,
)

logger = logging.getLogger(__name__)


class PRDiscoveryService(Protocol):
    """Interface for PR discovery service."""

    async def discover_prs_and_checks(self, repository: Repository) -> tuple[int, int]:
        """
        Discover PRs and check runs for a repository.

        Args:
            repository: Repository to discover PRs for

        Returns:
            Tuple of (pr_count, check_run_count) discovered
        """
        ...


class ChangeDetectionService(Protocol):
    """Interface for change detection service."""

    async def detect_changes(self, repository: Repository) -> ChangeSet:
        """
        Detect changes for a repository.

        Args:
            repository: Repository to analyze for changes

        Returns:
            ChangeSet containing all detected changes
        """
        ...


class SynchronizationService(Protocol):
    """Interface for data synchronization service."""

    async def synchronize_changes(self, changeset: ChangeSet) -> int:
        """
        Synchronize detected changes to persistent storage.

        Args:
            changeset: Changes to synchronize

        Returns:
            Number of changes successfully synchronized
        """
        ...


class PRProcessor(ABC):
    """
    Abstract base class for PR processing orchestration.

    Coordinates the entire processing flow for discovering and processing
    pull requests from GitHub repositories. Manages the flow between
    discovery, change detection, and synchronization services.
    """

    def __init__(
        self,
        discovery_service: PRDiscoveryService,
        change_detection_service: ChangeDetectionService,
        synchronization_service: SynchronizationService,
        max_concurrent_repos: int = 10,
    ) -> None:
        """
        Initialize the PR processor with required services.

        Args:
            discovery_service: Service for discovering PRs and check runs
            change_detection_service: Service for detecting data changes
            synchronization_service: Service for persisting changes
            max_concurrent_repos: Maximum concurrent repository processing
        """
        self.discovery_service = discovery_service
        self.change_detection_service = change_detection_service
        self.synchronization_service = synchronization_service
        self.max_concurrent_repos = max_concurrent_repos

        # Create semaphore for limiting concurrent operations
        self._semaphore = asyncio.Semaphore(max_concurrent_repos)

    @abstractmethod
    async def process_repository(self, repository: Repository) -> ProcessingResult:
        """
        Process a single repository for PR and check run changes.

        Args:
            repository: Repository to process

        Returns:
            ProcessingResult containing metrics and any errors
        """
        pass

    @abstractmethod
    async def process_repositories(
        self, repositories: list[Repository]
    ) -> BatchProcessingResult:
        """
        Process multiple repositories concurrently.

        Args:
            repositories: List of repositories to process

        Returns:
            BatchProcessingResult aggregating all repository results
        """
        pass


class DefaultPRProcessor(PRProcessor):
    """
    Default implementation of PR processor.

    Orchestrates the complete processing flow:
    1. Discovery: Find all PRs and check runs for a repository
    2. Change Detection: Identify what has changed since last processing
    3. Synchronization: Persist changes to database

    Provides error isolation, comprehensive metrics collection,
    and supports concurrent processing of multiple repositories.
    """

    async def process_repository(self, repository: Repository) -> ProcessingResult:
        """
        Process a single repository through the complete workflow.

        This method orchestrates the three-phase processing:
        1. Discovery phase: Fetch current state from GitHub
        2. Change detection phase: Compare with stored state
        3. Synchronization phase: Update database with changes

        Args:
            repository: Repository to process

        Returns:
            ProcessingResult with comprehensive metrics and error tracking
        """
        result = ProcessingResult(
            repository_id=repository.id,
            repository_url=repository.url,
        )

        logger.info(
            "Starting repository processing",
            extra={
                "repository_id": str(repository.id),
                "repository_url": repository.url,
                "repository_name": repository.name,
            },
        )

        try:
            # Phase 1: Discovery
            await self._execute_discovery_phase(repository, result)

            # Phase 2: Change Detection
            changeset = await self._execute_change_detection_phase(repository, result)

            # Phase 3: Synchronization
            await self._execute_synchronization_phase(changeset, result)

            # Mark as successful if no errors occurred
            result.success = len(result.errors) == 0

            # Update repository tracking
            await self._update_repository_tracking(repository, result)

        except Exception as e:
            logger.exception(
                "Unexpected error during repository processing",
                extra={
                    "repository_id": str(repository.id),
                    "error": str(e),
                },
            )
            result.add_error(
                error_type="processing_failure",
                message=f"Unexpected processing error: {e!s}",
                context={"exception_type": type(e).__name__},
            )
            result.success = False

        finally:
            result.mark_completed()

            logger.info(
                "Repository processing completed",
                extra={
                    "repository_id": str(repository.id),
                    "success": result.success,
                    "processing_time": result.processing_time,
                    "changes_synchronized": result.changes_synchronized,
                    "error_count": len(result.errors),
                },
            )

        return result

    async def process_repositories(
        self, repositories: list[Repository]
    ) -> BatchProcessingResult:
        """
        Process multiple repositories concurrently with error isolation.

        Uses asyncio.gather with return_exceptions=True to ensure that
        failures in individual repositories don't affect others.
        Results are collected and aggregated into a comprehensive
        batch processing result.

        Args:
            repositories: List of repositories to process concurrently

        Returns:
            BatchProcessingResult with aggregated metrics from all repositories
        """
        batch_result = BatchProcessingResult()

        if not repositories:
            logger.warning("No repositories provided for batch processing")
            batch_result.mark_completed()
            return batch_result

        logger.info(
            "Starting batch repository processing",
            extra={
                "repository_count": len(repositories),
                "max_concurrent": self.max_concurrent_repos,
            },
        )

        try:
            # Create processing tasks with semaphore limiting
            tasks = [
                self._process_repository_with_semaphore(repo) for repo in repositories
            ]

            # Execute all tasks concurrently, collecting results and exceptions
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and handle any exceptions
            for i, result_or_exception in enumerate(results):
                repository = repositories[i]

                if isinstance(result_or_exception, Exception):
                    # Create error result for failed repository
                    error_result = ProcessingResult(
                        repository_id=repository.id,
                        repository_url=repository.url,
                    )
                    error_result.add_error(
                        error_type="batch_processing_failure",
                        message=(
                            f"Repository processing failed: {result_or_exception!s}"
                        ),
                        context={
                            "exception_type": type(result_or_exception).__name__,
                        },
                    )
                    error_result.success = False
                    error_result.mark_completed()
                    batch_result.add_result(error_result)

                    logger.error(
                        "Repository processing failed in batch",
                        extra={
                            "repository_id": str(repository.id),
                            "error": str(result_or_exception),
                        },
                    )
                else:
                    # Add successful result (we know it's ProcessingResult here)
                    batch_result.add_result(result_or_exception)  # type: ignore[arg-type]

        except Exception:
            logger.exception("Unexpected error during batch processing")
            # Continue with whatever results we have

        finally:
            batch_result.mark_completed()

            logger.info(
                "Batch repository processing completed",
                extra={
                    "repositories_processed": batch_result.repositories_processed,
                    "success_rate": batch_result.success_rate,
                    "total_processing_time": batch_result.processing_time,
                    "total_errors": batch_result.total_errors,
                },
            )

        return batch_result

    async def _process_repository_with_semaphore(
        self, repository: Repository
    ) -> ProcessingResult:
        """
        Process a repository with semaphore-based concurrency limiting.

        Args:
            repository: Repository to process

        Returns:
            ProcessingResult from processing
        """
        async with self._semaphore:
            return await self.process_repository(repository)

    async def _execute_discovery_phase(
        self, repository: Repository, result: ProcessingResult
    ) -> None:
        """
        Execute the discovery phase to fetch current repository state.

        Args:
            repository: Repository to discover data for
            result: ProcessingResult to update with metrics
        """
        try:
            logger.debug(
                "Starting discovery phase",
                extra={"repository_id": str(repository.id)},
            )

            (
                prs_discovered,
                checks_discovered,
            ) = await self.discovery_service.discover_prs_and_checks(repository)

            result.prs_discovered = prs_discovered
            result.check_runs_discovered = checks_discovered

            logger.debug(
                "Discovery phase completed",
                extra={
                    "repository_id": str(repository.id),
                    "prs_discovered": prs_discovered,
                    "check_runs_discovered": checks_discovered,
                },
            )

        except Exception as e:
            logger.error(
                "Discovery phase failed",
                extra={
                    "repository_id": str(repository.id),
                    "error": str(e),
                },
            )
            result.add_error(
                error_type="discovery_failure",
                message=f"Failed to discover repository data: {e!s}",
                context={"exception_type": type(e).__name__},
            )

    async def _execute_change_detection_phase(
        self, repository: Repository, result: ProcessingResult
    ) -> ChangeSet:
        """
        Execute the change detection phase to identify data changes.

        Args:
            repository: Repository to analyze for changes
            result: ProcessingResult to update with metrics

        Returns:
            ChangeSet containing detected changes (empty changeset on failure)
        """
        try:
            logger.debug(
                "Starting change detection phase",
                extra={"repository_id": str(repository.id)},
            )

            changeset = await self.change_detection_service.detect_changes(repository)

            # Update result with change metrics
            result.update_from_changeset(changeset)

            logger.debug(
                "Change detection phase completed",
                extra={
                    "repository_id": str(repository.id),
                    "changes_detected": changeset.total_changes,
                    "new_prs": len(changeset.new_prs),
                    "updated_prs": len(changeset.updated_prs),
                    "new_check_runs": len(changeset.new_check_runs),
                    "updated_check_runs": len(changeset.updated_check_runs),
                },
            )

        except Exception as e:
            logger.error(
                "Change detection phase failed",
                extra={
                    "repository_id": str(repository.id),
                    "error": str(e),
                },
            )
            result.add_error(
                error_type="change_detection_failure",
                message=f"Failed to detect changes: {e!s}",
                context={"exception_type": type(e).__name__},
            )
            # Return empty changeset on failure
            changeset = ChangeSet(repository_id=repository.id)

        return changeset

    async def _execute_synchronization_phase(
        self, changeset: ChangeSet, result: ProcessingResult
    ) -> None:
        """
        Execute the synchronization phase to persist changes.

        Args:
            changeset: Changes to synchronize
            result: ProcessingResult to update with metrics
        """
        try:
            if not changeset.has_changes:
                logger.debug(
                    "No changes to synchronize",
                    extra={"repository_id": str(changeset.repository_id)},
                )
                result.changes_synchronized = 0
                return

            logger.debug(
                "Starting synchronization phase",
                extra={
                    "repository_id": str(changeset.repository_id),
                    "changes_to_sync": changeset.total_changes,
                },
            )

            synchronized_count = await self.synchronization_service.synchronize_changes(
                changeset
            )

            result.changes_synchronized = synchronized_count

            logger.debug(
                "Synchronization phase completed",
                extra={
                    "repository_id": str(changeset.repository_id),
                    "changes_synchronized": synchronized_count,
                },
            )

        except Exception as e:
            logger.error(
                "Synchronization phase failed",
                extra={
                    "repository_id": str(changeset.repository_id),
                    "error": str(e),
                },
            )
            result.add_error(
                error_type="synchronization_failure",
                message=f"Failed to synchronize changes: {e!s}",
                context={"exception_type": type(e).__name__},
            )

    async def _update_repository_tracking(
        self, repository: Repository, result: ProcessingResult
    ) -> None:
        """
        Update repository tracking information based on processing results.

        Args:
            repository: Repository that was processed
            result: Results from processing
        """
        try:
            if result.success:
                # Reset failure count on successful processing
                repository.reset_failure_count()
                repository.update_last_polled()
            else:
                # Increment failure count on processing failure
                error_messages = [str(error) for error in result.errors]
                failure_reason = "; ".join(error_messages[:3])  # Limit length
                repository.increment_failure_count(failure_reason)

            logger.debug(
                "Repository tracking updated",
                extra={
                    "repository_id": str(repository.id),
                    "success": result.success,
                    "failure_count": repository.failure_count,
                },
            )

        except Exception as e:
            logger.warning(
                "Failed to update repository tracking",
                extra={
                    "repository_id": str(repository.id),
                    "error": str(e),
                },
            )
