"""Unit tests for Repository Scanner component.

Tests PR discovery functionality including GitHub API integration,
pagination handling, ETag caching, and error recovery scenarios.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.workers.discovery.interfaces import (
    DiscoveryPriority,
    PRDiscoveryResult,
)
from src.workers.discovery.repository_scanner import GitHubRepositoryScanner
from tests.fixtures.discovery.factories import (
    DiscoveryConfigFactory,
    PRDiscoveryResultFactory,
)
from tests.fixtures.discovery.mock_data import MockGitHubAPIResponses


class TestRepositoryScannerDiscovery:
    """Tests for repository PR discovery functionality."""

    @pytest.fixture
    def mock_github_client(self) -> AsyncMock:
        """
        Why: Provides mock GitHub client for testing API interactions without
             external calls
        What: Creates AsyncMock with realistic GitHub API response methods
        How: Sets up mock methods for pull requests, pagination, and rate limiting
        """
        client = AsyncMock()

        # Create a proper async iterator class
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        # Default mock paginate behavior
        def default_paginate(*args, **kwargs):
            # Paginator yields individual PRs, not pages of PRs
            pr_data = [
                MockGitHubAPIResponses.pull_request_response(number=1),
                MockGitHubAPIResponses.pull_request_response(number=2),
                MockGitHubAPIResponses.pull_request_response(number=3),
            ]
            return MockAsyncIterator(pr_data)

        client.paginate = Mock(side_effect=default_paginate)
        return client

    @pytest.fixture
    def mock_repository_repo(self) -> AsyncMock:
        """
        Why: Provides mock repository repository for database operations without
             DB dependency
        What: Creates AsyncMock with repository lookup and state management methods
        How: Sets up mock methods for repository data access with realistic
              responses
        """
        repo = AsyncMock()

        # Mock repository object
        mock_repository = Mock()
        mock_repository.get_config_value = Mock(return_value=None)
        mock_repository.failure_count = 0
        mock_repository.last_polled_at = datetime.utcnow() - timedelta(minutes=30)
        mock_repository.polling_interval_minutes = 15
        mock_repository.url = "https://github.com/test-org/test-repo"

        repo.get_by_id = AsyncMock(return_value=mock_repository)
        return repo

    @pytest.fixture
    def mock_cache_strategy(self) -> AsyncMock:
        """
        Why: Provides mock caching for testing cache behavior without Redis dependency
        What: Creates AsyncMock with cache get/set operations and ETag support
        How: Sets up mock methods for cache operations with realistic response times
        """
        cache = AsyncMock()
        cache.get = AsyncMock()
        cache.set = AsyncMock()
        cache.get_with_etag = AsyncMock(
            return_value=(None, None)
        )  # Cache miss by default
        cache.set_with_etag = AsyncMock()
        cache.invalidate = AsyncMock()
        return cache

    @pytest.fixture
    def repository_scanner(
        self,
        mock_github_client,
        mock_repository_repo,
        mock_cache_strategy,
    ):
        """
        Why: Provides configured GitHubRepositoryScanner instance for testing
        What: Creates scanner with mocked dependencies for isolated testing
        How: Injects mock dependencies to test scanner logic without external calls
        """
        return GitHubRepositoryScanner(
            github_client=mock_github_client,
            repository_repo=mock_repository_repo,
            cache=mock_cache_strategy,
            max_pages=10,
            items_per_page=100,
        )

    async def test_discover_prs_returns_complete_result_for_valid_repository(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure repository scanner successfully discovers PRs and returns complete
             result data for valid repositories, providing confidence in basic
             functionality.

        What: Tests that discover_prs() successfully fetches PR data from GitHub API
              and returns PRDiscoveryResult with discovered PRs and metadata.

        How: Mocks GitHub API to return realistic PR data, calls discover_prs,
             and validates the returned result contains expected PR data and metrics.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"

        # Mock GitHub API paginate method
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_data(*args, **kwargs):
            # Paginator yields individual PRs, not pages of PRs
            pr_data = [
                MockGitHubAPIResponses.pull_request_response(number=1),
                MockGitHubAPIResponses.pull_request_response(number=2),
                MockGitHubAPIResponses.pull_request_response(number=3),
            ]
            return MockAsyncIterator(pr_data)

        mock_github_client.paginate.side_effect = mock_paginate_data

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert
        assert result is not None
        assert result.repository_id == repository_id
        assert result.repository_url == repository_url
        assert len(result.discovered_prs) == 3
        assert result.discovery_timestamp is not None
        assert result.api_calls_used >= 0
        assert result.processing_time_ms >= 0.0

        # Verify GitHub client paginate was called correctly
        mock_github_client.paginate.assert_called_once_with(
            "/repos/test-org/test-repo/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
            },
            per_page=100,
            max_pages=10,
        )

    async def test_discover_prs_respects_since_parameter_for_incremental_updates(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure incremental PR discovery works correctly by filtering PRs based on
             last update time, enabling efficient polling without processing
             unchanged data.

        What: Tests that discover_prs() with since parameter passes the filter
              to GitHub API
              for efficient server-side filtering of PRs.

        How: Mocks GitHub API paginate method, calls discover_prs with since parameter,
             and validates the since parameter was passed to GitHub API correctly.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"
        since_time = datetime.utcnow() - timedelta(hours=2)

        # Mock GitHub API paginate method
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_data(*args, **kwargs):
            # Return PRs that would be filtered by GitHub API
            recent_pr = MockGitHubAPIResponses.pull_request_response(
                number=123,
                updated_at=(datetime.utcnow() - timedelta(minutes=30)).isoformat()
                + "Z",
            )
            return MockAsyncIterator([recent_pr])

        mock_github_client.paginate.side_effect = mock_paginate_data

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url, since=since_time
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 1

        # Verify the since parameter was passed to GitHub API
        expected_params = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
            "since": since_time.isoformat(),
        }

        mock_github_client.paginate.assert_called_once_with(
            "/repos/test-org/test-repo/pulls",
            params=expected_params,
            per_page=100,
            max_pages=10,
        )

    async def test_discover_prs_handles_pagination_correctly_for_large_repositories(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure repository scanner can handle large repositories with
             hundreds of PRs
             by properly implementing pagination, preventing memory issues and timeouts.

        What: Tests that discover_prs() correctly handles GitHub API pagination to fetch
              all PRs from repositories with more PRs than fit in a single API response.

        How: Mocks GitHub API to return paginated responses, calls discover_prs,
             and validates all pages are fetched and combined into complete result.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/large-repo"

        # Mock paginated responses
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_multiple_pages(*args, **kwargs):
            # Paginator yields individual PRs from both pages
            page1_data = [
                MockGitHubAPIResponses.pull_request_response(number=i)
                for i in range(1, 4)
            ]

            page2_data = [
                MockGitHubAPIResponses.pull_request_response(number=i)
                for i in range(4, 6)
            ]
            # Flatten pages into individual PR items
            all_prs = page1_data + page2_data
            return MockAsyncIterator(all_prs, pages_count=2)  # 2 pages

        mock_github_client.paginate.side_effect = mock_paginate_multiple_pages

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id,
            repository_url=repository_url,
            max_prs=100,  # Request more than available
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 5  # Total from both pages
        assert result.api_calls_used == 2  # Two pages fetched
        assert result.processing_time_ms > 0

        # Verify paginate was called correctly
        mock_github_client.paginate.assert_called_once_with(
            "/repos/test-org/large-repo/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
            },
            per_page=100,
            max_pages=10,
        )

    async def test_discover_prs_uses_etag_caching_to_minimize_api_calls(
        self, repository_scanner, mock_github_client, mock_cache_strategy
    ):
        """
        Why: Ensure efficient API usage by implementing ETag-based conditional requests,
             reducing unnecessary API calls when repository data hasn't changed.

        What: Tests that discover_prs() attempts to use cached ETag data and checks
              cache for existing data before making API calls.

        How: Mocks cache to return no cached data, verifies cache methods are called
             and new data is cached after successful API call.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"

        # Mock cache to return no cached data (cache miss)
        mock_cache_strategy.get_with_etag.return_value = (None, None)

        # Mock GitHub API to return fresh data
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_data(*args, **kwargs):
            page_data = [
                MockGitHubAPIResponses.pull_request_response(number=1),
                MockGitHubAPIResponses.pull_request_response(number=2),
            ]
            return MockAsyncIterator(page_data)

        mock_github_client.paginate.side_effect = mock_paginate_data

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 2
        assert result.cache_misses == 1  # Should have cache miss
        assert result.api_calls_used == 1  # One API call made

        # Verify cache was checked for ETag
        mock_cache_strategy.get_with_etag.assert_called_once_with(
            "prs:test-org:test-repo:all"
        )

        # Verify new data was cached
        mock_cache_strategy.set_with_etag.assert_called_once()

    async def test_discover_prs_handles_github_rate_limit_errors(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure repository scanner gracefully handles GitHub API rate limit errors
             and records appropriate error information for monitoring and retry logic.

        What: Tests that discover_prs() catches GitHubRateLimitError and includes
              rate limit information in the discovery result errors.

        How: Mocks GitHub API paginate to raise rate limit error, verifies error
             is caught and included in result with proper metadata.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"

        from src.github.exceptions import GitHubRateLimitError

        # Mock GitHub API to raise rate limit error
        reset_timestamp = int((datetime.utcnow() + timedelta(minutes=60)).timestamp())
        rate_limit_error = GitHubRateLimitError(
            message="API rate limit exceeded", reset_time=reset_timestamp, remaining=0
        )

        def mock_paginate_rate_limit(*args, **kwargs):
            raise rate_limit_error

        mock_github_client.paginate.side_effect = mock_paginate_rate_limit

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 0  # No PRs discovered due to error
        assert len(result.errors) == 1

        error = result.errors[0]
        assert error.error_type == "rate_limit_exceeded"
        assert "rate limit exceeded" in error.message.lower()
        assert error.recoverable is True
        assert "reset_time" in error.context

    async def test_discover_prs_handles_github_api_errors_gracefully(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure repository scanner handles GitHub API errors gracefully without
             crashing, providing useful error information for debugging and recovery.

        What: Tests that discover_prs() catches and handles various GitHub API errors
              including network failures, authentication errors, and server errors.

        How: Mocks GitHub API to raise different exception types, verifies errors
             are caught and included in discovery result for proper error reporting.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"

        from src.github.exceptions import GitHubError

        # Mock GitHub API to raise general GitHub error
        def mock_paginate_error(*args, **kwargs):
            raise GitHubError("GitHub API temporarily unavailable", status_code=503)

        mock_github_client.paginate.side_effect = mock_paginate_error

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 0  # No PRs due to error
        assert len(result.errors) == 1

        # Verify error details
        error = result.errors[0]
        assert error.error_type == "github_api_error"
        assert "github api error" in error.message.lower()
        assert error.recoverable is True
        assert error.context["status_code"] == 503

    async def test_discover_prs_respects_max_prs_limit_for_large_repositories(
        self, repository_scanner, mock_github_client
    ):
        """
        Why: Ensure repository scanner respects max_prs parameter to prevent processing
             excessive amounts of data from very large repositories, controlling
             resource usage.

        What: Tests that discover_prs() with max_prs parameter stops fetching additional
              PRs once the limit is reached, even if more pages are available.

        How: Mocks GitHub API to return more PRs than the limit, calls discover_prs
             with max_prs, and validates the result contains at most the
             specified number.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/huge-repo"
        max_prs = 2  # Set low limit for testing

        # Mock GitHub API to return more PRs than limit across multiple pages
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_many_prs(*args, **kwargs):
            # Page 1: 3 PRs (more than limit)
            page1_data = [
                MockGitHubAPIResponses.pull_request_response(number=i)
                for i in range(1, 4)
            ]

            # Page 2: More PRs that shouldn't be processed due to limit
            page2_data = [
                MockGitHubAPIResponses.pull_request_response(number=i)
                for i in range(4, 7)
            ]
            # Flatten pages into individual PR items
            all_prs = page1_data + page2_data
            return MockAsyncIterator(all_prs)

        mock_github_client.paginate.side_effect = mock_paginate_many_prs

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url, max_prs=max_prs
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == max_prs  # Should respect limit

        # Verify paginate was called
        mock_github_client.paginate.assert_called_once()

    async def test_discover_prs_includes_comprehensive_metrics_in_result(
        self, repository_scanner, mock_github_client, mock_cache_strategy
    ):
        """
        Why: Ensure discovery results include comprehensive metrics for monitoring,
             debugging, and performance optimization of the discovery process.

        What: Tests that discover_prs() returns result with accurate metrics including
              API calls used, cache hit rates, processing time, and error counts.

        How: Mocks dependencies to simulate various scenarios, calls discover_prs,
             and validates all metric fields are populated with realistic values.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/test-repo"

        # Mock cache to return no cached data (cache miss)
        mock_cache_strategy.get_with_etag.return_value = (None, None)

        # Mock GitHub API
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_data(*args, **kwargs):
            page_data = [
                MockGitHubAPIResponses.pull_request_response(number=i)
                for i in range(1, 4)
            ]
            return MockAsyncIterator(page_data)

        mock_github_client.paginate.side_effect = mock_paginate_data

        # Act
        result = await repository_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert comprehensive metrics
        assert result is not None
        assert isinstance(result.api_calls_used, int)
        assert result.api_calls_used == 1  # One page fetched
        assert isinstance(result.cache_hits, int)
        assert result.cache_hits == 0  # Cache miss scenario
        assert isinstance(result.cache_misses, int)
        assert result.cache_misses == 1  # One cache miss
        assert isinstance(result.processing_time_ms, float)
        assert result.processing_time_ms >= 0.0
        assert isinstance(result.errors, list)
        assert len(result.errors) == 0  # No errors in successful scenario
        assert len(result.discovered_prs) == 3  # Three PRs discovered

        # Verify discovery timestamp is recent
        time_diff = datetime.utcnow() - result.discovery_timestamp
        assert time_diff.total_seconds() < 60  # Within last minute


class TestRepositoryScannerPriority:
    """Tests for repository priority determination logic."""

    @pytest.fixture
    def mock_github_client(self) -> AsyncMock:
        """Mock GitHub client for priority tests."""
        return AsyncMock()

    @pytest.fixture
    def mock_cache_strategy(self) -> AsyncMock:
        """Mock cache strategy for priority tests."""
        cache = AsyncMock()
        cache.get_with_etag = AsyncMock(return_value=(None, None))
        cache.set_with_etag = AsyncMock()
        return cache

    @pytest.fixture
    def mock_repository_repo_priority(self) -> AsyncMock:
        """Mock repository repo with different priority scenarios."""
        return AsyncMock()

    @pytest.fixture
    def repository_scanner_with_priority(
        self,
        mock_github_client,
        mock_repository_repo_priority,
        mock_cache_strategy,
    ):
        """Repository scanner configured for priority testing."""
        return GitHubRepositoryScanner(
            github_client=mock_github_client,
            repository_repo=mock_repository_repo_priority,
            cache=mock_cache_strategy,
        )

    async def test_get_priority_returns_critical_for_repositories_with_many_failures(
        self, repository_scanner_with_priority, mock_repository_repo_priority
    ):
        """
        Why: Ensure repositories with recent failures get highest priority for timely
             resolution of issues, preventing accumulation of problems.

        What: Tests that get_priority() returns CRITICAL priority for repositories
              with high failure counts indicating urgent attention needed.

        How: Mocks repository with high failure count, calls get_priority,
             and validates CRITICAL priority is returned.
        """
        # Arrange
        repository_id = uuid.uuid4()

        mock_repository = Mock()
        mock_repository.get_config_value = Mock(return_value=None)  # No manual override
        mock_repository.failure_count = 5  # High failure count
        mock_repository.last_polled_at = datetime.utcnow() - timedelta(minutes=30)
        mock_repository.polling_interval_minutes = 15

        mock_repository_repo_priority.get_by_id = AsyncMock(
            return_value=mock_repository
        )

        # Act
        priority = await repository_scanner_with_priority.get_priority(repository_id)

        # Assert
        assert priority == DiscoveryPriority.CRITICAL

    async def test_get_priority_returns_high_for_repositories_not_polled_recently(
        self, repository_scanner_with_priority, mock_repository_repo_priority
    ):
        """
        Why: Ensure repositories that haven't been polled recently get higher priority
             to maintain up-to-date monitoring coverage across all repositories.

        What: Tests that get_priority() returns HIGH priority for repositories
              that haven't been polled in over an hour.

        How: Mocks repository with old last_polled_at, calls get_priority,
             and validates HIGH priority is returned.
        """
        # Arrange
        repository_id = uuid.uuid4()

        mock_repository = Mock()
        mock_repository.get_config_value = Mock(return_value=None)
        mock_repository.failure_count = 0  # No failures
        mock_repository.last_polled_at = datetime.utcnow() - timedelta(hours=2)  # Old
        mock_repository.polling_interval_minutes = 15

        mock_repository_repo_priority.get_by_id = AsyncMock(
            return_value=mock_repository
        )

        # Act
        priority = await repository_scanner_with_priority.get_priority(repository_id)

        # Assert
        assert priority == DiscoveryPriority.HIGH

    async def test_get_priority_returns_low_for_inactive_repositories(
        self, repository_scanner_with_priority, mock_repository_repo_priority
    ):
        """
        Why: Ensure inactive repositories get low priority to focus resources on
             active development while still maintaining basic monitoring coverage.

        What: Tests that get_priority() returns LOW priority for repositories
              with long polling intervals indicating low activity.

        How: Mocks repository with long polling interval, calls get_priority,
             and validates LOW priority is returned.
        """
        # Arrange
        repository_id = uuid.uuid4()

        mock_repository = Mock()
        mock_repository.get_config_value = Mock(return_value=None)
        mock_repository.failure_count = 0  # No failures
        mock_repository.last_polled_at = datetime.utcnow() - timedelta(
            minutes=10
        )  # Recent
        mock_repository.polling_interval_minutes = 120  # Long interval (inactive)

        mock_repository_repo_priority.get_by_id = AsyncMock(
            return_value=mock_repository
        )

        # Act
        priority = await repository_scanner_with_priority.get_priority(repository_id)

        # Assert
        assert priority == DiscoveryPriority.LOW


class TestRepositoryScannerEdgeCases:
    """Tests for edge cases and error scenarios in repository scanning."""

    @pytest.fixture
    def mock_github_client(self) -> AsyncMock:
        """Mock GitHub client for edge case tests."""
        client = AsyncMock()

        # Create a proper async iterator class
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        # Default mock paginate behavior
        def default_paginate(*args, **kwargs):
            page_data = [
                MockGitHubAPIResponses.pull_request_response(number=1),
                MockGitHubAPIResponses.pull_request_response(number=2),
            ]
            return MockAsyncIterator(page_data)

        client.paginate = Mock(side_effect=default_paginate)
        return client

    @pytest.fixture
    def mock_repository_repo(self) -> AsyncMock:
        """Mock repository repo for edge case tests."""
        repo = AsyncMock()
        mock_repository = Mock()
        mock_repository.get_config_value = Mock(return_value=None)
        mock_repository.failure_count = 0
        mock_repository.last_polled_at = datetime.utcnow() - timedelta(minutes=30)
        mock_repository.polling_interval_minutes = 15
        mock_repository.url = "https://github.com/test-org/test-repo"
        repo.get_by_id = AsyncMock(return_value=mock_repository)
        return repo

    @pytest.fixture
    def mock_cache_strategy(self) -> AsyncMock:
        """Mock cache strategy for edge case tests."""
        cache = AsyncMock()
        cache.get_with_etag = AsyncMock(return_value=(None, None))
        cache.set_with_etag = AsyncMock()
        return cache

    @pytest.fixture
    def edge_case_scanner(
        self,
        mock_github_client,
        mock_repository_repo,
        mock_cache_strategy,
    ):
        """Scanner configured for edge case testing."""
        return GitHubRepositoryScanner(
            github_client=mock_github_client,
            repository_repo=mock_repository_repo,
            cache=mock_cache_strategy,
        )

    async def test_discover_prs_handles_empty_repository_gracefully(
        self, edge_case_scanner, mock_github_client
    ):
        """
        Why: Ensure scanner handles repositories with no PRs gracefully without errors,
             as empty repositories are valid and should not cause system failures.

        What: Tests that discover_prs() returns valid empty result when repository
              has no pull requests, handling the empty state correctly.

        How: Mocks GitHub API to return empty PR list, calls discover_prs,
             and validates empty result is returned with proper metrics.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/empty-repo"

        # Mock GitHub API to return empty PR list
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_empty(*args, **kwargs):
            return MockAsyncIterator([])  # Empty page

        mock_github_client.paginate.side_effect = mock_paginate_empty

        # Act
        result = await edge_case_scanner.discover_prs(
            repository_id=repository_id, repository_url=repository_url
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 0
        assert result.api_calls_used == 1  # Still made API call
        assert len(result.errors) == 0  # No errors for empty repo

    async def test_discover_prs_handles_invalid_repository_url_gracefully(
        self, edge_case_scanner, mock_github_client
    ):
        """
        Why: Ensure scanner handles malformed repository URLs gracefully with proper
             error reporting, preventing system crashes from invalid configuration.

        What: Tests that discover_prs() with invalid repository URL returns error
              result without crashing, providing useful error information.

        How: Provides malformed repository URL, calls discover_prs, validates
             error is caught and reported in the result.
        """
        # Arrange
        repository_id = uuid.uuid4()
        invalid_url = "not-a-valid-url"  # Invalid URL format

        # Act
        result = await edge_case_scanner.discover_prs(
            repository_id=repository_id, repository_url=invalid_url
        )

        # Assert
        assert result is not None
        assert len(result.discovered_prs) == 0  # No PRs due to error
        assert len(result.errors) == 1

        error = result.errors[0]
        assert error.error_type == "invalid_repository_url"
        assert "invalid" in error.message.lower() or "url" in error.message.lower()
        assert error.recoverable is False  # URL format errors aren't recoverable

    async def test_discover_prs_handles_concurrent_repository_access_safely(
        self, edge_case_scanner, mock_github_client
    ):
        """
        Why: Ensure scanner can handle concurrent access to the same repository safely
             without race conditions or data corruption, supporting parallel processing.

        What: Tests that multiple concurrent calls to discover_prs() for the same
              repository complete successfully without interfering with each other.

        How: Makes multiple concurrent discover_prs calls, validates all complete
             successfully and return consistent results without conflicts.
        """
        # Arrange
        repository_id = uuid.uuid4()
        repository_url = "https://github.com/test-org/concurrent-repo"

        # Mock GitHub API to return consistent data
        class MockAsyncIterator:
            def __init__(self, data, pages_count=1):
                self.data = data
                self.index = 0
                self._current_page = pages_count  # Simulate page tracking

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.data):
                    raise StopAsyncIteration
                result = self.data[self.index]
                self.index += 1
                return result

        def mock_paginate_concurrent(*args, **kwargs):
            page_data = [
                MockGitHubAPIResponses.pull_request_response(number=1),
                MockGitHubAPIResponses.pull_request_response(number=2),
            ]
            return MockAsyncIterator(page_data)

        mock_github_client.paginate.side_effect = mock_paginate_concurrent

        # Act - Make concurrent calls
        import asyncio

        tasks = [
            edge_case_scanner.discover_prs(repository_id, repository_url)
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks)

        # Assert
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert result.repository_id == repository_id
            assert len(result.discovered_prs) == 2  # Should get same data
            # All should complete successfully (no errors expected)
            assert len(result.errors) == 0
