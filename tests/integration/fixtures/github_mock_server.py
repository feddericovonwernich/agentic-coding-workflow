"""
GitHub API Mock Server for Integration Testing

This module provides a comprehensive GitHub API mock server that maintains realistic
API behavior while enabling controlled integration testing. The server uses FastAPI
to provide a real HTTP interface and supports all major GitHub API operations.
"""

import asyncio
import json
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Tracks request metrics for integration test analysis."""
    
    requests: List[Dict[str, Any]] = field(default_factory=list)
    total_requests: int = 0
    total_duration_ms: float = 0.0
    status_code_counts: Dict[int, int] = field(default_factory=dict)
    endpoint_counts: Dict[str, int] = field(default_factory=dict)
    
    def record_request(
        self, 
        endpoint: str, 
        method: str,
        duration_ms: float, 
        status_code: int
    ) -> None:
        """Record request metrics for analysis.
        
        Args:
            endpoint: API endpoint called
            method: HTTP method used
            duration_ms: Request duration in milliseconds
            status_code: HTTP response status code
        """
        self.requests.append({
            "endpoint": endpoint,
            "method": method,
            "duration_ms": duration_ms,
            "status_code": status_code,
            "timestamp": time.time()
        })
        
        self.total_requests += 1
        self.total_duration_ms += duration_ms
        self.status_code_counts[status_code] = (
            self.status_code_counts.get(status_code, 0) + 1
        )
        self.endpoint_counts[endpoint] = (
            self.endpoint_counts.get(endpoint, 0) + 1
        )
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary of request metrics.
        
        Returns:
            Dictionary containing detailed metrics analysis
        """
        if self.total_requests == 0:
            return {
                "total_requests": 0,
                "avg_duration_ms": 0,
                "requests_per_second": 0,
                "status_codes": {},
                "endpoints": {},
                "error_rate": 0.0
            }
        
        time_span = (
            self.requests[-1]["timestamp"] - self.requests[0]["timestamp"]
            if len(self.requests) > 1 else 1
        )
        
        error_requests = sum(
            count for status, count in self.status_code_counts.items()
            if status >= 400
        )
        
        return {
            "total_requests": self.total_requests,
            "avg_duration_ms": self.total_duration_ms / self.total_requests,
            "requests_per_second": self.total_requests / time_span,
            "status_codes": self.status_code_counts,
            "endpoints": self.endpoint_counts,
            "error_rate": error_requests / self.total_requests
        }
    
    def reset(self) -> None:
        """Reset all metrics for clean test isolation."""
        self.requests.clear()
        self.total_requests = 0
        self.total_duration_ms = 0.0
        self.status_code_counts.clear()
        self.endpoint_counts.clear()


@dataclass
class RateLimitState:
    """State tracking for rate limit simulation."""
    
    core_limit: int = 5000
    search_limit: int = 30
    core_remaining: int = 5000
    search_remaining: int = 30
    core_reset_time: int = int(time.time() + 3600)
    search_reset_time: int = int(time.time() + 3600)
    request_count: int = 0
    
    def consume_rate_limit(self, resource: str = "core") -> bool:
        """Consume a rate limit token and return if request should be allowed.
        
        Args:
            resource: Rate limit resource type ('core' or 'search')
            
        Returns:
            True if request should be allowed, False if rate limited
        """
        current_time = int(time.time())
        
        # Reset rate limits if time window expired
        if resource == "core":
            if current_time >= self.core_reset_time:
                self.core_remaining = self.core_limit
                self.core_reset_time = current_time + 3600
            
            if self.core_remaining <= 0:
                return False
                
            self.core_remaining -= 1
            
        elif resource == "search":
            if current_time >= self.search_reset_time:
                self.search_remaining = self.search_limit
                self.search_reset_time = current_time + 3600
            
            if self.search_remaining <= 0:
                return False
                
            self.search_remaining -= 1
        
        self.request_count += 1
        return True
    
    def get_rate_limit_headers(self, resource: str = "core") -> Dict[str, str]:
        """Get rate limit headers for response.
        
        Args:
            resource: Rate limit resource type
            
        Returns:
            Dictionary of rate limit headers
        """
        if resource == "core":
            return {
                "X-RateLimit-Limit": str(self.core_limit),
                "X-RateLimit-Remaining": str(max(0, self.core_remaining)),
                "X-RateLimit-Reset": str(self.core_reset_time),
                "X-RateLimit-Resource": "core"
            }
        else:
            return {
                "X-RateLimit-Limit": str(self.search_limit),
                "X-RateLimit-Remaining": str(max(0, self.search_remaining)),
                "X-RateLimit-Reset": str(self.search_reset_time),
                "X-RateLimit-Resource": "search"
            }


