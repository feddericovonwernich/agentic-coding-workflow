# PR Monitoring Workflow (Issue #48 - Updated)

## Purpose
This diagram shows the complete workflow of how the PR Monitor Worker discovers, tracks, and categorizes pull requests using the new comprehensive architecture. It demonstrates the decision logic that determines whether a PR should be analyzed, reviewed, or escalated to humans.

## What It Shows
- **Periodic Polling**: How the system regularly checks for PR updates
- **State Management**: How the system tracks what it has seen before
- **Decision Logic**: Rules for determining next actions
- **Escalation Triggers**: When human intervention is required

## Key Insights
- **Stateful Processing**: The system remembers what it has seen to avoid duplicate work
- **Configurable Filtering**: Skip patterns allow customization of what gets processed
- **Threshold-Based Escalation**: Repeated failures trigger human notification
- **Branching Logic**: Different paths for new vs. existing PRs

## Diagram

```mermaid
flowchart TD
    START([PRProcessor.process_repositories<br/>Triggered]) --> INIT[Phase: Initialization<br/>Load repository contexts]
    
    INIT --> DISCOVERY[Phase: Discovery<br/>PRDiscoveryEngine +<br/>CheckRunDiscoveryEngine]
    
    DISCOVERY --> CACHE_CHECK{Cache<br/>Hit?}
    CACHE_CHECK -->|Yes| LOAD_CACHED[Load Cached Data<br/>>95% efficiency]
    CACHE_CHECK -->|No| API_FETCH[GitHub API Fetch<br/>with rate limiting]
    
    API_FETCH --> PARSE_DATA[Parse DiscoveryResult &<br/>CheckRunDiscovery models]
    LOAD_CACHED --> CHANGE_DETECT[Phase: Change Detection<br/>StateChangeDetector]
    PARSE_DATA --> CHANGE_DETECT
    
    CHANGE_DETECT --> COMPARE_STATE{O(1) State<br/>Comparison}
    COMPARE_STATE --> FILTER_CHANGES{Significant<br/>Changes?}
    
    FILTER_CHANGES -->|No| END_SESSION[Complete Session<br/>Update metrics]
    FILTER_CHANGES -->|Yes| CATEGORIZE[Categorize Changes<br/>by severity & type]
    
    CATEGORIZE --> SYNC_PHASE[Phase: Synchronization<br/>DataSynchronizer]
    
    SYNC_PHASE --> BEGIN_TRANSACTION[Begin Database<br/>Transaction]
    BEGIN_TRANSACTION --> BULK_OPS[Bulk Operations<br/>Create/Update PRs & Checks]
    
    BULK_OPS --> VALIDATION{Validation<br/>Success?}
    VALIDATION -->|No| ROLLBACK[Rollback Transaction<br/>& Log Errors]
    VALIDATION -->|Yes| COMMIT[Commit Transaction<br/>& Record State Changes]
    
    COMMIT --> ROUTE_ACTIONS[Route Actions Based<br/>on Change Events]
    
    ROUTE_ACTIONS --> CHECK_FAILED{Actionable<br/>Failures?}
    CHECK_FAILED -->|Yes| QUEUE_ANALYSIS[Queue for Analysis<br/>High Priority]
    CHECK_FAILED -->|No| CHECK_SUCCESS{All Checks<br/>Passing?}
    
    CHECK_SUCCESS -->|Yes| QUEUE_REVIEW[Queue for Review<br/>Medium Priority]
    CHECK_SUCCESS -->|No| ESCALATE_CHECK{Failure Count ><br/>Threshold?}
    
    ESCALATE_CHECK -->|Yes| NOTIFY_ADMIN[Notify Admin<br/>Critical Priority]
    ESCALATE_CHECK -->|No| QUEUE_ANALYSIS
    
    ROLLBACK --> END_SESSION
    QUEUE_ANALYSIS --> END_SESSION
    QUEUE_REVIEW --> END_SESSION  
    NOTIFY_ADMIN --> END_SESSION
    
    END_SESSION --> COLLECT_METRICS[Collect Final Metrics<br/>Performance & Success Rates]
    COLLECT_METRICS --> CLEANUP[Resource Cleanup<br/>Clear Caches & Sessions]
    CLEANUP --> END_COMPLETE([Processing Complete<br/>Return ProcessingSession])
    
    style START fill:#e1f5fe
    style DISCOVERY fill:#f3e5f5
    style CHANGE_DETECT fill:#e8f5e9
    style SYNC_PHASE fill:#fff3e0
    style QUEUE_ANALYSIS fill:#ffebee
    style QUEUE_REVIEW fill:#e8f5e9
    style NOTIFY_ADMIN fill:#fff3e0
    style END_COMPLETE fill:#e1f5fe
```

