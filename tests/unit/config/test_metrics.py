"""Unit tests for configuration metrics functionality.

This module tests the configuration metrics and monitoring system including
event tracking, performance metrics, error monitoring, and health status.
"""

import threading
import time
from unittest.mock import patch

import pytest

from src.config.metrics import (
    ConfigurationEvent,
    ConfigurationMetrics,
    get_config_metrics,
    record_config_event,
    time_operation,
)


class TestConfigurationMetrics:
    """Tests for ConfigurationMetrics class functionality."""

    def test_metrics_initialization(self):
        """
        Why: Ensure metrics system initializes with proper state for tracking
        What: Tests that metrics initializes with clean counters and tracking state
        How: Creates metrics instance and verifies initial state
        """
        metrics = ConfigurationMetrics()

        assert len(metrics._counters) == 0
        assert len(metrics._gauges) == 0
        assert len(metrics._events) == 0
        assert len(metrics._error_counts) == 0
        assert metrics._health_status == "healthy"
        assert metrics._enable_detailed_tracking is True

    def test_metrics_initialization_without_detailed_tracking(self):
        """
        Why: Allow disabling detailed tracking for performance-sensitive environments
        What: Tests that detailed tracking can be disabled during initialization
        How: Creates metrics with detailed tracking disabled and verifies state
        """
        metrics = ConfigurationMetrics(enable_detailed_tracking=False)

        assert metrics._enable_detailed_tracking is False

    def test_record_event_basic(self):
        """
        Why: Ensure events are properly recorded for system monitoring
        What: Tests that record_event() stores events with correct data
        How: Records events and verifies they are stored with proper structure
        """
        metrics = ConfigurationMetrics()

        # Record an event
        details = {"load_time": 0.5}
        tags = {"source": "test"}
        metrics.record_event(ConfigurationEvent.CONFIG_LOADED, details, tags)

        # Verify event was recorded
        assert len(metrics._events) == 1
        assert metrics._event_counts[ConfigurationEvent.CONFIG_LOADED] == 1

        # Check event data
        event = metrics._events[0]
        assert event["event"] == ConfigurationEvent.CONFIG_LOADED
        assert event["details"] == details
        assert event["tags"] == tags
        assert "timestamp" in event

    def test_record_event_without_details_and_tags(self):
        """
        Why: Support simple event recording without additional metadata
        What: Tests that events can be recorded with minimal parameters
        How: Records event with no details/tags and verifies proper storage
        """
        metrics = ConfigurationMetrics()

        metrics.record_event(ConfigurationEvent.CACHE_HIT)

        assert len(metrics._events) == 1
        event = metrics._events[0]
        assert event["event"] == ConfigurationEvent.CACHE_HIT
        assert event["details"] == {}
        assert event["tags"] == {}

    def test_record_timing_success(self):
        """
        Why: Track operation performance for optimization and monitoring
        What: Tests timing information recorded correctly for successful operations
        How: Records timing and verifies storage in timers and histograms
        """
        metrics = ConfigurationMetrics()

        operation = "test_operation"
        duration = 0.25
        metrics.record_timing(operation, duration, success=True)

        # Check timers
        assert operation in metrics._timers
        assert len(metrics._timers[operation]) == 1
        timing = metrics._timers[operation][0]
        assert timing.operation == operation
        assert timing.duration == duration
        assert timing.success is True

        # Check histograms
        histogram_key = f"{operation}_duration"
        assert histogram_key in metrics._histograms
        assert metrics._histograms[histogram_key] == [duration]

        # Check success counter
        assert metrics._counters[f"{operation}_success"] == 1

    def test_record_timing_failure(self):
        """
        Why: Track operation failures for error monitoring and debugging
        What: Tests that failed operation timing is recorded correctly
        How: Records failed timing and verifies failure counter increment
        """
        metrics = ConfigurationMetrics()

        operation = "failing_operation"
        duration = 0.1
        metrics.record_timing(operation, duration, success=False)

        # Check failure counter
        assert metrics._counters[f"{operation}_failure"] == 1
        assert f"{operation}_success" not in metrics._counters

        # Timing should still be recorded
        assert len(metrics._timers[operation]) == 1

    def test_record_timing_with_tags(self):
        """
        Why: Support categorized timing metrics for detailed analysis
        What: Tests that timing can include tags for categorization
        How: Records timing with tags and verifies tag storage
        """
        metrics = ConfigurationMetrics()

        tags = {"provider": "redis", "environment": "test"}
        metrics.record_timing("queue_operation", 0.05, tags=tags)

        timing = metrics._timers["queue_operation"][0]
        assert timing.tags == tags

    def test_record_access_pattern_enabled(self):
        """
        Why: Track configuration access patterns for optimization insights
        What: Tests that access patterns are recorded when detailed tracking enabled
        How: Records access patterns and verifies tracking data
        """
        metrics = ConfigurationMetrics(enable_detailed_tracking=True)

        key = "database.url"
        metrics.record_access_pattern(key, "read")

        # Check access pattern tracking
        pattern = metrics._access_patterns[key]
        assert pattern["count"] == 1
        assert pattern["first_access"] is not None
        assert pattern["last_access"] is not None

        # Check general counter
        assert metrics._counters["access_read"] == 1

    def test_record_access_pattern_disabled(self):
        """
        Why: Allow disabling detailed tracking for performance optimization
        What: Tests that access patterns are not recorded when tracking disabled
        How: Records patterns with tracking disabled and verifies no tracking
        """
        metrics = ConfigurationMetrics(enable_detailed_tracking=False)

        metrics.record_access_pattern("database.url", "read")

        # Should not track patterns when disabled
        assert len(metrics._access_patterns) == 0

    def test_record_access_pattern_frequency_calculation(self):
        """
        Why: Calculate access frequency for identifying hot configuration paths
        What: Tests that access frequency is calculated correctly over time
        How: Records multiple accesses with time delays and verifies frequency
        """
        metrics = ConfigurationMetrics(enable_detailed_tracking=True)

        key = "system.environment"

        # Record first access
        metrics.record_access_pattern(key)
        time.sleep(0.01)  # Small delay

        # Record second access
        metrics.record_access_pattern(key)

        pattern = metrics._access_patterns[key]
        assert pattern["count"] == 2
        assert pattern["access_frequency"] > 0  # Should have calculated frequency

    def test_record_cache_performance(self):
        """
        Why: Monitor cache effectiveness for performance optimization
        What: Tests that cache performance metrics are recorded correctly
        How: Records cache performance and verifies metric calculation
        """
        metrics = ConfigurationMetrics()

        hits = 75
        misses = 25
        evictions = 5
        metrics.record_cache_performance(hits, misses, evictions)

        cache_perf = metrics._cache_performance
        assert cache_perf["cache_hits"] == hits
        assert cache_perf["cache_misses"] == misses
        assert cache_perf["total_requests"] == hits + misses
        assert cache_perf["hit_rate"] == 0.75  # 75/100
        assert metrics._counters["cache_evictions"] == evictions

    def test_record_cache_performance_zero_requests(self):
        """
        Why: Handle edge case of zero cache requests gracefully
        What: Tests that cache performance handles zero total requests
        How: Records zero hits/misses and verifies hit rate calculation
        """
        metrics = ConfigurationMetrics()

        metrics.record_cache_performance(0, 0)

        cache_perf = metrics._cache_performance
        assert cache_perf["total_requests"] == 0
        assert cache_perf["hit_rate"] == 0.0  # Should not divide by zero

    def test_record_error(self):
        """
        Why: Track configuration errors for system health monitoring
        What: Tests that errors are recorded with proper categorization
        How: Records errors and verifies error tracking and health impact
        """
        metrics = ConfigurationMetrics()

        error_type = "validation_error"
        error_message = "Invalid configuration value"
        context = {"field": "database.url", "value": "invalid"}

        metrics.record_error(error_type, error_message, context)

        # Check error counts
        assert metrics._error_counts[error_type] == 1
        assert metrics._counters[f"error_{error_type}"] == 1

        # Check recent errors
        assert len(metrics._recent_errors) == 1
        error_data = metrics._recent_errors[0]
        assert error_data["type"] == error_type
        assert error_data["message"] == error_message
        assert error_data["context"] == context

    def test_increment_counter(self):
        """
        Why: Support custom metric counters for application-specific tracking
        What: Tests that custom counters can be incremented
        How: Increments counters and verifies correct values
        """
        metrics = ConfigurationMetrics()

        # Increment counter by default amount
        metrics.increment_counter("custom_metric")
        assert metrics._counters["custom_metric"] == 1

        # Increment counter by specific amount
        metrics.increment_counter("custom_metric", 5)
        assert metrics._counters["custom_metric"] == 6

    def test_set_gauge(self):
        """
        Why: Support gauge metrics for current state values
        What: Tests that gauge values can be set and updated
        How: Sets gauge values and verifies storage
        """
        metrics = ConfigurationMetrics()

        # Set gauge value
        metrics.set_gauge("queue_size", 42.5)
        assert metrics._gauges["queue_size"] == 42.5

        # Update gauge value
        metrics.set_gauge("queue_size", 38.0)
        assert metrics._gauges["queue_size"] == 38.0

    def test_get_metrics_summary(self):
        """
        Why: Provide comprehensive view of all metrics for monitoring dashboards
        What: Tests that metrics summary includes all tracked data
        How: Records various metrics and verifies summary completeness
        """
        metrics = ConfigurationMetrics()

        # Record some data
        metrics.increment_counter("test_counter", 5)
        metrics.set_gauge("test_gauge", 42.0)
        metrics.record_event(ConfigurationEvent.CONFIG_LOADED)
        metrics.record_error("test_error", "Test error message")

        summary = metrics.get_metrics_summary()

        # Check summary structure
        assert "runtime_seconds" in summary
        assert "health_status" in summary
        assert "counters" in summary
        assert "gauges" in summary
        assert "event_counts" in summary
        assert "error_summary" in summary
        assert "performance_summary" in summary

        # Check specific values
        assert summary["counters"]["test_counter"] == 5
        assert summary["gauges"]["test_gauge"] == 42.0
        assert summary["event_counts"]["config_loaded"] == 1
        assert summary["error_summary"]["total_errors"] == 1

    def test_get_timing_statistics(self):
        """
        Why: Provide detailed timing analysis for performance optimization
        What: Tests that timing statistics include percentiles and aggregates
        How: Records multiple timings and verifies statistical calculations
        """
        metrics = ConfigurationMetrics()

        operation = "test_operation"
        durations = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Record multiple timings
        for duration in durations:
            metrics.record_timing(operation, duration)

        stats = metrics.get_timing_statistics(operation)

        assert stats["count"] == 5
        assert stats["min"] == 0.1
        assert stats["max"] == 0.5
        assert stats["avg"] == 0.3
        assert stats["median"] == 0.3
        assert stats["total"] == 1.5

    def test_get_timing_statistics_empty(self):
        """
        Why: Handle case where no timing data exists for operation
        What: Tests that timing statistics handles missing operation gracefully
        How: Requests stats for non-existent operation and verifies response
        """
        metrics = ConfigurationMetrics()

        stats = metrics.get_timing_statistics("nonexistent_operation")
        assert stats == {"count": 0}

    def test_get_recent_events_all(self):
        """
        Why: Support debugging and monitoring by accessing recent events
        What: Tests that recent events can be retrieved in chronological order
        How: Records events and verifies retrieval order and content
        """
        metrics = ConfigurationMetrics()

        # Record multiple events
        metrics.record_event(ConfigurationEvent.CONFIG_LOADED)
        metrics.record_event(ConfigurationEvent.CACHE_HIT)
        metrics.record_event(ConfigurationEvent.CONFIG_VALIDATED)

        events = metrics.get_recent_events()

        # Should return most recent first
        assert len(events) == 3
        assert events[0]["event"] == ConfigurationEvent.CONFIG_VALIDATED
        assert events[2]["event"] == ConfigurationEvent.CONFIG_LOADED

    def test_get_recent_events_filtered(self):
        """
        Why: Support filtered event retrieval for specific debugging scenarios
        What: Tests that events can be filtered by type
        How: Records mixed events and retrieves specific type
        """
        metrics = ConfigurationMetrics()

        # Record different event types
        metrics.record_event(ConfigurationEvent.CONFIG_LOADED)
        metrics.record_event(ConfigurationEvent.CACHE_HIT)
        metrics.record_event(ConfigurationEvent.CACHE_HIT)

        # Filter for cache hits only
        cache_events = metrics.get_recent_events(ConfigurationEvent.CACHE_HIT)

        assert len(cache_events) == 2
        for event in cache_events:
            assert event["event"] == ConfigurationEvent.CACHE_HIT

    def test_reset_metrics(self):
        """
        Why: Support metrics reset for testing and fresh monitoring periods
        What: Tests that reset_metrics() clears all tracked data
        How: Records various metrics and verifies complete reset
        """
        metrics = ConfigurationMetrics()

        # Record various data
        metrics.increment_counter("test_counter")
        metrics.set_gauge("test_gauge", 42.0)
        metrics.record_event(ConfigurationEvent.CONFIG_LOADED)
        metrics.record_error("test_error", "Test message")

        # Verify data exists
        assert len(metrics._counters) > 0
        assert len(metrics._gauges) > 0
        assert len(metrics._events) > 0
        assert len(metrics._error_counts) > 0

        # Reset metrics
        metrics.reset_metrics()

        # Verify everything is cleared
        assert len(metrics._counters) == 0
        assert len(metrics._gauges) == 0
        assert len(metrics._events) == 0
        assert len(metrics._error_counts) == 0
        assert metrics._health_status == "healthy"

    def test_health_status_degraded_on_high_error_rate(self):
        """
        Why: Automatically detect system health issues based on error patterns
        What: Tests that health status changes when error rate exceeds thresholds
        How: Records errors over time and verifies health status updates
        """
        metrics = ConfigurationMetrics()

        # Simulate high error rate by backdating start time
        metrics._start_time = time.time() - 120  # 2 minutes ago

        # Record many errors
        for i in range(10):
            metrics.record_error("test_error", f"Error {i}")

        # Health should be degraded due to high error rate
        assert metrics._health_status in ["degraded", "unhealthy"]

    def test_thread_safety(self):
        """
        Why: Ensure metrics collection is safe in multi-threaded environments
        What: Tests that concurrent metric operations don't cause race conditions
        How: Runs multiple threads recording metrics simultaneously
        """
        metrics = ConfigurationMetrics()

        errors = []

        def metric_worker():
            try:
                for _ in range(10):
                    metrics.increment_counter("thread_test")
                    metrics.record_event(ConfigurationEvent.CACHE_HIT)
                    metrics.record_timing("thread_operation", 0.1)
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=metric_worker) for _ in range(5)]
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should not have errors
        assert len(errors) == 0
        assert metrics._counters["thread_test"] == 50  # 10 operations x 5 threads


