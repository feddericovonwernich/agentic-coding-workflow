# Implementation Plan: PR Monitor Worker Core Logic (Issue #48)

## Problem Statement

Implement the core logic for the PR Monitor Worker that discovers pull requests from GitHub repositories, extracts metadata, tracks check runs, and detects state changes. The system must efficiently handle 100 repositories with 1000 PRs each within a 5-minute window while minimizing GitHub API calls through intelligent caching and incremental updates.

## Architectural Design

### Overview

The PR Monitor Worker follows a layered architecture with clear separation of concerns:
1. **Discovery Layer**: Fetches PRs and check runs from GitHub with intelligent caching
2. **Change Detection Layer**: Compares GitHub data with database state to identify changes
3. **Synchronization Layer**: Updates database with detected changes in transactions
4. **Processing Coordination**: Orchestrates the entire flow with error handling and metrics

### Components Affected

- **New Component - src/workers/monitor/processor.py**: Main orchestration class (PRProcessor)
- **New Component - src/workers/monitor/discovery.py**: GitHub data discovery logic
- **New Component - src/workers/monitor/change_detection.py**: State change detection logic  
- **New Component - src/workers/monitor/synchronization.py**: Database synchronization logic
- **Existing Component - src/workers/monitor/models.py**: Already exists with data models
- **Existing Component - src/github/client.py**: Used for GitHub API calls
- **Existing Component - src/repositories/**: Used for database operations

### New Interfaces/Contracts

```python
# Core processor interface
class PRProcessor(ABC):
    @abstractmethod
    async def process_repository(self, repository: Repository) -> ProcessingResult:
        """Process a single repository and return results."""
        pass
    
    @abstractmethod
    async def process_repositories(self, repositories: List[Repository]) -> BatchProcessingResult:
        """Process multiple repositories concurrently."""
        pass

# Discovery service interface
class PRDiscoveryService(ABC):
    @abstractmethod
    async def discover_prs(self, repository: Repository, since: Optional[datetime] = None) -> List[PRData]:
        """Discover PRs from GitHub for a repository."""
        pass
    
    @abstractmethod
    async def discover_check_runs(self, repository: Repository, pr_data: PRData) -> List[CheckRunData]:
        """Discover check runs for a specific PR."""
        pass

# Change detection interface  
class ChangeDetector(ABC):
    @abstractmethod
    async def detect_pr_changes(self, repository_id: UUID, pr_data_list: List[PRData]) -> List[PRChangeRecord]:
        """Detect changes in PRs compared to database state."""
        pass
        
    @abstractmethod
    async def detect_check_run_changes(self, pr_changes: List[PRChangeRecord], check_runs_by_pr: Dict[int, List[CheckRunData]]) -> List[CheckRunChangeRecord]:
        """Detect changes in check runs."""
        pass

# Synchronization interface
class DataSynchronizer(ABC):
    @abstractmethod
    async def synchronize_changes(self, repository_id: UUID, changeset: ChangeSet) -> int:
        """Synchronize detected changes to database."""
        pass
```

### Data Flow

1. **Repository Processing**: PRProcessor receives list of repositories to monitor
2. **PR Discovery**: For each repository, discover PRs using GitHub API with since filters
3. **Check Run Discovery**: For each PR, discover check runs concurrently
4. **Change Detection**: Compare discovered data with database state to identify changes
5. **Synchronization**: Update database with changes in transactions
6. **Results Collection**: Aggregate processing results and metrics

## Technical Considerations

### Design Decisions

- **Incremental Processing**: Use `updated_at` timestamps and etags to minimize API calls
- **Concurrent Processing**: Process repositories in parallel, PRs within repository sequentially
- **Transactional Synchronization**: Use database transactions to ensure consistency
- **Intelligent Caching**: Cache PR metadata and use conditional requests to GitHub
- **Error Isolation**: Continue processing other repositories if one fails
- **Rate Limit Awareness**: Leverage existing GitHub client rate limiting

### Error Handling

- **Repository Level Errors**: Log error, continue with other repositories
- **PR Level Errors**: Log error, continue with other PRs in same repository  
- **Database Errors**: Retry with exponential backoff, rollback on failure
- **GitHub API Errors**: Handled by existing client with circuit breaker
- **Partial Failure Recovery**: Track which repositories completed successfully

### Testing Strategy

- **Unit Tests**: Test each component in isolation with mocks
  - Discovery service with mocked GitHub client
  - Change detector with controlled database state
  - Synchronizer with transaction validation
- **Integration Tests**: Test component interactions
  - End-to-end repository processing
  - Database transaction behavior
  - GitHub client integration

### Security Considerations

- **API Token Management**: Use existing GitHub auth provider
- **Rate Limit Protection**: Respect GitHub API limits via existing client
- **Input Validation**: Validate repository URLs and data from GitHub
- **SQL Injection Prevention**: Use parameterized queries via repositories

## Implementation Steps

### Task 1: Create Core Processor Class
**Complexity:** Medium
**Can Parallelize:** No
**Description:** Implement the main PRProcessor class that orchestrates the entire processing flow
**Acceptance Criteria:**
- [ ] PRProcessor class with async processing methods
- [ ] Repository-level processing with error isolation
- [ ] Concurrent processing of multiple repositories
- [ ] Comprehensive result collection and metrics
- [ ] Proper error handling and logging

### Task 2: Implement PR Discovery Service
**Complexity:** Medium  
**Can Parallelize:** Yes (can work on this while Task 1 is in progress)
**Description:** Create service to discover PRs from GitHub with intelligent caching
**Acceptance Criteria:**
- [ ] Efficient PR discovery with since filters
- [ ] Pagination handling for repositories with many PRs
- [ ] ETag-based conditional requests for caching
- [ ] Proper GitHub API error handling
- [ ] Rate limit awareness and backoff

### Task 3: Implement Check Run Discovery
**Complexity:** Medium
**Can Parallelize:** Yes (depends on Task 2 interface)
**Description:** Create service to discover check runs for PRs with concurrent processing  
**Acceptance Criteria:**
- [ ] Concurrent check run discovery for multiple PRs
- [ ] Proper handling of PRs without check runs
- [ ] Check run metadata extraction and parsing
- [ ] Error handling for individual check run failures
- [ ] Performance optimization for large PR sets

### Task 4: Create Change Detection Logic
**Complexity:** High
**Can Parallelize:** Yes (can work on interface while Tasks 2-3 complete)
**Description:** Implement sophisticated change detection comparing GitHub data with database
**Acceptance Criteria:**
- [ ] Efficient database queries to get current state
- [ ] Accurate change detection for PRs (new, updated, state changes)
- [ ] Change detection for check runs (new, status/conclusion changes)
- [ ] Minimal false positives in change detection
- [ ] Proper handling of edge cases (deleted PRs, etc.)

### Task 5: Implement Database Synchronization
**Complexity:** High
**Can Parallelize:** Yes (can work on interface while Task 4 progresses)
**Description:** Create transactional synchronization logic for database updates
**Acceptance Criteria:**
- [ ] Transactional updates for consistency
- [ ] Efficient bulk operations for large change sets
- [ ] Proper foreign key handling and constraints
- [ ] Rollback on errors with proper cleanup
- [ ] Performance optimization for large repositories

### Task 6: Integration and Optimization
**Complexity:** Medium
**Can Parallelize:** No (requires all previous tasks)
**Description:** Integrate all components and optimize for performance requirements
**Acceptance Criteria:**
- [ ] End-to-end processing works correctly
- [ ] Meets performance requirements (100 repos, 1000 PRs each, 5-minute window)
- [ ] Proper resource cleanup and connection management
- [ ] Comprehensive logging and monitoring
- [ ] Memory usage optimization

### Task 7: Comprehensive Testing
**Complexity:** Medium
**Can Parallelize:** Yes (can start unit tests as components are completed)
**Description:** Create comprehensive test suite covering all components
**Acceptance Criteria:**
- [ ] Unit tests for all major components with >90% coverage
- [ ] Integration tests for database operations
- [ ] Performance tests validating scaling requirements
- [ ] Error scenario testing and recovery
- [ ] Load testing with realistic data volumes

## Dependencies

### External Dependencies
- Existing GitHub client (`src/github/client.py`)
- Existing repository patterns (`src/repositories/`)
- Database models (`src/models/`)
- AsyncIO for concurrent processing
- SQLAlchemy for database transactions

### Internal Dependencies Between Tasks
- Task 2 (PR Discovery) must complete interface before Tasks 4-5 can fully implement
- Task 3 (Check Run Discovery) depends on Task 2 for PR data structure
- Task 4 (Change Detection) depends on Tasks 2-3 for data structures
- Task 5 (Synchronization) can work on interface in parallel with Task 4
- Task 6 (Integration) requires Tasks 1-5 completion
- Task 7 (Testing) can begin unit tests as individual tasks complete

## Risk Assessment

### Risk 1: GitHub API Rate Limits
**Mitigation Strategy:** 
- Use existing rate limit manager and circuit breaker
- Implement aggressive caching with ETags and conditional requests
- Process repositories in smaller batches if needed
- Add configurable delays between repository processing

### Risk 2: Database Performance with Large Data Sets
**Mitigation Strategy:**
- Use bulk operations for inserts/updates
- Implement proper database indexes
- Use connection pooling efficiently
- Consider pagination for very large repositories

### Risk 3: Memory Usage with Concurrent Processing
**Mitigation Strategy:**
- Process repositories in bounded batches
- Stream large result sets instead of loading all in memory
- Use proper async/await patterns to prevent blocking
- Implement resource cleanup in finally blocks

### Risk 4: Partial Failures Leading to Inconsistent State
**Mitigation Strategy:**
- Use database transactions with proper rollback
- Implement retry logic with exponential backoff
- Track processing state to allow resume from failures
- Add reconciliation checks for data consistency

### Risk 5: Complex Change Detection Logic Bugs
**Mitigation Strategy:**
- Implement comprehensive unit tests with edge cases
- Use property-based testing for change detection logic
- Add extensive logging for debugging
- Implement dry-run mode for testing without database updates