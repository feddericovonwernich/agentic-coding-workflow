"""State change detector for comparing PR and check run states.

This module implements the StateChangeDetector interface to identify changes
between newly discovered data and current stored state.
"""

import logging
import uuid
from datetime import datetime

from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository

from .interfaces import (
    ChangeType,
    DiscoveredCheckRun,
    DiscoveredPR,
    EntityType,
    PRDiscoveryResult,
    RepositoryState,
    StateChange,
    StateChangeDetector,
    StoredPRState,
)

logger = logging.getLogger(__name__)


class DatabaseStateChangeDetector(StateChangeDetector):
    """Database-backed state change detection implementation.

    Compares discovered PR and check run data against current database state
    to identify new, updated, and state-changed entities.
    """

    def __init__(
        self, pr_repository: PullRequestRepository, check_repository: CheckRunRepository
    ):
        """Initialize state detector with repository dependencies.

        Args:
            pr_repository: Pull request repository for database access
            check_repository: Check run repository for database access
        """
        self.pr_repository = pr_repository
        self.check_repository = check_repository

    async def load_current_state(self, repository_id: uuid.UUID) -> RepositoryState:
        """Load current state for a repository from database.

        Args:
            repository_id: Database ID of the repository

        Returns:
            Current repository state
        """
        try:
            # Load all PRs for the repository with their check runs
            prs = await self.pr_repository.get_active_prs_for_repo(
                repository_id, include_drafts=True
            )

            # Build state map
            pull_requests = {}
            for pr in prs:
                # Get latest check runs for this PR
                latest_checks = pr.get_latest_check_runs()

                # Build check run state map (name -> conclusion)
                check_runs: dict[str, str] = {}
                for check in latest_checks:
                    conclusion = None
                    if check.conclusion:
                        conclusion = (
                            check.conclusion.value
                            if hasattr(check.conclusion, "value")
                            else str(check.conclusion)
                        )
                    # StoredPRState expects dict[str, str], convert None to empty string
                    check_runs[check.check_name] = conclusion or ""

                pr_state = StoredPRState(
                    pr_id=pr.id,
                    pr_number=pr.pr_number,
                    state=pr.state.value
                    if hasattr(pr.state, "value")
                    else str(pr.state),
                    head_sha=pr.head_sha,
                    updated_at=pr.updated_at,
                    check_runs=check_runs,
                )

                pull_requests[pr.pr_number] = pr_state

            return RepositoryState(
                repository_id=repository_id,
                pull_requests=pull_requests,
                last_updated=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(
                f"Error loading current state for repository {repository_id}: {e}"
            )
            # Return empty state on error
            return RepositoryState(
                repository_id=repository_id,
                pull_requests={},
                last_updated=datetime.utcnow(),
            )

    def _detect_pr_changes(
        self, discovered_pr: DiscoveredPR, stored_pr: StoredPRState | None
    ) -> list[StateChange]:
        """Detect changes in a single PR.

        Args:
            discovered_pr: Newly discovered PR data
            stored_pr: Current stored PR state (None if new)

        Returns:
            List of detected state changes
        """
        changes = []
        now = datetime.utcnow()

        if stored_pr is None:
            # New PR
            changes.append(
                StateChange(
                    entity_type=EntityType.PULL_REQUEST,
                    entity_id=uuid.UUID(
                        int=0
                    ),  # Placeholder - will be resolved during sync
                    external_id=str(discovered_pr.pr_number),
                    old_state=None,
                    new_state=discovered_pr.state,
                    change_type=ChangeType.CREATED,
                    metadata={
                        "pr_number": discovered_pr.pr_number,
                        "title": discovered_pr.title,
                        "author": discovered_pr.author,
                        "head_sha": discovered_pr.head_sha,
                        "draft": discovered_pr.draft,
                    },
                    detected_at=now,
                )
            )
        else:
            # Check for state changes
            if discovered_pr.state != stored_pr.state:
                changes.append(
                    StateChange(
                        entity_type=EntityType.PULL_REQUEST,
                        entity_id=stored_pr.pr_id,
                        external_id=str(discovered_pr.pr_number),
                        old_state=stored_pr.state,
                        new_state=discovered_pr.state,
                        change_type=ChangeType.STATE_CHANGED,
                        metadata={
                            "pr_number": discovered_pr.pr_number,
                            "title": discovered_pr.title,
                            "head_sha": discovered_pr.head_sha,
                        },
                        detected_at=now,
                    )
                )

            # Check for SHA changes (new commits)
            elif discovered_pr.head_sha != stored_pr.head_sha:
                changes.append(
                    StateChange(
                        entity_type=EntityType.PULL_REQUEST,
                        entity_id=stored_pr.pr_id,
                        external_id=str(discovered_pr.pr_number),
                        old_state=stored_pr.head_sha,
                        new_state=discovered_pr.head_sha,
                        change_type=ChangeType.UPDATED,
                        metadata={
                            "pr_number": discovered_pr.pr_number,
                            "title": discovered_pr.title,
                            "change_type": "head_sha_updated",
                            "old_sha": stored_pr.head_sha,
                            "new_sha": discovered_pr.head_sha,
                        },
                        detected_at=now,
                    )
                )

            # Check for updated timestamp (other changes)
            elif discovered_pr.updated_at > stored_pr.updated_at:
                changes.append(
                    StateChange(
                        entity_type=EntityType.PULL_REQUEST,
                        entity_id=stored_pr.pr_id,
                        external_id=str(discovered_pr.pr_number),
                        old_state=stored_pr.updated_at.isoformat(),
                        new_state=discovered_pr.updated_at.isoformat(),
                        change_type=ChangeType.UPDATED,
                        metadata={
                            "pr_number": discovered_pr.pr_number,
                            "title": discovered_pr.title,
                            "change_type": "metadata_updated",
                        },
                        detected_at=now,
                    )
                )

        return changes

    def _detect_check_changes(
        self,
        pr_number: int,
        discovered_checks: list[DiscoveredCheckRun],
        stored_pr: StoredPRState | None,
    ) -> list[StateChange]:
        """Detect changes in check runs for a PR.

        Args:
            pr_number: PR number
            discovered_checks: Newly discovered check runs
            stored_pr: Current stored PR state (None if new PR)

        Returns:
            List of detected state changes for check runs
        """
        changes = []
        now = datetime.utcnow()

        # Build discovered check map
        discovered_check_map = {
            check.name: check.conclusion for check in discovered_checks
        }

        # Get stored check map
        stored_check_map = stored_pr.check_runs if stored_pr else {}

        # Find new and changed checks
        for check_name, new_conclusion in discovered_check_map.items():
            old_conclusion = stored_check_map.get(check_name)

            if old_conclusion is None:
                # New check run
                changes.append(
                    StateChange(
                        entity_type=EntityType.CHECK_RUN,
                        entity_id=uuid.UUID(
                            int=0
                        ),  # Placeholder - will be resolved during sync
                        external_id=f"{pr_number}:{check_name}",
                        old_state=None,
                        new_state=new_conclusion or "running",
                        change_type=ChangeType.CREATED,
                        metadata={
                            "pr_number": pr_number,
                            "check_name": check_name,
                            "conclusion": new_conclusion,
                        },
                        detected_at=now,
                    )
                )
            elif new_conclusion != old_conclusion:
                # Check conclusion changed
                change_type = (
                    ChangeType.STATE_CHANGED if new_conclusion else ChangeType.UPDATED
                )

                changes.append(
                    StateChange(
                        entity_type=EntityType.CHECK_RUN,
                        entity_id=uuid.UUID(int=0),  # Will be resolved during sync
                        external_id=f"{pr_number}:{check_name}",
                        old_state=old_conclusion,
                        new_state=new_conclusion or "running",
                        change_type=change_type,
                        metadata={
                            "pr_number": pr_number,
                            "check_name": check_name,
                            "old_conclusion": old_conclusion,
                            "new_conclusion": new_conclusion,
                            "is_failure": new_conclusion == "failure",
                        },
                        detected_at=now,
                    )
                )

        # Find deleted/missing checks (checks that were in stored state but not
        # discovered)
        for check_name in stored_check_map:
            if check_name not in discovered_check_map:
                changes.append(
                    StateChange(
                        entity_type=EntityType.CHECK_RUN,
                        entity_id=uuid.UUID(int=0),  # Will be resolved during sync
                        external_id=f"{pr_number}:{check_name}",
                        old_state=stored_check_map[check_name],
                        new_state="deleted",
                        change_type=ChangeType.DELETED,
                        metadata={"pr_number": pr_number, "check_name": check_name},
                        detected_at=now,
                    )
                )

        return changes

    async def detect_changes(
        self, discovered_data: PRDiscoveryResult, current_state: RepositoryState
    ) -> list[StateChange]:
        """Detect state changes between discovered and current data.

        Args:
            discovered_data: Newly discovered PR data
            current_state: Current stored state

        Returns:
            List of detected state changes
        """
        all_changes = []

        try:
            logger.debug(
                f"Detecting changes for repository {discovered_data.repository_id}: "
                f"{len(discovered_data.discovered_prs)} discovered PRs vs "
                f"{len(current_state.pull_requests)} stored PRs"
            )

            # Track processed PR numbers to identify deleted PRs
            discovered_pr_numbers = {
                pr.pr_number for pr in discovered_data.discovered_prs
            }
            stored_pr_numbers = set(current_state.pull_requests.keys())

            # Process each discovered PR
            for discovered_pr in discovered_data.discovered_prs:
                stored_pr = current_state.get_pr_state(discovered_pr.pr_number)

                # Detect PR-level changes
                pr_changes = self._detect_pr_changes(discovered_pr, stored_pr)
                all_changes.extend(pr_changes)

                # Detect check run changes
                check_changes = self._detect_check_changes(
                    discovered_pr.pr_number, discovered_pr.check_runs, stored_pr
                )
                all_changes.extend(check_changes)

            # Check for deleted/closed PRs (PRs in stored state but not discovered)
            # Note: This might be expected if discovery filters by state or timeframe
            deleted_pr_numbers = stored_pr_numbers - discovered_pr_numbers

            if deleted_pr_numbers:
                logger.debug(
                    f"Found {len(deleted_pr_numbers)} PRs not in discovery results"
                )

                # Only flag as deleted if we're doing a comprehensive discovery
                # (i.e., not filtering by 'since' time or max_prs)
                if (
                    len(discovered_data.discovered_prs) < 100
                ):  # Heuristic for comprehensive scan
                    for pr_number in deleted_pr_numbers:
                        stored_pr = current_state.pull_requests[pr_number]

                        all_changes.append(
                            StateChange(
                                entity_type=EntityType.PULL_REQUEST,
                                entity_id=stored_pr.pr_id,
                                external_id=str(pr_number),
                                old_state=stored_pr.state,
                                new_state="not_found",
                                change_type=ChangeType.DELETED,
                                metadata={
                                    "pr_number": pr_number,
                                    "reason": "not_found_in_discovery",
                                },
                                detected_at=datetime.utcnow(),
                            )
                        )

            # Filter out insignificant changes if needed
            significant_changes = [
                change for change in all_changes if self._is_significant_change(change)
            ]

            logger.info(
                f"State change detection completed for repository "
                f"{discovered_data.repository_id}: "
                f"{len(significant_changes)} significant changes detected "
                f"({len(all_changes)} total changes)"
            )

            return significant_changes

        except Exception as e:
            logger.error(f"Error detecting state changes: {e}")
            return []

    def _is_significant_change(self, change: StateChange) -> bool:
        """Determine if a state change is significant enough to act on.

        Args:
            change: State change to evaluate

        Returns:
            True if change is significant
        """
        # All creation and deletion changes are significant
        if change.change_type in (ChangeType.CREATED, ChangeType.DELETED):
            return True

        # PR state changes are always significant
        if (
            change.entity_type == EntityType.PULL_REQUEST
            and change.change_type == ChangeType.STATE_CHANGED
        ):
            return True

        # Check run failures are significant
        if change.entity_type == EntityType.CHECK_RUN and change.new_state == "failure":
            return True

        # Check run state changes (completed, failed, etc.) are significant
        if (
            change.entity_type == EntityType.CHECK_RUN
            and change.change_type == ChangeType.STATE_CHANGED
        ):
            return True

        # Head SHA changes are significant (new commits)
        if (
            change.entity_type == EntityType.PULL_REQUEST
            and change.metadata.get("change_type") == "head_sha_updated"
        ):
            return True

        # Filter out minor metadata updates
        if change.change_type == ChangeType.UPDATED:
            # Only significant if it's not just a timestamp update
            change_type = change.metadata.get("change_type", "")
            return bool(change_type != "metadata_updated")

        return True

    async def get_change_summary(self, changes: list[StateChange]) -> dict[str, int]:
        """Get summary statistics for detected changes.

        Args:
            changes: List of state changes

        Returns:
            Dictionary with change statistics
        """
        summary = {
            "total_changes": len(changes),
            "pr_changes": 0,
            "check_changes": 0,
            "created": 0,
            "updated": 0,
            "state_changed": 0,
            "deleted": 0,
            "failed_checks": 0,
        }

        for change in changes:
            if change.entity_type == EntityType.PULL_REQUEST:
                summary["pr_changes"] += 1
            elif change.entity_type == EntityType.CHECK_RUN:
                summary["check_changes"] += 1

            summary[change.change_type.value] += 1

            # Count failed checks specifically
            if (
                change.entity_type == EntityType.CHECK_RUN
                and change.new_state == "failure"
            ):
                summary["failed_checks"] += 1

        return summary
