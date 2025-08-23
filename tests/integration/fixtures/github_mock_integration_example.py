"""
Integration Example: Using GitHub Mock Server with Real GitHubClient

This module demonstrates how to use the GitHub Mock Server with the actual
GitHubClient implementation from src/github/client.py for integration testing.
"""

import asyncio
from typing import Dict, Any

from src.github.client import GitHubClient, GitHubClientConfig
from src.github.auth import PersonalAccessTokenAuth
from tests.integration.fixtures.github_mock_server import (
    GitHubMockServer,
    GitHubMockIntegration,
    GITHUB_MOCK_SCENARIOS,
)


class MockTokenAuth(PersonalAccessTokenAuth):
    """Mock authentication provider for testing.
    
    This extends the real PersonalAccessTokenAuth but uses a mock token
    that works with the mock server.
    """
    
    def __init__(self):
        """Initialize with mock token."""
        super().__init__("mock_github_token_for_testing")


async def demonstrate_github_client_integration():
    """
    Demonstrate how to use the GitHub Mock Server with real GitHubClient.
    
    This example shows the complete integration pattern that should be used
    in actual integration tests.
    """
    print("🚀 Starting GitHub Mock Server Integration Example")
    
    # Step 1: Create and configure mock server
    mock_server = GitHubMockServer()
    mock_integration = GitHubMockIntegration(mock_server)
    
    # Step 2: Use the integration context manager
    async with mock_integration.create_github_context("basic_discovery") as context:
        print(f"✅ Mock server running at: {context.base_url}")
        
        # Step 3: Create real GitHubClient pointing to mock server
        auth = MockTokenAuth()
        config = GitHubClientConfig(
            base_url=context.base_url,  # Point to mock server instead of GitHub
            timeout=10,
            max_retries=2,
            rate_limit_buffer=50
        )
        
        # Step 4: Use GitHubClient exactly as in production code
        async with GitHubClient(auth=auth, config=config) as github_client:
            print("🔑 GitHubClient configured with mock server")
            
            # Test repository operations
            try:
                repo = await github_client.get_repo("test", "repo1")
                print(f"📁 Repository: {repo['full_name']}")
                print(f"   Description: {repo['description']}")
                print(f"   Language: {repo['language']}")
                print(f"   Stars: {repo['stargazers_count']}")
                
            except Exception as e:
                print(f"❌ Repository fetch failed: {e}")
                return
            
            # Test pull request operations
            try:
                # Use paginator for pull requests (real pagination)
                pr_paginator = github_client.list_pulls("test", "repo1", state="all")
                
                pulls = []
                async for pr in pr_paginator:
                    pulls.append(pr)
                
                print(f"🔄 Found {len(pulls)} pull requests:")
                for pr in pulls:
                    print(f"   #{pr['number']}: {pr['title']} ({pr['state']})")
                    
            except Exception as e:
                print(f"❌ Pull request fetch failed: {e}")
                return
            
            # Test rate limit checking
            try:
                rate_limit = await github_client.get_rate_limit()
                core_limit = rate_limit['resources']['core']
                print(f"⚡ Rate Limit Status:")
                print(f"   Limit: {core_limit['limit']}")
                print(f"   Remaining: {core_limit['remaining']}")
                print(f"   Reset: {core_limit['reset']}")
                
            except Exception as e:
                print(f"❌ Rate limit check failed: {e}")
                return
        
        # Step 5: Analyze request metrics
        server_metrics = context.server.get_request_metrics()
        client_metrics = context.client.get_request_metrics()
        
        print(f"\n📊 Request Metrics:")
        print(f"   Server tracked: {server_metrics['total_requests']} requests")
        print(f"   Client tracked: {client_metrics['total_requests']} requests")
        print(f"   Average duration: {server_metrics['avg_duration_ms']:.2f}ms")
        print(f"   Status codes: {server_metrics['status_codes']}")
        print(f"   Error rate: {server_metrics['error_rate']:.2%}")
        
        # Step 6: Examine request log for debugging
        print(f"\n📋 Request Log (last 3 requests):")
        for log_entry in context.request_log[-3:]:
            print(f"   {log_entry['method']} {log_entry['endpoint']} -> {log_entry['status_code']} ({log_entry['duration_ms']:.1f}ms)")
    
    print("✅ Integration example completed successfully")


async def demonstrate_error_handling():
    """
    Demonstrate error handling with the mock server.
    
    This shows how to test error conditions and client resilience.
    """
    print("\n🚀 Starting Error Handling Example")
    
    mock_server = GitHubMockServer()
    mock_integration = GitHubMockIntegration(mock_server)
    
    async with mock_integration.create_github_context("basic_discovery") as context:
        # Configure error simulation
        context.server.simulate_api_errors(error_rate=0.3, error_codes=[500, 502, 503])
        print("⚠️  Configured 30% error rate with server errors")
        
        auth = MockTokenAuth()
        config = GitHubClientConfig(
            base_url=context.base_url,
            timeout=5,
            max_retries=3,  # Enable retries to test resilience
            retry_backoff_factor=1.5
        )
        
        async with GitHubClient(auth=auth, config=config) as github_client:
            successful_requests = 0
            failed_requests = 0
            
            # Make multiple requests to trigger errors
            print("🔄 Making 10 requests to test error handling...")
            for i in range(10):
                try:
                    repo = await github_client.get_repo("test", f"repo{i}")
                    successful_requests += 1
                    print(f"   ✅ Request {i+1}: {repo['name']}")
                    
                except Exception as e:
                    failed_requests += 1
                    print(f"   ❌ Request {i+1}: {type(e).__name__}")
            
            print(f"\n📈 Results:")
            print(f"   Successful: {successful_requests}")
            print(f"   Failed: {failed_requests}")
            print(f"   Success rate: {successful_requests/(successful_requests+failed_requests):.1%}")
        
        # Analyze what happened
        metrics = context.server.get_request_metrics()
        print(f"\n📊 Server Metrics:")
        print(f"   Total requests: {metrics['total_requests']}")
        print(f"   Status codes: {metrics['status_codes']}")
        print(f"   Actual error rate: {metrics['error_rate']:.1%}")


