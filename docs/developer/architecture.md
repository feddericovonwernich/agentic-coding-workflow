# System Architecture

> **📋 Document Purpose**: This document provides **comprehensive system architecture documentation** including design decisions, component relationships, data flow patterns, and rationale for architectural choices.

## Architecture Overview

This document serves as the **definitive guide** to understanding the Agentic Coding Workflow system architecture, from high-level design principles to detailed component interactions.

## System Overview

The Agentic Coding Workflow is an automated system for monitoring, analyzing, and fixing failed GitHub pull request checks using LLM-powered analysis and intelligent code modification.

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    GitHub       │    │   Queue System  │    │   Database      │
│   Repositories  │◄──►│    (Redis)      │◄──►│ (PostgreSQL)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
┌─────────────────────────────────────────────────────────────────┐
│                     Worker Orchestration                        │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│   PR Monitor   │ Check Analyzer  │  Fix Applicator │ Review    │
│    Worker       │     Worker      │     Worker      │ Orchestr. │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
         ▲                       ▲                       ▲
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  GitHub API     │    │  LLM Providers  │    │  Notification   │
│   Integration   │    │ (Anthropic/AI)  │    │   Services      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Core Principles

1. **Microservices Architecture**: Separate workers for distinct responsibilities
2. **Event-Driven Processing**: Queue-based communication between components
3. **Provider Abstraction**: Pluggable providers for external services
4. **Asynchronous Operations**: Non-blocking I/O for scalability
5. **Fault Tolerance**: Graceful degradation and error recovery

## Component Architecture

### 1. Worker System

#### Base Worker Pattern

All workers implement a common interface for consistent behavior:

```python
class BaseWorker(ABC):
    """Base class for all worker implementations."""
    
    @abstractmethod
    async def process_message(self, message: WorkerMessage) -> None:
        """Process a single message from the queue."""
        pass
    
    async def run(self) -> None:
        """Main worker loop with error handling."""
        while True:
            message = await self.queue.get_message()
            try:
                await self.process_message(message)
                await self.queue.acknowledge_message(message)
            except Exception as e:
                await self.handle_processing_error(message, e)
```

#### PR Monitor Worker

**Responsibility**: Fetch and track pull request states from GitHub

```python
# Core functionality
class PRMonitorWorker(BaseWorker):
    async def process_message(self, message: WorkerMessage) -> None:
        repository_id = message.data["repository_id"]
        
        # Fetch latest PRs from GitHub
        prs = await self.github_client.get_pull_requests(repository_id)
        
        # Update database with new/changed PRs
        for pr in prs:
            await self.update_pr_state(pr)
            
        # Queue check analysis for failed checks
        for pr in prs:
            failed_checks = await self.get_failed_checks(pr)
            for check in failed_checks:
                await self.queue_check_analysis(check)
```

**Key Operations**:
- Repository polling based on configured intervals
- PR state change detection
- Failed check identification
- Analysis job queuing

#### Check Analyzer Worker

**Responsibility**: Analyze failed check logs using LLM providers

```python
class CheckAnalyzerWorker(BaseWorker):
    async def process_message(self, message: WorkerMessage) -> None:
        check_run_id = message.data["check_run_id"]
        
        # Extract check logs
        logs = await self.extract_check_logs(check_run_id)
        
        # Analyze with configured LLM
        analysis = await self.llm_provider.analyze_failure(logs, context)
        
        # Store analysis and route next action
        await self.store_analysis(analysis)
        await self.route_decision(analysis)
```

**Analysis Output**:
- Failure category (compilation, test, lint, deployment)
- Root cause identification with evidence
- Confidence score (0-100)
- Fix strategy recommendations
- Complexity estimation

#### Fix Applicator Worker

**Responsibility**: Apply automated fixes using Claude Code SDK

```python
class FixApplicatorWorker(BaseWorker):
    async def process_message(self, message: WorkerMessage) -> None:
        analysis_id = message.data["analysis_id"]
        
        # Load analysis and PR context
        analysis = await self.get_analysis(analysis_id)
        pr = await self.get_pull_request(analysis.check_run.pr_id)
        
        # Apply fix using Claude Code SDK
        fix_result = await self.claude_code_client.apply_fix(
            repository=pr.repository,
            branch=pr.branch,
            analysis=analysis
        )
        
        # Validate and commit fix
        if await self.validate_fix(fix_result):
            await self.commit_and_push_fix(fix_result)
        else:
            await self.escalate_fix_failure(analysis)
```

