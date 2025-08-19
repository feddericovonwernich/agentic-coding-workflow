"""Abstract base repository with common CRUD operations."""

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import BaseModel


class BaseRepository[ModelType: BaseModel]:
    """Abstract base repository with common CRUD operations."""

    def __init__(self, session: AsyncSession, model_class: type[ModelType]):
        """Initialize repository with database session and model class."""
        self.session = session
        self.model_class = model_class

    async def create(self, **kwargs: Any) -> ModelType:
        """Create a new entity."""
        entity = self.model_class(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelType | None:
        """Get entity by ID."""
        return await self.session.get(self.model_class, entity_id)

    async def get_by_id_or_raise(self, entity_id: uuid.UUID) -> ModelType:
        """Get entity by ID or raise exception if not found."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            raise ValueError(
                f"{self.model_class.__name__} with id {entity_id} not found"
            )
        return entity

    async def update(self, entity: ModelType, **kwargs: Any) -> ModelType:
        """Update an existing entity."""
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: ModelType) -> None:
        """Delete an entity."""
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: uuid.UUID) -> bool:
        """Delete entity by ID. Returns True if deleted, False if not found."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False

        await self.delete(entity)
        return True

    async def list_all(
        self, limit: int | None = None, offset: int | None = None
    ) -> list[ModelType]:
        """List all entities with optional pagination."""
        query = select(self.model_class)

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_all(self) -> int:
        """Count total number of entities."""
        query = select(func.count(self.model_class.id))
        result = await self.session.execute(query)
        return result.scalar_one()

    async def exists(self, entity_id: uuid.UUID) -> bool:
        """Check if entity exists by ID."""
        query = select(self.model_class.id).where(self.model_class.id == entity_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    def _build_base_query(self) -> Select[tuple[ModelType]]:
        """Build base query for the model."""
        return select(self.model_class)

    async def _execute_query(self, query: Select[tuple[ModelType]]) -> list[ModelType]:
        """Execute query and return results."""
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _execute_single_query(
        self, query: Select[tuple[ModelType]]
    ) -> ModelType | None:
        """Execute query and return single result."""
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _execute_count_query(self, query: Select[tuple[int]]) -> int:
        """Execute count query and return result."""
        result = await self.session.execute(query)
        return result.scalar_one()

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        await self.session.rollback()

    async def flush(self) -> None:
        """Flush pending changes to database."""
        await self.session.flush()

    async def refresh(self, entity: ModelType) -> None:
        """Refresh entity from database."""
        await self.session.refresh(entity)
