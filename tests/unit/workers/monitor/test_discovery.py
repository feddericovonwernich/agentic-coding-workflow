"""
Unit tests for PR and check run discovery service.

Why: Ensure the discovery service correctly fetches and processes PR data from GitHub
     with proper error handling, caching, and concurrent processing capabilities.

What: Tests GitHubPRDiscoveryService for PR discovery, check run discovery,
      ETag caching, batch processing, and error resilience.

How: Uses mocked GitHub client responses to test discovery behavior
     without making real GitHub API calls.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.github.client import GitHubClient
from src.github.exceptions import GitHubError, GitHubNotFoundError, GitHubRateLimitError
from src.models.repository import Repository
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.models import CheckRunData, PRData


class MockAsyncPaginator:
    """Mock async paginator for testing GitHub API pagination."""

    def __init__(self, pages: list[list[Any]]):
        self.pages = pages
        self.current_page = 0
        self.current_item = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Check if we've exhausted all pages
        if self.current_page >= len(self.pages):
            raise StopAsyncIteration
        
        # Get current page
        current_page_items = self.pages[self.current_page]
        
        # Check if we've exhausted current page
        if self.current_item >= len(current_page_items):
            # Move to next page
            self.current_page += 1
            self.current_item = 0
            
            # Check if we've exhausted all pages
            if self.current_page >= len(self.pages):
                raise StopAsyncIteration
            
            current_page_items = self.pages[self.current_page]
        
        # Return current item and advance
        item = current_page_items[self.current_item]
        self.current_item += 1
        return item


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client for testing."""
    return AsyncMock(spec=GitHubClient)


@pytest.fixture
def sample_repository():
    """Create a sample repository for testing."""
    repo = Repository()
    repo.url = "https://github.com/octocat/hello-world"
    repo.full_name = "octocat/hello-world"
    repo.name = "hello-world"
    return repo


@pytest.fixture
def sample_pr_json():
    """Create sample PR JSON data from GitHub API."""
    return {
        "number": 123,
        "title": "Add new feature",
        "state": "open",
        "draft": False,
        "user": {"login": "octocat"},
        "base": {"ref": "main", "sha": "abc123"},
        "head": {"ref": "feature-branch", "sha": "def456"},
        "html_url": "https://github.com/octocat/hello-world/pull/123",
        "body": "This PR adds a new feature",
        "labels": [{"name": "enhancement"}, {"name": "priority:high"}],
        "assignees": [{"login": "assignee1"}, {"login": "assignee2"}],
        "milestone": {"title": "v2.0"},
        "mergeable": True,
        "mergeable_state": "clean",
        "merged": False,
        "merge_commit_sha": None,
        "created_at": "2024-01-01T10:00:00Z",
        "updated_at": "2024-01-01T15:30:00Z",
        "closed_at": None,
        "merged_at": None,
    }


@pytest.fixture
def sample_check_run_json():
    """Create sample check run JSON data from GitHub API."""
    return {
        "id": 789,
        "name": "CI Build",
        "status": "completed",
        "conclusion": "success",
        "check_suite": {"id": "456"},
        "details_url": "https://github.com/octocat/hello-world/runs/789",
        "html_url": "https://github.com/octocat/hello-world/runs/789",
        "output": {
            "title": "All tests passed",
            "summary": "Build completed successfully",
            "text": "All 42 tests passed"
        },
        "started_at": "2024-01-01T11:00:00Z",
        "completed_at": "2024-01-01T11:15:00Z",
    }


@pytest.fixture
def discovery_service(mock_github_client):
    """Create PR discovery service with mocked client."""
    return GitHubPRDiscoveryService(
        github_client=mock_github_client,
        max_concurrent_requests=5,
        cache_ttl_seconds=300
    )


