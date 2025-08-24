# Task 2: Create Core Processor Class

## Objective
Implement the main PRProcessor class that orchestrates the entire processing flow for discovering and processing pull requests from GitHub repositories.

## Requirements
- Create `src/workers/monitor/processor.py`
- Implement PRProcessor class with async processing methods
- Support concurrent processing of multiple repositories
- Provide comprehensive error handling and result collection

## Implementation Details

### Core Interface
```python
class PRProcessor(ABC):
    async def process_repository(self, repository: Repository) -> ProcessingResult
    async def process_repositories(self, repositories: List[Repository]) -> BatchProcessingResult
```

### Key Features
1. **Repository Processing**:
   - Process single repository with all PRs and check runs
   - Coordinate discovery, change detection, and synchronization
   - Collect metrics and timing information

2. **Batch Processing**:
   - Process multiple repositories concurrently
   - Use semaphore to limit concurrent operations
   - Aggregate results from all repositories

3. **Error Handling**:
   - Isolate errors per repository
   - Continue processing other repositories on failure
   - Comprehensive error logging and reporting

4. **Performance**:
   - Process 100 repositories with 1000 PRs each within 5 minutes
   - Efficient resource management
   - Proper cleanup of connections

## Dependencies
- `src/workers/monitor/models.py` (ProcessingResult, BatchProcessingResult)
- `src/github/client.py` (GitHubClient)
- `src/repositories/` (Repository patterns)
- Discovery, change detection, and synchronization services (to be created)

## Testing Requirements
- Unit tests with mocked dependencies
- Test concurrent processing behavior
- Test error isolation and recovery
- Verify metrics collection

## Acceptance Criteria
- [ ] PRProcessor class with async processing methods
- [ ] Repository-level processing with error isolation
- [ ] Concurrent processing of multiple repositories
- [ ] Comprehensive result collection and metrics
- [ ] Proper error handling and logging
- [ ] Unit tests with >90% coverage