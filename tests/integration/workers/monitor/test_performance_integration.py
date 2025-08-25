"""
Performance and scalability integration tests for PR monitoring system.

Tests system performance under realistic loads, concurrent processing scenarios,
resource usage patterns, and scalability limits with real database operations.
"""

import asyncio
import statistics
import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from src.models.repository import Repository
from src.repositories.check_run import CheckRunRepository
from src.repositories.pull_request import PullRequestRepository
from src.repositories.pr_state_history import PRStateHistoryRepository
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.models import ChangeSet, CheckRunData, PRData
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.synchronization import DatabaseSynchronizer


@pytest.mark.integration
@pytest.mark.performance
class TestPRMonitoringPerformance:
    """Performance tests for PR monitoring system components."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_scale_pr_processing_performance(
        self,
        database_session,
        setup_database_schema,
        performance_test_data,
        mock_github_client,
    ):
        """
        Why: Verify system can handle large-scale PR processing efficiently
        What: Tests processing 100 PRs with 500 check runs under time constraints
        How: Processes large dataset through complete workflow and measures
             performance metrics including throughput and resource usage
        """
        # Create test repository
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/perf-test/large-repo"
        repo.name = "large-repo"
        repo.full_name = "perf-test/large-repo"
        
        await database_session.execute(
            text("""
            INSERT INTO repositories 
            (id, url, name, full_name, status, failure_count,
             created_at, updated_at)
            VALUES (:id, :url, :name, :full_name, 'active', 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "id": repo.id,
                "url": repo.url,
                "name": repo.name,
                "full_name": repo.full_name,
            },
        )
        await database_session.commit()
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(
            mock_github_client, max_concurrent_requests=20
        )
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Use performance test data
        large_prs = performance_test_data["prs"]  # 100 PRs
        large_checks = performance_test_data["check_runs"]  # 500 check runs
        
        # Mock discovery service to return performance data
        discovery_service.discover_prs_and_checks = AsyncMock(
            return_value=(len(large_prs), len(large_checks))
        )
        
        async def mock_large_changeset(repository):
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add all PRs as new (first time processing)
            for pr_data in large_prs:
                pr_data.raw_data["repository_id"] = str(repository.id)
                from src.workers.monitor.models import PRChangeRecord
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=mock_large_changeset)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=1,  # Single repo for this test
        )
        
        # Measure processing performance
        start_time = datetime.now(timezone.utc)
        start_memory = _get_memory_usage()
        
        result = await processor.process_repository(repo)
        
        end_time = datetime.now(timezone.utc)
        end_memory = _get_memory_usage()
        
        processing_time = (end_time - start_time).total_seconds()
        memory_increase = end_memory - start_memory
        
        # Verify performance benchmarks
        assert result.success is True
        assert result.changes_synchronized == 100  # 100 PRs processed
        assert processing_time < 60.0  # Should complete within 1 minute
        assert memory_increase < 200  # Memory increase should be < 200MB
        
        # Calculate throughput metrics
        prs_per_second = len(large_prs) / processing_time
        assert prs_per_second > 2  # Should process at least 2 PRs per second
        
        # Verify data was persisted correctly
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=repo.id
        )
        assert len(persisted_prs) == 100
        
        # Performance reporting
        print(f"\nPerformance Metrics:")
        print(f"  Processing Time: {processing_time:.2f} seconds")
        print(f"  PRs/Second: {prs_per_second:.2f}")
        print(f"  Memory Increase: {memory_increase:.1f} MB")
        print(f"  Changes Synchronized: {result.changes_synchronized}")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_repository_processing_performance(
        self,
        database_session,
        setup_database_schema,
        mock_github_client,
    ):
        """
        Why: Verify concurrent processing of multiple repositories performs efficiently
        What: Tests processing 20 repositories concurrently with realistic data
        How: Creates multiple repositories, processes them concurrently with
             controlled concurrency limits, and measures performance metrics
        """
        # Create 20 test repositories
        repositories = []
        for i in range(20):
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/concurrent-test/repo-{i:02d}"
            repo.name = f"concurrent-repo-{i:02d}"
            repo.full_name = f"concurrent-test/repo-{i:02d}"
            repositories.append(repo)
            
            # Insert into database
            await database_session.execute(
                text("""
                INSERT INTO repositories 
                (id, url, name, full_name, status, failure_count,
                 created_at, updated_at)
                VALUES (:id, :url, :name, :full_name, 'active', 0,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "id": repo.id,
                    "url": repo.url,
                    "name": repo.name,
                    "full_name": repo.full_name,
                },
            )
        await database_session.commit()
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Mock services with simulated processing delays
        call_times = []
        
        async def timed_discovery(repository):
            start = datetime.now(timezone.utc)
            await asyncio.sleep(0.1)  # Simulate API call time
            end = datetime.now(timezone.utc)
            call_times.append((end - start).total_seconds())
            return (5, 10)  # 5 PRs, 10 check runs per repo
        
        async def timed_change_detection(repository):
            await asyncio.sleep(0.05)  # Simulate processing time
            changeset = ChangeSet(repository_id=repository.id)
            
            # Add a few PRs per repository
            for i in range(3):
                pr_data = PRData(
                    number=1000 + hash(str(repository.id)) % 1000 + i,
                    title=f"PR {i} for {repository.name}",
                    author=f"dev-{i}",
                    state="open",
                    draft=False,
                    base_branch="main",
                    head_branch=f"feature/{repository.name}-{i}",
                    base_sha=f"base_{i}",
                    head_sha=f"head_{i}",
                    url=f"{repository.url}/pull/{1000 + i}",
                    raw_data={"repository_id": str(repository.id)},
                )
                from src.workers.monitor.models import PRChangeRecord
                changeset.new_prs.append(
                    PRChangeRecord(pr_data=pr_data, change_type="new")
                )
            
            return changeset
        
        discovery_service.discover_prs_and_checks = AsyncMock(side_effect=timed_discovery)
        change_detector.detect_changes = AsyncMock(side_effect=timed_change_detection)
        
        # Test different concurrency levels
        concurrency_levels = [2, 5, 10]
        performance_results = {}
        
        for concurrency in concurrency_levels:
            processor = DefaultPRProcessor(
                discovery_service=discovery_service,
                change_detection_service=change_detector,
                synchronization_service=synchronizer,
                max_concurrent_repos=concurrency,
            )
            
            # Measure concurrent processing
            start_time = datetime.now(timezone.utc)
            batch_result = await processor.process_repositories(repositories)
            end_time = datetime.now(timezone.utc)
            
            total_time = (end_time - start_time).total_seconds()
            
            performance_results[concurrency] = {
                "total_time": total_time,
                "repositories_processed": batch_result.repositories_processed,
                "success_rate": batch_result.success_rate,
                "repos_per_second": len(repositories) / total_time,
            }
            
            # Verify results
            assert batch_result.repositories_processed == 20
            assert batch_result.success_rate == 100.0
            assert total_time < 30.0  # Should complete within 30 seconds
        
        # Analyze performance scaling
        for concurrency in concurrency_levels:
            result = performance_results[concurrency]
            print(f"\nConcurrency {concurrency}:")
            print(f"  Total Time: {result['total_time']:.2f} seconds")
            print(f"  Repos/Second: {result['repos_per_second']:.2f}")
            print(f"  Success Rate: {result['success_rate']:.1f}%")
        
        # Higher concurrency should be faster (up to a point)
        assert performance_results[5]["total_time"] < performance_results[2]["total_time"]
        
        # Verify data was persisted for all repositories
        for repo in repositories[:5]:  # Check first 5 repositories
            persisted_prs = await pr_repo.get_recent_prs(
                since=datetime.min, repository_id=repo.id
            )
            assert len(persisted_prs) == 3  # 3 PRs per repository

    @pytest.mark.asyncio
    async def test_database_connection_pool_performance(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
    ):
        """
        Why: Verify database connection pooling handles concurrent operations efficiently
        What: Tests connection pool performance under high concurrent load
        How: Runs many concurrent database operations and measures connection
             pool utilization, query performance, and resource management
        """
        # Create many PRs to synchronize concurrently
        changeset = ChangeSet(repository_id=test_repository_in_db.id)
        
        # Generate 50 PRs for concurrent processing
        prs_data = []
        for i in range(50):
            pr_data = PRData(
                number=3000 + i,
                title=f"Concurrent DB Test PR {i}",
                author=f"db-test-author-{i}",
                state="open",
                draft=i % 3 == 0,  # Every 3rd PR is draft
                base_branch="main",
                head_branch=f"feature/db-test-{i}",
                base_sha=f"db_base_{i:03d}",
                head_sha=f"db_head_{i:03d}",
                url=f"https://github.com/test/repo/pull/{3000 + i}",
                labels=[f"label-{i % 5}"],
                assignees=[f"assignee-{i % 3}"] if i % 2 == 0 else [],
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            prs_data.append(pr_data)
            
            from src.workers.monitor.models import PRChangeRecord
            changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
        
        # Create multiple synchronizers (simulating concurrent processes)
        synchronizers = [DatabaseSynchronizer(database_session) for _ in range(5)]
        
        # Split changeset into chunks for concurrent processing
        chunk_size = 10
        tasks = []
        
        for i, synchronizer in enumerate(synchronizers):
            start_idx = i * chunk_size
            end_idx = min(start_idx + chunk_size, len(changeset.new_prs))
            
            if start_idx < len(changeset.new_prs):
                chunk_changeset = ChangeSet(repository_id=test_repository_in_db.id)
                chunk_changeset.new_prs = changeset.new_prs[start_idx:end_idx]
                
                tasks.append(
                    synchronizer.synchronize_changes(test_repository_in_db.id, chunk_changeset)
                )
        
        # Measure concurrent database operations
        start_time = datetime.now(timezone.utc)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = datetime.now(timezone.utc)
        
        operation_time = (end_time - start_time).total_seconds()
        
        # Analyze results
        successful_operations = [r for r in results if isinstance(r, int)]
        total_synchronized = sum(successful_operations)
        
        # Verify performance
        assert len(successful_operations) >= 4  # Most operations should succeed
        assert total_synchronized >= 40  # Most PRs should be synchronized
        assert operation_time < 15.0  # Should complete within 15 seconds
        
        # Calculate database throughput
        db_operations_per_second = total_synchronized / operation_time
        assert db_operations_per_second > 3  # At least 3 operations per second
        
        # Verify data integrity
        pr_repo = PullRequestRepository(database_session)
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        
        concurrent_prs = [pr for pr in persisted_prs if pr.pr_number >= 3000]
        assert len(concurrent_prs) == total_synchronized
        
        print(f"\nDatabase Performance Metrics:")
        print(f"  Operation Time: {operation_time:.2f} seconds")
        print(f"  DB Operations/Second: {db_operations_per_second:.2f}")
        print(f"  Successfully Synchronized: {total_synchronized}/50")
        print(f"  Successful Operations: {len(successful_operations)}/5")

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(
        self,
        database_session,
        setup_database_schema,
        performance_test_data,
        mock_github_client,
    ):
        """
        Why: Verify system maintains reasonable memory usage under high load
        What: Tests memory consumption patterns during large-scale processing
        How: Processes large datasets while monitoring memory usage patterns
             and validates memory is released properly after processing
        """
        import gc
        
        # Force garbage collection before starting
        gc.collect()
        initial_memory = _get_memory_usage()
        
        # Create test repository
        repo = Repository()
        repo.id = uuid.uuid4()
        repo.url = "https://github.com/memory-test/large-memory-repo"
        repo.name = "large-memory-repo"
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Process data in batches to monitor memory usage
        large_prs = performance_test_data["prs"]
        batch_size = 25
        memory_samples = []
        
        for batch_start in range(0, len(large_prs), batch_size):
            batch_end = min(batch_start + batch_size, len(large_prs))
            batch_prs = large_prs[batch_start:batch_end]
            
            # Mock services for this batch
            discovery_service.discover_prs_and_checks = AsyncMock(
                return_value=(len(batch_prs), len(batch_prs) * 2)
            )
            
            async def mock_batch_changeset(repository):
                changeset = ChangeSet(repository_id=repository.id)
                for pr_data in batch_prs:
                    pr_data.raw_data["repository_id"] = str(repository.id)
                    # Unique PR numbers for each batch
                    pr_data.number = pr_data.number + batch_start * 1000
                    from src.workers.monitor.models import PRChangeRecord
                    changeset.new_prs.append(
                        PRChangeRecord(pr_data=pr_data, change_type="new")
                    )
                return changeset
            
            change_detector.detect_changes = AsyncMock(side_effect=mock_batch_changeset)
            
            processor = DefaultPRProcessor(
                discovery_service=discovery_service,
                change_detection_service=change_detector,
                synchronization_service=synchronizer,
            )
            
            # Process batch and measure memory
            batch_start_memory = _get_memory_usage()
            result = await processor.process_repository(repo)
            batch_end_memory = _get_memory_usage()
            
            memory_samples.append({
                "batch": batch_start // batch_size,
                "before": batch_start_memory,
                "after": batch_end_memory,
                "increase": batch_end_memory - batch_start_memory,
                "prs_processed": len(batch_prs),
            })
            
            # Verify batch succeeded
            assert result.success is True
            assert result.changes_synchronized == len(batch_prs)
            
            # Force garbage collection between batches
            gc.collect()
        
        final_memory = _get_memory_usage()
        total_memory_increase = final_memory - initial_memory
        
        # Analyze memory usage patterns
        max_batch_memory_increase = max(sample["increase"] for sample in memory_samples)
        avg_batch_memory_increase = statistics.mean(sample["increase"] for sample in memory_samples)
        
        # Verify memory usage is reasonable
        assert total_memory_increase < 500  # Total increase < 500MB
        assert max_batch_memory_increase < 150  # Single batch increase < 150MB
        assert avg_batch_memory_increase < 100  # Average batch increase < 100MB
        
        # Print memory analysis
        print(f"\nMemory Usage Analysis:")
        print(f"  Initial Memory: {initial_memory:.1f} MB")
        print(f"  Final Memory: {final_memory:.1f} MB")
        print(f"  Total Increase: {total_memory_increase:.1f} MB")
        print(f"  Max Batch Increase: {max_batch_memory_increase:.1f} MB")
        print(f"  Avg Batch Increase: {avg_batch_memory_increase:.1f} MB")
        
        for sample in memory_samples[:3]:  # Show first 3 batches
            print(f"  Batch {sample['batch']}: {sample['increase']:.1f} MB "
                  f"({sample['prs_processed']} PRs)")

    @pytest.mark.asyncio
    async def test_error_recovery_performance(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        mock_github_client,
    ):
        """
        Why: Verify system performs well when recovering from errors
        What: Tests performance when some operations fail and need recovery
        How: Injects failures in processing chain and measures recovery time
             and overall system resilience under partial failure conditions
        """
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        # Create mixed success/failure scenario
        failure_rate = 0.2  # 20% failure rate
        call_count = 0
        successful_operations = 0
        failed_operations = 0
        
        async def intermittent_discovery(repository):
            nonlocal call_count, successful_operations, failed_operations
            call_count += 1
            
            # Simulate intermittent failures
            if call_count % 5 == 0:  # Every 5th call fails
                failed_operations += 1
                raise Exception(f"Simulated GitHub API failure #{failed_operations}")
            
            successful_operations += 1
            await asyncio.sleep(0.05)  # Simulate processing time
            return (3, 5)
        
        discovery_service.discover_prs_and_checks = AsyncMock(side_effect=intermittent_discovery)
        
        async def reliable_change_detection(repository):
            changeset = ChangeSet(repository_id=repository.id)
            # Add minimal PR for successful operations
            pr_data = PRData(
                number=4000 + call_count,
                title=f"Recovery Test PR {call_count}",
                author="recovery-test",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/recovery-{call_count}",
                base_sha="recovery_base",
                head_sha="recovery_head",
                url=f"https://github.com/test/repo/pull/{4000 + call_count}",
                raw_data={"repository_id": str(repository.id)},
            )
            from src.workers.monitor.models import PRChangeRecord
            changeset.new_prs.append(
                PRChangeRecord(pr_data=pr_data, change_type="new")
            )
            return changeset
        
        change_detector.detect_changes = AsyncMock(side_effect=reliable_change_detection)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
        )
        
        # Create multiple repositories for batch processing
        repositories = []
        for i in range(15):  # 15 repositories, ~3 will fail
            repo = Repository()
            repo.id = uuid.uuid4()
            repo.url = f"https://github.com/recovery-test/repo-{i}"
            repo.name = f"recovery-repo-{i}"
            repositories.append(repo)
        
        # Measure error recovery performance
        start_time = datetime.now(timezone.utc)
        batch_result = await processor.process_repositories(repositories)
        end_time = datetime.now(timezone.utc)
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Analyze error recovery performance
        expected_failures = len(repositories) // 5  # Every 5th should fail
        expected_successes = len(repositories) - expected_failures
        
        assert batch_result.repositories_processed == len(repositories)
        assert batch_result.success_rate >= 70.0  # At least 70% success rate
        assert processing_time < 20.0  # Should complete within 20 seconds despite errors
        
        # Verify that successful operations completed properly
        successful_repos = [r for r in batch_result.results if r.success]
        failed_repos = [r for r in batch_result.results if not r.success]
        
        assert len(successful_repos) >= expected_successes
        assert len(failed_repos) <= expected_failures + 1  # Allow for slight variance
        
        # Check that failed operations have proper error information
        for failed_result in failed_repos:
            assert len(failed_result.errors) > 0
            assert any("discovery_failure" in str(error) for error in failed_result.errors)
        
        # Verify successful operations actually persisted data
        persisted_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        recovery_prs = [pr for pr in persisted_prs if pr.pr_number >= 4000]
        assert len(recovery_prs) >= len(successful_repos)
        
        print(f"\nError Recovery Performance:")
        print(f"  Processing Time: {processing_time:.2f} seconds")
        print(f"  Success Rate: {batch_result.success_rate:.1f}%")
        print(f"  Successful Operations: {len(successful_repos)}")
        print(f"  Failed Operations: {len(failed_repos)}")
        print(f"  Recovery Overhead: {processing_time / len(repositories):.3f} sec/repo")


def _get_memory_usage() -> float:
    """Get current memory usage in MB."""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except ImportError:
        # Fallback if psutil is not available
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Convert to MB


@pytest.mark.integration
@pytest.mark.performance
class TestConcurrentProcessingScenarios:
    """Tests for various concurrent processing scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_high_frequency_updates_performance(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        mock_github_client,
    ):
        """
        Why: Verify system handles high-frequency updates efficiently
        What: Tests rapid successive updates to the same data
        How: Simulates webhook-like rapid updates and measures performance
        """
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
        )
        
        # Create initial PR
        initial_pr = PRData(
            number=5000,
            title="High Frequency Update Test PR",
            author="frequency-test",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/frequency-test",
            base_sha="freq_base",
            head_sha="freq_head_1",
            url="https://github.com/test/repo/pull/5000",
            raw_data={"repository_id": str(test_repository_in_db.id)},
        )
        
        # Create initial changeset
        initial_changeset = ChangeSet(repository_id=test_repository_in_db.id)
        from src.workers.monitor.models import PRChangeRecord
        initial_changeset.new_prs.append(
            PRChangeRecord(pr_data=initial_pr, change_type="new")
        )
        
        await synchronizer.synchronize_changes(test_repository_in_db.id, initial_changeset)
        
        # Get created PR
        created_pr = await pr_repo.get_by_repo_and_number(
            repository_id=test_repository_in_db.id, pr_number=5000
        )
        
        # Simulate rapid successive updates
        update_count = 20
        update_times = []
        
        for i in range(update_count):
            # Create updated PR data
            updated_pr = PRData(
                number=5000,
                title=f"Updated Title #{i}",  # Change title each time
                author="frequency-test",
                state="open",
                draft=i % 2 == 0,  # Toggle draft status
                base_branch="main",
                head_branch="feature/frequency-test",
                base_sha="freq_base",
                head_sha=f"freq_head_{i + 2}",  # New commit each time
                url="https://github.com/test/repo/pull/5000",
                labels=[f"update-{i}"],  # Change metadata
                raw_data={"repository_id": str(test_repository_in_db.id)},
            )
            
            # Mock services for this update
            discovery_service.discover_prs_and_checks = AsyncMock(return_value=(1, 0))
            
            async def mock_update_detection(repository):
                changeset = ChangeSet(repository_id=repository.id)
                update_record = PRChangeRecord(
                    pr_data=updated_pr,
                    change_type="updated",
                    existing_pr_id=created_pr.id,
                    title_changed=True,
                    old_title=f"Updated Title #{i-1}" if i > 0 else "High Frequency Update Test PR",
                    draft_changed=True if i > 0 else False,
                    sha_changed=True,
                    old_head_sha=f"freq_head_{i + 1}",
                    metadata_changed=True,
                )
                changeset.updated_prs.append(update_record)
                return changeset
            
            change_detector.detect_changes = AsyncMock(side_effect=mock_update_detection)
            
            # Measure update performance
            start_time = datetime.now(timezone.utc)
            result = await processor.process_repository(test_repository_in_db)
            end_time = datetime.now(timezone.utc)
            
            update_time = (end_time - start_time).total_seconds()
            update_times.append(update_time)
            
            # Verify update succeeded
            assert result.success is True
            assert result.changes_synchronized == 1
        
        # Analyze update performance
        avg_update_time = statistics.mean(update_times)
        max_update_time = max(update_times)
        min_update_time = min(update_times)
        
        # Performance assertions
        assert avg_update_time < 2.0  # Average update should be < 2 seconds
        assert max_update_time < 5.0  # No single update should take > 5 seconds
        assert min_update_time < 1.0  # Fast updates should be < 1 second
        
        # Verify final state
        final_pr = await pr_repo.get_by_id(created_pr.id)
        assert final_pr.title == f"Updated Title #{update_count - 1}"
        assert final_pr.head_sha == f"freq_head_{update_count + 1}"
        
        # Verify state history was maintained
        history_repo = PRStateHistoryRepository(database_session)
        history = await history_repo.get_history_for_pr(created_pr.id)
        # Should have initial creation + any state changes
        assert len(history) >= 1
        
        print(f"\nHigh Frequency Update Performance:")
        print(f"  Updates Processed: {update_count}")
        print(f"  Average Update Time: {avg_update_time:.3f} seconds")
        print(f"  Min Update Time: {min_update_time:.3f} seconds")
        print(f"  Max Update Time: {max_update_time:.3f} seconds")
        print(f"  Updates/Second: {1/avg_update_time:.2f}")

    @pytest.mark.asyncio
    async def test_resource_cleanup_after_processing(
        self,
        database_session,
        setup_database_schema,
        test_repository_in_db,
        mock_github_client,
    ):
        """
        Why: Verify system properly cleans up resources after processing
        What: Tests that connections, memory, and other resources are released
        How: Processes data and verifies resource cleanup through monitoring
        """
        import gc
        import asyncio
        
        # Force cleanup before starting
        gc.collect()
        await asyncio.sleep(0.1)
        
        initial_memory = _get_memory_usage()
        
        # Setup services
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        # Process multiple batches and verify cleanup
        for batch in range(5):
            discovery_service = GitHubPRDiscoveryService(mock_github_client)
            change_detector = DatabaseChangeDetector(pr_repo, check_repo)
            synchronizer = DatabaseSynchronizer(database_session)
            
            processor = DefaultPRProcessor(
                discovery_service=discovery_service,
                change_detection_service=change_detector,
                synchronization_service=synchronizer,
            )
            
            # Create PRs for this batch
            batch_prs = []
            for i in range(10):  # 10 PRs per batch
                pr_data = PRData(
                    number=6000 + batch * 100 + i,
                    title=f"Cleanup Test PR Batch {batch} #{i}",
                    author=f"cleanup-test-{batch}",
                    state="open",
                    draft=False,
                    base_branch="main",
                    head_branch=f"feature/cleanup-{batch}-{i}",
                    base_sha=f"cleanup_base_{batch}",
                    head_sha=f"cleanup_head_{batch}_{i}",
                    url=f"https://github.com/test/repo/pull/{6000 + batch * 100 + i}",
                    raw_data={"repository_id": str(test_repository_in_db.id)},
                )
                batch_prs.append(pr_data)
            
            # Mock services
            discovery_service.discover_prs_and_checks = AsyncMock(
                return_value=(len(batch_prs), 0)
            )
            
            async def mock_batch_detection(repository):
                changeset = ChangeSet(repository_id=repository.id)
                for pr_data in batch_prs:
                    from src.workers.monitor.models import PRChangeRecord
                    changeset.new_prs.append(
                        PRChangeRecord(pr_data=pr_data, change_type="new")
                    )
                return changeset
            
            change_detector.detect_changes = AsyncMock(side_effect=mock_batch_detection)
            
            # Process batch
            result = await processor.process_repository(test_repository_in_db)
            assert result.success is True
            assert result.changes_synchronized == 10
            
            # Clear references and force cleanup
            del processor
            del discovery_service
            del change_detector
            del synchronizer
            
            gc.collect()
            await asyncio.sleep(0.1)  # Allow async cleanup
        
        # Check final memory usage
        final_memory = _get_memory_usage()
        memory_increase = final_memory - initial_memory
        
        # Verify reasonable memory usage after cleanup
        assert memory_increase < 100  # Memory increase should be < 100MB after 50 PRs
        
        # Verify all data was actually persisted
        all_cleanup_prs = await pr_repo.get_recent_prs(
            since=datetime.min, repository_id=test_repository_in_db.id
        )
        cleanup_prs = [pr for pr in all_cleanup_prs if pr.pr_number >= 6000]
        assert len(cleanup_prs) == 50  # 5 batches * 10 PRs each
        
        print(f"\nResource Cleanup Analysis:")
        print(f"  Initial Memory: {initial_memory:.1f} MB")
        print(f"  Final Memory: {final_memory:.1f} MB")
        print(f"  Memory Increase: {memory_increase:.1f} MB")
        print(f"  PRs Processed: {len(cleanup_prs)}")
        print(f"  Memory per PR: {memory_increase / len(cleanup_prs):.3f} MB")