**Fix Validation Pipeline**:
1. Run affected tests locally
2. Execute linters and formatters
3. Verify build passes
4. Check for breaking changes

#### Review Orchestrator Worker

**Responsibility**: Coordinate multi-agent PR reviews

```python
class ReviewOrchestratorWorker(BaseWorker):
    async def process_message(self, message: WorkerMessage) -> None:
        pr_id = message.data["pr_id"]
        
        # Get configured reviewers for repository
        reviewers = await self.get_configured_reviewers(pr_id)
        
        # Execute reviews concurrently
        reviews = await asyncio.gather(*[
            self.execute_review(reviewer, pr_id)
            for reviewer in reviewers
        ])
        
        # Aggregate results and make decision
        decision = await self.aggregate_review_results(reviews)
        await self.apply_review_decision(pr_id, decision)
```

**Review Types**:
- Security review (authentication, input validation, crypto)
- Performance review (algorithms, database queries, caching)
- Code quality review (maintainability, testing, documentation)
- Architecture review (design patterns, coupling, cohesion)

### 2. Service Layer

#### GitHub Integration Service

```python
class GitHubClient:
    """Comprehensive GitHub API client with authentication and rate limiting."""
    
    async def get_pull_requests(self, repository: str) -> List[PullRequest]:
        """Fetch pull requests with automatic pagination."""
        
    async def get_check_runs(self, pr: PullRequest) -> List[CheckRun]:
        """Get check runs for a pull request."""
        
    async def get_check_logs(self, check_run: CheckRun) -> str:
        """Extract logs from a failed check run."""
        
    async def create_review(self, pr: PullRequest, review: Review) -> None:
        """Post automated review to GitHub."""
```

**Features**:
- Automatic rate limiting with backoff
- Authentication via PAT or GitHub App
- Comprehensive error handling
- Request caching for efficiency

#### LLM Provider Service

```python
class LLMProvider(ABC):
    """Abstract base class for LLM integrations."""
    
    @abstractmethod
    async def analyze_failure(
        self, 
        logs: str, 
        context: AnalysisContext
    ) -> FailureAnalysis:
        """Analyze check failure and determine fix strategy."""
        
    @abstractmethod
    async def generate_fix(
        self, 
        analysis: FailureAnalysis
    ) -> Optional[FixSuggestion]:
        """Generate specific fix suggestions."""
        
    @abstractmethod
    async def review_code(
        self, 
        pr: PullRequest, 
        focus_areas: List[str]
    ) -> ReviewResult:
        """Perform code review with specific focus areas."""
```

**Implementations**:
- **AnthropicProvider**: Claude integration for analysis and fixes
- **OpenAIProvider**: GPT models for specialized reviews
- **LocalProvider**: Self-hosted models for cost optimization

#### Notification Service

```python
class NotificationService:
    """Unified notification service with multiple providers."""
    
    async def send_escalation(
        self, 
        pr: PullRequest, 
        reason: EscalationReason
    ) -> bool:
        """Send human escalation notification."""
        
    async def send_fix_report(
        self, 
        fix_attempt: FixAttempt
    ) -> bool:
        """Report fix attempt results."""
        
    async def send_review_summary(
        self, 
        pr: PullRequest, 
        reviews: List[Review]
    ) -> bool:
        """Send aggregated review results."""
```

### 3. Data Layer

#### Database Schema

The system uses PostgreSQL with the following core entities:

