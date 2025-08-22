"""Tests for PR discovery engine."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.github import GitHubClient
from src.github.exceptions import GitHubError, GitHubNotFoundError
from src.workers.monitor.discovery import PRDiscoveryEngine
from src.workers.monitor.models import RepositoryConfig


class TestPRDiscoveryEngine:
    """
    Why: Ensure PR discovery engine correctly fetches and parses GitHub data
    What: Tests PR and check run discovery with various scenarios and error handling
    How: Mock GitHub API responses and verify correct parsing and error handling
    """
    
    @pytest.fixture
    def mock_github_client(self):
        """Create mock GitHub client."""
        client = Mock(spec=GitHubClient)
        client.list_pulls = AsyncMock()
        client.list_check_runs = AsyncMock()
        return client
    
    @pytest.fixture
    def discovery_engine(self, mock_github_client):
        """Create discovery engine with mocked client."""
        return PRDiscoveryEngine(mock_github_client)
    
    @pytest.fixture
    def repo_config(self):
        """Create test repository configuration."""
        return RepositoryConfig(
            id=uuid.uuid4(),
            url="https://github.com/owner/repo",
            owner="owner",
            name="repo",
            auth_token="test-token"
        )
    
    @pytest.fixture
    def sample_pr_data(self):
        """Create sample PR data from GitHub API."""
        return {
            "number": 123,
            "title": "Test PR",
            "user": {"login": "test-user"},
            "state": "open",
            "draft": False,
            "base": {"ref": "main", "sha": "base123"},
            "head": {"ref": "feature", "sha": "head456"},
            "html_url": "https://github.com/owner/repo/pull/123",
            "body": "Test PR body",
            "labels": [{"name": "bug"}, {"name": "priority-high"}],
            "milestone": {"title": "v1.0"},
            "assignees": [{"login": "assignee1"}],
            "requested_reviewers": [{"login": "reviewer1"}],
            "mergeable": True,
            "mergeable_state": "clean",
            "merged_at": None,
            "closed_at": None,
            "updated_at": "2024-01-01T12:00:00Z"
        }
    
    @pytest.fixture
    def sample_check_run_data(self):
        """Create sample check run data from GitHub API."""
        return {
            "check_runs": [
                {
                    "id": 456,
                    "name": "test-check",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2024-01-01T12:00:00Z",
                    "completed_at": "2024-01-01T12:05:00Z",
                    "details_url": "https://example.com/check/456",
                    "output": {
                        "title": "All tests passed",
                        "summary": "Tests completed successfully"
                    },
                    "external_id": "ext-456"
                }
            ]
        }
    
    async def test_discover_prs_success(self, discovery_engine, repo_config, sample_pr_data):
        """
        Why: Verify successful PR discovery and parsing
        What: Tests normal PR discovery flow with valid GitHub response
        How: Mock list_pulls to return sample data and verify correct parsing
        """
        # Arrange
        discovery_engine.github_client.list_pulls.return_value = AsyncMock()
        discovery_engine.github_client.list_pulls.return_value.__aiter__ = AsyncMock(
            return_value=iter([[sample_pr_data]])
        )
        
        # Act
        prs, errors = await discovery_engine.discover_prs(repo_config)
        
        # Assert
        assert len(prs) == 1
        assert len(errors) == 0
        
        pr = prs[0]
        assert pr.number == 123
        assert pr.title == "Test PR"
        assert pr.author == "test-user"
        assert pr.state == "open"
        assert not pr.draft
        assert pr.base_branch == "main"
        assert pr.head_branch == "feature"
        assert pr.base_sha == "base123"
        assert pr.head_sha == "head456"
        assert pr.url == "https://github.com/owner/repo/pull/123"
        assert pr.body == "Test PR body"
        assert pr.metadata["labels"] == ["bug", "priority-high"]
        assert pr.metadata["milestone"] == "v1.0"
        assert pr.metadata["assignees"] == ["assignee1"]
        
        # Verify GitHub client was called correctly
        discovery_engine.github_client.list_pulls.assert_called_once_with(
            "owner", "repo", state="open", per_page=100
        )
    
    async def test_discover_prs_multiple_states(self, discovery_engine, repo_config, sample_pr_data):
        """
        Why: Verify discovery handles multiple PR states correctly
        What: Tests discovery with both open and closed states
        How: Mock responses for both states and verify both are called
        """
        # Arrange
        discovery_engine.github_client.list_pulls.return_value = AsyncMock()
        discovery_engine.github_client.list_pulls.return_value.__aiter__ = AsyncMock(
            return_value=iter([[sample_pr_data]])
        )
        
        # Act
        prs, errors = await discovery_engine.discover_prs(
            repo_config, states=["open", "closed"]
        )
        
        # Assert
        assert len(prs) == 2  # One for each state
        assert len(errors) == 0
        
        # Verify GitHub client was called for both states
        assert discovery_engine.github_client.list_pulls.call_count == 2
    
    async def test_discover_prs_with_since_filter(self, discovery_engine, repo_config, sample_pr_data):
        """
        Why: Verify since filter correctly excludes old PRs
        What: Tests filtering PRs by update time
        How: Set since time after PR update time and verify PR is excluded
        """
        # Arrange
        discovery_engine.github_client.list_pulls.return_value = AsyncMock()
        discovery_engine.github_client.list_pulls.return_value.__aiter__ = AsyncMock(
            return_value=iter([[sample_pr_data]])
        )
        
        # Set since time after the PR's update time
        since_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        
        # Act
        prs, errors = await discovery_engine.discover_prs(repo_config, since=since_time)
        
        # Assert
        assert len(prs) == 0  # PR should be filtered out
        assert len(errors) == 0
    
    async def test_discover_prs_parsing_error(self, discovery_engine, repo_config):
        """
        Why: Verify graceful handling of malformed PR data
        What: Tests error handling when PR data is invalid
        How: Mock response with invalid data and verify error is recorded
        """
        # Arrange
        invalid_pr_data = {"number": 123}  # Missing required fields
        discovery_engine.github_client.list_pulls.return_value = AsyncMock()
        discovery_engine.github_client.list_pulls.return_value.__aiter__ = AsyncMock(
            return_value=iter([[invalid_pr_data]])
        )
        
        # Act
        prs, errors = await discovery_engine.discover_prs(repo_config)
        
        # Assert
        assert len(prs) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "pr_parsing_error"
        assert "Failed to parse PR #123" in errors[0].message
    
    async def test_discover_prs_repository_not_found(self, discovery_engine, repo_config):
        """
        Why: Verify handling of repository access errors
        What: Tests behavior when repository is not found or not accessible
        How: Mock GitHubNotFoundError and verify appropriate error is recorded
        """
        # Arrange
        discovery_engine.github_client.list_pulls.side_effect = GitHubNotFoundError(
            "Repository not found"
        )
        
        # Act
        prs, errors = await discovery_engine.discover_prs(repo_config)
        
        # Assert
        assert len(prs) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "repository_not_found"
        assert "not found or not accessible" in errors[0].message
    
    async def test_discover_prs_github_api_error(self, discovery_engine, repo_config):
        """
        Why: Verify handling of general GitHub API errors
        What: Tests error handling for GitHub API failures
        How: Mock GitHubError and verify error is properly recorded
        """
        # Arrange
        discovery_engine.github_client.list_pulls.side_effect = GitHubError(
            "API rate limit exceeded"
        )
        
        # Act
        prs, errors = await discovery_engine.discover_prs(repo_config)
        
        # Assert
        assert len(prs) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "github_api_error"
        assert "API rate limit exceeded" in errors[0].message
    
    async def test_discover_check_runs_success(self, discovery_engine, repo_config, sample_check_run_data):
        """
        Why: Verify successful check run discovery and parsing
        What: Tests normal check run discovery flow
        How: Mock list_check_runs and verify correct parsing
        """
        # Arrange
        discovery_engine.github_client.list_check_runs.return_value = AsyncMock()
        discovery_engine.github_client.list_check_runs.return_value.__aiter__ = AsyncMock(
            return_value=iter([sample_check_run_data])
        )
        
        # Act
        check_runs, errors = await discovery_engine.discover_check_runs(
            repo_config, "commit123"
        )
        
        # Assert
        assert len(check_runs) == 1
        assert len(errors) == 0
        
        check = check_runs[0]
        assert check.id == 456
        assert check.name == "test-check"
        assert check.status == "completed"
        assert check.conclusion == "success"
        assert check.details_url == "https://example.com/check/456"
        assert check.output_title == "All tests passed"
        assert check.output_summary == "Tests completed successfully"
        assert check.external_id == "ext-456"
        
        # Verify GitHub client was called correctly
        discovery_engine.github_client.list_check_runs.assert_called_once_with(
            "owner", "repo", "commit123", per_page=100
        )
    
    async def test_discover_check_runs_commit_not_found(self, discovery_engine, repo_config):
        """
        Why: Verify handling of invalid commit SHA
        What: Tests behavior when commit is not found
        How: Mock GitHubNotFoundError and verify appropriate error handling
        """
        # Arrange
        discovery_engine.github_client.list_check_runs.side_effect = GitHubNotFoundError(
            "Commit not found"
        )
        
        # Act
        check_runs, errors = await discovery_engine.discover_check_runs(
            repo_config, "invalid123"
        )
        
        # Assert
        assert len(check_runs) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "commit_not_found"
        assert "Commit invalid123 not found" in errors[0].message
    
    async def test_parse_pr_data_merged_pr(self, discovery_engine, sample_pr_data):
        """
        Why: Verify correct parsing of merged PRs
        What: Tests that merged PRs are identified correctly
        How: Set merged_at field and verify state is parsed as 'merged'
        """
        # Arrange
        sample_pr_data["state"] = "closed"
        sample_pr_data["merged_at"] = "2024-01-01T13:00:00Z"
        
        # Act
        pr = discovery_engine._parse_pr_data(sample_pr_data)
        
        # Assert
        assert pr.state == "merged"
        assert pr.metadata["merged_at"] == "2024-01-01T13:00:00Z"
    
    async def test_parse_pr_data_draft_pr(self, discovery_engine, sample_pr_data):
        """
        Why: Verify correct parsing of draft PRs
        What: Tests draft flag is properly extracted
        How: Set draft to True and verify it's parsed correctly
        """
        # Arrange
        sample_pr_data["draft"] = True
        
        # Act
        pr = discovery_engine._parse_pr_data(sample_pr_data)
        
        # Assert
        assert pr.draft is True
    
    @patch('src.workers.monitor.discovery.PersonalAccessTokenAuth')
    @patch('src.workers.monitor.discovery.GitHubClient')
    async def test_create_for_repository(self, mock_github_client, mock_auth, repo_config):
        """
        Why: Verify correct creation of discovery engine for repository
        What: Tests factory method creates properly configured engine
        How: Mock dependencies and verify proper initialization
        """
        # Arrange
        mock_client_instance = AsyncMock()
        mock_github_client.return_value = mock_client_instance
        
        # Act
        engine = await PRDiscoveryEngine.create_for_repository(repo_config)
        
        # Assert
        assert isinstance(engine, PRDiscoveryEngine)
        mock_auth.assert_called_once_with(repo_config.auth_token)
        mock_github_client.assert_called_once()
        mock_client_instance._ensure_session.assert_called_once()