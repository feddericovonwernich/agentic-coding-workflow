"""Data synchronizer for efficient database synchronization.

This module implements the DataSynchronizationStrategy interface to synchronize
discovered PR and check run data with the database using batch operations.
"""

import contextlib
import logging
import time
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.transactions import transaction_scope
from src.models.check_run import CheckRun
from src.models.enums import CheckConclusion, CheckStatus, PRState, TriggerEvent
from src.models.pull_request import PullRequest
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.state_history import PRStateHistoryRepository

from .interfaces import (
    ChangeType,
    DataSynchronizationStrategy,
    DiscoveredCheckRun,
    DiscoveredPR,
    DiscoveryError,
    EntityType,
    PRDiscoveryResult,
    StateChange,
    SynchronizationResult,
)

logger = logging.getLogger(__name__)


class DatabaseSynchronizer(DataSynchronizationStrategy):
    """Database implementation of data synchronization strategy.

    Provides efficient batch synchronization of discovered data with
    comprehensive error handling and transaction management.
    """

    def __init__(
        self,
        session: AsyncSession,
        pr_repository: PullRequestRepository,
        check_repository: CheckRunRepository,
        state_history_repository: PRStateHistoryRepository,
        batch_size: int = 100,
    ):
        """Initialize synchronizer with dependencies.

        Args:
            session: Database session
            pr_repository: Pull request repository
            check_repository: Check run repository
            state_history_repository: State history repository
            batch_size: Number of records to process in each batch
        """
        self.session = session
        self.pr_repository = pr_repository
        self.check_repository = check_repository
        self.state_history_repository = state_history_repository
        self.batch_size = batch_size

        # Transaction management
        self._current_transaction: AbstractAsyncContextManager[AsyncSession] | None = (
            None
        )

        # Metrics tracking
        self.stats = {
            "synchronizations": 0,
            "prs_processed": 0,
            "checks_processed": 0,
            "errors": 0,
            "transaction_rollbacks": 0,
        }

    async def begin_transaction(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Begin a database transaction."""
        if self._current_transaction is not None:
            logger.warning("Transaction already in progress")
            return self._current_transaction

        self._current_transaction = transaction_scope(self.session)
        await self._current_transaction.__aenter__()
        return self._current_transaction

    async def commit_transaction(self) -> None:
        """Commit the current transaction."""
        if self._current_transaction is None:
            logger.warning("No transaction to commit")
            return

        try:
            await self._current_transaction.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Error committing transaction: {e}")
            raise
        finally:
            self._current_transaction = None

    async def rollback_transaction(self) -> None:
        """Rollback the current transaction."""
        if self._current_transaction is None:
            logger.warning("No transaction to rollback")
            return

        self.stats["transaction_rollbacks"] += 1

        try:
            await self._current_transaction.__aexit__(
                Exception, Exception("Rollback"), None
            )
        except Exception as e:
            logger.error(f"Error rolling back transaction: {e}")
        finally:
            self._current_transaction = None

    def _convert_discovered_pr_to_model(
        self,
        discovered_pr: DiscoveredPR,
        repository_id: uuid.UUID,
        existing_pr: PullRequest | None = None,
    ) -> PullRequest:
        """Convert discovered PR to database model.

        Args:
            discovered_pr: Discovered PR data
            repository_id: Repository ID
            existing_pr: Existing PR model to update (if any)

        Returns:
            PullRequest model instance
        """
        # Parse PR state
        try:
            pr_state = PRState(discovered_pr.state.upper())
        except ValueError:
            pr_state = PRState.OPENED  # Default fallback

        if existing_pr:
            # Update existing PR
            pr = existing_pr
            pr.title = discovered_pr.title
            pr.author = discovered_pr.author
            pr.state = pr_state
            pr.draft = discovered_pr.draft
            pr.base_branch = discovered_pr.base_branch
            pr.head_branch = discovered_pr.head_branch
            pr.base_sha = discovered_pr.base_sha
            pr.head_sha = discovered_pr.head_sha
            pr.url = discovered_pr.url
            pr.body = discovered_pr.body
            pr.pr_metadata = discovered_pr.metadata
            pr.updated_at = discovered_pr.updated_at
        else:
            # Create new PR
            pr = PullRequest(
                repository_id=repository_id,
                pr_number=discovered_pr.pr_number,
                title=discovered_pr.title,
                author=discovered_pr.author,
                state=pr_state,
                draft=discovered_pr.draft,
                base_branch=discovered_pr.base_branch,
                head_branch=discovered_pr.head_branch,
                base_sha=discovered_pr.base_sha,
                head_sha=discovered_pr.head_sha,
                url=discovered_pr.url,
                body=discovered_pr.body,
                pr_metadata=discovered_pr.metadata,
                created_at=discovered_pr.created_at,
                updated_at=discovered_pr.updated_at,
            )

        return pr

    def _convert_discovered_check_to_model(
        self,
        discovered_check: DiscoveredCheckRun,
        pr_id: uuid.UUID,
        existing_check: CheckRun | None = None,
    ) -> CheckRun:
        """Convert discovered check run to database model.

        Args:
            discovered_check: Discovered check run data
            pr_id: Pull request ID
            existing_check: Existing check run model to update (if any)

        Returns:
            CheckRun model instance
        """
        # Parse check status and conclusion
        try:
            status = CheckStatus(discovered_check.status.upper())
        except ValueError:
            status = CheckStatus.QUEUED  # Default fallback

        conclusion = None
        if discovered_check.conclusion:
            with contextlib.suppress(ValueError):
                conclusion = CheckConclusion(discovered_check.conclusion.upper())

        # Extract output fields
        output_summary = None
        output_text = None
        if discovered_check.output:
            output_summary = discovered_check.output.get("summary")
            output_text = discovered_check.output.get("text")

        if existing_check:
            # Update existing check
            check = existing_check
            check.status = status
            check.conclusion = conclusion
            check.details_url = discovered_check.details_url
            check.output_summary = output_summary
            check.output_text = output_text
            check.started_at = discovered_check.started_at
            check.completed_at = discovered_check.completed_at
            check.check_metadata = discovered_check.output
        else:
            # Create new check
            check = CheckRun(
                pr_id=pr_id,
                external_id=discovered_check.external_id,
                check_name=discovered_check.name,
                status=status,
                conclusion=conclusion,
                details_url=discovered_check.details_url,
                output_summary=output_summary,
                output_text=output_text,
                started_at=discovered_check.started_at,
                completed_at=discovered_check.completed_at,
                check_metadata=discovered_check.output,
            )

        return check

    async def _synchronize_prs(
        self, discovered_prs: list[DiscoveredPR], repository_id: uuid.UUID
    ) -> tuple[int, int, list[DiscoveryError]]:
        """Synchronize discovered PRs with database.

        Args:
            discovered_prs: List of discovered PRs
            repository_id: Repository ID

        Returns:
            Tuple of (created_count, updated_count, errors)
        """
        created_count = 0
        updated_count = 0
        errors: list[DiscoveryError] = []

        if not discovered_prs:
            return created_count, updated_count, errors

        try:
            # Process PRs in batches
            for i in range(0, len(discovered_prs), self.batch_size):
                batch = discovered_prs[i : i + self.batch_size]
                pr_numbers = [pr.pr_number for pr in batch]

                # Get existing PRs for this batch
                existing_prs = {}
                query = select(PullRequest).where(
                    and_(
                        PullRequest.repository_id == repository_id,
                        PullRequest.pr_number.in_(pr_numbers),
                    )
                )
                result = await self.session.execute(query)
                for pr in result.scalars().all():
                    existing_prs[pr.pr_number] = pr

                # Process each PR in the batch
                for discovered_pr in batch:
                    try:
                        existing_pr = existing_prs.get(discovered_pr.pr_number)

                        if existing_pr:
                            # Update existing PR
                            self._convert_discovered_pr_to_model(
                                discovered_pr, repository_id, existing_pr
                            )
                            updated_count += 1
                        else:
                            # Create new PR
                            new_pr = self._convert_discovered_pr_to_model(
                                discovered_pr, repository_id
                            )
                            self.session.add(new_pr)
                            created_count += 1

                    except Exception as e:
                        error = DiscoveryError(
                            error_type="pr_sync_error",
                            message=f"Failed to sync PR "
                            f"#{discovered_pr.pr_number}: {e!s}",
                            context={
                                "pr_number": discovered_pr.pr_number,
                                "repository_id": str(repository_id),
                            },
                            timestamp=datetime.now(UTC),
                            recoverable=True,
                        )
                        errors.append(error)
                        logger.warning(
                            f"Error syncing PR #{discovered_pr.pr_number}: {e}"
                        )

                # Flush batch
                await self.session.flush()

        except Exception as e:
            error = DiscoveryError(
                error_type="pr_batch_sync_error",
                message=f"Failed to sync PR batch: {e!s}",
                context={"repository_id": str(repository_id)},
                timestamp=datetime.now(UTC),
                recoverable=True,
            )
            errors.append(error)
            logger.error(f"Error syncing PR batch: {e}")

        return created_count, updated_count, errors

    async def _synchronize_checks(
        self, discovered_prs: list[DiscoveredPR], repository_id: uuid.UUID
    ) -> tuple[int, int, list[DiscoveryError]]:
        """Synchronize discovered check runs with database.

        Args:
            discovered_prs: List of discovered PRs with check runs
            repository_id: Repository ID

        Returns:
            Tuple of (created_count, updated_count, errors)
        """
        created_count = 0
        updated_count = 0
        errors: list[DiscoveryError] = []

        try:
            # Collect all check runs
            all_checks = []
            pr_number_to_id = {}

            # Get PR IDs for check runs
            pr_numbers = [pr.pr_number for pr in discovered_prs if pr.check_runs]
            if pr_numbers:
                query = select(PullRequest.id, PullRequest.pr_number).where(
                    and_(
                        PullRequest.repository_id == repository_id,
                        PullRequest.pr_number.in_(pr_numbers),
                    )
                )
                result = await self.session.execute(query)
                pr_number_to_id = {
                    pr_number: pr_id for pr_id, pr_number in result.all()
                }

            # Collect check runs with PR IDs
            for discovered_pr in discovered_prs:
                pr_id = pr_number_to_id.get(discovered_pr.pr_number)
                if pr_id and discovered_pr.check_runs:
                    for check in discovered_pr.check_runs:
                        all_checks.append((check, pr_id, discovered_pr.pr_number))

            if not all_checks:
                return created_count, updated_count, errors

            # Process check runs in batches
            for i in range(0, len(all_checks), self.batch_size):
                batch = all_checks[i : i + self.batch_size]

                # Get existing check runs for this batch
                external_ids = [check.external_id for check, _, _ in batch]
                existing_checks = {}

                if external_ids:
                    check_query = select(CheckRun).where(
                        CheckRun.external_id.in_(external_ids)
                    )
                    result = await self.session.execute(check_query)
                    for check in result.scalars().all():
                        existing_checks[check.external_id] = check

                # Process each check in the batch
                for discovered_check, pr_id, pr_number in batch:
                    try:
                        existing_check = existing_checks.get(
                            discovered_check.external_id
                        )

                        if existing_check:
                            # Update existing check
                            self._convert_discovered_check_to_model(
                                discovered_check, pr_id, existing_check
                            )
                            updated_count += 1
                        else:
                            # Create new check
                            new_check = self._convert_discovered_check_to_model(
                                discovered_check, pr_id
                            )
                            self.session.add(new_check)
                            created_count += 1

                    except Exception as e:
                        error = DiscoveryError(
                            error_type="check_sync_error",
                            message=f"Failed to sync check "
                            f"{discovered_check.name} for PR "
                            f"#{pr_number}: {e!s}",
                            context={
                                "check_name": discovered_check.name,
                                "pr_number": pr_number,
                                "external_id": discovered_check.external_id,
                            },
                            timestamp=datetime.now(UTC),
                            recoverable=True,
                        )
                        errors.append(error)
                        logger.warning(
                            f"Error syncing check {discovered_check.name}: {e}"
                        )

                # Flush batch
                await self.session.flush()

        except Exception as e:
            error = DiscoveryError(
                error_type="check_batch_sync_error",
                message=f"Failed to sync check batch: {e!s}",
                context={"repository_id": str(repository_id)},
                timestamp=datetime.now(UTC),
                recoverable=True,
            )
            errors.append(error)
            logger.error(f"Error syncing check batch: {e}")

        return created_count, updated_count, errors

    async def _record_state_changes(
        self, state_changes: list[StateChange]
    ) -> tuple[int, list[DiscoveryError]]:
        """Record state changes in history.

        Args:
            state_changes: List of state changes

        Returns:
            Tuple of (recorded_count, errors)
        """
        recorded_count = 0
        errors: list[DiscoveryError] = []

        # Only record PR state changes for now
        pr_state_changes = [
            change
            for change in state_changes
            if change.entity_type == EntityType.PULL_REQUEST
        ]

        if not pr_state_changes:
            return recorded_count, errors

        try:
            for change in pr_state_changes:
                try:
                    # Skip placeholder entity IDs (new PRs)
                    if change.entity_id.int == 0:
                        continue

                    # Only record significant state changes
                    if change.change_type == ChangeType.STATE_CHANGED:
                        await self.state_history_repository.create_transition(
                            pr_id=change.entity_id,
                            old_state=PRState(change.old_state.upper())
                            if change.old_state
                            else None,
                            new_state=PRState(change.new_state.upper()),
                            trigger_event=TriggerEvent.SYNCHRONIZE,
                            metadata=change.metadata,
                        )
                        recorded_count += 1

                except Exception as e:
                    error = DiscoveryError(
                        error_type="state_change_record_error",
                        message=f"Failed to record state change: {e!s}",
                        context={
                            "entity_type": change.entity_type.value,
                            "entity_id": str(change.entity_id),
                            "change_type": change.change_type.value,
                        },
                        timestamp=datetime.now(UTC),
                        recoverable=True,
                    )
                    errors.append(error)
                    logger.warning(f"Error recording state change: {e}")

        except Exception as e:
            error = DiscoveryError(
                error_type="state_changes_record_error",
                message=f"Failed to record state changes: {e!s}",
                context={"changes_count": len(pr_state_changes)},
                timestamp=datetime.now(UTC),
                recoverable=True,
            )
            errors.append(error)
            logger.error(f"Error recording state changes: {e}")

        return recorded_count, errors

    async def synchronize(
        self,
        discovery_results: list[PRDiscoveryResult],
        state_changes: list[StateChange],
    ) -> SynchronizationResult:
        """Synchronize discovered data with database.

        Args:
            discovery_results: Results from PR discovery
            state_changes: Detected state changes

        Returns:
            Synchronization result with statistics
        """
        start_time = time.time()
        self.stats["synchronizations"] += 1

        # Initialize counters
        total_prs_processed = 0
        prs_created = 0
        prs_updated = 0
        total_checks_processed = 0
        checks_created = 0
        checks_updated = 0
        state_changes_recorded = 0
        all_errors = []

        transaction_started = False

        try:
            logger.info(
                f"Starting synchronization: {len(discovery_results)} repositories, "
                f"{len(state_changes)} state changes"
            )

            # Begin transaction
            await self.begin_transaction()
            transaction_started = True

            # Process each repository's results
            for result in discovery_results:
                try:
                    # Synchronize PRs
                    pr_created, pr_updated, pr_errors = await self._synchronize_prs(
                        result.discovered_prs, result.repository_id
                    )

                    prs_created += pr_created
                    prs_updated += pr_updated
                    total_prs_processed += len(result.discovered_prs)
                    all_errors.extend(pr_errors)

                    # Synchronize check runs
                    (
                        check_created,
                        check_updated,
                        check_errors,
                    ) = await self._synchronize_checks(
                        result.discovered_prs, result.repository_id
                    )

                    checks_created += check_created
                    checks_updated += check_updated
                    total_checks_processed += sum(
                        len(pr.check_runs) for pr in result.discovered_prs
                    )
                    all_errors.extend(check_errors)

                    self.stats["prs_processed"] += len(result.discovered_prs)
                    self.stats["checks_processed"] += sum(
                        len(pr.check_runs) for pr in result.discovered_prs
                    )

                except Exception as e:
                    error = DiscoveryError(
                        error_type="repository_sync_error",
                        message=f"Failed to sync repository "
                        f"{result.repository_id}: {e!s}",
                        context={"repository_id": str(result.repository_id)},
                        timestamp=datetime.now(UTC),
                        recoverable=True,
                    )
                    all_errors.append(error)
                    logger.error(
                        f"Error syncing repository {result.repository_id}: {e}"
                    )

            # Record state changes
            state_recorded, state_errors = await self._record_state_changes(
                state_changes
            )
            state_changes_recorded = state_recorded
            all_errors.extend(state_errors)

            # Commit transaction
            await self.commit_transaction()
            transaction_started = False

            processing_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Synchronization completed: {prs_created} PRs created, "
                f"{prs_updated} PRs updated, {checks_created} checks created, "
                f"{checks_updated} checks updated, "
                f"{state_changes_recorded} state changes recorded "
                f"({processing_time_ms:.1f}ms, {len(all_errors)} errors)"
            )

            return SynchronizationResult(
                total_prs_processed=total_prs_processed,
                prs_created=prs_created,
                prs_updated=prs_updated,
                total_checks_processed=total_checks_processed,
                checks_created=checks_created,
                checks_updated=checks_updated,
                state_changes_recorded=state_changes_recorded,
                errors=all_errors,
                processing_time_ms=processing_time_ms,
            )

        except Exception as e:
            self.stats["errors"] += 1

            # Rollback transaction if still active
            if transaction_started:
                try:
                    await self.rollback_transaction()
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {rollback_error}")

            error = DiscoveryError(
                error_type="synchronization_error",
                message=f"Synchronization failed: {e!s}",
                context={"discovery_results_count": len(discovery_results)},
                timestamp=datetime.now(UTC),
                recoverable=True,
            )
            all_errors.append(error)
            logger.error(f"Synchronization failed: {e}")

            processing_time_ms = (time.time() - start_time) * 1000

            return SynchronizationResult(
                total_prs_processed=total_prs_processed,
                prs_created=prs_created,
                prs_updated=prs_updated,
                total_checks_processed=total_checks_processed,
                checks_created=checks_created,
                checks_updated=checks_updated,
                state_changes_recorded=state_changes_recorded,
                errors=all_errors,
                processing_time_ms=processing_time_ms,
            )

    def get_stats(self) -> dict[str, int]:
        """Get synchronization statistics.

        Returns:
            Dictionary with statistics
        """
        return self.stats.copy()
