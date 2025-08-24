"""
Unit tests for MockAsyncPaginator class.

This module provides comprehensive tests for the MockAsyncPaginator implementation,
covering async iteration, pagination parameters, and edge cases.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class MockAsyncPaginator:
    """Mock implementation for testing - will be imported from github_mock_server.py."""

    def __init__(
        self,
        client: Any,
        endpoint: str,
        params: dict[str, Any],
        per_page: int = 30,
        max_pages: int = 10,
    ) -> None:
        """Initialize paginator with client and parameters."""
        self.client = client
        self.endpoint = endpoint
        self.params = params.copy()
        self.per_page = per_page
        self.max_pages = max_pages
        self.current_page = 1
        self.current_items: list[dict[str, Any]] = []
        self.current_index = 0

    def __aiter__(self) -> "MockAsyncPaginator":
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Get next item from paginated results."""
        # If we have items in current page, yield them
        if self.current_index < len(self.current_items):
            item = self.current_items[self.current_index]
            self.current_index += 1
            return item

        # Check if we've reached max pages
        if self.current_page > self.max_pages:
            raise StopAsyncIteration

        # Fetch next page
        params = self.params.copy()
        params["page"] = self.current_page
        params["per_page"] = self.per_page

        response = await self.client.get(self.endpoint, params=params)
        response.raise_for_status()

        items = response.json()

        # If no items, stop iteration
        if not items:
            raise StopAsyncIteration

        # Store items and reset index
        self.current_items = items
        self.current_index = 0
        self.current_page += 1

        # Return first item from new page
        if self.current_items:
            item = self.current_items[self.current_index]
            self.current_index += 1
            return item
        else:
            raise StopAsyncIteration


