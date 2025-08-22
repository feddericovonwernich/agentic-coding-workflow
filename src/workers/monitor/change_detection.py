"""State change detection for comparing GitHub data with database state."""

import logging
import uuid
from typing import Any, Optional

from src.models import CheckRun, PullRequest
from src.models.enums import TriggerEvent

from .models import ChangeSet, CheckRunData, PRData, StateChange

logger = logging.getLogger(__name__)


class StateChangeDetector:
    """Detects changes between GitHub data and database state."""
    
    def detect_pr_changes(
        self,
        github_pr: PRData,
        existing_pr: Optional[PullRequest]
    ) -> tuple[Optional[PullRequest], list[StateChange]]:
        """Detect changes to a pull request.
        
        Args:
            github_pr: PR data from GitHub
            existing_pr: Existing PR from database (None if new)
            
        Returns:
            Tuple of (updated PR model, list of state changes)
        """
        state_changes: list[StateChange] = []
        
        if existing_pr is None:
            # New PR - create model
            pr_model = PullRequest(
                repository_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # Will be set by caller
                pr_number=github_pr.number,
                title=github_pr.title,
                author=github_pr.author,
                state=github_pr.pr_state,
                draft=github_pr.draft,
                base_branch=github_pr.base_branch,
                head_branch=github_pr.head_branch,
                base_sha=github_pr.base_sha,
                head_sha=github_pr.head_sha,
                url=github_pr.url,
                body=github_pr.body,
                pr_metadata=github_pr.metadata
            )
            
            # Record as new PR change
            state_changes.append(StateChange(
                change_type="new_pr",
                entity_id=pr_model.id,
                old_value=None,
                new_value=github_pr.pr_state,
                metadata={"pr_number": github_pr.number}
            ))
            
            logger.info(f"Detected new PR: #{github_pr.number} in {github_pr.pr_state} state")
            return pr_model, state_changes
        
        # Existing PR - check for changes
        updated_pr = existing_pr
        has_updates = False
        
        # Check state changes
        if existing_pr.state != github_pr.pr_state:
            old_state = existing_pr.state
            state_changes.append(StateChange(
                change_type="pr_state",
                entity_id=existing_pr.id,
                old_value=old_state,
                new_value=github_pr.pr_state,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.state = github_pr.pr_state
            has_updates = True
            logger.info(f"PR #{github_pr.number} state changed: {old_state} → {github_pr.pr_state}")
        
        # Check draft status changes
        if existing_pr.draft != github_pr.draft:
            state_changes.append(StateChange(
                change_type="pr_draft",
                entity_id=existing_pr.id,
                old_value=existing_pr.draft,
                new_value=github_pr.draft,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.draft = github_pr.draft
            has_updates = True
            logger.debug(f"PR #{github_pr.number} draft status changed: {existing_pr.draft} → {github_pr.draft}")
        
        # Check title changes
        if existing_pr.title != github_pr.title:
            state_changes.append(StateChange(
                change_type="pr_title",
                entity_id=existing_pr.id,
                old_value=existing_pr.title,
                new_value=github_pr.title,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.title = github_pr.title
            has_updates = True
            logger.debug(f"PR #{github_pr.number} title changed")
        
        # Check SHA changes (indicates new commits)
        if existing_pr.head_sha != github_pr.head_sha:
            state_changes.append(StateChange(
                change_type="pr_head_sha",
                entity_id=existing_pr.id,
                old_value=existing_pr.head_sha,
                new_value=github_pr.head_sha,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.head_sha = github_pr.head_sha
            has_updates = True
            logger.info(f"PR #{github_pr.number} head SHA updated: {existing_pr.head_sha[:8]} → {github_pr.head_sha[:8]}")
        
        # Check base SHA changes (indicates base branch updates)
        if existing_pr.base_sha != github_pr.base_sha:
            state_changes.append(StateChange(
                change_type="pr_base_sha",
                entity_id=existing_pr.id,
                old_value=existing_pr.base_sha,
                new_value=github_pr.base_sha,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.base_sha = github_pr.base_sha
            has_updates = True
            logger.debug(f"PR #{github_pr.number} base SHA updated")
        
        # Check metadata changes (labels, assignees, etc.)
        if self._metadata_changed(existing_pr.pr_metadata or {}, github_pr.metadata):
            state_changes.append(StateChange(
                change_type="pr_metadata",
                entity_id=existing_pr.id,
                old_value=existing_pr.pr_metadata,
                new_value=github_pr.metadata,
                metadata={"pr_number": github_pr.number}
            ))
            updated_pr.pr_metadata = github_pr.metadata
            has_updates = True
            logger.debug(f"PR #{github_pr.number} metadata updated")
        
        return updated_pr if has_updates else None, state_changes
    
    def detect_check_run_changes(
        self,
        github_check: CheckRunData,
        existing_check: Optional[CheckRun]
    ) -> tuple[Optional[CheckRun], list[StateChange]]:
        """Detect changes to a check run.
        
        Args:
            github_check: Check run data from GitHub
            existing_check: Existing check run from database (None if new)
            
        Returns:
            Tuple of (updated check run model, list of state changes)
        """
        state_changes: list[StateChange] = []
        
        if existing_check is None:
            # New check run - create model
            check_model = CheckRun(
                pr_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # Will be set by caller
                external_check_id=str(github_check.id),
                check_name=github_check.name,
                status=github_check.check_status,
                conclusion=github_check.check_conclusion,
                started_at=github_check.started_at,
                completed_at=github_check.completed_at,
                details_url=github_check.details_url,
                output_title=github_check.output_title,
                output_summary=github_check.output_summary
            )
            
            # Record as new check run
            state_changes.append(StateChange(
                change_type="new_check_run",
                entity_id=check_model.id,
                old_value=None,
                new_value=github_check.check_status,
                metadata={
                    "check_name": github_check.name,
                    "external_id": github_check.id
                }
            ))
            
            logger.debug(f"Detected new check run: {github_check.name} ({github_check.check_status})")
            return check_model, state_changes
        
        # Existing check run - check for changes
        updated_check = existing_check
        has_updates = False
        
        # Check status changes
        if existing_check.status != github_check.check_status:
            old_status = existing_check.status
            state_changes.append(StateChange(
                change_type="check_status",
                entity_id=existing_check.id,
                old_value=old_status,
                new_value=github_check.check_status,
                metadata={
                    "check_name": github_check.name,
                    "external_id": github_check.id
                }
            ))
            updated_check.status = github_check.check_status
            has_updates = True
            logger.info(f"Check run {github_check.name} status changed: {old_status} → {github_check.check_status}")
        
        # Check conclusion changes
        if existing_check.conclusion != github_check.check_conclusion:
            old_conclusion = existing_check.conclusion
            state_changes.append(StateChange(
                change_type="check_conclusion",
                entity_id=existing_check.id,
                old_value=old_conclusion,
                new_value=github_check.check_conclusion,
                metadata={
                    "check_name": github_check.name,
                    "external_id": github_check.id
                }
            ))
            updated_check.conclusion = github_check.check_conclusion
            has_updates = True
            logger.info(f"Check run {github_check.name} conclusion changed: {old_conclusion} → {github_check.check_conclusion}")
        
        # Check timing changes
        if existing_check.started_at != github_check.started_at:
            updated_check.started_at = github_check.started_at
            has_updates = True
            logger.debug(f"Check run {github_check.name} started_at updated")
        
        if existing_check.completed_at != github_check.completed_at:
            updated_check.completed_at = github_check.completed_at
            has_updates = True
            logger.debug(f"Check run {github_check.name} completed_at updated")
        
        # Check output changes
        if (existing_check.output_title != github_check.output_title or 
            existing_check.output_summary != github_check.output_summary):
            updated_check.output_title = github_check.output_title
            updated_check.output_summary = github_check.output_summary
            has_updates = True
            logger.debug(f"Check run {github_check.name} output updated")
        
        return updated_check if has_updates else None, state_changes
    
    def build_change_set(
        self,
        pr_updates: list[tuple[Optional[PullRequest], list[StateChange]]],
        check_updates: list[tuple[Optional[CheckRun], list[StateChange]]]
    ) -> ChangeSet:
        """Build a consolidated change set from individual updates.
        
        Args:
            pr_updates: List of PR update tuples
            check_updates: List of check run update tuples
            
        Returns:
            Consolidated change set
        """
        change_set = ChangeSet()
        
        # Process PR updates
        for pr_model, pr_state_changes in pr_updates:
            if pr_model:
                # Check if this is a new PR by looking for new_pr state change
                is_new = any(change.change_type == "new_pr" for change in pr_state_changes)
                
                if is_new:
                    change_set.new_prs.append(pr_model)
                else:
                    change_set.updated_prs.append(pr_model)
                
                # Add state changes
                change_set.state_changes.extend(pr_state_changes)
        
        # Process check run updates
        for check_model, check_state_changes in check_updates:
            if check_model:
                # Check if this is a new check run
                is_new = any(change.change_type == "new_check_run" for change in check_state_changes)
                
                if is_new:
                    change_set.new_check_runs.append(check_model)
                else:
                    change_set.updated_check_runs.append(check_model)
                
                # Add state changes
                change_set.state_changes.extend(check_state_changes)
        
        logger.info(
            f"Built change set: {len(change_set.new_prs)} new PRs, "
            f"{len(change_set.updated_prs)} updated PRs, "
            f"{len(change_set.new_check_runs)} new check runs, "
            f"{len(change_set.updated_check_runs)} updated check runs, "
            f"{len(change_set.state_changes)} total state changes"
        )
        
        return change_set
    
    def _metadata_changed(self, old_metadata: dict[str, Any], new_metadata: dict[str, Any]) -> bool:
        """Check if metadata has changed significantly.
        
        Args:
            old_metadata: Existing metadata
            new_metadata: New metadata from GitHub
            
        Returns:
            True if metadata has changed
        """
        # Compare important metadata fields
        important_fields = ['labels', 'assignees', 'milestone', 'mergeable_state']
        
        for field in important_fields:
            if old_metadata.get(field) != new_metadata.get(field):
                return True
        
        return False