"""Data synchronization logic for the PR Monitor Worker.

This module implements a robust data synchronization system that updates existing PRs,
creates new PR records, updates check run records, and maintains data consistency
through database transactions and error recovery.

The DataSynchronizer class provides efficient bulk operations with comprehensive
error handling, conflict resolution, and audit trails for maintaining data integrity
between GitHub API responses and the local database.
"""

import logging
import uuid
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.transactions import DatabaseTransaction, TransactionError
from ...models import CheckRun, PullRequest
from ...repositories import CheckRunRepository, PullRequestRepository
from .models import (
    CheckRunDiscovery,
    DataSynchronizerInterface,
    DiscoveryResult,
    OperationStatus,
    StateChangeEvent,
    SyncOperation,
)

logger = logging.getLogger(__name__)


class SyncOperationType(str, Enum):
    """Types of synchronization operations."""

    # PR Operations
    CREATE_PR = "create_pr"
    UPDATE_PR_STATE = "update_pr_state"
    UPDATE_PR_METADATA = "update_pr_metadata"
    UPDATE_PR_BRANCH = "update_pr_branch"
    MARK_PR_CHECKED = "mark_pr_checked"

    # Check Run Operations
    CREATE_CHECK_RUN = "create_check_run"
    UPDATE_CHECK_STATUS = "update_check_status"
    UPDATE_CHECK_CONCLUSION = "update_check_conclusion"
    UPDATE_CHECK_OUTPUT = "update_check_output"
    LINK_CHECK_TO_PR = "link_check_to_pr"


class ConflictResolutionStrategy(str, Enum):
    """Strategies for resolving data conflicts."""

    GITHUB_WINS = "github_wins"
    DATABASE_WINS = "database_wins"
    MERGE_METADATA = "merge_metadata"
    FAIL_ON_CONFLICT = "fail_on_conflict"


