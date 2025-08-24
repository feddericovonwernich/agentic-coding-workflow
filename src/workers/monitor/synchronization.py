"""Database synchronization logic for PR monitoring changes."""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.transactions import TransactionError, database_transaction
from src.models import CheckRun, PRState, PullRequest, TriggerEvent
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.state_history import PRStateHistoryRepository

from .models import ChangeSet, CheckRunChangeRecord, PRChangeRecord

logger = logging.getLogger(__name__)


class DataSynchronizer(ABC):
    """Abstract base class for database synchronization operations."""

    @abstractmethod
    async def synchronize_changes(
        self, repository_id: uuid.UUID, changeset: ChangeSet
    ) -> int:
        """
        Synchronize all changes in a changeset to the database.

        Args:
            repository_id: UUID of the repository
            changeset: Collection of changes to synchronize

        Returns:
            Number of changes successfully synchronized
        """
        pass

    @abstractmethod
    async def create_new_prs(self, new_prs: list[PRChangeRecord]) -> list[PullRequest]:
        """
        Create new pull request records in the database.

        Args:
            new_prs: List of new PR change records

        Returns:
            List of created PullRequest entities
        """
        pass

    @abstractmethod
    async def update_existing_prs(
        self, updated_prs: list[PRChangeRecord]
    ) -> list[PullRequest]:
        """
        Update existing pull request records in the database.

        Args:
            updated_prs: List of updated PR change records

        Returns:
            List of updated PullRequest entities
        """
        pass

    @abstractmethod
    async def create_new_check_runs(
        self, new_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """
        Create new check run records in the database.

        Args:
            new_checks: List of new check run change records

        Returns:
            List of created CheckRun entities
        """
        pass

    @abstractmethod
    async def update_existing_check_runs(
        self, updated_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """
        Update existing check run records in the database.

        Args:
            updated_checks: List of updated check run change records

        Returns:
            List of updated CheckRun entities
        """
        pass


class DatabaseSynchronizer(DataSynchronizer):
    """Implementation of database synchronization with transactional support."""

    def __init__(self, session: AsyncSession):
        """
        Initialize synchronizer with database session.

        Args:
            session: Database session for operations
        """
        self.session = session
        self.pr_repo = PullRequestRepository(session)
        self.check_repo = CheckRunRepository(session)
        self.history_repo = PRStateHistoryRepository(session)

    async def synchronize_changes(
        self, repository_id: uuid.UUID, changeset: ChangeSet
    ) -> int:
        """
        Synchronize all changes in a changeset within a single transaction.

        Why: Ensures data consistency by wrapping all changes in a transaction
        What: Processes all PR and check run changes atomically
        How: Uses database transaction context manager with rollback on errors
        """
        if not changeset.has_changes:
            logger.info(f"No changes to synchronize for repository {repository_id}")
            return 0

        total_synchronized = 0

        try:
            async with database_transaction(self.session) as tx_session:
                logger.info(
                    f"Starting synchronization for repository {repository_id}: "
                    f"{changeset.total_changes} total changes"
                )

                # Create new PRs first (needed for foreign key relationships)
                if changeset.new_prs:
                    created_prs = await self._create_new_prs_bulk(changeset.new_prs)
                    total_synchronized += len(created_prs)
                    logger.debug(f"Created {len(created_prs)} new PRs")

                # Update existing PRs
                if changeset.updated_prs:
                    updated_prs = await self._update_existing_prs_bulk(
                        changeset.updated_prs
                    )
                    total_synchronized += len(updated_prs)
                    logger.debug(f"Updated {len(updated_prs)} existing PRs")

                # Create new check runs
                if changeset.new_check_runs:
                    created_checks = await self._create_new_check_runs_bulk(
                        changeset.new_check_runs
                    )
                    total_synchronized += len(created_checks)
                    logger.debug(f"Created {len(created_checks)} new check runs")

                # Update existing check runs
                if changeset.updated_check_runs:
                    updated_checks = await self._update_existing_check_runs_bulk(
                        changeset.updated_check_runs
                    )
                    total_synchronized += len(updated_checks)
                    logger.debug(f"Updated {len(updated_checks)} existing check runs")

                # Ensure all changes are flushed to database
                await tx_session.flush()

                logger.info(
                    f"Successfully synchronized {total_synchronized} changes "
                    f"for repository {repository_id}"
                )

                return total_synchronized

        except SQLAlchemyError as e:
            logger.error(
                f"Database error during synchronization for repository "
                f"{repository_id}: {e}"
            )
            raise TransactionError(f"Synchronization failed: {e}") from e
        except Exception as e:
            logger.error(
                f"Unexpected error during synchronization for repository "
                f"{repository_id}: {e}"
            )
            raise TransactionError(f"Synchronization failed unexpectedly: {e}") from e

    async def create_new_prs(self, new_prs: list[PRChangeRecord]) -> list[PullRequest]:
        """
        Create new pull request records using bulk operations.

        Why: Efficiently creates multiple PRs in a single database operation
        What: Converts PR change records to database entities
        How: Uses bulk insert with PostgreSQL ON CONFLICT handling
        """
        if not new_prs:
            return []

        return await self._create_new_prs_bulk(new_prs)

    async def update_existing_prs(
        self, updated_prs: list[PRChangeRecord]
    ) -> list[PullRequest]:
        """
        Update existing pull request records using bulk operations.

        Why: Efficiently updates multiple PRs with minimal database round trips
        What: Updates changed fields and creates state history records
        How: Uses individual updates to handle state transitions properly
        """
        if not updated_prs:
            return []

        return await self._update_existing_prs_bulk(updated_prs)

    async def create_new_check_runs(
        self, new_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """
        Create new check run records using bulk operations.

        Why: Efficiently creates multiple check runs in a single operation
        What: Converts check run change records to database entities
        How: Uses bulk insert with conflict resolution
        """
        if not new_checks:
            return []

        return await self._create_new_check_runs_bulk(new_checks)

    async def update_existing_check_runs(
        self, updated_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """
        Update existing check run records using bulk operations.

        Why: Efficiently updates check run status and timing information
        What: Updates changed fields like status, conclusion, timing
        How: Uses bulk update operations grouped by change type
        """
        if not updated_checks:
            return []

        return await self._update_existing_check_runs_bulk(updated_checks)

    async def _create_new_prs_bulk(
        self, new_prs: list[PRChangeRecord]
    ) -> list[PullRequest]:
        """Create new PRs using bulk insert operations."""
        if not new_prs:
            return []

        # Prepare bulk insert data
        pr_data = []
        for pr_change in new_prs:
            pr = pr_change.pr_data

            # Extract repository_id from raw_data or use a default for testing
            repo_id = pr_change.pr_data.raw_data.get("repository_id")
            if isinstance(repo_id, str):
                repo_id = uuid.UUID(repo_id)
            elif repo_id is None:
                # This should be set by the caller, but provide a fallback for tests
                repo_id = uuid.uuid4()

            pr_data.append(
                {
                    "id": uuid.uuid4(),
                    "repository_id": repo_id,
                    "pr_number": pr.number,
                    "title": pr.title,
                    "author": pr.author,
                    "state": pr.to_pr_state(),
                    "draft": pr.draft,
                    "base_branch": pr.base_branch,
                    "head_branch": pr.head_branch,
                    "base_sha": pr.base_sha,
                    "head_sha": pr.head_sha,
                    "url": pr.url,
                    "body": pr.body,
                    "pr_metadata": pr.get_metadata_dict(),
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            )

        # Use PostgreSQL UPSERT to handle potential conflicts
        stmt = pg_insert(PullRequest).values(pr_data)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["repository_id", "pr_number"]
        )

        await self.session.execute(stmt)
        await self.session.flush()

        # Retrieve created PRs (needed for relationship setup)
        created_prs = []
        for pr_change in new_prs:
            # Extract repository_id consistently
            repo_id = pr_change.pr_data.raw_data.get("repository_id")
            if isinstance(repo_id, str):
                repo_id = uuid.UUID(repo_id)
            elif repo_id is None:
                continue  # Skip if no repository_id available

            created_pr = await self.pr_repo.get_by_repo_and_number(
                repository_id=repo_id, pr_number=pr_change.pr_data.number
            )
            if created_pr:
                created_prs.append(created_pr)

                # Create initial state history record
                await self.history_repo.create_transition(
                    pr_id=created_pr.id,
                    old_state=None,
                    new_state=created_pr.state,
                    trigger_event=TriggerEvent.OPENED,
                    triggered_by="system",
                    metadata={"source": "github_sync", "initial_creation": True},
                )

        logger.debug(f"Created {len(created_prs)} new PRs via bulk insert")
        return created_prs

    async def _update_existing_prs_bulk(
        self, updated_prs: list[PRChangeRecord]
    ) -> list[PullRequest]:
        """Update existing PRs with proper state transition handling."""
        if not updated_prs:
            return []

        updated_results = []

        # Process each PR individually to handle state transitions properly
        for pr_change in updated_prs:
            if not pr_change.existing_pr_id:
                logger.warning(
                    f"No existing PR ID for update: {pr_change.pr_data.number}"
                )
                continue

            try:
                existing_pr = await self.pr_repo.get_by_id(pr_change.existing_pr_id)
                if not existing_pr:
                    logger.warning(
                        f"PR not found for update: {pr_change.existing_pr_id}"
                    )
                    continue

                # Build update fields
                update_fields: dict[str, Any] = {"updated_at": datetime.now(UTC)}

                if (
                    pr_change.title_changed
                    and pr_change.pr_data.title != existing_pr.title
                ):
                    update_fields["title"] = pr_change.pr_data.title

                if (
                    pr_change.draft_changed
                    and pr_change.pr_data.draft != existing_pr.draft
                ):
                    update_fields["draft"] = pr_change.pr_data.draft

                if pr_change.sha_changed:
                    if pr_change.pr_data.head_sha != existing_pr.head_sha:
                        update_fields["head_sha"] = pr_change.pr_data.head_sha
                    if pr_change.pr_data.base_sha != existing_pr.base_sha:
                        update_fields["base_sha"] = pr_change.pr_data.base_sha

                if pr_change.metadata_changed:
                    update_fields["pr_metadata"] = pr_change.pr_data.get_metadata_dict()

                # Apply basic field updates
                if len(update_fields) > 1:  # More than just updated_at
                    updated_pr = await self.pr_repo.update(existing_pr, **update_fields)
                else:
                    updated_pr = existing_pr

                # Handle state changes separately with state history
                if pr_change.state_changed and pr_change.old_state:
                    new_state = pr_change.pr_data.to_pr_state()
                    if new_state != existing_pr.state:
                        # Determine trigger event based on state transition
                        trigger_event = self._determine_trigger_event(
                            existing_pr.state, new_state
                        )

                        updated_pr = await self.pr_repo.update_state(
                            pr_id=existing_pr.id,
                            new_state=new_state,
                            trigger_event=trigger_event,
                            metadata={
                                "source": "github_sync",
                                "old_sha": getattr(pr_change, "old_head_sha", None),
                                "new_sha": pr_change.pr_data.head_sha,
                            },
                        )

                updated_results.append(updated_pr)

            except Exception as e:
                logger.error(f"Error updating PR {pr_change.existing_pr_id}: {e}")
                # Continue with other PRs rather than failing the entire batch
                continue

        logger.debug(f"Updated {len(updated_results)} existing PRs")
        return updated_results

    async def _create_new_check_runs_bulk(
        self, new_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """Create new check runs using bulk insert operations."""
        if not new_checks:
            return []

        # Prepare bulk insert data
        check_data = []
        for check_change in new_checks:
            check = check_change.check_data
            check_data.append(
                {
                    "id": uuid.uuid4(),
                    "pr_id": check_change.pr_id,
                    "external_id": check.external_id,
                    "check_name": check.check_name,
                    "check_suite_id": check.check_suite_id,
                    "status": check.to_check_status(),
                    "conclusion": check.to_check_conclusion(),
                    "details_url": check.details_url,
                    "logs_url": check.logs_url,
                    "output_summary": check.output_summary,
                    "output_text": check.output_text,
                    "started_at": check.started_at,
                    "completed_at": check.completed_at,
                    "check_metadata": check.get_metadata_dict(),
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            )

        # Use PostgreSQL UPSERT to handle potential conflicts on external_id
        stmt = pg_insert(CheckRun).values(check_data)
        stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"])

        await self.session.execute(stmt)
        await self.session.flush()

        # Retrieve created check runs
        created_checks = []
        for check_change in new_checks:
            check_run = await self.check_repo.get_by_external_id(
                check_change.check_data.external_id
            )
            if check_run:
                created_checks.append(check_run)

        logger.debug(f"Created {len(created_checks)} new check runs via bulk insert")
        return created_checks

    async def _update_existing_check_runs_bulk(
        self, updated_checks: list[CheckRunChangeRecord]
    ) -> list[CheckRun]:
        """Update existing check runs using bulk operations grouped by change type."""
        if not updated_checks:
            return []

        updated_results = []

        # Group updates by type for more efficient processing
        status_updates = []
        conclusion_updates = []
        timing_updates = []

        for check_change in updated_checks:
            if not check_change.existing_check_id:
                continue

            if check_change.status_changed:
                status_updates.append(check_change)

            if check_change.conclusion_changed:
                conclusion_updates.append(check_change)

            if check_change.timing_changed:
                timing_updates.append(check_change)

        # Process status updates in bulk
        if status_updates:
            for check_change in status_updates:
                try:
                    if check_change.existing_check_id is None:
                        continue
                    check_run = await self.check_repo.get_by_id(
                        check_change.existing_check_id
                    )
                    if check_run:
                        updated_check = await self.check_repo.update_status(
                            check_run_id=check_run.id,
                            status=check_change.check_data.to_check_status(),
                            conclusion=check_change.check_data.to_check_conclusion(),
                            metadata={
                                "source": "github_sync",
                                "update_type": "status_change",
                            },
                        )
                        updated_results.append(updated_check)
                except Exception as e:
                    logger.error(
                        f"Error updating check run status "
                        f"{check_change.existing_check_id}: {e}"
                    )

        # Process timing updates
        if timing_updates:
            timing_ids = [
                c.existing_check_id for c in timing_updates if c.existing_check_id
            ]
            if timing_ids:
                # Build update values for timing
                timing_update_data = {}
                for check_change in timing_updates:
                    if check_change.existing_check_id:
                        timing_update_data[check_change.existing_check_id] = {
                            "started_at": check_change.check_data.started_at,
                            "completed_at": check_change.check_data.completed_at,
                            "updated_at": datetime.now(UTC),
                        }

                # Apply timing updates individually
                # (SQLAlchemy doesn't support bulk updates with different values easily)
                for check_id, update_data in timing_update_data.items():
                    try:
                        check_run = await self.check_repo.get_by_id(check_id)
                        if check_run:
                            updated_check = await self.check_repo.update(
                                check_run, **update_data
                            )
                            if updated_check not in updated_results:
                                updated_results.append(updated_check)
                    except Exception as e:
                        logger.error(f"Error updating check run timing {check_id}: {e}")

        logger.debug(f"Updated {len(updated_results)} existing check runs")
        return updated_results

    def _determine_trigger_event(
        self, old_state: PRState, new_state: PRState
    ) -> TriggerEvent:
        """Determine the appropriate trigger event for a state transition."""
        if old_state == PRState.OPENED and new_state == PRState.CLOSED:
            return TriggerEvent.CLOSED
        elif old_state == PRState.OPENED and new_state == PRState.MERGED:
            return TriggerEvent.CLOSED  # Merged is considered closed
        elif old_state == PRState.CLOSED and new_state == PRState.OPENED:
            return TriggerEvent.REOPENED
        else:
            return TriggerEvent.SYNCHRONIZE  # Default for other transitions
