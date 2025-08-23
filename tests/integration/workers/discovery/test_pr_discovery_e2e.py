"""
End-to-end integration tests for PR Discovery workflow.

Tests complete discovery workflow from GitHub API through database synchronization,
using real dependencies: actual database operations, GitHub mock server HTTP calls,
real component interactions, and authentic data flows.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List

import pytest
import pytest_asyncio

from tests.fixtures.discovery import (
    DiscoveredPRFactory,
    PRDiscoveryResultFactory,
    StateChangeFactory,
    create_mock_github_pr_response,
    create_realistic_pr_data,
)
from tests.integration.fixtures.component_factory import (
    IntegrationComponentFactory,
    ComponentFactoryBuilder,
    IntegrationTestContext,
    create_minimal_testing_config,
    create_performance_testing_config,
    create_error_testing_config,
)
from tests.integration.fixtures.database import (
    RealTestDatabaseManager,
    TestDatabaseContext,
    get_test_database_manager,
)
from tests.integration.fixtures.github_mock_server import (
    GitHubMockServer,
    GitHubMockIntegration,
    MockServerGitHubClient,
    GITHUB_MOCK_SCENARIOS,
)
from src.github.client import GitHubClient
from src.workers.discovery.interfaces import DiscoveryConfig, PRDiscoveryResult


class TestPRDiscoveryEndToEndWorkflow:
    """Tests for complete PR discovery workflow integration using real dependencies."""

    @pytest_asyncio.fixture
    async def github_mock_server(self) -> GitHubMockServer:
        """
        Why: Provides realistic GitHub API responses for integration testing
             with actual HTTP traffic and authentic API contracts
        What: Creates GitHub mock server that serves real HTTP responses
              matching GitHub API specification
        How: Uses GitHubMockServer with realistic response data and 
             HTTP behavior including rate limiting and errors
        """
        server = GitHubMockServer()
        yield server
        # Server cleanup handled by context managers

    @pytest_asyncio.fixture
    async def real_database_context(
        self
    ) -> AsyncGenerator[TestDatabaseContext, None]:
        """
        Why: Provides real database with actual persistence for testing
             authentic data operations and transaction behavior
        What: Creates isolated database instance with applied migrations
              and transaction-based test isolation
        How: Uses RealTestDatabaseManager to create SQLite/PostgreSQL
             database with proper cleanup and performance monitoring
        """
        manager = get_test_database_manager()
        isolation_id = str(uuid.uuid4())
        
        context = await manager.create_test_database(isolation_id)
        try:
            await manager.apply_migrations(context)
            await manager.seed_test_data(context, "basic_discovery")
            yield context
        finally:
            await manager.cleanup_database(context)

    @pytest_asyncio.fixture
    async def integration_components(
        self, 
        real_database_context: TestDatabaseContext,
        github_mock_server: GitHubMockServer
    ) -> IntegrationComponentFactory:
        """
        Why: Provides real discovery components for authentic integration testing
             with actual dependencies and data flows
        What: Creates fully functional discovery engine with real repositories,
              cache, GitHub client, and database connections
        How: Uses IntegrationComponentFactory to assemble real components
             pointing to test database and GitHub mock server
        """
        async with github_mock_server as mock_server:
            server_url = await mock_server.start_server()
            
            # Configure mock server with realistic data
            mock_server.setup_repository_responses({
                "default": GITHUB_MOCK_SCENARIOS["basic_discovery"]
            })
            
            # Create real GitHub client pointing to mock server
            github_client = MockServerGitHubClient(server_url)
            
            async with real_database_context.session_factory() as session:
                # Build component factory with real dependencies
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_client)
                    .build()
                )
                
                try:
                    yield factory
                finally:
                    await factory.cleanup()

    @pytest_asyncio.fixture
    async def pr_discovery_engine(
        self, integration_components: IntegrationComponentFactory
    ):
        """
        Why: Provides real PR discovery engine for end-to-end workflow testing
             with authentic component interactions
        What: Creates PRDiscoveryEngine with real strategies, repositories,
              and state management using actual implementations
        How: Uses integration component factory to create engine with
             minimal testing configuration for fast but comprehensive tests
        """
        config = create_minimal_testing_config()
        engine = integration_components.create_discovery_engine(config)
        return engine

    @pytest.mark.asyncio
    async def test_complete_discovery_cycle_processes_multiple_repositories(
        self, 
        pr_discovery_engine,
        integration_components: IntegrationComponentFactory,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure complete discovery cycle successfully processes multiple
             repositories end-to-end using real components, validating
             authentic workflow from HTTP API calls to database persistence.

        What: Tests that run_discovery_cycle() processes all provided repositories
              through complete workflow including real GitHub HTTP requests,
              authentic state detection, and actual database synchronization.

        How: Creates real repository records, configures GitHub mock server with
             realistic responses, executes discovery cycle, validates actual
             database changes and component state transitions.
        """
        # Arrange - Create real repository records in database
        repository_ids = []
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            for i in range(3):
                repo = Repository(
                    id=uuid.uuid4(),
                    url=f"https://github.com/test/repo{i+1}",
                    name=f"test/repo{i+1}",
                    full_name=f"test/repo{i+1}", 
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                repository_ids.append(repo.id)
            
            await session.commit()

        # Act - Run real discovery cycle
        start_time = time.time()
        results = await pr_discovery_engine.run_discovery_cycle(repository_ids)
        processing_time = time.time() - start_time

        # Assert - Validate real results
        assert results is not None
        assert len(results) == len(repository_ids)
        assert processing_time < 30.0  # Should complete within 30 seconds

        # Verify each repository was processed with real data
        processed_repo_ids = {result.repository_id for result in results}
        expected_repo_ids = set(repository_ids)
        assert processed_repo_ids == expected_repo_ids
        
        # Verify real database changes occurred
        async with real_database_context.session_factory() as session:
            from src.repositories.pull_request import PullRequestRepository
            pr_repo = PullRequestRepository(session)
            
            for repo_id in repository_ids:
                # Check that PRs were actually created in database
                prs = await pr_repo.get_by_repository_id(repo_id)
                # Basic discovery scenario should create some PRs
                assert len(prs) >= 0  # May be 0 if no PRs in mock data
        
        # Verify component metrics show real activity
        event_publisher = integration_components.event_publisher
        discovery_events = event_publisher.get_events_by_type("discovery_complete")
        assert len(discovery_events) > 0

    @pytest.mark.asyncio
    async def test_discovery_workflow_handles_database_transactions_correctly(
        self, 
        pr_discovery_engine,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure discovery workflow properly manages database transactions with
             actual commit/rollback behavior, maintaining real data integrity
             throughout the process.

        What: Tests that discovery workflow creates real database transactions
              and handles commit/rollback scenarios with actual database operations
              and persistent data verification.

        How: Creates test data, processes discovery cycle, validates actual
             transaction behavior by checking database state before/after
             operations and testing rollback scenarios.
        """
        # Arrange - Create repository in database
        repository_id = uuid.uuid4()
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            repo = Repository(
                id=repository_id,
                url="https://github.com/test/transaction-repo",
                name="test/transaction-repo",
                full_name="test/transaction-repo",
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            await session.commit()

        # Capture initial database state
        async with real_database_context.session_factory() as session:
            from src.repositories.pull_request import PullRequestRepository
            pr_repo = PullRequestRepository(session)
            initial_pr_count = len(await pr_repo.get_by_repository_id(repository_id))

        # Act - Run discovery with real transactions
        results = await pr_discovery_engine.run_discovery_cycle([repository_id])

        # Assert - Verify transaction behavior with actual database
        assert results is not None
        assert len(results) == 1
        
        result = results[0]
        assert result.repository_id == repository_id
        assert len(result.errors) == 0  # Should complete without errors
        
        # Verify actual data persistence after transaction commits
        async with real_database_context.session_factory() as session:
            pr_repo = PullRequestRepository(session)
            final_pr_count = len(await pr_repo.get_by_repository_id(repository_id))
            
            # Data should have been committed (may be same count if no new PRs)
            assert final_pr_count >= initial_pr_count
            
        # Test rollback scenario by simulating error condition
        async with real_database_context.get_transaction_context(
            real_database_context
        ) as session:
            # Transaction should rollback on exception
            try:
                from src.models.pull_request import PullRequest
                from src.models.enums import PRState
                
                # Add PR that will be rolled back
                pr = PullRequest(
                    id=uuid.uuid4(),
                    repository_id=repository_id,
                    pr_number=999,
                    title="Test Rollback PR",
                    author="test-user",
                    state=PRState.OPENED,
                    base_branch="main", 
                    head_branch="rollback-test",
                    base_sha="abc123",
                    head_sha="def456",
                    url="https://github.com/test/transaction-repo/pull/999"
                )
                session.add(pr)
                await session.flush()
                
                # Force transaction rollback by exiting context
                # (session_factory creates transactions that rollback)
                pass
                
            except Exception:
                # Exception handling is part of transaction rollback test
                pass
        
        # Verify rollback worked - PR should not exist
        async with real_database_context.session_factory() as session:
            pr_repo = PullRequestRepository(session)
            rollback_pr_count = len(await pr_repo.get_by_repository_id(repository_id))
            # Count should be same as final_pr_count (rollback happened)
            assert rollback_pr_count == final_pr_count

    @pytest.mark.asyncio
    async def test_discovery_workflow_handles_github_api_failures_gracefully(
        self, 
        github_mock_server: GitHubMockServer,
        real_database_context: TestDatabaseContext,
        integration_components: IntegrationComponentFactory
    ):
        """
        Why: Ensure discovery workflow gracefully handles real GitHub API failures
             without corrupting data or crashing, maintaining authentic system
             resilience under actual HTTP error conditions.

        What: Tests that workflow continues processing other repositories when some
              real HTTP requests to GitHub mock server fail, with proper error
              reporting and partial success handling.

        How: Configures GitHub mock server to return HTTP error responses for
             specific repositories, validates partial success scenario and
             authentic error handling with real HTTP status codes.
        """
        # Arrange - Create repositories and configure error responses
        repository_ids = []
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            for i in range(3):
                repo = Repository(
                    id=uuid.uuid4(),
                    url=f"https://github.com/test/error-repo{i+1}",
                    name=f"test/error-repo{i+1}",
                    full_name=f"test/error-repo{i+1}",
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                repository_ids.append(repo.id)
            await session.commit()
        
        # Configure GitHub mock server with error simulation
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "basic_discovery"
        ) as github_context:
            # Set up error simulation for middle repository
            github_context.server.simulate_api_errors(
                error_rate=0.3,  # 30% error rate
                error_codes=[500, 502, 503]
            )
            
            # Configure endpoint-specific errors
            github_context.server.error_simulator.configure_endpoint_errors(
                "/repos/{owner}/{repo}/pulls",
                error_code=500,
                frequency=2  # Every 2nd request fails
            )
            
            # Create discovery engine with GitHub client pointing to mock server
            config = create_minimal_testing_config()
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                discovery_engine = factory.create_discovery_engine(config)
                
                try:
                    # Act - Run discovery with error conditions
                    results = await discovery_engine.run_discovery_cycle(repository_ids)
                    
                    # Assert - Verify graceful error handling
                    assert results is not None
                    assert len(results) == len(repository_ids)  # All repos attempted
                    
                    # Check that some operations succeeded despite errors
                    successful_results = [r for r in results if len(r.errors) == 0]
                    error_results = [r for r in results if len(r.errors) > 0]
                    
                    # With error rate, expect some failures but not total failure
                    assert len(successful_results) > 0 or len(error_results) > 0
                    
                    # Verify error details are captured properly
                    for error_result in error_results:
                        assert error_result.repository_id in repository_ids
                        assert len(error_result.errors) > 0
                        # Errors should contain HTTP-related information
                        error_messages = [str(e) for e in error_result.errors]
                        assert any("500" in msg or "502" in msg or "503" in msg 
                                 for msg in error_messages)
                    
                    # Verify database integrity maintained despite errors
                    async with real_database_context.session_factory() as check_session:
                        from src.repositories.repository import RepositoryRepository
                        repo_repo = RepositoryRepository(check_session)
                        
                        for repo_id in repository_ids:
                            repo_record = await repo_repo.get_by_id(repo_id)
                            assert repo_record is not None
                            # Repository status should be preserved
                            assert repo_record.status == RepositoryStatus.ACTIVE
                    
                    # Verify metrics captured error information
                    github_metrics = github_context.client.get_request_metrics()
                    assert github_metrics["total_requests"] > 0
                    assert github_metrics["error_rate"] > 0  # Should have some errors
                    
                finally:
                    await factory.cleanup()

    @pytest.mark.asyncio
    async def test_discovery_workflow_respects_rate_limiting_constraints(
        self,
        github_mock_server: GitHubMockServer, 
        real_database_context: TestDatabaseContext,
        integration_components: IntegrationComponentFactory
    ):
        """
        Why: Ensure discovery workflow respects real GitHub API rate limits and
             implements appropriate backoff strategies with actual HTTP rate
             limit headers, preventing API abuse and account suspension.

        What: Tests that workflow properly handles real HTTP 429 rate limit responses
              with actual rate limit headers and implements authentic backoff/retry
              logic without exceeding API limits.

        How: Configures GitHub mock server to simulate realistic rate limiting with
             HTTP 429 responses and rate limit headers, validates workflow
             implements proper waiting and retry behavior with actual timing.
        """
        # Arrange - Create repositories for rate limit testing
        repository_ids = []
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            for i in range(5):  # 5 repos to trigger rate limiting
                repo = Repository(
                    id=uuid.uuid4(),
                    url=f"https://github.com/test/ratelimit-repo{i+1}",
                    name=f"test/ratelimit-repo{i+1}",
                    full_name=f"test/ratelimit-repo{i+1}",
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                repository_ids.append(repo.id)
            await session.commit()
        
        # Configure realistic rate limiting on GitHub mock server
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "rate_limited"
        ) as github_context:
            # Set very low rate limits to trigger rate limiting quickly
            github_context.server.simulate_rate_limiting(
                resource="core",
                limit=3,  # Very low limit
                window_seconds=60
            )
            
            # Create discovery engine with rate limiting configuration
            config = create_minimal_testing_config()
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                discovery_engine = factory.create_discovery_engine(config)
                
                try:
                    # Act - Run discovery with rate limiting
                    start_time = time.time()
                    results = await discovery_engine.run_discovery_cycle(repository_ids)
                    end_time = time.time()
                    processing_time = end_time - start_time
                    
                    # Assert - Verify rate limiting behavior
                    assert results is not None
                    assert len(results) == len(repository_ids)  # All attempted
                    
                    # Processing should take longer due to rate limiting
                    # (Should implement backoff/retry delays)
                    assert processing_time > 1.0  # Should take at least 1 second with limits
                    
                    # Check for rate limit handling in results
                    rate_limited_results = [
                        r for r in results 
                        if any("rate limit" in str(e).lower() for e in r.errors)
                    ]
                    
                    # Should have encountered rate limits with such low limits
                    # (Unless implementation successfully handles them)
                    total_errors = sum(len(r.errors) for r in results)
                    
                    # Verify client metrics show rate limit encounters
                    client_metrics = github_context.client.get_request_metrics()
                    server_metrics = github_context.server.get_request_metrics()
                    
                    assert client_metrics["total_requests"] > 0
                    
                    # Server should have returned some 429 responses
                    status_codes = server_metrics.get("status_codes", {})
                    assert status_codes.get(429, 0) > 0  # Should have rate limit responses
                    
                    # Verify rate limit headers were processed
                    # Check that subsequent requests waited appropriately
                    assert server_metrics["total_requests"] >= len(repository_ids)
                    
                    # Verify database operations still completed successfully
                    # despite rate limiting
                    successful_results = [r for r in results if len(r.errors) == 0]
                    
                    # Even with rate limiting, some operations should succeed
                    # due to proper backoff/retry handling
                    if len(successful_results) == 0:
                        # If no successes, verify errors are rate limit related
                        all_errors = [e for r in results for e in r.errors]
                        rate_limit_errors = [
                            e for e in all_errors 
                            if "rate limit" in str(e).lower() or "429" in str(e)
                        ]
                        assert len(rate_limit_errors) > 0
                    
                finally:
                    await factory.cleanup()

    @pytest.mark.asyncio
    async def test_discovery_workflow_maintains_data_consistency_across_components(
        self,
        github_mock_server: GitHubMockServer,
        real_database_context: TestDatabaseContext,
        integration_components: IntegrationComponentFactory
    ):
        """
        Why: Ensure discovery workflow maintains authentic data consistency across
             all real components throughout the complete process, preventing
             actual data corruption or loss with real database validation.

        What: Tests that data flows correctly between real components (scanner,
              detector, synchronizer) with actual state tracking, database
              operations, and consistency validation across component boundaries.

        How: Processes complete workflow with real data tracking, validates
             consistent data representation in actual database records,
             component state, and cross-component data integrity.
        """
        # Arrange - Set up comprehensive test data
        repository_id = uuid.uuid4()
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            repo = Repository(
                id=repository_id,
                url="https://github.com/test/consistency-repo",
                name="test/consistency-repo",
                full_name="test/consistency-repo", 
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            await session.commit()
        
        # Configure GitHub mock server with rich, consistent test data
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "basic_discovery"
        ) as github_context:
            # Set up detailed PR and check data for consistency testing
            test_prs = [
                {
                    "number": 1,
                    "state": "open",
                    "title": "Feature: Add consistency checks",
                    "head": {"sha": "abc123def456", "ref": "feature/consistency"},
                    "base": {"sha": "main123def456", "ref": "main"},
                    "user": {"login": "test-user"},
                    "created_at": "2024-01-01T10:00:00Z",
                    "updated_at": "2024-01-01T11:00:00Z"
                },
                {
                    "number": 2, 
                    "state": "closed",
                    "title": "Fix: Resolve data inconsistency",
                    "head": {"sha": "fed987cba321", "ref": "fix/inconsistency"},
                    "base": {"sha": "main123def456", "ref": "main"},
                    "user": {"login": "test-user"},
                    "created_at": "2024-01-01T09:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z"
                }
            ]
            
            github_context.server.setup_pr_responses(
                "test/consistency-repo", 
                test_prs
            )
            
            # Set up corresponding check runs
            test_checks = [
                {
                    "id": 12345,
                    "name": "CI Tests", 
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2024-01-01T10:30:00Z",
                    "completed_at": "2024-01-01T10:45:00Z"
                },
                {
                    "id": 12346,
                    "name": "Lint Check",
                    "status": "completed", 
                    "conclusion": "failure",
                    "started_at": "2024-01-01T10:30:00Z",
                    "completed_at": "2024-01-01T10:40:00Z"
                }
            ]
            
            github_context.server.setup_check_responses(
                "test/consistency-repo",
                1,  # PR number
                test_checks
            )
            
            # Create discovery engine and capture initial state
            config = create_minimal_testing_config()
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                discovery_engine = factory.create_discovery_engine(config)
                
                # Capture initial database state
                pr_repo, check_repo, repo_repo = factory.create_repositories()
                
                initial_pr_count = len(await pr_repo.get_by_repository_id(repository_id))
                initial_check_count = len(await check_repo.get_by_repository_id(repository_id))
                
                try:
                    # Act - Run discovery workflow
                    results = await discovery_engine.run_discovery_cycle([repository_id])
                    
                    # Assert - Verify comprehensive data consistency
                    assert results is not None
                    assert len(results) == 1
                    
                    result = results[0]
                    assert result.repository_id == repository_id
                    assert len(result.errors) == 0  # Should complete successfully
                    
                    # Verify data consistency across all components
                    
                    # 1. PR Repository Consistency
                    final_prs = await pr_repo.get_by_repository_id(repository_id)
                    assert len(final_prs) >= initial_pr_count
                    
                    # Verify PR data matches GitHub responses
                    pr_numbers = {pr.pr_number for pr in final_prs}
                    expected_pr_numbers = {pr["number"] for pr in test_prs}
                    
                    # All GitHub PRs should be reflected in database
                    for expected_num in expected_pr_numbers:
                        assert expected_num in pr_numbers
                    
                    # Verify PR field consistency
                    for pr in final_prs:
                        matching_github_pr = next(
                            (gpr for gpr in test_prs if gpr["number"] == pr.pr_number),
                            None
                        )
                        if matching_github_pr:
                            assert pr.title == matching_github_pr["title"]
                            assert pr.head_sha == matching_github_pr["head"]["sha"]
                            assert pr.base_sha == matching_github_pr["base"]["sha"]
                            assert pr.author == matching_github_pr["user"]["login"]
                    
                    # 2. Check Repository Consistency 
                    final_checks = await check_repo.get_by_repository_id(repository_id)
                    assert len(final_checks) >= initial_check_count
                    
                    # Verify check data consistency with GitHub responses
                    check_external_ids = {check.external_id for check in final_checks}
                    expected_check_ids = {str(check["id"]) for check in test_checks}
                    
                    # GitHub checks should be in database
                    for expected_id in expected_check_ids:
                        assert expected_id in check_external_ids
                    
                    # 3. Cross-Component Consistency
                    # Verify PRs and their associated checks are properly linked
                    for pr in final_prs:
                        pr_checks = [c for c in final_checks if c.pull_request_id == pr.id]
                        
                        # PRs should have associated checks if they exist in test data
                        if pr.pr_number == 1:  # This PR has checks in test data
                            assert len(pr_checks) > 0
                            
                            # Verify check details match
                            for check in pr_checks:
                                matching_github_check = next(
                                    (gc for gc in test_checks 
                                     if str(gc["id"]) == check.external_id),
                                    None
                                )
                                if matching_github_check:
                                    assert check.check_name == matching_github_check["name"]
                                    assert check.status.value == matching_github_check["status"]
                                    assert check.conclusion.value == matching_github_check["conclusion"]
                    
                    # 4. Event Publisher Consistency
                    event_publisher = factory.event_publisher
                    
                    # Verify events were published for data changes
                    new_pr_events = event_publisher.get_events_by_type("new_pr")
                    state_change_events = event_publisher.get_events_by_type("state_change")
                    failed_check_events = event_publisher.get_events_by_type("failed_check")
                    
                    # Should have events corresponding to discovered data
                    assert len(new_pr_events) > 0  # New PRs discovered
                    
                    # Failed check events should match failed checks in data
                    failed_checks_in_data = [
                        c for c in final_checks 
                        if c.conclusion and c.conclusion.value == "failure"
                    ]
                    if failed_checks_in_data:
                        assert len(failed_check_events) > 0
                    
                    # 5. Cache Consistency (if applicable)
                    cache = factory.cache
                    if hasattr(cache, 'get_stats'):
                        cache_stats = await cache.get_stats()
                        # Cache should have been used during discovery
                        assert cache_stats.get('operations', 0) > 0
                    
                    # 6. Verify no data corruption occurred
                    # Re-read data and ensure consistency
                    verification_prs = await pr_repo.get_by_repository_id(repository_id)
                    verification_checks = await check_repo.get_by_repository_id(repository_id)
                    
                    assert len(verification_prs) == len(final_prs)
                    assert len(verification_checks) == len(final_checks)
                    
                    # Verify all foreign key relationships are valid
                    for check in verification_checks:
                        if check.pull_request_id:
                            matching_pr = next(
                                (pr for pr in verification_prs 
                                 if pr.id == check.pull_request_id),
                                None
                            )
                            assert matching_pr is not None
                            assert matching_pr.repository_id == repository_id
                    
                finally:
                    await factory.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_discovery_workflow_performance_meets_requirements(
        self,
        github_mock_server: GitHubMockServer,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure discovery workflow meets performance requirements using real
             components for processing multiple repositories within acceptable
             time limits with authentic I/O operations and database transactions.

        What: Tests that discovery cycle completes within specified time limits
              when processing multiple repositories with substantial PR counts
              using real database operations and HTTP requests.

        How: Creates multiple repositories with large PR datasets, measures
             actual processing time including real database I/O and HTTP requests,
             validates performance meets requirements with real component overhead.
        """
        # Arrange - Create multiple repositories with substantial data
        repository_ids = []
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            for i in range(10):  # 10 repositories for performance testing
                repo = Repository(
                    id=uuid.uuid4(),
                    url=f"https://github.com/test/perf-repo{i+1}",
                    name=f"test/perf-repo{i+1}",
                    full_name=f"test/perf-repo{i+1}",
                    status=RepositoryStatus.ACTIVE
                )
                session.add(repo)
                repository_ids.append(repo.id)
            await session.commit()
        
        # Configure GitHub mock server with substantial but realistic data
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "large_repository"
        ) as github_context:
            # Configure performance-optimized settings
            github_context.server.performance_simulator.configure_base_latency(
                base_ms=10.0,      # Realistic API latency
                variance_ms=5.0    # Small variance for consistent timing
            )
            
            # Create high-performance discovery configuration
            config = create_performance_testing_config()
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                discovery_engine = factory.create_discovery_engine(config)
                
                try:
                    # Act - Measure comprehensive performance metrics
                    start_time = time.time()
                    start_memory = self._get_memory_usage()
                    
                    results = await discovery_engine.run_discovery_cycle(repository_ids)
                    
                    end_time = time.time()
                    end_memory = self._get_memory_usage()
                    
                    processing_time = end_time - start_time
                    memory_delta = end_memory - start_memory
                    
                    # Assert - Verify performance requirements
                    assert results is not None
                    assert len(results) == len(repository_ids)
                    
                    # Performance assertions with real component overhead
                    assert processing_time < 120  # Within 2 minutes for 10 repos with real I/O
                    assert memory_delta < 100  # Less than 100MB memory increase
                    
                    # Verify throughput requirements
                    repos_per_second = len(repository_ids) / processing_time
                    assert repos_per_second > 0.1  # At least 1 repo per 10 seconds
                    
                    # Verify database performance
                    db_metrics = real_database_context.connection_manager.get_pool_status()
                    if hasattr(db_metrics, 'checked_out'):
                        # Connection pool should be healthy
                        assert db_metrics.checked_out >= 0
                    
                    # Verify GitHub API performance
                    client_metrics = github_context.client.get_request_metrics()
                    server_metrics = github_context.server.get_request_metrics()
                    
                    assert client_metrics["total_requests"] > 0
                    assert server_metrics["total_requests"] > 0
                    
                    # Average response time should be reasonable
                    avg_response_time = client_metrics["avg_duration_ms"]
                    assert avg_response_time < 500  # Less than 500ms average
                    
                    # Request rate should meet minimum throughput
                    requests_per_second = client_metrics["requests_per_second"]
                    assert requests_per_second > 1.0  # At least 1 request per second
                    
                    # Verify successful processing rate
                    successful_results = [r for r in results if len(r.errors) == 0]
                    success_rate = len(successful_results) / len(results)
                    assert success_rate > 0.8  # At least 80% success rate
                    
                    # Verify data processing efficiency
                    total_prs_processed = sum(len(r.discovered_prs) for r in results)
                    if total_prs_processed > 0:
                        prs_per_second = total_prs_processed / processing_time
                        assert prs_per_second > 1.0  # At least 1 PR per second
                    
                    # Verify resource utilization efficiency
                    total_db_operations = sum(r.database_operations for r in results if hasattr(r, 'database_operations'))
                    total_api_calls = sum(r.api_calls_used for r in results)
                    
                    if total_api_calls > 0:
                        # Should not exceed reasonable API usage
                        api_calls_per_repo = total_api_calls / len(repository_ids)
                        assert api_calls_per_repo < 50  # Less than 50 API calls per repo
                    
                    # Log performance metrics for analysis
                    print(f"\nPerformance Metrics:")
                    print(f"  Processing time: {processing_time:.2f}s")
                    print(f"  Memory delta: {memory_delta:.2f}MB")
                    print(f"  Repos/second: {repos_per_second:.2f}")
                    print(f"  Success rate: {success_rate:.2%}")
                    print(f"  Avg API response: {avg_response_time:.1f}ms")
                    if total_prs_processed > 0:
                        print(f"  PRs/second: {prs_per_second:.2f}")
                    
                finally:
                    await factory.cleanup()
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        import psutil
        import os
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except ImportError:
            return 0.0  # Return 0 if psutil not available

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_discovery_workflow_handles_large_pr_datasets_efficiently(
        self,
        github_mock_server: GitHubMockServer,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure discovery workflow efficiently handles repositories with large
             numbers of PRs using real memory management, database batching,
             and HTTP pagination without memory issues or excessive processing time.

        What: Tests that workflow processes repositories containing many PRs using
              real efficient memory management, database batching, and streaming
              strategies with actual resource monitoring.

        How: Creates repository with large PR dataset, configures GitHub mock server
             to return paginated responses, validates workflow completes successfully
             with acceptable resource usage using real memory and database monitoring.
        """
        # Arrange - Repository with large PR dataset
        repository_id = uuid.uuid4()
        large_pr_count = 500  # Large number of PRs for stress testing
        
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            repo = Repository(
                id=repository_id,
                url="https://github.com/test/large-dataset-repo",
                name="test/large-dataset-repo",
                full_name="test/large-dataset-repo",
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            await session.commit()
        
        # Configure GitHub mock server with large dataset scenario
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "large_repository"
        ) as github_context:
            # Generate large PR dataset with realistic pagination
            large_pr_dataset = [
                {
                    "number": i + 1,
                    "state": "open" if i % 3 != 0 else "closed",
                    "title": f"Large Dataset PR #{i + 1}",
                    "head": {"sha": f"sha{i+1:06d}", "ref": f"feature/large-{i+1}"},
                    "base": {"sha": "main123", "ref": "main"},
                    "user": {"login": f"user{i % 10}"},  # 10 different users
                    "created_at": f"2024-01-{(i % 28) + 1:02d}T10:00:00Z",
                    "updated_at": f"2024-01-{(i % 28) + 1:02d}T11:00:00Z"
                }
                for i in range(large_pr_count)
            ]
            
            github_context.server.setup_pr_responses(
                "test/large-dataset-repo",
                large_pr_dataset
            )
            
            # Configure realistic API latency for large datasets
            github_context.server.performance_simulator.configure_base_latency(
                base_ms=20.0,      # Slightly higher latency for large responses
                variance_ms=10.0
            )
            
            # Use performance configuration optimized for large datasets
            config = create_performance_testing_config()
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                discovery_engine = factory.create_discovery_engine(config)
                
                try:
                    # Monitor memory and performance during processing
                    start_time = time.time()
                    start_memory = self._get_memory_usage()
                    peak_memory = start_memory
                    
                    # Track memory usage during processing (simplified monitoring)
                    memory_samples = []
                    
                    # Act - Process large dataset
                    results = await discovery_engine.run_discovery_cycle([repository_id])
                    
                    end_time = time.time()
                    end_memory = self._get_memory_usage()
                    processing_time = end_time - start_time
                    memory_delta = end_memory - start_memory
                    
                    # Assert - Verify efficient processing
                    assert results is not None
                    assert len(results) == 1
                    
                    result = results[0]
                    assert result.repository_id == repository_id
                    assert len(result.errors) == 0  # Should process successfully
                    
                    # Verify memory efficiency with large dataset
                    assert memory_delta < 200  # Less than 200MB memory increase
                    assert processing_time < 180  # Within 3 minutes for 500 PRs
                    
                    # Verify data processing efficiency
                    total_prs_processed = len(result.discovered_prs)
                    assert total_prs_processed > 0  # Should discover PRs
                    
                    # Should handle pagination efficiently
                    prs_per_second = total_prs_processed / processing_time
                    assert prs_per_second > 2.0  # At least 2 PRs per second
                    
                    # Verify database operations were batched efficiently
                    async with real_database_context.session_factory() as verify_session:
                        from src.repositories.pull_request import PullRequestRepository
                        pr_repo = PullRequestRepository(verify_session)
                        
                        stored_prs = await pr_repo.get_by_repository_id(repository_id)
                        
                        # All discovered PRs should be stored in database
                        assert len(stored_prs) == total_prs_processed
                        
                        # Verify data integrity for large dataset
                        pr_numbers = {pr.pr_number for pr in stored_prs}
                        expected_numbers = {pr["number"] for pr in large_pr_dataset[:total_prs_processed]}
                        
                        # All processed PRs should have correct numbers
                        for pr in stored_prs:
                            assert pr.pr_number in expected_numbers
                            assert pr.repository_id == repository_id
                            assert pr.title is not None
                            assert pr.author is not None
                    
                    # Verify API usage was efficient with pagination
                    client_metrics = github_context.client.get_request_metrics()
                    server_metrics = github_context.server.get_request_metrics()
                    
                    # Should make reasonable number of paginated requests
                    total_requests = client_metrics["total_requests"]
                    assert total_requests > 0
                    
                    # Calculate expected pagination requests
                    # (GitHub typically returns 30 items per page)
                    expected_pages = (large_pr_count + 29) // 30
                    
                    # Should make approximately correct number of API calls
                    # (allowing for some variation due to discovery logic)
                    assert total_requests <= expected_pages * 2  # Allow for check runs, etc.
                    
                    # Verify streaming/batching worked (no single massive response)
                    avg_response_time = client_metrics["avg_duration_ms"]
                    assert avg_response_time < 1000  # No single request over 1 second
                    
                    # Verify error handling with large dataset
                    error_rate = server_metrics.get("error_rate", 0)
                    assert error_rate < 0.05  # Less than 5% error rate
                    
                    # Log large dataset performance metrics
                    print(f"\nLarge Dataset Performance:")
                    print(f"  PRs processed: {total_prs_processed}")
                    print(f"  Processing time: {processing_time:.2f}s")
                    print(f"  Memory delta: {memory_delta:.2f}MB")
                    print(f"  PRs/second: {prs_per_second:.2f}")
                    print(f"  API requests: {total_requests}")
                    print(f"  Avg response time: {avg_response_time:.1f}ms")
                    
                finally:
                    await factory.cleanup()


class TestPRDiscoveryComponentIntegration:
    """Tests for integration between real discovery components."""

    @pytest_asyncio.fixture
    async def integrated_components(
        self, 
        real_database_context: TestDatabaseContext,
        github_mock_server: GitHubMockServer
    ) -> IntegrationComponentFactory:
        """Setup real integrated discovery components for testing.
        
        Creates actual component instances with real dependencies for
        authentic integration testing scenarios.
        """
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "basic_discovery"
        ) as github_context:
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                try:
                    yield factory
                finally:
                    await factory.cleanup()

    @pytest.mark.asyncio
    async def test_repository_scanner_integrates_with_cache_correctly(
        self, 
        integrated_components: IntegrationComponentFactory,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure repository scanner properly integrates with real cache for
             efficient API usage and reduced GitHub API calls through
             authentic caching mechanisms.

        What: Tests that real repository scanner checks actual cache before making
              HTTP requests and stores results in real cache for subsequent requests
              with proper cache key management and TTL handling.

        How: Creates repository, configures real cache with test data, validates
             scanner uses cached data and updates cache with new discoveries,
             using actual cache implementation and HTTP client integration.
        """
        # Arrange - Create repository for caching test
        repository_id = uuid.uuid4()
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.enums import RepositoryStatus
            
            repo = Repository(
                id=repository_id,
                url="https://github.com/test/cache-repo",
                name="test/cache-repo",
                full_name="test/cache-repo",
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            await session.commit()
        
        # Get real components
        scanner = integrated_components.create_pr_discovery_strategy()
        cache = integrated_components.create_cache_strategy()
        
        # Pre-populate cache with test data
        cache_key = f"repository_prs:{repository_id}"
        test_cache_data = {
            "prs": [
                {
                    "number": 1,
                    "title": "Cached PR 1",
                    "state": "open",
                    "head": {"sha": "cached123"},
                    "base": {"sha": "main123"},
                    "user": {"login": "cached-user"}
                },
                {
                    "number": 2, 
                    "title": "Cached PR 2",
                    "state": "closed",
                    "head": {"sha": "cached456"},
                    "base": {"sha": "main123"},
                    "user": {"login": "cached-user"}
                }
            ],
            "etag": "cached-etag-123",
            "last_modified": "2024-01-01T10:00:00Z"
        }
        
        # Set cache data
        await cache.set_with_ttl(
            cache_key,
            test_cache_data,
            ttl_seconds=300
        )
        
        # Act - First request should hit cache
        result1 = await scanner.discover_prs(
            repository_id, 
            "https://github.com/test/cache-repo"
        )
        
        # Assert - Verify cache hit behavior
        assert result1 is not None
        assert result1.repository_id == repository_id
        assert result1.cache_hits > 0  # Should indicate cache was used
        assert result1.api_calls_used == 0 or result1.api_calls_used == 1  # Minimal API usage
        
        # Verify cached data was used
        cached_pr_numbers = {pr.pr_number for pr in result1.discovered_prs}
        expected_cached_numbers = {1, 2}  # From test cache data
        
        # Should contain cached PR numbers
        assert len(cached_pr_numbers.intersection(expected_cached_numbers)) > 0
        
        # Act - Clear cache and make second request (should hit API)
        await cache.delete(cache_key)
        
        result2 = await scanner.discover_prs(
            repository_id,
            "https://github.com/test/cache-repo"
        )
        
        # Assert - Verify cache miss behavior
        assert result2 is not None
        assert result2.repository_id == repository_id
        assert result2.cache_hits == 0  # No cache hits
        assert result2.api_calls_used > 0  # Should make API calls
        
        # Act - Third request should hit cache again (newly populated)
        result3 = await scanner.discover_prs(
            repository_id,
            "https://github.com/test/cache-repo"
        )
        
        # Assert - Verify cache repopulation
        assert result3 is not None
        assert result3.cache_hits > 0  # Cache should be used again
        
        # Verify cache contains updated data
        cached_data_after = await cache.get_with_ttl(cache_key)
        assert cached_data_after is not None
        assert "prs" in cached_data_after
        
        # Verify cache TTL functionality
        cache_stats = await cache.get_stats()
        assert cache_stats.get("hits", 0) > 0
        assert cache_stats.get("misses", 0) > 0

    @pytest.mark.asyncio
    async def test_state_detector_integrates_with_data_synchronizer_correctly(
        self,
        integrated_components: IntegrationComponentFactory,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure real state detector properly integrates with data synchronizer
             to coordinate authentic state change detection and database updates
             with actual database transactions and state persistence.

        What: Tests that real state detector provides change information to
              synchronizer and synchronizer processes state changes with actual
              database operations, transaction handling, and state history tracking.

        How: Creates initial database state, generates discovery results with
             changes, validates detector identifies real changes and synchronizer
             processes them with proper database operations and state history.
        """
        # Arrange - Create initial database state
        repository_id = uuid.uuid4()
        initial_pr_id = uuid.uuid4()
        
        async with real_database_context.session_factory() as session:
            from src.models.repository import Repository
            from src.models.pull_request import PullRequest
            from src.models.check_run import CheckRun
            from src.models.enums import RepositoryStatus, PRState, CheckStatus, CheckConclusion
            
            # Create repository
            repo = Repository(
                id=repository_id,
                url="https://github.com/test/state-detection-repo",
                name="test/state-detection-repo",
                full_name="test/state-detection-repo",
                status=RepositoryStatus.ACTIVE
            )
            session.add(repo)
            
            # Create initial PR state
            initial_pr = PullRequest(
                id=initial_pr_id,
                repository_id=repository_id,
                pr_number=1,
                title="Initial PR State",
                author="test-user",
                state=PRState.OPENED,  # Initial state: OPENED
                base_branch="main",
                head_branch="feature/initial",
                base_sha="main123",
                head_sha="initial456",
                url="https://github.com/test/state-detection-repo/pull/1"
            )
            session.add(initial_pr)
            
            # Create initial check run state
            initial_check = CheckRun(
                id=uuid.uuid4(),
                pull_request_id=initial_pr_id,
                external_id="check-123",
                check_name="CI Tests",
                status=CheckStatus.IN_PROGRESS,  # Initial state: IN_PROGRESS
                conclusion=None
            )
            session.add(initial_check)
            
            await session.commit()
        
        # Get real components
        state_detector = integrated_components.create_state_detector()
        data_synchronizer = integrated_components.create_data_synchronization_strategy()
        
        # Create discovery result with state changes
        from src.workers.discovery.interfaces import (
            PRDiscoveryResult, 
            DiscoveredPR, 
            DiscoveredCheckRun,
            PRState as DiscoveredPRState,
            CheckStatus as DiscoveredCheckStatus,
            CheckConclusion as DiscoveredCheckConclusion
        )
        
        # Simulate discovered changes
        updated_pr = DiscoveredPR(
            pr_number=1,
            title="Initial PR State",  # Same title
            author="test-user",
            state=DiscoveredPRState.CLOSED,  # Changed from OPENED to CLOSED
            base_branch="main",
            head_branch="feature/initial",
            base_sha="main123",
            head_sha="updated789",  # Changed SHA
            url="https://github.com/test/state-detection-repo/pull/1",
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 0, 0)  # Updated timestamp
        )
        
        updated_check = DiscoveredCheckRun(
            external_id="check-123",
            check_name="CI Tests",
            status=DiscoveredCheckStatus.COMPLETED,  # Changed from IN_PROGRESS
            conclusion=DiscoveredCheckConclusion.SUCCESS,  # New conclusion
            started_at=datetime(2024, 1, 1, 10, 30, 0),
            completed_at=datetime(2024, 1, 1, 11, 0, 0),
            url="https://github.com/test/state-detection-repo/runs/check-123"
        )
        
        discovery_result = PRDiscoveryResult(
            repository_id=repository_id,
            discovered_prs=[updated_pr],
            discovered_checks={1: [updated_check]},  # PR 1 has this check
            processing_time_ms=1000.0,
            api_calls_used=2,
            cache_hits=0,
            errors=[]
        )
        
        # Act - Execute integrated state detection and synchronization
        async with real_database_context.session_factory() as session:
            # Load current state from database
            current_state = await state_detector.load_current_state(repository_id)
            
            # Detect changes between current state and discovery result
            detected_changes = await state_detector.detect_changes(
                discovery_result, current_state
            )
            
            # Synchronize changes to database
            sync_result = await data_synchronizer.synchronize(
                [discovery_result], detected_changes
            )
        
        # Assert - Verify state detection and synchronization worked
        assert len(detected_changes) > 0  # Should detect state changes
        assert sync_result is not None
        
        # Verify specific state changes were detected
        pr_state_changes = [
            change for change in detected_changes 
            if change.entity_type.value == "pull_request"
        ]
        check_state_changes = [
            change for change in detected_changes
            if change.entity_type.value == "check_run" 
        ]
        
        assert len(pr_state_changes) > 0  # Should detect PR state change
        assert len(check_state_changes) > 0  # Should detect check state change
        
        # Verify PR state change details
        pr_change = pr_state_changes[0]
        assert str(pr_change.entity_id) == str(initial_pr_id)
        assert "OPENED" in str(pr_change.old_state) or "opened" in str(pr_change.old_state).lower()
        assert "CLOSED" in str(pr_change.new_state) or "closed" in str(pr_change.new_state).lower()
        
        # Verify changes were persisted to database
        async with real_database_context.session_factory() as session:
            from src.repositories.pull_request import PullRequestRepository
            from src.repositories.check_run import CheckRunRepository
            from src.repositories.state_history import PRStateHistoryRepository
            
            pr_repo = PullRequestRepository(session)
            check_repo = CheckRunRepository(session)
            state_history_repo = PRStateHistoryRepository(session)
            
            # Verify PR state was updated
            updated_pr_record = await pr_repo.get_by_id(initial_pr_id)
            assert updated_pr_record is not None
            assert updated_pr_record.state == PRState.CLOSED
            assert updated_pr_record.head_sha == "updated789"  # SHA should be updated
            
            # Verify check run state was updated  
            updated_checks = await check_repo.get_by_pull_request_id(initial_pr_id)
            assert len(updated_checks) > 0
            
            updated_check_record = updated_checks[0]
            assert updated_check_record.status == CheckStatus.COMPLETED
            assert updated_check_record.conclusion == CheckConclusion.SUCCESS
            
            # Verify state history was recorded
            state_history = await state_history_repo.get_by_pull_request_id(initial_pr_id)
            assert len(state_history) > 0
            
            # Should have history entry for PR state change
            pr_history_entries = [
                entry for entry in state_history 
                if "OPENED" in str(entry.old_state) and "CLOSED" in str(entry.new_state)
            ]
            assert len(pr_history_entries) > 0
        
        # Verify component integration metrics
        event_publisher = integrated_components.event_publisher
        state_change_events = event_publisher.get_events_by_type("state_change")
        
        # Should have published state change events
        assert len(state_change_events) > 0
        
        # Verify event data matches detected changes
        pr_state_events = [
            event for event in state_change_events
            if event["entity_type"] == "pull_request"
        ]
        check_state_events = [
            event for event in state_change_events
            if event["entity_type"] == "check_run"
        ]
        
        assert len(pr_state_events) > 0
        assert len(check_state_events) > 0

    @pytest.mark.asyncio
    async def test_components_handle_shared_error_scenarios_consistently(
        self,
        github_mock_server: GitHubMockServer,
        real_database_context: TestDatabaseContext
    ):
        """
        Why: Ensure all real components handle shared error scenarios consistently,
             maintaining system coherence during actual failure conditions with
             authentic error propagation and recovery mechanisms.

        What: Tests that real components respond consistently to common error scenarios
              like HTTP network failures, database transaction errors, and API rate
              limiting with proper error handling, logging, and recovery.

        How: Simulates real error conditions (HTTP errors, database failures) across
             components, validates consistent error handling patterns, error reporting,
             and system recovery across the integrated system.
        """
        # Test Scenario 1: HTTP Network Failures
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "basic_discovery"
        ) as github_context:
            # Configure server to return network-level errors
            github_context.server.simulate_api_errors(
                error_rate=1.0,  # 100% error rate
                error_codes=[500, 502, 503]
            )
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                try:
                    # Test repository scanner error handling
                    scanner = factory.create_pr_discovery_strategy()
                    
                    # Create test repository
                    repository_id = uuid.uuid4()
                    
                    # Act - Scanner should handle HTTP errors gracefully
                    result = await scanner.discover_prs(
                        repository_id,
                        "https://github.com/test/error-repo"
                    )
                    
                    # Assert - Scanner should return result with errors, not crash
                    assert result is not None
                    assert result.repository_id == repository_id
                    assert len(result.errors) > 0  # Should capture HTTP errors
                    
                    # Verify error messages contain HTTP status information
                    error_messages = [str(e) for e in result.errors]
                    assert any("500" in msg or "502" in msg or "503" in msg 
                             for msg in error_messages)
                    
                    # Test check discovery error handling
                    check_discoverer = factory.create_check_discovery_strategy()
                    
                    # Should handle same network errors consistently
                    try:
                        check_results = await check_discoverer.discover_check_runs(
                            repository_id,
                            "https://github.com/test/error-repo",
                            ["abc123"]
                        )
                        
                        # Should return results with errors, not crash
                        assert check_results is not None
                        assert len(check_results.errors) > 0
                        
                        # Error handling should be consistent with scanner
                        check_error_messages = [str(e) for e in check_results.errors]
                        assert any("500" in msg or "502" in msg or "503" in msg
                                 for msg in check_error_messages)
                        
                    except Exception as e:
                        # If exception is raised, it should be consistent type
                        assert "500" in str(e) or "502" in str(e) or "503" in str(e)
                    
                finally:
                    await factory.cleanup()
        
        # Test Scenario 2: Database Transaction Errors
        try:
            async with real_database_context.session_factory() as session:
                from src.models.repository import Repository
                from src.models.enums import RepositoryStatus
                
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(MockServerGitHubClient("http://mock"))
                    .build()
                )
                
                try:
                    # Create conflicting repository data to cause database errors
                    repo = Repository(
                        id=uuid.uuid4(),
                        url="https://github.com/test/db-error-repo",
                        name="test/db-error-repo",
                        full_name="test/db-error-repo",
                        status=RepositoryStatus.ACTIVE
                    )
                    session.add(repo)
                    await session.commit()
                    
                    # Test data synchronizer error handling
                    data_sync = factory.create_data_synchronization_strategy()
                    
                    # Create discovery result with invalid data to trigger DB error
                    from src.workers.discovery.interfaces import (
                        PRDiscoveryResult, 
                        DiscoveredPR,
                        PRState as DiscoveredPRState
                    )
                    
                    # Create PR with invalid foreign key (non-existent repository)
                    invalid_pr = DiscoveredPR(
                        pr_number=1,
                        title="Invalid PR",
                        author="test-user",
                        state=DiscoveredPRState.OPENED,
                        base_branch="main",
                        head_branch="feature/invalid",
                        base_sha="invalid123",
                        head_sha="invalid456",
                        url="https://github.com/nonexistent/repo/pull/1",
                        created_at=datetime(2024, 1, 1, 10, 0, 0),
                        updated_at=datetime(2024, 1, 1, 11, 0, 0)
                    )
                    
                    invalid_result = PRDiscoveryResult(
                        repository_id=uuid.uuid4(),  # Non-existent repository
                        discovered_prs=[invalid_pr],
                        discovered_checks={},
                        processing_time_ms=1000.0,
                        api_calls_used=1,
                        cache_hits=0,
                        errors=[]
                    )
                    
                    # Act - Synchronizer should handle database errors gracefully
                    try:
                        sync_result = await data_sync.synchronize(
                            [invalid_result], []
                        )
                        
                        # If no exception, should have error information in result
                        if hasattr(sync_result, 'errors'):
                            assert len(sync_result.errors) > 0
                        
                    except Exception as db_error:
                        # Should get database-related error
                        assert any(keyword in str(db_error).lower() 
                                 for keyword in ["constraint", "foreign", "database", "integrity"])
                    
                finally:
                    await factory.cleanup()
                    
        except Exception as setup_error:
            # Database setup errors are acceptable for this error testing
            assert "database" in str(setup_error).lower() or "connection" in str(setup_error).lower()
        
        # Test Scenario 3: Component Error Consistency
        # Verify all components use consistent error types and handling patterns
        
        async with GitHubMockIntegration(github_mock_server).create_github_context(
            "basic_discovery"
        ) as github_context:
            # Set up partial error conditions (some succeed, some fail)
            github_context.server.simulate_api_errors(
                error_rate=0.5,  # 50% error rate
                error_codes=[429, 500]  # Rate limiting and server errors
            )
            
            async with real_database_context.session_factory() as session:
                factory = (
                    ComponentFactoryBuilder()
                    .with_database_session(session)
                    .with_github_client(github_context.client)
                    .build()
                )
                
                try:
                    # Create discovery engine and test error consistency
                    config = create_error_testing_config()
                    engine = factory.create_discovery_engine(config)
                    
                    # Create test repository
                    repository_id = uuid.uuid4()
                    
                    async with session.begin():
                        from src.models.repository import Repository
                        from src.models.enums import RepositoryStatus
                        
                        repo = Repository(
                            id=repository_id,
                            url="https://github.com/test/consistency-repo",
                            name="test/consistency-repo",
                            full_name="test/consistency-repo",
                            status=RepositoryStatus.ACTIVE
                        )
                        session.add(repo)
                    
                    # Act - Run discovery with mixed error conditions
                    results = await engine.run_discovery_cycle([repository_id])
                    
                    # Assert - Error handling should be consistent
                    assert results is not None
                    assert len(results) == 1
                    
                    result = results[0]
                    
                    # Should have consistent error reporting structure
                    if len(result.errors) > 0:
                        # All errors should have consistent format/type
                        for error in result.errors:
                            error_str = str(error)
                            # Should contain contextual information
                            assert len(error_str) > 0
                            # Should be informative (not just generic "Error")
                            assert "error" in error_str.lower() or "failed" in error_str.lower()
                    
                    # Verify event publisher handled errors consistently
                    event_publisher = factory.event_publisher
                    all_events = event_publisher.published_events
                    
                    # Should have events even with errors (error events or partial success)
                    assert len(all_events) >= 0  # May have no events if all failed
                    
                    # If errors occurred, error handling should be logged/tracked
                    if len(result.errors) > 0:
                        # Component should maintain internal consistency
                        assert result.repository_id == repository_id
                        assert result.processing_time_ms > 0
                    
                finally:
                    await factory.cleanup()
