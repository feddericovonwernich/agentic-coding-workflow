"""Data synchronization logic for updating database with GitHub changes."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CheckRun, PullRequest
from src.models.enums import TriggerEvent
from src.repositories import CheckRunRepository, PullRequestRepository

from .models import ChangeSet, ProcessingError

logger = logging.getLogger(__name__)


class DataSynchronizer:
    """Synchronizes detected changes to the database."""
    
    def __init__(
        self,
        session: AsyncSession,
        pr_repo: Optional[PullRequestRepository] = None,
        check_repo: Optional[CheckRunRepository] = None
    ):
        """Initialize data synchronizer.
        
        Args:
            session: Database session
            pr_repo: Pull request repository (created if None)
            check_repo: Check run repository (created if None)
        """
        self.session = session
        self.pr_repo = pr_repo or PullRequestRepository(session)
        self.check_repo = check_repo or CheckRunRepository(session)
    
    async def synchronize_changes(
        self,
        repository_id: uuid.UUID,
        change_set: ChangeSet
    ) -> list[ProcessingError]:
        """Synchronize change set to database.
        
        Args:
            repository_id: Repository ID for new entities
            change_set: Changes to synchronize
            
        Returns:
            List of processing errors that occurred
        """
        errors: list[ProcessingError] = []
        
        if not change_set.has_changes:
            logger.debug("No changes to synchronize")
            return errors
        
        try:
            async with self.session.begin():
                # Process new PRs first
                for pr in change_set.new_prs:
                    try:
                        pr.repository_id = repository_id
                        await self._create_pr(pr)
                        logger.info(f"Created new PR #{pr.pr_number}")
                    except Exception as e:
                        error = ProcessingError(
                            error_type="pr_creation_error",
                            message=f"Failed to create PR #{pr.pr_number}: {e}",
                            details={"pr_id": str(pr.id), "pr_number": pr.pr_number}
                        )
                        errors.append(error)
                        logger.error(f"Failed to create PR #{pr.pr_number}: {e}")
                
                # Process updated PRs
                for pr in change_set.updated_prs:
                    try:
                        await self._update_pr(pr)
                        logger.debug(f"Updated PR #{pr.pr_number}")
                    except Exception as e:
                        error = ProcessingError(
                            error_type="pr_update_error",
                            message=f"Failed to update PR #{pr.pr_number}: {e}",
                            details={"pr_id": str(pr.id), "pr_number": pr.pr_number}
                        )
                        errors.append(error)
                        logger.error(f"Failed to update PR #{pr.pr_number}: {e}")
                
                # Process new check runs
                for check in change_set.new_check_runs:
                    try:
                        await self._create_check_run(check)
                        logger.debug(f"Created new check run: {check.check_name}")
                    except Exception as e:
                        error = ProcessingError(
                            error_type="check_run_creation_error",
                            message=f"Failed to create check run {check.check_name}: {e}",
                            details={"check_id": str(check.id), "check_name": check.check_name}
                        )
                        errors.append(error)
                        logger.error(f"Failed to create check run {check.check_name}: {e}")
                
                # Process updated check runs
                for check in change_set.updated_check_runs:
                    try:
                        await self._update_check_run(check)
                        logger.debug(f"Updated check run: {check.check_name}")
                    except Exception as e:
                        error = ProcessingError(
                            error_type="check_run_update_error",
                            message=f"Failed to update check run {check.check_name}: {e}",
                            details={"check_id": str(check.id), "check_name": check.check_name}
                        )
                        errors.append(error)
                        logger.error(f"Failed to update check run {check.check_name}: {e}")
                
                # Mark transaction as complete
                await self.session.flush()
                
        except SQLAlchemyError as e:
            error = ProcessingError(
                error_type="database_transaction_error",
                message=f"Database transaction failed: {e}",
                details={"repository_id": str(repository_id)}
            )
            errors.append(error)
            logger.error(f"Database transaction failed: {e}")
            await self.session.rollback()
            
        except Exception as e:
            error = ProcessingError(
                error_type="synchronization_error",
                message=f"Unexpected synchronization error: {e}",
                details={"repository_id": str(repository_id)}
            )
            errors.append(error)
            logger.error(f"Unexpected synchronization error: {e}")
            await self.session.rollback()
        
        if not errors:
            logger.info(
                f"Successfully synchronized {change_set.total_changes} changes "
                f"for repository {repository_id}"
            )
        else:
            logger.warning(
                f"Synchronized with {len(errors)} errors "
                f"for repository {repository_id}"
            )
        
        return errors
    
    async def bulk_update_last_checked(
        self,
        repository_id: uuid.UUID,
        checked_at: Optional[datetime] = None
    ) -> int:
        """Bulk update last_checked_at for all active PRs in repository.
        
        Args:
            repository_id: Repository ID
            checked_at: Timestamp to set (defaults to now)
            
        Returns:
            Number of PRs updated
        """
        if checked_at is None:
            checked_at = datetime.now(UTC)
        
        try:
            # Get all active PR IDs for the repository
            active_prs = await self.pr_repo.get_active_prs_for_repo(repository_id)
            pr_ids = [pr.id for pr in active_prs]
            
            if not pr_ids:
                return 0
            
            # Bulk update
            count = await self.pr_repo.bulk_update_last_checked(pr_ids, checked_at)
            logger.debug(f"Bulk updated last_checked_at for {count} PRs")
            return count
            
        except Exception as e:
            logger.error(f"Failed to bulk update last_checked_at: {e}")
            return 0
    
    async def _create_pr(self, pr: PullRequest) -> PullRequest:
        """Create new PR in database.
        
        Args:
            pr: PR model to create
            
        Returns:
            Created PR model
        """
        # Use repository method to ensure proper validation
        return await self.pr_repo.create(pr)
    
    async def _update_pr(self, pr: PullRequest) -> PullRequest:
        """Update existing PR in database.
        
        Args:
            pr: PR model with updates
            
        Returns:
            Updated PR model
        """
        # Use repository method for updates
        await self.pr_repo.flush()
        await self.pr_repo.refresh(pr)
        return pr
    
    async def _create_check_run(self, check: CheckRun) -> CheckRun:
        """Create new check run in database.
        
        Args:
            check: Check run model to create
            
        Returns:
            Created check run model
        """
        return await self.check_repo.create(check)
    
    async def _update_check_run(self, check: CheckRun) -> CheckRun:
        """Update existing check run in database.
        
        Args:
            check: Check run model with updates
            
        Returns:
            Updated check run model
        """
        await self.check_repo.flush()
        await self.check_repo.refresh(check)
        return check
    
    async def create_state_transition_records(
        self,
        change_set: ChangeSet
    ) -> list[ProcessingError]:
        """Create state history records for significant changes.
        
        Args:
            change_set: Changes to create history for
            
        Returns:
            List of errors that occurred
        """
        errors: list[ProcessingError] = []
        
        try:
            # Create state history for PR state changes
            for state_change in change_set.state_changes:
                if state_change.change_type == "pr_state":
                    try:
                        # Determine trigger event based on change
                        trigger_event = self._determine_trigger_event(
                            state_change.old_value,
                            state_change.new_value
                        )
                        
                        # Create state transition record
                        await self.pr_repo.update_state(
                            pr_id=state_change.entity_id,
                            new_state=state_change.new_value,
                            trigger_event=trigger_event,
                            metadata=state_change.metadata
                        )
                        
                    except Exception as e:
                        error = ProcessingError(
                            error_type="state_history_error",
                            message=f"Failed to create state history record: {e}",
                            details={
                                "change_type": state_change.change_type,
                                "entity_id": str(state_change.entity_id)
                            }
                        )
                        errors.append(error)
                        logger.error(f"Failed to create state history: {e}")
                        
        except Exception as e:
            error = ProcessingError(
                error_type="state_transition_error",
                message=f"Failed to process state transitions: {e}",
                details={}
            )
            errors.append(error)
            logger.error(f"Failed to process state transitions: {e}")
        
        return errors
    
    def _determine_trigger_event(
        self,
        old_state: Any,
        new_state: Any
    ) -> TriggerEvent:
        """Determine trigger event based on state change.
        
        Args:
            old_state: Previous state
            new_state: New state
            
        Returns:
            Appropriate trigger event
        """
        # Map state changes to trigger events
        if old_state is None:
            return TriggerEvent.PR_OPENED
        
        if str(new_state).upper() == "OPENED":
            return TriggerEvent.PR_REOPENED
        elif str(new_state).upper() == "CLOSED":
            return TriggerEvent.PR_CLOSED
        elif str(new_state).upper() == "MERGED":
            return TriggerEvent.PR_MERGED
        else:
            return TriggerEvent.MANUAL_UPDATE