class ResponseScenarioManager:
    """Manages response scenarios for different test conditions."""
    
    def __init__(self):
        """Initialize with default GitHub API response templates."""
        self.scenarios: Dict[str, Dict[str, Any]] = {}
        self.default_responses = self._create_default_responses()
    
    def setup_repository_responses(self, scenarios: Dict[str, Any]) -> None:
        """Configure repository-level responses for test scenarios.
        
        Args:
            scenarios: Dictionary mapping scenario names to response configurations
        """
        for scenario_name, config in scenarios.items():
            self.scenarios[scenario_name] = {
                "repositories": config.get("repositories", {}),
                "pulls": config.get("pulls", []),
                "check_runs": config.get("check_runs", {}),
                "rate_limits": config.get("rate_limits", {"core": 5000, "search": 30}),
                "error_rate": config.get("error_rate", 0.0)
            }
    
    def get_repository_response(
        self, 
        owner: str, 
        repo: str, 
        scenario: str = "default"
    ) -> Dict[str, Any]:
        """Get repository response data for scenario.
        
        Args:
            owner: Repository owner
            repo: Repository name
            scenario: Test scenario name
            
        Returns:
            Repository response data
        """
        scenario_config = self.scenarios.get(scenario, {})
        repositories = scenario_config.get("repositories", {})
        repo_key = f"{owner}/{repo}"
        
        if repo_key in repositories:
            # Use scenario-specific repository data
            repo_data = repositories[repo_key].copy()
            repo_data.update(self._customize_repository_response(owner, repo))
            return repo_data
        else:
            # Generate default repository response
            return self._generate_default_repository(owner, repo)
    
    def get_pulls_response(
        self, 
        owner: str, 
        repo: str, 
        scenario: str = "default",
        **params
    ) -> List[Dict[str, Any]]:
        """Get pull requests response for repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            scenario: Test scenario name
            **params: Query parameters (state, page, per_page)
            
        Returns:
            List of pull request data
        """
        scenario_config = self.scenarios.get(scenario, {})
        repositories = scenario_config.get("repositories", {})
        repo_key = f"{owner}/{repo}"
        
        if repo_key in repositories and "pulls" in repositories[repo_key]:
            pulls = repositories[repo_key]["pulls"]
        else:
            pulls = []
        
        # Filter by state if provided
        state = params.get("state", "open")
        if state != "all":
            pulls = [pr for pr in pulls if pr.get("state", "open") == state]
        
        # Apply pagination
        page = int(params.get("page", 1))
        per_page = min(int(params.get("per_page", 30)), 100)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        return pulls[start_idx:end_idx]
    
    def get_check_runs_response(
        self, 
        owner: str, 
        repo: str, 
        ref: str,
        scenario: str = "default"
    ) -> Dict[str, Any]:
        """Get check runs response for commit reference.
        
        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git reference (commit SHA, branch, tag)
            scenario: Test scenario name
            
        Returns:
            Check runs response data
        """
        scenario_config = self.scenarios.get(scenario, {})
        check_runs_config = scenario_config.get("check_runs", {})
        repo_key = f"{owner}/{repo}"
        
        if repo_key in check_runs_config and ref in check_runs_config[repo_key]:
            check_runs = check_runs_config[repo_key][ref]
        else:
            check_runs = []
        
        return {
            "total_count": len(check_runs),
            "check_runs": check_runs
        }
    
    def _create_default_responses(self) -> Dict[str, Any]:
        """Create default GitHub API response templates.
        
        Returns:
            Dictionary of default response templates
        """
        return {
            "repository": {
                "id": 123456789,
                "name": "test-repo",
                "full_name": "test/test-repo",
                "private": False,
                "owner": {
                    "login": "test",
                    "id": 12345,
                    "type": "User",
                    "avatar_url": "https://avatars.githubusercontent.com/u/12345?v=4"
                },
                "html_url": "https://github.com/test/test-repo",
                "description": "Test repository for integration tests",
                "fork": False,
                "url": "https://api.github.com/repos/test/test-repo",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "pushed_at": "2024-01-01T00:00:00Z",
                "language": "Python",
                "default_branch": "main",
                "stargazers_count": 10,
                "watchers_count": 10,
                "forks_count": 2,
                "open_issues_count": 1
            },
            "pull_request": {
                "id": 987654321,
                "number": 1,
                "state": "open",
                "title": "Test Pull Request",
                "user": {
                    "login": "testuser",
                    "id": 54321,
                    "type": "User",
                    "avatar_url": "https://avatars.githubusercontent.com/u/54321?v=4"
                },
                "body": "Test PR description",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "merged_at": None,
                "merge_commit_sha": None,
                "head": {
                    "sha": "abc123def456",
                    "ref": "feature-branch",
                    "repo": {
                        "name": "test-repo",
                        "full_name": "test/test-repo"
                    }
                },
                "base": {
                    "sha": "def456abc123",
                    "ref": "main",
                    "repo": {
                        "name": "test-repo", 
                        "full_name": "test/test-repo"
                    }
                },
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean"
            },
            "check_run": {
                "id": 12345,
                "name": "test-check",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:01:00Z",
                "html_url": "https://github.com/test/test-repo/runs/12345",
                "check_suite": {
                    "id": 67890
                }
            }
        }
    
    def _customize_repository_response(self, owner: str, repo: str) -> Dict[str, Any]:
        """Customize repository response with owner/repo specific data.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Dictionary of customized repository fields
        """
        return {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "html_url": f"https://github.com/{owner}/{repo}",
            "url": f"https://api.github.com/repos/{owner}/{repo}",
            "owner": {
                "login": owner,
                "id": hash(owner) % 1000000,
                "type": "User",
                "avatar_url": f"https://avatars.githubusercontent.com/u/{hash(owner) % 1000000}?v=4"
            }
        }
    
    def _generate_default_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Generate default repository response for unknown repositories.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Generated repository response data
        """
        base_repo = self.default_responses["repository"].copy()
        base_repo.update(self._customize_repository_response(owner, repo))
        base_repo["id"] = hash(f"{owner}/{repo}") % 1000000
        return base_repo


class ErrorSimulator:
    """Simulates various API error conditions for testing error handling."""
    
    def __init__(self):
        """Initialize error simulation configuration."""
        self.error_rate: float = 0.0
        self.error_codes: List[int] = [500, 502, 503, 504]
        self.request_count: int = 0
        self.specific_errors: Dict[str, Dict[str, Any]] = {}
    
    def configure_error_simulation(
        self, 
        error_rate: float, 
        error_codes: List[int]
    ) -> None:
        """Configure general error simulation parameters.
        
        Args:
            error_rate: Probability of error response (0.0 to 1.0)
            error_codes: List of HTTP status codes to return as errors
        """
        self.error_rate = max(0.0, min(1.0, error_rate))
        self.error_codes = error_codes
    
    def configure_endpoint_errors(
        self, 
        endpoint_pattern: str, 
        error_code: int, 
        frequency: int = 10
    ) -> None:
        """Configure errors for specific endpoints.
        
        Args:
            endpoint_pattern: Endpoint pattern to match (e.g., "/repos/{owner}/{repo}")
            error_code: HTTP status code to return
            frequency: Error frequency (every Nth request)
        """
        self.specific_errors[endpoint_pattern] = {
            "code": error_code,
            "frequency": frequency
        }
    
    def should_simulate_error(self, request: Request) -> Optional[Dict[str, Any]]:
        """Determine if request should return an error response.
        
        Args:
            request: Incoming HTTP request
            
        Returns:
            Error response data if error should be simulated, None otherwise
        """
        self.request_count += 1
        path = str(request.url.path)
        
        # Check for specific endpoint errors first
        for pattern, config in self.specific_errors.items():
            if self._matches_pattern(path, pattern):
                if self.request_count % config["frequency"] == 0:
                    return self._create_error_response(config["code"])
        
        # Check for random error rate
        if random.random() < self.error_rate:
            error_code = random.choice(self.error_codes)
            return self._create_error_response(error_code)
        
        return None
    
    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches error pattern.
        
        Args:
            path: Request path
            pattern: Pattern to match against
            
        Returns:
            True if path matches pattern
        """
        # Simple pattern matching - replace {var} with regex
        import re
        regex_pattern = pattern.replace("{owner}", r"[^/]+").replace("{repo}", r"[^/]+")
        regex_pattern = regex_pattern.replace("{pr_number}", r"\d+").replace("{ref}", r"[^/]+")
        return bool(re.match(regex_pattern, path))
    
    def _create_error_response(self, status_code: int) -> Dict[str, Any]:
        """Create error response data.
        
        Args:
            status_code: HTTP status code
            
        Returns:
            Error response dictionary
        """
        error_messages = {
            429: {"message": "API rate limit exceeded", "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"},
            500: {"message": "Internal Server Error"},
            502: {"message": "Bad Gateway"},  
            503: {"message": "Service Unavailable"},
            504: {"message": "Gateway Timeout"}
        }
        
        return {
            "status_code": status_code,
            "response_data": error_messages.get(
                status_code, 
                {"message": f"HTTP {status_code}"}
            )
        }
    
    def reset(self) -> None:
        """Reset error simulation state."""
        self.request_count = 0


