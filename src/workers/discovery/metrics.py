"""Metrics collection for PR Discovery system.

This module provides comprehensive metrics collection and monitoring
for the discovery process including performance, error rates, and
resource utilization tracking.
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryMetric:
    """Single metric data point."""

    name: str
    value: float
    timestamp: datetime
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert metric to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class DiscoveryTimer:
    """Timer for measuring duration metrics."""

    name: str
    start_time: float
    tags: dict[str, str] = field(default_factory=dict)

    def stop(self) -> float:
        """Stop timer and return duration in seconds."""
        return time.time() - self.start_time


class MetricsCollector:
    """Comprehensive metrics collector for discovery system.

    Collects and aggregates metrics including:
    - Discovery cycle performance
    - API call statistics
    - Cache hit/miss rates
    - Error rates and types
    - Resource utilization
    - Repository-specific metrics
    """

    def __init__(self, retention_hours: int = 24, aggregation_window_minutes: int = 5):
        """Initialize metrics collector.

        Args:
            retention_hours: Hours to retain detailed metrics
            aggregation_window_minutes: Window for metric aggregation
        """
        self.retention_hours = retention_hours
        self.aggregation_window = timedelta(minutes=aggregation_window_minutes)

        # Metric storage
        self.metrics: deque[DiscoveryMetric] = deque()
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.timers: dict[str, list[float]] = defaultdict(list)

        # Repository-specific metrics
        self.repository_metrics: dict[uuid.UUID, dict[str, Any]] = defaultdict(dict)

        # Aggregated metrics for quick access
        self.aggregated_metrics: dict[str, dict[str, float]] = defaultdict(dict)

        # Background cleanup task
        self._cleanup_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start metrics collection background tasks."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop metrics collection and cleanup."""
        self._shutdown_event.set()
        if self._cleanup_task:
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except TimeoutError:
                self._cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._cleanup_task
            self._cleanup_task = None

    def record_metric(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Record a metric value.

        Args:
            name: Metric name
            value: Metric value
            tags: Optional tags for categorization
        """
        metric = DiscoveryMetric(
            name=name,
            value=value,
            timestamp=datetime.now(UTC),
            tags=tags or {},
        )

        self.metrics.append(metric)

        # Update aggregated metrics
        self._update_aggregated_metric(name, value, tags)

        logger.debug(f"Recorded metric {name}={value} with tags {tags}")

    def increment_counter(
        self, name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Counter name
            value: Increment value
            tags: Optional tags
        """
        # Create unique counter key with tags
        counter_key = self._make_metric_key(name, tags)
        self.counters[counter_key] += value

        # Also record as regular metric
        self.record_metric(name, self.counters[counter_key], tags)

    def set_gauge(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: Gauge name
            value: Current value
            tags: Optional tags
        """
        gauge_key = self._make_metric_key(name, tags)
        self.gauges[gauge_key] = value

        # Record as regular metric
        self.record_metric(name, value, tags)

    def start_timer(
        self, name: str, tags: dict[str, str] | None = None
    ) -> DiscoveryTimer:
        """Start a timer for duration measurement.

        Args:
            name: Timer name
            tags: Optional tags

        Returns:
            Timer object
        """
        return DiscoveryTimer(name=name, start_time=time.time(), tags=tags or {})

    def record_timer(self, timer: DiscoveryTimer) -> float:
        """Record timer duration.

        Args:
            timer: Timer to record

        Returns:
            Duration in seconds
        """
        duration = timer.stop()

        # Store timer value
        timer_key = self._make_metric_key(timer.name, timer.tags)
        self.timers[timer_key].append(duration)

        # Record as metric
        self.record_metric(f"{timer.name}_duration", duration, timer.tags)

        return duration

    def record_discovery_cycle(
        self,
        repository_count: int,
        duration_seconds: float,
        prs_discovered: int,
        checks_discovered: int,
        errors_count: int,
        api_calls_used: int,
        cache_hits: int,
        cache_misses: int,
    ) -> None:
        """Record metrics for a complete discovery cycle.

        Args:
            repository_count: Number of repositories processed
            duration_seconds: Total cycle duration
            prs_discovered: Total PRs discovered
            checks_discovered: Total check runs discovered
            errors_count: Number of errors encountered
            api_calls_used: Total API calls made
            cache_hits: Cache hits
            cache_misses: Cache misses
        """
        datetime.now(UTC)

        # Core metrics
        self.record_metric("discovery_cycle_duration_seconds", duration_seconds)
        self.record_metric("discovery_repositories_processed", repository_count)
        self.record_metric("discovery_prs_discovered", prs_discovered)
        self.record_metric("discovery_checks_discovered", checks_discovered)
        self.record_metric("discovery_errors_total", errors_count)

        # API metrics
        self.record_metric("github_api_calls_total", api_calls_used)

        # Cache metrics
        cache_total = cache_hits + cache_misses
        cache_hit_rate = (cache_hits / cache_total * 100) if cache_total > 0 else 0

        self.record_metric("cache_hits_total", cache_hits)
        self.record_metric("cache_misses_total", cache_misses)
        self.record_metric("cache_hit_rate_percent", cache_hit_rate)

        # Performance metrics
        prs_per_second = (
            prs_discovered / duration_seconds if duration_seconds > 0 else 0
        )
        repos_per_second = (
            repository_count / duration_seconds if duration_seconds > 0 else 0
        )

        self.record_metric("discovery_prs_per_second", prs_per_second)
        self.record_metric("discovery_repositories_per_second", repos_per_second)

        # Error rate
        error_rate = (
            (errors_count / repository_count * 100) if repository_count > 0 else 0
        )
        self.record_metric("discovery_error_rate_percent", error_rate)

        logger.info(
            f"Recorded discovery cycle metrics: {repository_count} repos, "
            f"{duration_seconds:.2f}s"
        )

    def record_repository_metrics(
        self,
        repository_id: uuid.UUID,
        prs_count: int,
        checks_count: int,
        processing_time_ms: float,
        api_calls: int,
        cache_hits: int,
        errors: int,
    ) -> None:
        """Record metrics for individual repository processing.

        Args:
            repository_id: Repository ID
            prs_count: Number of PRs processed
            checks_count: Number of checks processed
            processing_time_ms: Processing time in milliseconds
            api_calls: API calls made
            cache_hits: Cache hits
            errors: Number of errors
        """
        tags = {"repository_id": str(repository_id)}

        self.record_metric("repository_prs_processed", prs_count, tags)
        self.record_metric("repository_checks_processed", checks_count, tags)
        self.record_metric("repository_processing_time_ms", processing_time_ms, tags)
        self.record_metric("repository_api_calls", api_calls, tags)
        self.record_metric("repository_cache_hits", cache_hits, tags)
        self.record_metric("repository_errors", errors, tags)

        # Update repository-specific storage
        repo_metrics = self.repository_metrics[repository_id]
        repo_metrics.update(
            {
                "last_updated": datetime.now(UTC),
                "prs_count": prs_count,
                "checks_count": checks_count,
                "processing_time_ms": processing_time_ms,
                "api_calls": api_calls,
                "cache_hits": cache_hits,
                "errors": errors,
            }
        )

    def record_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record error metrics.

        Args:
            error_type: Type/category of error
            error_message: Error message
            context: Additional error context
        """
        tags = {"error_type": error_type}
        if context:
            # Add context as tags (convert to strings)
            for key, value in context.items():
                if isinstance(value, str | int | float | bool):
                    tags[f"context_{key}"] = str(value)

        self.increment_counter("errors_total", tags=tags)
        self.record_metric("error_occurred", 1.0, tags)

        logger.debug(f"Recorded error metric: {error_type} - {error_message}")

    def get_current_metrics(self) -> dict[str, Any]:
        """Get current metric values.

        Returns:
            Dictionary with current metrics
        """
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timers_summary": {
                name: {
                    "count": len(values),
                    "avg": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                }
                for name, values in self.timers.items()
            },
            "aggregated": dict(self.aggregated_metrics),
            "repository_count": len(self.repository_metrics),
            "total_metrics": len(self.metrics),
        }

    def get_repository_metrics(self, repository_id: uuid.UUID) -> dict[str, Any] | None:
        """Get metrics for specific repository.

        Args:
            repository_id: Repository ID

        Returns:
            Repository metrics or None if not found
        """
        return self.repository_metrics.get(repository_id)

    def get_metrics_summary(self, hours: int = 1) -> dict[str, Any]:
        """Get aggregated metrics summary for the last N hours.

        Args:
            hours: Hours to include in summary

        Returns:
            Metrics summary
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        # Filter recent metrics
        recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return {"period_hours": hours, "metrics": {}}

        # Group metrics by name
        metrics_by_name = defaultdict(list)
        for metric in recent_metrics:
            metrics_by_name[metric.name].append(metric.value)

        # Calculate summary statistics
        summary = {}
        for name, values in metrics_by_name.items():
            summary[name] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1] if values else 0,
            }

        return {
            "period_hours": hours,
            "total_data_points": len(recent_metrics),
            "metrics": summary,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _make_metric_key(self, name: str, tags: dict[str, str] | None = None) -> str:
        """Create unique key for metric with tags."""
        if not tags:
            return name

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"

    def _update_aggregated_metric(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Update aggregated metrics for quick access."""
        if name not in self.aggregated_metrics:
            self.aggregated_metrics[name] = {
                "count": 0,
                "sum": 0.0,
                "min": float("inf"),
                "max": float("-inf"),
                "avg": 0.0,
            }

        agg = self.aggregated_metrics[name]
        agg["count"] += 1
        agg["sum"] += value
        agg["min"] = min(agg["min"], value)
        agg["max"] = max(agg["max"], value)
        agg["avg"] = agg["sum"] / agg["count"]

    async def _cleanup_loop(self) -> None:
        """Background task to clean up old metrics."""
        cleanup_interval = 3600  # 1 hour

        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=cleanup_interval
                )
                # Shutdown event was set
                break
            except TimeoutError:
                # Normal timeout, perform cleanup
                await self._cleanup_old_metrics()

    async def _cleanup_old_metrics(self) -> None:
        """Clean up old metrics beyond retention period."""
        cutoff_time = datetime.now(UTC) - timedelta(hours=self.retention_hours)

        # Clean main metrics
        original_count = len(self.metrics)
        self.metrics = deque([m for m in self.metrics if m.timestamp >= cutoff_time])

        # Clean timer data
        for name, values in list(self.timers.items()):
            # Keep only recent values (approximation)
            max_values = 1000
            if len(values) > max_values:
                self.timers[name] = values[-max_values:]

        # Clean repository metrics
        for repo_id, metrics in list(self.repository_metrics.items()):
            last_updated = metrics.get("last_updated")
            if last_updated and last_updated < cutoff_time:
                del self.repository_metrics[repo_id]

        cleaned_count = original_count - len(self.metrics)
        if cleaned_count > 0:
            logger.debug(f"Cleaned up {cleaned_count} old metrics")