class TestMockAsyncPaginator:
    """Test suite for MockAsyncPaginator class."""

    async def test_basic_iteration(self) -> None:
        """
        Why: Ensure paginator correctly iterates over multiple pages of data
        What: Async iteration functionality with multiple pages
        How: Mock client with 3 pages of data, verify all items are yielded
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        # Setup 3 pages of mock data
        page_data = {
            1: [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}],
            2: [{"id": 3, "name": "item3"}, {"id": 4, "name": "item4"}],
            3: [{"id": 5, "name": "item5"}],
            4: [],  # Empty page to signal end
        }

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            mock_response.json = MagicMock(return_value=page_data.get(page, []))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {"state": "open"})
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 5
        assert collected_items[0] == {"id": 1, "name": "item1"}
        assert collected_items[4] == {"id": 5, "name": "item5"}
        assert mock_client.get.call_count == 4  # 3 pages with data + 1 empty

    async def test_per_page_limit(self) -> None:
        """
        Why: Verify per_page parameter correctly controls items per request
        What: Pagination with custom per_page value
        How: Set per_page=5, verify requests use correct parameter
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        # Return 5 items per page
        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            params = kwargs.get("params", {})
            per_page = params.get("per_page", 30)
            page = params.get("page", 1)

            if page == 1:
                items = [{"id": i} for i in range(1, min(6, per_page + 1))]
            else:
                items = []

            mock_response.json = MagicMock(return_value=items)
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(
            mock_client, "/test/endpoint", {"state": "open"}, per_page=5
        )
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 5

        # Verify per_page was passed correctly
        call_args = mock_client.get.call_args_list[0]
        assert call_args[1]["params"]["per_page"] == 5

    async def test_max_pages_limit(self) -> None:
        """
        Why: Ensure max_pages parameter prevents infinite pagination
        What: Pagination stops after max_pages limit
        How: Set max_pages=2, provide 5 pages of data, verify only 2 pages fetched
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        # Setup unlimited pages of mock data
        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            # Always return data to simulate many pages
            items = [{"id": page * 10 + i} for i in range(3)]
            mock_response.json = MagicMock(return_value=items)
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(
            mock_client, "/test/endpoint", {"state": "open"}, per_page=3, max_pages=2
        )
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert - should only get 2 pages worth of data
        assert len(collected_items) == 6  # 2 pages * 3 items per page
        assert mock_client.get.call_count == 2

    async def test_empty_response(self) -> None:
        """
        Why: Handle empty result sets gracefully without errors
        What: Paginator behavior with no data
        How: Mock client returns empty list immediately
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[])
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {"state": "open"})
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 0
        assert mock_client.get.call_count == 1

    async def test_single_page_response(self) -> None:
        """
        Why: Verify correct handling when all data fits in one page
        What: Single page pagination scenario
        How: Return data in first page, empty in second
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        page_data = {
            1: [{"id": 1}, {"id": 2}, {"id": 3}],
            2: [],  # Empty second page
        }

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            mock_response.json = MagicMock(return_value=page_data.get(page, []))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {"state": "open"})
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 3
        assert collected_items == [{"id": 1}, {"id": 2}, {"id": 3}]
        assert mock_client.get.call_count == 2  # First page + empty second page

    async def test_large_dataset_iteration(self) -> None:
        """
        Why: Ensure paginator handles large datasets efficiently
        What: Iteration over multiple pages with many items
        How: Simulate 10 pages with 30 items each
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            if page <= 10:
                items = [{"id": (page - 1) * 30 + i, "page": page} for i in range(30)]
            else:
                items = []
            mock_response.json = MagicMock(return_value=items)
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(
            mock_client,
            "/test/endpoint",
            {"state": "open"},
            per_page=30,
            max_pages=15,  # Set higher than available pages
        )
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 300  # 10 pages * 30 items
        assert collected_items[0]["id"] == 0
        assert collected_items[299]["id"] == 299
        assert mock_client.get.call_count == 11  # 10 pages with data + 1 empty

    async def test_stop_iteration(self) -> None:
        """
        Why: Verify StopAsyncIteration is raised correctly at end of data
        What: Proper async iteration termination
        How: Manually call __anext__ after data exhausted
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        # Single page of data
        page_data = {1: [{"id": 1}], 2: []}

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            mock_response.json = MagicMock(return_value=page_data.get(page, []))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {})

        # Get first item
        item1 = await paginator.__anext__()
        assert item1 == {"id": 1}

        # Should raise StopAsyncIteration on next call after exhausting data
        with pytest.raises(StopAsyncIteration):
            await paginator.__anext__()

    async def test_exact_page_boundary(self) -> None:
        """
        Why: Test edge case where items exactly fill page boundaries
        What: Pagination with exact multiples of per_page
        How: Provide exactly 2 pages worth of data with per_page=10
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        page_data = {
            1: [{"id": i} for i in range(1, 11)],  # Exactly 10 items
            2: [{"id": i} for i in range(11, 21)],  # Exactly 10 items
            3: [],  # Empty to signal end
        }

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            mock_response.json = MagicMock(return_value=page_data.get(page, []))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {}, per_page=10)
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 20  # Exactly 2 full pages
        assert collected_items[0]["id"] == 1
        assert collected_items[9]["id"] == 10
        assert collected_items[10]["id"] == 11
        assert collected_items[19]["id"] == 20

    async def test_one_item_response(self) -> None:
        """
        Why: Handle edge case of single item in response
        What: Pagination with minimal data
        How: Return only one item total
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        page_data = {1: [{"id": 1, "single": True}], 2: []}

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            page = kwargs.get("params", {}).get("page", 1)
            mock_response.json = MagicMock(return_value=page_data.get(page, []))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {})
        collected_items = []

        async for item in paginator:
            collected_items.append(item)

        # Assert
        assert len(collected_items) == 1
        assert collected_items[0] == {"id": 1, "single": True}

    async def test_params_preserved(self) -> None:
        """
        Why: Ensure original query parameters are preserved during pagination
        What: Parameter passing through pagination
        How: Verify initial params are included in all requests
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[])
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        initial_params = {"state": "open", "sort": "created", "direction": "desc"}

        # Act
        paginator = MockAsyncPaginator(
            mock_client, "/test/endpoint", initial_params, per_page=5
        )

        # Trigger one iteration to make a request
        async for _ in paginator:
            pass

        # Assert
        call_args = mock_client.get.call_args_list[0]
        params = call_args[1]["params"]

        assert params["state"] == "open"
        assert params["sort"] == "created"
        assert params["direction"] == "desc"
        assert params["page"] == 1
        assert params["per_page"] == 5

    async def test_http_error_handling(self) -> None:
        """
        Why: Ensure HTTP errors are properly propagated
        What: Error handling during pagination
        How: Mock client raises HTTP error
        """
        # Arrange
        mock_client = AsyncMock()
        mock_response = MagicMock()

        # Make raise_for_status actually raise an exception
        from httpx import HTTPStatusError, Request, Response

        http_response = Response(404, request=Request("GET", "http://test.com"))
        mock_response.raise_for_status = MagicMock(
            side_effect=HTTPStatusError(
                "Not Found", request=http_response.request, response=http_response
            )
        )
        mock_response.json = MagicMock(return_value=[])
        mock_client.get = AsyncMock(return_value=mock_response)

        # Act & Assert
        paginator = MockAsyncPaginator(mock_client, "/test/endpoint", {})

        with pytest.raises(HTTPStatusError) as exc_info:
            async for _ in paginator:
                pass

        assert "Not Found" in str(exc_info.value)

    async def test_concurrent_iteration_isolation(self) -> None:
        """
        Why: Ensure multiple paginator instances don't interfere with each other
        What: Isolation between paginator instances
        How: Create two paginators with different parameters
        """
        # Arrange
        mock_client = AsyncMock()

        def get_page(*args: Any, **kwargs: Any) -> MagicMock:
            mock_response = MagicMock()
            params = kwargs.get("params", {})
            endpoint = args[0]

            if "endpoint1" in endpoint:
                items = [{"source": "endpoint1", "page": params.get("page", 1)}]
            else:
                items = [{"source": "endpoint2", "page": params.get("page", 1)}]

            if params.get("page", 1) > 1:
                items = []

            mock_response.json = MagicMock(return_value=items)
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_client.get = AsyncMock(side_effect=get_page)

        # Act
        paginator1 = MockAsyncPaginator(mock_client, "/endpoint1", {"filter": "A"})
        paginator2 = MockAsyncPaginator(mock_client, "/endpoint2", {"filter": "B"})

        items1 = []
        items2 = []

        async for item in paginator1:
            items1.append(item)

        async for item in paginator2:
            items2.append(item)

        # Assert
        assert len(items1) == 1
        assert items1[0]["source"] == "endpoint1"

        assert len(items2) == 1
        assert items2[0]["source"] == "endpoint2"
