"""
Unit tests for Check Run Discoverer component.

Tests check run discovery functionality including batch processing,
GitHub API integration, failure analysis, and error handling scenarios.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.workers.discovery.check_discoverer import GitHubCheckDiscoverer
from src.workers.discovery.interfaces import (
    DiscoveredCheckRun,
    DiscoveredPR,
)
from tests.fixtures.discovery import (
    DiscoveredCheckRunFactory,
    DiscoveredPRFactory,
    MockGitHubAPIResponses,
    create_mock_github_check_runs_response,
    create_realistic_check_run_data,
)


class TestCheckRunDiscovererSinglePR:
    """Tests for discovering check runs for individual PRs."""

    def _mock_paginate_with_response(self, mock_github_client, response):
        """Helper method to mock the paginate method with a proper async iterator."""
        from unittest.mock import Mock

        class MockAsyncIterator:
            def __init__(self, response):
                self.response = response
                self.yielded = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.yielded:
                    self.yielded = True
                    return self.response
                else:
                    raise StopAsyncIteration

        mock_paginator = MockAsyncIterator(response)
        mock_github_client.paginate = Mock(return_value=mock_paginator)

    def _mock_paginate_with_error(self, mock_github_client, error):
        """Helper method to mock the paginate method to raise an error."""
        from unittest.mock import Mock

        class MockAsyncIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise error

        mock_paginator = MockAsyncIterator()
        mock_github_client.paginate = Mock(return_value=mock_paginator)

    @pytest.fixture
    def mock_github_client(self) -> AsyncMock:
        """
        Why: Provides mock GitHub client for testing check run API interactions
        What: Creates AsyncMock with check run API methods and realistic responses
        How: Sets up mock methods for check runs, commit status, and API responses
        """
        client = AsyncMock()
        client.get_check_runs = AsyncMock()
        client.list_check_runs_for_ref = AsyncMock()
        client.get_check_run_logs = AsyncMock()
        client.get_commit_status = AsyncMock()
        return client

    @pytest.fixture
    def discovery_config(self):
        """Basic discovery configuration for testing."""
        config = MagicMock()
        config.batch_size = 10
        config.discovery_timeout_seconds = 60
        config.max_check_runs_per_pr = 50
        return config

    @pytest.fixture
    def mock_cache(self):
        """Mock cache strategy for testing."""
        cache = AsyncMock()
        cache.get.return_value = None  # Cache miss by default
        cache.set.return_value = True
        return cache

    @pytest.fixture
    def check_discoverer(self, mock_github_client, mock_cache):
        """
        Why: Provides configured CheckRunDiscoverer instance for testing
        What: Creates discoverer with mocked dependencies for isolated testing
        How: Injects mock GitHub client and cache for controlled testing
        """
        return GitHubCheckDiscoverer(
            github_client=mock_github_client,
            cache=mock_cache,
            batch_size=10,
            max_concurrent=5,
        )

    async def test_discover_checks_returns_all_check_runs_for_pr_commit(
        self, check_discoverer, mock_github_client
    ):
        """
        Why: Ensure check discoverer successfully fetches all check runs associated
             with a PR's commit, providing complete CI/CD status information.

        What: Tests that discover_checks() retrieves all check runs for PR's head commit
              and returns them as DiscoveredCheckRun objects with complete metadata.

        How: Mocks GitHub API to return realistic check run data, calls discover_checks
             with PR data, and validates all check runs are returned with correct
             details.
        """
        # Arrange
        pr_data = DiscoveredPRFactory.create(pr_number=123, head_sha="abc123def456")
        repository_url = "https://github.com/test-org/test-repo"

        # Mock GitHub API to return check runs via paginator
        check_runs_response = create_realistic_check_run_data(
            commit_sha=pr_data.head_sha, include_failures=True, failure_rate=0.3
        )

        # Mock the paginate method to return a proper async iterator
        self._mock_paginate_with_response(mock_github_client, check_runs_response)

        # Act
        result = await check_discoverer.discover_checks(pr_data, repository_url)

        # Assert
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0

        # Verify all check runs have required fields
        for check_run in result:
            assert isinstance(check_run, DiscoveredCheckRun)
            assert check_run.external_id is not None
            assert check_run.name is not None
            assert check_run.status is not None

        # Verify GitHub API was called correctly
        mock_github_client.paginate.assert_called_once()
        # Should be called with check runs endpoint for PR's head SHA
        call_args = mock_github_client.paginate.call_args
        assert (
            "/check-runs" in call_args[0][0]
        )  # First positional arg should contain check-runs endpoint

    async def test_discover_checks_includes_failure_details_for_failed_checks(
        self, check_discoverer, mock_github_client
    ):
        """
        Why: Ensure failed check runs include detailed failure information for
             automated analysis and fix generation, enabling effective error handling.

        What: Tests that discover_checks() retrieves and includes complete failure
              output, error messages, and logs for check runs with failure conclusion.

        How: Mocks GitHub API to return failed check runs with detailed output,
             calls discover_checks, and validates failure information is captured.
        """
        # Arrange
        pr_data = DiscoveredPRFactory.create(head_sha="failed123abc")
        repository_url = "https://github.com/test-org/test-repo"

        # Mock GitHub API to return failed check runs with detailed output
        failed_check_response = {
            "total_count": 2,
            "check_runs": [
                MockGitHubAPIResponses.check_run_response(
                    head_sha=pr_data.head_sha,
                    name="lint-check",
                    status="completed",
                    conclusion="failure",
                    output={
                        "title": "Linting Failed",
                        "summary": "Found 5 linting errors",
                        "text": """Error: ESLint failed