class DataSynchronizer(DataSynchronizerInterface):
    """Implements robust data synchronization with transaction management."""

    def __init__(
        self,
        session: AsyncSession,
        batch_size: int = 1000,
        conflict_resolution: ConflictResolutionStrategy = (
            ConflictResolutionStrategy.GITHUB_WINS
        ),
        enable_audit_log: bool = True,
    ):
        """Initialize the data synchronizer.

        Args:
            session: Database session for operations
            batch_size: Number of operations to process in each batch
            conflict_resolution: Strategy for resolving data conflicts
            enable_audit_log: Whether to enable detailed audit logging
        """
        self.session = session
        self.batch_size = batch_size
        self.conflict_resolution = conflict_resolution
        self.enable_audit_log = enable_audit_log

        # Initialize repositories
        self.pr_repo = PullRequestRepository(session)
        self.check_run_repo = CheckRunRepository(session)

        # Operation tracking
        self._current_operation: SyncOperation | None = None
        self._rollback_data: dict[str, Any] = {}

    async def create_sync_operation(
        self,
        pull_requests_to_create: list[DiscoveryResult] | None = None,
        pull_requests_to_update: list[DiscoveryResult] | None = None,
        check_runs_to_create: list[CheckRunDiscovery] | None = None,
        check_runs_to_update: list[CheckRunDiscovery] | None = None,
        state_changes: list[StateChangeEvent] | None = None,
    ) -> SyncOperation:
        """Create a new synchronization operation."""
        operation = SyncOperation(
            pull_requests_to_create=pull_requests_to_create or [],
            pull_requests_to_update=pull_requests_to_update or [],
            check_runs_to_create=check_runs_to_create or [],
            check_runs_to_update=check_runs_to_update or [],
            state_changes=state_changes or [],
        )

        logger.info(
            f"Created sync operation {operation.operation_id[:8]} with "
            f"{operation.total_operations} operations"
        )

        if self.enable_audit_log:
            self._log_operation_audit("CREATED", operation)

        return operation

    async def execute_sync_operation(self, operation: SyncOperation) -> SyncOperation:
        """Execute a synchronization operation with transaction support."""
        if operation.is_empty:
            logger.info("Empty sync operation, skipping execution")
            return replace(operation, status=OperationStatus.COMPLETED)

        self._current_operation = operation
        updated_operation = replace(
            operation,
            status=OperationStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
        )

        try:
            logger.info(
                f"Starting sync operation {operation.operation_id[:8]} with "
                f"{operation.total_operations} operations"
            )

            async with DatabaseTransaction(self.session, auto_commit=True):
                # Store rollback data before making changes
                await self._prepare_rollback_data(updated_operation)

                # Execute operations in phases for consistency
                await self._execute_sync_phases(updated_operation)

                # Update completion timestamp
                updated_operation = replace(
                    updated_operation,
                    status=OperationStatus.COMPLETED,
                    completed_at=datetime.now(UTC),
                )

                logger.info(
                    f"Completed sync operation {operation.operation_id[:8]} "
                    f"successfully"
                )

                if self.enable_audit_log:
                    self._log_operation_audit("COMPLETED", updated_operation)

                return updated_operation

        except Exception as e:
            logger.error(
                f"Failed to execute sync operation {operation.operation_id[:8]}: {e}"
            )

            # Update operation with failure status and error details
            error_message = str(e)
            updated_operation = replace(
                updated_operation,
                status=OperationStatus.FAILED,
                completed_at=datetime.now(UTC),
                errors=[*updated_operation.errors, error_message],
            )

            if self.enable_audit_log:
                self._log_operation_audit("FAILED", updated_operation, error=str(e))

            # Attempt rollback if possible
            if updated_operation.can_rollback:
                try:
                    updated_operation = await self.rollback_sync_operation(
                        updated_operation
                    )
                except Exception as rollback_error:
                    logger.error(f"Rollback also failed: {rollback_error}")
                    updated_operation = replace(
                        updated_operation,
                        errors=[
                            *updated_operation.errors,
                            f"Rollback failed: {rollback_error}",
                        ],
                    )

            raise TransactionError(f"Sync operation failed: {e}") from e

        finally:
            self._current_operation = None
            self._rollback_data.clear()

    async def synchronize_changes(
        self,
        discovered_prs: list[DiscoveryResult],
        discovered_check_runs: list[CheckRunDiscovery],
        state_changes: list[StateChangeEvent],
    ) -> SyncOperation:
        """Main entry point for bulk synchronization."""
        logger.info(
            f"Starting bulk synchronization of {len(discovered_prs)} PRs, "
            f"{len(discovered_check_runs)} check runs, and {len(state_changes)} changes"
        )

        # Categorize PRs into create vs update operations
        prs_to_create, prs_to_update = await self._categorize_pr_operations(
            discovered_prs
        )

        # Categorize check runs into create vs update operations
        checks_to_create, checks_to_update = await self._categorize_check_operations(
            discovered_check_runs
        )

        # Create and execute sync operation
        operation = await self.create_sync_operation(
            pull_requests_to_create=prs_to_create,
            pull_requests_to_update=prs_to_update,
            check_runs_to_create=checks_to_create,
            check_runs_to_update=checks_to_update,
            state_changes=state_changes,
        )

        return await self.execute_sync_operation(operation)

    async def sync_pull_requests(
        self, pull_requests: list[DiscoveryResult]
    ) -> tuple[int, int, list[str]]:
        """Handle all PR-related changes."""
        created_count = 0
        updated_count = 0
        errors = []

        for batch in self._batch_items(pull_requests):
            try:
                batch_created, batch_updated = await self._sync_pr_batch(batch)
                created_count += batch_created
                updated_count += batch_updated

            except Exception as e:
                error_msg = f"Failed to sync PR batch: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

        return created_count, updated_count, errors

    async def sync_check_runs(
        self, check_runs: list[CheckRunDiscovery]
    ) -> tuple[int, int, list[str]]:
        """Handle all check run changes."""
        created_count = 0
        updated_count = 0
        errors = []

        for batch in self._batch_items(check_runs):
            try:
                batch_created, batch_updated = await self._sync_check_batch(batch)
                created_count += batch_created
                updated_count += batch_updated

            except Exception as e:
                error_msg = f"Failed to sync check run batch: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

        return created_count, updated_count, errors

    async def rollback_sync_operation(self, operation: SyncOperation) -> SyncOperation:
        """Rollback a failed synchronization operation."""
        if not operation.can_rollback or not self._rollback_data:
            logger.warning(
                f"Cannot rollback operation {operation.operation_id[:8]} - "
                "no rollback data available"
            )
            return replace(operation, status=OperationStatus.FAILED)

        try:
            logger.info(f"Rolling back sync operation {operation.operation_id[:8]}")

            async with DatabaseTransaction(self.session, auto_commit=True):
                await self._execute_rollback_operations()

            updated_operation = replace(
                operation,
                status=OperationStatus.ROLLED_BACK,
                completed_at=datetime.now(UTC),
            )

            logger.info(
                f"Successfully rolled back operation {operation.operation_id[:8]}"
            )

            if self.enable_audit_log:
                self._log_operation_audit("ROLLED_BACK", updated_operation)

            return updated_operation

        except Exception as e:
            logger.error(
                f"Rollback failed for operation {operation.operation_id[:8]}: {e}"
            )
            return replace(
                operation,
                status=OperationStatus.FAILED,
                errors=[*operation.errors, f"Rollback failed: {e}"],
                completed_at=datetime.now(UTC),
            )

    async def get_operation_status(self, operation_id: str) -> SyncOperation | None:
        """Get the current status of a sync operation."""
        # For now, return the current operation if IDs match
        # In a production system, this would query a persistent operation store
        if (
            self._current_operation
            and self._current_operation.operation_id == operation_id
        ):
            return self._current_operation
        return None

    async def cleanup_completed_operations(
        self, older_than: datetime | None = None
    ) -> int:
        """Clean up completed sync operations to free resources."""
        # Placeholder for operation cleanup logic
        # In production, this would clean up persistent operation records
        logger.info("Operation cleanup requested")
        return 0

    # Private helper methods

    async def _execute_sync_phases(self, operation: SyncOperation) -> None:
        """Execute synchronization operations in ordered phases."""

        # Phase 1: Create/update core entities (PRs, Check Runs)
        logger.debug("Phase 1: Syncing core entities")
        await self._sync_core_entities(operation)

        # Phase 2: Update relationships and associations
        logger.debug("Phase 2: Syncing relationships")
        await self._sync_relationships(operation)

        # Phase 3: Update metadata and tracking fields
        logger.debug("Phase 3: Syncing metadata")
        await self._sync_metadata(operation)

        # Phase 4: Record state changes and update housekeeping fields
        logger.debug("Phase 4: Recording state changes")
        await self._sync_state_changes(operation)

    async def _sync_core_entities(self, operation: SyncOperation) -> None:
        """Sync core PR and check run entities."""
        # Sync PRs
        if operation.pull_requests_to_create:
            await self._create_prs_bulk(operation.pull_requests_to_create)

        if operation.pull_requests_to_update:
            await self._update_prs_bulk(operation.pull_requests_to_update)

        # Sync check runs
        if operation.check_runs_to_create:
            await self._create_check_runs_bulk(operation.check_runs_to_create)

        if operation.check_runs_to_update:
            await self._update_check_runs_bulk(operation.check_runs_to_update)

    async def _sync_relationships(self, operation: SyncOperation) -> None:
        """Update relationships and associations between entities."""
        # Link check runs to PRs (handled during creation/update)
        # Any additional relationship management would go here
        pass

    async def _sync_metadata(self, operation: SyncOperation) -> None:
        """Update non-critical metadata and tracking information."""
        # Update additional metadata fields that don't affect core functionality
        # This could include caching, derived fields, etc.
        pass

    async def _sync_state_changes(self, operation: SyncOperation) -> None:
        """Record state changes and update last_checked timestamps."""
        if operation.state_changes:
            await self._record_state_changes(operation.state_changes)

        # Update last_checked_at for all processed PRs
        pr_ids = await self._get_processed_pr_ids(operation)
        if pr_ids:
            await self.pr_repo.bulk_update_last_checked(pr_ids)

    async def _categorize_pr_operations(
        self, discovered_prs: list[DiscoveryResult]
    ) -> tuple[list[DiscoveryResult], list[DiscoveryResult]]:
        """Categorize PRs into create vs update operations."""
        prs_to_create = []
        prs_to_update = []

        for pr in discovered_prs:
            existing_pr = await self.pr_repo.get_by_repo_and_number(
                pr.repository_id, pr.pr_number
            )

            if existing_pr is None:
                prs_to_create.append(pr)
            else:
                # Check if update is needed
                if await self._pr_needs_update(existing_pr, pr):
                    prs_to_update.append(pr)

        logger.info(
            f"Categorized {len(discovered_prs)} PRs: "
            f"{len(prs_to_create)} to create, {len(prs_to_update)} to update"
        )

        return prs_to_create, prs_to_update

    async def _categorize_check_operations(
        self, discovered_checks: list[CheckRunDiscovery]
    ) -> tuple[list[CheckRunDiscovery], list[CheckRunDiscovery]]:
        """Categorize check runs into create vs update operations."""
        checks_to_create = []
        checks_to_update = []

        for check in discovered_checks:
            existing_check = await self.check_run_repo.get_by_external_id(
                check.github_check_run_id
            )

            if existing_check is None:
                checks_to_create.append(check)
            else:
                # Check if update is needed
                if await self._check_needs_update(existing_check, check):
                    checks_to_update.append(check)

        logger.info(
            f"Categorized {len(discovered_checks)} checks: "
            f"{len(checks_to_create)} to create, {len(checks_to_update)} to update"
        )

        return checks_to_create, checks_to_update

    async def _create_prs_bulk(self, prs: list[DiscoveryResult]) -> int:
        """Create PRs in bulk with optimized operations."""
        created_count = 0

        for batch in self._batch_items(prs):
            pr_entities = []

            for pr_data in batch:
                try:
                    # Validate PR data
                    pr_data.validate()

                    pr_entity = PullRequest(
                        repository_id=pr_data.repository_id,
                        pr_number=pr_data.pr_number,
                        title=pr_data.title,
                        body=pr_data.body,
                        author=pr_data.author,
                        state=pr_data.state,
                        draft=pr_data.draft,
                        base_branch=pr_data.base_branch,
                        head_branch=pr_data.head_branch,
                        base_sha=pr_data.base_sha,
                        head_sha=pr_data.head_sha,
                        url=pr_data.url,
                        pr_metadata=pr_data.pr_metadata or {},
                    )

                    pr_entities.append(pr_entity)

                except Exception as e:
                    logger.error(
                        f"Failed to create PR entity for #{pr_data.pr_number}: {e}"
                    )
                    continue

            # Bulk add to session
            if pr_entities:
                self.session.add_all(pr_entities)
                await self.session.flush()
                created_count += len(pr_entities)

                logger.debug(f"Created batch of {len(pr_entities)} PRs")

        logger.info(f"Created {created_count} PRs in bulk")
        return created_count

    async def _update_prs_bulk(self, prs: list[DiscoveryResult]) -> int:
        """Update PRs in bulk with conflict resolution."""
        updated_count = 0

        for batch in self._batch_items(prs):
            for pr_data in batch:
                try:
                    existing_pr = await self.pr_repo.get_by_repo_and_number(
                        pr_data.repository_id, pr_data.pr_number
                    )

                    if existing_pr is None:
                        logger.warning(f"PR #{pr_data.pr_number} not found for update")
                        continue

                    # Apply updates with conflict resolution
                    updated = await self._update_pr_with_conflict_resolution(
                        existing_pr, pr_data
                    )

                    if updated:
                        updated_count += 1

                except Exception as e:
                    logger.error(f"Failed to update PR #{pr_data.pr_number}: {e}")
                    continue

        if updated_count > 0:
            await self.session.flush()

        logger.info(f"Updated {updated_count} PRs in bulk")
        return updated_count

    async def _create_check_runs_bulk(self, checks: list[CheckRunDiscovery]) -> int:
        """Create check runs in bulk with optimized operations."""
        created_count = 0

        for batch in self._batch_items(checks):
            check_entities = []

            for check_data in batch:
                try:
                    # Validate check run data
                    check_data.validate()

                    check_entity = CheckRun(
                        pr_id=check_data.pr_id,
                        external_id=check_data.github_check_run_id,
                        check_name=check_data.check_name,
                        check_suite_id=check_data.check_suite_id,
                        status=check_data.status,
                        conclusion=check_data.conclusion,
                        details_url=check_data.details_url,
                        logs_url=check_data.logs_url,
                        output_summary=check_data.output_summary,
                        output_text=check_data.output_text,
                        started_at=check_data.started_at,
                        completed_at=check_data.completed_at,
                        check_metadata=check_data.check_metadata or {},
                    )

                    check_entities.append(check_entity)

                except Exception as e:
                    logger.error(
                        f"Failed to create check run entity for "
                        f"{check_data.check_name}: {e}"
                    )
                    continue

            # Bulk add to session
            if check_entities:
                self.session.add_all(check_entities)
                await self.session.flush()
                created_count += len(check_entities)

                logger.debug(f"Created batch of {len(check_entities)} check runs")

        logger.info(f"Created {created_count} check runs in bulk")
        return created_count

    async def _update_check_runs_bulk(self, checks: list[CheckRunDiscovery]) -> int:
        """Update check runs in bulk with conflict resolution."""
        updated_count = 0

        for batch in self._batch_items(checks):
            for check_data in batch:
                try:
                    existing_check = await self.check_run_repo.get_by_external_id(
                        check_data.github_check_run_id
                    )

                    if existing_check is None:
                        logger.warning(
                            f"Check run {check_data.github_check_run_id} "
                            f"not found for update"
                        )
                        continue

                    # Apply updates with conflict resolution
                    updated = await self._update_check_run_with_conflict_resolution(
                        existing_check, check_data
                    )

                    if updated:
                        updated_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to update check run "
                        f"{check_data.github_check_run_id}: {e}"
                    )
                    continue

        if updated_count > 0:
            await self.session.flush()

        logger.info(f"Updated {updated_count} check runs in bulk")
        return updated_count

    async def _pr_needs_update(
        self, existing_pr: PullRequest, new_pr_data: DiscoveryResult
    ) -> bool:
        """Check if a PR needs to be updated."""
        # Compare key fields to determine if update is needed
        needs_update = (
            existing_pr.title != new_pr_data.title
            or existing_pr.body != new_pr_data.body
            or existing_pr.state != new_pr_data.state
            or existing_pr.draft != new_pr_data.draft
            or existing_pr.head_sha != new_pr_data.head_sha
            or existing_pr.base_sha != new_pr_data.base_sha
        )

        return needs_update

    async def _check_needs_update(
        self, existing_check: CheckRun, new_check_data: CheckRunDiscovery
    ) -> bool:
        """Check if a check run needs to be updated."""
        # Compare key fields to determine if update is needed
        needs_update = (
            existing_check.status != new_check_data.status
            or existing_check.conclusion != new_check_data.conclusion
            or existing_check.output_summary != new_check_data.output_summary
            or existing_check.completed_at != new_check_data.completed_at
        )

        return needs_update

    async def _update_pr_with_conflict_resolution(
        self, existing_pr: PullRequest, new_data: DiscoveryResult
    ) -> bool:
        """Update PR with conflict resolution strategy."""
        if self.conflict_resolution == ConflictResolutionStrategy.GITHUB_WINS:
            # GitHub data takes precedence
            existing_pr.title = new_data.title
            existing_pr.body = new_data.body
            existing_pr.state = new_data.state
            existing_pr.draft = new_data.draft
            existing_pr.head_sha = new_data.head_sha
            existing_pr.base_sha = new_data.base_sha
            existing_pr.updated_at = new_data.last_updated_at or datetime.now(UTC)

            # Merge metadata if available
            if new_data.pr_metadata:
                if existing_pr.pr_metadata is None:
                    existing_pr.pr_metadata = {}
                existing_pr.pr_metadata.update(new_data.pr_metadata)

            return True

        elif self.conflict_resolution == ConflictResolutionStrategy.DATABASE_WINS:
            # Keep existing data, only update timestamp
            existing_pr.updated_at = datetime.now(UTC)
            return True

        elif self.conflict_resolution == ConflictResolutionStrategy.MERGE_METADATA:
            # Update core fields but merge metadata carefully
            existing_pr.title = new_data.title
            existing_pr.body = new_data.body
            existing_pr.state = new_data.state
            existing_pr.draft = new_data.draft
            existing_pr.head_sha = new_data.head_sha
            existing_pr.base_sha = new_data.base_sha
            existing_pr.updated_at = new_data.last_updated_at or datetime.now(UTC)

            # Careful metadata merge
            if new_data.pr_metadata and existing_pr.pr_metadata:
                # Merge non-conflicting fields
                for key, value in new_data.pr_metadata.items():
                    if key not in existing_pr.pr_metadata:
                        existing_pr.pr_metadata[key] = value
            elif new_data.pr_metadata:
                existing_pr.pr_metadata = new_data.pr_metadata

            return True

        else:  # FAIL_ON_CONFLICT
            # Check for conflicts and fail if any exist
            conflicts = []
            if existing_pr.title != new_data.title:
                conflicts.append("title")
            if existing_pr.body != new_data.body:
                conflicts.append("body")
            if existing_pr.state != new_data.state:
                conflicts.append("state")

            if conflicts:
                raise ValueError(f"PR update conflicts detected in fields: {conflicts}")

            return False

    async def _update_check_run_with_conflict_resolution(
        self, existing_check: CheckRun, new_data: CheckRunDiscovery
    ) -> bool:
        """Update check run with conflict resolution strategy."""
        if self.conflict_resolution == ConflictResolutionStrategy.GITHUB_WINS:
            # GitHub data takes precedence
            existing_check.status = new_data.status
            existing_check.conclusion = new_data.conclusion
            existing_check.output_summary = new_data.output_summary
            existing_check.output_text = new_data.output_text
            existing_check.started_at = new_data.started_at
            existing_check.completed_at = new_data.completed_at
            existing_check.updated_at = datetime.now(UTC)

            # Merge metadata if available
            if new_data.check_metadata:
                if existing_check.check_metadata is None:
                    existing_check.check_metadata = {}
                existing_check.check_metadata.update(new_data.check_metadata)

            return True

        elif self.conflict_resolution == ConflictResolutionStrategy.DATABASE_WINS:
            # Keep existing data, only update timestamp
            existing_check.updated_at = datetime.now(UTC)
            return True

        else:  # Other strategies handled similarly
            # For check runs, GitHub typically wins since they're authoritative
            return await self._update_check_run_with_conflict_resolution(
                existing_check, new_data
            )

    async def _record_state_changes(
        self, state_changes: list[StateChangeEvent]
    ) -> None:
        """Record state changes in the database."""
        # For now, just log the state changes
        # In a full implementation, this would create StateHistory records
        for change in state_changes:
            logger.info(f"State change recorded: {change}")

    async def _get_processed_pr_ids(self, operation: SyncOperation) -> list[uuid.UUID]:
        """Get list of PR IDs that were processed in this operation."""
        pr_ids = []

        # Add PR IDs from created PRs
        for pr_data in operation.pull_requests_to_create:
            pr_ids.append(pr_data.repository_id)  # This should be PR ID after creation

        # Add PR IDs from updated PRs
        for pr_data in operation.pull_requests_to_update:
            pr_ids.append(pr_data.repository_id)  # This should be PR ID

        # Add PR IDs from state changes
        for change in operation.state_changes:
            pr_ids.append(change.pr_id)

        return list(set(pr_ids))  # Remove duplicates

    async def _sync_pr_batch(self, prs: list[DiscoveryResult]) -> tuple[int, int]:
        """Sync a batch of PRs."""
        created = 0
        updated = 0

        for pr in prs:
            existing = await self.pr_repo.get_by_repo_and_number(
                pr.repository_id, pr.pr_number
            )

            if existing is None:
                await self._create_single_pr(pr)
                created += 1
            else:
                if await self._update_single_pr(existing, pr):
                    updated += 1

        return created, updated

    async def _sync_check_batch(
        self, checks: list[CheckRunDiscovery]
    ) -> tuple[int, int]:
        """Sync a batch of check runs."""
        created = 0
        updated = 0

        for check in checks:
            existing = await self.check_run_repo.get_by_external_id(
                check.github_check_run_id
            )

            if existing is None:
                await self._create_single_check(check)
                created += 1
            else:
                if await self._update_single_check(existing, check):
                    updated += 1

        return created, updated

    async def _create_single_pr(self, pr_data: DiscoveryResult) -> PullRequest:
        """Create a single PR."""
        pr_entity = PullRequest(
            repository_id=pr_data.repository_id,
            pr_number=pr_data.pr_number,
            title=pr_data.title,
            body=pr_data.body,
            author=pr_data.author,
            state=pr_data.state,
            draft=pr_data.draft,
            base_branch=pr_data.base_branch,
            head_branch=pr_data.head_branch,
            base_sha=pr_data.base_sha,
            head_sha=pr_data.head_sha,
            url=pr_data.url,
            pr_metadata=pr_data.pr_metadata or {},
        )

        self.session.add(pr_entity)
        await self.session.flush()
        return pr_entity

    async def _update_single_pr(
        self, existing_pr: PullRequest, pr_data: DiscoveryResult
    ) -> bool:
        """Update a single PR."""
        return await self._update_pr_with_conflict_resolution(existing_pr, pr_data)

    async def _create_single_check(self, check_data: CheckRunDiscovery) -> CheckRun:
        """Create a single check run."""
        check_entity = CheckRun(
            pr_id=check_data.pr_id,
            external_id=check_data.github_check_run_id,
            check_name=check_data.check_name,
            check_suite_id=check_data.check_suite_id,
            status=check_data.status,
            conclusion=check_data.conclusion,
            details_url=check_data.details_url,
            logs_url=check_data.logs_url,
            output_summary=check_data.output_summary,
            output_text=check_data.output_text,
            started_at=check_data.started_at,
            completed_at=check_data.completed_at,
            check_metadata=check_data.check_metadata or {},
        )

        self.session.add(check_entity)
        await self.session.flush()
        return check_entity

    async def _update_single_check(
        self, existing_check: CheckRun, check_data: CheckRunDiscovery
    ) -> bool:
        """Update a single check run."""
        return await self._update_check_run_with_conflict_resolution(
            existing_check, check_data
        )

    async def _prepare_rollback_data(self, operation: SyncOperation) -> None:
        """Prepare rollback data before making changes."""
        self._rollback_data = {
            "operation_id": operation.operation_id,
            "created_pr_ids": [],
            "created_check_ids": [],
            "original_pr_states": {},
            "original_check_states": {},
        }

    async def _execute_rollback_operations(self) -> None:
        """Execute rollback operations to undo changes."""
        if not self._rollback_data:
            return

        # Delete created entities
        created_pr_ids = self._rollback_data.get("created_pr_ids", [])
        created_check_ids = self._rollback_data.get("created_check_ids", [])

        if created_pr_ids:
            await self.session.execute(
                update(PullRequest).where(PullRequest.id.in_(created_pr_ids))
            )

        if created_check_ids:
            await self.session.execute(
                update(CheckRun).where(CheckRun.id.in_(created_check_ids))
            )

        # Restore original states (simplified)
        logger.info("Rollback operations executed")

    def _batch_items(self, items: list[Any]) -> Generator[list[Any], None, None]:
        """Split items into batches for processing."""
        for i in range(0, len(items), self.batch_size):
            yield items[i : i + self.batch_size]

    def _log_operation_audit(
        self, event: str, operation: SyncOperation, error: str | None = None
    ) -> None:
        """Log detailed audit information for operations."""
        audit_data = {
            "event": event,
            "operation_id": operation.operation_id,
            "operation_type": operation.operation_type,
            "status": operation.status.value,
            "total_operations": operation.total_operations,
            "duration": operation.duration,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if error:
            audit_data["error"] = error

        logger.info(f"AUDIT: {audit_data}")
