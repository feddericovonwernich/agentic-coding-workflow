"""Unit tests for PR Discovery Engine."""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.cache_manager import CacheManager
from src.github.client import GitHubClient
from src.github.exceptions import GitHubNotFoundError, GitHubRateLimitError
from src.models.enums import CheckConclusion, CheckStatus, PRState
from src.workers.monitor.discovery import (
    CheckRunDiscoveryEngine,
    DiscoveryConfig,
    PRDiscoveryEngine,
    RepositoryContext,
)
from src.workers.monitor.models import (
    ChangeType,
    CheckRunDiscovery,
    DiscoveryResult,
    StateChangeEvent,
)


class MockAsyncIterator:
    """Mock async iterator for testing paginators."""
    
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


class TestDiscoveryConfig:
    """Test configuration validation and defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DiscoveryConfig()
        
        assert config.per_page == 100
        assert config.max_pages is None
        assert config.max_concurrent_repos == 5
        assert config.cache_ttl == 300
        assert config.cache_pr_details_ttl == 900
        assert config.use_etag_caching is True
        assert config.batch_size == 20
        assert config.request_delay == 0.1
        assert config.max_retries == 3
        assert config.default_state_filter == PRState.OPENED
        assert config.include_drafts is False
        assert config.max_age_days == 30

    def test_config_validation_per_page(self):
        """Test per_page validation."""
        # Valid range
        config = DiscoveryConfig(per_page=50)
        config.validate()  # Should not raise

        # Invalid - too small
        with pytest.raises(ValueError, match="per_page must be between 1 and 100"):
            DiscoveryConfig(per_page=0).validate()

        # Invalid - too large
        with pytest.raises(ValueError, match="per_page must be between 1 and 100"):
            DiscoveryConfig(per_page=101).validate()

    def test_config_validation_concurrent_repos(self):
        """Test max_concurrent_repos validation."""
        # Valid
        config = DiscoveryConfig(max_concurrent_repos=10)
        config.validate()

        # Invalid
        with pytest.raises(ValueError, match="max_concurrent_repos must be positive"):
            DiscoveryConfig(max_concurrent_repos=0).validate()

    def test_config_validation_cache_ttl(self):
        """Test cache_ttl validation."""
        # Valid
        config = DiscoveryConfig(cache_ttl=600)
        config.validate()

        # Invalid
        with pytest.raises(ValueError, match="cache_ttl cannot be negative"):
            DiscoveryConfig(cache_ttl=-1).validate()


class TestRepositoryContext:
    """Test repository context model."""

    def test_creation(self):
        """Test repository context creation."""
        repo_id = uuid.uuid4()
        context = RepositoryContext(
            repository_id=repo_id,
            repository_owner="octocat",
            repository_name="Hello-World"
        )
        
        assert context.repository_id == repo_id
        assert context.repository_owner == "octocat"
        assert context.repository_name == "Hello-World"
        assert context.last_updated is None
        assert context.etag is None
        assert context.processing_priority == 1

    def test_with_optional_fields(self):
        """Test repository context with optional fields."""
        repo_id = uuid.uuid4()
        last_updated = datetime.now()
        
        context = RepositoryContext(
            repository_id=repo_id,
            repository_owner="octocat",
            repository_name="Hello-World",
            last_updated=last_updated,
            etag="abc123",
            processing_priority=5
        )
        
        assert context.last_updated == last_updated
        assert context.etag == "abc123"
        assert context.processing_priority == 5


class TestPRDiscoveryEngine:
    """Test PR Discovery Engine functionality."""

    @pytest.fixture
    def mock_github_client(self):
        """Create mock GitHub client."""
        return AsyncMock(spec=GitHubClient)

    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        mock = AsyncMock(spec=CacheManager)
        mock.get.return_value = None  # Default to cache miss
        return mock

    @pytest.fixture
    def discovery_config(self):
        """Create test discovery configuration."""
        return DiscoveryConfig(
            per_page=50,
            max_concurrent_repos=2,
            cache_ttl=60,
            batch_size=10,
            request_delay=0,  # No delay in tests
            max_age_days=0,  # Disable age filtering in tests
        )

    @pytest.fixture
    def discovery_engine(self, mock_github_client, mock_cache_manager, discovery_config):
        """Create discovery engine with mocks."""
        return PRDiscoveryEngine(
            github_client=mock_github_client,
            cache_manager=mock_cache_manager,
            config=discovery_config
        )

    @pytest.fixture
    def sample_repo_context(self):
        """Create sample repository context."""
        return RepositoryContext(
            repository_id=uuid.uuid4(),
            repository_owner="octocat",
            repository_name="Hello-World"
        )

    @pytest.fixture
    def sample_github_pr(self):
        """Create sample GitHub PR data."""
        return {
            "number": 123,
            "title": "Test PR",
            "state": "open",
            "draft": False,
            "user": {"login": "octocat"},
            "base": {
                "ref": "main",
                "sha": "abc123",
                "repo": {
                    "owner": {"login": "octocat"},
                    "name": "Hello-World"
                }
            },
            "head": {
                "ref": "feature-branch",
                "sha": "def456"
            },
            "html_url": "https://github.com/octocat/Hello-World/pull/123",
            "body": "This is a test PR",
            "updated_at": "2025-01-01T10:00:00Z",
            "created_at": "2025-01-01T09:00:00Z",
            "id": 456789,
            "node_id": "PR_node_123",
            "mergeable": True,
            "mergeable_state": "clean",
            "labels": [{"name": "bug"}, {"name": "enhancement"}],
            "assignees": [{"login": "octocat"}]
        }

    async def test_engine_initialization(self, mock_github_client, mock_cache_manager):
        """Test engine initialization."""
        engine = PRDiscoveryEngine(mock_github_client, mock_cache_manager)
        
        assert engine.github_client == mock_github_client
        assert engine.cache_manager == mock_cache_manager
        assert engine.config.per_page == 100  # Default value
        assert isinstance(engine._metrics, type(engine._metrics))

    async def test_discover_prs_single_repo_success(
        self, discovery_engine, sample_repo_context, sample_github_pr, mock_github_client
    ):
        """Test successful PR discovery for single repository."""
        # Mock paginator with proper async iterator
        mock_paginator = MockAsyncIterator([sample_github_pr])
        mock_github_client.paginate.return_value = mock_paginator

        results, metrics = await discovery_engine.discover_prs([sample_repo_context])
        
        assert len(results) == 1
        assert results[0].pr_number == 123
        assert results[0].title == "Test PR"
        assert results[0].repository_owner == "octocat"
        assert results[0].repository_name == "Hello-World"
        assert metrics.prs_discovered == 1
        assert metrics.discovery_duration > 0

    async def test_discover_prs_multiple_repos(
        self, discovery_engine, mock_github_client, sample_github_pr
    ):
        """Test PR discovery across multiple repositories."""
        # Create multiple repo contexts
        repos = [
            RepositoryContext(uuid.uuid4(), "owner1", "repo1"),
            RepositoryContext(uuid.uuid4(), "owner2", "repo2"),
        ]

        # Mock different PRs for each repo
        pr1 = {**sample_github_pr, "number": 100}
        pr2 = {**sample_github_pr, "number": 200}

        def mock_paginate_side_effect(path, **kwargs):
            if "owner1/repo1" in path:
                return MockAsyncIterator([pr1])
            else:
                return MockAsyncIterator([pr2])

        mock_github_client.paginate.side_effect = mock_paginate_side_effect

        results, metrics = await discovery_engine.discover_prs(repos)
        
        assert len(results) == 2
        assert {r.pr_number for r in results} == {100, 200}
        assert metrics.prs_discovered == 2

    async def test_discover_prs_with_filters(
        self, discovery_engine, sample_repo_context, sample_github_pr, mock_github_client
    ):
        """Test PR discovery with filtering options."""
        # Create draft PR
        draft_pr = {**sample_github_pr, "number": 124, "draft": True}
        closed_pr = {**sample_github_pr, "number": 125, "state": "closed"}

        mock_paginator = MockAsyncIterator([sample_github_pr, draft_pr, closed_pr])
        mock_github_client.paginate.return_value = mock_paginator

        # Test with drafts excluded (default)
        results, _ = await discovery_engine.discover_prs([sample_repo_context])
        assert len(results) == 2  # Excludes draft (gets open PR and closed PR)
        
        # Verify the draft was filtered out
        pr_numbers = {r.pr_number for r in results}
        assert 123 in pr_numbers  # Original open PR
        assert 125 in pr_numbers  # Closed PR
        assert 124 not in pr_numbers  # Draft PR should be filtered

        # Reset the mock for second test
        mock_paginator = MockAsyncIterator([sample_github_pr, draft_pr, closed_pr])
        mock_github_client.paginate.return_value = mock_paginator

        # Test with drafts included
        results, _ = await discovery_engine.discover_prs(
            [sample_repo_context], include_drafts=True
        )
        assert len(results) == 3  # Includes draft

    async def test_discover_prs_with_since_filter(
        self, discovery_engine, sample_repo_context, sample_github_pr, mock_github_client
    ):
        """Test PR discovery with since parameter."""
        since = datetime.now() - timedelta(days=1)

        mock_paginator = AsyncMock()
        mock_paginator.__aiter__ = AsyncMock(return_value=iter([sample_github_pr]))
        mock_github_client.paginate.return_value = mock_paginator

        await discovery_engine.discover_prs([sample_repo_context], since=since)
        
        # Verify paginate was called with since parameter
        mock_github_client.paginate.assert_called_once()
        call_args = mock_github_client.paginate.call_args
        assert "since" in call_args.kwargs["params"]

    async def test_discover_prs_for_repo_convenience_method(
        self, discovery_engine, sample_github_pr, mock_github_client
    ):
        """Test convenience method for single repository."""
        mock_paginator = MockAsyncIterator([sample_github_pr])
        mock_github_client.paginate.return_value = mock_paginator

        repo_id = uuid.uuid4()
        results = await discovery_engine.discover_prs_for_repo(
            repository_id=repo_id,
            repository_owner="octocat",
            repository_name="Hello-World"
        )
        
        assert len(results) == 1
        assert results[0].repository_id == repo_id

    async def test_get_pull_request_details_success(
        self, discovery_engine, sample_github_pr, mock_github_client, mock_cache_manager
    ):
        """Test fetching specific PR details."""
        mock_github_client.get_pull.return_value = sample_github_pr

        result = await discovery_engine.get_pull_request_details("octocat", "Hello-World", 123)
        
        assert result.pr_number == 123
        assert result.title == "Test PR"
        
        # Verify caching
        mock_cache_manager.set.assert_called_once()

    async def test_get_pull_request_details_cached(
        self, discovery_engine, sample_github_pr, mock_github_client, mock_cache_manager
    ):
        """Test fetching PR details from cache."""
        # Create discovery result for cache
        discovery_result = await discovery_engine._convert_github_pr_to_discovery_result(
            sample_github_pr, uuid.uuid4()
        )
        
        mock_cache_manager.get.return_value = discovery_result.to_dict()

        result = await discovery_engine.get_pull_request_details("octocat", "Hello-World", 123)
        
        assert result.pr_number == 123
        # GitHub API should not be called
        mock_github_client.get_pull.assert_not_called()

    async def test_get_pull_request_details_not_found(
        self, discovery_engine, mock_github_client
    ):
        """Test handling of PR not found."""
        mock_github_client.get_pull.side_effect = GitHubNotFoundError("PR not found")

        with pytest.raises(GitHubNotFoundError):
            await discovery_engine.get_pull_request_details("octocat", "Hello-World", 999)

    async def test_check_pr_exists_true(self, discovery_engine, sample_github_pr, mock_github_client):
        """Test PR existence check - exists."""
        mock_github_client.get_pull.return_value = sample_github_pr

        exists = await discovery_engine.check_pr_exists("octocat", "Hello-World", 123)
        assert exists is True

    async def test_check_pr_exists_false(self, discovery_engine, mock_github_client):
        """Test PR existence check - not found."""
        mock_github_client.get_pull.side_effect = GitHubNotFoundError("PR not found")

        exists = await discovery_engine.check_pr_exists("octocat", "Hello-World", 999)
        assert exists is False

    async def test_rate_limit_handling(
        self, discovery_engine, sample_repo_context, mock_github_client
    ):
        """Test rate limit handling."""
        # Mock rate limit error
        rate_limit_error = GitHubRateLimitError(
            "Rate limit exceeded",
            reset_time=int((datetime.now() + timedelta(seconds=1)).timestamp())
        )
        
        mock_paginator = AsyncMock()
        mock_paginator.__aiter__.side_effect = rate_limit_error
        mock_github_client.paginate.return_value = mock_paginator

        # Should handle gracefully and return empty results
        results, metrics = await discovery_engine.discover_prs([sample_repo_context])
        assert len(results) == 0
        # Should still complete without raising

    async def test_repository_not_found_handling(
        self, discovery_engine, sample_repo_context, mock_github_client
    ):
        """Test repository not found handling."""
        mock_paginator = AsyncMock()
        mock_paginator.__aiter__.side_effect = GitHubNotFoundError("Repository not found")
        mock_github_client.paginate.return_value = mock_paginator

        results, metrics = await discovery_engine.discover_prs([sample_repo_context])
        assert len(results) == 0
        # Should complete without raising

    async def test_concurrent_processing(self, mock_github_client, mock_cache_manager):
        """Test concurrent processing of repositories."""
        config = DiscoveryConfig(max_concurrent_repos=2, batch_size=1, request_delay=0)
        engine = PRDiscoveryEngine(mock_github_client, mock_cache_manager, config)

        # Create multiple repositories
        repos = [
            RepositoryContext(uuid.uuid4(), f"owner{i}", f"repo{i}")
            for i in range(3)
        ]

        # Track call order
        call_order = []
        
        def mock_paginate_side_effect(path, **kwargs):
            call_order.append(path)
            return MockAsyncIterator([])

        mock_github_client.paginate.side_effect = mock_paginate_side_effect

        await engine.discover_prs(repos)
        
        # Verify all repositories were processed
        assert len(call_order) == 3
        assert all(f"owner{i}/repo{i}" in path for i, path in enumerate(call_order))

    async def test_convert_github_pr_to_discovery_result(
        self, discovery_engine, sample_github_pr
    ):
        """Test conversion of GitHub PR data to DiscoveryResult."""
        repo_id = uuid.uuid4()
        
        result = await discovery_engine._convert_github_pr_to_discovery_result(
            sample_github_pr, repo_id
        )
        
        assert result.repository_id == repo_id
        assert result.pr_number == 123
        assert result.title == "Test PR"
        assert result.author == "octocat"
        assert result.state == PRState.OPENED
        assert result.draft is False
        assert result.base_branch == "main"
        assert result.head_branch == "feature-branch"
        assert result.base_sha == "abc123"
        assert result.head_sha == "def456"
        assert result.url == "https://github.com/octocat/Hello-World/pull/123"
        assert result.github_id == 456789
        assert result.github_node_id == "PR_node_123"
        
        # Check metadata
        assert result.pr_metadata is not None
        assert result.pr_metadata["mergeable"] is True
        assert result.pr_metadata["labels"] == ["bug", "enhancement"]
        assert result.pr_metadata["assignees"] == ["octocat"]

    async def test_convert_github_pr_merged_state(self, discovery_engine):
        """Test conversion of merged PR."""
        pr_data = {
            "number": 123,
            "title": "Merged PR",
            "state": "closed",
            "merged": True,
            "user": {"login": "octocat"},
            "base": {
                "ref": "main",
                "sha": "abc123",
                "repo": {"owner": {"login": "octocat"}, "name": "Hello-World"}
            },
            "head": {"ref": "feature", "sha": "def456"},
            "html_url": "https://github.com/octocat/Hello-World/pull/123",
        }
        
        result = await discovery_engine._convert_github_pr_to_discovery_result(
            pr_data, uuid.uuid4()
        )
        
        assert result.state == PRState.MERGED

    async def test_convert_github_pr_closed_state(self, discovery_engine):
        """Test conversion of closed (non-merged) PR."""
        pr_data = {
            "number": 123,
            "title": "Closed PR",
            "state": "closed",
            "merged": False,
            "user": {"login": "octocat"},
            "base": {
                "ref": "main",
                "sha": "abc123",
                "repo": {"owner": {"login": "octocat"}, "name": "Hello-World"}
            },
            "head": {"ref": "feature", "sha": "def456"},
            "html_url": "https://github.com/octocat/Hello-World/pull/123",
        }
        
        result = await discovery_engine._convert_github_pr_to_discovery_result(
            pr_data, uuid.uuid4()
        )
        
        assert result.state == PRState.CLOSED

    async def test_cache_key_generation(self, discovery_engine, sample_repo_context):
        """Test cache key generation."""
        since = datetime(2025, 1, 1, 10, 0, 0)
        
        key = discovery_engine._generate_cache_key(
            sample_repo_context, PRState.OPENED, since, False
        )
        
        expected = "prs:octocat/Hello-World:opened:2025-01-01T10:00:00:False"
        assert key == expected

    async def test_cache_key_generation_no_since(self, discovery_engine, sample_repo_context):
        """Test cache key generation without since parameter."""
        key = discovery_engine._generate_cache_key(
            sample_repo_context, PRState.OPENED, None, True
        )
        
        expected = "prs:octocat/Hello-World:opened:none:True"
        assert key == expected

    async def test_state_conversion_to_github(self, discovery_engine):
        """Test state conversion to GitHub API format."""
        assert discovery_engine._convert_state_to_github(PRState.OPENED) == "open"
        assert discovery_engine._convert_state_to_github(PRState.CLOSED) == "closed"
        assert discovery_engine._convert_state_to_github(PRState.MERGED) == "closed"

    async def test_passes_filters_draft_excluded(self, discovery_engine):
        """Test filtering logic for draft PRs."""
        # Create mock DiscoveryResult
        draft_pr = MagicMock()
        draft_pr.draft = True
        
        non_draft_pr = MagicMock()
        non_draft_pr.draft = False
        
        assert not discovery_engine._passes_filters(draft_pr, include_drafts=False)
        assert discovery_engine._passes_filters(non_draft_pr, include_drafts=False)
        assert discovery_engine._passes_filters(draft_pr, include_drafts=True)

    async def test_is_pr_too_old(self, discovery_engine):
        """Test PR age checking."""
        from datetime import timezone
        
        # Recent PR
        recent_pr = {
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        }
        assert not discovery_engine._is_pr_too_old(recent_pr, 30)
        
        # Old PR
        old_pr = {
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat().replace("+00:00", "Z")
        }
        assert discovery_engine._is_pr_too_old(old_pr, 30)
        
        # PR without updated_at
        no_date_pr = {}
        assert not discovery_engine._is_pr_too_old(no_date_pr, 30)

    async def test_prioritize_repositories(self, discovery_engine):
        """Test repository prioritization."""
        repos = [
            RepositoryContext(uuid.uuid4(), "owner1", "repo1", processing_priority=1),
            RepositoryContext(uuid.uuid4(), "owner2", "repo2", processing_priority=3),
            RepositoryContext(uuid.uuid4(), "owner3", "repo3", processing_priority=2),
        ]
        
        prioritized = discovery_engine._prioritize_repositories(repos)
        
        assert prioritized[0].processing_priority == 3
        assert prioritized[1].processing_priority == 2
        assert prioritized[2].processing_priority == 1

    async def test_create_batches(self, discovery_engine):
        """Test batch creation."""
        repos = [
            RepositoryContext(uuid.uuid4(), f"owner{i}", f"repo{i}")
            for i in range(5)
        ]
        
        batches = discovery_engine._create_batches(repos, batch_size=2)
        
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    async def test_get_metrics(self, discovery_engine):
        """Test metrics retrieval."""
        metrics = await discovery_engine.get_metrics()
        assert metrics.prs_discovered == 0  # Initial state

    async def test_clear_cache(self, discovery_engine, mock_cache_manager):
        """Test cache clearing."""
        mock_cache_manager.clear.return_value = 10
        
        cleared = await discovery_engine.clear_cache("prs:*")
        
        assert cleared == 10
        mock_cache_manager.clear.assert_called_once_with("prs:*")

    async def test_clear_cache_default_pattern(self, discovery_engine, mock_cache_manager):
        """Test cache clearing with default pattern."""
        mock_cache_manager.clear.return_value = 5
        
        cleared = await discovery_engine.clear_cache()
        
        assert cleared == 5
        mock_cache_manager.clear.assert_called_once_with("prs:*")


class TestCheckRunDiscoveryEngine:
    """Test Check Run Discovery Engine functionality."""

    @pytest.fixture
    def mock_github_client(self):
        """Create mock GitHub client."""
        return AsyncMock(spec=GitHubClient)

    @pytest.fixture
    def mock_cache_manager(self):
        """Create mock cache manager."""
        mock = AsyncMock(spec=CacheManager)
        mock.get.return_value = None  # Default to cache miss
        return mock

    @pytest.fixture
    def discovery_config(self):
        """Create test discovery configuration."""
        return DiscoveryConfig(
            per_page=50,
            max_concurrent_repos=2,
            cache_ttl=60,
            batch_size=10,
            request_delay=0,  # No delay in tests
        )

    @pytest.fixture
    def check_run_engine(self, mock_github_client, mock_cache_manager, discovery_config):
        """Create check run discovery engine with mocks."""
        return CheckRunDiscoveryEngine(
            github_client=mock_github_client,
            cache_manager=mock_cache_manager,
            config=discovery_config
        )

    @pytest.fixture
    def sample_github_check_run(self):
        """Create sample GitHub check run data."""
        return {
            "id": 12345,
            "name": "CI Build",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2025-01-01T10:00:00Z",
            "completed_at": "2025-01-01T10:05:00Z",
            "details_url": "https://github.com/octocat/Hello-World/runs/12345",
            "html_url": "https://github.com/octocat/Hello-World/actions/runs/12345",
            "check_suite": {
                "id": 67890
            },
            "output": {
                "title": "Build successful",
                "summary": "All tests passed",
                "text": "Build completed successfully with no errors",
                "annotations": [],
                "images": []
            },
            "app": {
                "name": "GitHub Actions",
                "slug": "github-actions",
                "owner": {"login": "github"}
            },
            "pull_requests": [],
            "node_id": "CR_node_12345"
        }

    @pytest.fixture
    def sample_failed_check_run(self):
        """Create sample failed check run data."""
        return {
            "id": 54321,
            "name": "Lint Check",
            "status": "completed",
            "conclusion": "failure",
            "started_at": "2025-01-01T10:00:00Z",
            "completed_at": "2025-01-01T10:02:00Z",
            "details_url": "https://github.com/octocat/Hello-World/runs/54321",
            "html_url": "https://github.com/octocat/Hello-World/actions/runs/54321",
            "check_suite": {
                "id": 67890
            },
            "output": {
                "title": "Linting failed",
                "summary": "Code style violations found",
                "text": "Error: Line 42: Missing semicolon",
                "annotations": [{"path": "src/main.js", "message": "Missing semicolon"}],
                "images": []
            },
            "app": {
                "name": "ESLint",
                "slug": "eslint"
            },
            "pull_requests": [],
            "node_id": "CR_node_54321"
        }

    async def test_engine_initialization(self, mock_github_client, mock_cache_manager):
        """Test check run engine initialization."""
        engine = CheckRunDiscoveryEngine(mock_github_client, mock_cache_manager)
        
        assert engine.github_client == mock_github_client
        assert engine.cache_manager == mock_cache_manager
        assert engine.config.per_page == 100  # Default value
        assert isinstance(engine._check_run_cache, dict)
        assert isinstance(engine._check_suite_cache, dict)

    async def test_discover_check_runs_success(
        self, check_run_engine, sample_github_check_run, mock_github_client
    ):
        """Test successful check run discovery."""
        mock_paginator = MockAsyncIterator([sample_github_check_run])
        mock_github_client.paginate.return_value = mock_paginator

        results = await check_run_engine.discover_check_runs(
            "octocat", "Hello-World", 123, "abc123"
        )
        
        assert len(results) == 1
        assert results[0].check_name == "CI Build"
        assert results[0].status == CheckStatus.COMPLETED
        assert results[0].conclusion == CheckConclusion.SUCCESS
        assert results[0].pr_number == 123
        assert results[0].github_check_run_id == "12345"

    async def test_discover_check_runs_for_commit(
        self, check_run_engine, sample_github_check_run, mock_github_client
    ):
        """Test check run discovery for specific commit."""
        mock_paginator = MockAsyncIterator([sample_github_check_run])
        mock_github_client.paginate.return_value = mock_paginator

        results = await check_run_engine.discover_check_runs_for_commit(
            "octocat", "Hello-World", "abc123"
        )
        
        assert len(results) == 1
        assert results[0].check_name == "CI Build"
        assert results[0].github_check_run_id == "12345"

    async def test_discover_check_runs_for_commit_cached(
        self, check_run_engine, sample_github_check_run, mock_github_client, mock_cache_manager
    ):
        """Test check run discovery with cache hit."""
        # Setup cache to return data
        cached_data = [{
            "pr_id": str(uuid.uuid4()),
            "pr_number": 0,
            "github_check_run_id": "12345",
            "check_name": "CI Build",
            "status": "completed",
            "conclusion": "success",
            "discovered_at": datetime.now().isoformat(),
        }]
        mock_cache_manager.get.return_value = cached_data

        results = await check_run_engine.discover_check_runs_for_commit(
            "octocat", "Hello-World", "abc123"
        )
        
        assert len(results) == 1
        # GitHub API should not be called
        mock_github_client.paginate.assert_not_called()

    async def test_convert_github_check_run_success(
        self, check_run_engine, sample_github_check_run
    ):
        """Test conversion of GitHub check run data."""
        result = await check_run_engine._convert_github_check_run(sample_github_check_run)
        
        assert result.github_check_run_id == "12345"
        assert result.check_name == "CI Build"
        assert result.status == CheckStatus.COMPLETED
        assert result.conclusion == CheckConclusion.SUCCESS
        assert result.check_suite_id == "67890"
        assert result.details_url == "https://github.com/octocat/Hello-World/runs/12345"
        assert result.output_summary == "All tests passed"
        assert result.output_text == "Build completed successfully with no errors"
        assert result.started_at is not None
        assert result.completed_at is not None

    async def test_convert_github_check_run_failed(
        self, check_run_engine, sample_failed_check_run
    ):
        """Test conversion of failed check run."""
        result = await check_run_engine._convert_github_check_run(sample_failed_check_run)
        
        assert result.github_check_run_id == "54321"
        assert result.check_name == "Lint Check"
        assert result.status == CheckStatus.COMPLETED
        assert result.conclusion == CheckConclusion.FAILURE
        assert result.is_failed is True

    async def test_convert_github_check_run_queued(self, check_run_engine):
        """Test conversion of queued check run."""
        queued_check = {
            "id": 11111,
            "name": "Pending Check",
            "status": "queued",
            "conclusion": None,
            "started_at": None,
            "completed_at": None,
            "check_suite": {"id": 22222},
            "output": {},
            "app": {"name": "Test App"}
        }
        
        result = await check_run_engine._convert_github_check_run(queued_check)
        
        assert result.status == CheckStatus.QUEUED
        assert result.conclusion is None
        assert result.started_at is None
        assert result.completed_at is None

    async def test_detect_check_run_changes_new_check(self, check_run_engine):
        """Test detection of new check runs."""
        old_runs = []
        new_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="New Check",
            status=CheckStatus.QUEUED,
        )
        new_runs = [new_run]
        
        changes = await check_run_engine.detect_check_run_changes(
            old_runs, new_runs, uuid.uuid4(), 123
        )
        
        assert len(changes) == 1
        assert changes[0].event_type == ChangeType.CHECK_RUN_CREATED
        assert changes[0].check_run_name == "New Check"

    async def test_detect_check_run_changes_status_updated(self, check_run_engine):
        """Test detection of status changes."""
        pr_id = uuid.uuid4()
        
        old_run = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="12345",
            check_name="Test Check",
            status=CheckStatus.QUEUED,
        )
        
        new_run = CheckRunDiscovery(
            pr_id=pr_id,
            pr_number=123,
            github_check_run_id="12345",
            check_name="Test Check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
        )
        
        changes = await check_run_engine.detect_check_run_changes(
            [old_run], [new_run], pr_id, 123
        )
        
        assert len(changes) == 1
        assert changes[0].event_type == ChangeType.CHECK_RUN_STATUS_CHANGED
        assert "status" in changes[0].changed_fields
        assert "conclusion" in changes[0].changed_fields

    async def test_compare_check_run_states(self, check_run_engine):
        """Test comparison of check run states."""
        old_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="Test Check",
            status=CheckStatus.QUEUED,
            output_summary="Initial",
        )
        
        new_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="Test Check",
            status=CheckStatus.COMPLETED,
            conclusion=CheckConclusion.SUCCESS,
            output_summary="Completed successfully",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        
        changed_fields = check_run_engine._compare_check_run_states(old_run, new_run)
        
        expected_fields = {"status", "conclusion", "output_summary", "started_at", "completed_at"}
        assert set(changed_fields) == expected_fields

    async def test_categorize_check_run_lint(self, check_run_engine):
        """Test check run categorization - lint."""
        check_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="ESLint Check",
        )
        
        category = check_run_engine._categorize_check_run(check_run)
        assert category == "lint"

    async def test_categorize_check_run_test(self, check_run_engine):
        """Test check run categorization - test."""
        check_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="Unit Tests",
        )
        
        category = check_run_engine._categorize_check_run(check_run)
        assert category == "test"

    async def test_categorize_check_run_build(self, check_run_engine):
        """Test check run categorization - build."""
        check_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="Build Project",
        )
        
        category = check_run_engine._categorize_check_run(check_run)
        assert category == "build"

    async def test_categorize_check_run_other(self, check_run_engine):
        """Test check run categorization - other."""
        check_run = CheckRunDiscovery(
            pr_id=uuid.uuid4(),
            pr_number=123,
            github_check_run_id="12345",
            check_name="Custom Check",
        )
        
        category = check_run_engine._categorize_check_run(check_run)
        assert category == "other"

    async def test_extract_check_metadata(self, check_run_engine, sample_github_check_run):
        """Test metadata extraction from check run."""
        metadata = await check_run_engine._extract_check_metadata(sample_github_check_run)
        
        assert "output" in metadata
        assert metadata["output"]["title"] == "Build successful"
        assert metadata["output"]["summary"] == "All tests passed"
        assert metadata["output"]["annotations_count"] == 0
        
        assert "app" in metadata
        assert metadata["app"]["name"] == "GitHub Actions"
        assert metadata["app"]["owner"] == "github"
        
        assert "external_id" in metadata
        assert metadata["external_id"] == 12345

    async def test_process_check_suite(
        self, check_run_engine, mock_github_client, mock_cache_manager
    ):
        """Test check suite processing."""
        suite_data = {
            "id": 67890,
            "head_branch": "main",
            "head_sha": "abc123",
            "status": "completed",
            "conclusion": "success",
            "url": "https://api.github.com/repos/octocat/Hello-World/check-suites/67890",
            "created_at": "2025-01-01T09:00:00Z",
            "updated_at": "2025-01-01T10:00:00Z",
            "app": {"name": "GitHub Actions"}
        }
        
        mock_github_client.get.return_value = suite_data
        
        result = await check_run_engine._process_check_suite(
            "octocat", "Hello-World", "67890"
        )
        
        assert result is not None
        assert result["id"] == 67890
        assert result["head_branch"] == "main"
        assert result["status"] == "completed"
        assert result["conclusion"] == "success"
        
        # Verify caching
        mock_cache_manager.set.assert_called_once()

    async def test_process_check_suite_cached(
        self, check_run_engine, mock_github_client, mock_cache_manager
    ):
        """Test check suite processing with cache hit."""
        cached_suite = {
            "id": 67890,
            "head_branch": "main",
            "status": "completed"
        }
        mock_cache_manager.get.return_value = cached_suite
        
        result = await check_run_engine._process_check_suite(
            "octocat", "Hello-World", "67890"
        )
        
        assert result == cached_suite
        # GitHub API should not be called
        mock_github_client.get.assert_not_called()

    async def test_process_check_suite_error(
        self, check_run_engine, mock_github_client, mock_cache_manager
    ):
        """Test check suite processing with error."""
        mock_github_client.get.side_effect = GitHubNotFoundError("Suite not found")
        
        result = await check_run_engine._process_check_suite(
            "octocat", "Hello-World", "67890"
        )
        
        assert result is None

    async def test_process_check_suites_batch(self, check_run_engine):
        """Test batch processing of check suites."""
        with patch.object(
            check_run_engine, '_process_check_suite', new_callable=AsyncMock
        ) as mock_process:
            suite_ids = ["123", "456", "789"]
            
            await check_run_engine._process_check_suites(
                "octocat", "Hello-World", suite_ids
            )
            
            assert mock_process.call_count == 3
            # Verify each suite ID was processed
            called_suite_ids = [call[0][2] for call in mock_process.call_args_list]
            assert set(called_suite_ids) == set(suite_ids)

    async def test_get_check_run_details(
        self, check_run_engine, sample_github_check_run, mock_github_client
    ):
        """Test getting detailed check run information."""
        mock_github_client.get.return_value = sample_github_check_run
        
        result = await check_run_engine.get_check_run_details(
            "octocat", "Hello-World", "12345"
        )
        
        assert result.github_check_run_id == "12345"
        assert result.check_name == "CI Build"
        assert result.status == CheckStatus.COMPLETED

    async def test_get_check_run_details_not_found(
        self, check_run_engine, mock_github_client
    ):
        """Test handling of check run not found."""
        mock_github_client.get.side_effect = GitHubNotFoundError("Check run not found")
        
        with pytest.raises(GitHubNotFoundError):
            await check_run_engine.get_check_run_details("octocat", "Hello-World", "99999")

    async def test_get_failed_check_runs(
        self, check_run_engine, sample_failed_check_run, mock_github_client
    ):
        """Test getting only failed check runs."""
        mock_paginator = MockAsyncIterator([sample_failed_check_run])
        mock_github_client.paginate.return_value = mock_paginator
        
        failed_runs = await check_run_engine.get_failed_check_runs(
            "octocat", "Hello-World", 123, "abc123"
        )
        
        assert len(failed_runs) == 1
        assert failed_runs[0].is_failed is True
        assert failed_runs[0].check_name == "Lint Check"

    async def test_get_failed_check_runs_mixed_results(
        self, check_run_engine, sample_github_check_run, sample_failed_check_run, mock_github_client
    ):
        """Test filtering failed check runs from mixed results."""
        mock_paginator = MockAsyncIterator([sample_github_check_run, sample_failed_check_run])
        mock_github_client.paginate.return_value = mock_paginator
        
        failed_runs = await check_run_engine.get_failed_check_runs(
            "octocat", "Hello-World", 123, "abc123"
        )
        
        # Should only return the failed check
        assert len(failed_runs) == 1
        assert failed_runs[0].conclusion == CheckConclusion.FAILURE

    async def test_rate_limit_handling_check_runs(
        self, check_run_engine, mock_github_client
    ):
        """Test rate limit handling for check runs."""
        rate_limit_error = GitHubRateLimitError(
            "Rate limit exceeded",
            reset_time=int((datetime.now() + timedelta(seconds=1)).timestamp())
        )
        
        mock_paginator = AsyncMock()
        mock_paginator.__aiter__.side_effect = rate_limit_error
        mock_github_client.paginate.return_value = mock_paginator
        
        # Should handle gracefully and return empty results
        results = await check_run_engine.discover_check_runs_for_commit(
            "octocat", "Hello-World", "abc123"
        )
        assert len(results) == 0

    async def test_commit_not_found_handling(self, check_run_engine, mock_github_client):
        """Test commit not found handling."""
        mock_paginator = AsyncMock()
        mock_paginator.__aiter__.side_effect = GitHubNotFoundError("Commit not found")
        mock_github_client.paginate.return_value = mock_paginator
        
        results = await check_run_engine.discover_check_runs_for_commit(
            "octocat", "Hello-World", "nonexistent"
        )
        assert len(results) == 0

    async def test_unknown_status_handling(self, check_run_engine):
        """Test handling of unknown check status."""
        check_with_unknown_status = {
            "id": 12345,
            "name": "Test Check",
            "status": "unknown_status",
            "conclusion": None,
            "check_suite": {"id": 67890},
            "output": {},
            "app": {"name": "Test"}
        }
        
        result = await check_run_engine._convert_github_check_run(check_with_unknown_status)
        
        # Should default to QUEUED for unknown status
        assert result.status == CheckStatus.QUEUED

    async def test_unknown_conclusion_handling(self, check_run_engine):
        """Test handling of unknown check conclusion."""
        check_with_unknown_conclusion = {
            "id": 12345,
            "name": "Test Check",
            "status": "completed",
            "conclusion": "unknown_conclusion",
            "check_suite": {"id": 67890},
            "output": {},
            "app": {"name": "Test"}
        }
        
        result = await check_run_engine._convert_github_check_run(check_with_unknown_conclusion)
        
        # Should set conclusion to None for unknown values
        assert result.conclusion is None

    async def test_get_metrics(self, check_run_engine):
        """Test metrics retrieval."""
        metrics = await check_run_engine.get_metrics()
        assert metrics.check_runs_discovered == 0  # Initial state
        assert metrics.check_run_discovery_duration >= 0

    async def test_clear_cache_check_runs(self, check_run_engine, mock_cache_manager):
        """Test cache clearing for check runs."""
        mock_cache_manager.clear.return_value = 15
        
        cleared = await check_run_engine.clear_cache("check_runs:*")
        
        assert cleared == 15
        mock_cache_manager.clear.assert_called_once_with("check_runs:*")

    async def test_clear_cache_default_pattern_check_runs(
        self, check_run_engine, mock_cache_manager
    ):
        """Test cache clearing with default pattern for check runs."""
        mock_cache_manager.clear.return_value = 8
        
        cleared = await check_run_engine.clear_cache()
        
        assert cleared == 8
        mock_cache_manager.clear.assert_called_once_with("check_runs:*")