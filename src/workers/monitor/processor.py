"""Core PR discovery and processing engine."""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import PullRequest
from src.repositories import CheckRunRepository, PullRequestRepository

from .change_detection import StateChangeDetector
from .discovery import PRDiscoveryEngine
from .models import ChangeSet, ProcessingError, ProcessingResult, RepositoryConfig
from .synchronization import DataSynchronizer

logger = logging.getLogger(__name__)


class PRProcessor:
    """Core PR discovery and processing engine."""
    
    def __init__(
        self,
        session: AsyncSession,
        pr_repo: Optional[PullRequestRepository] = None,
        check_repo: Optional[CheckRunRepository] = None
    ):
        """Initialize PR processor.
        
        Args:
            session: Database session
            pr_repo: Pull request repository (created if None)
            check_repo: Check run repository (created if None)
        """
        self.session = session
        self.pr_repo = pr_repo or PullRequestRepository(session)
        self.check_repo = check_repo or CheckRunRepository(session)
        self.state_detector = StateChangeDetector()
        self.synchronizer = DataSynchronizer(session, self.pr_repo, self.check_repo)
    
    async def process_repository(self, repo_config: RepositoryConfig) -> ProcessingResult:
        """Process a single repository for PR updates.
        
        Args:
            repo_config: Repository configuration
            
        Returns:
            Processing result with statistics and errors
        """
        start_time = time.time()
        errors: list[ProcessingError] = []
        prs_processed = 0
        new_prs = 0
        updated_prs = 0
        check_runs_updated = 0
        
        logger.info(f"Starting processing for repository {repo_config.owner}/{repo_config.name}")
        
        try:
            # Create discovery engine for this repository
            discovery_engine = await PRDiscoveryEngine.create_for_repository(repo_config)
            
            # Discover PRs from GitHub
            since_time = datetime.now(UTC) - timedelta(hours=24)  # Look back 24 hours
            github_prs, discovery_errors = await discovery_engine.discover_prs(
                repo_config, 
                states=['open', 'closed'],
                since=since_time
            )
            errors.extend(discovery_errors)
            
            if not github_prs and not errors:
                logger.info(f"No PRs found for {repo_config.owner}/{repo_config.name}")
                processing_time = time.time() - start_time
                return ProcessingResult(
                    repository_id=repo_config.id,
                    prs_processed=0,
                    new_prs=0,
                    updated_prs=0,
                    check_runs_updated=0,
                    errors=errors,
                    processing_time=processing_time
                )
            
            # Process each PR
            all_pr_updates = []
            all_check_updates = []
            
            for github_pr in github_prs:
                try:
                    pr_updates, check_updates, pr_errors = await self._process_single_pr(
                        repo_config, github_pr, discovery_engine
                    )
                    
                    all_pr_updates.extend(pr_updates)
                    all_check_updates.extend(check_updates)
                    errors.extend(pr_errors)
                    prs_processed += 1
                    
                except Exception as e:
                    error = ProcessingError(
                        error_type="pr_processing_error",
                        message=f"Failed to process PR #{github_pr.number}: {e}",
                        details={"pr_number": github_pr.number}
                    )
                    errors.append(error)
                    logger.error(f"Failed to process PR #{github_pr.number}: {e}")
            
            # Build change set from all updates
            change_set = self.state_detector.build_change_set(all_pr_updates, all_check_updates)
            
            # Synchronize changes to database
            if change_set.has_changes:
                sync_errors = await self.synchronizer.synchronize_changes(
                    repo_config.id, change_set
                )
                errors.extend(sync_errors)
                
                # Create state history records
                history_errors = await self.synchronizer.create_state_transition_records(change_set)
                errors.extend(history_errors)
                
                new_prs = len(change_set.new_prs)
                updated_prs = len(change_set.updated_prs)
                check_runs_updated = len(change_set.new_check_runs) + len(change_set.updated_check_runs)
            
            # Update last checked timestamp for processed PRs
            await self.synchronizer.bulk_update_last_checked(repo_config.id)
            
            # Close discovery engine
            await discovery_engine.github_client.close()
            
        except Exception as e:
            error = ProcessingError(
                error_type="repository_processing_error",
                message=f"Failed to process repository {repo_config.owner}/{repo_config.name}: {e}",
                details={"repository_id": str(repo_config.id)}
            )
            errors.append(error)
            logger.error(f"Failed to process repository: {e}")
        
        processing_time = time.time() - start_time
        
        result = ProcessingResult(
            repository_id=repo_config.id,
            prs_processed=prs_processed,
            new_prs=new_prs,
            updated_prs=updated_prs,
            check_runs_updated=check_runs_updated,
            errors=errors,
            processing_time=processing_time
        )
        
        logger.info(
            f"Completed processing for {repo_config.owner}/{repo_config.name}: "
            f"{prs_processed} PRs processed, {new_prs} new, {updated_prs} updated, "
            f"{check_runs_updated} check runs updated, {len(errors)} errors, "
            f"{processing_time:.2f}s"
        )
        
        return result
    
    async def _process_single_pr(
        self,
        repo_config: RepositoryConfig,
        github_pr,
        discovery_engine: PRDiscoveryEngine
    ) -> tuple[list, list, list[ProcessingError]]:
        """Process a single PR and its check runs.
        
        Args:
            repo_config: Repository configuration
            github_pr: PR data from GitHub
            discovery_engine: Discovery engine for API calls
            
        Returns:
            Tuple of (PR updates, check run updates, errors)
        """
        errors: list[ProcessingError] = []
        pr_updates = []
        check_updates = []
        
        try:
            # Get existing PR from database
            existing_pr = await self.pr_repo.get_by_repo_and_number(
                repo_config.id, github_pr.number
            )
            
            # Detect PR changes
            updated_pr, pr_state_changes = self.state_detector.detect_pr_changes(
                github_pr, existing_pr
            )
            
            if updated_pr or pr_state_changes:
                pr_updates.append((updated_pr, pr_state_changes))
            
            # Get PR ID for check runs (use existing or new PR ID)
            pr_id = existing_pr.id if existing_pr else (updated_pr.id if updated_pr else uuid.uuid4())
            
            # Discover and process check runs for this PR
            github_checks, check_errors = await discovery_engine.discover_check_runs(
                repo_config, github_pr.head_sha
            )
            errors.extend(check_errors)
            
            for github_check in github_checks:
                try:
                    # Get existing check run
                    existing_check = await self.check_repo.get_by_external_id(
                        str(github_check.id)
                    )
                    
                    # Detect check run changes
                    updated_check, check_state_changes = self.state_detector.detect_check_run_changes(
                        github_check, existing_check
                    )
                    
                    if updated_check:
                        updated_check.pr_id = pr_id
                    
                    if updated_check or check_state_changes:
                        check_updates.append((updated_check, check_state_changes))
                        
                except Exception as e:
                    error = ProcessingError(
                        error_type="check_run_processing_error",
                        message=f"Failed to process check run {github_check.name}: {e}",
                        details={
                            "pr_number": github_pr.number,
                            "check_name": github_check.name,
                            "check_id": github_check.id
                        }
                    )
                    errors.append(error)
                    logger.warning(f"Failed to process check run {github_check.name}: {e}")
        
        except Exception as e:
            error = ProcessingError(
                error_type="single_pr_processing_error",
                message=f"Failed to process PR #{github_pr.number}: {e}",
                details={"pr_number": github_pr.number}
            )
            errors.append(error)
            logger.error(f"Failed to process single PR #{github_pr.number}: {e}")
        
        return pr_updates, check_updates, errors
    
    async def process_multiple_repositories(
        self,
        repo_configs: list[RepositoryConfig],
        max_concurrent: int = 5
    ) -> list[ProcessingResult]:
        """Process multiple repositories concurrently.
        
        Args:
            repo_configs: List of repository configurations
            max_concurrent: Maximum concurrent repositories to process
            
        Returns:
            List of processing results
        """
        logger.info(f"Processing {len(repo_configs)} repositories with max_concurrent={max_concurrent}")
        
        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(config: RepositoryConfig) -> ProcessingResult:
            async with semaphore:
                return await self.process_repository(config)
        
        # Process all repositories concurrently
        tasks = [process_with_semaphore(config) for config in repo_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions and convert to ProcessingResults
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error result for failed repository
                config = repo_configs[i]
                error_result = ProcessingResult(
                    repository_id=config.id,
                    prs_processed=0,
                    new_prs=0,
                    updated_prs=0,
                    check_runs_updated=0,
                    errors=[ProcessingError(
                        error_type="repository_processing_exception",
                        message=f"Repository processing failed with exception: {result}",
                        details={"repository": f"{config.owner}/{config.name}"}
                    )],
                    processing_time=0.0
                )
                final_results.append(error_result)
                logger.error(f"Repository {config.owner}/{config.name} failed: {result}")
            else:
                final_results.append(result)
        
        # Log summary
        total_prs = sum(r.prs_processed for r in final_results)
        total_new = sum(r.new_prs for r in final_results)
        total_updated = sum(r.updated_prs for r in final_results)
        total_checks = sum(r.check_runs_updated for r in final_results)
        total_errors = sum(len(r.errors) for r in final_results)
        
        logger.info(
            f"Completed processing {len(repo_configs)} repositories: "
            f"{total_prs} PRs processed, {total_new} new, {total_updated} updated, "
            f"{total_checks} check runs updated, {total_errors} total errors"
        )
        
        return final_results