"""Change detection logic for PR monitoring system."""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.workers.monitor.models import (
    ChangeSet,
    CheckRunChangeRecord,
    CheckRunData,
    PRChangeRecord,
    PRData,
)


class ChangeDetector(ABC):
    """Abstract base class for change detection."""

    @abstractmethod
    async def detect_pr_changes(
        self, repository_id: uuid.UUID, pr_data_list: list[PRData]
    ) -> list[PRChangeRecord]:
        """Detect changes for a list of PRs from GitHub API data.

        Args:
            repository_id: The repository UUID
            pr_data_list: List of PR data from GitHub API

        Returns:
            List of PR change records with detected changes
        """
        pass

    @abstractmethod
    async def detect_check_run_changes(
        self,
        pr_changes: list[PRChangeRecord],
        check_runs_by_pr: dict[int, list[CheckRunData]],
    ) -> list[CheckRunChangeRecord]:
        """Detect changes for check runs based on PR changes and GitHub data.

        Args:
            pr_changes: List of PR change records (to identify relevant PRs)
            check_runs_by_pr: Dict mapping PR numbers to their check runs from GitHub

        Returns:
            List of check run change records with detected changes
        """
        pass

    @abstractmethod
    def create_changeset(
        self,
        repository_id: uuid.UUID,
        pr_changes: list[PRChangeRecord],
        check_changes: list[CheckRunChangeRecord],
    ) -> ChangeSet:
        """Create a comprehensive changeset from detected changes.

        Args:
            repository_id: The repository UUID
            pr_changes: List of PR change records
            check_changes: List of check run change records

        Returns:
            ChangeSet object organizing all changes by type
        """
        pass


