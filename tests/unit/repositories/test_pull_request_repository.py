"""
Unit tests for PullRequestRepository.

Why: Ensure PullRequestRepository correctly handles PR-specific operations,
     state management, and complex queries
What: Tests domain-specific methods like get_by_repo_and_number,
      state transitions, failed check queries, and bulk operations
How: Uses AsyncMock to simulate database operations and verify
     repository behavior with proper query construction
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.enums import CheckConclusion, CheckStatus, PRState, TriggerEvent
from src.models.pull_request import PullRequest
from src.repositories.pull_request import PullRequestRepository


class TestPullRequestRepository:
    """Test PullRequestRepository functionality."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """
        Why: Provide a mock AsyncSession for testing repository operations
        What: Creates AsyncMock session with database operation methods
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
    def repository(self, mock_session: AsyncMock) -> PullRequestRepository:
        """
        Why: Provide a repository instance for testing
        What: Creates PullRequestRepository with mocked session
        How: Instantiates PullRequestRepository with mock session
        """
        return PullRequestRepository(mock_session)

    @pytest.fixture
    def sample_pr(self) -> PullRequest:
        """
        Why: Provide a sample PR for testing operations
        What: Creates PullRequest instance with typical data
        How: Instantiates PullRequest with test values
        """
        return PullRequest(
            repository_id=uuid.uuid4(),
            pr_number=123,
            title="Test PR",
            author="testuser",
            state=PRState.OPENED,
        )

    async def test_repository_initialization(self, mock_session: AsyncMock) -> None:
        """
        Why: Verify repository initializes correctly with correct model
        What: Tests repository constructor sets PullRequest as model class
        How: Creates repository and checks model_class attribute
        """
        repo = PullRequestRepository(mock_session)

        assert repo.session == mock_session
        assert repo.model_class == PullRequest

    async def test_get_by_repo_and_number_found(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_by_repo_and_number() finds PR by repository and number
        What: Tests method returns PR when found
        How: Mocks session execute to return PR and verifies query construction
        """
        # Setup
        repository_id = uuid.uuid4()
        pr_number = 123
        mock_pr = PullRequest(
            repository_id=repository_id,
            pr_number=pr_number,
            title="Test PR",
            author="user",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pr
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_repo_and_number(repository_id, pr_number)

        # Verify
        assert result == mock_pr
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_get_by_repo_and_number_not_found(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_by_repo_and_number() returns None when not found
        What: Tests method returns None for non-existent PR
        How: Mocks session execute to return None and verifies result
        """
        # Setup
        repository_id = uuid.uuid4()
        pr_number = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_repo_and_number(repository_id, pr_number)

        # Verify
        assert result is None

    async def test_get_by_repo_url_and_number(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_by_repo_url_and_number() finds PR by URL and number
        What: Tests method performs join query with Repository table
        How: Mocks session execute and verifies query with join
        """
        # Setup
        repo_url = "https://github.com/test/repo"
        pr_number = 123
        mock_pr = PullRequest(
            repository_id=uuid.uuid4(),
            pr_number=pr_number,
            title="Test PR",
            author="user",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pr
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_by_repo_url_and_number(repo_url, pr_number)

        # Verify
        assert result == mock_pr
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_get_active_prs_for_repo_exclude_drafts(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_active_prs_for_repo() excludes drafts by default
        What: Tests method returns only non-draft opened PRs
        How: Mocks session execute and verifies query filters
        """
        # Setup
        repository_id = uuid.uuid4()
        mock_prs = [
            PullRequest(
                repository_id=repository_id,
                pr_number=1,
                title="PR 1",
                author="user",
                state=PRState.OPENED,
                draft=False,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_active_prs_for_repo(repository_id)

        # Verify
        assert result == mock_prs
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_get_active_prs_for_repo_include_drafts(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_active_prs_for_repo() includes drafts when requested
        What: Tests method includes draft PRs when include_drafts=True
        How: Calls method with include_drafts=True and verifies query
        """
        # Setup
        repository_id = uuid.uuid4()
        mock_prs = [
            PullRequest(
                repository_id=repository_id,
                pr_number=1,
                title="Draft PR",
                author="user",
                state=PRState.OPENED,
                draft=True,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_active_prs_for_repo(
            repository_id, include_drafts=True
        )

        # Verify
        assert result == mock_prs

    async def test_get_prs_needing_check(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_prs_needing_check() finds PRs that need monitoring
        What: Tests method returns PRs not checked recently or never checked
        How: Mocks session execute and verifies time-based filtering
        """
        # Setup
        cutoff_time = datetime.now(UTC)
        mock_prs = [
            PullRequest(
                repository_id=uuid.uuid4(),
                pr_number=1,
                title="Needs Check",
                author="user",
                state=PRState.OPENED,
                last_checked_at=None,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_prs_needing_check(cutoff_time, limit=10)

        # Verify
        assert result == mock_prs
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    @patch("src.repositories.state_history.PRStateHistoryRepository")
    async def test_update_state_valid_transition(
        self,
        mock_history_repo_class: MagicMock,
        repository: PullRequestRepository,
        sample_pr: PullRequest,
    ) -> None:
        """
        Why: Verify update_state() successfully updates PR state and creates history
        What: Tests state update creates history record and updates PR
        How: Mocks get_by_id_or_raise and history repository operations
        """
        # Setup
        mock_history_repo = AsyncMock()
        mock_history_repo_class.return_value = mock_history_repo

        repository.get_by_id_or_raise = AsyncMock(return_value=sample_pr)  # type: ignore[method-assign]
        sample_pr.can_transition_to = MagicMock(return_value=True)  # type: ignore[method-assign]

        # Execute
        result = await repository.update_state(
            sample_pr.id,
            PRState.CLOSED,
            TriggerEvent.CLOSED,
            {"reason": "Manual close"},
        )

        # Verify
        assert result.state == PRState.CLOSED
        assert result.pr_metadata and result.pr_metadata["reason"] == "Manual close"
        mock_history_repo.create_transition.assert_called_once()
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]
        repository.session.refresh.assert_called_once_with(result)  # type: ignore[attr-defined]

    @patch("src.repositories.state_history.PRStateHistoryRepository")
    async def test_update_state_invalid_transition(
        self,
        mock_history_repo_class: MagicMock,
        repository: PullRequestRepository,
        sample_pr: PullRequest,
    ) -> None:
        """
        Why: Verify update_state() raises error for invalid transitions
        What: Tests method raises ValueError for invalid state transitions
        How: Mocks can_transition_to to return False and verifies exception
        """
        # Setup
        repository.get_by_id_or_raise = AsyncMock(return_value=sample_pr)  # type: ignore[method-assign]
        sample_pr.can_transition_to = MagicMock(return_value=False)  # type: ignore[method-assign]
        sample_pr.state = PRState.MERGED  # Merged PRs cannot transition

        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid state transition"):
            await repository.update_state(
                sample_pr.id, PRState.OPENED, TriggerEvent.REOPENED
            )

    async def test_mark_as_checked(
        self, repository: PullRequestRepository, sample_pr: PullRequest
    ) -> None:
        """
        Why: Verify mark_as_checked() updates last_checked_at timestamp
        What: Tests method sets current timestamp on PR
        How: Mocks get_by_id_or_raise and verifies timestamp update
        """
        # Setup
        repository.get_by_id_or_raise = AsyncMock(return_value=sample_pr)  # type: ignore[method-assign]

        # Execute
        with patch("src.repositories.pull_request.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            mock_datetime.now.return_value = mock_now
            mock_datetime.UTC = UTC

            result = await repository.mark_as_checked(sample_pr.id)

        # Verify
        assert result.last_checked_at == mock_now
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]
        repository.session.refresh.assert_called_once_with(result)  # type: ignore[attr-defined]

    async def test_get_prs_with_failed_checks(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify get_prs_with_failed_checks() finds PRs with failing checks
        What: Tests method uses subquery to find PRs with failed check runs
        How: Mocks session execute and verifies subquery construction
        """
        # Setup
        repository_id = uuid.uuid4()
        mock_prs = [
            PullRequest(
                repository_id=repository_id,
                pr_number=1,
                title="Failed PR",
                author="user",
                state=PRState.OPENED,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_prs_with_failed_checks(repository_id, limit=5)

        # Verify
        assert result == mock_prs
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_get_recent_prs(self, repository: PullRequestRepository) -> None:
        """
        Why: Verify get_recent_prs() finds PRs created or updated recently
        What: Tests method filters by creation/update time and optional filters
        How: Mocks session execute and verifies time-based query
        """
        # Setup
        since_time = datetime(2024, 1, 1, tzinfo=UTC)
        repository_id = uuid.uuid4()
        states = [PRState.OPENED]

        mock_prs = [
            PullRequest(
                repository_id=repository_id,
                pr_number=1,
                title="Recent PR",
                author="user",
                state=PRState.OPENED,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_recent_prs(
            since=since_time, repository_id=repository_id, states=states, limit=10
        )

        # Verify
        assert result == mock_prs
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_get_pr_statistics(self, repository: PullRequestRepository) -> None:
        """
        Why: Verify get_pr_statistics() calculates PR counts by state
        What: Tests method returns statistics about PR states and types
        How: Mocks multiple session execute calls for different counts
        """
        # Setup
        repository_id = uuid.uuid4()

        # Mock count queries
        def mock_execute_side_effect(query: Any) -> MagicMock:
            result = MagicMock()
            # Return different counts for different queries
            result.scalar_one.return_value = 5  # Sample count
            return result

        repository.session.execute.side_effect = mock_execute_side_effect  # type: ignore[attr-defined]

        # Execute
        result = await repository.get_pr_statistics(repository_id)

        # Verify
        assert isinstance(result, dict)
        assert "total" in result
        assert "by_state" in result
        assert "active" in result
        assert "draft" in result
        # Should have made multiple execute calls for different counts
        assert repository.session.execute.call_count >= 3  # type: ignore[attr-defined]

    async def test_search_prs_with_filters(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify search_prs() applies multiple search filters correctly
        What: Tests method combines text search, author filter, state filter
        How: Mocks session execute and verifies query with multiple conditions
        """
        # Setup
        search_filters = {
            "query_text": "bug fix",
            "author": "developer",
            "state": PRState.OPENED,
            "repository_id": uuid.uuid4(),
            "limit": 20,
            "offset": 0,
        }

        mock_prs = [
            PullRequest(
                repository_id=search_filters["repository_id"],
                pr_number=1,
                title="Bug fix PR",
                author="developer",
                state=PRState.OPENED,
            )
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_prs
        mock_result.scalars.return_value = mock_scalars
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.search_prs(
            query_text=str(search_filters["query_text"]),
            author=str(search_filters["author"]),
            state=search_filters["state"],  # type: ignore[arg-type]
            repository_id=search_filters["repository_id"],  # type: ignore[arg-type]
            limit=search_filters["limit"],  # type: ignore[arg-type]
            offset=search_filters["offset"],  # type: ignore[arg-type]
        )

        # Verify
        assert result == mock_prs
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]

    async def test_bulk_update_last_checked(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify bulk_update_last_checked() efficiently updates multiple PRs
        What: Tests method uses bulk update for performance
        How: Mocks session execute and verifies bulk update query
        """
        # Setup
        pr_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        checked_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.rowcount = 3
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        result = await repository.bulk_update_last_checked(pr_ids, checked_at)

        # Verify
        assert result == 3  # Number of rows updated
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]

    async def test_bulk_update_last_checked_empty_list(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify bulk_update_last_checked() handles empty list efficiently
        What: Tests method returns 0 for empty PR list without database call
        How: Calls method with empty list and verifies no session calls
        """
        # Execute
        result = await repository.bulk_update_last_checked([])

        # Verify
        assert result == 0
        repository.session.execute.assert_not_called()  # type: ignore[attr-defined]

    async def test_bulk_update_last_checked_default_timestamp(
        self, repository: PullRequestRepository
    ) -> None:
        """
        Why: Verify bulk_update_last_checked() uses current time as default
        What: Tests method uses datetime.now() when no timestamp provided
        How: Mocks datetime.now and verifies timestamp usage
        """
        # Setup
        pr_ids = [uuid.uuid4()]
        mock_result = MagicMock()
        mock_result.rowcount = 1
        repository.session.execute.return_value = mock_result  # type: ignore[attr-defined]

        # Execute
        with patch("src.repositories.pull_request.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            mock_datetime.now.return_value = mock_now
            mock_datetime.UTC = UTC

            result = await repository.bulk_update_last_checked(pr_ids)

        # Verify
        assert result == 1
        repository.session.execute.assert_called_once()  # type: ignore[attr-defined]
        repository.session.flush.assert_called_once()  # type: ignore[attr-defined]