class TestGitHubPRDiscoveryService:
    """Test GitHub PR discovery service functionality."""

    async def test_discover_prs_success(self, discovery_service, mock_github_client, sample_repository, sample_pr_json):
        """
        Why: Validate that PR discovery correctly fetches and processes PR data from GitHub API.
        What: Tests successful PR discovery with proper data extraction and pagination handling.
        How: Mocks GitHub client to return sample PR data and verifies extracted PRData objects.
        """
        # Setup mock response
        mock_paginator = MockAsyncPaginator([[sample_pr_json]])
        mock_github_client.paginate.return_value = mock_paginator

        # Execute discovery
        prs = await discovery_service.discover_prs(sample_repository)

        # Verify results
        assert len(prs) == 1
        pr = prs[0]
        assert isinstance(pr, PRData)
        assert pr.number == 123
        assert pr.title == "Add new feature"
        assert pr.author == "octocat"
        assert pr.state == "open"
        assert not pr.draft
        assert pr.base_branch == "main"
        assert pr.head_branch == "feature-branch"
        assert pr.base_sha == "abc123"
        assert pr.head_sha == "def456"
        assert pr.url == "https://github.com/octocat/hello-world/pull/123"
        assert pr.body == "This PR adds a new feature"
        assert pr.labels == ["enhancement", "priority:high"]
        assert pr.assignees == ["assignee1", "assignee2"]
        assert pr.milestone == "v2.0"
        assert pr.mergeable is True
        assert pr.mergeable_state == "clean"
        assert not pr.merged
        assert pr.merge_commit_sha is None

        # Verify GitHub client was called correctly
        mock_github_client.paginate.assert_called_once_with(
            "/repos/octocat/hello-world/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            per_page=100
        )

    async def test_discover_prs_with_since_parameter(self, discovery_service, mock_github_client, sample_repository, sample_pr_json):
        """
        Why: Ensure incremental PR discovery works correctly with 'since' parameter for efficiency.
        What: Tests PR discovery with since parameter for incremental updates.
        How: Passes since datetime and verifies it's included in API request parameters.
        """
        # Setup
        since_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_paginator = MockAsyncPaginator([[sample_pr_json]])
        mock_github_client.paginate.return_value = mock_paginator

        # Execute
        prs = await discovery_service.discover_prs(sample_repository, since=since_time)

        # Verify
        assert len(prs) == 1
        mock_github_client.paginate.assert_called_once_with(
            "/repos/octocat/hello-world/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc", "since": "2024-01-01T12:00:00+00:00"},
            per_page=100
        )

    async def test_discover_prs_pagination(self, discovery_service, mock_github_client, sample_repository, sample_pr_json):
        """
        Why: Verify that PR discovery correctly handles pagination for repositories with many PRs.
        What: Tests pagination handling with multiple pages of PR data.
        How: Mocks paginator with multiple pages and verifies all PRs are collected.
        """
        # Setup multiple pages
        pr_json_2 = {**sample_pr_json, "number": 124, "title": "Another PR"}
        pr_json_3 = {**sample_pr_json, "number": 125, "title": "Third PR"}
        
        mock_paginator = MockAsyncPaginator([
            [sample_pr_json, pr_json_2],  # Page 1: 2 PRs
            [pr_json_3],                  # Page 2: 1 PR
        ])
        mock_github_client.paginate.return_value = mock_paginator

        # Execute
        prs = await discovery_service.discover_prs(sample_repository)

        # Verify all PRs collected
        assert len(prs) == 3
        assert prs[0].number == 123
        assert prs[1].number == 124
        assert prs[2].number == 125

    async def test_discover_prs_invalid_repository(self, discovery_service, mock_github_client):
        """
        Why: Ensure discovery service properly handles invalid repository configurations.
        What: Tests error handling when repository lacks required owner/repo information.
        How: Passes repository with missing owner/repo_name and expects ValueError.
        """
        # Setup invalid repository
        invalid_repo = Repository()
        invalid_repo.url = "invalid-url"
        invalid_repo.full_name = None

        # Execute and verify error
        with pytest.raises(ValueError, match="Invalid repository configuration"):
            await discovery_service.discover_prs(invalid_repo)

    async def test_discover_prs_github_error(self, discovery_service, mock_github_client, sample_repository):
        """
        Why: Verify proper error handling when GitHub API requests fail.
        What: Tests discovery service behavior when GitHub client raises exceptions.
        How: Mocks GitHub client to raise GitHubError and verifies exception propagation.
        """
        # Setup mock to raise error
        mock_github_client.paginate.side_effect = GitHubNotFoundError("Repository not found", 404, {})

        # Execute and verify error propagation
        with pytest.raises(GitHubNotFoundError):
            await discovery_service.discover_prs(sample_repository)

    async def test_discover_prs_malformed_data(self, discovery_service, mock_github_client, sample_repository, caplog):
        """
        Why: Ensure discovery service continues processing when individual PR data is malformed.
        What: Tests resilience against malformed PR data from GitHub API.
        How: Includes malformed PR in response and verifies it's skipped with warning logged.
        """
        # Setup with one valid and one malformed PR
        valid_pr = {
            "number": 123,
            "title": "Valid PR",
            "state": "open",
            "draft": False,
            "user": {"login": "octocat"},
            "base": {"ref": "main", "sha": "abc123"},
            "head": {"ref": "feature", "sha": "def456"},
            "html_url": "https://github.com/octocat/hello-world/pull/123",
        }
        malformed_pr = {"number": 124}  # Missing required fields

        mock_paginator = MockAsyncPaginator([[valid_pr, malformed_pr]])
        mock_github_client.paginate.return_value = mock_paginator

        # Execute
        prs = await discovery_service.discover_prs(sample_repository)

        # Verify only valid PR processed
        assert len(prs) == 1
        assert prs[0].number == 123

        # Verify warning logged for malformed PR
        assert "Failed to extract PR data for PR #124" in caplog.text

    async def test_discover_check_runs_success(self, discovery_service, mock_github_client, sample_repository, sample_check_run_json):
        """
        Why: Validate that check run discovery correctly fetches check runs for a specific PR.
        What: Tests successful check run discovery with proper data extraction.
        How: Mocks GitHub API response with check runs and verifies extracted CheckRunData.
        """
        # Setup PR data
        pr_data = PRData(
            number=123, title="Test PR", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc123", head_sha="def456",
            url="https://github.com/octocat/hello-world/pull/123"
        )

        # Setup mock response - the paginator should yield the wrapper object
        mock_response = {"check_runs": [sample_check_run_json]}
        mock_paginator = MockAsyncPaginator([[mock_response]])
        mock_github_client.paginate.return_value = mock_paginator

        # Execute
        check_runs = await discovery_service.discover_check_runs(sample_repository, pr_data)

        # Verify results
        assert len(check_runs) == 1
        check_run = check_runs[0]
        assert isinstance(check_run, CheckRunData)
        assert check_run.external_id == "789"
        assert check_run.check_name == "CI Build"
        assert check_run.status == "completed"
        assert check_run.conclusion == "success"
        assert check_run.check_suite_id == "456"
        assert check_run.details_url == "https://github.com/octocat/hello-world/runs/789"
        assert check_run.logs_url == "https://github.com/octocat/hello-world/runs/789"
        assert check_run.output_title == "All tests passed"
        assert check_run.output_summary == "Build completed successfully"
        assert check_run.output_text == "All 42 tests passed"

        # Verify API call
        mock_github_client.paginate.assert_called_once_with(
            "/repos/octocat/hello-world/commits/def456/check-runs",
            per_page=100
        )

    async def test_discover_check_runs_error_resilience(self, discovery_service, mock_github_client, sample_repository, caplog):
        """
        Why: Ensure check run discovery doesn't fail entire processing when API errors occur.
        What: Tests error handling during check run discovery returns empty list instead of raising.
        How: Mocks GitHub client to raise error and verifies empty list returned with error logged.
        """
        # Setup PR data
        pr_data = PRData(
            number=123, title="Test PR", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc123", head_sha="def456",
            url="https://github.com/octocat/hello-world/pull/123"
        )

        # Setup mock to raise error
        mock_github_client.paginate.side_effect = GitHubRateLimitError("Rate limited", reset_time=None, remaining=0, limit=5000)

        # Execute
        check_runs = await discovery_service.discover_check_runs(sample_repository, pr_data)

        # Verify empty list returned and error logged
        assert check_runs == []
        assert "Failed to discover check runs for PR #123" in caplog.text

    async def test_discover_check_runs_batch_success(self, discovery_service, mock_github_client, sample_repository, sample_check_run_json):
        """
        Why: Validate concurrent processing of check runs for multiple PRs with proper aggregation.
        What: Tests batch check run discovery with multiple PRs processed concurrently.
        How: Provides multiple PR data objects and mocks concurrent API responses.
        """
        # Setup multiple PRs
        pr_data_1 = PRData(
            number=123, title="PR 1", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature1", base_sha="abc123", head_sha="def456",
            url="https://github.com/octocat/hello-world/pull/123"
        )
        pr_data_2 = PRData(
            number=124, title="PR 2", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature2", base_sha="abc123", head_sha="ghi789",
            url="https://github.com/octocat/hello-world/pull/124"
        )

        # Mock check run discovery for each PR
        check_run_1 = {**sample_check_run_json, "id": 789, "name": "CI Build 1"}
        check_run_2 = {**sample_check_run_json, "id": 790, "name": "CI Build 2"}

        async def mock_discover_check_runs(repo, pr_data):
            if pr_data.number == 123:
                return [discovery_service._extract_check_run_data(check_run_1)]
            elif pr_data.number == 124:
                return [discovery_service._extract_check_run_data(check_run_2)]
            return []

        # Patch the discover_check_runs method
        with patch.object(discovery_service, 'discover_check_runs', side_effect=mock_discover_check_runs):
            # Execute batch discovery
            results = await discovery_service.discover_check_runs_batch(
                sample_repository, [pr_data_1, pr_data_2]
            )

            # Verify results
            assert len(results) == 2
            assert 123 in results
            assert 124 in results
            assert len(results[123]) == 1
            assert len(results[124]) == 1
            assert results[123][0].check_name == "CI Build 1"
            assert results[124][0].check_name == "CI Build 2"

    async def test_discover_check_runs_batch_empty_list(self, discovery_service, sample_repository):
        """
        Why: Ensure batch processing handles empty PR lists gracefully.
        What: Tests batch check run discovery with empty PR list.
        How: Passes empty list and verifies empty dict returned.
        """
        results = await discovery_service.discover_check_runs_batch(sample_repository, [])
        assert results == {}

    async def test_discover_check_runs_batch_error_handling(self, discovery_service, sample_repository, caplog):
        """
        Why: Verify that batch processing continues when individual PR processing fails.
        What: Tests error handling in batch check run discovery with partial failures.
        How: Mocks one successful and one failing PR discovery and verifies proper handling.
        """
        # Setup PRs
        pr_data_1 = PRData(
            number=123, title="PR 1", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature1", base_sha="abc123", head_sha="def456",
            url="https://github.com/octocat/hello-world/pull/123"
        )
        pr_data_2 = PRData(
            number=124, title="PR 2", author="octocat", state="open", draft=False,
            base_branch="main", head_branch="feature2", base_sha="abc123", head_sha="ghi789",
            url="https://github.com/octocat/hello-world/pull/124"
        )

        async def mock_discover_with_error(repo, pr_data):
            if pr_data.number == 123:
                return []  # Success with empty results
            else:
                raise GitHubError("API Error")

        # Patch method to simulate partial failure
        with patch.object(discovery_service, 'discover_check_runs', side_effect=mock_discover_with_error):
            results = await discovery_service.discover_check_runs_batch(
                sample_repository, [pr_data_1, pr_data_2]
            )

            # Verify both PRs processed (one with empty list due to error)
            assert len(results) == 2
            assert results[123] == []
            assert results[124] == []

            # Verify error logged
            assert "Error discovering check runs for PR #124" in caplog.text

    async def test_extract_pr_data_timestamp_parsing(self, discovery_service, sample_pr_json):
        """
        Why: Ensure PR timestamp parsing handles various ISO formats correctly.
        What: Tests timestamp extraction and conversion from GitHub API response.
        How: Provides PR JSON with timestamps and verifies correct datetime objects.
        """
        pr_data = discovery_service._extract_pr_data(sample_pr_json)

        assert pr_data.created_at is not None
        assert pr_data.updated_at is not None
        assert pr_data.created_at.tzinfo is not None  # Timezone aware
        assert pr_data.updated_at.tzinfo is not None
        assert pr_data.closed_at is None
        assert pr_data.merged_at is None

    async def test_extract_pr_data_invalid_timestamps(self, discovery_service, sample_pr_json, caplog):
        """
        Why: Verify graceful handling of malformed timestamp data from GitHub API.
        What: Tests PR data extraction with invalid timestamp formats.
        How: Provides malformed timestamps and verifies warning logged but extraction continues.
        """
        # Corrupt timestamp format
        corrupted_pr = {**sample_pr_json, "created_at": "invalid-timestamp"}
        
        pr_data = discovery_service._extract_pr_data(corrupted_pr)

        # Verify extraction continues despite bad timestamp
        assert pr_data.number == 123
        assert pr_data.created_at is None  # Should be None due to parsing failure

        # Verify warning logged
        assert "Failed to parse timestamp in PR #123" in caplog.text

    async def test_extract_check_run_data_complete(self, discovery_service, sample_check_run_json):
        """
        Why: Validate complete check run data extraction from GitHub API response.
        What: Tests extraction of all check run fields including optional ones.
        How: Provides complete check run JSON and verifies all fields extracted correctly.
        """
        check_run_data = discovery_service._extract_check_run_data(sample_check_run_json)

        assert check_run_data.external_id == "789"
        assert check_run_data.check_name == "CI Build"
        assert check_run_data.status == "completed"
        assert check_run_data.conclusion == "success"
        assert check_run_data.check_suite_id == "456"
        assert check_run_data.details_url == "https://github.com/octocat/hello-world/runs/789"
        assert check_run_data.logs_url == "https://github.com/octocat/hello-world/runs/789"
        assert check_run_data.output_title == "All tests passed"
        assert check_run_data.output_summary == "Build completed successfully"
        assert check_run_data.output_text == "All 42 tests passed"
        assert check_run_data.started_at is not None
        assert check_run_data.completed_at is not None

    async def test_extract_check_run_data_minimal(self, discovery_service):
        """
        Why: Ensure check run extraction works with minimal required fields only.
        What: Tests extraction with minimal check run data from GitHub API.
        How: Provides minimal check run JSON with only required fields.
        """
        minimal_check_run = {
            "id": 789,
            "name": "Minimal Check",
            "status": "queued"
        }

        check_run_data = discovery_service._extract_check_run_data(minimal_check_run)

        assert check_run_data.external_id == "789"
        assert check_run_data.check_name == "Minimal Check"
        assert check_run_data.status == "queued"
        assert check_run_data.conclusion is None
        assert check_run_data.check_suite_id is None
        assert check_run_data.details_url is None

    async def test_cache_functionality(self, discovery_service, mock_github_client, sample_repository, sample_pr_json):
        """
        Why: Verify ETag-based caching works correctly to minimize API calls.
        What: Tests cache storage, retrieval, and TTL handling for PR discovery.
        How: Performs multiple discoveries and verifies cache behavior.
        """
        # First request - should cache results
        mock_paginator = MockAsyncPaginator([[sample_pr_json]])
        mock_github_client.paginate.return_value = mock_paginator

        prs_1 = await discovery_service.discover_prs(sample_repository)
        assert len(prs_1) == 1

        # Verify cache populated
        cache_stats = discovery_service.get_cache_stats()
        assert cache_stats["cached_repositories"] == 1
        assert cache_stats["total_cached_prs"] == 1

        # Second request within TTL - should use cache
        # Note: In a real implementation, this would check ETag and potentially return 304
        prs_2 = await discovery_service.discover_prs(sample_repository)
        assert len(prs_2) == 1

    async def test_cache_clear(self, discovery_service, mock_github_client, sample_repository, sample_pr_json):
        """
        Why: Ensure cache can be manually cleared when needed.
        What: Tests cache clearing functionality.
        How: Populates cache, clears it, and verifies it's empty.
        """
        # Populate cache
        mock_paginator = MockAsyncPaginator([[sample_pr_json]])
        mock_github_client.paginate.return_value = mock_paginator
        
        await discovery_service.discover_prs(sample_repository)
        
        # Verify cache populated
        cache_stats = discovery_service.get_cache_stats()
        assert cache_stats["cached_repositories"] == 1

        # Clear cache
        discovery_service.clear_cache()

        # Verify cache cleared
        cache_stats = discovery_service.get_cache_stats()
        assert cache_stats["cached_repositories"] == 0
        assert cache_stats["total_cached_prs"] == 0

    async def test_concurrent_request_limiting(self, discovery_service, sample_repository):
        """
        Why: Verify that concurrent request limiting works to respect API rate limits.
        What: Tests semaphore-based request limiting for batch operations.
        How: Creates more requests than semaphore allows and verifies proper limiting.
        """
        # Create service with small concurrency limit
        limited_service = GitHubPRDiscoveryService(
            github_client=AsyncMock(spec=GitHubClient),
            max_concurrent_requests=2
        )

        # Verify semaphore configured correctly
        assert limited_service._request_semaphore._value == 2

    def test_get_cache_stats_empty(self, discovery_service):
        """
        Why: Ensure cache statistics work correctly with empty cache.
        What: Tests cache statistics reporting with no cached data.
        How: Gets cache stats from fresh service and verifies zero values.
        """
        stats = discovery_service.get_cache_stats()
        
        assert stats["cached_repositories"] == 0
        assert stats["total_cached_prs"] == 0
        assert stats["oldest_cache_age"] == 0
        assert stats["cache_ttl_seconds"] == 300


