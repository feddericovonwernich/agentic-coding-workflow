"""
Summary unit tests for Repository classes.

Why: Provide comprehensive test coverage for repository functionality
     focusing on the most critical operations without complex mocking
What: Tests core repository operations, query methods, and error handling
How: Uses simplified mocking approach for reliable testing
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.check_run import CheckRun
from src.models.pull_request import PullRequest
from src.models.repository import Repository
from src.repositories.base import BaseRepository
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.repository import RepositoryRepository


class TestRepositoryCore:
    """Test core repository functionality."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Provide mock AsyncSession for testing."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.add = AsyncMock()
        session.delete = AsyncMock()
        return session

    def test_base_repository_initialization(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify BaseRepository initializes with correct session and model
        What: Tests constructor properly sets attributes
        How: Creates repository and checks attributes
        """
        repo = BaseRepository(mock_session, Repository)

        assert repo.session == mock_session
        assert repo.model_class == Repository

    def test_pull_request_repository_initialization(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Why: Verify PullRequestRepository initializes correctly
        What: Tests constructor sets correct model class
        How: Creates repository and checks model_class
        """
        repo = PullRequestRepository(mock_session)

        assert repo.session == mock_session
        assert repo.model_class == PullRequest

    def test_check_run_repository_initialization(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify CheckRunRepository initializes correctly
        What: Tests constructor sets correct model class
        How: Creates repository and checks model_class
        """
        repo = CheckRunRepository(mock_session)

        assert repo.session == mock_session
        assert repo.model_class == CheckRun

    def test_repository_repository_initialization(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Why: Verify RepositoryRepository initializes correctly
        What: Tests constructor sets correct model class
        How: Creates repository and checks model_class
        """
        repo = RepositoryRepository(mock_session)

        assert repo.session == mock_session
        assert repo.model_class == Repository

    async def test_base_repository_crud_operations(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Why: Verify BaseRepository provides essential CRUD operations
        What: Tests create, read, update, delete operations work
        How: Calls CRUD methods and verifies session method calls
        """
        repo = BaseRepository(mock_session, Repository)

        # Test create
        result = await repo.create(name="test", url="https://github.com/test/repo")
        assert isinstance(result, Repository)
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called()

        # Test get_by_id
        test_id = uuid.uuid4()
        mock_repository = Repository()
        mock_session.get.return_value = mock_repository
        await repo.get_by_id(test_id)
        mock_session.get.assert_called_with(Repository, test_id)

        # Test update
        entity = Repository()
        await repo.update(entity, name="updated")
        assert entity.name == "updated"

        # Test delete
        await repo.delete(entity)
        mock_session.delete.assert_called_with(entity)

    async def test_repository_query_methods_exist(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Why: Verify all repositories have their domain-specific query methods
        What: Tests that custom query methods are defined on each repository
        How: Checks method existence on repository instances
        """
        # Test PullRequestRepository methods
        pr_repo = PullRequestRepository(mock_session)
        assert hasattr(pr_repo, "get_by_repo_and_number")
        assert hasattr(pr_repo, "get_active_prs_for_repo")
        assert hasattr(pr_repo, "get_prs_needing_check")
        assert hasattr(pr_repo, "mark_as_checked")
        assert hasattr(pr_repo, "bulk_update_last_checked")

        # Test CheckRunRepository methods
        check_repo = CheckRunRepository(mock_session)
        assert hasattr(check_repo, "get_by_external_id")
        assert hasattr(check_repo, "get_by_pr_and_check_name")
        assert hasattr(check_repo, "get_all_for_pr")
        assert hasattr(check_repo, "get_failed_checks_for_pr")

        # Test RepositoryRepository methods
        repo_repo = RepositoryRepository(mock_session)
        assert hasattr(repo_repo, "get_by_url")
        assert hasattr(repo_repo, "get_active_repositories")
        assert hasattr(repo_repo, "get_repositories_needing_poll")
        assert hasattr(repo_repo, "update_last_polled")

    async def test_session_transaction_methods(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify repositories properly delegate transaction operations
        What: Tests commit, rollback, flush methods delegate to session
        How: Calls transaction methods and verifies session calls
        """
        repo = BaseRepository(mock_session, Repository)

        # Test commit
        await repo.commit()
        mock_session.commit.assert_called_once()

        # Test rollback
        await repo.rollback()
        mock_session.rollback.assert_called_once()

        # Test flush
        await repo.flush()
        mock_session.flush.assert_called()

    async def test_query_helper_methods(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify query helper methods provide consistent result processing
        What: Tests _execute_query, _execute_single_query, _execute_count_query
        How: Calls helper methods and verifies result processing
        """
        repo = BaseRepository(mock_session, Repository)

        # Test _execute_query
        mock_query = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_entities = [Repository(), Repository()]
        mock_scalars.all.return_value = mock_entities
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo._execute_query(mock_query)
        assert result == mock_entities

        # Test _execute_single_query
        mock_entity = Repository()
        mock_result.scalar_one_or_none.return_value = mock_entity

        single_result = await repo._execute_single_query(mock_query)
        assert single_result == mock_entity

        # Test _execute_count_query
        mock_result.scalar_one.return_value = 42

        count_result = await repo._execute_count_query(mock_query)
        assert count_result == 42

    async def test_error_handling(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify repositories handle common error conditions gracefully
        What: Tests error handling for not found entities and invalid operations
        How: Tests get_by_id_or_raise with non-existent entity
        """
        repo = BaseRepository(mock_session, Repository)

        # Test get_by_id_or_raise with non-existent entity
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Repository with id .* not found"):
            await repo.get_by_id_or_raise(uuid.uuid4())

    def test_repository_inheritance_hierarchy(self) -> None:
        """
        Why: Verify all repositories inherit from BaseRepository correctly
        What: Tests inheritance relationships and method resolution
        How: Checks isinstance and method availability
        """
        mock_session = AsyncMock()

        # All specific repositories should inherit from BaseRepository
        pr_repo = PullRequestRepository(mock_session)
        check_repo = CheckRunRepository(mock_session)
        repo_repo = RepositoryRepository(mock_session)

        assert isinstance(pr_repo, BaseRepository)
        assert isinstance(check_repo, BaseRepository)
        assert isinstance(repo_repo, BaseRepository)

        # All should have base CRUD methods
        for repo in [pr_repo, check_repo, repo_repo]:
            assert hasattr(repo, "create")
            assert hasattr(repo, "get_by_id")
            assert hasattr(repo, "update")
            assert hasattr(repo, "delete")
            assert hasattr(repo, "list_all")
            assert hasattr(repo, "count_all")
            assert hasattr(repo, "exists")

    async def test_bulk_operations_interface(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify repositories provide bulk operation interfaces
        What: Tests that bulk operation methods exist and are callable
        How: Checks method existence and basic functionality
        """
        # Test PullRequestRepository bulk operations
        pr_repo = PullRequestRepository(mock_session)

        # Mock bulk update operation
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        # Test bulk_update_last_checked exists and returns row count
        result = await pr_repo.bulk_update_last_checked([])
        assert result == 0  # Empty list should return 0 without database call

        # Test RepositoryRepository bulk operations
        repo_repo = RepositoryRepository(mock_session)
        assert hasattr(repo_repo, "bulk_update_polling_interval")
        assert hasattr(repo_repo, "bulk_reset_failure_counts")

    def test_repository_type_safety(self) -> None:
        """
        Why: Verify repositories are properly typed for their model classes
        What: Tests that repositories work with correct model types
        How: Checks model_class attributes match expected types
        """
        mock_session = AsyncMock()

        pr_repo = PullRequestRepository(mock_session)
        assert pr_repo.model_class == PullRequest

        check_repo = CheckRunRepository(mock_session)
        assert check_repo.model_class == CheckRun

        repo_repo = RepositoryRepository(mock_session)
        assert repo_repo.model_class == Repository
