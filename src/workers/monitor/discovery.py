"""PR discovery logic for fetching pull requests and check runs from GitHub."""

import logging
from datetime import datetime
from typing import Any, Optional

from src.github import GitHubClient, PersonalAccessTokenAuth
from src.github.exceptions import GitHubError, GitHubNotFoundError

from .models import CheckRunData, PRData, ProcessingError, RepositoryConfig

logger = logging.getLogger(__name__)


class PRDiscoveryEngine:
    """Engine for discovering pull requests and check runs from GitHub."""
    
    def __init__(self, github_client: GitHubClient):
        """Initialize discovery engine.
        
        Args:
            github_client: GitHub API client
        """
        self.github_client = github_client
    
    async def discover_prs(
        self, 
        repo_config: RepositoryConfig,
        states: Optional[list[str]] = None,
        since: Optional[datetime] = None
    ) -> tuple[list[PRData], list[ProcessingError]]:
        """Discover pull requests from GitHub repository.
        
        Args:
            repo_config: Repository configuration
            states: PR states to fetch (default: ['open'])
            since: Only fetch PRs updated since this time
            
        Returns:
            Tuple of (PR data list, errors list)
        """
        if states is None:
            states = ['open']
        
        prs: list[PRData] = []
        errors: list[ProcessingError] = []
        
        try:
            logger.info(f"Discovering PRs for {repo_config.owner}/{repo_config.name}")
            
            for state in states:
                try:
                    async for pr_batch in self.github_client.list_pulls(
                        repo_config.owner, 
                        repo_config.name, 
                        state=state,
                        per_page=100
                    ):
                        for pr_data in pr_batch:
                            try:
                                pr = self._parse_pr_data(pr_data)
                                
                                # Filter by since time if provided
                                if since and pr.updated_at < since:
                                    continue
                                    
                                prs.append(pr)
                                
                            except Exception as e:
                                error = ProcessingError(
                                    error_type="pr_parsing_error",
                                    message=f"Failed to parse PR #{pr_data.get('number', 'unknown')}: {e}",
                                    details={"pr_data": pr_data}
                                )
                                errors.append(error)
                                logger.warning(f"Failed to parse PR data: {e}")
                
                except GitHubNotFoundError:
                    error = ProcessingError(
                        error_type="repository_not_found",
                        message=f"Repository {repo_config.owner}/{repo_config.name} not found or not accessible",
                        details={"state": state}
                    )
                    errors.append(error)
                    logger.error(f"Repository not found: {repo_config.owner}/{repo_config.name}")
                    break  # No point trying other states
                    
                except GitHubError as e:
                    error = ProcessingError(
                        error_type="github_api_error",
                        message=f"GitHub API error for state '{state}': {e}",
                        details={"state": state, "error_code": getattr(e, 'status_code', None)}
                    )
                    errors.append(error)
                    logger.error(f"GitHub API error: {e}")
                    
        except Exception as e:
            error = ProcessingError(
                error_type="discovery_error",
                message=f"Unexpected error during PR discovery: {e}",
                details={"repository": f"{repo_config.owner}/{repo_config.name}"}
            )
            errors.append(error)
            logger.error(f"Unexpected discovery error: {e}")
        
        logger.info(f"Discovered {len(prs)} PRs with {len(errors)} errors")
        return prs, errors
    
    async def discover_check_runs(
        self,
        repo_config: RepositoryConfig,
        commit_sha: str
    ) -> tuple[list[CheckRunData], list[ProcessingError]]:
        """Discover check runs for a specific commit.
        
        Args:
            repo_config: Repository configuration
            commit_sha: Git commit SHA to get check runs for
            
        Returns:
            Tuple of (check run data list, errors list)
        """
        check_runs: list[CheckRunData] = []
        errors: list[ProcessingError] = []
        
        try:
            logger.debug(f"Discovering check runs for {repo_config.owner}/{repo_config.name}@{commit_sha}")
            
            async for check_batch in self.github_client.list_check_runs(
                repo_config.owner,
                repo_config.name,
                commit_sha,
                per_page=100
            ):
                # The API returns {"check_runs": [...]} format
                check_runs_data = check_batch.get('check_runs', [])
                
                for check_data in check_runs_data:
                    try:
                        check_run = self._parse_check_run_data(check_data)
                        check_runs.append(check_run)
                        
                    except Exception as e:
                        error = ProcessingError(
                            error_type="check_run_parsing_error",
                            message=f"Failed to parse check run #{check_data.get('id', 'unknown')}: {e}",
                            details={"check_data": check_data}
                        )
                        errors.append(error)
                        logger.warning(f"Failed to parse check run data: {e}")
        
        except GitHubNotFoundError:
            error = ProcessingError(
                error_type="commit_not_found",
                message=f"Commit {commit_sha} not found in {repo_config.owner}/{repo_config.name}",
                details={"commit_sha": commit_sha}
            )
            errors.append(error)
            logger.warning(f"Commit not found: {commit_sha}")
            
        except GitHubError as e:
            error = ProcessingError(
                error_type="github_api_error",
                message=f"GitHub API error for check runs: {e}",
                details={"commit_sha": commit_sha, "error_code": getattr(e, 'status_code', None)}
            )
            errors.append(error)
            logger.error(f"GitHub API error: {e}")
            
        except Exception as e:
            error = ProcessingError(
                error_type="check_run_discovery_error",
                message=f"Unexpected error during check run discovery: {e}",
                details={
                    "repository": f"{repo_config.owner}/{repo_config.name}",
                    "commit_sha": commit_sha
                }
            )
            errors.append(error)
            logger.error(f"Unexpected check run discovery error: {e}")
        
        logger.debug(f"Discovered {len(check_runs)} check runs with {len(errors)} errors")
        return check_runs, errors
    
    def _parse_pr_data(self, pr_data: dict[str, Any]) -> PRData:
        """Parse GitHub PR data into internal format.
        
        Args:
            pr_data: Raw GitHub PR data
            
        Returns:
            Parsed PR data
        """
        # Handle merged PRs (GitHub reports them as "closed" with merged_at set)
        state = pr_data.get('state', 'open')
        if state == 'closed' and pr_data.get('merged_at'):
            state = 'merged'
        
        return PRData(
            number=pr_data['number'],
            title=pr_data['title'],
            author=pr_data['user']['login'],
            state=state,
            draft=pr_data.get('draft', False),
            base_branch=pr_data['base']['ref'],
            head_branch=pr_data['head']['ref'],
            base_sha=pr_data['base']['sha'],
            head_sha=pr_data['head']['sha'],
            url=pr_data['html_url'],
            body=pr_data.get('body'),
            metadata={
                'labels': [label['name'] for label in pr_data.get('labels', [])],
                'milestone': pr_data.get('milestone', {}).get('title') if pr_data.get('milestone') else None,
                'assignees': [assignee['login'] for assignee in pr_data.get('assignees', [])],
                'requested_reviewers': [reviewer['login'] for reviewer in pr_data.get('requested_reviewers', [])],
                'mergeable': pr_data.get('mergeable'),
                'mergeable_state': pr_data.get('mergeable_state'),
                'merged_at': pr_data.get('merged_at'),
                'closed_at': pr_data.get('closed_at'),
            },
            updated_at=datetime.fromisoformat(pr_data['updated_at'].replace('Z', '+00:00'))
        )
    
    def _parse_check_run_data(self, check_data: dict[str, Any]) -> CheckRunData:
        """Parse GitHub check run data into internal format.
        
        Args:
            check_data: Raw GitHub check run data
            
        Returns:
            Parsed check run data
        """
        # Parse timestamps
        started_at = None
        if check_data.get('started_at'):
            started_at = datetime.fromisoformat(check_data['started_at'].replace('Z', '+00:00'))
            
        completed_at = None
        if check_data.get('completed_at'):
            completed_at = datetime.fromisoformat(check_data['completed_at'].replace('Z', '+00:00'))
        
        # Get output information
        output = check_data.get('output', {})
        
        return CheckRunData(
            id=check_data['id'],
            name=check_data['name'],
            status=check_data['status'],
            conclusion=check_data.get('conclusion'),
            started_at=started_at,
            completed_at=completed_at,
            details_url=check_data.get('details_url'),
            output_title=output.get('title'),
            output_summary=output.get('summary'),
            external_id=check_data.get('external_id')
        )
    
    @classmethod
    async def create_for_repository(cls, repo_config: RepositoryConfig) -> 'PRDiscoveryEngine':
        """Create discovery engine for a specific repository.
        
        Args:
            repo_config: Repository configuration
            
        Returns:
            Configured discovery engine
        """
        auth = PersonalAccessTokenAuth(repo_config.auth_token)
        github_client = GitHubClient(auth)
        await github_client._ensure_session()
        
        return cls(github_client)