class DatabaseChangeDetector(ChangeDetector):
    """Database-backed change detector implementation."""

    def __init__(
        self,
        pr_repository: PullRequestRepository,
        check_run_repository: CheckRunRepository,
    ):
        """Initialize with repository dependencies.

        Args:
            pr_repository: Repository for PR database operations
            check_run_repository: Repository for check run database operations
        """
        self.pr_repo = pr_repository
        self.check_repo = check_run_repository

    async def detect_pr_changes(
        self, repository_id: uuid.UUID, pr_data_list: list[PRData]
    ) -> list[PRChangeRecord]:
        """Detect PR changes by comparing GitHub data with database state.

        This method efficiently queries the database to get current PR states,
        then compares with incoming GitHub data to identify:
        - New PRs not in database
        - PR metadata changes (title, state, draft status, etc.)
        - PR SHA changes (new commits)
        - Handle edge cases like deleted PRs

        Args:
            repository_id: The repository UUID
            pr_data_list: List of PR data from GitHub API

        Returns:
            List of PR change records with specific change details
        """
        if not pr_data_list:
            return []

        changes: list[PRChangeRecord] = []

        # Get current PRs from database in bulk using existing method
        # We'll get all PRs for the repo since get_active_prs_for_repo only
        # gets opened ones and we need to detect state changes from any state
        try:
            # Get all recent PRs for this repository (not just active ones)
            existing_prs = await self.pr_repo.get_recent_prs(
                since=datetime.min,  # Get all PRs ever
                repository_id=repository_id,
                limit=None,  # Get all
            )
        except Exception:
            # Fallback to empty list if query fails
            existing_prs = []

        # Create lookup dictionary for efficient comparison
        existing_prs_by_number = {pr.pr_number: pr for pr in existing_prs}

        # Process each PR from GitHub
        for pr_data in pr_data_list:
            existing_pr = existing_prs_by_number.get(pr_data.number)

            if existing_pr is None:
                # This is a new PR
                changes.append(
                    PRChangeRecord(
                        pr_data=pr_data,
                        change_type="new",
                        existing_pr_id=None,
                    )
                )
            else:
                # Check for changes in existing PR
                change_record = self._detect_pr_field_changes(pr_data, existing_pr)
                if self._has_pr_changes(change_record):
                    change_record.existing_pr_id = existing_pr.id
                    changes.append(change_record)

        # TODO: Handle PRs that exist in database but not in GitHub (deleted PRs)
        # This would require additional logic to track and handle deleted PRs
        # For now, we focus on changes we can detect from GitHub API

        return changes

    def _detect_pr_field_changes(
        self,
        pr_data: PRData,
        existing_pr: Any,  # PullRequest model
    ) -> PRChangeRecord:
        """Compare PR data with existing PR to detect specific field changes.

        Args:
            pr_data: GitHub PR data
            existing_pr: Database PR model

        Returns:
            PRChangeRecord with detected changes marked
        """
        change_record = PRChangeRecord(
            pr_data=pr_data,
            change_type="updated",
        )

        # Check title changes
        if pr_data.title != existing_pr.title:
            change_record.title_changed = True
            change_record.old_title = existing_pr.title

        # Check state changes
        new_state = pr_data.to_pr_state()
        if new_state != existing_pr.state:
            change_record.state_changed = True
            change_record.old_state = existing_pr.state

        # Check draft status changes
        if pr_data.draft != existing_pr.draft:
            change_record.draft_changed = True

        # Check SHA changes (new commits)
        if pr_data.head_sha != existing_pr.head_sha:
            change_record.sha_changed = True
            change_record.old_head_sha = existing_pr.head_sha

        # Check metadata changes (labels, assignees, etc.)
        new_metadata = pr_data.get_metadata_dict()
        existing_metadata = existing_pr.pr_metadata or {}

        # Compare key metadata fields that might change
        metadata_fields_to_check = ["labels", "assignees", "milestone"]
        for field in metadata_fields_to_check:
            new_value = new_metadata.get(field)
            existing_value = existing_metadata.get(field)

            # Handle empty lists vs None/missing fields
            if field in ["labels", "assignees"]:
                new_value = new_value or []
                existing_value = existing_value or []

            if new_value != existing_value:
                change_record.metadata_changed = True
                break

        return change_record

    def _has_pr_changes(self, change_record: PRChangeRecord) -> bool:
        """Check if PR change record has any actual changes.

        Args:
            change_record: PR change record to check

        Returns:
            True if any changes detected, False otherwise
        """
        return (
            change_record.title_changed
            or change_record.state_changed
            or change_record.draft_changed
            or change_record.sha_changed
            or change_record.metadata_changed
        )

    async def detect_check_run_changes(
        self,
        pr_changes: list[PRChangeRecord],
        check_runs_by_pr: dict[int, list[CheckRunData]],
    ) -> list[CheckRunChangeRecord]:
        """Detect check run changes based on PR changes and GitHub data.

        This method:
        1. Identifies which PRs have changes or new check runs to process
        2. Gets existing check runs from database for those PRs
        3. Compares GitHub check run data with database state
        4. Detects new check runs, status changes, conclusion changes

        Args:
            pr_changes: List of PR change records
            check_runs_by_pr: Dict mapping PR numbers to their check runs

        Returns:
            List of check run change records with specific change details
        """
        if not check_runs_by_pr:
            return []

        changes: list[CheckRunChangeRecord] = []

        # Get PR IDs we need to check - includes new PRs and PRs with changes
        pr_ids_to_check = set()
        pr_id_by_number = {}

        # Add existing PR IDs from change records
        for pr_change in pr_changes:
            if pr_change.existing_pr_id:
                pr_ids_to_check.add(pr_change.existing_pr_id)
                pr_id_by_number[pr_change.pr_data.number] = pr_change.existing_pr_id

        # For new PRs, we'll handle them separately since they won't have
        # existing check runs

        # Get existing check runs for all relevant PRs in bulk
        existing_check_runs = {}
        for pr_id in pr_ids_to_check:
            try:
                check_runs = await self.check_repo.get_all_for_pr(pr_id)
                existing_check_runs[pr_id] = {
                    check.external_id: check for check in check_runs
                }
            except Exception:
                # If we can't get check runs, assume none exist
                existing_check_runs[pr_id] = {}

        # Process check runs for each PR
        for pr_number, github_check_runs in check_runs_by_pr.items():
            # Find the corresponding PR ID
            found_pr_id = pr_id_by_number.get(pr_number)

            if found_pr_id is None:
                # This is for a new PR - all check runs will be new
                # We'll handle this when we actually create the PR in the database
                # For now, skip check runs for PRs we don't have IDs for
                continue

            existing_checks = existing_check_runs.get(found_pr_id, {})

            # Process each check run from GitHub
            for check_data in github_check_runs:
                existing_check = existing_checks.get(check_data.external_id)

                if existing_check is None:
                    # This is a new check run
                    changes.append(
                        CheckRunChangeRecord(
                            check_data=check_data,
                            pr_id=found_pr_id,
                            change_type="new",
                            existing_check_id=None,
                        )
                    )
                else:
                    # Check for changes in existing check run
                    change_record = self._detect_check_run_field_changes(
                        check_data, existing_check, found_pr_id
                    )
                    if self._has_check_run_changes(change_record):
                        change_record.existing_check_id = existing_check.id
                        changes.append(change_record)

        return changes

    def _detect_check_run_field_changes(
        self,
        check_data: CheckRunData,
        existing_check: Any,  # CheckRun model
        pr_id: uuid.UUID,
    ) -> CheckRunChangeRecord:
        """Compare check run data with existing check to detect changes.

        Args:
            check_data: GitHub check run data
            existing_check: Database check run model
            pr_id: PR UUID this check belongs to

        Returns:
            CheckRunChangeRecord with detected changes marked
        """
        change_record = CheckRunChangeRecord(
            check_data=check_data,
            pr_id=pr_id,
            change_type="updated",
        )

        # Check status changes
        new_status = check_data.to_check_status()
        if new_status != existing_check.status:
            change_record.status_changed = True
            change_record.old_status = existing_check.status

        # Check conclusion changes
        new_conclusion = check_data.to_check_conclusion()
        if new_conclusion != existing_check.conclusion:
            change_record.conclusion_changed = True
            change_record.old_conclusion = existing_check.conclusion

        # Check timing changes (started_at, completed_at)
        timing_changed = False

        # Check started_at changes - either was None and now has value, or values differ
        if check_data.started_at != existing_check.started_at:
            timing_changed = True

        # Check completed_at changes - value differences
        if check_data.completed_at != existing_check.completed_at:
            timing_changed = True

        change_record.timing_changed = timing_changed

        return change_record

    def _has_check_run_changes(self, change_record: CheckRunChangeRecord) -> bool:
        """Check if check run change record has any actual changes.

        Args:
            change_record: Check run change record to check

        Returns:
            True if any changes detected, False otherwise
        """
        return (
            change_record.status_changed
            or change_record.conclusion_changed
            or change_record.timing_changed
        )

    def create_changeset(
        self,
        repository_id: uuid.UUID,
        pr_changes: list[PRChangeRecord],
        check_changes: list[CheckRunChangeRecord],
    ) -> ChangeSet:
        """Create a comprehensive changeset organizing all changes by type.

        Args:
            repository_id: The repository UUID
            pr_changes: List of PR change records
            check_changes: List of check run change records

        Returns:
            ChangeSet object with changes organized by type (new vs updated)
        """
        changeset = ChangeSet(repository_id=repository_id)

        # Organize PR changes by type
        for pr_change in pr_changes:
            if pr_change.change_type == "new":
                changeset.new_prs.append(pr_change)
            else:
                changeset.updated_prs.append(pr_change)

        # Organize check run changes by type
        for check_change in check_changes:
            if check_change.change_type == "new":
                changeset.new_check_runs.append(check_change)
            else:
                changeset.updated_check_runs.append(check_change)

        return changeset