class TestGlobalMetricsFunctions:
    """Tests for global metrics convenience functions."""

    def test_get_config_metrics_singleton(self):
        """
        Why: Ensure global metrics provides consistent instance across application
        What: Tests that get_config_metrics() returns same instance
        How: Calls function multiple times and verifies same instance
        """
        metrics1 = get_config_metrics()
        metrics2 = get_config_metrics()
        assert metrics1 is metrics2

    def test_record_config_event_global(self):
        """
        Why: Allow global event recording from anywhere in application
        What: Tests that record_config_event() updates global metrics
        How: Records event globally and verifies it appears in global metrics
        """
        # Clear any existing events
        global_metrics = get_config_metrics()
        global_metrics.reset_metrics()

        # Record event globally
        details = {"test": "data"}
        record_config_event(ConfigurationEvent.CONFIG_LOADED, details)

        # Verify event in global metrics
        events = global_metrics.get_recent_events()
        assert len(events) == 1
        assert events[0]["event"] == ConfigurationEvent.CONFIG_LOADED
        assert events[0]["details"] == details

    def test_time_operation_decorator_success(self):
        """
        Why: Provide convenient timing decorator for configuration operations
        What: Tests time_operation decorator records timing for success
        How: Decorates function and verifies timing is recorded
        """
        global_metrics = get_config_metrics()
        global_metrics.reset_metrics()

        @time_operation("test_function")
        def test_function():
            time.sleep(0.01)  # Small delay for measurable timing
            return "success"

        result = test_function()

        # Function should execute normally
        assert result == "success"

        # Timing should be recorded
        stats = global_metrics.get_timing_statistics("test_function")
        assert stats["count"] == 1
        assert stats["min"] > 0
        assert global_metrics._counters["test_function_success"] == 1

    def test_time_operation_decorator_failure(self):
        """
        Why: Ensure timing decorator properly handles and records failures
        What: Tests that decorator records failure timing when function raises exception
        How: Decorates failing function and verifies failure timing
        """
        global_metrics = get_config_metrics()
        global_metrics.reset_metrics()

        @time_operation("failing_function")
        def failing_function():
            raise ValueError("Test error")

        # Function should still raise exception
        with pytest.raises(ValueError, match="Test error"):
            failing_function()

        # Failure timing should be recorded
        assert global_metrics._counters["failing_function_failure"] == 1
        stats = global_metrics.get_timing_statistics("failing_function")
        assert stats["count"] == 1
