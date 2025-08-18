# Agentic Coding Workflow - Requirements Specification

## 1. Executive Summary

An automated system for monitoring, analyzing, and fixing failed GitHub pull request checks, with intelligent PR review capabilities. The system uses LLM-powered analysis to categorize failures, apply automatic fixes where possible, and orchestrate multi-agent code reviews.

## 2. System Architecture

### 2.1 Core Components

- **PR Monitor Worker**: Periodically fetches and tracks PR states
- **Check Analyzer Worker**: Analyzes failed check logs using LLMs
- **Fix Applicator Worker**: Applies automated fixes using Claude Code SDK
- **Review Orchestrator Worker**: Manages multi-agent PR reviews
- **Notification Service**: Handles human escalations and notifications

### 2.2 Data Flow

```
GitHub PRs → Monitor → Database → Analyzer → Decision Router
                                                ├─→ Fix Worker → GitHub
                                                ├─→ Review Worker → GitHub/Database
                                                └─→ Notification → Human
```

## 3. Functional Requirements

### 3.1 PR Monitoring

#### 3.1.1 Repository Configuration
- **Repository URL**: GitHub repository identifier
- **Authentication**: GitHub PAT or App credentials
- **Skip Patterns**: 
  - PR title/label patterns to exclude from processing
  - Check name patterns to ignore
  - Author patterns (e.g., exclude dependabot)
- **Polling Interval**: Configurable frequency (default: 5 minutes)
- **Priority Rules**: Define high-priority PRs for faster processing

#### 3.1.2 PR State Management
- Track PR lifecycle: opened, updated, checks_running, checks_complete, merged, closed
- Store check history with timestamps
- Detect new check runs vs re-runs
- Track fix attempts and outcomes

### 3.2 Check Analysis

#### 3.2.1 Log Extraction
- Fetch check run logs from GitHub API
- Support for different CI providers (GitHub Actions, CircleCI, Jenkins)
- Parse structured and unstructured log formats

#### 3.2.2 LLM Analysis
- **Provider Configuration**: Support multiple LLM providers via LangChain
- **Analysis Output**:
  - Failure category (compilation, test, lint, deployment, infrastructure)
  - Root cause with supporting log evidence
  - Confidence score (0-100)
  - Fix strategy (if applicable)
  - Estimated complexity

#### 3.2.3 Decision Routing
- **Auto-fixable criteria**:
  - Confidence score > 80%
  - Category in allowed list (e.g., lint, simple test failures)
  - No security implications
  - Previous success rate > 70%
- **Human escalation triggers**:
  - Confidence score < 50%
  - Security-related failures
  - Infrastructure issues
  - Repeated failures (configurable threshold)

### 3.3 Automated Fixing

#### 3.3.1 Fix Application
- Use Claude Code SDK for code modifications
- Receive analysis context from analyzer
- Clone PR branch for modifications
- Apply fixes based on analysis strategy

#### 3.3.2 Validation
- Run affected tests locally before pushing
- Execute linters and formatters
- Verify build passes
- Check for breaking changes

#### 3.3.3 PR Update
- Commit with descriptive message referencing issue
- Push to PR branch
- Add comment explaining fix
- Update fix attempt counter

### 3.4 PR Review

#### 3.4.1 Review Triggers
- All checks passing
- Manual review request
- Significant code changes detected

#### 3.4.2 Multi-Agent Review
- **Reviewer Configuration**:
  ```yaml
  reviewers:
    - name: "Security Reviewer"
      provider: "openai"
      model: "gpt-4"
      prompt_template: "security_review.txt"
      focus_areas: ["auth", "crypto", "input_validation"]
    
    - name: "Performance Reviewer"
      provider: "anthropic"
      model: "claude-3"
      prompt_template: "performance_review.txt"
      focus_areas: ["algorithms", "database", "caching"]
  ```

#### 3.4.3 Review Output Format
```json
{
  "reviewer": "Security Reviewer",
  "decision": "APPROVE|REQUEST_CHANGES|COMMENT",
  "confidence": 85,
  "comments": [
    {
      "type": "line|file|general",
      "severity": "critical|major|minor|info",
      "file": "path/to/file.py",
      "line": 42,
      "message": "Potential SQL injection vulnerability",
      "suggestion": "Use parameterized queries"
    }
  ]
}
```

#### 3.4.4 Review Aggregation
- **Approval Logic**: Configurable (unanimous, majority, weighted)
- **Comment Placement**: 
  - Option 1: Direct GitHub PR comments
  - Option 2: Summary comment with detailed report
  - Option 3: Internal storage with dashboard view
- **Conflict Resolution**: Priority-based or human escalation

### 3.5 Notifications

#### 3.5.1 Notification Triggers
- Consecutive check failures exceeding threshold
- Low confidence analysis results
- Review conflicts requiring human input
- Successful automated fixes
- PR approval by all reviewers

#### 3.5.2 Provider Abstraction
```python
class NotificationProvider(ABC):
    @abstractmethod
    def send(self, message: Message, priority: Priority) -> bool:
        pass

class TelegramProvider(NotificationProvider):
    # Implementation
    
class SlackProvider(NotificationProvider):
    # Implementation
```

## 4. Non-Functional Requirements