class DiscoveryHealthChecker:
    """Health checker for discovery system components."""

    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize health checker.

        Args:
            metrics_collector: Metrics collector for health data
        """
        self.metrics = metrics_collector

        # Health check thresholds
        self.thresholds = {
            "max_error_rate_percent": 10.0,
            "min_cache_hit_rate_percent": 30.0,
            "max_avg_processing_time_seconds": 300.0,
            "max_failed_repositories_percent": 20.0,
        }

    async def check_discovery_health(self) -> dict[str, Any]:
        """Perform comprehensive health check of discovery system.

        Returns:
            Health check results
        """
        health: dict[str, Any] = {
            "healthy": True,
            "checks": {},
            "overall_status": "healthy",
            "issues": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            # Get recent metrics for analysis
            recent_metrics = self.metrics.get_metrics_summary(hours=1)

            # Check error rate
            health["checks"]["error_rate"] = await self._check_error_rate(
                recent_metrics
            )
            if not health["checks"]["error_rate"]["healthy"]:
                health["healthy"] = False
                health["issues"].append("High error rate detected")

            # Check cache performance
            health["checks"]["cache_performance"] = await self._check_cache_performance(
                recent_metrics
            )
            if not health["checks"]["cache_performance"]["healthy"]:
                health["issues"].append("Poor cache performance")

            # Check processing performance
            health["checks"][
                "processing_performance"
            ] = await self._check_processing_performance(recent_metrics)
            if not health["checks"]["processing_performance"]["healthy"]:
                health["issues"].append("Slow processing performance")

            # Check system resources
            health["checks"]["system_resources"] = await self._check_system_resources()
            if not health["checks"]["system_resources"]["healthy"]:
                health["issues"].append("System resource issues")

            # Set overall status
            if not health["healthy"]:
                health["overall_status"] = "degraded"
            elif health["issues"]:
                health["overall_status"] = "warning"

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health["healthy"] = False
            health["overall_status"] = "error"
            health["issues"].append(f"Health check error: {e!s}")

        return health

    async def _check_error_rate(self, recent_metrics: dict[str, Any]) -> dict[str, Any]:
        """Check error rate health."""
        metrics = recent_metrics.get("metrics", {})
        error_rate_metric = metrics.get("discovery_error_rate_percent", {})

        current_error_rate = error_rate_metric.get("latest", 0)
        avg_error_rate = error_rate_metric.get("avg", 0)

        healthy = (
            current_error_rate <= self.thresholds["max_error_rate_percent"]
            and avg_error_rate <= self.thresholds["max_error_rate_percent"]
        )

        return {
            "healthy": healthy,
            "current_error_rate_percent": current_error_rate,
            "avg_error_rate_percent": avg_error_rate,
            "threshold": self.thresholds["max_error_rate_percent"],
            "message": (
                f"Error rate: {current_error_rate:.1f}% "
                f"(threshold: {self.thresholds['max_error_rate_percent']}%)"
            ),
        }

    async def _check_cache_performance(
        self, recent_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """Check cache performance health."""
        metrics = recent_metrics.get("metrics", {})
        cache_hit_rate_metric = metrics.get("cache_hit_rate_percent", {})

        current_hit_rate = cache_hit_rate_metric.get("latest", 0)
        avg_hit_rate = cache_hit_rate_metric.get("avg", 0)

        healthy = (
            current_hit_rate >= self.thresholds["min_cache_hit_rate_percent"]
            or avg_hit_rate >= self.thresholds["min_cache_hit_rate_percent"]
        )

        return {
            "healthy": healthy,
            "current_hit_rate_percent": current_hit_rate,
            "avg_hit_rate_percent": avg_hit_rate,
            "threshold": self.thresholds["min_cache_hit_rate_percent"],
            "message": (
                f"Cache hit rate: {current_hit_rate:.1f}% "
                f"(threshold: >{self.thresholds['min_cache_hit_rate_percent']}%)"
            ),
        }

    async def _check_processing_performance(
        self, recent_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """Check processing performance health."""
        metrics = recent_metrics.get("metrics", {})
        duration_metric = metrics.get("discovery_cycle_duration_seconds", {})

        current_duration = duration_metric.get("latest", 0)
        avg_duration = duration_metric.get("avg", 0)

        healthy = (
            current_duration <= self.thresholds["max_avg_processing_time_seconds"]
            and avg_duration <= self.thresholds["max_avg_processing_time_seconds"]
        )

        return {
            "healthy": healthy,
            "current_duration_seconds": current_duration,
            "avg_duration_seconds": avg_duration,
            "threshold": self.thresholds["max_avg_processing_time_seconds"],
            "message": (
                f"Processing time: {current_duration:.1f}s "
                f"(threshold: <{self.thresholds['max_avg_processing_time_seconds']}s)"
            ),
        }

    async def _check_system_resources(self) -> dict[str, Any]:
        """Check system resource health."""
        # This is a simplified check - in production you'd want to check
        # actual system resources like memory, CPU, etc.

        return {"healthy": True, "message": "System resources OK"}

    def update_thresholds(self, new_thresholds: dict[str, float]) -> None:
        """Update health check thresholds.

        Args:
            new_thresholds: Dictionary of new threshold values
        """
        for key, value in new_thresholds.items():
            if key in self.thresholds:
                self.thresholds[key] = value
                logger.info(f"Updated health threshold {key} = {value}")
            else:
                logger.warning(f"Unknown health threshold: {key}")
