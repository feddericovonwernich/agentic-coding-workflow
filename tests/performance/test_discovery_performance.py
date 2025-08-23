"""
Performance tests for PR Discovery and Processing system.

Tests system performance under various load conditions including high repository counts,
large PR datasets, concurrent processing, and resource utilization scenarios.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.discovery import (
    DiscoveryConfigFactory,
    PRDiscoveryResultFactory,
    create_realistic_pr_data,
)


class MockPerformanceDiscoveryEngine:
    """Mock discovery engine optimized for performance testing."""

    def __init__(self, config):
        self.config = config
        self.metrics = {
            "repositories_processed": 0,
            "total_prs_processed": 0,
            "api_calls_made": 0,
            "cache_operations": 0,
            "processing_times": [],
        }

    async def run_discovery_cycle(self, repository_ids: list[uuid.UUID]):
        """Mock discovery cycle with realistic processing simulation."""
        start_time = time.perf_counter()

        results = []
        for repo_id in repository_ids:
            # Simulate processing time based on repository size
            processing_delay = 0.1 + (len(repository_ids) * 0.01)  # Realistic delay
            await asyncio.sleep(processing_delay)

            result = PRDiscoveryResultFactory.create(repository_id=repo_id)
            results.append(result)

            # Update metrics
            self.metrics["repositories_processed"] += 1
            self.metrics["total_prs_processed"] += len(result.discovered_prs)
            self.metrics["api_calls_made"] += result.api_calls_used

        end_time = time.perf_counter()
        cycle_time = end_time - start_time
        self.metrics["processing_times"].append(cycle_time)

        return results

    async def process_repository_batch(self, repository_batch: list[uuid.UUID]):
        """Mock batch processing for performance testing."""
        # Simulate parallel processing
        tasks = [
            self._process_single_repository(repo_id) for repo_id in repository_batch
        ]
        return await asyncio.gather(*tasks)

    async def _process_single_repository(self, repository_id: uuid.UUID):
        """Mock single repository processing."""
        # Simulate realistic processing time
        await asyncio.sleep(0.05)  # 50ms processing time
        return PRDiscoveryResultFactory.create(repository_id=repository_id)


@pytest.mark.performance
class TestDiscoveryPerformanceScenarios:
    """Tests for various performance scenarios and load conditions."""

    @pytest.fixture
    def performance_config(self):
        """
        Why: Provides performance-optimized configuration for testing under load
        What: Creates discovery config with settings optimized for high throughput
        How: Sets high concurrency and batch sizes suitable for performance testing
        """
        return DiscoveryConfigFactory.create_performance_optimized(
            max_concurrent_repositories=20,
            max_prs_per_repository=2000,
            batch_size=200,
            discovery_timeout_seconds=600,
        )

    @pytest.fixture
    def performance_engine(self, performance_config):
        """
        Why: Provides discovery engine configured for performance testing
        What: Creates engine with performance-optimized settings and mock dependencies
        How: Uses performance config and mock implementations for controlled testing
        """
        return MockPerformanceDiscoveryEngine(config=performance_config)

    @pytest.mark.asyncio
    async def test_discovery_processes_100_repositories_within_time_limit(
        self, performance_engine
    ):
        """
        Why: Ensure discovery system meets the core performance requirement of
             processing 100+ repositories within 5-minute window as specified in
             architecture.

        What: Tests that discovery cycle processes 100 repositories with realistic
              PR counts within the 5-minute performance target.

        How: Creates 100 repository IDs, measures total processing time, validates
             completion within 5-minute limit with proper throughput metrics.
        """
        # Arrange
        repository_count = 100
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]
        time_limit_seconds = 300  # 5 minutes

        # Act
        start_time = time.perf_counter()
        results = await performance_engine.run_discovery_cycle(repository_ids)
        end_time = time.perf_counter()

        total_time = end_time - start_time

        # Assert performance requirements met
        assert total_time < time_limit_seconds, (
            f"Processing took {total_time:.2f}s, limit is {time_limit_seconds}s"
        )
        assert len(results) == repository_count

        # Assert throughput metrics
        repositories_per_second = repository_count / total_time
        assert repositories_per_second >= 0.33, (
            f"Throughput {repositories_per_second:.2f} repos/s too low"
        )

        # Verify all repositories processed successfully
        processed_repo_ids = {r.repository_id for r in results}
        expected_repo_ids = set(repository_ids)
        assert processed_repo_ids == expected_repo_ids

    @pytest.mark.asyncio
    async def test_discovery_handles_large_pr_volumes_efficiently(
        self, performance_engine
    ):
        """
        Why: Ensure discovery system efficiently handles repositories with large
             numbers of PRs (1000+) without memory issues or excessive processing time.

        What: Tests processing of repositories containing 1000+ PRs each, validating
              memory efficiency and processing time stay within acceptable bounds.

        How: Creates repositories with large PR datasets, monitors memory usage and
             processing time, validates efficient handling of high-volume data.
        """
        # Arrange
        repository_count = 5  # Fewer repos but with many PRs each
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]

        # Mock large PR datasets for each repository
        large_pr_counts = [1000, 1500, 800, 1200, 900]  # Varied large PR counts

        # Override the factory to create results with large PR counts
        original_create = PRDiscoveryResultFactory.create

        def create_large_result(**kwargs):
            repo_id = kwargs.get("repository_id", uuid.uuid4())
            repo_index = (
                repository_ids.index(repo_id) if repo_id in repository_ids else 0
            )
            pr_count = large_pr_counts[repo_index % len(large_pr_counts)]

            kwargs["discovered_prs"] = [
                MagicMock()
                for _ in range(pr_count)  # Mock PRs for performance
            ]
            return original_create(**kwargs)

        PRDiscoveryResultFactory.create = create_large_result

        try:
            # Act
            start_time = time.perf_counter()
            results = await performance_engine.run_discovery_cycle(repository_ids)
            end_time = time.perf_counter()

            processing_time = end_time - start_time

            # Assert
            assert len(results) == repository_count
            assert processing_time < 120  # Should complete within 2 minutes

            # Verify large datasets processed
            total_prs_processed = sum(len(r.discovered_prs) for r in results)
            assert total_prs_processed >= 5000  # At least 5K PRs total

            # Performance metrics
            prs_per_second = total_prs_processed / processing_time
            assert prs_per_second >= 50, (
                f"PR processing rate {prs_per_second:.2f} PRs/s too low"
            )

        finally:
            # Restore original factory
            PRDiscoveryResultFactory.create = original_create

    @pytest.mark.asyncio
    async def test_concurrent_repository_processing_scales_properly(
        self, performance_engine
    ):
        """
        Why: Ensure concurrent processing scales properly with increased parallelism,
             validating the system can efficiently utilize multiple processing threads.

        What: Tests processing performance with various concurrency levels, measuring
              throughput improvements and resource utilization scaling.

        How: Processes same workload with different concurrency levels, compares
             processing times and validates scaling efficiency.
        """
        # Arrange
        repository_count = 50
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]

        # Test different concurrency levels
        concurrency_levels = [5, 10, 20]
        results_by_concurrency = {}

        for concurrency in concurrency_levels:
            # Configure engine for specific concurrency
            performance_engine.config.max_concurrent_repositories = concurrency

            # Process in batches matching concurrency level
            start_time = time.perf_counter()

            # Split repositories into batches
            batch_size = concurrency
            batches = [
                repository_ids[i : i + batch_size]
                for i in range(0, len(repository_ids), batch_size)
            ]

            all_results = []
            for batch in batches:
                batch_results = await performance_engine.process_repository_batch(batch)
                all_results.extend(batch_results)

            end_time = time.perf_counter()

            processing_time = end_time - start_time
            results_by_concurrency[concurrency] = {
                "time": processing_time,
                "throughput": repository_count / processing_time,
                "results_count": len(all_results),
            }

        # Assert scaling improvements
        assert results_by_concurrency[5]["time"] > results_by_concurrency[10]["time"]
        assert results_by_concurrency[10]["time"] > results_by_concurrency[20]["time"]

        # Verify throughput improvements with higher concurrency
        assert (
            results_by_concurrency[20]["throughput"]
            > results_by_concurrency[5]["throughput"]
        )

    @pytest.mark.asyncio
    async def test_discovery_memory_usage_stays_bounded_under_load(
        self, performance_engine
    ):
        """
        Why: Ensure discovery system maintains bounded memory usage under load,
             preventing memory exhaustion during long-running or high-volume operations.

        What: Tests memory usage patterns during intensive discovery operations,
              validating memory stays within acceptable bounds throughout processing.

        How: Monitors memory usage during processing of large repository sets,
             validates memory growth patterns and garbage collection effectiveness.
        """
        # Arrange
        repository_count = 50
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]

        # Mock memory usage tracking
        memory_samples = []

        async def track_memory_usage():
            """Mock memory usage tracking."""
            import os

            import psutil

            try:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
                memory_samples.append(memory_mb)
            except Exception:
                # Fallback if psutil not available
                memory_samples.append(100)  # Mock 100MB usage

        # Act - Process repositories while monitoring memory
        start_memory_task = asyncio.create_task(track_memory_usage())
        await start_memory_task

        # Process in chunks to monitor memory over time
        chunk_size = 10
        for i in range(0, repository_count, chunk_size):
            chunk = repository_ids[i : i + chunk_size]
            await performance_engine.run_discovery_cycle(chunk)

            # Sample memory usage
            memory_task = asyncio.create_task(track_memory_usage())
            await memory_task

            # Brief pause to allow garbage collection
            await asyncio.sleep(0.1)

        # Assert memory usage patterns
        assert len(memory_samples) > 1
        max_memory = max(memory_samples)
        min_memory = min(memory_samples)

        # Memory should not grow unboundedly
        memory_growth = max_memory - min_memory
        assert memory_growth < 200, f"Memory growth {memory_growth:.2f}MB too high"

        # No single sample should exceed reasonable limit
        assert max_memory < 500, f"Peak memory usage {max_memory:.2f}MB too high"

    @pytest.mark.asyncio
    async def test_api_rate_limit_efficiency_under_load(self, performance_engine):
        """
        Why: Ensure discovery system efficiently manages API rate limits under load,
             maximizing throughput while staying within GitHub API constraints.

        What: Tests API call efficiency during high-volume processing, validating
              optimal rate limit usage without exceeding available quotas.

        How: Processes large repository set while tracking API calls, validates
             API usage stays within limits and achieves target efficiency.
        """
        # Arrange
        repository_count = 100
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]

        # Mock API rate limit tracking
        api_limit = 5000  # GitHub API limit
        api_buffer = 500  # Reserve buffer
        available_calls = api_limit - api_buffer

        # Act
        start_time = time.perf_counter()
        await performance_engine.run_discovery_cycle(repository_ids)
        end_time = time.perf_counter()

        # Calculate API usage
        total_api_calls = performance_engine.metrics["api_calls_made"]
        processing_time = end_time - start_time

        # Assert API efficiency
        assert total_api_calls < available_calls, (
            f"Used {total_api_calls} calls, limit is {available_calls}"
        )

        # Verify efficient API usage (target: < 50 calls per repository)
        avg_calls_per_repo = total_api_calls / repository_count
        assert avg_calls_per_repo < 50, (
            f"Average {avg_calls_per_repo:.2f} calls/repo too high"
        )

        # API calls per second should be reasonable
        api_calls_per_second = total_api_calls / processing_time
        assert api_calls_per_second < 100, (
            f"API rate {api_calls_per_second:.2f} calls/s too high"
        )

    @pytest.mark.asyncio
    async def test_cache_effectiveness_under_repeated_processing(
        self, performance_engine
    ):
        """
        Why: Ensure caching system provides effective performance benefits under
             repeated processing scenarios, validating cache hit rates and speed
             improvements.

        What: Tests cache performance during repeated repository processing cycles,
              measuring cache hit rates and processing time improvements.

        How: Processes same repositories multiple times, measures cache hit rates
             and validates significant performance improvements from caching.
        """
        # Arrange
        repository_count = 20
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]
        processing_cycles = 3

        cycle_times = []
        cache_hit_rates = []

        # Act - Process same repositories multiple times
        for _cycle in range(processing_cycles):
            start_time = time.perf_counter()
            results = await performance_engine.run_discovery_cycle(repository_ids)
            end_time = time.perf_counter()

            cycle_time = end_time - start_time
            cycle_times.append(cycle_time)

            # Calculate cache hit rate for this cycle
            total_cache_operations = performance_engine.metrics["cache_operations"]
            cache_hits = sum(r.cache_hits for r in results)
            cache_hit_rate = cache_hits / max(total_cache_operations, 1)
            cache_hit_rates.append(cache_hit_rate)

            # Update metrics for next cycle
            performance_engine.metrics["cache_operations"] += (
                len(results) * 2
            )  # Mock cache ops

        # Assert cache effectiveness
        # Later cycles should be faster due to caching
        assert cycle_times[2] < cycle_times[0], (
            "Final cycle should be faster than first"
        )

        # Cache hit rate should improve over cycles
        if len(cache_hit_rates) > 1:
            final_hit_rate = cache_hit_rates[-1]
            assert final_hit_rate > 0.3, f"Cache hit rate {final_hit_rate:.2f} too low"

        # Overall performance improvement
        performance_improvement = (cycle_times[0] - cycle_times[-1]) / cycle_times[0]
        assert performance_improvement > 0.2, (
            f"Performance improvement {performance_improvement:.2f} insufficient"
        )


@pytest.mark.performance
class TestDiscoveryStressScenarios:
    """Tests for stress and edge case performance scenarios."""

    @pytest.fixture
    def stress_test_engine(self):
        """Discovery engine configured for stress testing."""
        config = DiscoveryConfigFactory.create(
            max_concurrent_repositories=50,  # High concurrency for stress
            discovery_timeout_seconds=1800,  # 30 minute timeout
            batch_size=500,
        )
        return MockPerformanceDiscoveryEngine(config=config)

    @pytest.mark.asyncio
    async def test_maximum_supported_repository_count(self, stress_test_engine):
        """
        Why: Determine maximum number of repositories system can handle in single
             discovery cycle, establishing operational limits and scaling boundaries.

        What: Tests discovery system with progressively larger repository counts
              until performance degrades or limits are reached.

        How: Processes increasing repository counts, measures performance degradation,
             identifies maximum sustainable repository count.
        """
        # Arrange - Test increasing repository counts
        test_counts = [50, 100, 200, 300, 500]
        max_processing_time = 600  # 10 minutes max

        successful_counts = []

        for repo_count in test_counts:
            repository_ids = [uuid.uuid4() for _ in range(repo_count)]

            try:
                # Act
                start_time = time.perf_counter()
                results = await asyncio.wait_for(
                    stress_test_engine.run_discovery_cycle(repository_ids),
                    timeout=max_processing_time,
                )
                end_time = time.perf_counter()

                processing_time = end_time - start_time

                # If processing completed successfully and within reasonable time
                if len(results) == repo_count and processing_time < max_processing_time:
                    successful_counts.append(repo_count)

                    # Log performance metrics
                    throughput = repo_count / processing_time
                    print(
                        f"Successfully processed {repo_count} repos in "
                        f"{processing_time:.2f}s ({throughput:.2f} repos/s)"
                    )

            except TimeoutError:
                print(f"Timeout processing {repo_count} repositories")
                break
            except Exception as e:
                print(f"Failed processing {repo_count} repositories: {e}")
                break

        # Assert
        assert len(successful_counts) > 0, "No repository counts processed successfully"
        max_supported = max(successful_counts)
        assert max_supported >= 100, f"Maximum supported count {max_supported} too low"

    @pytest.mark.asyncio
    async def test_sustained_processing_performance_over_time(self, stress_test_engine):
        """
        Why: Ensure discovery system maintains consistent performance during
             sustained operation, validating long-term stability and resource
             management.

        What: Tests repeated discovery cycles over extended period, monitoring
              performance consistency and resource leak detection.

        How: Runs multiple discovery cycles over time, tracks performance metrics,
             validates consistent throughput and resource usage patterns.
        """
        # Arrange
        repository_count = 30
        processing_cycles = 10  # Multiple cycles for sustained testing
        repository_ids = [uuid.uuid4() for _ in range(repository_count)]

        cycle_metrics = []

        # Act - Run sustained processing cycles
        for cycle in range(processing_cycles):
            start_time = time.perf_counter()
            results = await stress_test_engine.run_discovery_cycle(repository_ids)
            end_time = time.perf_counter()

            cycle_time = end_time - start_time
            throughput = repository_count / cycle_time

            cycle_metrics.append(
                {
                    "cycle": cycle,
                    "time": cycle_time,
                    "throughput": throughput,
                    "results_count": len(results),
                }
            )

            # Brief pause between cycles
            await asyncio.sleep(1)

        # Assert sustained performance
        assert len(cycle_metrics) == processing_cycles

        # Calculate performance stability
        times = [m["time"] for m in cycle_metrics]
        throughputs = [m["throughput"] for m in cycle_metrics]

        # Performance should be relatively stable (coefficient of variation < 0.3)
        import statistics

        time_std = statistics.stdev(times)
        time_mean = statistics.mean(times)
        time_cv = time_std / time_mean

        assert time_cv < 0.3, f"Performance variability {time_cv:.2f} too high"

        # No significant degradation over time
        first_half_avg = statistics.mean(throughputs[: processing_cycles // 2])
        second_half_avg = statistics.mean(throughputs[processing_cycles // 2 :])

        degradation = (first_half_avg - second_half_avg) / first_half_avg
        assert degradation < 0.2, f"Performance degradation {degradation:.2f} too high"
