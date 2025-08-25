# PR Monitoring Developer Guide

This guide provides comprehensive instructions for developers working with the PR monitoring system, including setup, configuration, usage patterns, and integration examples.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Development Setup](#development-setup)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Testing](#testing)
- [Performance Tuning](#performance-tuning)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL database (or SQLite for development)
- GitHub Personal Access Token
- Project dependencies installed (`pip install -r requirements.txt`)

### Basic Setup

```python
import asyncio
import uuid
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.synchronization import DatabaseSynchronizer
from src.github.client import GitHubClient
from src.repositories.pull_request import PullRequestRepository
from src.repositories.check_run import CheckRunRepository
from src.models.repository import Repository
from src.database.connection import get_async_session

async def basic_pr_monitoring():
    """Basic PR monitoring example."""
    
    # Setup database session
    async with get_async_session() as session:
        # Initialize GitHub client
        github_client = GitHubClient(token="your-github-token")
        
        # Create repository instances
        pr_repo = PullRequestRepository(session)
        check_repo = CheckRunRepository(session)
        
        # Initialize services
        discovery_service = GitHubPRDiscoveryService(github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(session)
        
        # Create processor
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Process a repository
        repository = Repository(
            id=uuid.uuid4(),
            url="https://github.com/owner/repo",
            name="repo",
            owner="owner",
            repo_name="repo"
        )
        
        result = await processor.process_repository(repository)
        
        print(f"Processing result:")
        print(f"  Success: {result.success}")
        print(f"  PRs discovered: {result.prs_discovered}")
        print(f"  Check runs discovered: {result.check_runs_discovered}")
        print(f"  Changes synchronized: {result.changes_synchronized}")
        print(f"  Processing time: {result.processing_time:.2f}s")

# Run the example
asyncio.run(basic_pr_monitoring())
```

## Architecture Overview

The PR monitoring system uses a three-phase processing pipeline:

### Phase 1: Discovery
- **GitHubPRDiscoveryService**: Fetches PR and check run data from GitHub API
- **Features**: ETag caching, rate limiting, concurrent processing, error isolation

### Phase 2: Change Detection  
- **DatabaseChangeDetector**: Compares GitHub data with database state
- **Features**: Granular change tracking, bulk queries, relationship mapping

### Phase 3: Synchronization
- **DatabaseSynchronizer**: Persists changes with transactional consistency
- **Features**: Bulk operations, state history, error recovery

### Orchestration
- **DefaultPRProcessor**: Coordinates all three phases
- **Features**: Error handling, metrics collection, concurrent repository processing

## Development Setup

### Environment Configuration

```bash
# 1. Clone and setup project
git clone <repository-url>
cd agentic-coding-workflow
pip install -r requirements.txt

# 2. Database setup
docker-compose up postgres  # Start PostgreSQL
alembic upgrade head        # Run migrations

# 3. Environment variables
export GITHUB_TOKEN="your-github-token"
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
```

### Development Configuration File

Create `config/development.yaml`:

```yaml
# Development configuration for PR monitoring
github:
  token: ${GITHUB_TOKEN}
  base_url: "https://api.github.com"
  timeout: 30
  max_retries: 3

database:
  url: ${DATABASE_URL}
  pool_size: 5
  max_overflow: 10

pr_monitoring:
  discovery:
    max_concurrent_requests: 5  # Lower for development
    cache_ttl_seconds: 300
    
  processing:
    max_concurrent_repos: 3     # Lower for development
    
  batch_size:
    pr_creation: 10
    pr_updates: 20
    check_creation: 50

logging:
  level: DEBUG
  structured: true
```

### Test Database Setup

```python
# conftest.py additions for PR monitoring tests
import pytest
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.synchronization import DatabaseSynchronizer

@pytest.fixture
async def pr_processor(database_session, mock_github_client):
    """Create PR processor for testing."""
    pr_repo = PullRequestRepository(database_session)
    check_repo = CheckRunRepository(database_session)
    
    discovery_service = GitHubPRDiscoveryService(mock_github_client)
    change_detector = DatabaseChangeDetector(pr_repo, check_repo)
    synchronizer = DatabaseSynchronizer(database_session)
    
    return DefaultPRProcessor(
        discovery_service=discovery_service,
        change_detection_service=change_detector,
        synchronization_service=synchronizer
    )

@pytest.fixture
def sample_pr_data():
    """Sample PR data for testing."""
    return [
        PRData(
            number=1,
            title="Test PR 1",
            author="testuser",
            state="open",
            draft=False,
            base_branch="main",
            head_branch="feature-1",
            base_sha="abc123",
            head_sha="def456",
            url="https://github.com/owner/repo/pull/1"
        ),
        # Add more test data as needed
    ]
```

## Usage Examples

### Single Repository Processing

```python
async def process_single_repository():
    """Process a single repository with detailed logging."""
    
    async with get_async_session() as session:
        # Setup processor
        processor = create_pr_processor(session)
        
        # Create repository
        repository = Repository(
            id=uuid.uuid4(),
            url="https://github.com/microsoft/vscode",
            name="vscode",
            owner="microsoft", 
            repo_name="vscode"
        )
        
        # Process with error handling
        try:
            result = await processor.process_repository(repository)
            
            if result.success:
                print(f"✅ Successfully processed {repository.name}")
                print(f"   📊 Metrics:")
                print(f"     - PRs discovered: {result.prs_discovered}")
                print(f"     - Check runs discovered: {result.check_runs_discovered}")
                print(f"     - New PRs: {result.new_prs}")
                print(f"     - Updated PRs: {result.updated_prs}")
                print(f"     - New check runs: {result.new_check_runs}")
                print(f"     - Updated check runs: {result.updated_check_runs}")
                print(f"     - Processing time: {result.processing_time:.2f}s")
            else:
                print(f"❌ Failed to process {repository.name}")
                for error in result.errors:
                    print(f"   Error: {error}")
                    
        except Exception as e:
            print(f"💥 Unexpected error processing {repository.name}: {e}")
```

### Batch Repository Processing

```python
async def process_multiple_repositories():
    """Process multiple repositories concurrently."""
    
    repositories = [
        Repository(
            id=uuid.uuid4(),
            url="https://github.com/microsoft/vscode",
            name="vscode",
            owner="microsoft",
            repo_name="vscode"
        ),
        Repository(
            id=uuid.uuid4(),
            url="https://github.com/facebook/react",
            name="react", 
            owner="facebook",
            repo_name="react"
        ),
        Repository(
            id=uuid.uuid4(),
            url="https://github.com/nodejs/node",
            name="node",
            owner="nodejs",
            repo_name="node"
        ),
    ]
    
    async with get_async_session() as session:
        processor = create_pr_processor(session, max_concurrent_repos=2)
        
        print(f"🚀 Starting batch processing of {len(repositories)} repositories...")
        start_time = time.time()
        
        batch_result = await processor.process_repositories(repositories)
        
        total_time = time.time() - start_time
        
        print(f"📊 Batch Processing Results:")
        print(f"   Repositories processed: {batch_result.repositories_processed}")
        print(f"   Success rate: {batch_result.success_rate:.1f}%")
        print(f"   Total PRs discovered: {batch_result.total_prs_discovered}")
        print(f"   Total check runs discovered: {batch_result.total_check_runs_discovered}")
        print(f"   Total changes synchronized: {batch_result.total_changes_synchronized}")
        print(f"   Total processing time: {total_time:.2f}s")
        print(f"   Average time per repo: {total_time / len(repositories):.2f}s")
        
        # Show individual results
        for i, result in enumerate(batch_result.results):
            repo = repositories[i]
            status = "✅" if result.success else "❌"
            print(f"   {status} {repo.name}: {result.changes_synchronized} changes "
                  f"({result.processing_time:.2f}s)")
```

### Custom Discovery Service

```python
class FilteredPRDiscoveryService(GitHubPRDiscoveryService):
    """Custom discovery service with filtering capabilities."""
    
    def __init__(
        self, 
        github_client: GitHubClient,
        exclude_drafts: bool = True,
        exclude_labels: list[str] = None,
        **kwargs
    ):
        super().__init__(github_client, **kwargs)
        self.exclude_drafts = exclude_drafts
        self.exclude_labels = exclude_labels or []
    
    async def discover_prs(
        self, 
        repository: Repository, 
        since: datetime | None = None
    ) -> list[PRData]:
        """Discover PRs with custom filtering."""
        
        # Get all PRs from parent class
        all_prs = await super().discover_prs(repository, since)
        
        # Apply custom filters
        filtered_prs = []
        for pr in all_prs:
            # Skip drafts if configured
            if self.exclude_drafts and pr.draft:
                continue
                
            # Skip PRs with excluded labels
            if any(label in self.exclude_labels for label in pr.labels):
                continue
                
            filtered_prs.append(pr)
        
        logger.info(f"Filtered {len(all_prs)} PRs down to {len(filtered_prs)} "
                   f"for {repository.name}")
        
        return filtered_prs

# Usage
async def use_custom_discovery():
    """Example using custom discovery service."""
    
    github_client = GitHubClient(token="your-token")
    
    # Create custom discovery service
    discovery_service = FilteredPRDiscoveryService(
        github_client=github_client,
        exclude_drafts=True,
        exclude_labels=["wip", "dependencies"],
        max_concurrent_requests=5
    )
    
    # Use in processor
    processor = DefaultPRProcessor(
        discovery_service=discovery_service,
        change_detection_service=change_detector,
        synchronization_service=synchronizer
    )
```

### Monitoring and Metrics

```python
class MetricsCollector:
    """Simple metrics collection for PR monitoring."""
    
    def __init__(self):
        self.repository_metrics = {}
    
    def record_processing_result(self, repository: Repository, result: ProcessingResult):
        """Record processing result for a repository."""
        repo_name = repository.name
        
        if repo_name not in self.repository_metrics:
            self.repository_metrics[repo_name] = {
                "total_runs": 0,
                "successful_runs": 0,
                "total_prs_discovered": 0,
                "total_changes_synchronized": 0,
                "total_processing_time": 0.0,
                "errors": []
            }
        
        metrics = self.repository_metrics[repo_name]
        metrics["total_runs"] += 1
        
        if result.success:
            metrics["successful_runs"] += 1
        
        metrics["total_prs_discovered"] += result.prs_discovered
        metrics["total_changes_synchronized"] += result.changes_synchronized
        metrics["total_processing_time"] += result.processing_time
        
        if result.errors:
            metrics["errors"].extend([str(e) for e in result.errors])
    
    def get_summary(self) -> dict:
        """Get summary of all metrics."""
        summary = {
            "repositories": len(self.repository_metrics),
            "total_runs": sum(m["total_runs"] for m in self.repository_metrics.values()),
            "overall_success_rate": 0.0,
            "total_changes_synchronized": sum(
                m["total_changes_synchronized"] for m in self.repository_metrics.values()
            ),
            "repository_details": {}
        }
        
        if summary["total_runs"] > 0:
            total_successful = sum(
                m["successful_runs"] for m in self.repository_metrics.values()
            )
            summary["overall_success_rate"] = (total_successful / summary["total_runs"]) * 100
        
        for repo_name, metrics in self.repository_metrics.items():
            success_rate = 0.0
            if metrics["total_runs"] > 0:
                success_rate = (metrics["successful_runs"] / metrics["total_runs"]) * 100
            
            summary["repository_details"][repo_name] = {
                "success_rate": success_rate,
                "avg_processing_time": (
                    metrics["total_processing_time"] / metrics["total_runs"]
                    if metrics["total_runs"] > 0 else 0
                ),
                "total_changes": metrics["total_changes_synchronized"],
                "error_count": len(metrics["errors"])
            }
        
        return summary

# Usage with metrics
async def monitored_processing():
    """Process repositories with metrics collection."""
    
    metrics = MetricsCollector()
    repositories = get_repositories_to_process()
    
    async with get_async_session() as session:
        processor = create_pr_processor(session)
        
        for repository in repositories:
            result = await processor.process_repository(repository)
            metrics.record_processing_result(repository, result)
        
        # Print summary
        summary = metrics.get_summary()
        print(f"📊 Processing Summary:")
        print(f"   Repositories: {summary['repositories']}")
        print(f"   Total runs: {summary['total_runs']}")
        print(f"   Success rate: {summary['overall_success_rate']:.1f}%")
        print(f"   Total changes: {summary['total_changes_synchronized']}")
        
        for repo_name, details in summary["repository_details"].items():
            print(f"   📁 {repo_name}:")
            print(f"     Success: {details['success_rate']:.1f}%")
            print(f"     Avg time: {details['avg_processing_time']:.2f}s")
            print(f"     Changes: {details['total_changes']}")
```

## Configuration

### Environment Variables

```bash
# Required
GITHUB_TOKEN="ghp_your_github_token"
DATABASE_URL="postgresql://user:pass@localhost/db"

# Optional - GitHub API
GITHUB_BASE_URL="https://api.github.com"  # For GitHub Enterprise
GITHUB_TIMEOUT=30
GITHUB_MAX_RETRIES=3

# Optional - PR Monitoring
PR_MONITOR_MAX_CONCURRENT_REPOS=10
PR_MONITOR_MAX_CONCURRENT_REQUESTS=15
PR_MONITOR_CACHE_TTL_SECONDS=300

# Optional - Database
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

### Configuration File Examples

**Production Configuration (`config/production.yaml`):**

```yaml
github:
  token: ${GITHUB_TOKEN}
  timeout: 30
  max_retries: 5
  rate_limit_buffer: 200  # Conservative buffer

database:
  url: ${DATABASE_URL}
  pool_size: 20
  max_overflow: 30
  pool_pre_ping: true
  
pr_monitoring:
  discovery:
    max_concurrent_requests: 15
    cache_ttl_seconds: 600  # 10 minutes
    
  processing:
    max_concurrent_repos: 10
    
  batch_size:
    pr_creation: 50
    pr_updates: 100
    check_creation: 200

logging:
  level: INFO
  structured: true
  correlation_ids: true

performance:
  enable_query_monitoring: true
  slow_query_threshold_ms: 1000
```

**Development Configuration (`config/development.yaml`):**

```yaml
github:
  token: ${GITHUB_TOKEN}
  timeout: 15
  max_retries: 2
  
database:
  url: "sqlite:///./dev.db"  # SQLite for development
  
pr_monitoring:
  discovery:
    max_concurrent_requests: 3
    cache_ttl_seconds: 60
    
  processing:
    max_concurrent_repos: 2
    
logging:
  level: DEBUG
  structured: false  # Plain text for development
```

### Configuration Loading

```python
from src.config.loader import load_config, ConfigurationError

def create_configured_processor(config_file: str = None):
    """Create PR processor from configuration file."""
    
    try:
        config = load_config(config_file)
        
        # GitHub client configuration
        github_client = GitHubClient(
            token=config.github.token,
            timeout=config.github.timeout,
            max_retries=config.github.max_retries
        )
        
        # Service configuration
        discovery_service = GitHubPRDiscoveryService(
            github_client=github_client,
            max_concurrent_requests=config.pr_monitoring.discovery.max_concurrent_requests,
            cache_ttl_seconds=config.pr_monitoring.discovery.cache_ttl_seconds
        )
        
        # Create processor
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer,
            max_concurrent_repos=config.pr_monitoring.processing.max_concurrent_repos
        )
        
        return processor
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise
```

## Testing

### Unit Testing

```python
# test_pr_monitoring.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.models import PRData, CheckRunData, ChangeSet

class TestPRProcessor:
    """Unit tests for PR processor."""
    
    @pytest.mark.asyncio
    async def test_single_repository_processing(self):
        """Test processing a single repository."""
        # Setup mocks
        discovery_service = AsyncMock()
        change_detector = AsyncMock()
        synchronizer = AsyncMock()
        
        discovery_service.discover_prs_and_checks.return_value = (5, 10)
        change_detector.detect_changes.return_value = ChangeSet(
            repository_id=uuid.uuid4()
        )
        synchronizer.synchronize_changes.return_value = 3
        
        # Create processor
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Test processing
        repository = Repository(id=uuid.uuid4(), url="https://github.com/test/repo")
        result = await processor.process_repository(repository)
        
        # Assertions
        assert result.success is True
        assert result.prs_discovered == 5
        assert result.check_runs_discovered == 10
        assert result.changes_synchronized == 3
        assert len(result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during processing."""
        # Setup mocks
        discovery_service = AsyncMock()
        change_detector = AsyncMock()
        synchronizer = AsyncMock()
        
        # Inject error in discovery phase
        discovery_service.discover_prs_and_checks.side_effect = Exception("GitHub API error")
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        repository = Repository(id=uuid.uuid4(), url="https://github.com/test/repo")
        result = await processor.process_repository(repository)
        
        # Assertions
        assert result.success is False
        assert len(result.errors) > 0
        assert "discovery_failure" in str(result.errors[0])
```

### Integration Testing

```python
@pytest.mark.integration
class TestPRMonitoringIntegration:
    """Integration tests with real database."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_processing(
        self,
        database_session,
        mock_github_client,
        sample_pr_data
    ):
        """Test complete workflow with database."""
        
        # Setup processor with real database session
        pr_repo = PullRequestRepository(database_session)
        check_repo = CheckRunRepository(database_session)
        
        discovery_service = GitHubPRDiscoveryService(mock_github_client)
        change_detector = DatabaseChangeDetector(pr_repo, check_repo)
        synchronizer = DatabaseSynchronizer(database_session)
        
        processor = DefaultPRProcessor(
            discovery_service=discovery_service,
            change_detection_service=change_detector,
            synchronization_service=synchronizer
        )
        
        # Mock GitHub API responses
        mock_github_client.get_pulls.return_value = sample_pr_data
        
        # Process repository
        repository = Repository(
            id=uuid.uuid4(),
            url="https://github.com/test/repo",
            name="repo"
        )
        
        result = await processor.process_repository(repository)
        
        # Verify processing
        assert result.success is True
        assert result.changes_synchronized > 0
        
        # Verify data persistence
        prs_in_db = await pr_repo.get_recent_prs(
            since=datetime.min, 
            repository_id=repository.id
        )
        assert len(prs_in_db) > 0
```

### Performance Testing

```python
@pytest.mark.performance
class TestPRMonitoringPerformance:
    """Performance tests for PR monitoring."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_volume_processing(self, database_session):
        """Test processing large volumes of data."""
        
        # Create large test dataset
        large_pr_data = generate_large_pr_dataset(100)  # 100 PRs
        large_check_data = generate_large_check_dataset(500)  # 500 check runs
        
        processor = create_test_processor(database_session)
        
        start_time = time.time()
        result = await processor.process_repository(test_repository)
        processing_time = time.time() - start_time
        
        # Performance assertions
        assert result.success is True
        assert processing_time < 30.0  # Should complete within 30 seconds
        assert result.changes_synchronized == 100
```

## Performance Tuning

### Database Optimization

```python
# Optimize database connections
database_config = {
    "pool_size": 20,          # Number of connections to maintain
    "max_overflow": 30,       # Additional connections allowed
    "pool_timeout": 30,       # Timeout for getting connection
    "pool_recycle": 3600,     # Recycle connections after 1 hour
    "pool_pre_ping": True,    # Verify connections before use
}

# Optimize batch sizes based on your data volume
synchronizer_config = {
    "pr_batch_size": 50,      # PRs to create in single batch
    "check_batch_size": 200,  # Check runs to create in single batch
    "update_batch_size": 100, # Updates to process in single batch
}
```

### GitHub API Optimization

```python
# Optimize GitHub API usage
discovery_config = {
    "max_concurrent_requests": 15,  # Balance between speed and rate limits
    "cache_ttl_seconds": 600,       # 10 minutes cache for ETag
    "request_timeout": 30,          # Timeout for individual requests
    "retry_attempts": 3,            # Retry failed requests
}

# Rate limiting strategy
rate_limit_config = {
    "buffer_requests": 200,         # Keep buffer for other operations
    "enable_circuit_breaker": True, # Stop on consecutive failures
    "backoff_factor": 2.0,          # Exponential backoff multiplier
}
```

### Concurrency Tuning

```python
# Balance concurrency based on resources
processor_config = {
    "max_concurrent_repos": 10,     # Repository-level concurrency
    "max_concurrent_prs": 50,       # PR-level concurrency within repo
    "semaphore_timeout": 300,       # Timeout for acquiring semaphore
}

# Memory management
memory_config = {
    "enable_result_streaming": True,  # Stream results instead of batching
    "max_changeset_size": 1000,      # Limit changeset size
    "garbage_collection_interval": 100, # Force GC every N repositories
}
```

## Troubleshooting

### Common Issues

**1. GitHub Rate Limiting**
```python
# Handle rate limit errors
try:
    result = await processor.process_repository(repository)
except GitHubRateLimitError as e:
    logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
    await asyncio.sleep(e.retry_after)
    # Retry processing
```

**2. Database Connection Issues**
```python
# Connection pool exhaustion
try:
    result = await processor.process_repository(repository)
except sqlalchemy.exc.TimeoutError:
    logger.error("Database connection pool exhausted")
    # Consider increasing pool size or reducing concurrency
```

**3. Memory Issues with Large Repositories**
```python
# Process in smaller batches
async def process_large_repository_safely(repository):
    # Get PR count first
    pr_count = await discovery_service.get_pr_count(repository)
    
    if pr_count > 1000:
        # Process in chunks
        logger.info(f"Large repository {repository.name} has {pr_count} PRs, "
                   f"processing in chunks")
        
        batch_size = 100
        for offset in range(0, pr_count, batch_size):
            chunk_result = await processor.process_repository_chunk(
                repository, offset, batch_size
            )
            logger.info(f"Processed chunk {offset}-{offset+batch_size}: "
                       f"{chunk_result.changes_synchronized} changes")
```

### Debugging

```python
# Enable debug logging
import logging
logging.getLogger("src.workers.monitor").setLevel(logging.DEBUG)

# Add correlation IDs for tracing
import uuid
correlation_id = str(uuid.uuid4())
logger = logging.getLogger(__name__).bind(correlation_id=correlation_id)

# Monitor performance
import time
start = time.time()
result = await processor.process_repository(repository)
duration = time.time() - start

if duration > 30:  # Slow processing
    logger.warning(f"Slow processing detected: {duration:.2f}s for {repository.name}")
```

### Health Checks

```python
async def health_check_pr_monitoring():
    """Health check for PR monitoring system."""
    
    health_status = {
        "github_api": False,
        "database": False,
        "processing_pipeline": False
    }
    
    try:
        # Test GitHub API
        github_client = GitHubClient(token="your-token")
        await github_client.get_user("octocat")
        health_status["github_api"] = True
        
        # Test database
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
        health_status["database"] = True
        
        # Test processing pipeline
        processor = create_pr_processor(session)
        test_repo = create_test_repository()
        result = await processor.process_repository(test_repo)
        health_status["processing_pipeline"] = result.success
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
    
    return health_status
```

## Contributing

### Code Style

Follow the project's coding standards:

```python
# Good: Clear naming and documentation
class GitHubPRDiscoveryService(PRDiscoveryService):
    """
    GitHub implementation of PR discovery service.
    
    Provides efficient PR and check run discovery with caching,
    rate limiting, and error handling.
    """
    
    async def discover_prs(
        self, 
        repository: Repository, 
        since: datetime | None = None
    ) -> list[PRData]:
        """
        Discover pull requests from a GitHub repository.
        
        Args:
            repository: Repository to discover PRs for
            since: Optional timestamp for incremental updates
            
        Returns:
            List of PR data objects
            
        Raises:
            GitHubError: If GitHub API request fails
        """

# Bad: Unclear naming and no documentation
class Service:
    async def get_stuff(self, repo, ts=None):
        # Get PRs or something
        pass
```

### Testing Requirements

All new features must include:

1. **Unit tests** with mocks for external dependencies
2. **Integration tests** with real database interactions
3. **Performance tests** for features handling large datasets
4. **Documentation** with examples and configuration details

### Contribution Workflow

1. **Fork** the repository and create a feature branch
2. **Implement** your changes following the coding standards
3. **Add tests** covering your changes
4. **Update documentation** as needed
5. **Run the test suite** and ensure all tests pass
6. **Submit a pull request** with clear description

---

**Need Help?**
- 📖 **API Documentation**: [PR Monitoring API](../api/pr-monitoring-api.md)
- 🧪 **Testing Guide**: [Testing Guidelines](../../TESTING_GUIDELINES.md)
- 🛠️ **Troubleshooting**: [Troubleshooting Hub](../troubleshooting-hub.md)
- 💬 **Community**: [GitHub Discussions](https://github.com/feddericovonwernich/agentic-coding-workflow/discussions)