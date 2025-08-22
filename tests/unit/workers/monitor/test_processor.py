"""Tests for PR processor core logic."""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models import PullRequest
from src.models.enums import PRState
from src.workers.monitor.models import ProcessingResult, RepositoryConfig
from src.workers.monitor.processor import PRProcessor


class TestPRProcessor:
    """
    Why: Ensure PR processor correctly orchestrates discovery, change detection, and synchronization
    What: Tests end-to-end processing workflow with various scenarios
    How: Mock dependencies and verify proper coordination between components
    """
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_pr_repo(self):
        """Create mock PR repository."""
        repo = Mock()
        repo.get_by_repo_and_number = AsyncMock()
        repo.get_active_prs_for_repo = AsyncMock(return_value=[])
        repo.bulk_update_last_checked = AsyncMock(return_value=0)
        return repo
    
    @pytest.fixture
    def mock_check_repo(self):
        """Create mock check run repository."""
        repo = Mock()
        repo.get_by_external_id = AsyncMock()
        return repo
    
    @pytest.fixture
    def processor(self, mock_session, mock_pr_repo, mock_check_repo):
        """Create PR processor with mocked dependencies."""
        return PRProcessor(mock_session, mock_pr_repo, mock_check_repo)
    
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
    
    @patch('src.workers.monitor.processor.PRDiscoveryEngine')
    async def test_process_repository_success(self, mock_discovery_engine, processor, repo_config):
        """
        Why: Verify successful repository processing workflow
        What: Tests complete processing with successful discovery and synchronization
        How: Mock all dependencies and verify proper orchestration
        """
        # Arrange
        mock_engine_instance = AsyncMock()
        mock_discovery_engine.create_for_repository.return_value = mock_engine_instance
        
        # Mock discovery results
        mock_pr_data = Mock()
        mock_pr_data.number = 123
        mock_pr_data.head_sha = "head123"
        
        mock_engine_instance.discover_prs.return_value = ([mock_pr_data], [])
        mock_engine_instance.discover_check_runs.return_value = ([], [])
        mock_engine_instance.github_client = AsyncMock()
        
        # Mock existing PR
        existing_pr = PullRequest(
            id=uuid.uuid4(),
            repository_id=repo_config.id,
            pr_number=123,
            title="Existing PR",
            author="user",
            state=PRState.OPENED,
            base_branch="main",
            head_branch="feature",
            base_sha="base123",
            head_sha="oldhead456",
            url="https://example.com",
            draft=False
        )
        processor.pr_repo.get_by_repo_and_number.return_value = existing_pr
        
        # Mock state detector
        processor.state_detector.detect_pr_changes = Mock(return_value=(existing_pr, []))
        processor.state_detector.build_change_set = Mock()
        processor.state_detector.build_change_set.return_value.has_changes = False
        
        # Act
        result = await processor.process_repository(repo_config)
        
        # Assert
        assert isinstance(result, ProcessingResult)
        assert result.repository_id == repo_config.id
        assert result.prs_processed == 1
        assert not result.has_errors
        
        # Verify discovery was called
        mock_discovery_engine.create_for_repository.assert_called_once_with(repo_config)
        mock_engine_instance.discover_prs.assert_called_once()
        
        # Verify PR lookup was called
        processor.pr_repo.get_by_repo_and_number.assert_called_once_with(
            repo_config.id, 123
        )
        
        # Verify cleanup
        mock_engine_instance.github_client.close.assert_called_once()
    
    @patch('src.workers.monitor.processor.PRDiscoveryEngine')
    async def test_process_repository_no_prs(self, mock_discovery_engine, processor, repo_config):
        """
        Why: Verify handling when no PRs are found
        What: Tests behavior when repository has no PRs to process
        How: Mock empty PR discovery and verify appropriate result
        """
        # Arrange
        mock_engine_instance = AsyncMock()
        mock_discovery_engine.create_for_repository.return_value = mock_engine_instance
        
        # Mock empty discovery results
        mock_engine_instance.discover_prs.return_value = ([], [])
        mock_engine_instance.github_client = AsyncMock()
        
        # Act
        result = await processor.process_repository(repo_config)
        
        # Assert
        assert result.prs_processed == 0
        assert result.new_prs == 0
        assert result.updated_prs == 0
        assert not result.has_errors
    
    @patch('src.workers.monitor.processor.PRDiscoveryEngine')
    async def test_process_repository_with_changes(self, mock_discovery_engine, processor, repo_config):
        """
        Why: Verify handling when changes are detected and need synchronization
        What: Tests processing with detected changes that require database updates
        How: Mock changes detected and verify synchronization is called
        """
        # Arrange
        mock_engine_instance = AsyncMock()
        mock_discovery_engine.create_for_repository.return_value = mock_engine_instance
        
        mock_pr_data = Mock()
        mock_pr_data.number = 123
        mock_pr_data.head_sha = "head123"
        
        mock_engine_instance.discover_prs.return_value = ([mock_pr_data], [])
        mock_engine_instance.discover_check_runs.return_value = ([], [])
        mock_engine_instance.github_client = AsyncMock()
        
        # Mock no existing PR (new PR)
        processor.pr_repo.get_by_repo_and_number.return_value = None
        
        # Mock new PR detected
        new_pr = PullRequest(pr_number=123, state=PRState.OPENED)
        processor.state_detector.detect_pr_changes = Mock(return_value=(new_pr, [{"change_type": "new_pr"}]))
        
        # Mock change set with changes
        mock_change_set = Mock()
        mock_change_set.has_changes = True
        mock_change_set.new_prs = [new_pr]
        mock_change_set.updated_prs = []
        mock_change_set.new_check_runs = []
        mock_change_set.updated_check_runs = []
        processor.state_detector.build_change_set.return_value = mock_change_set
        
        # Mock synchronizer
        processor.synchronizer.synchronize_changes = AsyncMock(return_value=[])
        processor.synchronizer.create_state_transition_records = AsyncMock(return_value=[])
        
        # Act
        result = await processor.process_repository(repo_config)
        
        # Assert
        assert result.new_prs == 1
        assert result.prs_processed == 1
        
        # Verify synchronization was called
        processor.synchronizer.synchronize_changes.assert_called_once_with(
            repo_config.id, mock_change_set
        )
        processor.synchronizer.create_state_transition_records.assert_called_once_with(mock_change_set)
    
    @patch('src.workers.monitor.processor.PRDiscoveryEngine')
    async def test_process_repository_with_errors(self, mock_discovery_engine, processor, repo_config):
        """
        Why: Verify error handling during repository processing
        What: Tests that errors are properly collected and reported
        How: Mock discovery errors and verify they're included in result
        """
        # Arrange
        mock_engine_instance = AsyncMock()
        mock_discovery_engine.create_for_repository.return_value = mock_engine_instance
        
        # Mock discovery with errors
        from src.workers.monitor.models import ProcessingError
        discovery_error = ProcessingError(
            error_type="github_api_error",
            message="API rate limit exceeded"
        )
        mock_engine_instance.discover_prs.return_value = ([], [discovery_error])
        mock_engine_instance.github_client = AsyncMock()
        
        # Act
        result = await processor.process_repository(repo_config)
        
        # Assert
        assert result.has_errors
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "github_api_error"
        assert result.success_rate < 1.0
    
    @patch('src.workers.monitor.processor.PRDiscoveryEngine')
    async def test_process_repository_exception_handling(self, mock_discovery_engine, processor, repo_config):
        """
        Why: Verify handling of unexpected exceptions during processing
        What: Tests that unexpected errors are caught and converted to ProcessingErrors
        How: Mock exception during discovery and verify error handling
        """
        # Arrange
        mock_discovery_engine.create_for_repository.side_effect = Exception("Unexpected error")
        
        # Act
        result = await processor.process_repository(repo_config)
        
        # Assert
        assert result.has_errors
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "repository_processing_error"
        assert "Unexpected error" in result.errors[0].message
        assert result.prs_processed == 0
    
    async def test_process_multiple_repositories(self, processor):
        """
        Why: Verify concurrent processing of multiple repositories
        What: Tests that multiple repositories can be processed concurrently
        How: Mock multiple repository configs and verify concurrent processing
        """
        # Arrange
        repo_configs = [
            RepositoryConfig(
                id=uuid.uuid4(),
                url="https://github.com/owner/repo1",
                owner="owner",
                name="repo1",
                auth_token="token1"
            ),
            RepositoryConfig(
                id=uuid.uuid4(),
                url="https://github.com/owner/repo2", 
                owner="owner",
                name="repo2",
                auth_token="token2"
            )
        ]
        
        # Mock process_repository to return success results
        async def mock_process_repo(config):
            return ProcessingResult(
                repository_id=config.id,
                prs_processed=1,
                new_prs=0,
                updated_prs=1,
                check_runs_updated=0,
                errors=[],
                processing_time=1.0
            )
        
        processor.process_repository = AsyncMock(side_effect=mock_process_repo)
        
        # Act
        results = await processor.process_multiple_repositories(repo_configs, max_concurrent=2)
        
        # Assert
        assert len(results) == 2
        assert all(isinstance(r, ProcessingResult) for r in results)
        assert processor.process_repository.call_count == 2
    
    async def test_process_multiple_repositories_with_exception(self, processor):
        """
        Why: Verify handling of exceptions during concurrent processing
        What: Tests that exceptions in one repository don't affect others
        How: Mock one repository to fail and verify error handling
        """
        # Arrange
        repo_configs = [
            RepositoryConfig(
                id=uuid.uuid4(),
                url="https://github.com/owner/good-repo",
                owner="owner", 
                name="good-repo",
                auth_token="token1"
            ),
            RepositoryConfig(
                id=uuid.uuid4(),
                url="https://github.com/owner/bad-repo",
                owner="owner",
                name="bad-repo", 
                auth_token="token2"
            )
        ]
        
        # Mock first repo to succeed, second to fail
        async def mock_process_repo(config):
            if config.name == "bad-repo":
                raise Exception("Repository processing failed")
            return ProcessingResult(
                repository_id=config.id,
                prs_processed=1,
                new_prs=0,
                updated_prs=1,
                check_runs_updated=0,
                errors=[],
                processing_time=1.0
            )
        
        processor.process_repository = AsyncMock(side_effect=mock_process_repo)
        
        # Act
        results = await processor.process_multiple_repositories(repo_configs)
        
        # Assert
        assert len(results) == 2
        
        # First result should be successful
        good_result = next(r for r in results if not r.has_errors)
        assert good_result.prs_processed == 1
        
        # Second result should be error result
        error_result = next(r for r in results if r.has_errors)
        assert error_result.prs_processed == 0
        assert error_result.errors[0].error_type == "repository_processing_exception"