```sql
-- Repositories being monitored
CREATE TABLE repositories (
    id UUID PRIMARY KEY,
    url VARCHAR(500) NOT NULL,
    name VARCHAR(255) NOT NULL,
    configuration JSONB,
    last_checked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Pull requests tracked in the system
CREATE TABLE pull_requests (
    id UUID PRIMARY KEY,
    repository_id UUID REFERENCES repositories(id),
    pr_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    author VARCHAR(255) NOT NULL,
    branch VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_checked_at TIMESTAMP
);

-- Individual check runs for each PR
CREATE TABLE check_runs (
    id UUID PRIMARY KEY,
    pr_id UUID REFERENCES pull_requests(id),
    external_id VARCHAR(255),  -- GitHub check run ID
    check_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    conclusion VARCHAR(50),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    log_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- LLM analysis results
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY,
    check_run_id UUID REFERENCES check_runs(id),
    provider VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,
    root_cause TEXT NOT NULL,
    confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
    fix_strategy JSONB,
    evidence JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Automated fix attempts
CREATE TABLE fix_attempts (
    id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES analysis_results(id),
    status VARCHAR(50) NOT NULL,
    commit_sha VARCHAR(40),
    error_message TEXT,
    validation_results JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Multi-agent reviews
CREATE TABLE reviews (
    id UUID PRIMARY KEY,
    pr_id UUID REFERENCES pull_requests(id),
    reviewer_name VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    decision VARCHAR(50) NOT NULL,
    confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
    comments JSONB,
    focus_areas TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Repository Pattern Implementation

```python
class BaseRepository:
    """Base repository with common database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, **kwargs) -> T:
        """Create new entity."""
        
    async def get_by_id(self, id: UUID) -> Optional[T]:
        """Get entity by ID."""
        
    async def update(self, id: UUID, **kwargs) -> Optional[T]:
        """Update entity."""
        
    async def delete(self, id: UUID) -> bool:
        """Delete entity."""

class PullRequestRepository(BaseRepository[PullRequest]):
    """Specialized operations for pull requests."""
    
    async def get_by_repository_and_number(
        self, 
        repository_id: UUID, 
        pr_number: int
    ) -> Optional[PullRequest]:
        """Get PR by repository and number."""
        
    async def get_prs_with_failed_checks(self) -> List[PullRequest]:
        """Get PRs that have failed checks needing analysis."""
        
    async def get_prs_ready_for_review(self) -> List[PullRequest]:
        """Get PRs with all checks passing, ready for review."""
```

## Data Flow Architecture

### 1. PR Monitoring Flow

```
GitHub Repository
        │
        ▼
   PR Monitor Worker ────► Queue: check_analysis
        │
        ▼
    Database: PRs, CheckRuns
```

### 2. Analysis and Fix Flow

```
Queue: check_analysis
        │
        ▼
  Check Analyzer Worker ◄──► LLM Provider
        │
        ▼
  Decision Router
    ├─► Auto-fixable ────► Queue: apply_fix
    ├─► Review needed ───► Queue: review_pr  
    └─► Escalate ────────► Notification Service
```

### 3. Fix Application Flow

```
Queue: apply_fix
        │
        ▼
  Fix Applicator Worker ◄──► Claude Code SDK
        │
        ▼
   Validation Pipeline
    ├─► Success ─────► GitHub (commit & push)
    └─► Failure ─────► Escalation
```

### 4. Review Flow

```
Queue: review_pr
        │
        ▼
Review Orchestrator Worker
        │
        ├─► Security Reviewer ◄──► LLM Provider
        ├─► Performance Reviewer ◄─► LLM Provider  
        └─► Quality Reviewer ◄────► LLM Provider
        │
        ▼
   Result Aggregation
        │
        ▼
  GitHub Review + Database
```

## Design Decisions

### 1. Queue-Based Architecture

**Decision**: Use Redis queues for inter-worker communication

**Rationale**:
- Decouples worker components for independent scaling
- Provides natural backpressure and flow control
- Enables dead letter queues for error handling
- Supports priority queues for urgent PRs

**Alternatives Considered**:
- Direct database polling (rejected: inefficient, no backpressure)
- Webhook-based (rejected: complex failure handling)

### 2. Provider Pattern for External Services

**Decision**: Abstract all external services behind provider interfaces

**Rationale**:
- Enables easy switching between LLM providers
- Supports multiple notification channels
- Facilitates testing with mock providers
- Allows per-repository provider configuration

**Implementation Pattern**:
```python
# Abstract interface
class LLMProvider(ABC):
    async def analyze_failure(self, logs: str) -> FailureAnalysis:
        pass

# Multiple implementations
class AnthropicProvider(LLMProvider): ...
class OpenAIProvider(LLMProvider): ...
class LocalModelProvider(LLMProvider): ...
```

### 3. Async/Await Throughout

**Decision**: Use async/await for all I/O operations

**Rationale**:
- Maximizes concurrency for I/O-bound operations
- Reduces resource usage vs threading
- Natural fit for worker pattern
- Better error propagation

**Key Areas**:
- Database operations (SQLAlchemy async)
- HTTP requests (aiohttp)
- Queue operations (aioredis)
- LLM API calls (async providers)

### 4. Configuration-Driven Behavior

**Decision**: Use YAML configuration with environment variable substitution

**Rationale**:
- Enables different behavior per repository
- Supports environment-specific settings
- Avoids hardcoded values in source
- Easy validation with Pydantic schemas

**Example Configuration**:
```yaml
repositories:
  - url: "https://github.com/org/critical-app"
    failure_threshold: 1  # Immediate analysis
    auto_fix_enabled: false  # Manual review only
    reviewers: ["security", "performance"]
    
  - url: "https://github.com/org/test-app"  
    failure_threshold: 3  # More tolerance
    auto_fix_enabled: true
    reviewers: ["quality"]
```

### 5. Database Schema Design

**Decision**: Normalized schema with JSONB for flexible data

**Rationale**:
- Structured data benefits from normalization
- JSONB provides flexibility for evolving analysis formats
- PostgreSQL JSONB supports efficient queries
- Maintains data integrity with foreign keys

**Key Design Choices**:
- UUIDs for primary keys (distributed-friendly)
- Timestamps for all entities (audit trail)
- JSONB for analysis results and configurations
- Enum constraints for status fields

## Performance Considerations

### 1. Concurrency Patterns

```python
# Process multiple repositories concurrently
async def monitor_repositories(repository_ids: List[UUID]) -> None:
    tasks = [
        monitor_single_repository(repo_id) 
        for repo_id in repository_ids
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

# Batch database operations
async def update_multiple_prs(prs: List[PullRequest]) -> None:
    async with session.begin():
        for pr in prs:
            session.add(pr)
        await session.commit()
```

### 2. Caching Strategy

- **GitHub API responses**: Cache for 60 seconds to reduce API calls
- **LLM analysis**: Cache by log content hash to avoid reanalysis
- **Database queries**: Use SQLAlchemy query caching
- **Configuration**: Cache loaded config for 5 minutes

### 3. Rate Limiting

```python
class GitHubRateLimiter:
    """GitHub API rate limiting with token bucket algorithm."""
    
    async def acquire(self) -> None:
        """Wait for rate limit availability."""
        if self.remaining_requests <= 10:
            wait_time = self.reset_time - time.time()
            await asyncio.sleep(wait_time)
```

## Security Architecture

### 1. Credential Management

- **API Keys**: Stored in environment variables only
- **Database**: Connection strings with encrypted passwords
- **GitHub Access**: Least privilege tokens (read repos, write PRs)

### 2. Input Validation

- **GitHub Data**: Validate all API responses with Pydantic
- **LLM Responses**: Sanitize before applying to code
- **User Configuration**: Schema validation on load

### 3. Audit Logging

```python
async def log_action(
    action: str,
    entity_type: str, 
    entity_id: UUID,
    actor: str,
    details: Dict[str, Any]
) -> None:
    """Log all system actions for audit trail."""
    logger.info(
        "System action performed",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        actor=actor,
        details=details
    )
```

## Scalability Architecture

### 1. Horizontal Scaling

- **Workers**: Can run multiple instances of each worker type
- **Database**: Read replicas for query scaling
- **Queue**: Redis Cluster for queue scaling
- **Load Balancing**: Worker instances automatically balance via queue

### 2. Partitioning Strategy

- **Database**: Partition by repository_id for large datasets
- **Queues**: Separate queues by priority and worker type
- **Caching**: Distributed cache with consistent hashing

### 3. Resource Management

```python
# Configurable worker pool sizes
class WorkerConfig:
    max_concurrent_analyses: int = 10
    max_concurrent_fixes: int = 5
    max_concurrent_reviews: int = 3
    
# Memory-conscious batch processing
async def process_large_dataset(items: List[T], batch_size: int = 100) -> None:
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        await process_batch(batch)
```

## Monitoring and Observability

### 1. Metrics

- **Business Metrics**: Fix success rate, analysis accuracy, time to resolution
- **System Metrics**: Worker throughput, queue depth, API response times
- **Cost Metrics**: LLM API usage, infrastructure costs

### 2. Logging

- **Structured Logging**: JSON format with correlation IDs
- **Context Propagation**: Trace requests across workers
- **Error Tracking**: Detailed error context and stack traces

### 3. Health Checks

```python
async def health_check() -> HealthStatus:
    """Comprehensive system health check."""
    return HealthStatus(
        database=await check_database_connection(),
        queue=await check_queue_connection(),
        github_api=await check_github_api(),
        llm_providers=await check_llm_providers()
    )
```

---

This architecture provides a robust, scalable foundation for automated PR monitoring and fixing while maintaining flexibility for future enhancements and provider integrations.