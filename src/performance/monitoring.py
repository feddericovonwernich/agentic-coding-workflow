"""Performance monitoring utilities."""

import asyncio
import functools
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class QueryMetrics:
    """Metrics for a database query."""

    query_hash: str
    execution_time: float
    timestamp: datetime
    success: bool
    error_message: str | None = None
    row_count: int | None = None
    cache_hit: bool = False


@dataclass
class PerformanceStats:
    """Aggregated performance statistics."""

    total_queries: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    success_rate: float
    cache_hit_rate: float
    slow_query_count: int
    error_count: int


class PerformanceMonitor:
    """Monitor and track database performance metrics."""

    def __init__(
        self,
        slow_query_threshold: float = 1.0,
        max_history_size: int = 10000,
        enable_logging: bool = True,
    ):
        """Initialize performance monitor.

        Args:
            slow_query_threshold: Threshold in seconds for slow query detection
            max_history_size: Maximum number of metrics to keep in memory
            enable_logging: Whether to log performance warnings
        """
        self.slow_query_threshold = slow_query_threshold
        self.max_history_size = max_history_size
        self.enable_logging = enable_logging

        self._metrics: deque[QueryMetrics] = deque(maxlen=max_history_size)
        self._query_stats: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def record_query(
        self,
        query_hash: str,
        execution_time: float,
        success: bool = True,
        error_message: str | None = None,
        row_count: int | None = None,
        cache_hit: bool = False,
    ) -> None:
        """Record a query execution."""
        async with self._lock:
            metric = QueryMetrics(
                query_hash=query_hash,
                execution_time=execution_time,
                timestamp=datetime.utcnow(),
                success=success,
                error_message=error_message,
                row_count=row_count,
                cache_hit=cache_hit,
            )

            self._metrics.append(metric)

            if success:
                self._query_stats[query_hash].append(execution_time)
                # Keep only recent stats per query
                if len(self._query_stats[query_hash]) > 100:
                    self._query_stats[query_hash] = self._query_stats[query_hash][-100:]

            # Log slow queries
            if self.enable_logging and execution_time > self.slow_query_threshold:
                logger.warning(
                    f"Slow query detected: {query_hash} took {execution_time:.2f}s"
                )

    async def get_stats(
        self,
        since: datetime | None = None,
        query_pattern: str | None = None,
    ) -> PerformanceStats:
        """Get aggregated performance statistics."""
        async with self._lock:
            # Filter metrics by time and pattern
            filtered_metrics = []
            for metric in self._metrics:
                if since and metric.timestamp < since:
                    continue
                if query_pattern and query_pattern not in metric.query_hash:
                    continue
                filtered_metrics.append(metric)

            if not filtered_metrics:
                return PerformanceStats(
                    total_queries=0,
                    total_time=0.0,
                    avg_time=0.0,
                    min_time=0.0,
                    max_time=0.0,
                    success_rate=0.0,
                    cache_hit_rate=0.0,
                    slow_query_count=0,
                    error_count=0,
                )

            # Calculate statistics
            execution_times = [m.execution_time for m in filtered_metrics]
            successful_queries = [m for m in filtered_metrics if m.success]
            cache_hits = [m for m in filtered_metrics if m.cache_hit]
            slow_queries = [
                m
                for m in filtered_metrics
                if m.execution_time > self.slow_query_threshold
            ]
            errors = [m for m in filtered_metrics if not m.success]

            return PerformanceStats(
                total_queries=len(filtered_metrics),
                total_time=sum(execution_times),
                avg_time=sum(execution_times) / len(execution_times),
                min_time=min(execution_times),
                max_time=max(execution_times),
                success_rate=len(successful_queries) / len(filtered_metrics),
                cache_hit_rate=len(cache_hits) / len(filtered_metrics),
                slow_query_count=len(slow_queries),
                error_count=len(errors),
            )

    async def get_slow_queries(
        self,
        limit: int = 10,
        since: datetime | None = None,
    ) -> list[QueryMetrics]:
        """Get slowest queries."""
        async with self._lock:
            filtered_metrics = []
            for metric in self._metrics:
                if since and metric.timestamp < since:
                    continue
                if metric.execution_time > self.slow_query_threshold:
                    filtered_metrics.append(metric)

            # Sort by execution time (descending)
            filtered_metrics.sort(key=lambda m: m.execution_time, reverse=True)
            return filtered_metrics[:limit]

    async def get_query_patterns(self) -> dict[str, dict[str, Any]]:
        """Get statistics for each query pattern."""
        async with self._lock:
            patterns = {}
            for query_hash, times in self._query_stats.items():
                if times:
                    patterns[query_hash] = {
                        "count": len(times),
                        "avg_time": sum(times) / len(times),
                        "min_time": min(times),
                        "max_time": max(times),
                        "total_time": sum(times),
                    }
            return patterns

    async def clear_stats(self, older_than: datetime | None = None) -> int:
        """Clear old statistics."""
        async with self._lock:
            if older_than is None:
                count = len(self._metrics)
                self._metrics.clear()
                self._query_stats.clear()
                return count

            # Remove old metrics
            original_count = len(self._metrics)
            self._metrics = deque(
                (m for m in self._metrics if m.timestamp >= older_than),
                maxlen=self.max_history_size,
            )
            return original_count - len(self._metrics)