async def demonstrate_rate_limiting():
    """
    Demonstrate rate limiting simulation and client handling.
    
    This shows how to test rate limit scenarios and client backoff behavior.
    """
    print("\n🚀 Starting Rate Limiting Example")
    
    mock_server = GitHubMockServer()
    mock_integration = GitHubMockIntegration(mock_server)
    
    async with mock_integration.create_github_context("rate_limited") as context:
        # Configure aggressive rate limiting
        context.server.simulate_rate_limiting("core", limit=5, window_seconds=60)
        print("⚡ Configured rate limit: 5 requests per minute")
        
        auth = MockTokenAuth()
        config = GitHubClientConfig(
            base_url=context.base_url,
            timeout=10,
            max_retries=2,
            rate_limit_buffer=0  # Don't reserve buffer, hit limit exactly
        )
        
        async with GitHubClient(auth=auth, config=config) as github_client:
            print("🔄 Making requests until rate limited...")
            
            for i in range(8):  # Try more than the limit
                try:
                    repo = await github_client.get_repo("test", f"repo{i}")
                    print(f"   ✅ Request {i+1}: {repo['name']}")
                    
                    # Check rate limit status
                    if i % 2 == 0:  # Check every other request
                        rate_limit = await github_client.get_rate_limit()
                        remaining = rate_limit['resources']['core']['remaining']
                        print(f"      Rate limit remaining: {remaining}")
                        
                except Exception as e:
                    print(f"   ❌ Request {i+1}: {type(e).__name__} - {e}")
                    if "rate limit" in str(e).lower():
                        print("      🛑 Hit rate limit as expected!")
                        break
        
        # Show final rate limit status
        async with context.client as client:
            try:
                final_rate_limit = await client.get_rate_limit()
                core_status = final_rate_limit['resources']['core']
                print(f"\n⚡ Final Rate Limit Status:")
                print(f"   Limit: {core_status['limit']}")
                print(f"   Remaining: {core_status['remaining']}")
                print(f"   Reset time: {core_status['reset']}")
            except Exception as e:
                print(f"❌ Could not check final rate limit: {e}")


async def demonstrate_performance_testing():
    """
    Demonstrate performance testing capabilities.
    
    This shows how to use the mock server for load testing and performance validation.
    """
    print("\n🚀 Starting Performance Testing Example")
    
    mock_server = GitHubMockServer()
    mock_integration = GitHubMockIntegration(mock_server)
    
    async with mock_integration.create_github_context("large_repository") as context:
        # Configure for performance testing
        context.server.performance_simulator.configure_base_latency(5.0, 2.0)  # 5ms ± 2ms
        print("⚡ Configured realistic API latency simulation")
        
        auth = MockTokenAuth()
        config = GitHubClientConfig(
            base_url=context.base_url,
            timeout=30,
            max_concurrent_requests=20  # High concurrency
        )
        
        async with GitHubClient(auth=auth, config=config) as github_client:
            import time
            
            print("🏃 Running concurrent request performance test...")
            start_time = time.time()
            
            # Create many concurrent requests
            tasks = []
            for i in range(50):
                task = github_client.get_repo("test", f"perf-repo-{i % 10}")
                tasks.append(task)
            
            # Execute all concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # Analyze results
            successful = [r for r in results if not isinstance(r, Exception)]
            failed = [r for r in results if isinstance(r, Exception)]
            
            total_time = end_time - start_time
            requests_per_second = len(successful) / total_time
            
            print(f"\n📊 Performance Results:")
            print(f"   Total requests: {len(results)}")
            print(f"   Successful: {len(successful)}")
            print(f"   Failed: {len(failed)}")
            print(f"   Total time: {total_time:.2f} seconds")
            print(f"   Requests per second: {requests_per_second:.1f}")
        
        # Server-side metrics
        metrics = context.server.get_request_metrics()
        print(f"\n🖥️  Server Metrics:")
        print(f"   Average response time: {metrics['avg_duration_ms']:.2f}ms")
        print(f"   Total requests handled: {metrics['total_requests']}")


async def main():
    """Main entry point for integration examples."""
    print("GitHub Mock Server Integration Examples")
    print("=" * 50)
    
    try:
        await demonstrate_github_client_integration()
        await demonstrate_error_handling()
        await demonstrate_rate_limiting()
        await demonstrate_performance_testing()
        
        print("\n🎉 All integration examples completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())