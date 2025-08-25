"""
Integration tests for database synchronization with transactional behavior.

Tests database operations, transaction handling, bulk operations, and
data consistency during PR and check run synchronization.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import text

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState, TriggerEvent
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.state_history import PRStateHistoryRepository
from src.workers.monitor.models import (
    ChangeSet,
    CheckRunChangeRecord,
    CheckRunData,
    PRChangeRecord,
    PRData,
)
from src.workers.monitor.synchronization import DatabaseSynchronizer


@pytest.mark.integration
class TestDatabaseSynchronizerIntegration:
    """Integration tests for database synchronization operations."""

    @pytest.mark.asyncio
    async def test_complete_synchronization_workflow(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
        sample_check_run_data,
    ):
        """
        Why: Verify complete synchronization workflow works with real database
        What: Tests full changeset synchronization including PRs and check runs
        How: Creates changeset with new and updated records, synchronizes,
             and validates all data is correctly persisted in database
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Create changeset with new PRs and check runs
        changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Add new PRs to changeset
        for pr_data in sample_pr_data:
            pr_data.raw_data["repository_id"] = str(test_repository_in_db.id)
            changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # Execute synchronization
        changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, changeset
        )
        
        # Verify synchronization results
        assert changes_synchronized == len(sample_pr_data)
        
        # Verify PRs were created in database
        pr_repo = PullRequestRepository(database_session)
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        
        assert len(persisted_prs) == len(sample_pr_data)
        
        # Verify PR data integrity
        pr_by_number = {pr.pr_number: pr for pr in persisted_prs}
        for original_pr in sample_pr_data:
            db_pr = pr_by_number[original_pr.number]
            assert db_pr.title == original_pr.title
            assert db_pr.author == original_pr.author
            assert db_pr.state == original_pr.to_pr_state()
            assert db_pr.draft == original_pr.draft
            assert db_pr.base_branch == original_pr.base_branch
            assert db_pr.head_branch == original_pr.head_branch
            assert db_pr.base_sha == original_pr.base_sha
            assert db_pr.head_sha == original_pr.head_sha
            assert db_pr.url == original_pr.url
            
            # Verify metadata was stored
            if original_pr.labels:
                assert db_pr.pr_metadata["labels"] == original_pr.labels
            if original_pr.assignees:
                assert db_pr.pr_metadata["assignees"] == original_pr.assignees
        
        # Verify state history records were created
        history_repo = PRStateHistoryRepository(database_session)
        for db_pr in persisted_prs:
            history = await history_repo.get_history_for_pr(db_pr.id)
            assert len(history) >= 1  # At least initial state
            initial_history = history[0]
            assert initial_history.old_state is None
            assert initial_history.new_state == db_pr.state
            assert initial_history.trigger_event == TriggerEvent.OPENED
        
        # Now add check runs for the created PRs
        changeset2 = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Link check runs to first PR
        first_pr = persisted_prs[0]
        for check_data in sample_check_run_data:
            changeset2.new_check_runs.append(
                CheckRunChangeRecord(
                    check_data=check_data,
                    pr_id=first_pr.id,
                    change_type="new",
                )
            )
        
        # Synchronize check runs
        check_changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, changeset2
        )
        
        assert check_changes_synchronized == len(sample_check_run_data)
        
        # Verify check runs were created
        check_repo = CheckRunRepository(database_session)
        persisted_checks = await check_repo.get_all_for_pr(first_pr.id)
        
        assert len(persisted_checks) == len(sample_check_run_data)
        
        # Verify check run data integrity
        check_by_external_id = {check.external_id: check for check in persisted_checks}
        for original_check in sample_check_run_data:
            db_check = check_by_external_id[original_check.external_id]
            assert db_check.check_name == original_check.check_name
            assert db_check.status == original_check.to_check_status()
            assert db_check.conclusion == original_check.to_check_conclusion()
            assert db_check.check_suite_id == original_check.check_suite_id
            assert db_check.details_url == original_check.details_url

    @pytest.mark.asyncio
    async def test_pr_update_synchronization(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify PR updates are correctly synchronized with state transitions
        What: Tests updating existing PRs with state changes and field updates
        How: Creates PRs, then updates them with various changes and validates
             proper synchronization including state history tracking
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # First, create initial PR
        initial_pr = PRData(
            number=500,
            title="Initial Title",
            author="initial-author",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/initial",
            base_sha="initial_base",
            head_sha="initial_head",
            url="https://github.com/test/repo/pull/500",
            body="Initial body",
            labels=["initial"],
            assignees=["initial-assignee"],
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        
        initial_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        initial_changeset.new_prs.append(
            PRChangeRecord(pr_data=initial_pr, change_type="new")
        )
        
        await synchronizer.synchronize_changes(test_repository_in_db.id, initial_changeset)
        
        # Get the created PR
        pr_repo = PullRequestRepository(database_session)
        created_pr = await pr_repo.get_by_repo_and_number(
            repository_id=test_repository_in_db.id, pr_number=500
        )
        assert created_pr is not None
        
        # Create update changeset with multiple changes
        updated_pr = PRData(
            number=500,
            title="Updated Title",  # Title change
            author="initial-author",
            state="closed",  # State change
            draft=True,  # Draft change
            base_branch="main",
            head_branch="feature/initial",
            base_sha="initial_base",
            head_sha="updated_head",  # SHA change (new commits)
            url="https://github.com/test/repo/pull/500",
            body="Updated body",  # Body change
            labels=["initial", "updated"],  # Metadata change
            assignees=["initial-assignee", "reviewer"],  # Metadata change
            milestone="v2.0",  # New milestone
            merged=True,  # Merged flag
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        
        update_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        update_record = PRChangeRecord(
            pr_data=updated_pr,
            change_type="updated",
            existing_pr_id=created_pr.id,
            title_changed=True,
            old_title="Initial Title",
            state_changed=True,
            old_state=PRState.OPENED,
            draft_changed=True,
            sha_changed=True,
            old_head_sha="initial_head",
            metadata_changed=True,
        )
        update_changeset.updated_prs.append(update_record)
        
        # Synchronize updates
        changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, update_changeset
        )
        
        assert changes_synchronized == 1
        
        # Verify PR was updated
        updated_db_pr = await pr_repo.get_by_id(created_pr.id)
        assert updated_db_pr.title == "Updated Title"
        assert updated_db_pr.state == PRState.MERGED  # closed + merged = MERGED
        assert updated_db_pr.draft is True
        assert updated_db_pr.head_sha == "updated_head"
        assert updated_db_pr.pr_metadata["labels"] == ["initial", "updated"]
        assert updated_db_pr.pr_metadata["assignees"] == ["initial-assignee", "reviewer"]
        assert updated_db_pr.pr_metadata["milestone"] == "v2.0"
        
        # Verify state history was created
        history_repo = PRStateHistoryRepository(database_session)
        history = await history_repo.get_history_for_pr(created_pr.id)
        assert len(history) >= 2  # Initial + update
        
        # Find state transition record
        state_transition = next(
            (h for h in history if h.old_state == PRState.OPENED), None
        )
        assert state_transition is not None
        assert state_transition.new_state == PRState.MERGED
        assert state_transition.trigger_event == TriggerEvent.CLOSED

    @pytest.mark.asyncio
    async def test_check_run_update_synchronization(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify check run updates are correctly synchronized
        What: Tests updating existing check runs with status and conclusion changes
        How: Creates check runs, then updates them and validates proper sync
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Create initial PR for check runs
        pr_data = PRData(
            number=600,
            title="PR for Check Run Updates",
            author="check-test-author",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/check-updates",
            base_sha="check_base",
            head_sha="check_head",
            url="https://github.com/test/repo/pull/600",
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        
        pr_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        pr_changeset.new_prs.append(
            PRChangeRecord(pr_data=pr_data, change_type="new")
        )
        await synchronizer.synchronize_changes(test_repository_in_db.id, pr_changeset)
        
        # Get created PR
        pr_repo = PullRequestRepository(database_session)
        created_pr = await pr_repo.get_by_repo_and_number(
            repository_id=test_repository_in_db.id, pr_number=600
        )
        
        # Create initial check runs
        initial_checks = [
            CheckRunData(
                external_id="update_test_1",
                check_name="Build Check",
                status="in_progress",
                conclusion=None,
                check_suite_id="suite_1",
                details_url="https://example.com/build/1",
                started_at=datetime.now(timezone.utc),
            ),
            CheckRunData(
                external_id="update_test_2",
                check_name="Test Check",
                status="queued",
                conclusion=None,
                check_suite_id="suite_2",
                details_url="https://example.com/test/2",
            ),
        ]
        
        initial_check_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        for check_data in initial_checks:
            initial_check_changeset.new_check_runs.append(
                CheckRunChangeRecord(
                    check_data=check_data,
                    pr_id=created_pr.id,
                    change_type="new",
                )
            )
        
        await synchronizer.synchronize_changes(test_repository_in_db.id, initial_check_changeset)
        
        # Get created check runs
        check_repo = CheckRunRepository(database_session)
        created_checks = await check_repo.get_all_for_pr(created_pr.id)
        check_by_external_id = {check.external_id: check for check in created_checks}
        
        # Create updates for both check runs
        updated_checks = [
            CheckRunData(
                external_id="update_test_1",
                check_name="Build Check",
                status="completed",  # Status change
                conclusion="success",  # Conclusion change
                check_suite_id="suite_1",
                details_url="https://example.com/build/1",
                output_summary="Build completed successfully",  # New output
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),  # Timing change
            ),
            CheckRunData(
                external_id="update_test_2",
                check_name="Test Check",
                status="completed",  # Status change
                conclusion="failure",  # Conclusion change
                check_suite_id="suite_2",
                details_url="https://example.com/test/2",
                output_summary="Tests failed",
                output_text="3 tests failed",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),  # Timing change
            ),
        ]
        
        update_check_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        for updated_check in updated_checks:
            existing_check = check_by_external_id[updated_check.external_id]
            update_record = CheckRunChangeRecord(
                check_data=updated_check,
                pr_id=created_pr.id,
                change_type="updated",
                existing_check_id=existing_check.id,
                status_changed=True,
                old_status=existing_check.status,
                conclusion_changed=True,
                old_conclusion=existing_check.conclusion,
                timing_changed=True,
            )
            update_check_changeset.updated_check_runs.append(update_record)
        
        # Synchronize updates
        check_changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, update_check_changeset
        )
        
        assert check_changes_synchronized == 2
        
        # Verify check runs were updated
        updated_checks_db = await check_repo.get_all_for_pr(created_pr.id)
        updated_check_by_external_id = {check.external_id: check for check in updated_checks_db}
        
        # Verify first check run
        build_check = updated_check_by_external_id["update_test_1"]
        assert build_check.status == CheckStatus.COMPLETED
        assert build_check.conclusion == CheckConclusion.SUCCESS
        assert build_check.output_summary == "Build completed successfully"
        assert build_check.completed_at is not None
        
        # Verify second check run
        test_check = updated_check_by_external_id["update_test_2"]
        assert test_check.status == CheckStatus.COMPLETED
        assert test_check.conclusion == CheckConclusion.FAILURE
        assert test_check.output_summary == "Tests failed"
        assert test_check.output_text == "3 tests failed"
        assert test_check.completed_at is not None

    @pytest.mark.asyncio
    async def test_transaction_rollback_behavior(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify transaction rollback works correctly on errors
        What: Tests that partial failures don't commit any changes
        How: Causes synchronization to fail partway through and validates
             that no partial data is persisted due to rollback
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Create changeset with valid and invalid data
        changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Add valid PR
        valid_pr = PRData(
            number=700,
            title="Valid PR",
            author="valid-author",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/valid",
            base_sha="valid_base",
            head_sha="valid_head",
            url="https://github.com/test/repo/pull/700",
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        changeset.new_prs.append(
            PRChangeRecord(pr_data=valid_pr, change_type="new")
        )
        
        # Add PR that will cause constraint violation (duplicate number)
        duplicate_pr = PRData(
            number=700,  # Same number - will cause unique constraint violation
            title="Duplicate PR",
            author="duplicate-author",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/duplicate",
            base_sha="duplicate_base",
            head_sha="duplicate_head",
            url="https://github.com/test/repo/pull/700",
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        changeset.new_prs.append(
            PRChangeRecord(pr_data=duplicate_pr, change_type="new")
        )
        
        # Get initial PR count
        pr_repo = PullRequestRepository(database_session)
        initial_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        initial_count = len(initial_prs)
        
        # Attempt synchronization - should fail due to constraint violation
        with pytest.raises(Exception):  # Should raise TransactionError
            await synchronizer.synchronize_changes(test_repository_in_db.id, changeset)
        
        # Verify no partial data was committed
        final_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        final_count = len(final_prs)
        
        # Count should be unchanged - transaction should have rolled back
        assert final_count == initial_count
        
        # Verify specific PR was not created
        pr_700 = await pr_repo.get_by_repo_and_number(
            repository_id=test_repository_in_db.id, pr_number=700
        )
        assert pr_700 is None

    @pytest.mark.asyncio
    async def test_bulk_operations_performance(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        performance_test_data,
    ):
        """
        Why: Verify bulk operations perform efficiently with large datasets
        What: Tests synchronization performance with many PRs and check runs
        How: Creates large changeset, measures synchronization time, and
             validates data integrity with realistic performance benchmarks
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Create large changeset from performance test data
        changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Use first 50 PRs to keep test manageable but still substantial
        large_prs = performance_test_data["prs"][:50]
        
        for pr_data in large_prs:
            pr_data.raw_data["repository_id"] = str(test_repository_in_db.id)
            changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # Measure synchronization performance
        start_time = datetime.now(timezone.utc)
        changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, changeset
        )
        end_time = datetime.now(timezone.utc)
        
        sync_time = (end_time - start_time).total_seconds()
        
        # Verify performance
        assert changes_synchronized == 50
        assert sync_time < 10.0  # Should complete within 10 seconds
        
        # Verify all PRs were created correctly
        pr_repo = PullRequestRepository(database_session)
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        
        assert len(persisted_prs) == 50
        
        # Verify data integrity with sampling
        sample_prs = persisted_prs[:5]  # Check first 5 PRs
        for pr in sample_prs:
            assert pr.repository_id == test_repository_in_db.id
            assert pr.pr_number >= 1000  # From performance test data
            assert pr.title.startswith("Test PR")
            assert pr.author.startswith("developer")
            assert pr.base_branch == "main"

    @pytest.mark.asyncio
    async def test_concurrent_synchronization_safety(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify synchronization handles concurrent operations safely
        What: Tests that concurrent synchronization doesn't cause data corruption
        How: Runs multiple synchronization operations concurrently and validates
             data consistency and proper transaction isolation
        """
        import asyncio
        
        # Create multiple synchronizers (simulating concurrent processes)
        synchronizer1 = DatabaseSynchronizer(database_session)
        synchronizer2 = DatabaseSynchronizer(database_session)
        
        # Create separate changesets for concurrent operations
        changeset1 = ChangeSet(repository_id=test_repository_in_db.id)
        changeset2 = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Changeset 1: PRs 800-809
        for i in range(10):
            pr_data = PRData(
                number=800 + i,
                title=f"Concurrent PR Set 1 - {i}",
                author=f"concurrent-dev-1-{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/concurrent-1-{i}",
                base_sha=f"base1_{i:03d}",
                head_sha=f"head1_{i:03d}",
                url=f"https://github.com/test/repo/pull/{800 + i}",
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            changeset1.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # Changeset 2: PRs 810-819
        for i in range(10):
            pr_data = PRData(
                number=810 + i,
                title=f"Concurrent PR Set 2 - {i}",
                author=f"concurrent-dev-2-{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/concurrent-2-{i}",
                base_sha=f"base2_{i:03d}",
                head_sha=f"head2_{i:03d}",
                url=f"https://github.com/test/repo/pull/{810 + i}",
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            changeset2.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # Run concurrent synchronizations
        results = await asyncio.gather(
            synchronizer1.synchronize_changes(test_repository_in_db.id, changeset1),
            synchronizer2.synchronize_changes(test_repository_in_db.id, changeset2),
            return_exceptions=True,
        )
        
        # Both should succeed (or handle conflicts gracefully)
        successful_operations = [r for r in results if isinstance(r, int)]
        assert len(successful_operations) >= 1  # At least one should succeed
        
        # Verify data consistency - all successfully synchronized PRs should be in DB
        pr_repo = PullRequestRepository(database_session)
        all_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        
        # Filter PRs from our concurrent test (numbers 800-819)
        concurrent_prs = [pr for pr in all_prs if 800 <= pr.pr_number <= 819]
        
        # Should have PRs from successful synchronizations
        assert len(concurrent_prs) >= 10  # At least one set should be synchronized
        assert len(concurrent_prs) <= 20  # No more than both sets
        
        # Verify no data corruption - all PRs should have valid data
        for pr in concurrent_prs:
            assert pr.title.startswith("Concurrent PR Set")
            assert pr.author.startswith("concurrent-dev")
            assert pr.repository_id == test_repository_in_db.id
            assert pr.base_branch == "main"

    @pytest.mark.asyncio
    async def test_complex_mixed_changeset_synchronization(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify complex changesets with mixed operations synchronize correctly
        What: Tests changeset with new PRs, updated PRs, new checks, updated checks
        How: Creates complex changeset and validates all operations complete correctly
        """
        synchronizer = DatabaseSynchronizer(database_session)
        
        # First, create some existing PRs and check runs
        initial_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        existing_prs = []
        for i in range(3):
            pr_data = PRData(
                number=900 + i,
                title=f"Existing PR {i}",
                author=f"existing-author-{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/existing-{i}",
                base_sha=f"existing_base_{i}",
                head_sha=f"existing_head_{i}",
                url=f"https://github.com/test/repo/pull/{900 + i}",
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            existing_prs.append(pr_data)
            initial_changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        await synchronizer.synchronize_changes(test_repository_in_db.id, initial_changeset)
        
        # Get created PRs
        pr_repo = PullRequestRepository(database_session)
        created_prs = []
        for i in range(3):
            pr = await pr_repo.get_by_repo_and_number(
                repository_id=test_repository_in_db.id, pr_number=900 + i
            )
            created_prs.append(pr)
        
        # Create check runs for first PR
        check_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        initial_checks = [
            CheckRunData(
                external_id="complex_check_1",
                check_name="Build",
                status="completed",
                conclusion="success",
                check_suite_id="complex_suite_1",
            ),
            CheckRunData(
                external_id="complex_check_2",
                check_name="Test",
                status="in_progress",
                conclusion=None,
                check_suite_id="complex_suite_2",
            ),
        ]
        
        for check_data in initial_checks:
            check_changeset.new_check_runs.append(
                CheckRunChangeRecord(
                    check_data=check_data,
                    pr_id=created_prs[0].id,
                    change_type="new",
                )
            )
        
        await synchronizer.synchronize_changes(test_repository_in_db.id, check_changeset)
        
        # Get created check runs
        check_repo = CheckRunRepository(database_session)
        created_checks = await check_repo.get_all_for_pr(created_prs[0].id)
        
        # Now create complex mixed changeset
        complex_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        # 1. New PRs
        for i in range(2):
            pr_data = PRData(
                number=950 + i,
                title=f"New PR {i}",
                author=f"new-author-{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/new-{i}",
                base_sha=f"new_base_{i}",
                head_sha=f"new_head_{i}",
                url=f"https://github.com/test/repo/pull/{950 + i}",
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            complex_changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # 2. Updated PRs
        for i, existing_pr in enumerate(created_prs[:2]):  # Update first 2 PRs
            updated_pr_data = PRData(
                number=existing_pr.pr_number,
                title=f"Updated PR {i}",  # Title change
                author=existing_pr.author,
                state="closed",  # State change
                draft=True,  # Draft change
                base_branch=existing_pr.base_branch,
                head_branch=existing_pr.head_branch,
                base_sha=existing_pr.base_sha,
                head_sha=f"updated_head_{i}",  # SHA change
                url=existing_pr.url,
                merged=True,
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            
            update_record = PRChangeRecord(
                pr_data=updated_pr_data,
                change_type="updated",
                existing_pr_id=existing_pr.id,
                title_changed=True,
                old_title=existing_pr.title,
                state_changed=True,
                old_state=existing_pr.state,
                draft_changed=True,
                sha_changed=True,
                old_head_sha=existing_pr.head_sha,
            )
            complex_changeset.updated_prs.append(update_record)
        
        # 3. New check runs
        for i in range(2):
            check_data = CheckRunData(
                external_id=f"complex_new_check_{i}",
                check_name=f"New Check {i}",
                status="completed",
                conclusion="success",
                check_suite_id=f"new_suite_{i}",
            )
            complex_changeset.new_check_runs.append(
                CheckRunChangeRecord(
                    check_data=check_data,
                    pr_id=created_prs[1].id,  # Add to second PR
                    change_type="new",
                )
            )
        
        # 4. Updated check runs
        for i, existing_check in enumerate(created_checks):
            updated_check_data = CheckRunData(
                external_id=existing_check.external_id,
                check_name=existing_check.check_name,
                status="completed",  # Status change
                conclusion="failure",  # Conclusion change
                check_suite_id=existing_check.check_suite_id,
                output_summary=f"Updated output {i}",
                completed_at=datetime.now(timezone.utc),  # Timing change
            )
            
            update_record = CheckRunChangeRecord(
                check_data=updated_check_data,
                pr_id=created_prs[0].id,
                change_type="updated",
                existing_check_id=existing_check.id,
                status_changed=True,
                old_status=existing_check.status,
                conclusion_changed=True,
                old_conclusion=existing_check.conclusion,
                timing_changed=True,
            )
            complex_changeset.updated_check_runs.append(update_record)
        
        # Execute complex synchronization
        changes_synchronized = await synchronizer.synchronize_changes(
            test_repository_in_db.id, complex_changeset
        )
        
        # Verify all operations completed
        expected_changes = (
            len(complex_changeset.new_prs) +
            len(complex_changeset.updated_prs) +
            len(complex_changeset.new_check_runs) +
            len(complex_changeset.updated_check_runs)
        )
        assert changes_synchronized == expected_changes
        
        # Verify new PRs were created
        new_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        pr_950 = next((pr for pr in new_prs if pr.pr_number == 950), None)
        pr_951 = next((pr for pr in new_prs if pr.pr_number == 951), None)
        assert pr_950 is not None
        assert pr_951 is not None
        
        # Verify PR updates
        updated_pr_900 = await pr_repo.get_by_id(created_prs[0].id)
        assert updated_pr_900.title == "Updated PR 0"
        assert updated_pr_900.state == PRState.MERGED
        assert updated_pr_900.draft is True
        
        # Verify new check runs were created
        pr_1_checks = await check_repo.get_all_for_pr(created_prs[1].id)
        new_check_ids = {check.external_id for check in pr_1_checks}
        assert "complex_new_check_0" in new_check_ids
        assert "complex_new_check_1" in new_check_ids
        
        # Verify check run updates
        updated_checks = await check_repo.get_all_for_pr(created_prs[0].id)
        for check in updated_checks:
            assert check.status == CheckStatus.COMPLETED
            assert check.conclusion == CheckConclusion.FAILURE
            assert check.completed_at is not None