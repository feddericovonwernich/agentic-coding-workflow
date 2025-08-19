"""Repository repository for configuration and tracking operations."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Repository, RepositoryStatus

from .base import BaseRepository


class RepositoryRepository(BaseRepository[Repository]):
    """Repository for Repository configuration operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, Repository)

    async def get_by_url(self, url: str) -> Repository | None:
        """Get repository by URL."""
        query = (
            select(Repository)
            .where(Repository.url == url)
            .options(selectinload(Repository.pull_requests))
        )
        return await self._execute_single_query(query)

    async def get_by_name(self, name: str) -> Repository | None:
        """Get repository by name."""
        query = (
            select(Repository)
            .where(Repository.name == name)
            .options(selectinload(Repository.pull_requests))
        )
        return await self._execute_single_query(query)

    async def get_by_full_name(self, full_name: str) -> Repository | None:
        """Get repository by full name (owner/repo)."""
        query = (
            select(Repository)
            .where(Repository.full_name == full_name)
            .options(selectinload(Repository.pull_requests))
        )
        return await self._execute_single_query(query)

    async def get_active_repositories(self) -> list[Repository]:
        """Get all active repositories."""
        query = (
            select(Repository)
            .where(Repository.status == RepositoryStatus.ACTIVE)
            .order_by(Repository.name)
            .options(selectinload(Repository.pull_requests))
        )
        return await self._execute_query(query)

    async def get_repositories_needing_poll(self) -> list[Repository]:
        """Get repositories that need polling."""
        now = datetime.now(UTC)

        query = (
            select(Repository)
            .where(
                and_(
                    Repository.status == RepositoryStatus.ACTIVE,
                    or_(
                        Repository.last_polled_at.is_(None),
                        func.extract("epoch", now - Repository.last_polled_at)
                        > (Repository.polling_interval_minutes * 60),
                    ),
                )
            )
            .order_by(Repository.last_polled_at.asc().nulls_first())
        )
        return await self._execute_query(query)

    async def update_last_polled(
        self, repository_id: uuid.UUID, timestamp: datetime | None = None
    ) -> Repository:
        """Update last polled timestamp."""
        if timestamp is None:
            timestamp = datetime.now(UTC)

        repository = await self.get_by_id_or_raise(repository_id)
        repository.last_polled_at = timestamp

        await self.flush()
        await self.refresh(repository)
        return repository

    async def increment_failure_count(
        self, repository_id: uuid.UUID, reason: str | None = None
    ) -> Repository:
        """Increment failure count and handle status changes."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.increment_failure_count(reason)

        await self.flush()
        await self.refresh(repository)
        return repository

    async def reset_failure_count(self, repository_id: uuid.UUID) -> Repository:
        """Reset failure count after successful operation."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.reset_failure_count()

        await self.flush()
        await self.refresh(repository)
        return repository

    async def suspend_repository(
        self, repository_id: uuid.UUID, reason: str | None = None
    ) -> Repository:
        """Suspend repository monitoring."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.suspend(reason)

        await self.flush()
        await self.refresh(repository)
        return repository

    async def activate_repository(self, repository_id: uuid.UUID) -> Repository:
        """Activate repository monitoring."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.activate()

        await self.flush()
        await self.refresh(repository)
        return repository

    async def get_repositories_by_status(
        self, status: RepositoryStatus
    ) -> list[Repository]:
        """Get repositories by status."""
        query = (
            select(Repository)
            .where(Repository.status == status)
            .order_by(desc(Repository.updated_at))
        )
        return await self._execute_query(query)

    async def get_unhealthy_repositories(
        self, min_failure_count: int = 3
    ) -> list[Repository]:
        """Get repositories with high failure counts."""
        query = (
            select(Repository)
            .where(Repository.failure_count >= min_failure_count)
            .order_by(desc(Repository.failure_count))
        )
        return await self._execute_query(query)

    async def update_polling_interval(
        self, repository_id: uuid.UUID, interval_minutes: int
    ) -> Repository:
        """Update polling interval for a repository."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.polling_interval_minutes = interval_minutes

        await self.flush()
        await self.refresh(repository)
        return repository

    async def set_config_override(
        self, repository_id: uuid.UUID, key: str, value: Any
    ) -> Repository:
        """Set configuration override value."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.set_config_override(key, value)

        await self.flush()
        await self.refresh(repository)
        return repository

    async def remove_config_override(
        self, repository_id: uuid.UUID, key: str
    ) -> Repository:
        """Remove configuration override value."""
        repository = await self.get_by_id_or_raise(repository_id)
        repository.remove_config_override(key)

        await self.flush()
        await self.refresh(repository)
        return repository

    async def get_repository_statistics(self) -> dict[str, Any]:
        """Get overall repository statistics."""
        # Count by status
        status_counts = {}
        for status in RepositoryStatus:
            count_query = select(func.count(Repository.id)).where(
                Repository.status == status
            )
            result = await self.session.execute(count_query)
            status_counts[status.value] = result.scalar_one()

        # Count total
        total_query = select(func.count(Repository.id))
        total_result = await self.session.execute(total_query)
        total_count = total_result.scalar_one()

        # Count with high failure rates
        high_failure_query = select(func.count(Repository.id)).where(
            Repository.failure_count >= 5
        )
        high_failure_result = await self.session.execute(high_failure_query)
        high_failure_count = high_failure_result.scalar_one()

        # Average failure count
        avg_failure_query = select(func.avg(Repository.failure_count))
        avg_failure_result = await self.session.execute(avg_failure_query)
        avg_failure_count = avg_failure_result.scalar_one() or 0.0

        return {
            "total": total_count,
            "by_status": status_counts,
            "high_failure_count": high_failure_count,
            "avg_failure_count": float(avg_failure_count),
        }

    async def search_repositories(
        self,
        query_text: str | None = None,
        status: RepositoryStatus | None = None,
        owner: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Repository]:
        """Search repositories with various filters."""
        conditions = []

        if query_text:
            conditions.append(
                or_(
                    Repository.name.ilike(f"%{query_text}%"),
                    Repository.full_name.ilike(f"%{query_text}%"),
                    Repository.url.ilike(f"%{query_text}%"),
                    Repository.description.ilike(f"%{query_text}%"),
                )
            )

        if status:
            conditions.append(Repository.status == status)

        if owner:
            conditions.append(Repository.full_name.ilike(f"{owner}/%"))

        query = (
            select(Repository)
            .where(and_(*conditions) if conditions else text("1=1"))
            .order_by(Repository.name)
        )

        if offset:
            query = query.offset(offset)

        if limit:
            query = query.limit(limit)

        return await self._execute_query(query)

    async def bulk_update_polling_interval(
        self, repository_ids: list[uuid.UUID], interval_minutes: int
    ) -> int:
        """Bulk update polling interval for multiple repositories."""
        if not repository_ids:
            return 0

        stmt = (
            update(Repository)
            .where(Repository.id.in_(repository_ids))
            .values(polling_interval_minutes=interval_minutes)
        )

        result = await self.session.execute(stmt)
        await self.flush()
        return result.rowcount

    async def bulk_reset_failure_counts(self, repository_ids: list[uuid.UUID]) -> int:
        """Bulk reset failure counts for multiple repositories."""
        if not repository_ids:
            return 0

        stmt = (
            update(Repository)
            .where(Repository.id.in_(repository_ids))
            .values(failure_count=0, last_failure_at=None, last_failure_reason=None)
        )

        result = await self.session.execute(stmt)
        await self.flush()
        return result.rowcount

    async def get_repositories_with_auth(self) -> list[Repository]:
        """Get repositories that have authentication configured."""
        query = (
            select(Repository)
            .where(
                or_(
                    Repository.github_token.is_not(None),
                    and_(
                        Repository.github_app_id.is_not(None),
                        Repository.github_installation_id.is_not(None),
                    ),
                )
            )
            .order_by(Repository.name)
        )
        return await self._execute_query(query)
