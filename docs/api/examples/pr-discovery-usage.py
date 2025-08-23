#!/usr/bin/env python3
"""
PR Discovery API Usage Examples

This file demonstrates comprehensive usage of the PR Discovery system,
including basic setup, performance monitoring, custom strategies, and
error handling patterns.

Requirements:
- Python 3.11+
- All project dependencies installed
- GitHub API access configured
- Database connection configured
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from src.workers.discovery.interfaces import (
    DiscoveredCheckRun,
    DiscoveredPR,
    DiscoveryConfig,
    DiscoveryError,
    DiscoveryPriority,
    PRDiscoveryResult,
    PRDiscoveryStrategy,
)

# Import PR Discovery components
from src.workers.discovery.pr_discovery_engine import PRDiscoveryEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Example 1: Basic PR Discovery Setup
async def basic_discovery_example() -> None:
    """
    Basic example showing how to set up and run PR discovery.

    This example demonstrates:
    - Engine configuration for different scales
    - Basic discovery cycle execution
    - Results processing and metrics
    """
    print("=== Basic PR Discovery Example ===")

    # Configure for medium-scale operation
    config = DiscoveryConfig(
        max_concurrent_repositories=20,
        max_prs_per_repository=500,
        cache_ttl_seconds=300,
        use_etag_caching=True,
        batch_size=50,
        priority_scheduling=True,
    )

    # Setup discovery engine (dependencies would be injected in real usage)
    engine = await setup_mock_discovery_engine(config)

    # Sample repository IDs to process
    repository_ids = [uuid.uuid4() for _ in range(10)]

    print(f"Starting discovery for {len(repository_ids)} repositories...")

    # Run discovery cycle
    start_time = time.time()
    results = await engine.run_discovery_cycle(repository_ids)
    processing_time = time.time() - start_time

    # Process results
    total_prs = sum(len(result.discovered_prs) for result in results)
    total_checks = sum(
        sum(len(pr.check_runs) for pr in result.discovered_prs) for result in results
    )
    total_api_calls = sum(result.api_calls_used for result in results)
    total_cache_hits = sum(result.cache_hits for result in results)
    total_cache_requests = sum(
        result.cache_hits + result.cache_misses for result in results
    )

    cache_hit_rate = (
        (total_cache_hits / total_cache_requests * 100)
        if total_cache_requests > 0
        else 0
    )

    print(f"Discovery completed in {processing_time:.2f} seconds:")
    print(f"  - {len(results)} repositories processed")
    print(f"  - {total_prs} PRs discovered")
    print(f"  - {total_checks} check runs discovered")
    print(f"  - {total_api_calls} API calls made")
    print(f"  - {cache_hit_rate:.1f}% cache hit rate")

    # Show per-repository statistics
    print("\nPer-repository results:")
    for i, result in enumerate(results[:5]):  # Show first 5
        print(
            f"  Repository {i + 1}: "
            f"{len(result.discovered_prs)} PRs, "
            f"{result.processing_time_ms:.0f}ms, "
            f"{len(result.errors)} errors"
        )


# Example 2: Performance Monitoring
async def performance_monitoring_example() -> None:
    """
    Example showing how to monitor discovery performance in real-time.

    This example demonstrates:
    - Real-time status monitoring
    - Performance metrics collection
    - Health status checking
    - Error detection and reporting
    """
    print("\n=== Performance Monitoring Example ===")

    config = DiscoveryConfig(max_concurrent_repositories=15)
    engine = await setup_mock_discovery_engine(config)

    # Simulate ongoing discovery monitoring
    repository_ids = [uuid.uuid4() for _ in range(25)]

    # Start discovery in background
    discovery_task = asyncio.create_task(engine.run_discovery_cycle(repository_ids))

    # Monitor progress
    monitoring_count = 0
    while not discovery_task.done() and monitoring_count < 5:
        status = await engine.get_discovery_status()

        print(f"Discovery Status Check {monitoring_count + 1}:")
        print(f"  Status: {status['status']}")
        print(f"  Progress: {status['current_cycle']['progress_percentage']:.1f}%")
        print(
            f"  Repositories processed: "
            f"{status['current_cycle']['repositories_processed']}"
        )
        print(f"  PRs discovered: {status['current_cycle']['prs_discovered']}")
        print(f"  Active tasks: {status['concurrency']['active_tasks']}")

        # Check for issues
        if status["status"] == "degraded":
            print("  WARNING: System is in degraded state!")
            recent_errors = status.get("recent_errors", [])
            if recent_errors:
                print(f"  Recent errors: {len(recent_errors)}")
                for error in recent_errors[-2:]:
                    print(f"    - {error['type']}: {error['message']}")

        monitoring_count += 1
        await asyncio.sleep(1)  # Check every second

    # Wait for completion and show final results
    results = await discovery_task
    final_status = await engine.get_discovery_status()

    print("\nFinal Results:")
    print(f"  Total repositories: {len(results)}")
    processing_time = final_status["current_cycle"]["processing_time_seconds"]
    print(f"  Processing time: {processing_time:.2f}s")
    cache_stats = final_status.get("cache_stats", {})
    hit_rate = cache_stats.get("hit_rate", 0)
    print(f"  Overall cache hit rate: {hit_rate:.1f}%")


# Example 3: Custom Discovery Strategy
class ExampleCustomDiscoveryStrategy(PRDiscoveryStrategy):
    """
    Example custom PR discovery strategy showing how to implement
    organization-specific discovery logic.
    """

    def __init__(self, github_client: Any, repository_repo: Any) -> None:
        self.github_client = github_client
        self.repository_repo = repository_repo
        self.organization_priorities = {
            "critical-org": DiscoveryPriority.CRITICAL,
            "high-priority-org": DiscoveryPriority.HIGH,
            "standard-org": DiscoveryPriority.NORMAL,
        }

    async def discover_prs(
        self,
        repository_id: uuid.UUID,
        repository_url: str,
        since: datetime | None = None,
        max_prs: int | None = None,
    ) -> PRDiscoveryResult:
        """Custom PR discovery with organization-specific filtering."""
        start_time = time.time()

        try:
            # Mock discovery logic (replace with real GitHub API calls)
            discovered_prs = await self._mock_discover_prs(
                repository_url, since, max_prs
            )

            # Apply custom filtering
            filtered_prs = []
            for pr in discovered_prs:
                if self._should_include_pr(pr):
                    filtered_prs.append(pr)

            processing_time_ms = (time.time() - start_time) * 1000

            return PRDiscoveryResult(
                repository_id=repository_id,
                repository_url=repository_url,
                discovered_prs=filtered_prs,
                discovery_timestamp=datetime.now(UTC),
                api_calls_used=2,  # Mock API usage
                cache_hits=1,  # Mock cache hits
                cache_misses=1,  # Mock cache misses
                processing_time_ms=processing_time_ms,
                errors=[],
            )

        except Exception as e:
            return PRDiscoveryResult(
                repository_id=repository_id,
                repository_url=repository_url,
                discovered_prs=[],
                discovery_timestamp=datetime.now(UTC),
                api_calls_used=0,
                cache_hits=0,
                cache_misses=0,
                processing_time_ms=(time.time() - start_time) * 1000,
                errors=[
                    DiscoveryError(
                        error_type="custom_discovery_error",
                        message=f"Custom discovery failed: {e!s}",
                        context={"repository_id": str(repository_id)},
                        timestamp=datetime.now(UTC),
                        recoverable=True,
                    )
                ],
            )

    async def get_priority(self, repository_id: uuid.UUID) -> DiscoveryPriority:
        """Custom priority logic based on organization."""
        try:
            # Mock repository lookup (replace with real repository access)
            org_name = await self._get_repository_org(repository_id)
            return self.organization_priorities.get(org_name, DiscoveryPriority.NORMAL)
        except Exception:
            return DiscoveryPriority.NORMAL

    def _should_include_pr(self, pr: DiscoveredPR) -> bool:
        """Custom logic for PR inclusion."""
        # Example: Skip bot PRs but include everything else
        bot_authors = ["dependabot[bot]", "renovate[bot]", "github-actions[bot]"]
        return pr.author not in bot_authors

    async def _mock_discover_prs(
        self, repository_url: str, since: datetime | None, max_prs: int | None
    ) -> list[DiscoveredPR]:
        """Mock PR discovery (replace with real GitHub API calls)."""
        # Simulate API delay
        await asyncio.sleep(0.1)

        # Create mock PRs
        prs = []
        pr_count = min(max_prs or 10, 10)  # Limit for example

        for i in range(pr_count):
            pr = DiscoveredPR(
                pr_number=1000 + i,
                title=f"Example PR {i + 1}",
                author=f"developer-{i % 3}",  # Rotate through developers
                state="open",
                draft=i % 5 == 0,  # Every 5th PR is draft
                base_branch="main",
                head_branch=f"feature/example-{i}",
                base_sha=f"abc123{i:03d}",
                head_sha=f"def456{i:03d}",
                url=f"{repository_url}/pull/{1000 + i}",
                body=f"This is example PR {i + 1} for testing",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                merged_at=None,
                metadata={"example": True},
                check_runs=await self._create_mock_check_runs(i),
            )
            prs.append(pr)

        return prs

    async def _create_mock_check_runs(self, pr_index: int) -> list[DiscoveredCheckRun]:
        """Create mock check runs for a PR."""
        checks = []
        check_names = ["build", "test", "lint", "security-scan"]

        for j, name in enumerate(check_names):
            # Make some checks fail for demonstration
            failed = (pr_index + j) % 7 == 0

            check = DiscoveredCheckRun(
                external_id=f"check-{pr_index}-{j}",
                name=name,
                status="completed",
                conclusion="failure" if failed else "success",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                details_url=f"https://example.com/check/{pr_index}-{j}",
                output={"title": f"{name} result", "summary": "Check completed"},
            )
            checks.append(check)

        return checks

    async def _get_repository_org(self, repository_id: uuid.UUID) -> str:
        """Get organization name for repository (mock implementation)."""
        # Mock organization lookup
        org_map = {0: "critical-org", 1: "high-priority-org", 2: "standard-org"}
        return org_map.get(hash(repository_id) % 3, "standard-org")


async def custom_strategy_example() -> None:
    """
    Example showing how to use a custom discovery strategy.

    This example demonstrates:
    - Custom PR filtering logic
    - Organization-based priority assignment
    - Custom error handling
    - Mock GitHub API integration
    """
    print("\n=== Custom Discovery Strategy Example ===")

    # Create custom strategy
    custom_strategy = ExampleCustomDiscoveryStrategy(
        github_client=None,  # Would be real GitHub client
        repository_repo=None,  # Would be real repository
    )

    # Test individual strategy methods
    repository_id = uuid.uuid4()

    print("Testing custom discovery strategy...")

    # Test priority assignment
    priority = await custom_strategy.get_priority(repository_id)
    print(f"Repository priority: {priority.name}")

    # Test PR discovery
    result = await custom_strategy.discover_prs(
        repository_id=repository_id,
        repository_url="https://github.com/example/repo",
        max_prs=5,
    )

    print("Custom discovery result:")
    print(f"  - {len(result.discovered_prs)} PRs discovered")
    print(f"  - {result.processing_time_ms:.0f}ms processing time")
    print(f"  - {result.api_calls_used} API calls")
    print(f"  - {len(result.errors)} errors")

    # Show filtered PR details
    for pr in result.discovered_prs[:3]:  # Show first 3
        failed_checks = sum(1 for check in pr.check_runs if check.is_failed)
        print(
            f"  PR #{pr.pr_number}: {pr.title} "
            f"(Author: {pr.author}, Failed checks: {failed_checks})"
        )


# Example 4: Error Handling and Recovery
async def error_handling_example() -> None:
    """
    Example showing comprehensive error handling patterns.

    This example demonstrates:
    - Handling different error types
    - Partial success scenarios
    - Recovery strategies
    - Error reporting and logging
    """
    print("\n=== Error Handling Example ===")

    config = DiscoveryConfig(max_concurrent_repositories=5)
    engine = await setup_mock_discovery_engine(config)

    # Mix of valid and problematic repository IDs
    repository_ids = [uuid.uuid4() for _ in range(8)]

    print(f"Testing error handling with {len(repository_ids)} repositories...")

    try:
        results = await engine.run_discovery_cycle(repository_ids)

        # Analyze results for errors
        successful_results = [r for r in results if not r.errors]
        failed_results = [r for r in results if r.errors]

        print("Results analysis:")
        print(f"  - {len(successful_results)} repositories processed successfully")
        print(f"  - {len(failed_results)} repositories had errors")

        # Show error details
        if failed_results:
            print("\nError details:")
            for result in failed_results[:3]:  # Show first 3 with errors
                for error in result.errors:
                    print(f"  {error.error_type}: {error.message}")
                    if error.recoverable:
                        print("    (Recoverable: retry possible)")

        # Calculate overall success rate
        total_prs = sum(len(result.discovered_prs) for result in results)
        if total_prs > 0:
            print("\nOverall metrics:")
            print(f"  - {total_prs} total PRs discovered despite errors")
            success_rate = len(successful_results) / len(results) * 100
            print(f"  - Partial success rate: {success_rate:.1f}%")

    except Exception as e:
        print(f"Fatal discovery error: {e}")
        print("This would trigger system-level error handling and recovery")


# Example 5: High-Performance Configuration
async def high_performance_example() -> None:
    """
    Example showing configuration for high-performance scenarios.

    This example demonstrates:
    - Performance-optimized configuration
    - Large-scale repository processing
    - Resource utilization monitoring
    - Throughput optimization
    """
    print("\n=== High-Performance Configuration Example ===")

    # High-performance configuration
    high_perf_config = DiscoveryConfig(
        max_concurrent_repositories=50,  # High concurrency
        max_prs_per_repository=1000,  # Support large repositories
        cache_ttl_seconds=600,  # Longer cache TTL
        use_etag_caching=True,  # Enable all optimizations
        batch_size=100,  # Large batch sizes
        discovery_timeout_seconds=600,  # Allow more time
        priority_scheduling=True,  # Use priority scheduling
    )

    engine = await setup_mock_discovery_engine(high_perf_config)

    # Simulate large number of repositories
    repository_ids = [uuid.uuid4() for _ in range(100)]

    print(f"High-performance discovery of {len(repository_ids)} repositories...")
    print("Configuration:")
    print(f"  - Max concurrent: {high_perf_config.max_concurrent_repositories}")
    print(f"  - Max PRs per repo: {high_perf_config.max_prs_per_repository}")
    print(f"  - Batch size: {high_perf_config.batch_size}")
    print(f"  - Cache TTL: {high_perf_config.cache_ttl_seconds}s")

    # Measure performance
    start_time = time.time()
    results = await engine.run_discovery_cycle(repository_ids)
    processing_time = time.time() - start_time

    # Calculate throughput metrics
    total_prs = sum(len(result.discovered_prs) for result in results)
    total_checks = sum(
        sum(len(pr.check_runs) for pr in result.discovered_prs) for result in results
    )

    repositories_per_second = len(results) / processing_time
    prs_per_second = total_prs / processing_time

    print("\nHigh-performance results:")
    print(f"  - Processing time: {processing_time:.2f} seconds")
    print(f"  - Throughput: {repositories_per_second:.1f} repos/second")
    print(f"  - Throughput: {prs_per_second:.1f} PRs/second")
    print(f"  - Total PRs processed: {total_prs}")
    print(f"  - Total checks processed: {total_checks}")

    # Show performance characteristics
    if processing_time < 300:  # Less than 5 minutes
        print("✓ Meets performance requirement: <5 minutes for 100+ repositories")
    else:
        print("⚠ Performance requirement not met, consider tuning")


# Mock helper functions for examples
async def setup_mock_discovery_engine(config: DiscoveryConfig) -> PRDiscoveryEngine:
    """Setup a mock discovery engine for examples."""
    # In real usage, these would be properly initialized components
    from unittest.mock import AsyncMock, MagicMock

    # Create mock components
    pr_discovery = AsyncMock()
    pr_discovery.discover_prs = AsyncMock(side_effect=mock_discover_prs)
    pr_discovery.get_priority = AsyncMock(return_value=DiscoveryPriority.NORMAL)

    check_discovery = AsyncMock()
    state_detector = AsyncMock()
    data_sync = AsyncMock()
    rate_limiter = AsyncMock()
    cache = AsyncMock()
    event_publisher = AsyncMock()
    repository_repo = AsyncMock()

    # Configure mocks
    state_detector.detect_changes = AsyncMock(return_value=[])
    data_sync.synchronize = AsyncMock(
        return_value=MagicMock(
            prs_created=10, prs_updated=5, checks_created=40, checks_updated=20
        )
    )
    rate_limiter.get_available_tokens = AsyncMock(return_value=1000)
    cache.get_stats = MagicMock(return_value={"hit_rate": 65.0})

    # Mock repository data
    mock_repo = MagicMock()
    mock_repo.name = "example/repo"
    mock_repo.url = "https://github.com/example/repo"
    mock_repo.is_active = True
    mock_repo.failure_count = 0
    mock_repo.metadata = {}
    repository_repo.get_by_id = AsyncMock(return_value=mock_repo)
    repository_repo.update_last_polled = AsyncMock()
    repository_repo.reset_failure_count = AsyncMock()
    repository_repo.increment_failure_count = AsyncMock()

    # Create engine
    engine = PRDiscoveryEngine(
        config=config,
        pr_discovery=pr_discovery,
        check_discovery=check_discovery,
        state_detector=state_detector,
        data_sync=data_sync,
        rate_limiter=rate_limiter,
        cache=cache,
        event_publisher=event_publisher,
        repository_repo=repository_repo,
    )

    return engine


async def mock_discover_prs(
    repository_id: uuid.UUID,
    repository_url: str,
    since: datetime | None = None,
    max_prs: int | None = None,
) -> PRDiscoveryResult:
    """Mock PR discovery for examples."""
    # Simulate processing delay
    await asyncio.sleep(0.05)  # 50ms per repository

    # Create mock PRs
    pr_count = min(max_prs or 100, 100)
    discovered_prs = []

    for i in range(pr_count):
        pr = DiscoveredPR(
            pr_number=i + 1,
            title=f"Mock PR {i + 1}",
            author=f"user-{i % 5}",
            state="open",
            draft=False,
            base_branch="main",
            head_branch=f"feature/mock-{i}",
            base_sha=f"abc{i:06d}",
            head_sha=f"def{i:06d}",
            url=f"{repository_url}/pull/{i + 1}",
            body="Mock PR for example",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            merged_at=None,
            metadata={},
            check_runs=[],
        )
        discovered_prs.append(pr)

    return PRDiscoveryResult(
        repository_id=repository_id,
        repository_url=repository_url,
        discovered_prs=discovered_prs,
        discovery_timestamp=datetime.now(UTC),
        api_calls_used=1,
        cache_hits=1 if hash(repository_id) % 2 == 0 else 0,
        cache_misses=0 if hash(repository_id) % 2 == 0 else 1,
        processing_time_ms=50.0,
        errors=[],
    )


async def main() -> None:
    """Run all PR Discovery examples."""
    print("PR Discovery API Usage Examples")
    print("=" * 50)

    try:
        await basic_discovery_example()
        await performance_monitoring_example()
        await custom_strategy_example()
        await error_handling_example()
        await high_performance_example()

        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        print("\nKey takeaways:")
        print("- PR Discovery system handles 100+ repositories efficiently")
        print("- Intelligent caching reduces API calls by >60%")
        print("- Custom strategies enable organization-specific logic")
        print("- Comprehensive error handling ensures reliability")
        print("- Performance tuning supports various scales")

    except Exception as e:
        logger.error(f"Example execution failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
