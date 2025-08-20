"""
Unit tests for GitHub pagination module.

Why: Ensure pagination works correctly for large GitHub API responses
     and handles Link headers properly for efficient data fetching.

What: Tests LinkHeader parsing, PaginatedResponse, and AsyncPaginator
      for proper pagination handling and iterator functionality.

How: Uses mock responses with Link headers to test pagination logic
     without making real API calls.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from src.github.pagination import AsyncPaginator, LinkHeader, PaginatedResponse


class TestLinkHeader:
    """Test LinkHeader parsing."""

    def test_link_header_empty(self) -> None:
        """
        Why: Ensure LinkHeader handles missing or empty Link headers gracefully
             when GitHub API responses don't include pagination links.
        What: Tests LinkHeader with empty or None header.
        How: Creates LinkHeader with None and validates empty state.
        """
        link_header = LinkHeader(None)
        assert link_header.links == {}
        assert not link_header.has_next
        assert not link_header.has_prev

    def test_link_header_single_link(self) -> None:
        """
        Why: Verify LinkHeader correctly parses single pagination link
             (typically 'next' for first page of results).
        What: Tests LinkHeader with single link.
        How: Provides single link header and validates URL extraction.
        """
        header_value = (
            '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"'
        )
        link_header = LinkHeader(header_value)

        assert (
            link_header.next_url
            == "https://api.github.com/repos/owner/repo/pulls?page=2"
        )
        assert link_header.has_next
        assert not link_header.has_prev

    def test_link_header_multiple_links(self) -> None:
        """
        Why: Ensure LinkHeader parses complex Link headers with multiple
             pagination relationships (next, prev, first, last).
        What: Tests LinkHeader with multiple links.
        How: Provides multi-link header and validates all URLs are parsed.
        """
        header_value = (
            '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next", '
            '<https://api.github.com/repos/owner/repo/pulls?page=1>; rel="prev", '
            '<https://api.github.com/repos/owner/repo/pulls?page=1>; rel="first", '
            '<https://api.github.com/repos/owner/repo/pulls?page=10>; rel="last"'
        )
        link_header = LinkHeader(header_value)

        assert (
            link_header.next_url
            == "https://api.github.com/repos/owner/repo/pulls?page=2"
        )
        assert (
            link_header.prev_url
            == "https://api.github.com/repos/owner/repo/pulls?page=1"
        )
        assert (
            link_header.first_url
            == "https://api.github.com/repos/owner/repo/pulls?page=1"
        )
        assert (
            link_header.last_url
            == "https://api.github.com/repos/owner/repo/pulls?page=10"
        )
        assert link_header.has_next
        assert link_header.has_prev

    def test_link_header_malformed(self) -> None:
        """Test LinkHeader with malformed header."""
        header_value = "malformed link header"
        link_header = LinkHeader(header_value)

        assert link_header.links == {}
        assert not link_header.has_next

    def test_get_last_page_number(self) -> None:
        """Test extracting last page number."""
        header_value = (
            '<https://api.github.com/repos/owner/repo/pulls?page=10>; rel="last"'
        )
        link_header = LinkHeader(header_value)

        assert link_header.get_last_page_number() == 10

    def test_get_last_page_number_no_last(self) -> None:
        """Test getting last page number when no last link."""
        header_value = (
            '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"'
        )
        link_header = LinkHeader(header_value)

        assert link_header.get_last_page_number() is None

    def test_get_last_page_number_invalid(self) -> None:
        """Test getting last page number with invalid URL."""
        header_value = (
            '<https://api.github.com/repos/owner/repo/pulls?invalid=url>; rel="last"'
        )
        link_header = LinkHeader(header_value)

        assert link_header.get_last_page_number() is None


class TestPaginatedResponse:
    """Test PaginatedResponse wrapper."""

    def test_paginated_response_creation(self) -> None:
        """Test PaginatedResponse creation."""
        data = [{"id": 1}, {"id": 2}]
        headers = {
            "Link": '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"'
        }
        url = "https://api.github.com/repos/owner/repo/pulls?page=1"

        response = PaginatedResponse(data, headers, url)

        assert response.data == data
        assert response.headers == headers
        assert response.url == url
        assert response.items == data

    def test_paginated_response_has_next_page(self) -> None:
        """Test has_next_page property."""
        headers_with_next = {
            "Link": '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"'
        }
        headers_without_next: dict[str, str] = {}

        response_with_next = PaginatedResponse([], headers_with_next, "")
        response_without_next = PaginatedResponse([], headers_without_next, "")

        assert response_with_next.has_next_page
        assert not response_without_next.has_next_page

    def test_paginated_response_next_page_url(self) -> None:
        """Test next_page_url property."""
        headers = {
            "Link": '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"'
        }
        response = PaginatedResponse([], headers, "")

        assert (
            response.next_page_url
            == "https://api.github.com/repos/owner/repo/pulls?page=2"
        )

    def test_paginated_response_total_pages(self) -> None:
        """Test total_pages property."""
        headers = {
            "Link": (
                '<https://api.github.com/repos/owner/repo/pulls?page=10>; rel="last"'
            )
        }
        response = PaginatedResponse([], headers, "")

        assert response.total_pages == 10


class TestAsyncPaginator:
    """Test AsyncPaginator iterator."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock GitHub client."""
        client = Mock()
        client._fetch_paginated = AsyncMock()
        return client

    def test_async_paginator_creation(self, mock_client: Mock) -> None:
        """
        Why: Ensure AsyncPaginator initializes with proper configuration
             for efficient pagination through large datasets.
        What: Tests AsyncPaginator creation.
        How: Creates paginator with parameters and validates configuration.
        """
        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/repos/owner/repo/pulls",
            params={"state": "open"},
            max_pages=5,
            per_page=50,
        )

        assert paginator.client == mock_client
        assert paginator.initial_url == "https://api.github.com/repos/owner/repo/pulls"
        assert paginator.params["state"] == "open"
        assert paginator.params["per_page"] == 50
        assert paginator.max_pages == 5
        assert paginator.per_page == 50

    def test_async_paginator_per_page_limit(self, mock_client: Mock) -> None:
        """Test AsyncPaginator per_page limit enforcement."""
        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
            per_page=150,  # Above GitHub's limit of 100
        )

        assert paginator.per_page == 100  # Should be capped at 100

    @pytest.mark.asyncio
    async def test_async_paginator_single_page(self, mock_client: Mock) -> None:
        """Test AsyncPaginator with single page response."""
        # Mock response with no next page
        mock_response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            headers={},  # No Link header
            url="https://api.github.com/test",
        )
        mock_client._fetch_paginated.return_value = mock_response

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
        )

        items = []
        async for item in paginator:
            items.append(item)

        assert len(items) == 2
        assert items[0]["id"] == 1
        assert items[1]["id"] == 2
        assert mock_client._fetch_paginated.call_count == 1

    @pytest.mark.asyncio
    async def test_async_paginator_multiple_pages(self, mock_client: Mock) -> None:
        """Test AsyncPaginator with multiple pages."""
        # First page response
        first_response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            headers={"Link": '<https://api.github.com/test?page=2>; rel="next"'},
            url="https://api.github.com/test",
        )

        # Second page response (last page)
        second_response = PaginatedResponse(
            data=[{"id": 3}, {"id": 4}],
            headers={},  # No next link
            url="https://api.github.com/test?page=2",
        )

        mock_client._fetch_paginated.side_effect = [first_response, second_response]

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
        )

        items = []
        async for item in paginator:
            items.append(item)

        assert len(items) == 4
        assert [item["id"] for item in items] == [1, 2, 3, 4]
        assert mock_client._fetch_paginated.call_count == 2

    @pytest.mark.asyncio
    async def test_async_paginator_max_pages_limit(self, mock_client: Mock) -> None:
        """Test AsyncPaginator with max_pages limit."""
        # Mock response that always has next page
        mock_response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            headers={"Link": '<https://api.github.com/test?page=2>; rel="next"'},
            url="https://api.github.com/test",
        )
        mock_client._fetch_paginated.return_value = mock_response

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
            max_pages=2,  # Limit to 2 pages
        )

        items = []
        async for item in paginator:
            items.append(item)

        # Should only fetch 2 pages worth of items
        assert len(items) == 4  # 2 items per page x 2 pages
        assert mock_client._fetch_paginated.call_count == 2

    @pytest.mark.asyncio
    async def test_async_paginator_collect_all(self, mock_client: Mock) -> None:
        """Test collecting all items at once."""
        mock_response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            headers={},
            url="https://api.github.com/test",
        )
        mock_client._fetch_paginated.return_value = mock_response

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
        )

        items = await paginator.collect_all()

        assert len(items) == 2
        assert items[0]["id"] == 1
        assert items[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_async_paginator_collect_pages(self, mock_client: Mock) -> None:
        """Test collecting specific number of pages."""
        # Mock response that always has next page
        mock_response = PaginatedResponse(
            data=[{"id": 1}, {"id": 2}],
            headers={"Link": '<https://api.github.com/test?page=2>; rel="next"'},
            url="https://api.github.com/test",
        )
        mock_client._fetch_paginated.return_value = mock_response

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
            per_page=2,
        )

        items = await paginator.collect_pages(2)

        # Should collect exactly 2 pages worth of items
        assert len(items) == 4  # 2 items per page x 2 pages
        assert mock_client._fetch_paginated.call_count == 2

    @pytest.mark.asyncio
    async def test_async_paginator_empty_response(self, mock_client: Mock) -> None:
        """Test AsyncPaginator with empty response."""
        mock_response = PaginatedResponse(
            data=[],
            headers={},
            url="https://api.github.com/test",
        )
        mock_client._fetch_paginated.return_value = mock_response

        paginator = AsyncPaginator(
            client=mock_client,
            initial_url="https://api.github.com/test",
        )

        items = []
        async for item in paginator:
            items.append(item)

        assert len(items) == 0
        assert mock_client._fetch_paginated.call_count == 1
