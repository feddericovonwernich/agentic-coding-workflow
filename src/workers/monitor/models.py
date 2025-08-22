"""Processing data models for PR Monitor Worker."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.models.enums import CheckConclusion, CheckStatus, PRState


@dataclass
class ProcessingError:
    """Error that occurred during processing."""
    
    error_type: str
    message: str
    details: Optional[dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProcessingResult:
    """Result of processing a repository."""
    
    repository_id: uuid.UUID
    prs_processed: int
    new_prs: int
    updated_prs: int
    check_runs_updated: int
    errors: list[ProcessingError]
    processing_time: float
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.prs_processed
        if total == 0:
            return 1.0
        failed = len(self.errors)
        return max(0.0, (total - failed) / total)
    
    @property
    def has_errors(self) -> bool:
        """Check if processing had errors."""
        return len(self.errors) > 0


@dataclass
class PRData:
    """PR data from GitHub API."""
    
    number: int
    title: str
    author: str
    state: str
    draft: bool
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    url: str
    body: Optional[str]
    metadata: dict[str, Any]
    updated_at: datetime
    
    @property
    def pr_state(self) -> PRState:
        """Convert GitHub state to internal enum."""
        state_map = {
            "open": PRState.OPENED,
            "closed": PRState.CLOSED,
        }
        return state_map.get(self.state.lower(), PRState.OPENED)


@dataclass
class CheckRunData:
    """Check run data from GitHub API."""
    
    id: int
    name: str
    status: str
    conclusion: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    details_url: Optional[str]
    output_title: Optional[str]
    output_summary: Optional[str]
    external_id: Optional[str]
    
    @property
    def check_status(self) -> CheckStatus:
        """Convert GitHub status to internal enum."""
        status_map = {
            "queued": CheckStatus.QUEUED,
            "in_progress": CheckStatus.IN_PROGRESS,
            "completed": CheckStatus.COMPLETED,
        }
        return status_map.get(self.status.lower(), CheckStatus.QUEUED)
    
    @property
    def check_conclusion(self) -> Optional[CheckConclusion]:
        """Convert GitHub conclusion to internal enum."""
        if not self.conclusion:
            return None
            
        conclusion_map = {
            "success": CheckConclusion.SUCCESS,
            "failure": CheckConclusion.FAILURE,
            "neutral": CheckConclusion.NEUTRAL,
            "cancelled": CheckConclusion.CANCELLED,
            "timed_out": CheckConclusion.TIMED_OUT,
            "action_required": CheckConclusion.ACTION_REQUIRED,
        }
        return conclusion_map.get(self.conclusion.lower())


@dataclass
class StateChange:
    """Represents a change in PR or check run state."""
    
    change_type: str  # 'pr_state', 'pr_metadata', 'check_run'
    entity_id: uuid.UUID
    old_value: Any
    new_value: Any
    metadata: Optional[dict[str, Any]] = None
    
    
@dataclass
class ChangeSet:
    """Collection of changes detected during processing."""
    
    new_prs: list['PullRequest']
    updated_prs: list['PullRequest'] 
    new_check_runs: list['CheckRun']
    updated_check_runs: list['CheckRun']
    state_changes: list[StateChange]
    
    def __init__(self):
        """Initialize empty change set."""
        self.new_prs = []
        self.updated_prs = []
        self.new_check_runs = []
        self.updated_check_runs = []
        self.state_changes = []
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.new_prs 
            or self.updated_prs 
            or self.new_check_runs 
            or self.updated_check_runs 
            or self.state_changes
        )
    
    @property
    def total_changes(self) -> int:
        """Get total number of changes."""
        return (
            len(self.new_prs) +
            len(self.updated_prs) +
            len(self.new_check_runs) +
            len(self.updated_check_runs) +
            len(self.state_changes)
        )


@dataclass
class RepositoryConfig:
    """Configuration for processing a repository."""
    
    id: uuid.UUID
    url: str
    owner: str
    name: str
    auth_token: str
    polling_interval: int = 300  # seconds
    check_interval: int = 60     # seconds
    enabled: bool = True
    
    @classmethod
    def from_repo_model(cls, repo: 'Repository', auth_token: str) -> 'RepositoryConfig':
        """Create config from repository model."""
        # Extract owner/name from URL
        # Assumes format: https://github.com/owner/repo
        url_parts = repo.url.rstrip('/').split('/')
        owner = url_parts[-2]
        name = url_parts[-1]
        
        return cls(
            id=repo.id,
            url=repo.url,
            owner=owner,
            name=name,
            auth_token=auth_token,
            enabled=repo.is_active
        )