"""Database connection pool optimizations."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool, StaticPool

logger = logging.getLogger(__name__)


@dataclass
class ConnectionPoolStats:
    """Statistics for connection pool monitoring."""

    size: int
    checked_in: int
    checked_out: int
    overflow: int
    total_connections: int
    pool_hits: int
    pool_misses: int
    pool_timeouts: int
    avg_checkout_time: float
    max_checkout_time: float


class ConnectionPoolOptimizer:
    """Optimize and monitor database connection pools."""

    def __init__(self, engine: AsyncEngine):
        """Initialize connection pool optimizer.

        Args:
            engine: SQLAlchemy async engine to optimize
        """
        self.engine = engine
        self._stats = {
            "pool_hits": 0,
            "pool_misses": 0,
            "pool_timeouts": 0,
            "checkout_times": [],
            "total_checkouts": 0,
        }
        self._setup_pool_monitoring()

    def _setup_pool_monitoring(self) -> None:
        """Set up event listeners for pool monitoring."""
        pool = self.engine.pool

        @event.listens_for(pool, "connect")
        def on_connect(dbapi_conn: Any, connection_record: Any) -> None:
            """Track new connections."""
            pool_misses = self._stats.get("pool_misses", 0)
            self._stats["pool_misses"] = int(pool_misses) + 1  # type: ignore[call-overload]
            logger.debug("New database connection created")

        @event.listens_for(pool, "checkout")
        def on_checkout(
            dbapi_conn: Any, connection_record: Any, connection_proxy: Any
        ) -> None:
            """Track connection checkouts."""
            connection_record._checkout_time = time.time()
            total_checkouts = self._stats.get("total_checkouts", 0)
            self._stats["total_checkouts"] = int(total_checkouts) + 1  # type: ignore[call-overload]

        @event.listens_for(pool, "checkin")
        def on_checkin(dbapi_conn: Any, connection_record: Any) -> None:
            """Track connection checkins."""
            if hasattr(connection_record, "_checkout_time"):
                checkout_time = time.time() - connection_record._checkout_time
                checkout_times_list = self._stats["checkout_times"]
                if isinstance(checkout_times_list, list):
                    checkout_times_list.append(checkout_time)
                # Keep only recent checkout times
                checkout_times_list = self._stats["checkout_times"]
                if (
                    isinstance(checkout_times_list, list)
                    and len(checkout_times_list) > 1000
                ):
                    self._stats["checkout_times"] = checkout_times_list[-1000:]
                delattr(connection_record, "_checkout_time")

        @event.listens_for(pool, "soft_invalidate")
        def on_soft_invalidate(
            dbapi_conn: Any, connection_record: Any, exception: Any
        ) -> None:
            """Track connection invalidations."""
            logger.warning(f"Connection soft invalidated: {exception}")

        @event.listens_for(pool, "hard_invalidate")
        def on_hard_invalidate(
            dbapi_conn: Any, connection_record: Any, exception: Any
        ) -> None:
            """Track connection hard invalidations."""
            logger.error(f"Connection hard invalidated: {exception}")

    async def get_pool_stats(self) -> ConnectionPoolStats:
        """Get current connection pool statistics."""
        pool = self.engine.pool

        # Calculate average checkout time
        checkout_times = self._stats["checkout_times"]
        if isinstance(checkout_times, list) and checkout_times:
            avg_checkout_time = sum(checkout_times) / len(checkout_times)
            max_checkout_time = max(checkout_times)
        else:
            avg_checkout_time = 0.0
            max_checkout_time = 0.0

        return ConnectionPoolStats(
            size=pool.size(),  # type: ignore
            checked_in=pool.checkedin(),  # type: ignore
            checked_out=pool.checkedout(),  # type: ignore
            overflow=pool.overflow(),  # type: ignore
            total_connections=pool.size() + pool.overflow(),  # type: ignore
            pool_hits=int(self._stats.get("total_checkouts", 0))  # type: ignore[call-overload]
            - int(self._stats.get("pool_misses", 0)),  # type: ignore[call-overload]
            pool_misses=int(self._stats.get("pool_misses", 0)),  # type: ignore[call-overload]
            pool_timeouts=int(self._stats.get("pool_timeouts", 0)),  # type: ignore[call-overload]
            avg_checkout_time=avg_checkout_time,
            max_checkout_time=max_checkout_time,
        )

    async def health_check(self) -> dict[str, Any]:
        """Perform connection pool health check."""
        stats = await self.get_pool_stats()

        # Health indicators
        health_status = "healthy"
        issues = []

        # Check for connection exhaustion
        utilization = stats.checked_out / max(stats.total_connections, 1)
        hit_rate = stats.pool_hits / max(stats.pool_hits + stats.pool_misses, 1)
        if utilization > 0.9:
            health_status = "degraded"
            issues.append(f"High connection utilization: {utilization:.1%}")

        # Check for slow checkouts
        if stats.avg_checkout_time > 0.1:  # 100ms threshold
            health_status = "degraded" if health_status == "healthy" else health_status
            issues.append(
                f"Slow connection checkout: {stats.avg_checkout_time:.3f}s avg"
            )

        # Check for timeouts
        if stats.pool_timeouts > 0:
            health_status = "unhealthy"
            issues.append(f"Connection pool timeouts: {stats.pool_timeouts}")

        return {
            "status": health_status,
            "issues": issues,
            "stats": {
                "total_connections": stats.total_connections,
                "active_connections": stats.checked_out,
                "idle_connections": stats.checked_in,
                "utilization": f"{utilization:.1%}",
                "avg_checkout_time": f"{stats.avg_checkout_time:.3f}s",
                "pool_hit_rate": f"{hit_rate:.1%}",
            },
        }

    async def optimize_pool_size(
        self,
        target_utilization: float = 0.7,
        measurement_window: int = 300,  # 5 minutes
    ) -> dict[str, Any]:
        """Analyze and suggest optimal pool size.

        Args:
            target_utilization: Target connection utilization (0.0-1.0)
            measurement_window: Time window for analysis in seconds
        """
        # Collect stats over measurement window
        initial_stats = await self.get_pool_stats()
        await asyncio.sleep(min(measurement_window, 60))  # Max 60s for demo
        final_stats = await self.get_pool_stats()

        # Calculate metrics
        avg_utilization = (initial_stats.checked_out + final_stats.checked_out) / (
            2 * max(initial_stats.total_connections, 1)
        )

        peak_connections = max(initial_stats.checked_out, final_stats.checked_out)

        # Suggest optimal size
        if avg_utilization < target_utilization * 0.5:
            suggestion = "reduce"
            optimal_size = max(5, int(peak_connections / target_utilization * 0.8))
        elif avg_utilization > target_utilization * 1.2:
            suggestion = "increase"
            optimal_size = int(peak_connections / target_utilization * 1.2)
        else:
            suggestion = "maintain"
            optimal_size = initial_stats.total_connections

        return {
            "current_size": initial_stats.total_connections,
            "suggested_size": optimal_size,
            "suggestion": suggestion,
            "metrics": {
                "avg_utilization": f"{avg_utilization:.1%}",
                "peak_connections": peak_connections,
                "target_utilization": f"{target_utilization:.1%}",
            },
            "reasoning": self._get_sizing_reasoning(
                avg_utilization, target_utilization, suggestion
            ),
        }

    def _get_sizing_reasoning(
        self, avg_util: float, target_util: float, suggestion: str
    ) -> str:
        """Get human-readable reasoning for pool sizing suggestion."""
        if suggestion == "reduce":
            return (
                f"Average utilization ({avg_util:.1%}) is well below target "
                f"({target_util:.1%}). Pool can be reduced to save resources."
            )
        elif suggestion == "increase":
            return (
                f"Average utilization ({avg_util:.1%}) exceeds target "
                f"({target_util:.1%}). Pool should be increased to prevent contention."
            )
        else:
            return (
                f"Average utilization ({avg_util:.1%}) is near target "
                f"({target_util:.1%}). Current pool size is appropriate."
            )

    async def test_connection_performance(self, iterations: int = 10) -> dict[str, Any]:
        """Test connection acquisition and query performance."""
        connection_times = []
        query_times = []
        errors = 0

        for _ in range(iterations):
            start_time = time.time()

            try:
                async with self.engine.begin() as conn:
                    conn_time = time.time() - start_time
                    connection_times.append(conn_time)

                    # Simple query to test performance
                    query_start = time.time()
                    await conn.execute(text("SELECT 1"))
                    query_time = time.time() - query_start
                    query_times.append(query_time)

            except Exception as e:
                logger.error(f"Connection test error: {e}")
                errors += 1

            # Small delay between iterations
            await asyncio.sleep(0.01)

        return {
            "iterations": iterations,
            "errors": errors,
            "success_rate": f"{(iterations - errors) / iterations:.1%}",
            "connection_times": {
                "avg": f"{sum(connection_times) / len(connection_times):.3f}s"
                if connection_times
                else "N/A",
                "min": f"{min(connection_times):.3f}s" if connection_times else "N/A",
                "max": f"{max(connection_times):.3f}s" if connection_times else "N/A",
            },
            "query_times": {
                "avg": f"{sum(query_times) / len(query_times):.3f}s"
                if query_times
                else "N/A",
                "min": f"{min(query_times):.3f}s" if query_times else "N/A",
                "max": f"{max(query_times):.3f}s" if query_times else "N/A",
            },
        }


class PoolConfigurationManager:
    """Manage optimal pool configurations for different environments."""

    @staticmethod
    def get_production_config(max_connections: int = 20) -> dict[str, Any]:
        """Get production-optimized pool configuration."""
        return {
            "pool_size": max_connections // 2,
            "max_overflow": max_connections // 2,
            "pool_timeout": 30,
            "pool_recycle": 3600,  # 1 hour
            "pool_pre_ping": True,
            "poolclass": QueuePool,
        }

    @staticmethod
    def get_development_config() -> dict[str, Any]:
        """Get development-optimized pool configuration."""
        return {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 10,
            "pool_recycle": 1800,  # 30 minutes
            "pool_pre_ping": True,
            "poolclass": QueuePool,
        }

    @staticmethod
    def get_testing_config() -> dict[str, Any]:
        """Get testing-optimized pool configuration."""
        return {
            "pool_size": 1,
            "max_overflow": 4,
            "pool_timeout": 5,
            "pool_recycle": 300,  # 5 minutes
            "pool_pre_ping": False,
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},  # For SQLite
        }

    @staticmethod
    def get_high_load_config(max_connections: int = 50) -> dict[str, Any]:
        """Get high-load optimized pool configuration."""
        return {
            "pool_size": max_connections * 2 // 3,
            "max_overflow": max_connections // 3,
            "pool_timeout": 60,
            "pool_recycle": 7200,  # 2 hours
            "pool_pre_ping": True,
            "poolclass": QueuePool,
        }


async def diagnose_pool_issues(engine: AsyncEngine) -> dict[str, Any]:
    """Diagnose common connection pool issues."""
    optimizer = ConnectionPoolOptimizer(engine)
    stats = await optimizer.get_pool_stats()
    health = await optimizer.health_check()

    issues = []
    recommendations = []

    # Check for connection leaks
    if stats.checked_out > stats.size * 0.9:
        issues.append("Possible connection leak detected")
        recommendations.append(
            "Review connection usage patterns and ensure proper cleanup"
        )

    # Check for undersized pool
    if stats.overflow > stats.size * 0.5:
        issues.append("Pool frequently using overflow connections")
        recommendations.append("Consider increasing base pool size")

    # Check for oversized pool
    utilization = stats.checked_out / max(stats.total_connections, 1)
    if utilization < 0.2 and stats.size > 5:
        issues.append("Pool appears oversized for current load")
        recommendations.append("Consider reducing pool size to save resources")

    # Check for slow operations
    if stats.avg_checkout_time > 0.05:  # 50ms
        issues.append("Slow connection acquisition detected")
        recommendations.append(
            "Investigate database server performance or network latency"
        )

    return {
        "health_status": health["status"],
        "stats": stats.__dict__,
        "issues": issues,
        "recommendations": recommendations,
        "optimization_suggestions": await optimizer.optimize_pool_size(),
    }
