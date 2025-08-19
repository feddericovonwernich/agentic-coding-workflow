# Database Schema Documentation

## Overview

The agentic coding workflow system uses a PostgreSQL database with a comprehensive schema designed to support automated monitoring, analysis, and fixing of failed GitHub pull request checks. The schema is organized around core entities that track the lifecycle of pull requests and their associated check runs.

## Core Tables

### repositories

**Purpose**: Stores repository configuration and monitoring status.

```sql
CREATE TABLE repositories (
    id UUID PRIMARY KEY,
    url VARCHAR(500) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    status repository_status NOT NULL DEFAULT 'active',
    failure_count INTEGER NOT NULL DEFAULT 0,
    config_override JSONB,
    last_polled_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields**:
- `url`: Unique GitHub repository URL
- `status`: Enum ('active', 'suspended', 'error') indicating repository monitoring status
- `failure_count`: Counter for consecutive monitoring failures
- `config_override`: Repository-specific configuration overrides
- `last_polled_at`: Timestamp of last successful poll

### pull_requests

**Purpose**: Central table tracking all monitored pull requests and their metadata.

```sql
CREATE TABLE pull_requests (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    pr_number INTEGER NOT NULL,
    title VARCHAR(500) NOT NULL,
    author VARCHAR(100) NOT NULL,
    state pr_state NOT NULL,
    draft BOOLEAN NOT NULL DEFAULT false,
    base_branch VARCHAR(200) NOT NULL,
    head_branch VARCHAR(200) NOT NULL,
    base_sha VARCHAR(40) NOT NULL,
    head_sha VARCHAR(40) NOT NULL,
    url VARCHAR(500) NOT NULL,
    metadata JSONB,
    last_checked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repository_id, pr_number)
);
```

**Key Fields**:
- `state`: Enum ('opened', 'closed', 'merged') tracking PR lifecycle
- `metadata`: Flexible JSONB field for additional PR data
- `last_checked_at`: Timestamp of last check run analysis

**Relationships**:
- **Many-to-One** with `repositories` (repository_id → repositories.id)
- **One-to-Many** with `check_runs` (id ← check_runs.pr_id)
- **One-to-Many** with `pr_state_history` (id ← pr_state_history.pr_id)

### check_runs

**Purpose**: Tracks individual check runs associated with pull requests.

```sql
CREATE TABLE check_runs (
    id UUID PRIMARY KEY,
    pr_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    external_id VARCHAR(100) NOT NULL UNIQUE,
    check_name VARCHAR(200) NOT NULL,
    check_suite_id VARCHAR(100),
    status check_status NOT NULL,
    conclusion check_conclusion,
    logs_url VARCHAR(500),
    details_url VARCHAR(500),
    metadata JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields**:
- `external_id`: GitHub's unique identifier for the check run
- `status`: Enum ('queued', 'in_progress', 'completed', 'cancelled')
- `conclusion`: Enum ('success', 'failure', 'neutral', 'cancelled', 'timed_out', 'action_required', 'stale', 'skipped')

**Relationships**:
- **Many-to-One** with `pull_requests` (pr_id → pull_requests.id)
- **One-to-Many** with `analysis_results` (id ← analysis_results.check_run_id)

### pr_state_history

**Purpose**: Audit table tracking all state changes for pull requests.

```sql
CREATE TABLE pr_state_history (
    id UUID PRIMARY KEY,
    pr_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    old_state pr_state,
    new_state pr_state NOT NULL,
    trigger_event trigger_event NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields**:
- `trigger_event`: Enum ('opened', 'synchronize', 'closed', 'reopened', 'edited', 'manual_check')
- `metadata`: Additional context about the state change

**Relationships**:
- **Many-to-One** with `pull_requests` (pr_id → pull_requests.id)

## Future-Ready Tables (Phase 2)

### analysis_results

**Purpose**: Stores LLM analysis results for failed check runs.

```sql
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY,
    check_run_id UUID NOT NULL REFERENCES check_runs(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    confidence_score FLOAT NOT NULL,
    root_cause TEXT,
    recommended_action VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships**:
- **Many-to-One** with `check_runs` (check_run_id → check_runs.id)
- **One-to-Many** with `fix_attempts` (id ← fix_attempts.analysis_result_id)

### fix_attempts

**Purpose**: Tracks automated fix attempts and their outcomes.

```sql
CREATE TABLE fix_attempts (
    id UUID PRIMARY KEY,
    analysis_result_id UUID NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    fix_strategy VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    success BOOLEAN,
    error_message TEXT,
    metadata JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships**:
- **Many-to-One** with `analysis_results` (analysis_result_id → analysis_results.id)

### reviews

**Purpose**: Stores multi-agent PR review information.

```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY,
    pr_id UUID NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    reviewer_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    decision VARCHAR(50),
    feedback TEXT,
    metadata JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships**:
- **Many-to-One** with `pull_requests` (pr_id → pull_requests.id)

## ENUM Types

### pr_state
- `opened`: PR is open and active
- `closed`: PR was closed without merging
- `merged`: PR was successfully merged

### check_status
- `queued`: Check run is queued for execution
- `in_progress`: Check run is currently executing
- `completed`: Check run has finished
- `cancelled`: Check run was cancelled

### check_conclusion
- `success`: Check run passed
- `failure`: Check run failed
- `neutral`: Check run completed neutrally
- `cancelled`: Check run was cancelled
- `timed_out`: Check run exceeded time limit
- `action_required`: Check run requires manual action
- `stale`: Check run is stale
- `skipped`: Check run was skipped

### repository_status
- `active`: Repository is actively monitored
- `suspended`: Repository monitoring is suspended
- `error`: Repository is in error state

### trigger_event
- `opened`: PR was opened
- `synchronize`: PR was updated with new commits
- `closed`: PR was closed
- `reopened`: PR was reopened
- `edited`: PR was edited
- `manual_check`: Manual check was triggered

## Indexes

### Performance Indexes

**Repository Indexes**:
- `idx_repositories_status` ON repositories(status)
- `idx_repositories_last_polled` ON repositories(last_polled_at)

**Pull Request Indexes**:
- `idx_pull_requests_repository_id` ON pull_requests(repository_id)
- `idx_pull_requests_state` ON pull_requests(state)
- `idx_pull_requests_last_checked` ON pull_requests(last_checked_at)
- `idx_pull_requests_created_at` ON pull_requests(created_at)
- `idx_pull_requests_repo_state` ON pull_requests(repository_id, state)

**Check Run Indexes**:
- `idx_check_runs_pr_id` ON check_runs(pr_id)
- `idx_check_runs_status` ON check_runs(status)
- `idx_check_runs_conclusion` ON check_runs(conclusion)
- `idx_check_runs_check_name` ON check_runs(check_name)
- `idx_check_runs_created_at` ON check_runs(created_at)
- `idx_check_runs_pr_status` ON check_runs(pr_id, status)
- `idx_check_runs_pr_conclusion` ON check_runs(pr_id, conclusion)

**Audit Indexes**:
- `idx_pr_state_history_pr_id` ON pr_state_history(pr_id)
- `idx_pr_state_history_created_at` ON pr_state_history(created_at)
- `idx_pr_state_history_trigger_event` ON pr_state_history(trigger_event)
- `idx_pr_state_history_pr_created` ON pr_state_history(pr_id, created_at)

## Database Triggers

### Automatic Timestamp Updates

**Function**: `update_updated_at_column()`
- Automatically updates `updated_at` column on row modifications

**Triggers**:
- `update_repositories_updated_at` ON repositories
- `update_pull_requests_updated_at` ON pull_requests  
- `update_check_runs_updated_at` ON check_runs

### Audit Logging

**Function**: `log_pr_state_change()`
- Automatically logs PR state changes to `pr_state_history`
- Captures both INSERT (new PR) and UPDATE (state change) events
- Includes metadata about the change context

**Trigger**:
- `log_pull_request_state_changes` ON pull_requests

## Data Flow

```
GitHub → Monitor → Queue → Analyzer → Router → Fix/Review/Notify → GitHub
                     ↓        ↓         ↓
                  Database (PostgreSQL)
```

### Typical Data Flow:

1. **Repository Registration**: Repository added to `repositories` table
2. **PR Discovery**: New PRs added to `pull_requests` table, triggers audit log
3. **Check Run Tracking**: Check runs added to `check_runs` table as they execute
4. **State Changes**: PR state changes logged automatically via triggers
5. **Analysis** (Phase 2): Failed checks analyzed, results stored in `analysis_results`
6. **Fix Attempts** (Phase 2): Automated fixes tracked in `fix_attempts`
7. **Reviews** (Phase 2): Multi-agent reviews stored in `reviews`

## Query Patterns

### Common Query Examples

**Find active repositories due for polling**:
```sql
SELECT * FROM repositories 
WHERE status = 'active' 
AND (last_polled_at IS NULL OR last_polled_at < NOW() - INTERVAL '5 minutes')
ORDER BY last_polled_at ASC NULLS FIRST;
```

**Get open PRs with failed checks**:
```sql
SELECT pr.*, cr.check_name, cr.conclusion
FROM pull_requests pr
JOIN check_runs cr ON pr.id = cr.pr_id
WHERE pr.state = 'opened' 
AND cr.conclusion = 'failure'
AND cr.status = 'completed';
```

**Track PR state history**:
```sql
SELECT psh.*, pr.title
FROM pr_state_history psh
JOIN pull_requests pr ON psh.pr_id = pr.id
WHERE pr.repository_id = ?
ORDER BY psh.created_at DESC;
```

## Performance Considerations

### Query Performance Targets:
- PR lookup queries: < 10ms
- Check run queries: < 50ms
- Repository polling queries: < 100ms

### Scaling Considerations:
- Designed to handle 10,000+ PRs
- Partition `pr_state_history` by date for large volumes
- Archive old check runs and analysis results
- Use connection pooling for high concurrency

### Monitoring:
- Track index usage and query performance
- Monitor trigger execution times
- Alert on foreign key constraint violations

## Migration Strategy

The schema is managed through Alembic migrations with:
- Idempotent ENUM creation
- Automatic rollback capability
- Comprehensive test coverage
- Cross-platform PostgreSQL compatibility (versions 12-15)

## Security Considerations

- All tables use UUID primary keys to prevent enumeration attacks
- Foreign key constraints ensure referential integrity
- JSONB fields validated at application layer
- Database user has minimal required permissions
- No sensitive data stored in database (tokens stored in environment)