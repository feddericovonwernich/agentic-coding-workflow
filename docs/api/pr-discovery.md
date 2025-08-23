# PR Discovery API

> **📚 Navigation**: This is the **PR Discovery API reference**. For high-level architecture, see [System Architecture](../developer/architecture.md). For performance optimization, see [Developer Best Practices](../developer/best-practices.md). For integration troubleshooting, see [Configuration Troubleshooting](../config/troubleshooting.md).

The PR Discovery API provides high-performance, scalable pull request and check run discovery capabilities for monitoring large numbers of GitHub repositories. This system handles 100+ repositories with 1000+ PRs each within 5-minute processing windows.

## Table of Contents

- [Core Interfaces](#core-interfaces)
- [Data Models](#data-models)
- [Discovery Engine](#discovery-engine)
- [Component APIs](#component-apis)
- [Configuration](#configuration)
- [Performance Characteristics](#performance-characteristics)
- [Error Handling](#error-handling)
- [Usage Examples](#usage-examples)

## Core Interfaces

### DiscoveryOrchestrator

The main interface for orchestrating PR discovery operations.

```python
from abc import ABC, abstractmethod
from typing import List
import uuid

class DiscoveryOrchestrator(ABC):
    """Abstract base class for orchestrating the discovery process."""
    
    @abstractmethod
    async def run_discovery_cycle(
        self, repository_ids: List[uuid.UUID]
    ) -> List[PRDiscoveryResult]:
        """Run a complete discovery cycle for repositories.
        
        Args:
            repository_ids: List of repository IDs to process
            
        Returns:
            List of discovery results with PRs, metrics, and errors
            
        Performance:
            - Handles 100+ repositories concurrently
            - Processes 1000+ PRs within 5-minute windows
            - Achieves >60% cache hit rates
            - Maintains >95% uptime with error recovery
        """
        pass
```

### PRDiscoveryStrategy

Strategy interface for repository-specific PR discovery.

```python
class PRDiscoveryStrategy(ABC):
    """Abstract base class for PR discovery strategies."""
    
    @abstractmethod
    async def discover_prs(
        self,
        repository_id: uuid.UUID,
        repository_url: str,
        since: Optional[datetime] = None,
        max_prs: Optional[int] = None,
    ) -> PRDiscoveryResult:
        """Discover PRs for a repository.
        
        Args:
            repository_id: Database ID of the repository
            repository_url: GitHub URL of the repository
            since: Only discover PRs updated after this time
            max_prs: Maximum number of PRs to discover (default: 1000)
            
        Returns:
            Discovery result with PRs and performance metadata
        """
        pass
    
    @abstractmethod
    async def get_priority(self, repository_id: uuid.UUID) -> DiscoveryPriority:
        """Get discovery priority for a repository.
        
        Args:
            repository_id: Database ID of the repository
            
        Returns:
            Priority level for discovery scheduling:
            - CRITICAL (1): Recently active repositories
            - HIGH (2): Repositories with recent failures  
            - NORMAL (3): Regular monitoring
            - LOW (4): Inactive repositories
        """
        pass
```

## Data Models

### DiscoveredPR

Complete pull request data with metadata and check runs.

```python
@dataclass
class DiscoveredPR:
    """Discovered pull request with complete metadata."""
    
    pr_number: int
    title: str
    author: str
    state: str  # 'open', 'closed', 'merged'
    draft: bool
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    url: str
    body: Optional[str]
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime]
    metadata: dict[str, Any]  # Additional GitHub metadata
    check_runs: list[DiscoveredCheckRun]
    
    @property
    def is_active(self) -> bool:
        """Check if PR is in an active state."""
        return self.state == "open" and not self.draft
```

### DiscoveredCheckRun

Check run information with status and output details.

```python
@dataclass
class DiscoveredCheckRun:
    """Discovered check run with status and output."""
    
    external_id: str  # GitHub check run ID
    name: str
    status: str  # 'queued', 'in_progress', 'completed'
    conclusion: Optional[str]  # 'success', 'failure', 'cancelled', etc.
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    details_url: Optional[str]
    output: Optional[dict[str, Any]]  # Check output including title, summary, text
    
    @property
    def is_failed(self) -> bool:
        """Check if the check run failed."""
        return self.status == "completed" and self.conclusion == "failure"
```

### PRDiscoveryResult

Complete discovery results with performance metrics.

```python
@dataclass
class PRDiscoveryResult:
    """Result of PR discovery for a single repository."""
    
    repository_id: uuid.UUID
    repository_url: str
    discovered_prs: list[DiscoveredPR]
    discovery_timestamp: datetime
    api_calls_used: int
    cache_hits: int
    cache_misses: int
    processing_time_ms: float
    errors: list[DiscoveryError]
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate of discovery."""
        total = len(self.discovered_prs) + len(self.errors)
        return len(self.discovered_prs) / total if total > 0 else 1.0
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate for this discovery."""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
```

## Discovery Engine

### PRDiscoveryEngine

The main orchestrator implementation providing high-performance discovery.

```python
class PRDiscoveryEngine(DiscoveryOrchestrator):
    """Main discovery engine orchestrating the entire discovery process.
    
    Coordinates parallel repository processing, state change detection,
    data synchronization, and event publishing with comprehensive
    error handling and performance monitoring.
    """
    
    def __init__(
        self,
        config: DiscoveryConfig,
        pr_discovery: PRDiscoveryStrategy,
        check_discovery: CheckDiscoveryStrategy,
        state_detector: StateChangeDetector,
        data_sync: DataSynchronizationStrategy,
        rate_limiter: RateLimitStrategy,
        cache: CacheStrategy,
        event_publisher: EventPublisher,
        repository_repo: RepositoryRepository,
        state_manager: Optional[RepositoryStateManager] = None,
    ):
        """Initialize discovery engine with all dependencies."""
        pass
    
    async def run_discovery_cycle(
        self, repository_ids: List[uuid.UUID]
    ) -> List[PRDiscoveryResult]:
        """Run a complete discovery cycle for repositories.
        
        Processing Steps:
        1. Sort repositories by priority (critical → low)
        2. Process repositories in configurable batches
        3. Detect state changes across all results
        4. Synchronize data with database in transactions
        5. Publish events for downstream processing
        6. Update performance metrics
        
        Performance Characteristics:
        - Processes 100+ repositories with configurable concurrency
        - Completes 1000+ PRs within 5-minute windows
        - Maintains >60% cache hit rates through ETag caching
        - Supports graceful error handling with partial success
        """
        pass
    
    async def get_discovery_status(self) -> dict[str, Any]:
        """Get current discovery status and performance metrics.
        
        Returns:
            Status information including:
            - Current cycle progress and statistics
            - Overall performance metrics
            - Rate limit status for GitHub API
            - Cache performance statistics
            - Concurrency and resource utilization
            - Recent errors and batch statistics
        """
        pass
```

### Configuration

Discovery system configuration with performance tuning options.

```python
@dataclass
class DiscoveryConfig:
    """Configuration for discovery operations."""
    
    max_concurrent_repositories: int = 10  # Concurrent repository processing
    max_prs_per_repository: int = 1000     # Limit PRs per repository
    cache_ttl_seconds: int = 300           # Cache TTL (5 minutes)
    use_etag_caching: bool = True          # Enable ETag-based caching
    batch_size: int = 100                  # Batch size for processing
    discovery_timeout_seconds: int = 300   # Discovery timeout (5 minutes)
    priority_scheduling: bool = True       # Enable priority-based scheduling
```

## Component APIs

### Cache Strategy

Multi-tier caching with Redis and memory backends.

```python
class CacheStrategy(ABC):
    """Abstract base class for caching strategies."""
    
    @abstractmethod
    async def get_with_etag(self, key: str) -> tuple[Optional[Any], Optional[str]]:
        """Get cached value with ETag for conditional requests.
        
        Args:
            key: Cache key
            
        Returns:
            Tuple of (cached value, etag) for GitHub conditional requests
        """
        pass
    
    @abstractmethod
    async def set_with_etag(
        self, key: str, value: Any, etag: str, ttl: Optional[int] = None
    ) -> None:
        """Set cached value with ETag.
        
        Args:
            key: Cache key
            value: Value to cache
            etag: ETag for conditional requests
            ttl: Time-to-live in seconds
        """
        pass
```

### Rate Limiting

Token bucket algorithm for GitHub API rate limiting.

```python
class RateLimitStrategy(ABC):
    """Abstract base class for rate limit management."""
    
    @abstractmethod
    async def acquire_tokens(self, resource: str, count: int = 1) -> bool:
        """Acquire rate limit tokens.
        
        Args:
            resource: Resource identifier ('core', 'search', etc.)
            count: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False if not available
            
        Note:
            Implements token bucket algorithm with priority scheduling
        """
        pass
    
    @abstractmethod
    async def wait_for_tokens(
        self, resource: str, count: int = 1, timeout: Optional[float] = None
    ) -> bool:
        """Wait until tokens are available.
        
        Args:
            resource: Resource identifier
            count: Number of tokens needed
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if tokens acquired, False if timeout
        """
        pass
```

### State Change Detection

Real-time detection of significant state changes.

```python
class StateChangeDetector(ABC):
    """Abstract base class for state change detection."""
    
    @abstractmethod
    async def detect_changes(
        self, discovered_data: PRDiscoveryResult, current_state: RepositoryState
    ) -> list[StateChange]:
        """Detect state changes between discovered and current data.
        
        Args:
            discovered_data: Newly discovered PR data
            current_state: Current stored state
            
        Returns:
            List of significant state changes requiring action
            
        Change Types:
        - CREATED: New PR or check run
        - UPDATED: Modified PR or check run
        - STATE_CHANGED: Status or conclusion changed
        - DELETED: Removed PR or check run
        """
        pass
```

## Performance Characteristics

### Throughput Metrics

The PR Discovery system is designed for high-performance operation:

- **Repository Processing**: 100+ repositories concurrently
- **PR Processing**: 1000+ PRs within 5-minute windows
- **API Efficiency**: 60% reduction in GitHub API calls through caching
- **Cache Performance**: >60% cache hit rates with ETag support
- **Uptime**: >95% availability with graceful error handling
- **Concurrency**: Configurable limits (10-50 repositories, 100-1000 PRs)

### Scaling Characteristics

```python
# Example performance configuration for different scales
SMALL_SCALE_CONFIG = DiscoveryConfig(
    max_concurrent_repositories=5,
    max_prs_per_repository=100,
    batch_size=10
)

MEDIUM_SCALE_CONFIG = DiscoveryConfig(
    max_concurrent_repositories=20,
    max_prs_per_repository=500,
    batch_size=50
)

LARGE_SCALE_CONFIG = DiscoveryConfig(
    max_concurrent_repositories=50,
    max_prs_per_repository=1000,
    batch_size=100
)
```

### Memory Usage

- **Base Memory**: ~50MB for core engine
- **Per Repository**: ~1-5MB depending on PR count
- **Cache Memory**: Configurable (Redis: unlimited, Memory: 100MB default)
- **Peak Usage**: Linear with concurrent repository processing

## Error Handling

### Exception Hierarchy

```python
from src.workers.discovery.exceptions import (
    DiscoveryError,              # Base discovery error
    RepositoryAccessError,       # GitHub repository access issues
    RateLimitExceededError,     # API rate limit exceeded
    CacheError,                 # Cache operation failures
    StateDetectionError,        # State change detection issues
    SynchronizationError        # Database synchronization failures
)

# Error handling example
try:
    results = await discovery_engine.run_discovery_cycle(repository_ids)
except RateLimitExceededError as e:
    # Handle rate limiting with backoff
    await asyncio.sleep(e.retry_after)
except RepositoryAccessError as e:
    # Handle repository access issues
    logger.error(f"Cannot access repository {e.repository_id}: {e.message}")
except DiscoveryError as e:
    # Handle general discovery errors
    logger.error(f"Discovery failed: {e.message}")
```

### Error Recovery

The system implements comprehensive error recovery:

- **Partial Success**: Continue processing other repositories when some fail
- **Retry Logic**: Exponential backoff for transient failures
- **Circuit Breaker**: Prevent cascade failures during API outages
- **Graceful Degradation**: Reduce processing load when errors occur
- **Error Reporting**: Detailed error context in discovery results

## Usage Examples

### Basic Discovery Setup

```python
import asyncio
from src.workers.discovery.pr_discovery_engine import PRDiscoveryEngine
from src.workers.discovery.interfaces import DiscoveryConfig

async def setup_discovery_engine():
    """Setup PR discovery engine with all components."""
    config = DiscoveryConfig(
        max_concurrent_repositories=20,
        max_prs_per_repository=500,
        cache_ttl_seconds=300,
        use_etag_caching=True
    )
    
    # Setup all dependencies (simplified)
    engine = PRDiscoveryEngine(
        config=config,
        pr_discovery=pr_discovery_strategy,
        check_discovery=check_discovery_strategy,
        state_detector=state_detector,
        data_sync=data_synchronizer,
        rate_limiter=rate_limiter,
        cache=cache_strategy,
        event_publisher=event_publisher,
        repository_repo=repository_repository
    )
    
    return engine

async def run_discovery():
    """Run discovery cycle for multiple repositories."""
    engine = await setup_discovery_engine()
    
    # Get repository IDs to process
    repository_ids = await get_active_repository_ids()
    
    # Run discovery cycle
    results = await engine.run_discovery_cycle(repository_ids)
    
    # Process results
    total_prs = sum(len(result.discovered_prs) for result in results)
    total_errors = sum(len(result.errors) for result in results)
    
    print(f"Discovery completed: {total_prs} PRs discovered, {total_errors} errors")
    
    # Get performance metrics
    status = await engine.get_discovery_status()
    print(f"Cache hit rate: {status['cache_stats']['hit_rate']:.1f}%")
    print(f"Processing time: {status['current_cycle']['processing_time_seconds']:.2f}s")

if __name__ == "__main__":
    asyncio.run(run_discovery())
```

### Repository Processing with Priority

```python
async def prioritized_discovery():
    """Example of priority-based repository discovery."""
    engine = await setup_discovery_engine()
    
    # Repositories will be automatically sorted by priority
    repository_ids = [
        uuid.uuid4(),  # Critical repository
        uuid.uuid4(),  # High priority repository
        uuid.uuid4(),  # Normal priority repository
        uuid.uuid4(),  # Low priority repository
    ]
    
    # Discovery engine will process critical repositories first
    results = await engine.run_discovery_cycle(repository_ids)
    
    # Analyze priority processing
    for result in results:
        priority = await engine.pr_discovery.get_priority(result.repository_id)
        print(f"Repository {result.repository_id}: "
              f"Priority {priority.name}, "
              f"{len(result.discovered_prs)} PRs, "
              f"{result.processing_time_ms:.0f}ms")
```

### Performance Monitoring

```python
async def monitor_discovery_performance():
    """Monitor discovery performance and health."""
    engine = await setup_discovery_engine()
    
    while True:
        status = await engine.get_discovery_status()
        
        print(f"Discovery Status: {status['status']}")
        print(f"Repositories processed: {status['current_cycle']['repositories_processed']}")
        print(f"Progress: {status['current_cycle']['progress_percentage']:.1f}%")
        print(f"PRs discovered: {status['current_cycle']['prs_discovered']}")
        print(f"Cache hit rate: {status['cache_stats'].get('hit_rate', 0):.1f}%")
        print(f"Rate limit remaining: {status['rate_limits'].get('core_remaining', 'unknown')}")
        print(f"Active tasks: {status['concurrency']['active_tasks']}")
        
        # Check for degraded status
        if status['status'] == 'degraded':
            print("WARNING: Discovery system is in degraded state")
            print("Recent errors:", status['recent_errors'][-3:])
        
        await asyncio.sleep(30)  # Monitor every 30 seconds
```

### Custom Discovery Strategy

```python
class CustomPRDiscoveryStrategy(PRDiscoveryStrategy):
    """Custom PR discovery strategy with specific business logic."""
    
    async def discover_prs(
        self,
        repository_id: uuid.UUID,
        repository_url: str,
        since: Optional[datetime] = None,
        max_prs: Optional[int] = None,
    ) -> PRDiscoveryResult:
        """Custom PR discovery with organization-specific logic."""
        start_time = time.time()
        
        try:
            # Custom GitHub API interaction
            prs = await self.github_client.get_pull_requests(
                repository_url,
                state="all",
                since=since,
                limit=max_prs or 1000
            )
            
            # Apply custom filtering
            filtered_prs = []
            for pr in prs:
                if self._should_include_pr(pr):
                    discovered_pr = self._convert_pr(pr)
                    filtered_prs.append(discovered_pr)
            
            # Return results with metrics
            return PRDiscoveryResult(
                repository_id=repository_id,
                repository_url=repository_url,
                discovered_prs=filtered_prs,
                discovery_timestamp=datetime.now(timezone.utc),
                api_calls_used=1,
                cache_hits=0,
                cache_misses=1,
                processing_time_ms=(time.time() - start_time) * 1000,
                errors=[]
            )
            
        except Exception as e:
            return PRDiscoveryResult(
                repository_id=repository_id,
                repository_url=repository_url,
                discovered_prs=[],
                discovery_timestamp=datetime.now(timezone.utc),
                api_calls_used=0,
                cache_hits=0,
                cache_misses=0,
                processing_time_ms=(time.time() - start_time) * 1000,
                errors=[DiscoveryError(
                    error_type="custom_discovery_error",
                    message=str(e),
                    context={"repository_id": str(repository_id)},
                    timestamp=datetime.now(timezone.utc),
                    recoverable=True
                )]
            )
    
    def _should_include_pr(self, pr: dict) -> bool:
        """Custom logic for PR inclusion."""
        # Example: Only include PRs from certain authors
        return pr["user"]["login"] not in ["dependabot[bot]", "renovate[bot]"]
    
    async def get_priority(self, repository_id: uuid.UUID) -> DiscoveryPriority:
        """Custom priority logic."""
        # Example: Check repository metadata for priority
        repo = await self.repository_repo.get_by_id(repository_id)
        if repo and repo.metadata.get("critical", False):
            return DiscoveryPriority.CRITICAL
        return DiscoveryPriority.NORMAL
```

---

## Performance Optimization

### Cache Configuration

```python
# Optimize cache settings for your workload
CACHE_CONFIG = {
    "ttl_seconds": 300,        # 5 minutes for active repositories
    "etag_enabled": True,      # Enable ETag caching for GitHub API
    "memory_limit_mb": 500,    # Memory cache limit
    "redis_url": "redis://localhost:6379/0"
}
```

### Concurrency Tuning

```python
# Tune concurrency based on your infrastructure
PERFORMANCE_CONFIG = DiscoveryConfig(
    max_concurrent_repositories=min(50, cpu_count() * 2),
    batch_size=100,
    discovery_timeout_seconds=300
)
```

For more performance optimization guidance, see [Developer Best Practices](../developer/best-practices.md).

---

**Ready to integrate PR Discovery?**
- 🚀 **Getting Started**: Use the [basic discovery setup example](#basic-discovery-setup)
- ⚡ **Performance**: Review [performance characteristics](#performance-characteristics)
- 🛠️ **Troubleshooting**: Visit the [🛠️ Troubleshooting Hub](../troubleshooting-hub.md)
- 📖 **Architecture**: See [System Architecture](../developer/architecture.md)