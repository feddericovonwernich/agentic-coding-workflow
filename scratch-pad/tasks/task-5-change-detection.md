# Task 5: Create Change Detection Logic

## Objective
Implement sophisticated change detection that compares GitHub data with database state to identify new, updated, and state-changed PRs and check runs.

## Requirements
- Create `src/workers/monitor/change_detection.py`
- Implement ChangeDetector class
- Efficiently query database for current state
- Accurately detect all types of changes

## Implementation Details

### Core Interface
```python
class ChangeDetector(ABC):
    async def detect_pr_changes(self, repository_id: UUID, pr_data_list: List[PRData]) -> List[PRChangeRecord]
    async def detect_check_run_changes(self, pr_changes: List[PRChangeRecord], check_runs_by_pr: Dict[int, List[CheckRunData]]) -> List[CheckRunChangeRecord]
    async def create_changeset(self, repository_id: UUID, pr_changes: List[PRChangeRecord], check_changes: List[CheckRunChangeRecord]) -> ChangeSet
```

### Key Features
1. **PR Change Detection**:
   - Identify new PRs not in database
   - Detect PR metadata changes (title, labels, assignees)
   - Track PR state changes (opened → closed, etc.)
   - Identify SHA changes (new commits pushed)
   - Handle PR deletions from GitHub

2. **Check Run Change Detection**:
   - Identify new check runs
   - Detect status changes (queued → in_progress → completed)
   - Track conclusion changes (success → failure)
   - Handle check run timing updates
   - Detect check run deletions

3. **Database Querying**:
   - Efficient bulk queries for existing PRs
   - Fetch current check run states
   - Use repository's pull request repository pattern
   - Minimize database round trips

4. **Change Record Creation**:
   - Create detailed change records with old/new values
   - Track specific fields that changed
   - Maintain audit trail for changes
   - Support rollback if needed

## Dependencies
- `src/repositories/pull_request.py` (PullRequestRepository)
- `src/repositories/check_run.py` (CheckRunRepository)
- `src/workers/monitor/models.py` (PRChangeRecord, CheckRunChangeRecord, ChangeSet)
- Database models from `src/models/`

## Database Queries Required
- Get all PRs for a repository
- Get all check runs for a set of PRs
- Bulk fetch PR metadata
- Query latest state history records

## Edge Cases to Handle
- PR exists in database but not in GitHub (deleted)
- Check runs appear/disappear between polls
- PR state changes while processing
- Concurrent updates from multiple workers
- Handle timezone differences in timestamps

## Testing Requirements
- Test new PR detection
- Test various types of PR changes
- Test check run state transitions
- Mock database state for controlled testing
- Test edge cases and race conditions

## Acceptance Criteria
- [ ] Efficient database queries to get current state
- [ ] Accurate change detection for PRs (new, updated, state changes)
- [ ] Change detection for check runs (new, status/conclusion changes)
- [ ] Minimal false positives in change detection
- [ ] Proper handling of edge cases (deleted PRs, etc.)
- [ ] Unit tests with >90% coverage