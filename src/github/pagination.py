"""GitHub API pagination utilities."""

import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlparse


class LinkHeader:
    """Parser for GitHub Link headers."""

    def __init__(self, link_header: str | None = None):
        """Initialize Link header parser.

        Args:
            link_header: Raw Link header value from response
        """
        self.links: dict[str, str] = {}
        if link_header:
            self._parse(link_header)

    def _parse(self, link_header: str) -> None:
        """Parse Link header into dictionary of rel -> url.

        Args:
            link_header: Raw Link header value
        """
        # Link header format: <url>; rel="next", <url>; rel="last"
        link_pattern = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')

        for match in link_pattern.finditer(link_header):
            url, rel = match.groups()
            self.links[rel] = url

    @property
    def next_url(self) -> str | None:
        """Get URL for next page."""
        return self.links.get("next")

    @property
    def prev_url(self) -> str | None:
        """Get URL for previous page."""
        return self.links.get("prev")

    @property
    def first_url(self) -> str | None:
        """Get URL for first page."""
        return self.links.get("first")

    @property
    def last_url(self) -> str | None:
        """Get URL for last page."""
        return self.links.get("last")

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return "next" in self.links

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return "prev" in self.links

    def get_last_page_number(self) -> int | None:
        """Extract last page number from last URL."""
        if not self.last_url:
            return None

        try:
            parsed = urlparse(self.last_url)
            params = parse_qs(parsed.query)
            page = params.get("page", [None])[0]
            return int(page) if page else None
        except (ValueError, TypeError):
            return None


class PaginatedResponse:
    """Wrapper for paginated GitHub API responses."""

    def __init__(
        self,
        data: list[dict[str, Any]],
        headers: dict[str, str],
        url: str,
    ):
        """Initialize paginated response.

        Args:
            data: Response data
            headers: Response headers
            url: Request URL
        """
        self.data = data
        self.headers = headers
        self.url = url
        self.link_header = LinkHeader(headers.get("Link"))

    @property
    def has_next_page(self) -> bool:
        """Check if there's a next page."""
        return self.link_header.has_next

    @property
    def next_page_url(self) -> str | None:
        """Get URL for next page."""
        return self.link_header.next_url

    @property
    def total_pages(self) -> int | None:
        """Get total number of pages."""
        return self.link_header.get_last_page_number()

    @property
    def items(self) -> list[dict[str, Any]]:
        """Get items from current page."""
        return self.data


class AsyncPaginator:
    """Async iterator for paginated GitHub API responses."""

    def __init__(
        self,
        client: Any,  # Avoid circular import
        initial_url: str,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
        per_page: int = 100,
    ):
        """Initialize async paginator.

        Args:
            client: GitHub client instance
            initial_url: Initial URL to fetch
            params: Query parameters
            max_pages: Maximum number of pages to fetch
            per_page: Items per page (max 100 for GitHub)
        """
        self.client = client
        self.initial_url = initial_url
        self.params = params or {}
        self.max_pages = max_pages
        self.per_page = min(per_page, 100)  # GitHub max is 100

        # Add per_page to params
        self.params["per_page"] = self.per_page

        self._current_page = 0
        self._next_url: str | None = initial_url
        self._exhausted = False

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator implementation."""
        while not self._exhausted and self._next_url:
            # Check max pages limit
            if self.max_pages and self._current_page >= self.max_pages:
                break

            # Fetch next page
            response = await self._fetch_page(self._next_url)
            self._current_page += 1

            # Update next URL from Link header
            if response.has_next_page:
                self._next_url = response.next_page_url
            else:
                self._exhausted = True
                self._next_url = None

            # Yield items from current page
            for item in response.items:
                yield item

    async def _fetch_page(self, url: str) -> PaginatedResponse:
        """Fetch a single page.

        Args:
            url: URL to fetch

        Returns:
            PaginatedResponse with data and headers
        """
        # This will be implemented by the client
        # to avoid circular dependency
        result: PaginatedResponse = await self.client._fetch_paginated(url, self.params)
        return result

    async def collect_all(self) -> list[dict[str, Any]]:
        """Collect all items from all pages.

        Returns:
            List of all items
        """
        items = []
        async for item in self:
            items.append(item)
        return items

    async def collect_pages(self, num_pages: int) -> list[dict[str, Any]]:
        """Collect items from specified number of pages.

        Args:
            num_pages: Number of pages to collect

        Returns:
            List of items from the pages
        """
        items = []
        page_count = 0

        async for item in self:
            items.append(item)

            # Check if we've completed a page
            if len(items) % self.per_page == 0:
                page_count += 1
                if page_count >= num_pages:
                    break

        return items