# Global performance monitor instance
_performance_monitor: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def set_performance_monitor(monitor: PerformanceMonitor) -> None:
    """Set global performance monitor instance."""
    global _performance_monitor
    _performance_monitor = monitor


def query_timer(
    query_name: str | None = None,
    track_rows: bool = False,
) -> Callable[[F], F]:
    """Decorator to time query execution."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            monitor = get_performance_monitor()
            query_hash = query_name or f"{func.__module__}.{func.__name__}"

            start_time = time.time()
            error_message = None
            success = True
            row_count = None

            try:
                result = await func(*args, **kwargs)

                # Try to get row count if result is a list
                if track_rows and isinstance(result, list | tuple):
                    row_count = len(result)

                return result

            except Exception as e:
                success = False
                error_message = str(e)
                raise

            finally:
                execution_time = time.time() - start_time
                await monitor.record_query(
                    query_hash=query_hash,
                    execution_time=execution_time,
                    success=success,
                    error_message=error_message,
                    row_count=row_count,
                )

        return wrapper  # type: ignore

    return decorator


def track_performance(
    operation_name: str | None = None,
    log_slow: bool = True,
    threshold: float = 1.0,
) -> Callable[[F], F]:
    """Decorator to track performance of any async operation."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                execution_time = time.time() - start_time

                if log_slow and execution_time > threshold:
                    logger.warning(
                        f"Slow operation: {op_name} took {execution_time:.2f}s"
                    )

                # Could also record to performance monitor
                monitor = get_performance_monitor()
                await monitor.record_query(
                    query_hash=f"operation:{op_name}",
                    execution_time=execution_time,
                    success=True,
                )

        return wrapper  # type: ignore

    return decorator


class PerformanceReporter:
    """Generate performance reports."""

    def __init__(self, monitor: PerformanceMonitor):
        self.monitor = monitor

    async def generate_daily_report(self) -> dict[str, Any]:
        """Generate daily performance report."""
        since = datetime.utcnow() - timedelta(days=1)
        stats = await self.monitor.get_stats(since=since)
        slow_queries = await self.monitor.get_slow_queries(since=since)
        patterns = await self.monitor.get_query_patterns()

        return {
            "period": "last_24_hours",
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_queries": stats.total_queries,
                "avg_response_time": f"{stats.avg_time:.3f}s",
                "success_rate": f"{stats.success_rate:.1%}",
                "cache_hit_rate": f"{stats.cache_hit_rate:.1%}",
                "slow_queries": stats.slow_query_count,
                "errors": stats.error_count,
            },
            "slow_queries": [
                {
                    "query": sq.query_hash,
                    "time": f"{sq.execution_time:.3f}s",
                    "timestamp": sq.timestamp.isoformat(),
                    "error": sq.error_message,
                }
                for sq in slow_queries[:5]
            ],
            "top_queries": {
                pattern: {
                    "count": data["count"],
                    "avg_time": f"{data['avg_time']:.3f}s",
                    "total_time": f"{data['total_time']:.3f}s",
                }
                for pattern, data in sorted(
                    patterns.items(), key=lambda x: x[1]["total_time"], reverse=True
                )[:10]
            },
        }

    async def generate_health_check(self) -> dict[str, Any]:
        """Generate health check report."""
        since = datetime.utcnow() - timedelta(minutes=5)
        stats = await self.monitor.get_stats(since=since)

        # Health thresholds
        healthy_success_rate = 0.95
        healthy_avg_time = 0.5
        healthy_error_rate = 0.05

        health_status = "healthy"
        issues = []

        if stats.success_rate < healthy_success_rate:
            health_status = "unhealthy"
            issues.append(f"Low success rate: {stats.success_rate:.1%}")

        if stats.avg_time > healthy_avg_time:
            health_status = "degraded" if health_status == "healthy" else health_status
            issues.append(f"High avg response time: {stats.avg_time:.3f}s")

        error_rate = stats.error_count / max(stats.total_queries, 1)
        if error_rate > healthy_error_rate:
            health_status = "unhealthy"
            issues.append(f"High error rate: {error_rate:.1%}")

        return {
            "status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "queries_last_5min": stats.total_queries,
                "avg_response_time": f"{stats.avg_time:.3f}s",
                "success_rate": f"{stats.success_rate:.1%}",
                "error_count": stats.error_count,
            },
            "issues": issues,
        }
