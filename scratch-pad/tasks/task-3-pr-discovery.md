# Task 3: Implement PR Discovery Service

## Objective
Create service to discover pull requests from GitHub repositories with intelligent caching and efficient API usage.

## Requirements
- Create `src/workers/monitor/discovery.py`
- Implement PRDiscoveryService class
- Support incremental fetching using timestamps
- Implement ETag-based caching for API efficiency

## Implementation Details

### Core Interface
```python
class PRDiscoveryService(ABC):
    async def discover_prs(self, repository: Repository, since: Optional[datetime] = None) -> List[PRData]
    async def discover_check_runs(self, repository: Repository, pr_data: PRData) -> List[CheckRunData]
```

### Key Features
1. **PR Discovery**:
   - Fetch all PRs for a repository from GitHub
   - Support filtering by state (open, closed, merged)
   - Use `since` parameter for incremental updates
   - Handle pagination for repositories with many PRs

2. **Metadata Extraction**:
   - Extract core PR data (number, title, author, branches, SHAs)
   - Process labels, milestones, assignees
   - Parse PR body and description
   - Handle draft status and mergeable state

3. **Caching Strategy**:
   - Use ETags for conditional requests
   - Cache PR metadata to minimize API calls
   - Track last fetch time per repository
   - Implement cache invalidation logic

4. **Performance Optimization**:
   - Batch API requests where possible
   - Use GitHub's GraphQL API for efficient data fetching
   - Implement request coalescing for duplicate requests
   - Respect rate limits via existing client

## Dependencies
- `src/github/client.py` (GitHubClient)
- `src/workers/monitor/models.py` (PRData, CheckRunData)
- `src/models/repository.py` (Repository model)

## API Endpoints to Use
- `GET /repos/{owner}/{repo}/pulls` - List pull requests
- `GET /repos/{owner}/{repo}/pulls/{number}` - Get single PR details
- `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` - Get check runs

## Testing Requirements
- Mock GitHub API responses for various scenarios
- Test pagination handling with large PR lists
- Verify correct metadata extraction
- Test incremental update logic
- Test ETag caching behavior

## Acceptance Criteria
- [ ] Efficient PR discovery with since filters
- [ ] Pagination handling for repositories with many PRs
- [ ] ETag-based conditional requests for caching
- [ ] Proper GitHub API error handling
- [ ] Rate limit awareness and backoff
- [ ] Unit tests with >90% coverage