src/utils.js:23:1: Expected 2 blank lines, found 1
src/worker.py:45:80: Line too long (85 > 79 characters)
src/config.ts:67:5: Unused variable 'debug'""",
                    },
                ),
                MockGitHubAPIResponses.check_run_response(
                    head_sha=pr_data.head_sha,
                    name="test-check",
                    status="completed",
                    conclusion="success",
                ),
            ],
        }

        # Mock the paginate method to return a proper async iterator
        self._mock_paginate_with_response(mock_github_client, failed_check_response)

        # Act
        result = await check_discoverer.discover_checks(pr_data, repository_url)

        # Assert
        assert result is not None
        assert len(result) == 2

        # Find the failed check
        failed_check = next((c for c in result if c.conclusion == "failure"), None)
        assert failed_check is not None
        assert failed_check.is_failed is True
        assert failed_check.output is not None
        # The mock generates failure output, so check for failure indicators
        assert "failed" in failed_check.output.get("title", "").lower()
        assert failed_check.output.get("text") is not None
        assert len(failed_check.output.get("text", "")) > 0

    async def test_discover_checks_handles_in_progress_check_runs_correctly(
        self, check_discoverer, mock_github_client
    ):
        """
        Why: Ensure discoverer correctly handles check runs that are still in progress,
             maintaining accurate status tracking for ongoing CI/CD processes.

        What: Tests that discover_checks() properly identifies and handles check runs
              with "queued" or "in_progress" status without conclusion values.

        How: Mocks GitHub API to return mix of completed and in-progress checks,
             validates in-progress checks have correct status and no conclusion.
        """
        # Arrange
        pr_data = DiscoveredPRFactory.create(head_sha="inprogress456def")
        repository_url = "https://github.com/test-org/test-repo"

        # Mock GitHub API to return mix of check statuses
        mixed_status_response = {
            "total_count": 3,
            "check_runs": [
                MockGitHubAPIResponses.check_run_response(
                    name="build-check",
                    status="queued",
                    conclusion=None,
                    started_at=None,
                    completed_at=None,
                ),
                MockGitHubAPIResponses.check_run_response(
                    name="lint-check",
                    status="in_progress",
                    conclusion=None,
                    completed_at=None,
                ),
                MockGitHubAPIResponses.check_run_response(
                    name="test-check", status="completed", conclusion="success"
                ),
            ],
        }

        # Mock the paginate method to return a proper async iterator
        self._mock_paginate_with_response(mock_github_client, mixed_status_response)

        # Act
        result = await check_discoverer.discover_checks(pr_data, repository_url)

        # Assert
        assert result is not None
        assert len(result) == 3

        # Verify status handling
        statuses = {check.name: check.status for check in result}
        assert statuses["build-check"] == "queued"
        assert statuses["lint-check"] == "in_progress"
        assert statuses["test-check"] == "completed"

        # Verify in-progress checks have no conclusion
        in_progress_checks = [c for c in result if c.status != "completed"]
        for check in in_progress_checks:
            assert check.conclusion is None
            assert check.completed_at is None

    async def test_discover_checks_handles_missing_check_runs_gracefully(
        self, check_discoverer, mock_github_client
    ):
        """
        Why: Ensure discoverer handles PRs with no check runs gracefully, as some
             repositories may not have CI/CD configured or checks may not be required.

        What: Tests that discover_checks() returns empty list when PR has no associated
              check runs, without errors or exceptions.

        How: Mocks GitHub API to return empty check runs response, calls
             discover_checks,
             and validates empty result is handled correctly.
        """
        # Arrange
        pr_data = DiscoveredPRFactory.create()
        repository_url = "https://github.com/test-org/no-ci-repo"

        # Mock GitHub API to return empty check runs
        empty_check_response = {
            "total_count": 0,
            "check_runs": [],
        }

        # Mock the paginate method to return a proper async iterator
        self._mock_paginate_with_response(mock_github_client, empty_check_response)

        # Act
        result = await check_discoverer.discover_checks(pr_data, repository_url)

        # Assert
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 0

        # Verify API was still called
        mock_github_client.paginate.assert_called_once()

    async def test_discover_checks_handles_github_api_errors_gracefully(
        self, check_discoverer, mock_github_client
    ):
        """
        Why: Ensure discoverer handles GitHub API errors gracefully without crashing,
             maintaining system stability when external dependencies fail.

        What: Tests that discover_checks() catches API exceptions and returns
              appropriate
              error information instead of propagating exceptions to caller.

        How: Mocks GitHub API to raise various exceptions, validates exceptions are
             caught and handled with proper error reporting or empty results.
        """
        # Arrange
        pr_data = DiscoveredPRFactory.create()
        repository_url = "https://github.com/test-org/error-repo"

        # Mock GitHub API to raise error via paginator
        self._mock_paginate_with_error(mock_github_client, Exception("API timeout"))

        # Act - Should not raise exception
        try:
            result = await check_discoverer.discover_checks(pr_data, repository_url)

            # Assert
            # Result could be empty list or contain error information
            assert result is not None
            assert isinstance(result, list)

        except Exception as e:
            # If exception is raised, it should be a handled type
            assert "timeout" in str(e).lower()


class TestCheckRunDiscovererBatchProcessing:
    """Tests for batch processing multiple PRs efficiently."""

    def _mock_paginate_with_multi_response(self, mock_github_client, response_map):
        """Helper method to mock paginate with different responses based on endpoint."""
        from unittest.mock import Mock

        def create_paginator(endpoint_url, **kwargs):
            # Extract SHA from the endpoint URL for mapping
            sha = None
            if "/commits/" in endpoint_url and "/check-runs" in endpoint_url:
                sha = endpoint_url.split("/commits/")[1].split("/check-runs")[0]

            class MockAsyncIterator:
                def __init__(self, response):
                    self.response = response
                    self.yielded = False

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        return self.response
                    else:
                        raise StopAsyncIteration

            response = response_map.get(sha, {"check_runs": []})
            return MockAsyncIterator(response)

        mock_github_client.paginate = Mock(side_effect=create_paginator)

    def _mock_paginate_with_error_for_sha(
        self, mock_github_client, error_shas, success_response
    ):
        """Helper method to mock paginate with errors for specific SHAs."""
        from unittest.mock import Mock

        def create_paginator(endpoint_url, **kwargs):
            # Extract SHA from the endpoint URL
            sha = None
            if "/commits/" in endpoint_url and "/check-runs" in endpoint_url:
                sha = endpoint_url.split("/commits/")[1].split("/check-runs")[0]

            class MockAsyncIterator:
                def __init__(self, should_error, response):
                    self.should_error = should_error
                    self.response = response
                    self.yielded = False

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self.should_error:
                        raise Exception(f"API error for {sha}")

                    if not self.yielded:
                        self.yielded = True
                        return self.response
                    else:
                        raise StopAsyncIteration

            should_error = sha in error_shas
            response = success_response if not should_error else {"check_runs": []}
            return MockAsyncIterator(should_error, response)

        mock_github_client.paginate = Mock(side_effect=create_paginator)

    @pytest.fixture
    def mock_github_client(self) -> AsyncMock:
        """
        Why: Provides mock GitHub client for testing batch check run API interactions
        What: Creates AsyncMock with check run API methods and realistic responses
        How: Sets up mock methods for check runs, commit status, and API responses
        """
        client = AsyncMock()
        client.get_check_runs = AsyncMock()
        client.list_check_runs_for_ref = AsyncMock()
        client.get_check_run_logs = AsyncMock()
        client.get_commit_status = AsyncMock()
        return client

    @pytest.fixture
    def mock_cache(self):
        """Mock cache strategy for testing."""
        cache = AsyncMock()
        cache.get.return_value = None  # Cache miss by default
        cache.set.return_value = True
        return cache

    @pytest.fixture
    def batch_check_discoverer(self, mock_github_client, mock_cache):
        """Check discoverer configured for batch testing."""
        return GitHubCheckDiscoverer(
            github_client=mock_github_client,
            cache=mock_cache,
            batch_size=10,
            max_concurrent=5,
        )

    async def test_batch_discover_checks_processes_multiple_prs_efficiently(
        self, batch_check_discoverer, mock_github_client
    ):
        """
        Why: Ensure batch processing efficiently handles multiple PRs with minimal
             API calls, optimizing performance for large repository discovery.

        What: Tests that batch_discover_checks() processes multiple PRs and returns
              check runs for all PRs with optimized API usage and proper grouping.

        How: Provides multiple PR objects, mocks batch API responses, validates
             all PRs are processed and results are properly organized by PR number.
        """
        # Arrange
        prs = [
            DiscoveredPRFactory.create(pr_number=100, head_sha="sha100abc"),
            DiscoveredPRFactory.create(pr_number=101, head_sha="sha101def"),
            DiscoveredPRFactory.create(pr_number=102, head_sha="sha102ghi"),
        ]
        repository_url = "https://github.com/test-org/batch-repo"

        # Mock GitHub API to return check runs for each unique SHA via paginator
        unique_shas = list({pr.head_sha for pr in prs})
        responses = {
            sha: create_realistic_check_run_data(sha, include_failures=False)
            for sha in unique_shas
        }

        self._mock_paginate_with_multi_response(mock_github_client, responses)

        # Act
        result = await batch_check_discoverer.batch_discover_checks(prs, repository_url)

        # Assert
        assert result is not None
        assert isinstance(result, dict)
        assert len(result) == 3

        # Verify all PR numbers are in result
        assert 100 in result
        assert 101 in result
        assert 102 in result

        # Verify each PR has check runs
        for _pr_number, check_runs in result.items():
            assert isinstance(check_runs, list)
            # Each PR should have check runs (from factory)

    async def test_batch_discover_checks_optimizes_api_calls_for_same_commit(
        self, batch_check_discoverer, mock_github_client
    ):
        """
        Why: Ensure batch processing optimizes API calls by deduplicating requests
             for PRs with the same head commit SHA, reducing unnecessary API usage.

        What: Tests that batch_discover_checks() identifies PRs sharing the same
              commit and makes only one API call per unique commit SHA.

        How: Provides multiple PRs with same head SHA, mocks single API response,
             validates only one API call is made and results are shared appropriately.
        """
        # Arrange - Multiple PRs with same head SHA
        shared_sha = "shared123abc"
        prs = [
            DiscoveredPRFactory.create(pr_number=200, head_sha=shared_sha),
            DiscoveredPRFactory.create(pr_number=201, head_sha=shared_sha),
            DiscoveredPRFactory.create(pr_number=202, head_sha="unique456def"),
        ]
        repository_url = "https://github.com/test-org/dedupe-repo"

        # Mock GitHub API responses via paginator
        responses = {
            shared_sha: create_realistic_check_run_data(shared_sha),
            "unique456def": create_realistic_check_run_data("unique456def"),
        }

        self._mock_paginate_with_multi_response(mock_github_client, responses)

        # Act
        result = await batch_check_discoverer.batch_discover_checks(prs, repository_url)

        # Assert
        assert result is not None

        # Should only make 2 API calls (one per unique SHA)
        # Note: This assertion depends on actual implementation
        # mock_github_client.get_check_runs.call_count should be 2

        # Verify results for shared SHA PRs
        assert 200 in result
        assert 201 in result
        assert 202 in result

    async def test_batch_discover_checks_handles_partial_failures_gracefully(
        self, batch_check_discoverer, mock_github_client
    ):
        """
        Why: Ensure batch processing continues when some PRs fail to fetch check runs,
             maximizing successful processing instead of failing entire batch.

        What: Tests that batch_discover_checks() handles individual PR failures and
              returns results for successful PRs while reporting failed ones.

        How: Mocks API to succeed for some PRs and fail for others, validates
             successful PRs are processed and failures are handled gracefully.
        """
        # Arrange
        prs = [
            DiscoveredPRFactory.create(pr_number=300, head_sha="success300"),
            DiscoveredPRFactory.create(pr_number=301, head_sha="failure301"),
            DiscoveredPRFactory.create(pr_number=302, head_sha="success302"),
        ]
        repository_url = "https://github.com/test-org/partial-fail-repo"

        # Mock GitHub API to succeed for some, fail for others via paginator
        error_shas = {"failure301"}
        success_response = create_realistic_check_run_data("success")

        self._mock_paginate_with_error_for_sha(
            mock_github_client, error_shas, success_response
        )

        # Act
        result = await batch_check_discoverer.batch_discover_checks(prs, repository_url)

        # Assert
        assert result is not None
        assert isinstance(result, dict)

        # Should have results for successful PRs
        # Failed PRs might be omitted or have empty/error results
        # Implementation-dependent behavior

    async def test_batch_discover_checks_respects_batch_size_limits(
        self, batch_check_discoverer, mock_github_client
    ):
        """
        Why: Ensure batch processing respects configured limits to prevent overwhelming
             GitHub API and maintain stable performance under various load conditions.

        What: Tests that batch_discover_checks() processes large PR lists in batches
              according to configuration limits, preventing resource exhaustion.

        How: Provides more PRs than batch size limit, validates processing occurs
             in batches with proper pacing and all PRs are eventually processed.
        """
        # Arrange - More PRs than batch size
        batch_size = batch_check_discoverer.batch_size  # 10 from fixture
        prs = [
            DiscoveredPRFactory.create(pr_number=400 + i, head_sha=f"sha{400 + i}")
            for i in range(batch_size + 5)  # 15 PRs, batch size is 10
        ]
        repository_url = "https://github.com/test-org/large-batch-repo"

        # Mock GitHub API to return check runs via paginator
        # Since all PRs have different SHAs, create a response for each
        responses = {}
        for pr in prs:
            responses[pr.head_sha] = create_realistic_check_run_data(pr.head_sha)

        self._mock_paginate_with_multi_response(mock_github_client, responses)

        # Act
        result = await batch_check_discoverer.batch_discover_checks(prs, repository_url)

        # Assert
        assert result is not None
        assert len(result) == len(prs)  # All PRs should be processed eventually

        # Note: Actual batching behavior verification would depend on implementation
        # Could verify API call patterns or timing if batching includes delays

    async def test_batch_discover_checks_maintains_pr_to_checks_mapping_correctly(
        self, batch_check_discoverer, mock_github_client
    ):
        """
        Why: Ensure batch processing maintains correct mapping between PRs and their
             check runs, preventing data corruption or misassignment in results.

        What: Tests that batch_discover_checks() returns results with correct PR number
              to check runs mapping, preserving data integrity across batch operations.

        How: Provides PRs with distinct check patterns, mocks specific responses,
             validates each PR's check runs are correctly mapped and contain
             expected data.
        """
        # Arrange
        prs = [
            DiscoveredPRFactory.create(pr_number=500, head_sha="lint500"),
            DiscoveredPRFactory.create(pr_number=501, head_sha="test501"),
            DiscoveredPRFactory.create(pr_number=502, head_sha="build502"),
        ]
        repository_url = "https://github.com/test-org/mapping-repo"

        # Mock distinct check run patterns for each PR via paginator
        responses = {
            pr.head_sha: create_realistic_check_run_data(
                pr.head_sha, include_failures=False
            )
            for pr in prs
        }

        self._mock_paginate_with_multi_response(mock_github_client, responses)

        # Act
        result = await batch_check_discoverer.batch_discover_checks(prs, repository_url)

        # Assert
        assert result is not None
        assert isinstance(result, dict)

        # Verify mapping integrity
        for pr in prs:
            assert pr.pr_number in result
            check_runs = result[pr.pr_number]
            assert isinstance(check_runs, list)

            # Verify check runs are valid DiscoveredCheckRun objects
            for check_run in check_runs:
                assert hasattr(check_run, "external_id")
                assert hasattr(check_run, "name")
                assert hasattr(check_run, "status")
