"""
Integration tests for PR discovery service with GitHub API interactions.

Tests GitHub API integration patterns, caching behavior, error handling,
and realistic data processing scenarios with controlled mocking.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse, parse_qs

import pytest
from aiohttp import ClientResponse, ClientError

from src.github.client import GitHubClient
from src.models.repository import Repository
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.models import CheckRunData, PRData


@pytest.mark.integration
class TestGitHubPRDiscoveryServiceIntegration:
    """Integration tests for GitHub API discovery patterns."""

    @pytest.mark.asyncio
    async def test_realistic_github_api_pagination(self, test_repository):
        """
        Why: Verify pagination handling works with realistic GitHub API patterns
        What: Tests discovery service handles multi-page GitHub API responses
        How: Mocks GitHub client with paginated responses and validates
             all data is collected across multiple pages
        """
        # Create mock GitHub client with realistic pagination
        mock_client = MagicMock(spec=GitHubClient)
        
        # Mock paginated PR responses
        async def mock_paginate(url, params=None, per_page=100):
            """Mock paginator that yields individual PR objects across pages."""
            if "/pulls" in url:
                # First page - 2 PRs
                yield {
                    "number": 101,
                    "title": "Feature: Add user authentication",
                    "user": {"login": "alice"},
                    "state": "open",
                    "draft": False,
                    "base": {"ref": "main", "sha": "abcd1234"},
                    "head": {"ref": "feature/auth", "sha": "efgh5678"},
                    "html_url": "https://github.com/test/repo/pull/101",
                    "body": "Implements user authentication system",
                    "labels": [{"name": "feature"}, {"name": "security"}],
                    "assignees": [{"login": "alice"}],
                    "milestone": {"title": "v2.0"},
                    "created_at": "2024-01-15T10:00:00Z",
                    "updated_at": "2024-01-15T14:30:00Z",
                    "merged": False,
                }
                
                yield {
                    "number": 102,
                    "title": "Fix: Memory leak in data processor",
                    "user": {"login": "bob"},
                    "state": "open",
                    "draft": True,
                    "base": {"ref": "main", "sha": "abcd1234"},
                    "head": {"ref": "fix/memory-leak", "sha": "ijkl9012"},
                    "html_url": "https://github.com/test/repo/pull/102",
                    "body": "Fixes memory leak in background processor",
                    "labels": [{"name": "bug"}, {"name": "performance"}],
                    "assignees": [{"login": "bob"}, {"login": "charlie"}],
                    "created_at": "2024-01-14T09:15:00Z",
                    "updated_at": "2024-01-15T11:20:00Z",
                    "merged": False,
                }
                
                # Second page - 1 PR
                yield {
                    "number": 103,
                    "title": "Docs: Update API documentation",
                    "user": {"login": "docs-bot"},
                    "state": "closed",
                    "draft": False,
                    "base": {"ref": "main", "sha": "abcd1234"},
                    "head": {"ref": "docs/api-update", "sha": "mnop3456"},
                    "html_url": "https://github.com/test/repo/pull/103",
                    "body": "Updates API documentation with new endpoints",
                    "labels": [{"name": "documentation"}],
                    "assignees": [],
                    "merged": True,
                    "merged_at": "2024-01-13T16:45:00Z",
                    "created_at": "2024-01-12T14:00:00Z",
                    "updated_at": "2024-01-13T16:45:00Z",
                    "closed_at": "2024-01-13T16:45:00Z",
                }
        
        mock_client.paginate = mock_paginate
        
        # Create discovery service
        service = GitHubPRDiscoveryService(
            github_client=mock_client,
            max_concurrent_requests=5,
            cache_ttl_seconds=300,
        )
        
        # Execute discovery
        prs = await service.discover_prs(test_repository)
        
        # Verify all PRs were collected
        assert len(prs) == 3
        
        # Verify first PR (feature)
        feature_pr = next(pr for pr in prs if pr.number == 101)
        assert feature_pr.title == "Feature: Add user authentication"
        assert feature_pr.author == "alice"
        assert feature_pr.state == "open"
        assert feature_pr.draft is False
        assert feature_pr.base_branch == "main"
        assert feature_pr.head_branch == "feature/auth"
        assert "feature" in feature_pr.labels
        assert "security" in feature_pr.labels
        assert "alice" in feature_pr.assignees
        assert feature_pr.milestone == "v2.0"
        
        # Verify second PR (draft bugfix)
        bugfix_pr = next(pr for pr in prs if pr.number == 102)
        assert bugfix_pr.title == "Fix: Memory leak in data processor"
        assert bugfix_pr.author == "bob"
        assert bugfix_pr.draft is True
        assert "bug" in bugfix_pr.labels
        assert len(bugfix_pr.assignees) == 2
        
        # Verify third PR (merged docs)
        docs_pr = next(pr for pr in prs if pr.number == 103)
        assert docs_pr.state == "closed"
        assert docs_pr.merged is True
        assert docs_pr.merged_at is not None
        assert "documentation" in docs_pr.labels

    @pytest.mark.asyncio
    async def test_check_run_discovery_with_complex_scenarios(self, test_repository):
        """
        Why: Verify check run discovery handles complex real-world scenarios
        What: Tests discovery of check runs with various states and conclusions
        How: Mocks GitHub API responses with diverse check run data and
             validates proper parsing and data extraction
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        # Create test PR data
        test_pr = PRData(
            number=150,
            title="Test PR for check runs",
            author="developer",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature/test",
            base_sha="base123",
            head_sha="head456",
            url="https://github.com/test/repo/pull/150",
        )
        
        # Mock check run responses with complex scenarios
        async def mock_paginate(url, per_page=100):
            """Mock paginator for check run API responses."""
            if "/check-runs" in url:
                # GitHub API returns wrapper object with check_runs array
                yield {
                    "total_count": 6,
                    "check_runs": [
                        {
                            "id": 2001,
                            "name": "CI / Build (ubuntu-latest, python3.9)",
                            "status": "completed",
                            "conclusion": "success",
                            "check_suite": {"id": 5001},
                            "details_url": "https://github.com/test/repo/actions/runs/2001",
                            "html_url": "https://github.com/test/repo/actions/runs/2001",
                            "output": {
                                "title": "Build Successful",
                                "summary": "All tests passed successfully",
                                "text": "✅ 42 tests passed\n✅ Coverage: 95%",
                            },
                            "started_at": "2024-01-15T10:00:00Z",
                            "completed_at": "2024-01-15T10:05:23Z",
                            "app": {"name": "GitHub Actions"},
                        },
                        {
                            "id": 2002,
                            "name": "CI / Build (ubuntu-latest, python3.10)",
                            "status": "completed",
                            "conclusion": "failure",
                            "check_suite": {"id": 5001},
                            "details_url": "https://github.com/test/repo/actions/runs/2002",
                            "html_url": "https://github.com/test/repo/actions/runs/2002",
                            "output": {
                                "title": "Build Failed",
                                "summary": "Tests failed due to compatibility issues",
                                "text": "❌ 3 tests failed\n⚠️  Python 3.10 compatibility issues",
                            },
                            "started_at": "2024-01-15T10:00:00Z",
                            "completed_at": "2024-01-15T10:08:45Z",
                            "app": {"name": "GitHub Actions"},
                        },
                        {
                            "id": 2003,
                            "name": "CodeQL Analysis",
                            "status": "in_progress",
                            "conclusion": None,
                            "check_suite": {"id": 5002},
                            "details_url": "https://github.com/test/repo/security/code-scanning",
                            "html_url": "https://github.com/test/repo/security/code-scanning",
                            "started_at": "2024-01-15T10:01:00Z",
                            "app": {"name": "CodeQL"},
                        },
                    ],
                }
                
                # Second page with more check runs
                yield {
                    "total_count": 6,
                    "check_runs": [
                        {
                            "id": 2004,
                            "name": "Dependency Review",
                            "status": "completed",
                            "conclusion": "neutral",
                            "check_suite": {"id": 5003},
                            "details_url": "https://github.com/test/repo/network/dependencies",
                            "output": {
                                "title": "Dependencies Reviewed",
                                "summary": "No security vulnerabilities found",
                                "text": "Reviewed 127 dependencies",
                            },
                            "started_at": "2024-01-15T10:00:30Z",
                            "completed_at": "2024-01-15T10:02:15Z",
                            "app": {"name": "GitHub"},
                        },
                        {
                            "id": 2005,
                            "name": "Deploy Preview",
                            "status": "queued",
                            "conclusion": None,
                            "check_suite": {"id": 5004},
                            "details_url": "https://deploy-preview-150.netlify.app",
                            "app": {"name": "Netlify"},
                        },
                        {
                            "id": 2006,
                            "name": "Performance Benchmark",
                            "status": "completed",
                            "conclusion": "cancelled",
                            "check_suite": {"id": 5005},
                            "details_url": "https://performance.example.com/reports/150",
                            "output": {
                                "title": "Benchmark Cancelled",
                                "summary": "Cancelled due to resource constraints",
                                "text": "Will retry in next commit",
                            },
                            "started_at": "2024-01-15T10:03:00Z",
                            "completed_at": "2024-01-15T10:03:30Z",
                            "app": {"name": "PerfBot"},
                        },
                    ],
                }
        
        mock_client.paginate = mock_paginate
        
        service = GitHubPRDiscoveryService(mock_client)
        
        # Execute check run discovery
        check_runs = await service.discover_check_runs(test_repository, test_pr)
        
        # Verify all check runs were discovered
        assert len(check_runs) == 6
        
        # Verify successful build
        successful_build = next(cr for cr in check_runs if cr.external_id == "2001")
        assert successful_build.check_name == "CI / Build (ubuntu-latest, python3.9)"
        assert successful_build.status == "completed"
        assert successful_build.conclusion == "success"
        assert successful_build.check_suite_id == "5001"
        assert "All tests passed" in successful_build.output_summary
        assert "42 tests passed" in successful_build.output_text
        assert successful_build.started_at is not None
        assert successful_build.completed_at is not None
        
        # Verify failed build
        failed_build = next(cr for cr in check_runs if cr.external_id == "2002")
        assert failed_build.conclusion == "failure"
        assert "Build Failed" in failed_build.output_title
        assert "compatibility issues" in failed_build.output_summary
        
        # Verify in-progress check
        in_progress = next(cr for cr in check_runs if cr.external_id == "2003")
        assert in_progress.status == "in_progress"
        assert in_progress.conclusion is None
        assert in_progress.started_at is not None
        assert in_progress.completed_at is None
        
        # Verify neutral conclusion
        neutral_check = next(cr for cr in check_runs if cr.external_id == "2004")
        assert neutral_check.conclusion == "neutral"
        
        # Verify queued check
        queued_check = next(cr for cr in check_runs if cr.external_id == "2005")
        assert queued_check.status == "queued"
        assert queued_check.started_at is None
        
        # Verify cancelled check
        cancelled_check = next(cr for cr in check_runs if cr.external_id == "2006")
        assert cancelled_check.conclusion == "cancelled"

    @pytest.mark.asyncio
    async def test_github_api_error_handling(self, test_repository):
        """
        Why: Verify service handles GitHub API errors gracefully
        What: Tests various error scenarios (rate limits, 404s, network errors)
        How: Injects different types of API errors and validates proper
             error handling, retry logic, and graceful degradation
        """
        mock_client = MagicMock(spec=GitHubClient)
        service = GitHubPRDiscoveryService(mock_client)
        
        # Test 1: Rate limit error
        async def rate_limit_error(*args, **kwargs):
            raise ClientError("API rate limit exceeded")
        
        mock_client.paginate = rate_limit_error
        
        with pytest.raises(Exception) as exc_info:
            await service.discover_prs(test_repository)
        assert "rate limit" in str(exc_info.value).lower()
        
        # Test 2: Repository not found (404)
        async def not_found_error(*args, **kwargs):
            raise ClientError("Repository not found")
        
        mock_client.paginate = not_found_error
        
        with pytest.raises(Exception) as exc_info:
            await service.discover_prs(test_repository)
        assert "not found" in str(exc_info.value).lower()
        
        # Test 3: Network timeout
        async def timeout_error(*args, **kwargs):
            raise asyncio.TimeoutError("Request timeout")
        
        mock_client.paginate = timeout_error
        
        with pytest.raises(Exception) as exc_info:
            await service.discover_prs(test_repository)
        assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_check_run_discovery(self, test_repository):
        """
        Why: Verify concurrent discovery of check runs works efficiently
        What: Tests batch discovery of check runs for multiple PRs
        How: Creates multiple PRs, discovers check runs concurrently,
             and validates proper concurrency handling and results
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        # Create multiple test PRs
        test_prs = [
            PRData(
                number=200 + i,
                title=f"Test PR {i}",
                author=f"dev{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/test-{i}",
                base_sha=f"base{i:03d}",
                head_sha=f"head{i:03d}",
                url=f"https://github.com/test/repo/pull/{200 + i}",
            )
            for i in range(5)
        ]
        
        # Track concurrent requests
        request_count = 0
        max_concurrent = 0
        active_requests = 0
        
        async def mock_paginate(url, per_page=100):
            nonlocal request_count, max_concurrent, active_requests
            
            request_count += 1
            active_requests += 1
            max_concurrent = max(max_concurrent, active_requests)
            
            # Simulate processing time
            await asyncio.sleep(0.1)
            
            # Extract PR number from URL to return specific check runs
            pr_number = None
            for pr in test_prs:
                if f"/{pr.head_sha}/check-runs" in url:
                    pr_number = pr.number
                    break
            
            if pr_number:
                yield {
                    "total_count": 2,
                    "check_runs": [
                        {
                            "id": pr_number * 1000 + 1,
                            "name": f"Build for PR {pr_number}",
                            "status": "completed",
                            "conclusion": "success",
                            "check_suite": {"id": pr_number * 100},
                            "details_url": f"https://example.com/{pr_number}/1",
                            "started_at": "2024-01-15T10:00:00Z",
                            "completed_at": "2024-01-15T10:05:00Z",
                        },
                        {
                            "id": pr_number * 1000 + 2,
                            "name": f"Test for PR {pr_number}",
                            "status": "completed",
                            "conclusion": "success",
                            "check_suite": {"id": pr_number * 100},
                            "details_url": f"https://example.com/{pr_number}/2",
                            "started_at": "2024-01-15T10:00:00Z",
                            "completed_at": "2024-01-15T10:03:00Z",
                        },
                    ],
                }
            
            active_requests -= 1
        
        mock_client.paginate = mock_paginate
        
        service = GitHubPRDiscoveryService(
            mock_client, max_concurrent_requests=3  # Limit concurrency
        )
        
        # Execute batch discovery
        check_runs_by_pr = await service.discover_check_runs_batch(
            test_repository, test_prs
        )
        
        # Verify results
        assert len(check_runs_by_pr) == 5
        assert request_count == 5  # One request per PR
        assert max_concurrent <= 3  # Respected concurrency limit
        
        # Verify each PR has check runs
        for pr in test_prs:
            assert pr.number in check_runs_by_pr
            check_runs = check_runs_by_pr[pr.number]
            assert len(check_runs) == 2
            
            # Verify check run data
            build_check = next(cr for cr in check_runs if "Build" in cr.check_name)
            assert build_check.external_id == str(pr.number * 1000 + 1)
            assert build_check.conclusion == "success"

    @pytest.mark.asyncio
    async def test_caching_behavior(self, test_repository):
        """
        Why: Verify caching reduces API calls and works correctly
        What: Tests ETag caching and cache invalidation behavior
        How: Makes repeated requests and validates cache hits and misses
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        call_count = 0
        cached_response = [
            {
                "number": 300,
                "title": "Cached PR",
                "user": {"login": "cache-test"},
                "state": "open",
                "draft": False,
                "base": {"ref": "main", "sha": "cached123"},
                "head": {"ref": "feature/cache", "sha": "cached456"},
                "html_url": "https://github.com/test/repo/pull/300",
                "body": "This PR tests caching",
                "labels": [],
                "assignees": [],
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "merged": False,
            }
        ]
        
        async def mock_paginate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            for item in cached_response:
                yield item
        
        mock_client.paginate = mock_paginate
        
        service = GitHubPRDiscoveryService(
            mock_client, cache_ttl_seconds=1  # Short cache for testing
        )
        
        # First call - should hit API
        prs1 = await service.discover_prs(test_repository)
        assert len(prs1) == 1
        assert call_count == 1
        
        # Second call immediately - should use cache
        prs2 = await service.discover_prs(test_repository)
        assert len(prs2) == 1
        assert call_count == 1  # No additional API call
        
        # Verify cached data is identical
        assert prs1[0].number == prs2[0].number
        assert prs1[0].title == prs2[0].title
        
        # Wait for cache to expire
        await asyncio.sleep(1.1)
        
        # Third call - cache expired, should hit API again
        prs3 = await service.discover_prs(test_repository)
        assert len(prs3) == 1
        assert call_count == 2  # Additional API call
        
        # Test cache clearing
        service.clear_cache()
        
        # Fourth call - cache cleared, should hit API
        prs4 = await service.discover_prs(test_repository)
        assert len(prs4) == 1
        assert call_count == 3  # Additional API call

    @pytest.mark.asyncio
    async def test_incremental_updates_with_since_parameter(self, test_repository):
        """
        Why: Verify incremental updates work correctly with since parameter
        What: Tests that since parameter is properly handled for efficient updates
        How: Makes requests with since parameter and validates filtering behavior
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        # Track parameters passed to paginate
        captured_params = []
        
        async def mock_paginate(url, params=None, per_page=100):
            captured_params.append(params.copy() if params else {})
            
            # Return different data based on since parameter
            if params and "since" in params:
                # Only return recent PRs for incremental update
                yield {
                    "number": 400,
                    "title": "Recent PR",
                    "user": {"login": "recent-dev"},
                    "state": "open",
                    "draft": False,
                    "base": {"ref": "main", "sha": "recent123"},
                    "head": {"ref": "feature/recent", "sha": "recent456"},
                    "html_url": "https://github.com/test/repo/pull/400",
                    "body": "This is a recent PR",
                    "labels": [],
                    "assignees": [],
                    "created_at": "2024-01-16T10:00:00Z",
                    "updated_at": "2024-01-16T10:00:00Z",
                    "merged": False,
                }
            else:
                # Return all PRs for full sync
                yield {
                    "number": 401,
                    "title": "Old PR",
                    "user": {"login": "old-dev"},
                    "state": "closed",
                    "draft": False,
                    "base": {"ref": "main", "sha": "old123"},
                    "head": {"ref": "feature/old", "sha": "old456"},
                    "html_url": "https://github.com/test/repo/pull/401",
                    "body": "This is an old PR",
                    "labels": [],
                    "assignees": [],
                    "created_at": "2024-01-10T10:00:00Z",
                    "updated_at": "2024-01-10T10:00:00Z",
                    "merged": False,
                    "closed_at": "2024-01-11T10:00:00Z",
                }
        
        mock_client.paginate = mock_paginate
        service = GitHubPRDiscoveryService(mock_client)
        
        # Test 1: Full sync (no since parameter)
        captured_params.clear()
        full_prs = await service.discover_prs(test_repository)
        
        assert len(full_prs) == 1
        assert full_prs[0].title == "Old PR"
        assert len(captured_params) == 1
        assert "since" not in captured_params[0]
        
        # Test 2: Incremental sync (with since parameter)
        since_time = datetime(2024, 1, 15, tzinfo=timezone.utc)
        captured_params.clear()
        
        incremental_prs = await service.discover_prs(test_repository, since=since_time)
        
        assert len(incremental_prs) == 1
        assert incremental_prs[0].title == "Recent PR"
        assert len(captured_params) == 1
        assert "since" in captured_params[0]
        assert captured_params[0]["since"] == "2024-01-15T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_malformed_data_handling(self, test_repository):
        """
        Why: Verify service handles malformed GitHub API responses gracefully
        What: Tests resilience against incomplete or invalid API data
        How: Provides malformed API responses and validates error handling
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        async def mock_paginate_malformed(*args, **kwargs):
            # Yield a mix of valid and malformed data
            
            # Valid PR
            yield {
                "number": 500,
                "title": "Valid PR",
                "user": {"login": "valid-user"},
                "state": "open",
                "draft": False,
                "base": {"ref": "main", "sha": "valid123"},
                "head": {"ref": "feature/valid", "sha": "valid456"},
                "html_url": "https://github.com/test/repo/pull/500",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "merged": False,
            }
            
            # Missing required fields
            yield {
                "number": 501,
                "title": "Incomplete PR",
                # Missing user field
                "state": "open",
                "draft": False,
                # Missing base/head fields
                "html_url": "https://github.com/test/repo/pull/501",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
            }
            
            # Invalid timestamp format
            yield {
                "number": 502,
                "title": "Invalid Timestamps",
                "user": {"login": "timestamp-user"},
                "state": "open",
                "draft": False,
                "base": {"ref": "main", "sha": "time123"},
                "head": {"ref": "feature/time", "sha": "time456"},
                "html_url": "https://github.com/test/repo/pull/502",
                "created_at": "invalid-timestamp",
                "updated_at": "also-invalid",
                "merged": False,
            }
        
        mock_client.paginate = mock_paginate_malformed
        service = GitHubPRDiscoveryService(mock_client)
        
        # Execute discovery - should handle malformed data gracefully
        prs = await service.discover_prs(test_repository)
        
        # Should only have successfully parsed PRs
        # The service should log warnings for malformed data but continue processing
        assert len(prs) >= 1  # At least the valid PR should be processed
        
        valid_pr = next((pr for pr in prs if pr.number == 500), None)
        assert valid_pr is not None
        assert valid_pr.title == "Valid PR"
        assert valid_pr.author == "valid-user"