### 4.1 Performance
- Process PR within 2 minutes of detection
- Support monitoring 100+ repositories
- Handle 1000+ concurrent PRs
- LLM response timeout: 30 seconds

### 4.2 Reliability
- 99.9% uptime for monitoring service
- Automatic retry with exponential backoff
- Dead letter queue for failed jobs
- Graceful degradation if LLM unavailable

### 4.3 Security
- Encrypted storage for API keys
- Least privilege GitHub permissions
- Audit logging for all actions
- No sensitive data in logs

### 4.4 Scalability
- Horizontal scaling for workers
- Queue-based job distribution
- Database partitioning by repository
- Configurable worker pool sizes

## 5. Database Schema

### 5.1 Core Tables

```sql
-- Pull Requests
CREATE TABLE pull_requests (
    id UUID PRIMARY KEY,
    repo_id VARCHAR(255),
    pr_number INTEGER,
    title TEXT,
    author VARCHAR(255),
    branch VARCHAR(255),
    state VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_checked TIMESTAMP
);

-- Check Runs
CREATE TABLE check_runs (
    id UUID PRIMARY KEY,
    pr_id UUID REFERENCES pull_requests(id),
    check_name VARCHAR(255),
    status VARCHAR(50),
    conclusion VARCHAR(50),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    log_url TEXT
);

-- Analysis Results
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY,
    check_run_id UUID REFERENCES check_runs(id),
    category VARCHAR(100),
    root_cause TEXT,
    confidence INTEGER,
    fix_strategy JSON,
    evidence JSON,
    created_at TIMESTAMP
);

-- Fix Attempts
CREATE TABLE fix_attempts (
    id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES analysis_results(id),
    status VARCHAR(50),
    commit_sha VARCHAR(40),
    error_message TEXT,
    created_at TIMESTAMP
);

-- Reviews
CREATE TABLE reviews (
    id UUID PRIMARY KEY,
    pr_id UUID REFERENCES pull_requests(id),
    reviewer_name VARCHAR(255),
    decision VARCHAR(50),
    confidence INTEGER,
    comments JSON,
    created_at TIMESTAMP
);
```

## 6. Configuration File Structure

```yaml
# config.yaml
system:
  polling_interval: 300  # seconds
  max_workers: 10
  retry_attempts: 3

repositories:
  - url: "https://github.com/org/repo"
    auth_token: "${GITHUB_TOKEN}"
    skip_patterns:
      pr_labels: ["wip", "draft"]
      check_names: ["codecov/*"]
      authors: ["dependabot[bot]"]
    failure_threshold: 3
    priority: "high"

llm_providers:
  default: "anthropic"
  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-opus"
      temperature: 0.3
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4"
      temperature: 0.3

notifications:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  
database:
  url: "${DATABASE_URL}"
  pool_size: 20
  
queue:
  type: "redis"
  url: "${REDIS_URL}"
  
claude_code:
  api_key: "${CLAUDE_CODE_API_KEY}"
  max_iterations: 5
  test_command: "npm test"
  lint_command: "npm run lint"
```

## 7. Open Questions & Decisions Needed

1. **Review Comment Strategy**: Should the system post reviews directly to GitHub or maintain internal storage?
   - **Recommendation**: Hybrid approach - summary on GitHub, detailed reports in dashboard

2. **Fix Rollback Strategy**: How to handle cases where automated fixes cause new failures?
   - **Recommendation**: Automatic revert after 2 failed attempts, then escalate

3. **Multi-Repository PRs**: How to handle PRs that affect multiple repositories?
   - **Recommendation**: Track as separate entities with correlation ID

4. **Cost Management**: How to control LLM API costs?
   - **Recommendation**: Implement daily/monthly budgets with automatic throttling

5. **Review Consensus**: What constitutes approval when reviewers disagree?
   - **Recommendation**: Configurable per repository (unanimous for critical, majority for others)

## 8. Implementation Phases

### Phase 1: Core Monitoring (Week 1-2)
- PR fetching and state tracking
- Basic database setup
- Configuration management

### Phase 2: Analysis Engine (Week 3-4)
- Log extraction
- LLM integration via LangChain
- Failure categorization

### Phase 3: Automated Fixing (Week 5-6)
- Claude Code SDK integration
- Fix validation pipeline
- PR update mechanism

### Phase 4: Review System (Week 7-8)
- Multi-agent review orchestration
- Comment aggregation
- Decision logic

### Phase 5: Production Readiness (Week 9-10)
- Notification system
- Monitoring and metrics
- Documentation and testing

## 9. Success Metrics

- **Automation Rate**: % of failed checks automatically fixed
- **Fix Success Rate**: % of fixes that resolve issues
- **Time to Resolution**: Average time from failure to fix
- **False Positive Rate**: % of incorrect fix attempts
- **Review Quality**: Human agreement rate with automated reviews
- **Cost Efficiency**: Cost per PR analyzed/fixed

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|---------|------------|
| LLM hallucinations causing bad fixes | High | Strict validation, conservative confidence thresholds |
| GitHub API rate limits | Medium | Implement caching, request batching |
| Infinite fix loops | Medium | Maximum retry limits, escalation rules |
| Security vulnerabilities in fixes | High | Security-focused reviewer, restricted permissions |
| High LLM costs | Medium | Budget controls, tiered processing |