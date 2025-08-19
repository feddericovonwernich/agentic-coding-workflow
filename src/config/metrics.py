"""Configuration metrics and monitoring system.

This module provides comprehensive monitoring and metrics collection for
configuration usage patterns, performance characteristics, and operational
health. It integrates with the caching system to provide insights into
configuration access patterns and system behavior.

The metrics system tracks:
- Configuration access frequency and patterns
- Configuration load performance and timing
- Configuration validation results and errors
- Cache performance and hit rates
- Configuration change frequency and impact
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricType(Enum):
    """Types of configuration metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class ConfigurationEvent(Enum):
    """Types of configuration events to track."""

    CONFIG_LOADED = "config_loaded"
    CONFIG_RELOADED = "config_reloaded"
    CONFIG_VALIDATED = "config_validated"
    CONFIG_ERROR = "config_error"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_EVICTION = "cache_eviction"
    ACCESS_PATTERN = "access_pattern"
    VALIDATION_ERROR = "validation_error"
    VALIDATION_WARNING = "validation_warning"


@dataclass
class MetricValue:
    """Container for metric values with metadata."""

    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TimingMetric:
    """Container for timing measurements."""

    operation: str
    duration: float
    timestamp: float
    success: bool
    tags: dict[str, str] = field(default_factory=dict)


