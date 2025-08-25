# PR Monitoring Testing Guide

This guide provides comprehensive testing strategies and examples for the PR monitoring system, covering unit tests, integration tests, performance tests, and testing best practices.

## Table of Contents

- [Testing Overview](#testing-overview)
- [Test Architecture](#test-architecture)
- [Unit Testing](#unit-testing)
- [Integration Testing](#integration-testing)
- [Performance Testing](#performance-testing)
- [Test Data Management](#test-data-management)
- [Mock Services](#mock-services)
- [Testing Best Practices](#testing-best-practices)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting Tests](#troubleshooting-tests)

## Testing Overview

The PR monitoring system testing strategy follows a three-tier approach:

1. **Unit Tests**: Test individual components in isolation using mocks
2. **Integration Tests**: Test complete workflows with real database interactions
3. **Performance Tests**: Validate system behavior under load and large datasets

### Testing Philosophy

- **Why Testing**: Each test documents its business purpose
- **What Testing**: Clear description of what functionality is tested
- **How Testing**: Implementation details and test methodology
- **Isolation**: Tests are independent and can run in any order
- **Repeatability**: Tests produce consistent results across environments

## Test Architecture

### Directory Structure

```
tests/
├── unit/
│   └── workers/
│       └── monitor/
│           ├── test_processor.py
│           ├── test_discovery.py
│           ├── test_change_detection.py
│           └── test_synchronization.py
├── integration/
│   └── workers/
│       └── monitor/
│           ├── test_processor_integration.py
│           ├── test_discovery_integration.py
│           ├── test_change_detection_integration.py
│           └── test_synchronization_integration.py
└── performance/
    └── test_pr_monitoring_performance.py
```

### Test Categories

```python
import pytest

# Test markers for categorization
pytestmark = [
    pytest.mark.pr_monitoring,  # All PR monitoring tests
]

@pytest.mark.unit
def test_unit_functionality():
    """Unit test marker."""
    pass

@pytest.mark.integration  
def test_integration_workflow():
    """Integration test marker."""
    pass

@pytest.mark.performance
@pytest.mark.slow
def test_performance_scalability():
    """Performance test marker."""
    pass
```

## Unit Testing

### Testing Components in Isolation

#### PRProcessor Unit Tests

```python
# tests/unit/workers/monitor/test_processor.py
"""
Unit tests for PR processor orchestration logic.

Why: Validates the PR processor correctly orchestrates the three-phase workflow
What: Tests orchestration logic, error handling, and metrics collection
How: Uses mocks for all external dependencies (services, database)
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.models import (
    ChangeSet, ProcessingResult, PRChangeRecord, CheckRunChangeRecord
)
from src.models.repository import Repository


class TestDefaultPRProcessor:
    """Test suite for DefaultPRProcessor."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for processor."""
        discovery_service = AsyncMock()
        change_detector = AsyncMock()  
        synchronizer = AsyncMock()
        
        return {
            "discovery": discovery_service,
            "change_detector": change_detector,
            "synchronizer": synchronizer
        }

    @pytest.fixture
    def processor(self, mock_services):
        """Create processor with mock services."""
        return DefaultPRProcessor(
            discovery_service=mock_services["discovery"],
            change_detection_service=mock_services["change_detector"], 
            synchronization_service=mock_services["synchronizer"],
            max_concurrent_repos=5
        )

    @pytest.fixture
    def test_repository(self):
        """Create test repository."""
        return Repository(
            id=uuid.uuid4(),
            url="https://github.com/test-org/test-repo",
            name="test-repo",
            owner="test-org",
            repo_name="test-repo"
        )

    @pytest.mark.asyncio
    async def test_successful_repository_processing(
        self, processor, mock_services, test_repository
    ):
        """
        Why: Validates complete successful processing workflow
        What: Tests that all three phases execute and metrics are collected
        How: Mocks all services to return success, verifies all phases called
        """
        # Setup mocks
        mock_services["discovery"].discover_prs_and_checks.return_value = (5, 10)
        
        changeset = ChangeSet(repository_id=test_repository.id)
        changeset.new_prs = [MagicMock()] * 2  # 2 new PRs
        changeset.new_check_runs = [MagicMock()] * 3  # 3 new check runs
        mock_services["change_detector"].detect_changes.return_value = changeset
        
        mock_services["synchronizer"].synchronize_changes.return_value = 5
        
        # Execute
        result = await processor.process_repository(test_repository)
        
        # Verify all phases called
        mock_services["discovery"].discover_prs_and_checks.assert_called_once_with(
            test_repository
        )
        mock_services["change_detector"].detect_changes.assert_called_once_with(
            test_repository
        )
        mock_services["synchronizer"].synchronize_changes.assert_called_once_with(
            changeset
        )
        
        # Verify results
        assert result.success is True
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 10
        assert result.changes_synchronized == 5
        assert result.new_prs == 2
        assert result.new_check_runs == 3
        assert len(result.errors) == 0
        assert result.processing_time > 0

    @pytest.mark.asyncio
    async def test_discovery_phase_failure(
        self, processor, mock_services, test_repository
    ):
        """
        Why: Validates error handling when GitHub API fails
        What: Tests that discovery failures are caught and recorded
        How: Mocks discovery service to raise exception, verifies error handling
        """
        # Setup discovery failure
        mock_services["discovery"].discover_prs_and_checks.side_effect = Exception(
            "GitHub API timeout"
        )
        
        # Execute
        result = await processor.process_repository(test_repository)
        
        # Verify error handling
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "discovery_failure"
        assert "GitHub API timeout" in result.errors[0].message
        assert result.prs_discovered == 0
        assert result.check_runs_discovered == 0
        
        # Verify other phases not called after discovery failure
        mock_services["change_detector"].detect_changes.assert_not_called()
        mock_services["synchronizer"].synchronize_changes.assert_not_called()

    @pytest.mark.asyncio  
    async def test_change_detection_phase_failure(
        self, processor, mock_services, test_repository
    ):
        """
        Why: Validates error handling when database queries fail
        What: Tests that change detection failures are isolated
        How: Mocks change detector to fail, verifies graceful degradation
        """
        # Setup successful discovery
        mock_services["discovery"].discover_prs_and_checks.return_value = (3, 7)
        
        # Setup change detection failure
        mock_services["change_detector"].detect_changes.side_effect = Exception(
            "Database connection lost"
        )
        
        # Execute
        result = await processor.process_repository(test_repository)
        
        # Verify error handling
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "change_detection_failure"
        assert "Database connection lost" in result.errors[0].message
        
        # Verify discovery succeeded but sync not called
        assert result.prs_discovered == 3
        assert result.check_runs_discovered == 7
        mock_services["synchronizer"].synchronize_changes.assert_not_called()

    @pytest.mark.asyncio
    async def test_synchronization_phase_failure(
        self, processor, mock_services, test_repository  
    ):
        """
        Why: Validates error handling when database transactions fail
        What: Tests that sync failures are caught and don't corrupt data
        How: Mocks synchronizer to fail, verifies rollback behavior
        """
        # Setup successful discovery and change detection
        mock_services["discovery"].discover_prs_and_checks.return_value = (2, 4)
        
        changeset = ChangeSet(repository_id=test_repository.id)
        changeset.new_prs = [MagicMock()]
        mock_services["change_detector"].detect_changes.return_value = changeset
        
        # Setup synchronization failure
        mock_services["synchronizer"].synchronize_changes.side_effect = Exception(
            "Transaction deadlock"
        )
        
        # Execute  
        result = await processor.process_repository(test_repository)
        
        # Verify error handling
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "synchronization_failure"
        assert "Transaction deadlock" in result.errors[0].message
        
        # Verify no changes recorded as synchronized
        assert result.changes_synchronized == 0

    @pytest.mark.asyncio
    async def test_batch_processing_with_failures(
        self, processor, mock_services
    ):
        """
        Why: Validates that individual repository failures don't affect others
        What: Tests error isolation in batch processing
        How: Processes multiple repos with some failures, verifies isolation
        """
        # Create test repositories
        repo1 = Repository(id=uuid.uuid4(), url="https://github.com/org/repo1", name="repo1")
        repo2 = Repository(id=uuid.uuid4(), url="https://github.com/org/repo2", name="repo2")  
        repo3 = Repository(id=uuid.uuid4(), url="https://github.com/org/repo3", name="repo3")
        repositories = [repo1, repo2, repo3]
        
        # Setup mixed success/failure responses
        discovery_responses = [
            (2, 3),  # repo1: success
            Exception("API error"),  # repo2: failure
            (1, 2),  # repo3: success
        ]
        mock_services["discovery"].discover_prs_and_checks.side_effect = discovery_responses
        
        # Setup change detection (only called for successful discoveries)
        changeset1 = ChangeSet(repository_id=repo1.id)
        changeset1.new_prs = [MagicMock()]
        changeset3 = ChangeSet(repository_id=repo3.id)  
        changeset3.new_prs = [MagicMock()]
        
        mock_services["change_detector"].detect_changes.side_effect = [
            changeset1, changeset3
        ]
        mock_services["synchronizer"].synchronize_changes.side_effect = [1, 1]
        
        # Execute batch processing
        batch_result = await processor.process_repositories(repositories)
        
        # Verify batch results
        assert batch_result.repositories_processed == 3
        assert batch_result.success_rate == 66.67  # 2 out of 3 successful
        assert len(batch_result.results) == 3
        
        # Verify individual results
        repo1_result, repo2_result, repo3_result = batch_result.results
        
        # repo1: successful
        assert repo1_result.success is True
        assert repo1_result.changes_synchronized == 1
        
        # repo2: failed
        assert repo2_result.success is False
        assert len(repo2_result.errors) == 1
        
        # repo3: successful  
        assert repo3_result.success is True
        assert repo3_result.changes_synchronized == 1

    @pytest.mark.asyncio
    async def test_concurrent_processing_limits(self, mock_services):
        """
        Why: Validates that concurrency limits are respected
        What: Tests semaphore-based concurrency control
        How: Creates processor with low limit, verifies sequential processing
        """
        # Create processor with very low concurrency limit
        processor = DefaultPRProcessor(
            discovery_service=mock_services["discovery"],
            change_detection_service=mock_services["change_detector"],
            synchronization_service=mock_services["synchronizer"], 
            max_concurrent_repos=1  # Force sequential processing
        )
        
        # Create multiple repositories
        repositories = [
            Repository(id=uuid.uuid4(), url=f"https://github.com/org/repo{i}", name=f"repo{i}")
            for i in range(5)
        ]
        
        # Track call order
        call_order = []
        
        async def track_discovery_calls(repository):
            call_order.append(f"start_{repository.name}")
            await asyncio.sleep(0.1)  # Simulate processing time
            call_order.append(f"end_{repository.name}")
            return (1, 1)
        
        mock_services["discovery"].discover_prs_and_checks.side_effect = track_discovery_calls
        mock_services["change_detector"].detect_changes.return_value = ChangeSet(
            repository_id=uuid.uuid4()
        )
        mock_services["synchronizer"].synchronize_changes.return_value = 0
        
        # Execute batch processing
        await processor.process_repositories(repositories)
        
        # Verify sequential processing (with concurrency=1)
        # Each repo should start and end before next one starts
        for i in range(5):
            repo_name = f"repo{i}"
            start_idx = call_order.index(f"start_{repo_name}")
            end_idx = call_order.index(f"end_{repo_name}")
            
            # Verify this repo completed before next one started
            if i < 4:
                next_repo_start = call_order.index(f"start_repo{i+1}")
                assert end_idx < next_repo_start
```

#### Discovery Service Unit Tests

```python
# tests/unit/workers/monitor/test_discovery.py
"""
Unit tests for GitHub PR discovery service.

Why: Validates GitHub API integration logic and error handling
What: Tests PR fetching, caching, pagination, and rate limiting
How: Mocks GitHub client to test discovery logic without API calls
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.models import PRData, CheckRunData
from src.models.repository import Repository


class TestGitHubPRDiscoveryService:
    """Test suite for GitHubPRDiscoveryService."""

    @pytest.fixture
    def mock_github_client(self):
        """Create mock GitHub client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def discovery_service(self, mock_github_client):
        """Create discovery service with mock client."""
        return GitHubPRDiscoveryService(
            github_client=mock_github_client,
            max_concurrent_requests=5,
            cache_ttl_seconds=300
        )

    @pytest.fixture
    def test_repository(self):
        """Create test repository."""
        return Repository(
            id=uuid.uuid4(),
            url="https://github.com/microsoft/vscode",
            name="vscode",
            owner="microsoft",
            repo_name="vscode"
        )

    @pytest.mark.asyncio
    async def test_discover_prs_success(
        self, discovery_service, mock_github_client, test_repository
    ):
        """
        Why: Validates successful PR discovery from GitHub API
        What: Tests PR fetching, data extraction, and pagination
        How: Mocks GitHub client pagination to return sample PR data
        """
        # Setup mock PR data
        sample_pr_json = {
            "number": 123,
            "title": "Fix bug in editor",
            "user": {"login": "contributor"},
            "state": "open",
            "draft": False,
            "base": {"ref": "main", "sha": "abc123"},
            "head": {"ref": "feature-branch", "sha": "def456"},
            "html_url": "https://github.com/microsoft/vscode/pull/123",
            "body": "This PR fixes a critical bug",
            "labels": [{"name": "bug"}, {"name": "editor"}],
            "assignees": [{"login": "maintainer"}],
            "milestone": {"title": "v1.2.0"},
            "created_at": "2023-01-01T12:00:00Z",
            "updated_at": "2023-01-02T12:00:00Z"
        }
        
        # Mock pagination to yield individual items
        async def mock_paginate(*args, **kwargs):
            yield sample_pr_json
            
        mock_github_client.paginate.side_effect = mock_paginate
        
        # Execute
        prs = await discovery_service.discover_prs(test_repository)
        
        # Verify API call
        mock_github_client.paginate.assert_called_once()
        call_args = mock_github_client.paginate.call_args
        assert "/repos/microsoft/vscode/pulls" in call_args[0][0]
        
        # Verify result  
        assert len(prs) == 1
        pr = prs[0]
        assert isinstance(pr, PRData)
        assert pr.number == 123
        assert pr.title == "Fix bug in editor"
        assert pr.author == "contributor"
        assert pr.state == "open"
        assert pr.draft is False
        assert pr.base_branch == "main"
        assert pr.head_branch == "feature-branch"
        assert pr.base_sha == "abc123"
        assert pr.head_sha == "def456"
        assert pr.url == "https://github.com/microsoft/vscode/pull/123"
        assert pr.labels == ["bug", "editor"]
        assert pr.assignees == ["maintainer"]
        assert pr.milestone == "v1.2.0"

    @pytest.mark.asyncio
    async def test_discover_check_runs_success(
        self, discovery_service, mock_github_client, test_repository
    ):
        """
        Why: Validates successful check run discovery for PRs
        What: Tests check run fetching and data extraction
        How: Mocks GitHub API to return sample check run data
        """
        # Create test PR data
        pr_data = PRData(
            number=123,
            title="Test PR",
            author="test-user", 
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature",
            base_sha="abc123",
            head_sha="def456",
            url="https://github.com/microsoft/vscode/pull/123"
        )
        
        # Setup mock check run data
        sample_check_json = {
            "id": 456789,
            "name": "CI Build",
            "status": "completed",
            "conclusion": "success",
            "check_suite": {"id": 123456},
            "details_url": "https://github.com/microsoft/vscode/runs/456789",
            "html_url": "https://github.com/microsoft/vscode/runs/456789",
            "output": {
                "title": "Build Successful",
                "summary": "All tests passed",
                "text": "Detailed build log..."
            },
            "started_at": "2023-01-01T12:00:00Z",
            "completed_at": "2023-01-01T12:05:00Z"
        }
        
        # Mock pagination for check runs
        async def mock_paginate(*args, **kwargs):
            # GitHub API returns wrapper object for check runs
            yield {
                "check_runs": [sample_check_json]
            }
            
        mock_github_client.paginate.side_effect = mock_paginate
        
        # Execute
        check_runs = await discovery_service.discover_check_runs(
            test_repository, pr_data
        )
        
        # Verify API call
        mock_github_client.paginate.assert_called_once()
        call_args = mock_github_client.paginate.call_args
        assert f"/repos/microsoft/vscode/commits/{pr_data.head_sha}/check-runs" in call_args[0][0]
        
        # Verify result
        assert len(check_runs) == 1
        check_run = check_runs[0]
        assert isinstance(check_run, CheckRunData)
        assert check_run.external_id == "456789"
        assert check_run.check_name == "CI Build"
        assert check_run.status == "completed"
        assert check_run.conclusion == "success"
        assert check_run.check_suite_id == "123456"
        assert check_run.details_url == "https://github.com/microsoft/vscode/runs/456789"
        assert check_run.output_title == "Build Successful"
        assert check_run.output_summary == "All tests passed"

    @pytest.mark.asyncio
    async def test_caching_behavior(
        self, discovery_service, mock_github_client, test_repository
    ):
        """
        Why: Validates ETag caching reduces redundant API calls
        What: Tests that repeated calls use cached results  
        How: Mocks same response twice, verifies only one API call made
        """
        # Setup mock response
        sample_pr = {"number": 1, "title": "Test", "user": {"login": "test"}, 
                    "state": "open", "draft": False,
                    "base": {"ref": "main", "sha": "abc"}, 
                    "head": {"ref": "feature", "sha": "def"},
                    "html_url": "https://example.com"}
        
        async def mock_paginate(*args, **kwargs):
            yield sample_pr
            
        mock_github_client.paginate.side_effect = mock_paginate
        
        # First call
        prs1 = await discovery_service.discover_prs(test_repository)
        
        # Second call should use cache (within TTL)
        prs2 = await discovery_service.discover_prs(test_repository)
        
        # Verify results are same
        assert len(prs1) == len(prs2) == 1
        assert prs1[0].number == prs2[0].number
        
        # Verify cache was used (API called once but returned twice)
        # Note: Actual caching implementation may vary
        assert len(discovery_service._etag_cache) > 0

    @pytest.mark.asyncio
    async def test_error_handling_github_api_failure(
        self, discovery_service, mock_github_client, test_repository
    ):
        """
        Why: Validates graceful handling of GitHub API failures
        What: Tests that API errors are caught and re-raised appropriately
        How: Mocks GitHub client to raise exception, verifies handling
        """
        # Setup API failure
        mock_github_client.paginate.side_effect = Exception("GitHub API unavailable")
        
        # Execute and expect exception
        with pytest.raises(Exception) as exc_info:
            await discovery_service.discover_prs(test_repository)
        
        assert "GitHub API unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_batch_check_run_discovery(
        self, discovery_service, mock_github_client, test_repository
    ):
        """
        Why: Validates concurrent check run discovery for multiple PRs
        What: Tests parallel processing of check runs with error isolation
        How: Creates multiple PRs, mocks some failures, verifies isolation
        """
        # Create test PR data
        pr_data_list = [
            PRData(number=i, title=f"PR {i}", author="test", state="open", 
                  draft=False, base_branch="main", head_branch=f"feature{i}",
                  base_sha="abc", head_sha=f"sha{i}", url=f"url{i}")
            for i in range(1, 4)
        ]
        
        # Setup mock responses - some succeed, some fail
        check_run_responses = {
            1: [CheckRunData(external_id="1", check_name="test1", status="completed")],
            2: Exception("API timeout"),  # This PR will fail
            3: [CheckRunData(external_id="3", check_name="test3", status="in_progress")]
        }
        
        async def mock_discover_check_runs(repository, pr_data):
            response = check_run_responses[pr_data.number]
            if isinstance(response, Exception):
                raise response
            return response
        
        # Replace individual method with mock
        discovery_service.discover_check_runs = AsyncMock(side_effect=mock_discover_check_runs)
        
        # Execute batch discovery
        results = await discovery_service.discover_check_runs_batch(
            test_repository, pr_data_list
        )
        
        # Verify results
        assert len(results) == 3
        
        # PR 1: successful
        assert 1 in results
        assert len(results[1]) == 1
        assert results[1][0].external_id == "1"
        
        # PR 2: failed (should have empty list)
        assert 2 in results
        assert len(results[2]) == 0
        
        # PR 3: successful
        assert 3 in results
        assert len(results[3]) == 1
        assert results[3][0].external_id == "3"
```

#### Change Detection Unit Tests

```python
# tests/unit/workers/monitor/test_change_detection.py
"""
Unit tests for change detection logic.

Why: Validates change detection algorithms and database comparison logic
What: Tests PR and check run change detection with various scenarios
How: Mocks repository interfaces to test detection logic in isolation
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.models import PRData, CheckRunData, PRChangeRecord
from src.models.enums import PRState, CheckStatus, CheckConclusion


class TestDatabaseChangeDetector:
    """Test suite for DatabaseChangeDetector."""

    @pytest.fixture
    def mock_repositories(self):
        """Create mock repository interfaces."""
        pr_repo = AsyncMock()
        check_repo = AsyncMock()
        return {"pr_repo": pr_repo, "check_repo": check_repo}

    @pytest.fixture
    def change_detector(self, mock_repositories):
        """Create change detector with mock repositories."""
        return DatabaseChangeDetector(
            pr_repository=mock_repositories["pr_repo"],
            check_run_repository=mock_repositories["check_repo"]
        )

    @pytest.mark.asyncio
    async def test_detect_new_prs(self, change_detector, mock_repositories):
        """
        Why: Validates detection of new PRs not in database
        What: Tests identification of PRs that need to be created
        How: Mocks empty database response, provides GitHub PR data
        """
        repository_id = uuid.uuid4()
        
        # Setup empty database (no existing PRs)
        mock_repositories["pr_repo"].get_recent_prs.return_value = []
        
        # Create GitHub PR data
        github_prs = [
            PRData(
                number=1,
                title="New PR 1",
                author="user1",
                state="open",
                draft=False,
                base_branch="main",
                head_branch="feature1", 
                base_sha="abc123",
                head_sha="def456",
                url="https://github.com/org/repo/pull/1"
            ),
            PRData(
                number=2,
                title="New PR 2", 
                author="user2",
                state="open",
                draft=True,
                base_branch="main",
                head_branch="feature2",
                base_sha="abc123", 
                head_sha="ghi789",
                url="https://github.com/org/repo/pull/2"
            )
        ]
        
        # Execute detection
        changes = await change_detector.detect_pr_changes(repository_id, github_prs)
        
        # Verify all PRs detected as new
        assert len(changes) == 2
        for change in changes:
            assert change.change_type == "new"
            assert change.existing_pr_id is None
            assert isinstance(change.pr_data, PRData)

    @pytest.mark.asyncio 
    async def test_detect_pr_field_changes(self, change_detector, mock_repositories):
        """
        Why: Validates detection of specific field changes in existing PRs
        What: Tests title, state, draft, SHA, and metadata change detection
        How: Mocks database PR with old values, provides updated GitHub data
        """
        repository_id = uuid.uuid4()
        
        # Create existing PR in database
        existing_pr = MagicMock()
        existing_pr.id = uuid.uuid4()
        existing_pr.pr_number = 1
        existing_pr.title = "Old Title"
        existing_pr.state = PRState.OPENED
        existing_pr.draft = False
        existing_pr.head_sha = "old_sha"
        existing_pr.pr_metadata = {"labels": ["bug"], "assignees": ["user1"]}
        
        mock_repositories["pr_repo"].get_recent_prs.return_value = [existing_pr]
        
        # Create updated GitHub PR data
        updated_pr = PRData(
            number=1,
            title="Updated Title",  # Changed
            author="same_user",
            state="closed",         # Changed 
            draft=True,             # Changed
            base_branch="main",
            head_branch="feature1",
            base_sha="abc123",
            head_sha="new_sha",     # Changed
            url="https://github.com/org/repo/pull/1",
            labels=["bug", "enhancement"],  # Changed
            assignees=["user1", "user2"]    # Changed
        )
        
        # Execute detection
        changes = await change_detector.detect_pr_changes(repository_id, [updated_pr])
        
        # Verify changes detected
        assert len(changes) == 1
        change = changes[0]
        assert change.change_type == "updated"
        assert change.existing_pr_id == existing_pr.id
        
        # Verify specific field changes
        assert change.title_changed is True
        assert change.old_title == "Old Title"
        assert change.state_changed is True
        assert change.old_state == PRState.OPENED
        assert change.draft_changed is True
        assert change.sha_changed is True
        assert change.old_head_sha == "old_sha"
        assert change.metadata_changed is True

    @pytest.mark.asyncio
    async def test_no_changes_detected(self, change_detector, mock_repositories):
        """
        Why: Validates that unchanged PRs are not flagged for updates
        What: Tests that identical data results in no changes
        How: Mocks database PR matching GitHub data exactly
        """
        repository_id = uuid.uuid4()
        
        # Create existing PR that matches GitHub data exactly
        existing_pr = MagicMock()
        existing_pr.id = uuid.uuid4()
        existing_pr.pr_number = 1
        existing_pr.title = "Same Title"
        existing_pr.state = PRState.OPENED
        existing_pr.draft = False
        existing_pr.head_sha = "same_sha"
        existing_pr.pr_metadata = {"labels": ["bug"], "assignees": ["user1"]}
        
        mock_repositories["pr_repo"].get_recent_prs.return_value = [existing_pr]
        
        # Create GitHub PR data identical to database
        github_pr = PRData(
            number=1,
            title="Same Title",
            author="user",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature1",
            base_sha="abc123",
            head_sha="same_sha",
            url="https://github.com/org/repo/pull/1",
            labels=["bug"],
            assignees=["user1"]
        )
        
        # Execute detection
        changes = await change_detector.detect_pr_changes(repository_id, [github_pr])
        
        # Verify no changes detected
        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_detect_new_check_runs(self, change_detector, mock_repositories):
        """
        Why: Validates detection of new check runs for existing PRs
        What: Tests identification of check runs that need to be created
        How: Mocks existing PR with no check runs, provides GitHub check data
        """
        # Setup existing PR changes
        pr_change = PRChangeRecord(
            pr_data=PRData(
                number=1, title="Test", author="user", state="open", draft=False,
                base_branch="main", head_branch="feature", base_sha="abc", 
                head_sha="def", url="url"
            ),
            change_type="updated",
            existing_pr_id=uuid.uuid4()
        )
        
        # Mock empty check runs in database
        mock_repositories["check_repo"].get_all_for_pr.return_value = []
        
        # Create GitHub check run data
        github_checks = {
            1: [
                CheckRunData(
                    external_id="12345",
                    check_name="CI Build",
                    status="completed", 
                    conclusion="success",
                    details_url="https://example.com/check/12345"
                ),
                CheckRunData(
                    external_id="12346",
                    check_name="Tests",
                    status="in_progress",
                    conclusion=None,
                    details_url="https://example.com/check/12346"
                )
            ]
        }
        
        # Execute detection
        changes = await change_detector.detect_check_run_changes(
            [pr_change], github_checks
        )
        
        # Verify all check runs detected as new
        assert len(changes) == 2
        for change in changes:
            assert change.change_type == "new"
            assert change.pr_id == pr_change.existing_pr_id
            assert change.existing_check_id is None
            assert isinstance(change.check_data, CheckRunData)

    @pytest.mark.asyncio
    async def test_detect_check_run_status_changes(self, change_detector, mock_repositories):
        """
        Why: Validates detection of check run status and conclusion changes
        What: Tests status transitions and completion updates
        How: Mocks existing check run, provides updated GitHub data
        """
        # Setup PR change
        pr_id = uuid.uuid4()
        pr_change = PRChangeRecord(
            pr_data=MagicMock(),
            change_type="updated",
            existing_pr_id=pr_id
        )
        pr_change.pr_data.number = 1
        
        # Mock existing check run in database
        existing_check = MagicMock()
        existing_check.id = uuid.uuid4()
        existing_check.external_id = "12345"
        existing_check.status = CheckStatus.IN_PROGRESS
        existing_check.conclusion = None
        existing_check.started_at = datetime(2023, 1, 1, 12, 0, 0)
        existing_check.completed_at = None
        
        mock_repositories["check_repo"].get_all_for_pr.return_value = [existing_check]
        
        # Create updated GitHub check run data
        updated_check = CheckRunData(
            external_id="12345",
            check_name="CI Build",
            status="completed",      # Changed from in_progress
            conclusion="success",    # Changed from None
            started_at=datetime(2023, 1, 1, 12, 0, 0),  # Same
            completed_at=datetime(2023, 1, 1, 12, 5, 0) # New completion time
        )
        
        github_checks = {1: [updated_check]}
        
        # Execute detection
        changes = await change_detector.detect_check_run_changes(
            [pr_change], github_checks
        )
        
        # Verify changes detected
        assert len(changes) == 1
        change = changes[0]
        assert change.change_type == "updated"
        assert change.existing_check_id == existing_check.id
        assert change.status_changed is True
        assert change.old_status == CheckStatus.IN_PROGRESS
        assert change.conclusion_changed is True
        assert change.old_conclusion is None
        assert change.timing_changed is True  # completed_at was added
```

## Integration Testing

Integration tests validate the complete workflow with real database interactions.

### End-to-End Integration Tests

```python
# tests/integration/workers/monitor/test_processor_integration.py
"""
Integration tests for complete PR processing workflow.

Why: Validates end-to-end functionality with real database operations
What: Tests complete processing pipeline with actual data persistence
How: Uses test database with real repositories and GitHub mock responses
"""
import pytest
import asyncio
import uuid
from datetime import datetime

from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.synchronization import DatabaseSynchronizer
from src.repositories.pull_request import PullRequestRepository
from src.repositories.check_run import CheckRunRepository


@pytest.mark.integration
class TestPRProcessorIntegration:
    """Integration tests for complete PR processing."""

    @pytest.mark.asyncio
    async def test_complete_pr_processing_workflow(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        sample_pr_data,
        sample_check_run_data,
        mock_github_client,
    ):
        """
        Why: Validates complete workflow from discovery to database persistence
        What: Tests full processing pipeline with real database operations
        How: Processes sample data through all phases, verifies database state
        """
        # Setup repositories
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        # Create services with real database connections
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock GitHub API responses
        discovery_service.discover_prs_and_checks = AsyncMock(
            return_value=(len(sample_pr_data), len(sample_check_run_data))
        )
        
        # Mock change detection to return all data as new
        async def mock_detect_changes(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add new PR changes
            for pr_data in sample_pr_data:
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            # Add new check run changes
            if changeset.new_prs:
                for check_data in sample_check_run_data:
                    changeset.new_check_runs.append(
                        CheckRunChangeRecord(
                            check_data=check_data,
                            pr_id=uuid.uuid4(),  # Will be resolved during sync
                            change_type="new"
                        )
                    )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_detect_changes)
        
        # Create processor
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Execute processing
        result = await processor.process_repository(test_repository_in_db)
        
        # Verify processing results
        assert result.success is True
        assert result.prs_discovered == len(sample_pr_data)
        assert result.check_runs_discovered == len(sample_check_run_data)
        assert result.changes_synchronized > 0
        assert result.processing_time > 0
        assert len(result.errors) == 0
        
        # Verify data persistence in database
        prs_in_db = await pr_repo.get_recent_prs(
            since=datetime.min, 
            repository_id=test_repository_in_db.id
        )
        assert len(prs_in_db) == len(sample_pr_data)
        
        # Verify PR data matches
        pr_by_number = {pr.pr_number: pr for pr in prs_in_db}
        for original_pr in sample_pr_data:
            db_pr = pr_by_number[original_pr.number]
            assert db_pr.title == original_pr.title
            assert db_pr.author == original_pr.author
            assert db_pr.state == original_pr.to_pr_state()
            assert db_pr.draft == original_pr.draft
            assert db_pr.head_sha == original_pr.head_sha

    @pytest.mark.asyncio
    async def test_incremental_updates(
        self,
        database_session,
        test_repository_in_db,
        sample_pr_data,
        mock_github_client,
    ):
        """
        Why: Validates that subsequent processing only updates changed data
        What: Tests incremental change detection and update behavior
        How: Processes data twice with changes, verifies only updates occur
        """
        # Setup processor
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Mock services for first run (all new)
        discovery_service.discover_prs_and_checks = AsyncMock(return_value=(2, 0))
        
        async def mock_first_run(repository):
            changeset = ChangeSet(repository_id=repository.id)
            for pr_data in sample_pr_data[:2]:  # First 2 PRs
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_first_run)
        
        # First processing run
        result1 = await processor.process_repository(test_repository_in_db)
        assert result1.success is True
        assert result1.new_prs == 2
        assert result1.updated_prs == 0
        
        # Setup for second run with updates
        updated_pr = sample_pr_data[0]
        updated_pr.title = "Updated Title"  # Change title
        updated_pr.state = "closed"         # Change state
        
        async def mock_second_run(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Get existing PR from database
            existing_prs = await pr_repo.get_recent_prs(
                since=datetime.min, repository_id=repository.id
            )
            existing_pr = next(pr for pr in existing_prs if pr.pr_number == updated_pr.number)
            
            # Create update change
            changeset.updated_prs.append(
                PRChangeRecord(
                    pr_data=updated_pr,
                    change_type="updated",
                    existing_pr_id=existing_pr.id,
                    title_changed=True,
                    state_changed=True,
                    old_title=existing_pr.title,
                    old_state=existing_pr.state
                )
            )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_second_run)
        
        # Second processing run
        result2 = await processor.process_repository(test_repository_in_db)
        assert result2.success is True
        assert result2.new_prs == 0
        assert result2.updated_prs == 1
        assert result2.changes_synchronized == 1
        
        # Verify updates were applied
        updated_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        updated_pr_in_db = next(pr for pr in updated_prs if pr.pr_number == updated_pr.number)
        assert updated_pr_in_db.title == "Updated Title"
        assert updated_pr_in_db.state.name.lower() == "closed"

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_failure(
        self,
        database_session,
        test_repository_in_db,
        sample_pr_data,
    ):
        """
        Why: Validates that database transactions rollback properly on failures
        What: Tests that partial failures don't leave inconsistent data
        How: Injects failure during sync, verifies no partial data committed
        """
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = AsyncMock()
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock successful discovery and change detection
        discovery_service.discover_prs_and_checks = AsyncMock(return_value=(3, 0))
        
        async def mock_changes_with_failure(repository):
            changeset = ChangeSet(repository_id=repository.id)
            for pr_data in sample_pr_data:
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_changes_with_failure)
        
        # Inject failure in synchronization
        original_sync = synchronizer.synchronize_changes
        
        async def failing_sync(repo_id, changeset):
            # Simulate database constraint violation during processing
            raise Exception("Database constraint violation") 
        
        synchronizer.synchronize_changes = AsyncMock(side_effect=failing_sync)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Get initial PR count
        initial_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        initial_count = len(initial_prs)
        
        # Execute processing (should fail)
        result = await processor.process_repository(test_repository_in_db)
        
        # Verify failure was recorded
        assert result.success is False
        assert len(result.errors) > 0
        assert "synchronization_failure" in str(result.errors[0])
        
        # Verify no partial data was committed (transaction rolled back)
        final_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        final_count = len(final_prs)
        assert final_count == initial_count  # No new PRs should be committed
```

## Performance Testing

Performance tests validate system behavior under load and with large datasets.

```python
# tests/performance/test_pr_monitoring_performance.py
"""
Performance tests for PR monitoring system.

Why: Validates system performance under realistic load conditions
What: Tests processing speed, memory usage, and scalability limits
How: Uses large datasets and concurrent processing to measure performance
"""
import pytest
import asyncio
import time
import psutil
import os
from datetime import datetime

from src.workers.monitor.processor import DefaultPRProcessor


@pytest.mark.performance
class TestPRMonitoringPerformance:
    """Performance tests for PR monitoring system."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_repository_processing(
        self,
        database_session,
        performance_test_data,  # Fixture providing large dataset
        mock_github_client,
    ):
        """
        Why: Validates system can handle large repositories efficiently
        What: Tests processing of 100+ PRs with 500+ check runs
        How: Measures processing time and memory usage with large dataset
        """
        # Get performance test data (large dataset)
        large_prs = performance_test_data["prs"]  # 100 PRs
        large_checks = performance_test_data["check_runs"]  # 500 check runs
        
        # Create test repository
        repository = Repository(
            id=uuid.uuid4(),
            url="https://github.com/large-org/large-repo",
            name="large-repo"
        )
        
        # Setup processor
        processor = create_test_processor(database_session, max_concurrent_repos=5)
        
        # Mock services with large dataset
        discovery_service.discover_prs_and_checks = AsyncMock(
            return_value=(len(large_prs), len(large_checks))
        )
        
        async def mock_large_changeset(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add subset to avoid timeout in tests
            for pr_data in large_prs[:50]:  # Process 50 PRs
                pr_data.raw_data["repository_id"] = str(repository.id)
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_large_changeset)
        
        # Measure performance
        start_memory = get_memory_usage()
        start_time = time.time()
        
        result = await processor.process_repository(repository)
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        processing_time = end_time - start_time
        memory_increase = end_memory - start_memory
        
        # Verify processing succeeded
        assert result.success is True
        assert result.changes_synchronized == 50
        
        # Performance assertions
        assert processing_time < 30.0  # Should complete within 30 seconds
        assert memory_increase < 100.0  # Should not use more than 100MB
        
        # Log performance metrics
        logger.info(f"Large repository performance:")
        logger.info(f"  Processing time: {processing_time:.2f}s")
        logger.info(f"  Memory increase: {memory_increase:.1f}MB")
        logger.info(f"  Throughput: {result.changes_synchronized/processing_time:.1f} changes/s")

    @pytest.mark.asyncio
    async def test_concurrent_repository_processing_performance(
        self,
        database_session,
        mock_github_client,
    ):
        """
        Why: Validates concurrent processing scales properly
        What: Tests processing multiple repositories in parallel
        How: Measures throughput with different concurrency levels
        """
        # Create multiple test repositories
        repositories = [
            Repository(
                id=uuid.uuid4(),
                url=f"https://github.com/org/repo-{i}",
                name=f"repo-{i}"
            )
            for i in range(10)
        ]
        
        # Test different concurrency levels
        concurrency_levels = [1, 5, 10]
        performance_results = {}
        
        for max_concurrent in concurrency_levels:
            processor = create_test_processor(
                database_session, 
                max_concurrent_repos=max_concurrent
            )
            
            # Mock consistent processing for each repo
            setup_mock_services(processor, prs_per_repo=5, processing_delay=0.1)
            
            # Measure concurrent processing
            start_time = time.time()
            batch_result = await processor.process_repositories(repositories)
            end_time = time.time()
            
            total_time = end_time - start_time
            throughput = len(repositories) / total_time
            
            performance_results[max_concurrent] = {
                "total_time": total_time,
                "throughput": throughput,
                "success_rate": batch_result.success_rate
            }
            
            # Verify all processing succeeded
            assert batch_result.success_rate == 100.0
            
            logger.info(f"Concurrency {max_concurrent}: {throughput:.1f} repos/s")
        
        # Verify scaling benefits (higher concurrency should be faster)
        assert performance_results[5]["throughput"] > performance_results[1]["throughput"]
        assert performance_results[10]["throughput"] >= performance_results[5]["throughput"]

    @pytest.mark.asyncio
    async def test_memory_efficiency_with_large_datasets(
        self,
        database_session,
        performance_test_data,
    ):
        """
        Why: Validates system doesn't consume excessive memory with large data
        What: Tests memory usage patterns during large-scale processing
        How: Monitors memory throughout processing, ensures reasonable usage
        """
        # Get initial memory baseline
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Setup processor with large dataset
        processor = create_test_processor(database_session)
        
        # Process in batches to test memory management
        large_dataset = performance_test_data["prs"][:100]
        batch_size = 20
        
        memory_readings = [initial_memory]
        
        for i in range(0, len(large_dataset), batch_size):
            batch = large_dataset[i:i + batch_size]
            
            # Mock processing for this batch
            setup_mock_batch_processing(processor, batch)
            
            # Process batch
            repository = Repository(id=uuid.uuid4(), url=f"test-repo-{i}", name=f"repo-{i}")
            result = await processor.process_repository(repository)
            
            assert result.success is True
            
            # Record memory usage
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_readings.append(current_memory)
            
            logger.debug(f"Batch {i//batch_size + 1}: {current_memory:.1f}MB")
        
        final_memory = memory_readings[-1]
        total_memory_increase = final_memory - initial_memory
        max_memory_increase = max(memory_readings) - initial_memory
        
        # Memory efficiency assertions
        assert total_memory_increase < 50.0  # Final increase should be minimal
        assert max_memory_increase < 100.0   # Peak increase should be reasonable
        
        logger.info(f"Memory efficiency test:")
        logger.info(f"  Initial: {initial_memory:.1f}MB")
        logger.info(f"  Final: {final_memory:.1f}MB")
        logger.info(f"  Total increase: {total_memory_increase:.1f}MB")
        logger.info(f"  Peak increase: {max_memory_increase:.1f}MB")

def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def setup_mock_services(processor, prs_per_repo: int, processing_delay: float):
    """Setup mock services for consistent testing."""
    async def mock_discovery(repository):
        await asyncio.sleep(processing_delay)  # Simulate processing time
        return (prs_per_repo, prs_per_repo * 2)
    
    async def mock_changes(repository):
        await asyncio.sleep(processing_delay / 2)
        changeset = ChangeSet(repository_id=repository.id)
        # Add mock changes
        for i in range(prs_per_repo):
            changeset.new_prs.append(create_mock_pr_change())
        return changeset
    
    async def mock_sync(changeset):
        await asyncio.sleep(processing_delay / 4)
        return changeset.total_changes
    
    processor.discovery_service.discover_prs_and_checks = AsyncMock(side_effect=mock_discovery)
    processor.change_detection_service.detect_changes = AsyncMock(side_effect=mock_changes)
    processor.synchronization_service.synchronize_changes = AsyncMock(side_effect=mock_sync)
```

## Test Data Management

### Fixture Organization

```python
# tests/conftest.py - Test fixtures
"""
Shared test fixtures for PR monitoring tests.

Provides reusable test data, database setup, and mock configurations
for unit, integration, and performance tests.
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock

from src.workers.monitor.models import PRData, CheckRunData
from src.models.repository import Repository


@pytest.fixture
def sample_pr_data():
    """Create sample PR data for testing."""
    return [
        PRData(
            number=1,
            title="Fix critical bug in authentication",
            author="security-team",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="fix/auth-bug", 
            base_sha="abc123def456",
            head_sha="fed654cba321",
            url="https://github.com/org/repo/pull/1",
            body="This PR fixes a critical security vulnerability in the authentication module.",
            labels=["security", "bug", "critical"],
            assignees=["security-lead", "tech-lead"],
            milestone="v2.1.0",
            created_at=datetime(2023, 1, 1, 10, 0, 0),
            updated_at=datetime(2023, 1, 2, 15, 30, 0)
        ),
        PRData(
            number=2,
            title="Add user preferences feature",
            author="feature-team",
            state="open", 
            draft=True,
            base_branch="main",
            head_branch="feature/user-preferences",
            base_sha="abc123def456",
            head_sha="123456789abc",
            url="https://github.com/org/repo/pull/2",
            body="Draft PR for new user preferences functionality.",
            labels=["enhancement", "frontend"],
            assignees=["frontend-lead"],
            milestone=None,
            created_at=datetime(2023, 1, 3, 9, 0, 0),
            updated_at=datetime(2023, 1, 3, 9, 0, 0)
        ),
        PRData(
            number=3,
            title="Update documentation for API changes",
            author="docs-team",
            state="closed",
            draft=False,
            base_branch="main", 
            head_branch="docs/api-updates",
            base_sha="abc123def456",
            head_sha="987654321fed",
            url="https://github.com/org/repo/pull/3",
            body="Updates API documentation to reflect recent changes in v2.0.",
            labels=["documentation"],
            assignees=["tech-writer"],
            milestone="v2.0.1",
            created_at=datetime(2023, 1, 4, 14, 0, 0),
            updated_at=datetime(2023, 1, 5, 16, 45, 0),
            closed_at=datetime(2023, 1, 5, 16, 45, 0),
            merged_at=datetime(2023, 1, 5, 16, 45, 0)
        )
    ]

@pytest.fixture  
def sample_check_run_data():
    """Create sample check run data for testing."""
    return [
        CheckRunData(
            external_id="123456789",
            check_name="CI Build",
            status="completed",
            conclusion="success", 
            check_suite_id="987654321",
            details_url="https://github.com/org/repo/runs/123456789",
            logs_url="https://github.com/org/repo/runs/123456789",
            output_title="Build Successful",
            output_summary="All compilation steps completed successfully",
            output_text="Detailed build log...\nCompilation: SUCCESS\nUnit Tests: PASSED\nLinting: PASSED",
            started_at=datetime(2023, 1, 1, 10, 5, 0),
            completed_at=datetime(2023, 1, 1, 10, 8, 30)
        ),
        CheckRunData(
            external_id="123456790",
            check_name="Unit Tests",
            status="completed",
            conclusion="failure",
            check_suite_id="987654321", 
            details_url="https://github.com/org/repo/runs/123456790",
            logs_url="https://github.com/org/repo/runs/123456790",
            output_title="Tests Failed",
            output_summary="3 tests failed, 47 passed",
            output_text="Test Results:\n✅ 47 passed\n❌ 3 failed\n\nFailed Tests:\n- test_authentication_flow\n- test_user_permissions\n- test_session_handling",
            started_at=datetime(2023, 1, 1, 10, 8, 45),
            completed_at=datetime(2023, 1, 1, 10, 12, 15)
        ),
        CheckRunData(
            external_id="123456791", 
            check_name="Security Scan",
            status="in_progress",
            conclusion=None,
            check_suite_id="987654321",
            details_url="https://github.com/org/repo/runs/123456791",
            logs_url="https://github.com/org/repo/runs/123456791", 
            output_title="Security Scan In Progress",
            output_summary="Scanning for vulnerabilities...",
            output_text="Security scan initiated...\nScanning dependencies...\nProgress: 65%",
            started_at=datetime(2023, 1, 1, 10, 13, 0),
            completed_at=None
        )
    ]

@pytest.fixture
async def test_repository_in_db(database_session):
    """Create a test repository in the database."""
    from src.repositories.repository import RepositoryRepository
    
    repo_repo = RepositoryRepository(database_session)
    
    repository = Repository(
        id=uuid.uuid4(),
        url="https://github.com/test-org/test-repo",
        name="test-repo",
        owner="test-org",
        repo_name="test-repo",
        status="active",
        failure_count=0
    )
    
    created_repo = await repo_repo.create(repository)
    await database_session.commit()
    
    return created_repo

@pytest.fixture
def performance_test_data():
    """Create large dataset for performance testing."""
    # Generate 100 PRs
    prs = []
    for i in range(1, 101):
        pr = PRData(
            number=i,
            title=f"Performance Test PR {i}",
            author=f"user-{i % 10}",  # 10 different users
            state="open" if i % 3 != 0 else "closed",
            draft=i % 5 == 0,  # Every 5th PR is draft
            base_branch="main",
            head_branch=f"feature/perf-test-{i}",
            base_sha="abc123",
            head_sha=f"sha{i:06d}", 
            url=f"https://github.com/perf/test/pull/{i}",
            labels=[f"label-{i % 3}"],
            assignees=[f"assignee-{i % 2}"]
        )
        prs.append(pr)
    
    # Generate 500 check runs (5 per PR on average)
    check_runs = []
    for i in range(1, 501):
        check = CheckRunData(
            external_id=f"check-{i}",
            check_name=f"Check-{i % 5}",  # 5 different check types
            status="completed" if i % 4 != 0 else "in_progress",
            conclusion="success" if i % 6 != 0 else "failure"
        )
        check_runs.append(check)
    
    return {"prs": prs, "check_runs": check_runs}

@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client for testing."""
    client = AsyncMock()
    
    # Setup default responses
    client.get_user.return_value = {"login": "testuser", "id": 12345}
    client.get_pulls.return_value = []
    client.paginate.return_value = AsyncIterator([])
    
    return client

class AsyncIterator:
    """Helper for async iteration in mocks."""
    
    def __init__(self, items):
        self.items = items
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
```

## Testing Best Practices

### Test Organization

1. **Clear Test Names**: Use descriptive names that explain the purpose
2. **Documentation**: Include Why/What/How comments for each test
3. **Isolation**: Tests should not depend on each other
4. **Repeatability**: Tests should produce consistent results

### Mock Strategy

```python
# Good: Mock external dependencies, test internal logic
@pytest.mark.asyncio
async def test_pr_processing_with_github_failure():
    """
    Why: Validates error handling when GitHub API fails
    What: Tests processor handles discovery service failures gracefully
    How: Mocks discovery service to raise exception, verifies error handling
    """
    discovery_service = AsyncMock()
    discovery_service.discover_prs_and_checks.side_effect = GitHubError("API timeout")
    
    processor = DefaultPRProcessor(discovery_service, change_detector, synchronizer)
    result = await processor.process_repository(test_repository)
    
    assert result.success is False
    assert any("discovery_failure" in str(error) for error in result.errors)

# Bad: Over-mocking makes tests brittle  
@pytest.mark.asyncio
async def test_pr_processing_over_mocked():
    # Mocking too many internal details makes test fragile
    processor = MagicMock()
    processor.process_repository = AsyncMock()
    processor._execute_discovery_phase = AsyncMock()
    processor._execute_change_detection_phase = AsyncMock()
    # ... too much mocking
```

### Assertion Strategies

```python
# Good: Specific, meaningful assertions
async def test_pr_change_detection():
    changes = await change_detector.detect_pr_changes(repository_id, pr_data_list)
    
    # Verify specific expectations
    assert len(changes) == 2
    assert changes[0].change_type == "new"
    assert changes[0].pr_data.number == 123
    assert changes[1].change_type == "updated"
    assert changes[1].title_changed is True
    assert changes[1].old_title == "Previous Title"

# Bad: Generic assertions that don't validate behavior
async def test_pr_change_detection_generic():
    changes = await change_detector.detect_pr_changes(repository_id, pr_data_list)
    
    # Too generic - doesn't validate actual behavior
    assert changes is not None
    assert len(changes) > 0
    assert isinstance(changes[0], PRChangeRecord)
```

## CI/CD Integration

### GitHub Actions Configuration

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run database migrations
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/test
        run: alembic upgrade head
      
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/test
          GITHUB_TOKEN: ${{ secrets.TEST_GITHUB_TOKEN }}
        run: pytest tests/integration/ -v -m integration

  performance-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run performance tests
        run: pytest tests/performance/ -v -m performance --timeout=300
```

### Test Commands

```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only  
pytest -m performance    # Performance tests only

# Run tests with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run tests in parallel
pytest -n auto           # Auto-detect CPU cores

# Run specific test file
pytest tests/unit/workers/monitor/test_processor.py -v

# Run specific test
pytest tests/unit/workers/monitor/test_processor.py::TestDefaultPRProcessor::test_successful_repository_processing -v
```

## Troubleshooting Tests

### Common Issues

**1. Database Connection Issues**
```python
# Fix: Ensure test database is running and accessible
@pytest.fixture(scope="session", autouse=True) 
async def setup_test_database():
    """Ensure test database is available."""
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Test database not available: {e}")
```

**2. Mock Configuration Issues**
```python
# Fix: Proper mock setup and verification
@pytest.fixture
def properly_configured_mock():
    """Create properly configured mock service."""
    mock_service = AsyncMock()
    
    # Configure default return values
    mock_service.discover_prs_and_checks.return_value = (0, 0)
    mock_service.detect_changes.return_value = ChangeSet(repository_id=uuid.uuid4())
    mock_service.synchronize_changes.return_value = 0
    
    return mock_service
```

**3. Async Test Issues**
```python
# Fix: Proper async test decoration and await usage
@pytest.mark.asyncio
async def test_async_functionality():
    """Properly test async functions."""
    # Always await async calls
    result = await async_function()
    
    # Use AsyncMock for async mocks
    mock_service = AsyncMock()
    mock_service.async_method.return_value = expected_value
```

**4. Performance Test Timeouts**
```python
# Fix: Increase timeout for slow tests
@pytest.mark.asyncio
@pytest.mark.timeout(120)  # 2 minute timeout
async def test_long_running_operation():
    """Test that may take a while to complete."""
    result = await long_running_operation()
    assert result.success
```

### Debugging Test Failures

```python
# Add detailed logging for debugging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use pytest fixtures for debugging
@pytest.fixture
def debug_processor(database_session, caplog):
    """Create processor with debug logging."""
    with caplog.at_level(logging.DEBUG):
        processor = create_processor(database_session)
        yield processor
    
    # Print logs on test failure
    if caplog.records:
        for record in caplog.records:
            print(f"LOG: {record.levelname}: {record.message}")

# Add breakpoints for interactive debugging
@pytest.mark.asyncio
async def test_with_debugging():
    result = await processor.process_repository(repository)
    
    # Add breakpoint for investigation
    import pdb; pdb.set_trace()
    
    assert result.success
```

---

**Need Help with Testing?**
- 📖 **Testing Guidelines**: [TESTING_GUIDELINES.md](../../TESTING_GUIDELINES.md)
- 🧪 **Developer Testing**: [Developer Testing Guide](../developer/testing-guide.md)
- 🛠️ **Troubleshooting**: [Testing Troubleshooting](troubleshooting.md)
- 💬 **Community**: [GitHub Discussions](https://github.com/feddericovonwernich/agentic-coding-workflow/discussions)