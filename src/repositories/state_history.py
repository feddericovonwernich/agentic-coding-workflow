"""PRStateHistory repository for audit trail operations."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import PRState, PRStateHistory, TriggerEvent
from .base import BaseRepository


class PRStateHistoryRepository(BaseRepository[PRStateHistory]):
    """Repository for PRStateHistory audit operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, PRStateHistory)

    async def create_transition(
        self,
        pr_id: uuid.UUID,
        old_state: Optional[PRState],
        new_state: PRState,
        trigger_event: TriggerEvent,
        triggered_by: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> PRStateHistory:
        """Create a new state transition record."""
        return await self.create(
            pr_id=pr_id,
            old_state=old_state,
            new_state=new_state,
            trigger_event=trigger_event,
            triggered_by=triggered_by,
            metadata=metadata or {}
        )

    async def get_history_for_pr(
        self, 
        pr_id: uuid.UUID, 
        limit: Optional[int] = None
    ) -> list[PRStateHistory]:
        """Get state history for a PR, ordered by most recent first."""
        query = (
            select(PRStateHistory)
            .where(PRStateHistory.pr_id == pr_id)
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_latest_transition_for_pr(
        self, 
        pr_id: uuid.UUID
    ) -> Optional[PRStateHistory]:
        """Get the most recent state transition for a PR."""
        query = (
            select(PRStateHistory)
            .where(PRStateHistory.pr_id == pr_id)
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        return await self._execute_single_query(query)

    async def get_state_changes_in_period(
        self,
        start: datetime,
        end: datetime,
        pr_id: Optional[uuid.UUID] = None,
        trigger_event: Optional[TriggerEvent] = None
    ) -> list[PRStateHistory]:
        """Get state changes within a time period."""
        conditions = [
            PRStateHistory.created_at >= start,
            PRStateHistory.created_at <= end
        ]
        
        if pr_id:
            conditions.append(PRStateHistory.pr_id == pr_id)
        
        if trigger_event:
            conditions.append(PRStateHistory.trigger_event == trigger_event)
        
        query = (
            select(PRStateHistory)
            .where(and_(*conditions))
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        return await self._execute_query(query)

    async def get_transitions_by_event(
        self,
        trigger_event: TriggerEvent,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> list[PRStateHistory]:
        """Get state transitions by trigger event."""
        conditions = [PRStateHistory.trigger_event == trigger_event]
        
        if since:
            conditions.append(PRStateHistory.created_at >= since)
        
        query = (
            select(PRStateHistory)
            .where(and_(*conditions))
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_reopening_events(
        self,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> list[PRStateHistory]:
        """Get PR reopening events."""
        conditions = [
            PRStateHistory.old_state == PRState.CLOSED,
            PRStateHistory.new_state == PRState.OPENED
        ]
        
        if since:
            conditions.append(PRStateHistory.created_at >= since)
        
        query = (
            select(PRStateHistory)
            .where(and_(*conditions))
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_merge_events(
        self,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> list[PRStateHistory]:
        """Get PR merge events."""
        conditions = [PRStateHistory.new_state == PRState.MERGED]
        
        if since:
            conditions.append(PRStateHistory.created_at >= since)
        
        query = (
            select(PRStateHistory)
            .where(and_(*conditions))
            .order_by(desc(PRStateHistory.created_at))
            .options(selectinload(PRStateHistory.pull_request))
        )
        
        if limit:
            query = query.limit(limit)
            
        return await self._execute_query(query)

    async def get_activity_timeline(
        self,
        pr_id: uuid.UUID,
        include_metadata: bool = True
    ) -> list[dict[str, Any]]:
        """Get a formatted activity timeline for a PR."""
        history = await self.get_history_for_pr(pr_id)
        
        timeline = []
        for entry in history:
            timeline_item = {
                "id": str(entry.id),
                "timestamp": entry.created_at.isoformat(),
                "old_state": entry.old_state.value if entry.old_state else None,
                "new_state": entry.new_state.value,
                "trigger_event": entry.trigger_event.value,
                "triggered_by": entry.triggered_by,
                "description": entry.get_transition_description(),
                "is_initial": entry.is_initial_state,
                "is_reopening": entry.is_reopening,
                "is_closing": entry.is_closing,
                "is_merging": entry.is_merging,
            }
            
            if include_metadata and entry.metadata:
                timeline_item["metadata"] = entry.metadata
            
            timeline.append(timeline_item)
        
        return timeline

    async def get_transition_statistics(
        self,
        since: Optional[datetime] = None
    ) -> dict[str, Any]:
        """Get statistics about state transitions."""
        conditions = []
        if since:
            conditions.append(PRStateHistory.created_at >= since)
        
        # Count by trigger event
        event_counts = {}
        for event in TriggerEvent:
            event_conditions = conditions + [PRStateHistory.trigger_event == event]
            count_query = select(func.count(PRStateHistory.id)).where(and_(*event_conditions))
            result = await self.session.execute(count_query)
            event_counts[event.value] = result.scalar_one()
        
        # Count by state transition type
        transition_counts = {
            "openings": 0,
            "closings": 0,
            "merges": 0,
            "reopenings": 0,
        }
        
        # Openings (initial states)
        openings_query = select(func.count(PRStateHistory.id)).where(
            and_(
                PRStateHistory.old_state.is_(None),
                PRStateHistory.new_state == PRState.OPENED,
                *conditions
            )
        )
        result = await self.session.execute(openings_query)
        transition_counts["openings"] = result.scalar_one()
        
        # Closings
        closings_query = select(func.count(PRStateHistory.id)).where(
            and_(
                PRStateHistory.old_state == PRState.OPENED,
                PRStateHistory.new_state == PRState.CLOSED,
                *conditions
            )
        )
        result = await self.session.execute(closings_query)
        transition_counts["closings"] = result.scalar_one()
        
        # Merges
        merges_query = select(func.count(PRStateHistory.id)).where(
            and_(
                PRStateHistory.new_state == PRState.MERGED,
                *conditions
            )
        )
        result = await self.session.execute(merges_query)
        transition_counts["merges"] = result.scalar_one()
        
        # Reopenings
        reopenings_query = select(func.count(PRStateHistory.id)).where(
            and_(
                PRStateHistory.old_state == PRState.CLOSED,
                PRStateHistory.new_state == PRState.OPENED,
                *conditions
            )
        )
        result = await self.session.execute(reopenings_query)
        transition_counts["reopenings"] = result.scalar_one()
        
        # Total transitions
        total_query = select(func.count(PRStateHistory.id)).where(
            and_(*conditions) if conditions else True
        )
        result = await self.session.execute(total_query)
        total_transitions = result.scalar_one()
        
        return {
            "total_transitions": total_transitions,
            "by_trigger_event": event_counts,
            "by_transition_type": transition_counts,
        }

    async def get_pr_lifecycle_duration(
        self, 
        pr_id: uuid.UUID
    ) -> dict[str, Any]:
        """Get duration metrics for a PR's lifecycle."""
        history = await self.get_history_for_pr(pr_id)
        
        if not history:
            return {"error": "No history found"}
        
        # Find key events
        opened_at = None
        closed_at = None
        merged_at = None
        
        for entry in reversed(history):  # Process in chronological order
            if entry.is_initial_state and entry.new_state == PRState.OPENED:
                opened_at = entry.created_at
            elif entry.is_closing:
                closed_at = entry.created_at
            elif entry.is_merging:
                merged_at = entry.created_at
        
        result = {
            "opened_at": opened_at.isoformat() if opened_at else None,
            "closed_at": closed_at.isoformat() if closed_at else None,
            "merged_at": merged_at.isoformat() if merged_at else None,
        }
        
        # Calculate durations
        if opened_at:
            if merged_at:
                duration = merged_at - opened_at
                result["time_to_merge_seconds"] = duration.total_seconds()
                result["time_to_merge_hours"] = duration.total_seconds() / 3600
            elif closed_at:
                duration = closed_at - opened_at
                result["time_to_close_seconds"] = duration.total_seconds()
                result["time_to_close_hours"] = duration.total_seconds() / 3600
            else:
                # Still open
                now = datetime.now(timezone.utc)
                duration = now - opened_at
                result["open_duration_seconds"] = duration.total_seconds()
                result["open_duration_hours"] = duration.total_seconds() / 3600
        
        return result

    async def cleanup_old_history(
        self, 
        older_than: datetime,
        keep_latest_per_pr: int = 50
    ) -> int:
        """Clean up old state history entries, keeping the latest N per PR."""
        # This would be a complex operation requiring careful ranking and deletion
        # For now, return 0 as placeholder
        # TODO: Implement proper cleanup logic
        return 0