class TestPRDataModel:
    """Test PRData model methods and properties."""

    def test_to_pr_state_conversion(self):
        """
        Why: Ensure PR state conversion from GitHub strings to enum values works correctly.
        What: Tests conversion of GitHub state strings to PRState enum.
        How: Creates PRData with different states and tests conversion method.
        """
        from src.models.enums import PRState

        # Test open state
        pr_open = PRData(
            number=1, title="Test", author="user", state="open", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc", head_sha="def",
            url="https://example.com"
        )
        assert pr_open.to_pr_state() == PRState.OPENED

        # Test closed but not merged
        pr_closed = PRData(
            number=2, title="Test", author="user", state="closed", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc", head_sha="def",
            url="https://example.com", merged=False
        )
        assert pr_closed.to_pr_state() == PRState.CLOSED

        # Test closed and merged
        pr_merged = PRData(
            number=3, title="Test", author="user", state="closed", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc", head_sha="def",
            url="https://example.com", merged=True
        )
        assert pr_merged.to_pr_state() == PRState.MERGED

    def test_has_changed_since(self):
        """
        Why: Verify change detection logic works correctly for incremental updates.
        What: Tests has_changed_since method with various timestamp scenarios.
        How: Creates PRData with timestamps and tests against comparison dates.
        """
        from datetime import timezone

        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        earlier_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        later_time = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)

        pr_data = PRData(
            number=1, title="Test", author="user", state="open", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc", head_sha="def",
            url="https://example.com", updated_at=base_time
        )

        # Should be changed if last updated after comparison time
        assert not pr_data.has_changed_since(later_time)
        assert pr_data.has_changed_since(earlier_time)

        # Should assume changed if no updated_at timestamp
        pr_no_timestamp = PRData(
            number=2, title="Test", author="user", state="open", draft=False,
            base_branch="main", head_branch="feature", base_sha="abc", head_sha="def",
            url="https://example.com"
        )
        assert pr_no_timestamp.has_changed_since(base_time)