class PerformanceSimulator:
    """Simulates GitHub API performance characteristics for realistic testing."""
    
    def __init__(self):
        """Initialize performance simulation configuration."""
        self.base_latency_ms: float = 50.0
        self.latency_variance_ms: float = 25.0
        self.slow_endpoint_config: Dict[str, float] = {}
    
    def configure_base_latency(
        self, 
        base_ms: float, 
        variance_ms: float
    ) -> None:
        """Configure base latency parameters.
        
        Args:
            base_ms: Base latency in milliseconds
            variance_ms: Latency variance in milliseconds
        """
        self.base_latency_ms = max(0, base_ms)
        self.latency_variance_ms = max(0, variance_ms)
    
    def configure_endpoint_latency(
        self, 
        endpoint_pattern: str, 
        latency_ms: float
    ) -> None:
        """Configure latency for specific endpoints.
        
        Args:
            endpoint_pattern: Endpoint pattern to match
            latency_ms: Fixed latency for this endpoint
        """
        self.slow_endpoint_config[endpoint_pattern] = max(0, latency_ms)
    
    async def apply_performance_simulation(self, request: Request) -> None:
        """Apply simulated latency to request.
        
        Args:
            request: Incoming HTTP request
        """
        path = str(request.url.path)
        
        # Check for specific endpoint latency
        for pattern, latency in self.slow_endpoint_config.items():
            if self._matches_pattern(path, pattern):
                await asyncio.sleep(latency / 1000)
                return
        
        # Apply base latency with variance
        latency = self.base_latency_ms + random.uniform(
            -self.latency_variance_ms,
            self.latency_variance_ms
        )
        latency = max(0, latency)  # Ensure non-negative
        
        await asyncio.sleep(latency / 1000)
    
    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches latency pattern.
        
        Args:
            path: Request path
            pattern: Pattern to match against
            
        Returns:
            True if path matches pattern
        """
        # Simple pattern matching - replace {var} with regex
        import re
        regex_pattern = pattern.replace("{owner}", r"[^/]+").replace("{repo}", r"[^/]+")
        regex_pattern = regex_pattern.replace("{pr_number}", r"\d+").replace("{ref}", r"[^/]+")
        return bool(re.match(regex_pattern, path))


class GitHubMockServer:
    """HTTP mock server implementing realistic GitHub API contract.
    
    This server provides controlled, realistic GitHub API responses for integration
    testing while using real HTTP clients and maintaining API contract compliance.
    """
    
    def __init__(self):
        """Initialize GitHub mock server with all simulation components."""
        self.app = FastAPI(
            title="GitHub API Mock Server",
            description="Mock server for GitHub API integration testing",
            version="1.0.0"
        )
        self.server: Optional[uvicorn.Server] = None
        self.server_task: Optional[asyncio.Task] = None
        
        # Simulation components
        self.request_metrics = RequestMetrics()
        self.response_manager = ResponseScenarioManager()
        self.rate_limit_state = RateLimitState()
        self.error_simulator = ErrorSimulator()
        self.performance_simulator = PerformanceSimulator()
        
        # Request tracking
        self.request_log: List[Dict[str, Any]] = []
        self.current_scenario = "default"
        
        self._setup_middleware()
        self._setup_routes()
    
    def _setup_middleware(self) -> None:
        """Setup FastAPI middleware for request processing."""
        # CORS middleware for browser testing
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Request processing middleware
        @self.app.middleware("http")
        async def request_processing_middleware(request: Request, call_next):
            """Process all requests through simulation middleware."""
            start_time = time.time()
            
            # Apply performance simulation
            await self.performance_simulator.apply_performance_simulation(request)
            
            # Check for error simulation
            error_response = self.error_simulator.should_simulate_error(request)
            if error_response:
                response = Response(
                    content=json.dumps(error_response["response_data"]),
                    status_code=error_response["status_code"],
                    headers={"content-type": "application/json"}
                )
                self._add_github_headers(response, request)
                duration_ms = (time.time() - start_time) * 1000
                self._record_request(request, duration_ms, response.status_code)
                return response
            
            # Check rate limiting
            resource = "search" if "/search/" in str(request.url.path) else "core"
            if not self.rate_limit_state.consume_rate_limit(resource):
                rate_limit_response = {
                    "message": "API rate limit exceeded",
                    "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"
                }
                response = Response(
                    content=json.dumps(rate_limit_response),
                    status_code=429,
                    headers={"content-type": "application/json"}
                )
                self._add_github_headers(response, request, resource)
                duration_ms = (time.time() - start_time) * 1000
                self._record_request(request, duration_ms, 429)
                return response
            
            # Process request normally
            response = await call_next(request)
            
            # Add GitHub headers and record metrics
            self._add_github_headers(response, request, resource)
            duration_ms = (time.time() - start_time) * 1000
            self._record_request(request, duration_ms, response.status_code)
            
            return response
    
    def _setup_routes(self) -> None:
        """Setup GitHub API routes."""
        
        @self.app.get("/")
        async def root():
            """GitHub API root endpoint."""
            return {
                "message": "GitHub API Mock Server",
                "documentation_url": "https://docs.github.com/rest",
                "current_user_url": "https://api.github.com/user",
                "rate_limit_url": "https://api.github.com/rate_limit"
            }
        
        @self.app.get("/user")
        async def get_authenticated_user():
            """Get authenticated user information."""
            return {
                "login": "mock-user",
                "id": 12345,
                "type": "User",
                "name": "Mock User",
                "email": "mock-user@example.com",
                "avatar_url": "https://avatars.githubusercontent.com/u/12345?v=4",
                "html_url": "https://github.com/mock-user"
            }
        
        @self.app.get("/rate_limit")
        async def get_rate_limit():
            """Get rate limit status."""
            return {
                "resources": {
                    "core": {
                        "limit": self.rate_limit_state.core_limit,
                        "remaining": max(0, self.rate_limit_state.core_remaining),
                        "reset": self.rate_limit_state.core_reset_time
                    },
                    "search": {
                        "limit": self.rate_limit_state.search_limit,
                        "remaining": max(0, self.rate_limit_state.search_remaining),
                        "reset": self.rate_limit_state.search_reset_time
                    }
                },
                "rate": {
                    "limit": self.rate_limit_state.core_limit,
                    "remaining": max(0, self.rate_limit_state.core_remaining),
                    "reset": self.rate_limit_state.core_reset_time
                }
            }
        
        @self.app.get("/repos/{owner}/{repo}")
        async def get_repository(owner: str, repo: str):
            """Get repository information."""
            return self.response_manager.get_repository_response(
                owner, repo, self.current_scenario
            )
        
        @self.app.get("/repos/{owner}/{repo}/pulls")
        async def get_pulls(owner: str, repo: str, request: Request):
            """Get pull requests for repository."""
            params = dict(request.query_params)
            pulls = self.response_manager.get_pulls_response(
                owner, repo, self.current_scenario, **params
            )
            return pulls
        
        @self.app.get("/repos/{owner}/{repo}/pulls/{pr_number}")
        async def get_pull_request(owner: str, repo: str, pr_number: int):
            """Get specific pull request."""
            # Generate pull request response based on scenario
            pr_template = self.response_manager.default_responses["pull_request"].copy()
            pr_template.update({
                "number": pr_number,
                "title": f"Pull Request #{pr_number}",
                "head": {
                    **pr_template["head"],
                    "repo": {
                        "name": repo,
                        "full_name": f"{owner}/{repo}"
                    }
                },
                "base": {
                    **pr_template["base"],
                    "repo": {
                        "name": repo,
                        "full_name": f"{owner}/{repo}"
                    }
                }
            })
            return pr_template
        
        @self.app.get("/repos/{owner}/{repo}/commits/{ref}/check-runs")
        async def get_check_runs(owner: str, repo: str, ref: str):
            """Get check runs for commit reference."""
            return self.response_manager.get_check_runs_response(
                owner, repo, ref, self.current_scenario
            )
        
        @self.app.get("/repos/{owner}/{repo}/check-runs/{check_run_id}")
        async def get_check_run(owner: str, repo: str, check_run_id: int):
            """Get specific check run."""
            check_run_template = self.response_manager.default_responses["check_run"].copy()
            check_run_template["id"] = check_run_id
            return check_run_template
        
        # Health check endpoint for testing
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "server_time": time.time(),
                "total_requests": self.request_metrics.total_requests,
                "current_scenario": self.current_scenario
            }
    
    def _add_github_headers(
        self, 
        response: Response, 
        request: Request, 
        resource: str = "core"
    ) -> None:
        """Add realistic GitHub API headers to response.
        
        Args:
            response: FastAPI response object
            request: Original request
            resource: Rate limit resource type
        """
        # Rate limit headers
        rate_limit_headers = self.rate_limit_state.get_rate_limit_headers(resource)
        for key, value in rate_limit_headers.items():
            response.headers[key] = value
        
        # GitHub-specific headers
        response.headers["X-GitHub-Media-Type"] = "github.v3; format=json"
        response.headers["X-GitHub-Request-Id"] = str(uuid.uuid4())
        response.headers["Server"] = "GitHub.com"
        response.headers["Referrer-Policy"] = "origin-when-cross-origin, strict-origin-when-cross-origin"
        
        # CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset"
    
    def _record_request(
        self, 
        request: Request, 
        duration_ms: float, 
        status_code: int
    ) -> None:
        """Record request for metrics and logging.
        
        Args:
            request: HTTP request
            duration_ms: Request duration in milliseconds
            status_code: Response status code
        """
        endpoint = str(request.url.path)
        method = request.method
        
        # Record in metrics
        self.request_metrics.record_request(endpoint, method, duration_ms, status_code)
        
        # Add to request log
        self.request_log.append({
            "timestamp": time.time(),
            "method": method,
            "endpoint": endpoint,
            "query_params": dict(request.query_params),
            "duration_ms": duration_ms,
            "status_code": status_code,
            "user_agent": request.headers.get("User-Agent", ""),
            "authorization_present": "Authorization" in request.headers
        })
    
    async def start_server(self, port: int = 0) -> str:
        """Start mock GitHub API server.
        
        Args:
            port: Port to bind to (0 for automatic assignment)
            
        Returns:
            Base URL of started server
        """
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=port,
            log_level="warning",  # Reduce noise in tests
            access_log=False
        )
        
        self.server = uvicorn.Server(config)
        
        # Start server in background
        self.server_task = asyncio.create_task(self.server.serve())
        
        # Wait for server to start
        max_attempts = 50
        attempt = 0
        while not self.server.started and attempt < max_attempts:
            await asyncio.sleep(0.1)
            attempt += 1
        
        if not self.server.started:
            raise RuntimeError("Failed to start mock server within timeout")
        
        # Get actual port
        actual_port = None
        for server_socket in self.server.servers[0].sockets:
            actual_port = server_socket.getsockname()[1]
            break
        
        if actual_port is None:
            raise RuntimeError("Unable to determine server port")
        
        base_url = f"http://127.0.0.1:{actual_port}"
        logger.info(f"GitHub mock server started at {base_url}")
        
        return base_url
    
    async def stop_server(self) -> None:
        """Stop mock GitHub API server and cleanup resources."""
        if self.server:
            self.server.should_exit = True
            
        if self.server_task and not self.server_task.done():
            try:
                await asyncio.wait_for(self.server_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Server shutdown timed out, cancelling task")
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass
        
        self.server = None
        self.server_task = None
        logger.info("GitHub mock server stopped")
    
    def setup_repository_responses(self, scenarios: Dict[str, Any]) -> None:
        """Configure repository-level API responses for test scenarios.
        
        Args:
            scenarios: Dictionary mapping scenario names to response configurations
        """
        self.response_manager.setup_repository_responses(scenarios)
    
    def setup_pr_responses(self, repository_url: str, prs: List[Dict[str, Any]]) -> None:
        """Configure pull request API responses for repository.
        
        Args:
            repository_url: GitHub repository URL (e.g., "owner/repo")
            prs: List of PR response data dictionaries
        """
        # Add to current scenario
        if "default" not in self.response_manager.scenarios:
            self.response_manager.scenarios["default"] = {
                "repositories": {},
                "rate_limits": {"core": 5000, "search": 30},
                "error_rate": 0.0
            }
        
        if repository_url not in self.response_manager.scenarios["default"]["repositories"]:
            self.response_manager.scenarios["default"]["repositories"][repository_url] = {}
        
        self.response_manager.scenarios["default"]["repositories"][repository_url]["pulls"] = prs
    
    def setup_check_responses(
        self, 
        repository_url: str, 
        pr_number: int, 
        checks: List[Dict[str, Any]]
    ) -> None:
        """Configure check run API responses for specific PR.
        
        Args:
            repository_url: GitHub repository URL
            pr_number: Pull request number  
            checks: List of check run response data dictionaries
        """
        # Add to current scenario
        if "default" not in self.response_manager.scenarios:
            self.response_manager.scenarios["default"] = {
                "repositories": {},
                "rate_limits": {"core": 5000, "search": 30},
                "error_rate": 0.0
            }
        
        scenario = self.response_manager.scenarios["default"]
        if "check_runs" not in scenario:
            scenario["check_runs"] = {}
        
        if repository_url not in scenario["check_runs"]:
            scenario["check_runs"][repository_url] = {}
        
        # Use PR head SHA as reference
        ref = f"pr-{pr_number}-head"  # Mock reference
        scenario["check_runs"][repository_url][ref] = checks
    
    def simulate_rate_limiting(self, resource: str, limit: int, window_seconds: int) -> None:
        """Configure rate limiting simulation for GitHub API resource.
        
        Args:
            resource: API resource type ('core', 'search', etc.)
            limit: Request limit for the window
            window_seconds: Time window in seconds
        """
        current_time = int(time.time())
        
        if resource == "core":
            self.rate_limit_state.core_limit = limit
            self.rate_limit_state.core_remaining = limit
            self.rate_limit_state.core_reset_time = current_time + window_seconds
        elif resource == "search":
            self.rate_limit_state.search_limit = limit
            self.rate_limit_state.search_remaining = limit
            self.rate_limit_state.search_reset_time = current_time + window_seconds
    
    def simulate_api_errors(self, error_rate: float, error_codes: List[int]) -> None:
        """Configure API error simulation with specified rates and codes.
        
        Args:
            error_rate: Probability of error response (0.0 to 1.0)
            error_codes: List of HTTP status codes to return as errors
        """
        self.error_simulator.configure_error_simulation(error_rate, error_codes)
    
    def get_request_metrics(self) -> Dict[str, Any]:
        """Get metrics about requests made to mock server.
        
        Returns:
            Dictionary containing request counts, timing, and error statistics
        """
        return self.request_metrics.get_metrics_summary()
    
    def reset_mock_state(self) -> None:
        """Reset mock server state for test isolation."""
        self.request_metrics.reset()
        self.request_log.clear()
        self.rate_limit_state = RateLimitState()
        self.error_simulator.reset()
        self.current_scenario = "default"


class MockServerGitHubClient:
    """Real GitHub client configured to use mock server.
    
    This client maintains authentic request/response handling while pointing
    to the mock server instead of the real GitHub API.
    """
    
    def __init__(self, mock_server_base_url: str, auth_token: str = "mock_token"):
        """Initialize client with mock server configuration.
        
        Args:
            mock_server_base_url: Base URL of mock server
            auth_token: Mock authentication token
        """
        self.base_url = mock_server_base_url
        self.auth_token = auth_token
        self.request_metrics = RequestMetrics()
        
        # HTTP client with realistic configuration
        timeout = httpx.Timeout(30.0, connect=10.0)
        self.session = httpx.AsyncClient(
            base_url=mock_server_base_url,
            headers={
                "Authorization": f"token {auth_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Integration-Test-Client/1.0"
            },
            timeout=timeout,
            follow_redirects=True
        )
    
    async def __aenter__(self) -> "MockServerGitHubClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.session.aclose()
    
    async def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository using real HTTP request to mock server.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            Repository data from mock server
        """
        start_time = time.time()
        
        try:
            response = await self.session.get(f"/repos/{owner}/{repo}")
            response.raise_for_status()
            
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=f"/repos/{owner}/{repo}",
                method="GET",
                duration_ms=duration_ms,
                status_code=response.status_code
            )
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=f"/repos/{owner}/{repo}",
                method="GET", 
                duration_ms=duration_ms,
                status_code=e.response.status_code
            )
            raise
    
    async def get_pulls(
        self, 
        owner: str, 
        repo: str, 
        state: str = "open",
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """Get pull requests with pagination support.
        
        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state filter
            per_page: Items per page
            
        Returns:
            List of pull request data
        """
        all_pulls = []
        page = 1
        
        while True:
            start_time = time.time()
            params = {"state": state, "page": page, "per_page": per_page}
            
            try:
                response = await self.session.get(
                    f"/repos/{owner}/{repo}/pulls",
                    params=params
                )
                response.raise_for_status()
                
                duration_ms = (time.time() - start_time) * 1000
                self.request_metrics.record_request(
                    endpoint=f"/repos/{owner}/{repo}/pulls",
                    method="GET",
                    duration_ms=duration_ms,
                    status_code=response.status_code
                )
                
                pulls = response.json()
                if not pulls:  # No more pages
                    break
                
                all_pulls.extend(pulls)
                
                # Check for pagination (simplified)
                if len(pulls) < per_page:
                    break
                
                page += 1
                
                # Safety limit to prevent infinite loops
                if page > 100:
                    break
                
            except httpx.HTTPStatusError as e:
                duration_ms = (time.time() - start_time) * 1000
                self.request_metrics.record_request(
                    endpoint=f"/repos/{owner}/{repo}/pulls",
                    method="GET",
                    duration_ms=duration_ms,
                    status_code=e.response.status_code
                )
                raise
        
        return all_pulls
    
    async def get_pull_request(
        self, 
        owner: str, 
        repo: str, 
        pr_number: int
    ) -> Dict[str, Any]:
        """Get specific pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            
        Returns:
            Pull request data
        """
        start_time = time.time()
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        
        try:
            response = await self.session.get(endpoint)
            response.raise_for_status()
            
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=endpoint,
                method="GET",
                duration_ms=duration_ms,
                status_code=response.status_code
            )
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=endpoint,
                method="GET",
                duration_ms=duration_ms,
                status_code=e.response.status_code
            )
            raise
    
    async def get_check_runs(
        self, 
        owner: str, 
        repo: str, 
        ref: str
    ) -> Dict[str, Any]:
        """Get check runs for commit reference.
        
        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git reference
            
        Returns:
            Check runs response
        """
        start_time = time.time()
        endpoint = f"/repos/{owner}/{repo}/commits/{ref}/check-runs"
        
        try:
            response = await self.session.get(endpoint)
            response.raise_for_status()
            
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=endpoint,
                method="GET",
                duration_ms=duration_ms,
                status_code=response.status_code
            )
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint=endpoint,
                method="GET",
                duration_ms=duration_ms,
                status_code=e.response.status_code
            )
            raise
    
    async def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status.
        
        Returns:
            Rate limit information
        """
        start_time = time.time()
        
        try:
            response = await self.session.get("/rate_limit")
            response.raise_for_status()
            
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint="/rate_limit",
                method="GET",
                duration_ms=duration_ms,
                status_code=response.status_code
            )
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.request_metrics.record_request(
                endpoint="/rate_limit",
                method="GET",
                duration_ms=duration_ms,
                status_code=e.response.status_code
            )
            raise
    
    def get_request_metrics(self) -> Dict[str, Any]:
        """Get client-side request metrics.
        
        Returns:
            Dictionary of request metrics from client perspective
        """
        return self.request_metrics.get_metrics_summary()


# Test Scenarios and Integration Support

GITHUB_MOCK_SCENARIOS = {
    "basic_discovery": {
        "repositories": {
            "test/repo1": {
                "pulls": [
                    {
                        "number": 1,
                        "state": "open", 
                        "title": "Feature implementation",
                        "head": {"sha": "abc123def456"},
                        "base": {"sha": "def456abc123"}
                    },
                    {
                        "number": 2,
                        "state": "closed",
                        "title": "Bug fix",
                        "head": {"sha": "fed987cba321"},
                        "base": {"sha": "def456abc123"}
                    }
                ],
                "check_runs": {
                    "abc123def456": [
                        {
                            "id": 12345,
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "success"
                        }
                    ]
                }
            }
        },
        "rate_limits": {"core": 5000, "search": 30},
        "error_rate": 0.0
    },
    
    "rate_limited": {
        "repositories": {
            "test/repo1": {"pulls": []}
        },
        "rate_limits": {"core": 5, "search": 2},
        "error_rate": 0.0
    },
    
    "high_error_rate": {
        "repositories": {
            "test/repo1": {"pulls": []}
        },
        "rate_limits": {"core": 5000, "search": 30},
        "error_rate": 0.3
    },
    
    "large_repository": {
        "repositories": {
            "test/large-repo": {
                "pulls": [
                    {
                        "number": i,
                        "state": "open",
                        "title": f"PR #{i}",
                        "head": {"sha": f"sha{i:06d}"},
                        "base": {"sha": "main123"}
                    }
                    for i in range(1, 101)  # 100 PRs
                ]
            }
        },
        "rate_limits": {"core": 5000, "search": 30},
        "error_rate": 0.0
    }
}


@dataclass
class GitHubMockContext:
    """Context for GitHub API mock server with real HTTP client integration."""
    
    server: GitHubMockServer
    client: MockServerGitHubClient
    base_url: str
    request_log: List[Dict[str, Any]]
    scenario_configs: Dict[str, Any]
    rate_limit_config: Dict[str, int]


class GitHubMockIntegration:
    """Integrates GitHub mock server with real components for testing."""
    
    def __init__(self, mock_server: GitHubMockServer):
        """Initialize integration with mock server instance.
        
        Args:
            mock_server: GitHub mock server instance
        """
        self.mock_server = mock_server
        self.github_client: Optional[MockServerGitHubClient] = None
    
    @asynccontextmanager
    async def create_github_context(
        self, 
        scenario: str = "basic_discovery"
    ) -> GitHubMockContext:
        """Create GitHub context for integration testing.
        
        Args:
            scenario: Test scenario name
            
        Returns:
            Async context manager providing complete GitHub testing context
        """
        # Start mock server
        server_url = await self.mock_server.start_server()
        
        try:
            # Configure scenario
            scenario_config = GITHUB_MOCK_SCENARIOS.get(
                scenario, 
                GITHUB_MOCK_SCENARIOS["basic_discovery"]
            )
            self.mock_server.setup_repository_responses({"default": scenario_config})
            self.mock_server.current_scenario = "default"
            
            # Create real GitHub client pointing to mock server
            self.github_client = MockServerGitHubClient(server_url)
            
            context = GitHubMockContext(
                server=self.mock_server,
                client=self.github_client,
                base_url=server_url,
                request_log=self.mock_server.request_log,
                scenario_configs={scenario: scenario_config},
                rate_limit_config=scenario_config.get("rate_limits", {"core": 5000, "search": 30})
            )
            
            yield context
            
        finally:
            # Cleanup
            if self.github_client:
                await self.github_client.close()
                self.github_client = None
            
            await self.mock_server.stop_server()