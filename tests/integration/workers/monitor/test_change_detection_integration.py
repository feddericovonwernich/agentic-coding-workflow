"""
Integration tests for change detection with real database interactions.

Tests change detection logic against actual database operations, including
PR and check run comparison, change identification, and edge case handling.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import text

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.models import CheckRunData, PRData


@pytest.mark.integration
class TestDatabaseChangeDetectorIntegration:
    """Integration tests for change detection with real database operations."""

    @pytest.mark.asyncio
    async def test_pr_change_detection_with_database(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
    ):
        """
        Why: Verify PR change detection works with real database comparisons
        What: Tests detection of new PRs, updated PRs, and specific field changes
        How: Seeds database with existing PRs, provides updated GitHub data,
             and validates accurate change detection with real database queries
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Seed database with existing PRs
        existing_pr_data = [
            {
                "id": uuid.uuid4(),
                "repository_id": test_repository_in_db.id,
                "pr_number": 123,
                "title": "Old Feature Title",  # Will be changed
                "author": "developer1",
                "state": "opened",
                "draft": False,  # Will be changed to True
                "base_branch": "main",
                "head_branch": "feature/new-feature",
                "base_sha": "abc123def456",
                "head_sha": "old456ghi789",  # Will be changed (new commits)
                "url": "https://github.com/test-org/test-repo/pull/123",
                "body": "This PR adds a new feature",
                "pr_metadata": {"labels": ["feature"], "assignees": ["developer1"]},
            },
            {
                "id": uuid.uuid4(),
                "repository_id": test_repository_in_db.id,
                "pr_number": 125,
                "title": "Update documentation",
                "author": "tech-writer",
                "state": "opened",  # Will be changed to closed/merged
                "draft": False,
                "base_branch": "main",
                "head_branch": "docs/update-readme",
                "base_sha": "abc123def456",
                "head_sha": "jkl012mno345",
                "url": "https://github.com/test-org/test-repo/pull/125",
                "body": "Updates README with new installation instructions",
                "pr_metadata": {"labels": ["documentation"], "assignees": []},
            },
        ]
        
        for pr_data in existing_pr_data:
            await database_session.execute(
                text("""
                INSERT INTO pull_requests 
                (id, repository_id, pr_number, title, author, state, draft,
                 base_branch, head_branch, base_sha, head_sha, url, body, pr_metadata,
                 created_at, updated_at)
                VALUES (:id, :repository_id, :pr_number, :title, :author, :state, :draft,
                        :base_branch, :head_branch, :base_sha, :head_sha, :url, :body, :pr_metadata,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                pr_data,
            )
        await database_session.commit()
        
        # Update sample PR data to match existing PRs but with changes
        updated_github_prs = [
            # PR 123: Title change, draft change, new commits
            PRData(
                number=123,
                title="Add new advanced feature",  # Changed title
                author="developer1",
                state="open",
                draft=True,  # Changed to draft
                base_branch="main",
                head_branch="feature/new-feature",
                base_sha="abc123def456",
                head_sha="def456ghi789",  # New commits (SHA changed)
                url="https://github.com/test-org/test-repo/pull/123",
                body="This PR adds a new feature",
                labels=["feature", "enhancement"],  # Added label
                assignees=["developer1", "reviewer1"],  # Added assignee
                milestone="v2.0",  # Added milestone
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                raw_data={"repository_id": str(test_repository_in_db.id)},
            ),
            
            # PR 124: Completely new PR
            PRData(
                number=124,
                title="Fix critical bug",
                author="developer2",
                state="open",
                draft=True,
                base_branch="main",
                head_branch="bugfix/critical-fix",
                base_sha="abc123def456",
                head_sha="ghi789jkl012",
                url="https://github.com/test-org/test-repo/pull/124",
                body="Fixes critical production bug",
                labels=["bug", "critical"],
                assignees=["developer2", "lead-dev"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                raw_data={"repository_id": str(test_repository_in_db.id)},
            ),
            
            # PR 125: State change (merged)
            PRData(
                number=125,
                title="Update documentation",
                author="tech-writer",
                state="closed",
                draft=False,
                merged=True,
                base_branch="main",
                head_branch="docs/update-readme",
                base_sha="abc123def456",
                head_sha="jkl012mno345",
                url="https://github.com/test-org/test-repo/pull/125",
                body="Updates README with new installation instructions",
                labels=["documentation"],
                assignees=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                merged_at=datetime.now(timezone.utc),
                raw_data={"repository_id": str(test_repository_in_db.id)},
            ),
        ]
        
        # Execute change detection
        pr_changes = await detector.detect_pr_changes(
            test_repository_in_db.id, updated_github_prs
        )
        
        # Verify change detection results
        assert len(pr_changes) == 3
        
        # Analyze changes by PR number
        changes_by_number = {change.pr_data.number: change for change in pr_changes}
        
        # Verify PR 123 changes (title, draft, SHA, metadata)
        pr_123_changes = changes_by_number[123]
        assert pr_123_changes.change_type == "updated"
        assert pr_123_changes.title_changed is True
        assert pr_123_changes.old_title == "Old Feature Title"
        assert pr_123_changes.draft_changed is True
        assert pr_123_changes.sha_changed is True
        assert pr_123_changes.old_head_sha == "old456ghi789"
        assert pr_123_changes.metadata_changed is True
        assert pr_123_changes.existing_pr_id is not None
        
        # Verify PR 124 changes (new PR)
        pr_124_changes = changes_by_number[124]
        assert pr_124_changes.change_type == "new"
        assert pr_124_changes.existing_pr_id is None
        
        # Verify PR 125 changes (state change)
        pr_125_changes = changes_by_number[125]
        assert pr_125_changes.change_type == "updated"
        assert pr_125_changes.state_changed is True
        assert pr_125_changes.old_state == PRState.OPENED
        assert pr_125_changes.existing_pr_id is not None

    @pytest.mark.asyncio
    async def test_check_run_change_detection_with_database(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_check_run_data,
    ):
        """
        Why: Verify check run change detection works with real database operations
        What: Tests detection of new check runs, status changes, conclusion changes
        How: Seeds database with existing check runs, provides updated GitHub data,
             and validates accurate change detection with database queries
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Create test PR first
        test_pr_id = uuid.uuid4()
        await database_session.execute(
            text("""
            INSERT INTO pull_requests 
            (id, repository_id, pr_number, title, author, state, draft,
             base_branch, head_branch, base_sha, head_sha, url, body,
             created_at, updated_at)
            VALUES (:id, :repository_id, 150, 'Test PR for check runs', 'developer', 'opened', false,
                    'main', 'feature/test', 'base123', 'head456', 
                    'https://github.com/test-org/test-repo/pull/150', 'Test PR body',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"id": test_pr_id, "repository_id": test_repository_in_db.id},
        )
        
        # Seed database with existing check runs
        existing_check_data = [
            {
                "id": uuid.uuid4(),
                "pr_id": test_pr_id,
                "external_id": "12345678901",
                "check_name": "CI Build",
                "check_suite_id": "87654321098",
                "status": "in_progress",  # Will change to completed
                "conclusion": None,  # Will change to success
                "details_url": "https://github.com/test-org/test-repo/actions/runs/123",
                "logs_url": None,
                "output_summary": None,
                "output_text": None,
                "started_at": datetime.now(timezone.utc),
                "completed_at": None,  # Will be set
                "check_metadata": {},
            },
            {
                "id": uuid.uuid4(),
                "pr_id": test_pr_id,
                "external_id": "12345678902",
                "check_name": "Code Quality",
                "check_suite_id": "87654321098",
                "status": "completed",
                "conclusion": "success",  # Will change to failure
                "details_url": "https://github.com/test-org/test-repo/actions/runs/124",
                "output_summary": "All quality checks passed",
                "output_text": "No issues found",
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "check_metadata": {},
            },
        ]
        
        for check_data in existing_check_data:
            await database_session.execute(
                text("""
                INSERT INTO check_runs 
                (id, pr_id, external_id, check_name, check_suite_id, status, conclusion,
                 details_url, logs_url, output_summary, output_text, started_at, completed_at,
                 check_metadata, created_at, updated_at)
                VALUES (:id, :pr_id, :external_id, :check_name, :check_suite_id, :status, :conclusion,
                        :details_url, :logs_url, :output_summary, :output_text, :started_at, :completed_at,
                        :check_metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                check_data,
            )
        await database_session.commit()
        
        # Create updated GitHub check run data
        updated_github_checks = [
            # Check 12345678901: Status and conclusion change
            CheckRunData(
                external_id="12345678901",
                check_name="CI Build",
                status="completed",  # Changed from in_progress
                conclusion="success",  # Changed from None
                check_suite_id="87654321098",
                details_url="https://github.com/test-org/test-repo/actions/runs/123",
                output_summary="Build completed successfully",  # New output
                output_text="All tests passed",  # New output
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),  # New completion time
                raw_data={"app": {"name": "GitHub Actions"}},
            ),
            
            # Check 12345678902: Conclusion change
            CheckRunData(
                external_id="12345678902",
                check_name="Code Quality",
                status="completed",
                conclusion="failure",  # Changed from success
                check_suite_id="87654321098",
                details_url="https://github.com/test-org/test-repo/actions/runs/124",
                output_summary="Code quality checks failed",  # Changed summary
                output_text="Found 3 linting errors",  # Changed text
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                raw_data={"app": {"name": "SonarCloud"}},
            ),
            
            # Check 12345678903: New check run
            CheckRunData(
                external_id="12345678903",
                check_name="Security Scan",
                status="in_progress",
                conclusion=None,
                check_suite_id="87654321098",
                details_url="https://github.com/test-org/test-repo/actions/runs/125",
                started_at=datetime.now(timezone.utc),
                raw_data={"app": {"name": "Snyk"}},
            ),
        ]
        
        # Create mock PR changes to provide PR IDs
        from src.workers.monitor.models import PRChangeRecord
        mock_pr_changes = [
            PRChangeRecord(
                pr_data=PRData(
                    number=150,
                    title="Test PR for check runs",
                    author="developer",
                    state="open",
                    draft=False,
                    base_branch="main",
                    head_branch="feature/test",
                    base_sha="base123",
                    head_sha="head456",
                    url="https://github.com/test-org/test-repo/pull/150",
                ),
                change_type="updated",
                existing_pr_id=test_pr_id,
            )
        ]
        
        # Map GitHub check runs to PR
        check_runs_by_pr = {150: updated_github_checks}
        
        # Execute change detection
        check_changes = await detector.detect_check_run_changes(
            mock_pr_changes, check_runs_by_pr
        )
        
        # Verify change detection results
        assert len(check_changes) == 3
        
        # Analyze changes by external ID
        changes_by_external_id = {
            change.check_data.external_id: change for change in check_changes
        }
        
        # Verify check 12345678901 changes (status and conclusion)
        check_901_changes = changes_by_external_id["12345678901"]
        assert check_901_changes.change_type == "updated"
        assert check_901_changes.status_changed is True
        assert check_901_changes.old_status == CheckStatus.IN_PROGRESS
        assert check_901_changes.conclusion_changed is True
        assert check_901_changes.old_conclusion is None
        assert check_901_changes.timing_changed is True  # completed_at was set
        assert check_901_changes.existing_check_id is not None
        
        # Verify check 12345678902 changes (conclusion change)
        check_902_changes = changes_by_external_id["12345678902"]
        assert check_902_changes.change_type == "updated"
        assert check_902_changes.status_changed is False  # Still completed
        assert check_902_changes.conclusion_changed is True
        assert check_902_changes.old_conclusion == CheckConclusion.SUCCESS
        assert check_902_changes.existing_check_id is not None
        
        # Verify check 12345678903 changes (new check run)
        check_903_changes = changes_by_external_id["12345678903"]
        assert check_903_changes.change_type == "new"
        assert check_903_changes.existing_check_id is None

    @pytest.mark.asyncio
    async def test_changeset_creation_and_organization(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify changeset creation properly organizes detected changes
        What: Tests that changes are correctly categorized in ChangeSet structure
        How: Creates various types of changes and validates they're properly
             organized in the resulting ChangeSet object
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Create mixed set of changes
        from src.workers.monitor.models import PRChangeRecord, CheckRunChangeRecord
        
        # PR changes: 2 new, 1 updated
        pr_changes = [
            # New PRs
            PRChangeRecord(
                pr_data=PRData(
                    number=201,
                    title="New Feature A",
                    author="dev1",
                    state="open",
                    draft=False,
                    base_branch="main",
                    head_branch="feature/a",
                    base_sha="base1",
                    head_sha="head1",
                    url="https://github.com/test/repo/pull/201",
                ),
                change_type="new",
            ),
            PRChangeRecord(
                pr_data=PRData(
                    number=202,
                    title="New Feature B",
                    author="dev2",
                    state="open",
                    draft=True,
                    base_branch="main",
                    head_branch="feature/b",
                    base_sha="base2",
                    head_sha="head2",
                    url="https://github.com/test/repo/pull/202",
                ),
                change_type="new",
            ),
            
            # Updated PR
            PRChangeRecord(
                pr_data=PRData(
                    number=203,
                    title="Updated Feature C",
                    author="dev3",
                    state="open",
                    draft=False,
                    base_branch="main",
                    head_branch="feature/c",
                    base_sha="base3",
                    head_sha="head3",
                    url="https://github.com/test/repo/pull/203",
                ),
                change_type="updated",
                existing_pr_id=uuid.uuid4(),
                title_changed=True,
                old_title="Old Feature C",
            ),
        ]
        
        # Check run changes: 3 new, 2 updated
        test_pr_id = uuid.uuid4()
        check_changes = [
            # New check runs
            CheckRunChangeRecord(
                check_data=CheckRunData(
                    external_id="new_check_1",
                    check_name="New Build Check",
                    status="completed",
                    conclusion="success",
                ),
                pr_id=test_pr_id,
                change_type="new",
            ),
            CheckRunChangeRecord(
                check_data=CheckRunData(
                    external_id="new_check_2",
                    check_name="New Test Check",
                    status="in_progress",
                    conclusion=None,
                ),
                pr_id=test_pr_id,
                change_type="new",
            ),
            CheckRunChangeRecord(
                check_data=CheckRunData(
                    external_id="new_check_3",
                    check_name="New Security Check",
                    status="queued",
                    conclusion=None,
                ),
                pr_id=test_pr_id,
                change_type="new",
            ),
            
            # Updated check runs
            CheckRunChangeRecord(
                check_data=CheckRunData(
                    external_id="updated_check_1",
                    check_name="Updated Build Check",
                    status="completed",
                    conclusion="failure",
                ),
                pr_id=test_pr_id,
                change_type="updated",
                existing_check_id=uuid.uuid4(),
                conclusion_changed=True,
                old_conclusion=CheckConclusion.SUCCESS,
            ),
            CheckRunChangeRecord(
                check_data=CheckRunData(
                    external_id="updated_check_2",
                    check_name="Updated Quality Check",
                    status="completed",
                    conclusion="success",
                ),
                pr_id=test_pr_id,
                change_type="updated",
                existing_check_id=uuid.uuid4(),
                status_changed=True,
                old_status=CheckStatus.IN_PROGRESS,
            ),
        ]
        
        # Create changeset
        changeset = detector.create_changeset(
            test_repository_in_db.id, pr_changes, check_changes
        )
        
        # Verify changeset organization
        assert changeset.repository_id == test_repository_in_db.id
        assert changeset.has_changes is True
        assert changeset.total_changes == 8  # 3 PRs + 5 check runs
        
        # Verify PR change organization
        assert len(changeset.new_prs) == 2
        assert len(changeset.updated_prs) == 1
        
        # Verify new PRs
        new_pr_numbers = {pr.pr_data.number for pr in changeset.new_prs}
        assert new_pr_numbers == {201, 202}
        
        # Verify updated PR
        updated_pr = changeset.updated_prs[0]
        assert updated_pr.pr_data.number == 203
        assert updated_pr.title_changed is True
        assert updated_pr.old_title == "Old Feature C"
        
        # Verify check run change organization
        assert len(changeset.new_check_runs) == 3
        assert len(changeset.updated_check_runs) == 2
        
        # Verify new check runs
        new_check_ids = {check.check_data.external_id for check in changeset.new_check_runs}
        assert new_check_ids == {"new_check_1", "new_check_2", "new_check_3"}
        
        # Verify updated check runs
        updated_check_ids = {check.check_data.external_id for check in changeset.updated_check_runs}
        assert updated_check_ids == {"updated_check_1", "updated_check_2"}
        
        # Verify PR IDs with changes
        pr_ids_with_changes = changeset.get_pr_ids_with_changes()
        assert test_pr_id in pr_ids_with_changes
        assert updated_pr.existing_pr_id in pr_ids_with_changes

    @pytest.mark.asyncio
    async def test_edge_cases_and_boundary_conditions(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify change detection handles edge cases correctly
        What: Tests scenarios like empty datasets, no changes, deleted PRs
        How: Provides various edge case scenarios and validates robust handling
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Test 1: Empty PR list
        empty_pr_changes = await detector.detect_pr_changes(
            test_repository_in_db.id, []
        )
        assert len(empty_pr_changes) == 0
        
        # Test 2: PRs with no changes (identical to database)
        # First, create a PR in database
        test_pr_id = uuid.uuid4()
        await database_session.execute(
            text("""
            INSERT INTO pull_requests 
            (id, repository_id, pr_number, title, author, state, draft,
             base_branch, head_branch, base_sha, head_sha, url, body, pr_metadata,
             created_at, updated_at)
            VALUES (:id, :repository_id, 300, 'Unchanged PR', 'author', 'opened', false,
                    'main', 'feature/unchanged', 'base_unchanged', 'head_unchanged', 
                    'https://github.com/test/repo/pull/300', 'No changes here',
                    '{"labels": ["test"], "assignees": []}',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"id": test_pr_id, "repository_id": test_repository_in_db.id},
        )
        await database_session.commit()
        
        # Provide identical GitHub data
        identical_pr_data = [
            PRData(
                number=300,
                title="Unchanged PR",
                author="author",
                state="open",
                draft=False,
                base_branch="main",
                head_branch="feature/unchanged",
                base_sha="base_unchanged",
                head_sha="head_unchanged",
                url="https://github.com/test/repo/pull/300",
                body="No changes here",
                labels=["test"],
                assignees=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
        ]
        
        no_change_results = await detector.detect_pr_changes(
            test_repository_in_db.id, identical_pr_data
        )
        assert len(no_change_results) == 0  # No changes detected
        
        # Test 3: Check runs with no changes
        # Create a check run in database
        check_id = uuid.uuid4()
        await database_session.execute(
            text("""
            INSERT INTO check_runs 
            (id, pr_id, external_id, check_name, status, conclusion,
             details_url, started_at, completed_at, created_at, updated_at)
            VALUES (:id, :pr_id, 'unchanged_check', 'Unchanged Check', 'completed', 'success',
                    'https://example.com/unchanged', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"id": check_id, "pr_id": test_pr_id},
        )
        await database_session.commit()
        
        # Provide identical check run data
        from src.workers.monitor.models import PRChangeRecord
        mock_pr_changes = [
            PRChangeRecord(
                pr_data=identical_pr_data[0],
                change_type="updated",  # This PR exists but has no changes
                existing_pr_id=test_pr_id,
            )
        ]
        
        identical_check_data = {
            300: [
                CheckRunData(
                    external_id="unchanged_check",
                    check_name="Unchanged Check",
                    status="completed",
                    conclusion="success",
                    details_url="https://example.com/unchanged",
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
            ]
        }
        
        no_check_changes = await detector.detect_check_run_changes(
            mock_pr_changes, identical_check_data
        )
        assert len(no_check_changes) == 0  # No check run changes detected
        
        # Test 4: Empty changeset creation
        empty_changeset = detector.create_changeset(
            test_repository_in_db.id, [], []
        )
        assert empty_changeset.repository_id == test_repository_in_db.id
        assert empty_changeset.has_changes is False
        assert empty_changeset.total_changes == 0
        assert len(empty_changeset.new_prs) == 0
        assert len(empty_changeset.updated_prs) == 0
        assert len(empty_changeset.new_check_runs) == 0
        assert len(empty_changeset.updated_check_runs) == 0

    @pytest.mark.asyncio
    async def test_performance_with_large_datasets(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        performance_test_data,
    ):
        """
        Why: Verify change detection performs well with large datasets
        What: Tests detection performance with hundreds of PRs and check runs
        How: Seeds database with large dataset, provides updated data,
             and measures detection performance and accuracy
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Seed database with many existing PRs (50 PRs to keep test manageable)
        existing_prs = []
        for i in range(50):
            pr_id = uuid.uuid4()
            await database_session.execute(
                text("""
                INSERT INTO pull_requests 
                (id, repository_id, pr_number, title, author, state, draft,
                 base_branch, head_branch, base_sha, head_sha, url, body,
                 created_at, updated_at)
                VALUES (:id, :repository_id, :pr_number, :title, :author, 'opened', false,
                        'main', :head_branch, :base_sha, :head_sha, :url, 'Body',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "id": pr_id,
                    "repository_id": test_repository_in_db.id,
                    "pr_number": 2000 + i,
                    "title": f"Existing PR {i}",
                    "author": f"dev{i % 10}",
                    "head_branch": f"feature/existing-{i}",
                    "base_sha": f"base{i:04d}",
                    "head_sha": f"head{i:04d}",
                    "url": f"https://github.com/test/repo/pull/{2000 + i}",
                },
            )
            existing_prs.append(pr_id)
        await database_session.commit()
        
        # Use performance test data but modify some to create changes
        large_pr_data = performance_test_data["prs"][:60]  # 60 PRs total
        
        # Modify some existing PRs to create changes
        for i in range(10):  # First 10 will be updates
            large_pr_data[i].number = 2000 + i  # Match existing PR numbers
            large_pr_data[i].title = f"Updated PR {i}"  # Change title
            large_pr_data[i].raw_data["repository_id"] = str(test_repository_in_db.id)
        
        # Next 10 are new PRs (keeping original numbers > 2050)
        for i in range(10, 20):
            large_pr_data[i].raw_data["repository_id"] = str(test_repository_in_db.id)
        
        # Measure performance
        start_time = datetime.now(timezone.utc)
        pr_changes = await detector.detect_pr_changes(
            test_repository_in_db.id, large_pr_data[:20]  # Process 20 PRs
        )
        end_time = datetime.now(timezone.utc)
        
        detection_time = (end_time - start_time).total_seconds()
        
        # Verify performance and accuracy
        assert detection_time < 5.0  # Should complete within 5 seconds
        assert len(pr_changes) == 20  # 10 updates + 10 new PRs
        
        # Verify change types
        new_prs = [change for change in pr_changes if change.change_type == "new"]
        updated_prs = [change for change in pr_changes if change.change_type == "updated"]
        
        assert len(new_prs) == 10
        assert len(updated_prs) == 10
        
        # Verify updated PRs have proper change detection
        for updated_pr in updated_prs:
            assert updated_pr.title_changed is True
            assert updated_pr.existing_pr_id is not None
            assert updated_pr.pr_data.title.startswith("Updated PR")


@pytest.mark.integration
class TestChangeDetectionErrorHandling:
    """Integration tests for error handling in change detection."""

    @pytest.mark.asyncio
    async def test_database_error_handling(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
    ):
        """
        Why: Verify change detection handles database errors gracefully
        What: Tests behavior when database queries fail or return unexpected data
        How: Simulates database errors and validates proper error handling
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Test with invalid repository ID (UUID that doesn't exist)
        invalid_repo_id = uuid.uuid4()
        
        # This should not raise an exception, but return empty changes
        pr_changes = await detector.detect_pr_changes(invalid_repo_id, sample_pr_data)
        
        # Should handle gracefully and treat all PRs as new
        assert len(pr_changes) == len(sample_pr_data)
        for change in pr_changes:
            assert change.change_type == "new"
            assert change.existing_pr_id is None

    @pytest.mark.asyncio
    async def test_data_type_conversion_edge_cases(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify change detection handles data type conversions correctly
        What: Tests edge cases in state conversions, enum mappings, etc.
        How: Provides edge case data and validates proper type handling
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        detector = DatabaseChangeDetector(pr_repo, check_repo)
        
        # Create PR data with edge case values
        edge_case_prs = [
            PRData(
                number=400,
                title="",  # Empty title
                author="edge-case-dev",
                state="OPEN",  # Uppercase state
                draft=False,
                base_branch="main",
                head_branch="feature/edge",
                base_sha="",  # Empty SHA
                head_sha="edge123",
                url="https://github.com/test/repo/pull/400",
                body=None,  # None body
                labels=[],  # Empty labels
                assignees=None,  # None assignees
                milestone="",  # Empty milestone
                created_at=None,  # None timestamp
                updated_at=None,  # None timestamp
                raw_data={"repository_id": str(test_repository_in_db.id)},
            ),
            PRData(
                number=401,
                title="Very " + "long " * 100 + "title",  # Very long title
                author="edge-case-dev-2",
                state="closed",
                draft=True,
                base_branch="main",
                head_branch="feature/long",
                base_sha="long123",
                head_sha="long456",
                url="https://github.com/test/repo/pull/401",
                merged=True,  # Closed but merged
                labels=["label-" + str(i) for i in range(20)],  # Many labels
                assignees=["user-" + str(i) for i in range(10)],  # Many assignees
                raw_data={"repository_id": str(test_repository_in_db.id)},
            ),
        ]
        
        # Should handle edge cases without errors
        pr_changes = await detector.detect_pr_changes(
            test_repository_in_db.id, edge_case_prs
        )
        
        assert len(pr_changes) == 2
        
        # Verify empty/none values are handled
        empty_pr = next(change for change in pr_changes if change.pr_data.number == 400)
        assert empty_pr.pr_data.title == ""
        assert empty_pr.pr_data.body is None
        assert empty_pr.pr_data.labels == []
        
        # Verify state conversion works with different cases
        assert empty_pr.pr_data.to_pr_state() == PRState.OPENED
        
        # Verify merged state handling
        merged_pr = next(change for change in pr_changes if change.pr_data.number == 401)
        assert merged_pr.pr_data.to_pr_state() == PRState.MERGED  # Closed + merged = MERGED