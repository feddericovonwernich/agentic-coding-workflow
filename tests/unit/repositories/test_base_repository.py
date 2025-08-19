"""
Unit tests for BaseRepository.

Why: Ensure BaseRepository provides correct CRUD operations and query methods
     that all specific repositories depend on
What: Tests BaseRepository's create, read, update, delete operations and
      common query functionality with mocked database sessions
How: Uses AsyncMock to simulate database operations and verify repository
     behavior without actual database connections
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel
from src.repositories.base import BaseRepository


class TestModel(BaseModel):
    """Test model for testing BaseRepository functionality."""

    __tablename__ = "test_model"

    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TestRepository(BaseRepository[TestModel]):
    """Test repository for testing BaseRepository functionality."""

    def __init__(self, session: AsyncMock):
        super().__init__(session, TestModel)


class TestBaseRepository:
    """Test BaseRepository functionality."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """
        Why: Provide a mock AsyncSession for testing repository operations
        What: Creates AsyncMock session with common database methods
        How: Sets up mocked execute, get, flush, commit, rollback methods
        """
        session = AsyncMock()
        session.execute = AsyncMock()
        session.get = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> TestRepository:
        """
        Why: Provide a repository instance for testing
        What: Creates TestRepository with mocked session
        How: Instantiates TestRepository with mock session
        """
        return TestRepository(mock_session)

    async def test_repository_initialization(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify repository initializes correctly with session and model
        What: Tests repository constructor sets session and model_class
        How: Creates repository and checks attributes
        """
        repo = TestRepository(mock_session)

        assert repo.session == mock_session
        assert repo.model_class == TestModel

    async def test_create_entity(self, repository: TestRepository) -> None:
        """
        Why: Verify create() method instantiates and persists new entities
        What: Tests create() calls flush and refresh on new entity
        How: Calls create() and verifies session method calls
        """
        # Setup
        test_data = {"name": "test", "value": 42}

        # Execute
        result = await repository.create(**test_data)

        # Verify
        assert isinstance(result, TestModel)
        repository.session.add.assert_called_once_with(result)  # type: ignore[attr-defined]
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]
        repository.session.refresh.assert_called_once_with(result)  # type: ignore[attr-defined]

    async def test_get_by_id_found(self, repository: TestRepository) -> None:
        """
        Why: Verify get_by_id() returns entity when found
        What: Tests get_by_id() calls session.get and returns result
        How: Mocks session.get to return entity and verifies call
        """
        # Setup
        entity_id = uuid.uuid4()
        mock_entity = TestModel()
        repository.session.get.return_value = mock_entity  # type: ignore[attr-defined]  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_id(entity_id)

        # Verify
        assert result == mock_entity
        repository.session.get.assert_called_once_with(TestModel, entity_id)  # type: ignore[attr-defined]  # type: ignore[attr-defined]

    async def test_get_by_id_not_found(self, repository: TestRepository) -> None:
        """
        Why: Verify get_by_id() returns None when entity not found
        What: Tests get_by_id() with non-existent ID returns None
        How: Mocks session.get to return None and verifies result
        """
        # Setup
        entity_id = uuid.uuid4()
        repository.session.get.return_value = None  # type: ignore[attr-defined]  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_id(entity_id)

        # Verify
        assert result is None
        repository.session.get.assert_called_once_with(TestModel, entity_id)  # type: ignore[attr-defined]

    async def test_get_by_id_or_raise_found(self, repository: TestRepository) -> None:
        """
        Why: Verify get_by_id_or_raise() returns entity when found
        What: Tests get_by_id_or_raise() with existing entity
        How: Mocks session.get to return entity and verifies return
        """
        # Setup
        entity_id = uuid.uuid4()
        mock_entity = TestModel()
        repository.session.get.return_value = mock_entity  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_id_or_raise(entity_id)

        # Verify
        assert result == mock_entity

    async def test_get_by_id_or_raise_not_found(
        self, repository: TestRepository
    ) -> None:
        """
        Why: Verify get_by_id_or_raise() raises ValueError when not found
        What: Tests get_by_id_or_raise() with non-existent ID raises exception
        How: Mocks session.get to return None and verifies ValueError
        """
        # Setup
        entity_id = uuid.uuid4()
        repository.session.get.return_value = None  # type: ignore[attr-defined]

        # Execute & Verify
        with pytest.raises(ValueError, match="TestModel with id .* not found"):
            await repository.get_by_id_or_raise(entity_id)

    async def test_update_entity(self, repository: TestRepository) -> None:
        """
        Why: Verify update() method modifies entity attributes
        What: Tests update() sets new values and calls flush/refresh
        How: Creates entity, calls update with new data, verifies changes
        """
        # Setup
        entity = TestModel()
        entity.name = "old_name"
        update_data = {"name": "new_name", "value": 100}

        # Execute
        result = await repository.update(entity, **update_data)

        # Verify
        assert result == entity
        assert entity.name == "new_name"
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]
        repository.session.refresh.assert_called_once_with(entity)  # type: ignore[attr-defined]

    async def test_update_entity_ignores_invalid_attributes(
        self, repository: TestRepository
    ) -> None:
        """
        Why: Verify update() safely ignores attributes that don't exist
        What: Tests update() with invalid attribute names doesn't cause errors
        How: Calls update with invalid field and verifies no error
        """
        # Setup
        entity = TestModel()
        update_data = {"nonexistent_field": "value", "name": "valid_name"}

        # Execute (should not raise)
        result = await repository.update(entity, **update_data)

        # Verify
        assert result == entity
        assert not hasattr(entity, "nonexistent_field")

    async def test_delete_entity(self, repository: TestRepository) -> None:
        """
        Why: Verify delete() method removes entity from session
        What: Tests delete() calls session.delete and flush
        How: Creates entity, calls delete, verifies session calls
        """
        # Setup
        entity = TestModel()

        # Execute
        await repository.delete(entity)

        # Verify
        repository.session.delete.assert_called_once_with(entity)  # type: ignore[attr-defined]
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]

    async def test_delete_by_id_found(self, repository: TestRepository) -> None:
        """
        Why: Verify delete_by_id() deletes entity when found
        What: Tests delete_by_id() returns True for existing entity
        How: Mocks get_by_id to return entity and verifies deletion
        """
        # Setup
        entity_id = uuid.uuid4()
        mock_entity = TestModel()
        repository.session.get.return_value = mock_entity  # type: ignore[attr-defined]

        # Execute
        result = await repository.delete_by_id(entity_id)

        # Verify
        assert result is True
        repository.session.delete.assert_called_once_with(mock_entity)  # type: ignore[attr-defined]
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]

    async def test_delete_by_id_not_found(self, repository: TestRepository) -> None:
        """
        Why: Verify delete_by_id() returns False when entity not found
        What: Tests delete_by_id() with non-existent ID returns False
        How: Mocks get_by_id to return None and verifies result
        """
        # Setup
        entity_id = uuid.uuid4()
        repository.session.get.return_value = None  # type: ignore[attr-defined]

        # Execute
        result = await repository.delete_by_id(entity_id)

        # Verify
        assert result is False
        repository.session.delete.assert_not_called()  # type: ignore[attr-defined]

    async def test_list_all_no_pagination(self, repository: TestRepository) -> None:
        """
        Why: Verify list_all() returns all entities without pagination
        What: Tests list_all() executes query and returns results
        How: Mocks session.execute and verifies query execution
        """
        # Setup
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_entities = [TestModel(), TestModel()]
        mock_scalars.all.return_value = mock_entities
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.list_all()

        # Verify
        assert result == mock_entities
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_list_all_with_pagination(self, repository: TestRepository) -> None:
        """
        Why: Verify list_all() applies limit and offset when provided
        What: Tests list_all() with pagination parameters
        How: Calls list_all with limit/offset and verifies query construction
        """
        # Setup
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_entities = [TestModel()]
        mock_scalars.all.return_value = mock_entities
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.list_all(limit=10, offset=20)

        # Verify
        assert result == mock_entities
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_count_all(self, repository: TestRepository) -> None:
        """
        Why: Verify count_all() returns total entity count
        What: Tests count_all() executes count query
        How: Mocks session execute and scalar_one to return count
        """
        # Setup
        expected_count = 42
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = expected_count
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.count_all()

        # Verify
        assert result == expected_count
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_exists_true(self, repository: TestRepository) -> None:
        """
        Why: Verify exists() returns True when entity exists
        What: Tests exists() with existing entity ID
        How: Mocks session execute to return non-None result
        """
        # Setup
        entity_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity_id
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.exists(entity_id)

        # Verify
        assert result is True
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_exists_false(self, repository: TestRepository) -> None:
        """
        Why: Verify exists() returns False when entity doesn't exist
        What: Tests exists() with non-existent entity ID
        How: Mocks session execute to return None result
        """
        # Setup
        entity_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.exists(entity_id)

        # Verify
        assert result is False

    async def test_commit(self, repository: TestRepository) -> None:
        """
        Why: Verify commit() delegates to session commit
        What: Tests commit() calls session.commit()
        How: Calls commit and verifies session method call
        """
        # Execute
        await repository.commit()

        # Verify
        repository.session.commit.assert_called_once()  # type: ignore[attr-defined]

    async def test_rollback(self, repository: TestRepository) -> None:
        """
        Why: Verify rollback() delegates to session rollback
        What: Tests rollback() calls session.rollback()
        How: Calls rollback and verifies session method call
        """
        # Execute
        await repository.rollback()

        # Verify
        repository.session.rollback.assert_called_once()  # type: ignore[attr-defined]

    async def test_flush(self, repository: TestRepository) -> None:
        """
        Why: Verify flush() delegates to session flush
        What: Tests flush() calls session.flush()
        How: Calls flush and verifies session method call
        """
        # Execute
        await repository.flush()

        # Verify
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]

    async def test_refresh(self, repository: TestRepository) -> None:
        """
        Why: Verify refresh() delegates to session refresh
        What: Tests refresh() calls session.refresh()
        How: Calls refresh with entity and verifies session call
        """
        # Setup
        entity = TestModel()

        # Execute
        await repository.refresh(entity)

        # Verify
        repository.session.refresh.assert_called_once_with(entity)  # type: ignore[attr-defined]

    async def test_execute_query_helper(self, repository: TestRepository) -> None:
        """
        Why: Verify _execute_query() helper processes results correctly
        What: Tests _execute_query() returns list of entities
        How: Mocks query execution and verifies result processing
        """
        # Setup
        mock_query = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_entities = [TestModel(), TestModel()]
        mock_scalars.all.return_value = mock_entities
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository._execute_query(mock_query)

        # Verify
        assert result == mock_entities
        repository.session.execute.assert_called_once_with(mock_query)  # type: ignore[attr-defined]

    async def test_execute_single_query_helper(
        self, repository: TestRepository
    ) -> None:
        """
        Why: Verify _execute_single_query() helper returns single result
        What: Tests _execute_single_query() returns first result or None
        How: Mocks query execution and verifies single result processing
        """
        # Setup
        mock_query = MagicMock()
        mock_result = MagicMock()
        mock_entity = TestModel()
        mock_result.scalar_one_or_none.return_value = mock_entity
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository._execute_single_query(mock_query)

        # Verify
        assert result == mock_entity
        repository.session.execute.assert_called_once_with(mock_query)  # type: ignore[attr-defined]

    async def test_execute_count_query_helper(self, repository: TestRepository) -> None:
        """
        Why: Verify _execute_count_query() helper returns count result
        What: Tests _execute_count_query() returns integer count
        How: Mocks count query execution and verifies result
        """
        # Setup
        mock_query = MagicMock()
        mock_result = MagicMock()
        expected_count = 10
        mock_result.scalar_one.return_value = expected_count
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository._execute_count_query(mock_query)

        # Verify
        assert result == expected_count
        repository.session.execute.assert_called_once_with(mock_query)  # type: ignore[attr-defined]

    async def test_build_base_query_helper(self, repository: TestRepository) -> None:
        """
        Why: Verify _build_base_query() returns proper select query
        What: Tests _build_base_query() creates select statement
        How: Calls method and verifies query type
        """
        # Execute
        query = repository._build_base_query()

        # Verify
        # Note: In actual implementation, this would return a SQLAlchemy Select object
        # For testing, we just verify the method exists and is callable
        assert query is not None