@pytest.mark.integration 
class TestGitHubPRDiscoveryServicePerformance:
    """Performance and scalability tests for GitHub discovery service."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_repository_discovery_performance(self, test_repository):
        """
        Why: Verify service can handle large repositories efficiently
        What: Tests discovery performance with many PRs and check runs
        How: Simulates large repository with hundreds of PRs and validates
             performance meets acceptable benchmarks
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        # Generate large number of PRs
        large_pr_count = 500
        
        async def mock_paginate_large(*args, **kwargs):
            # Generate PRs in batches to simulate pagination
            batch_size = 100
            for batch_start in range(0, large_pr_count, batch_size):
                for i in range(batch_start, min(batch_start + batch_size, large_pr_count)):
                    yield {
                        "number": 1000 + i,
                        "title": f"Large Repo PR #{i}",
                        "user": {"login": f"dev{i % 50}"},  # 50 different developers
                        "state": "open" if i % 3 != 0 else "closed",
                        "draft": i % 10 == 0,
                        "base": {"ref": "main", "sha": f"base{i:06d}"},
                        "head": {"ref": f"feature/large-{i}", "sha": f"head{i:06d}"},
                        "html_url": f"https://github.com/test/repo/pull/{1000 + i}",
                        "body": f"This is PR #{i} in a large repository",
                        "labels": [{"name": f"category-{i % 10}"}],
                        "assignees": [{"login": f"reviewer{i % 20}"}] if i % 5 == 0 else [],
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z",
                        "merged": i % 7 == 0,
                    }
        
        mock_client.paginate = mock_paginate_large
        service = GitHubPRDiscoveryService(mock_client, max_concurrent_requests=10)
        
        # Measure discovery performance
        start_time = datetime.now(timezone.utc)
        prs = await service.discover_prs(test_repository)
        end_time = datetime.now(timezone.utc)
        
        discovery_time = (end_time - start_time).total_seconds()
        
        # Verify results
        assert len(prs) == large_pr_count
        assert discovery_time < 60.0  # Should complete within 60 seconds
        
        # Verify data quality with sampling
        sample_prs = prs[:10]  # Check first 10 PRs
        for pr in sample_prs:
            assert pr.number >= 1000
            assert "Large Repo PR" in pr.title
            assert pr.author.startswith("dev")
            assert pr.base_branch == "main"

    @pytest.mark.asyncio
    async def test_concurrent_api_rate_limiting(self, test_repository):
        """
        Why: Verify service respects GitHub API rate limits during high concurrency
        What: Tests that concurrent requests are properly rate-limited
        How: Creates many concurrent requests and validates they're throttled
             according to the configured concurrency limits
        """
        mock_client = MagicMock(spec=GitHubClient)
        
        # Track concurrent request handling
        active_requests = 0
        max_concurrent_observed = 0
        request_times = []
        
        async def mock_paginate_rate_limited(*args, **kwargs):
            nonlocal active_requests, max_concurrent_observed
            
            active_requests += 1
            max_concurrent_observed = max(max_concurrent_observed, active_requests)
            request_start = datetime.now(timezone.utc)
            
            # Simulate API processing time
            await asyncio.sleep(0.2)
            
            active_requests -= 1
            request_end = datetime.now(timezone.utc)
            request_times.append((request_start, request_end))
            
            # Return minimal check run data
            yield {
                "total_count": 1,
                "check_runs": [{
                    "id": 9999,
                    "name": "Rate Limited Check",
                    "status": "completed",
                    "conclusion": "success",
                    "check_suite": {"id": 8888},
                    "details_url": "https://example.com/rate-test",
                    "started_at": "2024-01-15T10:00:00Z",
                    "completed_at": "2024-01-15T10:05:00Z",
                }]
            }
        
        mock_client.paginate = mock_paginate_rate_limited
        
        # Create service with low concurrency limit
        service = GitHubPRDiscoveryService(
            mock_client, max_concurrent_requests=3
        )
        
        # Create multiple PRs to trigger concurrent requests
        test_prs = [
            PRData(
                number=600 + i,
                title=f"Concurrent Test PR {i}",
                author=f"concurrent-dev{i}",
                state="open",
                draft=False,
                base_branch="main",
                head_branch=f"feature/concurrent-{i}",
                base_sha=f"base{i:03d}",
                head_sha=f"head{i:03d}",
                url=f"https://github.com/test/repo/pull/{600 + i}",
            )
            for i in range(10)
        ]
        
        # Execute concurrent discovery
        start_time = datetime.now(timezone.utc)
        check_runs_by_pr = await service.discover_check_runs_batch(
            test_repository, test_prs
        )
        end_time = datetime.now(timezone.utc)
        
        total_time = (end_time - start_time).total_seconds()
        
        # Verify concurrency was limited
        assert max_concurrent_observed <= 3  # Should not exceed limit
        assert len(check_runs_by_pr) == 10  # All PRs processed
        
        # Verify timing - with 10 requests, limit of 3, and 0.2s each,
        # should take at least ceil(10/3) * 0.2 = 0.8 seconds
        assert total_time >= 0.6  # Allow some variance
        
        # Verify all PRs have check runs
        for pr in test_prs:
            assert pr.number in check_runs_by_pr
            assert len(check_runs_by_pr[pr.number]) == 1