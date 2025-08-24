# Task 4: Implement Check Run Discovery

## Objective
Extend the discovery service to fetch check runs for pull requests with concurrent processing and proper error handling.

## Requirements
- Add check run discovery to `src/workers/monitor/discovery.py`
- Support concurrent fetching for multiple PRs
- Extract check run metadata and failure information
- Handle PRs without check runs gracefully

## Implementation Details

### Core Functionality
```python
async def discover_check_runs(self, repository: Repository, pr_data: PRData) -> List[CheckRunData]
async def discover_check_runs_batch(self, repository: Repository, pr_data_list: List[PRData]) -> Dict[int, List[CheckRunData]]
```

### Key Features
1. **Check Run Fetching**:
   - Get all check runs for each PR's head SHA
   - Track check run status (queued, in_progress, completed)
   - Extract check run conclusions (success, failure, cancelled)
   - Handle check suites and individual checks

2. **Metadata Processing**:
   - Parse check run metadata (logs URL, details URL, timing)
   - Track external check run IDs for correlation
   - Handle check re-runs and updates
   - Extract failure information when available

3. **Concurrent Processing**:
   - Fetch check runs for multiple PRs concurrently
   - Use asyncio.gather with error handling
   - Limit concurrent requests to respect rate limits
   - Aggregate results efficiently

4. **Error Handling**:
   - Continue processing other PRs if one fails
   - Log errors with context (PR number, repository)
   - Handle PRs with no check runs gracefully
   - Retry transient failures with backoff

## Dependencies
- Existing PRDiscoveryService from Task 3
- `src/github/client.py` (GitHubClient)
- `src/workers/monitor/models.py` (CheckRunData)

## API Endpoints to Use
- `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` - List check runs for a commit
- `GET /repos/{owner}/{repo}/check-runs/{check_run_id}` - Get single check run details
- `GET /repos/{owner}/{repo}/commits/{ref}/check-suites` - List check suites

## Performance Considerations
- Process check runs for up to 1000 PRs per repository
- Use semaphore to limit concurrent API requests
- Batch requests where GitHub API supports it
- Cache check run data when appropriate

## Testing Requirements
- Test concurrent check run discovery
- Mock various check run states and conclusions
- Test error handling for failed API calls
- Verify proper aggregation of results
- Test PRs without any check runs

## Acceptance Criteria
- [ ] Concurrent check run discovery for multiple PRs
- [ ] Proper handling of PRs without check runs
- [ ] Check run metadata extraction and parsing
- [ ] Error handling for individual check run failures
- [ ] Performance optimization for large PR sets
- [ ] Unit tests with >90% coverage