## Workflow Steps Explained (New Implementation)

### 1. Session Initialization
- **PRProcessor**: Main orchestrator coordinates the entire workflow
- **Repository Contexts**: Load repository metadata with processing priorities
- **Processing Modes**: Full, incremental, or dry-run processing
- **Resource Management**: Configure memory limits, concurrency, and monitoring

### 2. Discovery Phase
- **PRDiscoveryEngine**: Fetches PRs with intelligent pagination and filtering
- **CheckRunDiscoveryEngine**: Discovers associated check runs for each PR
- **Performance Optimization**: Repository-level parallelization with semaphore control
- **Data Models**: Immutable DiscoveryResult and CheckRunDiscovery with validation

### 3. Intelligent Caching
- **Cache Strategy**: >95% cache hit rate for unchanged data
- **Incremental Updates**: Only fetch changes since last processing
- **ETag Support**: GitHub ETag headers for efficient API usage
- **Memory Management**: Configurable cache sizes and eviction policies

### 4. State Change Detection
- **StateChangeDetector**: Efficient O(1) comparison of PR and check run states
- **Change Events**: StateChangeEvent models with severity levels and categorization
- **Prioritization**: Automatic priority assignment based on change significance
- **Filtering**: Actionable change detection to avoid unnecessary processing

### 5. Data Synchronization
- **DataSynchronizer**: Handles bulk database operations with transaction management
- **ACID Compliance**: Full transaction support with rollback capabilities
- **Conflict Resolution**: Handles concurrent updates and database constraints
- **Bulk Operations**: Optimized batch processing for large datasets

### 6. Transaction Management
- **Database Transactions**: Ensure data consistency across all operations
- **Rollback Capability**: Full rollback on any failure with detailed error logging
- **Validation**: Comprehensive data validation before committing changes
- **Error Recovery**: Repository-level isolation prevents cascade failures

### 7. Action Routing
- **Actionable Failures**: Identify check runs that can be automatically fixed
- **Failure Categorization**: Route by failure type (lint, format, test, build, etc.)
- **Success Handling**: Queue successful PRs for multi-agent review
- **Escalation Logic**: Threshold-based escalation to human reviewers

### 8. Comprehensive Monitoring
- **ProcessingMetrics**: Track API usage, processing times, and success rates
- **Resource Monitoring**: Memory and CPU usage tracking with alerts
- **Performance Optimization**: Dynamic batching and concurrency adjustment
- **Session Results**: Detailed ProcessingSession with complete audit trail

## Configuration Options (New Implementation)

### Processor Configuration
```yaml
# PRProcessor configuration
processor_config:
  # Concurrency limits
  max_concurrent_repos: 10
  max_concurrent_api_calls: 50
  max_concurrent_check_discoveries: 20
  
  # Performance tuning
  batch_size: 25
  api_timeout: 30
  db_batch_size: 100
  memory_limit_mb: 2048
  
  # Processing behavior
  incremental_window_hours: 24
  enable_dry_run: false
  stop_on_first_error: false
  enable_recovery_mode: true
  
  # Monitoring and debugging
  enable_metrics: true
  enable_detailed_logging: false
  log_level: "INFO"
  metrics_collection_interval: 10
```

### Discovery Engine Configuration
```yaml
# Discovery configuration
discovery_config:
  per_page: 100
  max_concurrent_repos: 10
  batch_size: 25
  request_delay: 0.1
  cache_ttl: 300
  enable_etag_caching: true
```

### Repository Settings
```yaml
repositories:
  - url: "https://github.com/org/repo"
    skip_patterns:
      pr_labels: ["wip", "draft", "dependencies"]
      check_names: ["codecov/*", "license/*"]
      authors: ["dependabot[bot]"]
    failure_threshold: 5
    polling_interval: 300
    processing_priority: 1  # Higher numbers = higher priority
```

### Skip Pattern Examples
- **PR Labels**: Skip PRs with certain labels
- **Check Names**: Ignore specific CI checks
- **Authors**: Exclude automated PR creators
- **File Patterns**: Skip PRs touching only certain files

## Error Handling

### GitHub API Failures
- **Rate Limiting**: Exponential backoff and retry
- **Network Errors**: Temporary failure handling
- **Authentication**: Token refresh mechanisms

### Database Failures
- **Connection Pooling**: Maintain database connectivity
- **Transaction Rollback**: Ensure data consistency
- **Deadlock Handling**: Retry logic for concurrent updates

### Queue Failures
- **Message Persistence**: Ensure events aren't lost
- **Dead Letter Queues**: Handle unprocessable messages
- **Circuit Breakers**: Stop publishing when queue is down