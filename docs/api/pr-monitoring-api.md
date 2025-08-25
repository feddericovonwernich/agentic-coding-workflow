# PR Monitoring API Documentation

The PR Monitoring API provides comprehensive interfaces for discovering, tracking, and synchronizing pull request data from GitHub repositories. This system uses a three-phase processing pipeline with sophisticated change detection and transactional synchronization.

## Table of Contents

- [Quick Start](#quick-start)
- [Core Components](#core-components)
- [Processing Pipeline](#processing-pipeline)
- [Service Interfaces](#service-interfaces)
- [Data Models](#data-models)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Testing](#testing)
- [Examples](#examples)

## Quick Start

### Basic Usage

```python
from src.workers.monitor.processor import DefaultPRProcessor
from src.workers.monitor.discovery import GitHubPRDiscoveryService
from src.workers.monitor.change_detection import DatabaseChangeDetector
from src.workers.monitor.synchronization import DatabaseSynchronizer
from src.github.client import GitHubClient
from src.models.repository import Repository

# Initialize services
github_client = GitHubClient(token="your-github-token")
pr_repo = PullRequestRepository(session)
check_repo = CheckRunRepository(session)

# Create processing services
discovery_service = GitHubPRDiscoveryService(github_client)
change_detector = DatabaseChangeDetector(pr_repo, check_repo)
synchronizer = DatabaseSynchronizer(session)

# Create processor
processor = DefaultPRProcessor(
    discovery_service=discovery_service,
    change_detection_service=change_detector,
    synchronization_service=synchronizer,
    max_concurrent_repos=10
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
print(f"Success: {result.success}, Changes: {result.changes_synchronized}")
```

### Batch Processing

```python
# Process multiple repositories concurrently
repositories = [repo1, repo2, repo3]
batch_result = await processor.process_repositories(repositories)

print(f"Processed: {batch_result.repositories_processed}")
print(f"Success Rate: {batch_result.success_rate:.1f}%")
```

## Core Components

### PR Processor

The `PRProcessor` is the main orchestrator that coordinates the three-phase processing pipeline.

#### DefaultPRProcessor

```python
class DefaultPRProcessor(PRProcessor):
    """
    Default implementation of PR processor.
    
    Orchestrates the complete processing flow:
    1. Discovery: Find all PRs and check runs for a repository
    2. Change Detection: Identify what has changed since last processing  
    3. Synchronization: Persist changes to database
    """
    
    async def process_repository(self, repository: Repository) -> ProcessingResult:
        """Process a single repository through the complete workflow."""
        
    async def process_repositories(self, repositories: list[Repository]) -> BatchProcessingResult:
        """Process multiple repositories concurrently."""
```

**Key Features:**
- **Error Isolation**: Individual repository failures don't affect others
- **Comprehensive Metrics**: Detailed tracking of processing results
- **Concurrency Control**: Semaphore-based limiting of concurrent operations
- **State Tracking**: Updates repository failure counts and timestamps

### GitHub PR Discovery Service

The `GitHubPRDiscoveryService` handles fetching PR and check run data from GitHub's API.

```python
class GitHubPRDiscoveryService(PRDiscoveryService):
    """GitHub implementation of PR discovery service with caching and optimization."""
    
    def __init__(
        self,
        github_client: GitHubClient,
        max_concurrent_requests: int = 10,
        cache_ttl_seconds: int = 300
    ):
        """Initialize with GitHub client and performance settings."""
    
    async def discover_prs(
        self, 
        repository: Repository, 
        since: datetime | None = None
    ) -> list[PRData]:
        """Discover pull requests from a GitHub repository."""
    
    async def discover_check_runs_batch(
        self, 
        repository: Repository, 
        pr_data_list: list[PRData]
    ) -> dict[int, list[CheckRunData]]:
        """Discover check runs for multiple pull requests concurrently."""
```

**Key Features:**
- **ETag Caching**: Conditional requests to minimize API calls
- **Rate Limiting**: Semaphore-based request throttling
- **Pagination**: Automatic handling of large result sets
- **Concurrent Processing**: Parallel check run discovery
- **Error Resilience**: Individual PR failures don't stop batch processing

### Database Change Detector

The `DatabaseChangeDetector` compares GitHub data with stored database state to identify changes.

```python
class DatabaseChangeDetector(ChangeDetector):
    """Database-backed change detector implementation."""
    
    def __init__(
        self,
        pr_repository: PullRequestRepository,
        check_run_repository: CheckRunRepository
    ):
        """Initialize with repository dependencies."""
    
    async def detect_pr_changes(
        self, 
        repository_id: uuid.UUID, 
        pr_data_list: list[PRData]
    ) -> list[PRChangeRecord]:
        """Detect changes for a list of PRs from GitHub API data."""
    
    async def detect_check_run_changes(
        self,
        pr_changes: list[PRChangeRecord],
        check_runs_by_pr: dict[int, list[CheckRunData]]
    ) -> list[CheckRunChangeRecord]:
        """Detect changes for check runs based on PR changes and GitHub data."""
```

**Change Detection Types:**
- **New Entities**: PRs and check runs not in database
- **Field Changes**: Title, state, draft status, metadata updates
- **SHA Changes**: New commits (head_sha changes)
- **Status Changes**: Check run status and conclusion updates
- **Timing Changes**: Check run start/completion times

### Database Synchronizer

The `DatabaseSynchronizer` persists changes to the database with transactional consistency.

```python
class DatabaseSynchronizer(DataSynchronizer):
    """Implementation of database synchronization with transactional support."""
    
    def __init__(self, session: AsyncSession):
        """Initialize synchronizer with database session."""
    
    async def synchronize_changes(
        self, 
        repository_id: uuid.UUID, 
        changeset: ChangeSet
    ) -> int:
        """Synchronize all changes in a changeset within a single transaction."""
    
    async def create_new_prs(self, new_prs: list[PRChangeRecord]) -> list[PullRequest]:
        """Create new pull request records using bulk operations."""
    
    async def update_existing_prs(self, updated_prs: list[PRChangeRecord]) -> list[PullRequest]:
        """Update existing pull request records using bulk operations."""
```

**Key Features:**
- **Transactional Consistency**: All changes committed or rolled back together
- **Bulk Operations**: PostgreSQL UPSERT for performance
- **State History**: Maintains audit trail of PR state transitions
- **Error Recovery**: Automatic rollback on failures

## Processing Pipeline

### Phase 1: Discovery

```python
# Discover PRs and check runs from GitHub
prs_discovered, checks_discovered = await discovery_service.discover_prs_and_checks(repository)
```

**Operations:**
1. Fetch PRs using GitHub API with pagination
2. Apply ETag caching for conditional requests
3. Discover check runs for each PR's head commit
4. Handle rate limiting and API errors
5. Extract structured data from GitHub responses

### Phase 2: Change Detection

```python
# Detect what has changed since last processing
changeset = await change_detection_service.detect_changes(repository)
```

**Operations:**
1. Query database for existing PRs and check runs
2. Compare GitHub data with database state
3. Identify specific field changes and new entities
4. Create change records with old/new value tracking
5. Organize changes into structured changeset

### Phase 3: Synchronization

```python
# Persist changes to database
synchronized_count = await synchronization_service.synchronize_changes(changeset)
```

**Operations:**
1. Begin database transaction
2. Bulk create new PRs with conflict resolution
3. Update existing PRs with state transitions
4. Create and update check runs in batches
5. Record state history for audit trail
6. Commit transaction or rollback on error

## Service Interfaces

### PRDiscoveryService Protocol

```python
class PRDiscoveryService(Protocol):
    """Interface for PR discovery service."""
    
    async def discover_prs_and_checks(self, repository: Repository) -> tuple[int, int]:
        """Discover PRs and check runs for a repository."""
```

### ChangeDetectionService Protocol

```python
class ChangeDetectionService(Protocol):
    """Interface for change detection service."""
    
    async def detect_changes(self, repository: Repository) -> ChangeSet:
        """Detect changes for a repository."""
```

### SynchronizationService Protocol

```python
class SynchronizationService(Protocol):
    """Interface for data synchronization service."""
    
    async def synchronize_changes(self, changeset: ChangeSet) -> int:
        """Synchronize detected changes to persistent storage."""
```

## Data Models

### PRData

```python
@dataclass
class PRData:
    """Raw GitHub PR data representation."""
    
    # Basic PR information
    number: int
    title: str
    author: str
    state: str
    draft: bool
    
    # Branch information
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    
    # URLs and metadata
    url: str
    body: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    
    def to_pr_state(self) -> PRState:
        """Convert GitHub state string to PRState enum."""
    
    def get_metadata_dict(self) -> dict[str, Any]:
        """Get metadata dictionary for database storage."""
```

### CheckRunData

```python
@dataclass
class CheckRunData:
    """Raw GitHub check run data representation."""
    
    # GitHub check run information
    external_id: str
    check_name: str
    status: str
    conclusion: str | None = None
    
    # URLs and output
    details_url: str | None = None
    logs_url: str | None = None
    output_summary: str | None = None
    
    # Timing information
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    def to_check_status(self) -> CheckStatus:
        """Convert GitHub status string to CheckStatus enum."""
    
    def to_check_conclusion(self) -> CheckConclusion | None:
        """Convert GitHub conclusion string to CheckConclusion enum."""
```

### ChangeSet

```python
@dataclass
class ChangeSet:
    """Collection of detected changes for a repository."""
    
    repository_id: uuid.UUID
    
    # PR changes
    new_prs: list[PRChangeRecord] = field(default_factory=list)
    updated_prs: list[PRChangeRecord] = field(default_factory=list)
    
    # Check run changes
    new_check_runs: list[CheckRunChangeRecord] = field(default_factory=list)
    updated_check_runs: list[CheckRunChangeRecord] = field(default_factory=list)
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any changes to process."""
    
    @property
    def total_changes(self) -> int:
        """Get total number of changes."""
```

### ProcessingResult

```python
@dataclass
class ProcessingResult:
    """Results of processing a single repository."""
    
    repository_id: uuid.UUID
    repository_url: str
    
    # Processing metrics
    prs_discovered: int = 0
    check_runs_discovered: int = 0
    changes_synchronized: int = 0
    
    # Change breakdown
    new_prs: int = 0
    updated_prs: int = 0
    new_check_runs: int = 0
    updated_check_runs: int = 0
    
    # Processing timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    
    # Error tracking
    errors: list[ProcessingError] = field(default_factory=list)
    success: bool = True
    
    @property
    def processing_time(self) -> float:
        """Get processing time in seconds."""
```

## Configuration

### Basic Configuration

```python
# Discovery Service Configuration
discovery_service = GitHubPRDiscoveryService(
    github_client=github_client,
    max_concurrent_requests=10,  # API request concurrency
    cache_ttl_seconds=300       # ETag cache TTL
)

# Processor Configuration  
processor = DefaultPRProcessor(
    discovery_service=discovery_service,
    change_detection_service=change_detector,
    synchronization_service=synchronizer,
    max_concurrent_repos=10     # Repository processing concurrency
)
```

### GitHub Client Configuration

```python
github_client = GitHubClient(
    token="your-github-token",
    base_url="https://api.github.com",  # GitHub Enterprise support
    timeout=30,                         # Request timeout
    retry_attempts=3                    # Retry failed requests
)
```

### Performance Tuning

```python
# High-throughput configuration
processor = DefaultPRProcessor(
    # ... services ...
    max_concurrent_repos=20  # Higher concurrency for more repos
)

discovery_service = GitHubPRDiscoveryService(
    github_client=github_client,
    max_concurrent_requests=15,  # Higher API concurrency
    cache_ttl_seconds=600       # Longer cache TTL
)
```

## Error Handling

### Error Types

```python
@dataclass
class ProcessingError:
    """Error that occurred during processing."""
    
    error_type: str  # "discovery_failure", "change_detection_failure", "synchronization_failure"
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Optional details
    repository_id: uuid.UUID | None = None
    pr_number: int | None = None
    check_run_id: str | None = None
```

### Error Recovery

```python
# Process repository with error handling
result = await processor.process_repository(repository)

if not result.success:
    for error in result.errors:
        logger.error(f"Processing error: {error}")
        
        # Handle specific error types
        if error.error_type == "discovery_failure":
            # Maybe retry with different parameters
            pass
        elif error.error_type == "synchronization_failure":
            # Check for database issues
            pass
```

### Repository Failure Tracking

```python
# Repository automatically tracks failures
if result.success:
    repository.reset_failure_count()
else:
    repository.increment_failure_count(str(result.errors[0]))

# Check if repository needs attention
if repository.failure_count > 5:
    logger.warning(f"Repository {repository.name} has {repository.failure_count} consecutive failures")
```

## Performance Considerations

### Concurrency Control

- **Repository Level**: `max_concurrent_repos` limits parallel repository processing
- **API Level**: `max_concurrent_requests` limits parallel GitHub API calls
- **Database Level**: Connection pooling manages database connections

### Optimization Strategies

```python
# Bulk database operations
await synchronizer.create_new_prs(new_prs)  # Single bulk insert
await synchronizer.update_existing_prs(updated_prs)  # Batch updates

# ETag caching
# Automatically used by discovery service for repeat requests

# Rate limiting
# Built into GitHub client and discovery service
```

### Memory Management

- **Streaming Processing**: Processes repositories individually, not all at once
- **Connection Pooling**: Reuses database connections
- **Cache Management**: Automatic cleanup of expired ETag cache entries

## Testing

### Unit Testing

```python
# Test individual components with mocks
async def test_discovery_service(mock_github_client):
    service = GitHubPRDiscoveryService(mock_github_client)
    prs = await service.discover_prs(repository)
    assert len(prs) == expected_count

async def test_change_detection(mock_pr_repo, mock_check_repo):
    detector = DatabaseChangeDetector(mock_pr_repo, mock_check_repo) 
    changes = await detector.detect_pr_changes(repo_id, pr_data_list)
    assert len(changes) == expected_changes
```

### Integration Testing

```python
# Test complete workflow with real database
async def test_end_to_end_processing(database_session, sample_data):
    processor = create_processor(database_session)
    result = await processor.process_repository(test_repository)
    
    assert result.success
    assert result.changes_synchronized > 0
    
    # Verify data was persisted
    prs_in_db = await pr_repo.get_recent_prs(repo_id)
    assert len(prs_in_db) == expected_count
```

## Examples

### Custom Discovery Service

```python
class CustomPRDiscoveryService(PRDiscoveryService):
    """Custom discovery service with additional filtering."""
    
    def __init__(self, github_client: GitHubClient, exclude_labels: list[str]):
        self.github_client = github_client
        self.exclude_labels = exclude_labels
    
    async def discover_prs(self, repository: Repository, since: datetime | None = None) -> list[PRData]:
        """Discover PRs with label filtering."""
        all_prs = await self.github_client.get_pulls(repository.full_name)
        
        # Filter out PRs with excluded labels
        filtered_prs = []
        for pr_json in all_prs:
            pr_labels = [label["name"] for label in pr_json.get("labels", [])]
            if not any(label in self.exclude_labels for label in pr_labels):
                filtered_prs.append(self._extract_pr_data(pr_json))
        
        return filtered_prs
```

### Custom Change Detector

```python
class ThresholdChangeDetector(DatabaseChangeDetector):
    """Change detector with significance thresholds."""
    
    def __init__(self, pr_repo, check_repo, min_change_threshold=0.1):
        super().__init__(pr_repo, check_repo)
        self.min_change_threshold = min_change_threshold
    
    async def detect_pr_changes(self, repository_id, pr_data_list):
        """Only detect changes above significance threshold."""
        all_changes = await super().detect_pr_changes(repository_id, pr_data_list)
        
        # Filter changes by significance
        significant_changes = []
        for change in all_changes:
            if self._is_significant_change(change):
                significant_changes.append(change)
        
        return significant_changes
```

### Monitoring Integration

```python
class MonitoredPRProcessor(DefaultPRProcessor):
    """PR processor with metrics collection."""
    
    def __init__(self, *args, metrics_collector, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = metrics_collector
    
    async def process_repository(self, repository):
        start_time = time.time()
        result = await super().process_repository(repository)
        processing_time = time.time() - start_time
        
        # Record metrics
        self.metrics.record_processing_time(repository.id, processing_time)
        self.metrics.record_changes_synchronized(repository.id, result.changes_synchronized)
        
        if result.success:
            self.metrics.record_success(repository.id)
        else:
            self.metrics.record_failure(repository.id, result.errors)
        
        return result
```

---

**Next Steps:**
- 📖 **Usage Examples**: See [PR Monitor Examples](examples/pr-monitor-usage.py) for complete implementations
- 🔧 **Configuration**: Review [Configuration Guide](../config/README.md) for advanced setup
- 🧪 **Testing**: Check [Testing Guide](../testing/README.md) for testing strategies
- 📊 **Monitoring**: See [Monitoring Guide](../user-guide/monitoring.md) for operational monitoring