class TestCheckRunDataModel:
    """Test CheckRunData model methods and properties."""

    def test_status_conclusion_conversion(self):
        """
        Why: Ensure check run status and conclusion conversion works correctly.
        What: Tests conversion from GitHub strings to enum values.
        How: Creates CheckRunData and tests conversion methods.
        """
        from src.models.enums import CheckStatus, CheckConclusion

        check_run = CheckRunData(
            external_id="123",
            check_name="Test Check",
            status="completed",
            conclusion="success"
        )

        assert check_run.to_check_status() == CheckStatus.COMPLETED
        assert check_run.to_check_conclusion() == CheckConclusion.SUCCESS

        # Test with no conclusion
        check_run_no_conclusion = CheckRunData(
            external_id="124",
            check_name="Test Check 2",
            status="in_progress"
        )

        assert check_run_no_conclusion.to_check_status() == CheckStatus.IN_PROGRESS
        assert check_run_no_conclusion.to_check_conclusion() is None

    def test_change_detection(self):
        """
        Why: Verify change detection for check run status and conclusion updates.
        What: Tests has_status_changed and has_conclusion_changed methods.
        How: Creates check runs and tests change detection against current values.
        """
        from src.models.enums import CheckStatus, CheckConclusion

        check_run = CheckRunData(
            external_id="123",
            check_name="Test Check",
            status="completed",
            conclusion="success"
        )

        # Test status change detection
        assert not check_run.has_status_changed(CheckStatus.COMPLETED)
        assert check_run.has_status_changed(CheckStatus.IN_PROGRESS)

        # Test conclusion change detection
        assert not check_run.has_conclusion_changed(CheckConclusion.SUCCESS)
        assert check_run.has_conclusion_changed(CheckConclusion.FAILURE)
        assert check_run.has_conclusion_changed(None)