class ConfigurationMetrics:
    """Comprehensive configuration metrics and monitoring system.

    This class provides detailed tracking of configuration system behavior,
    including access patterns, performance metrics, error rates, and
    operational health indicators.
    """

    def __init__(self, enable_detailed_tracking: bool = True) -> None:
        """Initialize configuration metrics system.

        Args:
            enable_detailed_tracking: Whether to track detailed access patterns
        """
        self._enable_detailed_tracking = enable_detailed_tracking
        self._lock = threading.RLock()

        # Core metrics storage
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Event tracking
        self._events: deque = deque(maxlen=10000)
        self._event_counts: dict[ConfigurationEvent, int] = defaultdict(int)

        # Access pattern tracking
        self._access_patterns: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "first_access": None,
                "last_access": None,
                "access_frequency": 0.0,
            }
        )

        # Performance tracking
        self._load_times: deque = deque(maxlen=100)
        self._validation_times: deque = deque(maxlen=100)
        self._cache_performance: dict[str, Any] = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "hit_rate": 0.0,
        }

        # Error tracking
        self._error_counts: dict[str, int] = defaultdict(int)
        self._recent_errors: deque = deque(maxlen=100)

        # Health indicators
        self._health_status = "healthy"
        self._health_checks: dict[str, bool] = {}

        # Start time for rate calculations
        self._start_time = time.time()

    def record_event(
        self,
        event: ConfigurationEvent,
        details: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a configuration system event.

        Args:
            event: Type of event that occurred
            details: Optional additional event details
            tags: Optional tags for categorizing the event
        """
        with self._lock:
            timestamp = time.time()

            # Store event
            event_data = {
                "event": event,
                "timestamp": timestamp,
                "details": details or {},
                "tags": tags or {},
            }
            self._events.append(event_data)

            # Update event counts
            self._event_counts[event] += 1

            # Update specific metrics based on event type
            self._update_event_metrics(event, details, timestamp)

    def record_timing(
        self,
        operation: str,
        duration: float,
        success: bool = True,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record timing information for configuration operations.

        Args:
            operation: Name of the operation timed
            duration: Duration in seconds
            success: Whether the operation was successful
            tags: Optional tags for categorizing the timing
        """
        with self._lock:
            timing = TimingMetric(
                operation=operation,
                duration=duration,
                timestamp=time.time(),
                success=success,
                tags=tags or {},
            )

            self._timers[operation].append(timing)

            # Update histogram data
            self._histograms[f"{operation}_duration"].append(duration)

            # Update success/failure counters
            if success:
                self._counters[f"{operation}_success"] += 1
            else:
                self._counters[f"{operation}_failure"] += 1

    def record_access_pattern(self, key: str, access_type: str = "read") -> None:
        """Record configuration access pattern for analysis.

        Args:
            key: Configuration key accessed
            access_type: Type of access (read, write, validate)
        """
        if not self._enable_detailed_tracking:
            return

        with self._lock:
            timestamp = time.time()
            pattern = self._access_patterns[key]

            pattern["count"] += 1
            pattern["last_access"] = timestamp

            if pattern["first_access"] is None:
                pattern["first_access"] = timestamp
            else:
                # Calculate access frequency (accesses per hour)
                time_span = timestamp - pattern["first_access"]
                if time_span > 0:
                    pattern["access_frequency"] = pattern["count"] / (time_span / 3600)

            # Record general access counter
            self._counters[f"access_{access_type}"] += 1

    def record_cache_performance(
        self, hits: int, misses: int, evictions: int = 0
    ) -> None:
        """Record cache performance metrics.

        Args:
            hits: Number of cache hits
            misses: Number of cache misses
            evictions: Number of cache evictions
        """
        with self._lock:
            self._cache_performance["cache_hits"] = hits
            self._cache_performance["cache_misses"] = misses
            self._cache_performance["total_requests"] = hits + misses

            if self._cache_performance["total_requests"] > 0:
                self._cache_performance["hit_rate"] = (
                    hits / self._cache_performance["total_requests"]
                )

            self._counters["cache_evictions"] = evictions

    def record_error(
        self, error_type: str, error_message: str, context: dict[str, Any] | None = None
    ) -> None:
        """Record configuration error for tracking and analysis.

        Args:
            error_type: Type/category of the error
            error_message: Error message or description
            context: Optional context information
        """
        with self._lock:
            timestamp = time.time()

            # Update error counts
            self._error_counts[error_type] += 1
            self._counters[f"error_{error_type}"] += 1

            # Store recent error details
            error_data = {
                "type": error_type,
                "message": error_message,
                "timestamp": timestamp,
                "context": context or {},
            }
            self._recent_errors.append(error_data)

            # Update health status if error rate is high
            self._update_health_status()

    def increment_counter(
        self, name: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Increment a named counter metric.

        Args:
            name: Counter name
            value: Value to add to counter
            tags: Optional tags for the metric
        """
        with self._lock:
            self._counters[name] += value

    def set_gauge(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: Gauge name
            value: Current gauge value
            tags: Optional tags for the metric
        """
        with self._lock:
            self._gauges[name] = value

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary.

        Returns:
            Dictionary containing all collected metrics
        """
        with self._lock:
            runtime = time.time() - self._start_time

            return {
                "runtime_seconds": runtime,
                "health_status": self._health_status,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "cache_performance": self._cache_performance.copy(),
                "event_counts": {
                    event.value: count for event, count in self._event_counts.items()
                },
                "error_summary": {
                    "total_errors": sum(self._error_counts.values()),
                    "error_types": dict(self._error_counts),
                    "error_rate": sum(self._error_counts.values()) / runtime
                    if runtime > 0
                    else 0.0,
                },
                "performance_summary": self._get_performance_summary(),
                "access_patterns_summary": self._get_access_patterns_summary(),
            }

    def get_timing_statistics(self, operation: str) -> dict[str, float]:
        """Get timing statistics for a specific operation.

        Args:
            operation: Operation name to get statistics for

        Returns:
            Dictionary with timing statistics (min, max, avg, p95, etc.)
        """
        with self._lock:
            timings = self._timers.get(operation, deque())

            if not timings:
                return {"count": 0}

            durations = [t.duration for t in timings]
            durations.sort()

            count = len(durations)
            total = sum(durations)

            stats = {
                "count": count,
                "total": total,
                "min": min(durations),
                "max": max(durations),
                "avg": total / count,
                "median": durations[count // 2],
            }

            # Calculate percentiles
            if count >= 5:
                stats["p95"] = durations[int(count * 0.95)]
                stats["p99"] = durations[int(count * 0.99)]

            return stats

    def get_recent_events(
        self, event_type: ConfigurationEvent | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get recent configuration events.

        Args:
            event_type: Optional specific event type to filter
            limit: Maximum number of events to return

        Returns:
            List of recent events
        """
        with self._lock:
            events = list(self._events)

            if event_type:
                events = [e for e in events if e["event"] == event_type]

            # Return most recent events first
            return list(reversed(events))[:limit]

    def reset_metrics(self) -> None:
        """Reset all metrics and counters."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()
            self._events.clear()
            self._event_counts.clear()
            self._access_patterns.clear()
            self._load_times.clear()
            self._validation_times.clear()
            self._cache_performance = {
                "total_requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "hit_rate": 0.0,
            }
            self._error_counts.clear()
            self._recent_errors.clear()
            self._health_status = "healthy"
            self._health_checks.clear()
            self._start_time = time.time()

    def _update_event_metrics(
        self,
        event: ConfigurationEvent,
        details: dict[str, Any] | None,
        timestamp: float,
    ) -> None:
        """Update specific metrics based on event type."""
        if event == ConfigurationEvent.CONFIG_LOADED:
            if details and "load_time" in details:
                self._load_times.append(details["load_time"])

        elif event == ConfigurationEvent.CONFIG_VALIDATED:
            if details and "validation_time" in details:
                self._validation_times.append(details["validation_time"])

        elif event in [ConfigurationEvent.CACHE_HIT, ConfigurationEvent.CACHE_MISS]:
            # Cache metrics are updated via record_cache_performance
            pass

        elif event in [
            ConfigurationEvent.CONFIG_ERROR,
            ConfigurationEvent.VALIDATION_ERROR,
        ]:
            self._counters["total_errors"] += 1

    def _get_performance_summary(self) -> dict[str, Any]:
        """Get performance metrics summary."""
        summary = {}

        # Load time statistics
        if self._load_times:
            load_times = list(self._load_times)
            summary["load_time"] = {
                "avg": sum(load_times) / len(load_times),
                "min": min(load_times),
                "max": max(load_times),
                "count": len(load_times),
            }

        # Validation time statistics
        if self._validation_times:
            val_times = list(self._validation_times)
            summary["validation_time"] = {
                "avg": sum(val_times) / len(val_times),
                "min": min(val_times),
                "max": max(val_times),
                "count": len(val_times),
            }

        return summary

    def _get_access_patterns_summary(self) -> dict[str, Any]:
        """Get access patterns summary."""
        if not self._enable_detailed_tracking:
            return {"tracking_disabled": True}

        patterns = dict(self._access_patterns)

        # Sort by access frequency
        sorted_patterns = sorted(
            patterns.items(), key=lambda x: x[1]["access_frequency"], reverse=True
        )

        return {
            "total_keys": len(patterns),
            "top_accessed_keys": sorted_patterns[:10],
            "total_accesses": sum(p["count"] for p in patterns.values()),
        }

    def _update_health_status(self) -> None:
        """Update overall health status based on error rates and metrics."""
        runtime = time.time() - self._start_time

        if runtime < 60:  # Not enough data yet
            self._health_status = "healthy"
            return

        # Calculate error rate (errors per minute)
        total_errors = sum(self._error_counts.values())
        error_rate = total_errors / (runtime / 60)

        # Health thresholds
        if error_rate > 10:  # More than 10 errors per minute
            self._health_status = "unhealthy"
        elif (
            error_rate > 3 or self._cache_performance.get("hit_rate", 1.0) < 0.5
        ):  # More than 3 errors per minute
            self._health_status = "degraded"
        else:
            self._health_status = "healthy"


# Global metrics instance
_global_metrics: ConfigurationMetrics | None = None
_metrics_lock = threading.Lock()


def get_config_metrics() -> ConfigurationMetrics:
    """Get the global configuration metrics instance.

    Returns:
        Global configuration metrics instance
    """
    global _global_metrics

    if _global_metrics is None:
        with _metrics_lock:
            if _global_metrics is None:
                _global_metrics = ConfigurationMetrics()

    return _global_metrics


def record_config_event(
    event: ConfigurationEvent,
    details: dict[str, Any] | None = None,
    tags: dict[str, str] | None = None,
) -> None:
    """Record a configuration event in global metrics.

    Args:
        event: Configuration event type
        details: Optional event details
        tags: Optional event tags
    """
    metrics = get_config_metrics()
    metrics.record_event(event, details, tags)


def time_operation(operation_name: str) -> Callable:
    """Decorator to time configuration operations.

    Args:
        operation_name: Name of the operation being timed

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            success = True

            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                success = False
                raise
            finally:
                duration = time.time() - start_time
                metrics = get_config_metrics()
                metrics.record_timing(operation_name, duration, success)

        return wrapper

    return decorator
