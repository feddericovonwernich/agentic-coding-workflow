#!/usr/bin/env python3
"""
GitHub API Integration Examples

This module demonstrates comprehensive usage of the GitHub API client
for common integration patterns in the agentic coding workflow.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from src.github.auth import GitHubAppAuth, PersonalAccessTokenAuth
from src.github.client import GitHubClient
from src.github.exceptions import (
    GitHubAuthenticationError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from src.github.pagination import PaginationConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GitHubIntegrationExamples:
    """Examples of GitHub API integration patterns."""

    def __init__(self, token: str):
        """Initialize with GitHub token."""
        auth = PersonalAccessTokenAuth(token=token)
        self.client = GitHubClient(auth=auth)

    async def example_basic_operations(self):
        """Example: Basic GitHub API operations."""
        logger.info("=== Basic GitHub Operations ===")

        try:
            # Get authenticated user
            user = await self.client.get_user()
            logger.info(f"Authenticated as: {user['login']}")

            # Get user repositories
            repos = await self.client.get_user_repos()
            logger.info(f"Found {len(repos)} repositories")

            # Get specific repository
            repo = await self.client.get_repo("octocat", "Hello-World")
            logger.info(f"Repository: {repo['full_name']} - {repo['description']}")

        except GitHubAuthenticationError:
            logger.error("Authentication failed - check your token")
        except GitHubNotFoundError as e:
            logger.error(f"Resource not found: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    async def example_pull_request_monitoring(self):
        """Example: Monitor pull requests for a repository."""
        logger.info("=== Pull Request Monitoring ===")

        owner = "microsoft"
        repo = "vscode"

        try:
            # Get open pull requests
            pulls = await self.client.get_pulls(
                owner=owner, repo=repo, state="open", per_page=10
            )

            logger.info(f"Found {len(pulls)} open pull requests")

            for pr in pulls[:3]:  # Process first 3 PRs
                logger.info(f"PR #{pr['number']}: {pr['title']}")

                # Get PR details
                pr_detail = await self.client.get_pull(owner, repo, pr["number"])
                logger.info(f"  - Created: {pr_detail['created_at']}")
                logger.info(f"  - Author: {pr_detail['user']['login']}")
                logger.info(f"  - Mergeable: {pr_detail['mergeable']}")

                # Get check runs for the PR
                check_runs = await self.client.get_check_runs(
                    owner=owner, repo=repo, ref=pr["head"]["sha"]
                )

                logger.info(f"  - Check runs: {len(check_runs)}")
                for check in check_runs[:2]:  # Show first 2 checks
                    logger.info(
                        f"    * {check['name']}: {check['status']} - "
                        f"{check['conclusion']}"
                    )

        except GitHubRateLimitError as e:
            logger.warning(f"Rate limit hit: {e.reset_time}")
            logger.info("Waiting for rate limit reset...")
            await asyncio.sleep(60)  # Wait and retry

        except Exception as e:
            logger.error(f"Error monitoring PRs: {e}")

    async def example_repository_analysis(self):
        """Example: Analyze repository activity and health."""
        logger.info("=== Repository Analysis ===")

        owner = "octocat"
        repo = "Hello-World"

        try:
            # Get repository details
            repo_data = await self.client.get_repo(owner, repo)

            # Analyze repository metrics
            metrics = {
                "stars": repo_data["stargazers_count"],
                "forks": repo_data["forks_count"],
                "open_issues": repo_data["open_issues_count"],
                "language": repo_data["language"],
                "created_at": repo_data["created_at"],
                "updated_at": repo_data["updated_at"],
            }

            logger.info("Repository Metrics:")
            for key, value in metrics.items():
                logger.info(f"  {key}: {value}")

            # Get recent commits
            commits = await self.client.get_commits(owner=owner, repo=repo, per_page=5)

            logger.info(f"\nRecent commits ({len(commits)}):")
            for commit in commits:
                author = commit["commit"]["author"]["name"]
                message = commit["commit"]["message"].split("\n")[0]
                date = commit["commit"]["author"]["date"]
                logger.info(f"  - {author}: {message} ({date})")

            # Check repository activity (issues and PRs)
            since = (datetime.now() - timedelta(days=30)).isoformat()

            recent_issues = await self.client.get_issues(
                owner=owner, repo=repo, state="all", since=since, per_page=10
            )

            logger.info(
                f"\nRecent activity (last 30 days): {len(recent_issues)} issues/PRs"
            )

        except Exception as e:
            logger.error(f"Error analyzing repository: {e}")

    async def example_pagination_handling(self):
        """Example: Handle large datasets with pagination."""
        logger.info("=== Pagination Handling ===")

        try:
            # Configure pagination
            pagination_config = PaginationConfig(
                per_page=50, max_pages=5, auto_paginate=True
            )

            # Get all repositories for a user with pagination
            all_repos = []
            async for page in self.client.paginate_user_repos(
                username="octocat", pagination_config=pagination_config
            ):
                all_repos.extend(page)
                logger.info(f"Fetched page with {len(page)} repositories")

            logger.info(f"Total repositories fetched: {len(all_repos)}")

            # Example: Process repositories in batches
            batch_size = 10
            for i in range(0, len(all_repos), batch_size):
                batch = all_repos[i : i + batch_size]
                logger.info(
                    f"Processing batch {i // batch_size + 1} with {len(batch)} repos"
                )

                # Process each repository in batch
                for repo in batch:
                    # Simulate processing
                    logger.info(f"  - Processing: {repo['name']}")

        except Exception as e:
            logger.error(f"Error handling pagination: {e}")

    async def example_rate_limiting(self):
        """Example: Handle rate limiting gracefully."""
        logger.info("=== Rate Limiting Example ===")

        try:
            # Check current rate limit status
            rate_limit = await self.client.get_rate_limit()

            logger.info("Rate Limit Status:")
            logger.info(
                f"  Core: {rate_limit['core']['remaining']}/"
                f"{rate_limit['core']['limit']}"
            )
            logger.info(
                f"  Search: {rate_limit['search']['remaining']}/"
                f"{rate_limit['search']['limit']}"
            )

            # Example of rate-limited operations
            repos_to_check = ["microsoft/vscode", "facebook/react", "google/go-github"]

            for repo_name in repos_to_check:
                owner, repo = repo_name.split("/")

                try:
                    # Check if we're approaching rate limit
                    current_limit = await self.client.get_rate_limit()
                    if current_limit["core"]["remaining"] < 10:
                        logger.warning("Approaching rate limit, waiting...")
                        await asyncio.sleep(60)

                    # Make API call
                    repo_data = await self.client.get_repo(owner, repo)
                    logger.info(
                        f"Checked {repo_name}: {repo_data['stargazers_count']} stars"
                    )

                except GitHubRateLimitError as e:
                    logger.warning(f"Rate limited, waiting until {e.reset_time}")
                    # In real application, you'd wait until reset_time
                    await asyncio.sleep(5)  # Short wait for demo

        except Exception as e:
            logger.error(f"Error handling rate limiting: {e}")

    async def example_error_handling(self):
        """Example: Comprehensive error handling patterns."""
        logger.info("=== Error Handling Examples ===")

        # Example 1: Handle authentication errors
        try:
            invalid_client = GitHubClient(auth=PersonalAccessTokenAuth("invalid_token"))
            await invalid_client.get_user()
        except GitHubAuthenticationError:
            logger.warning("Expected authentication error caught")

        # Example 2: Handle not found errors
        try:
            await self.client.get_repo("nonexistent", "repository")
        except GitHubNotFoundError:
            logger.warning("Expected not found error caught")

        # Example 3: Handle rate limit with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                user = await self.client.get_user()
                logger.info(f"Successfully got user: {user['login']}")
                break
            except GitHubRateLimitError:
                if attempt < max_retries - 1:
                    wait_time = min(60, 2**attempt)  # Exponential backoff
                    logger.warning(f"Rate limited, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded for rate limit")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break


class GitHubAppExample:
    """Example using GitHub App authentication."""

    def __init__(self, app_id: str, private_key: str, installation_id: str):
        """Initialize with GitHub App credentials."""
        auth = GitHubAppAuth(
            app_id=app_id, private_key=private_key, installation_id=installation_id
        )
        self.client = GitHubClient(auth=auth)

    async def example_app_operations(self):
        """Example operations using GitHub App authentication."""
        logger.info("=== GitHub App Operations ===")

        try:
            # Get installation repositories
            repos = await self.client.get_installation_repos()
            logger.info(f"App has access to {len(repos)} repositories")

            for repo in repos[:3]:
                logger.info(f"  - {repo['full_name']}")

                # Get pull requests for each repository
                owner, repo_name = repo["full_name"].split("/")
                pulls = await self.client.get_pulls(owner, repo_name, state="open")
                logger.info(f"    Open PRs: {len(pulls)}")

        except Exception as e:
            logger.error(f"Error with GitHub App operations: {e}")


async def comprehensive_github_example():
    """Comprehensive example demonstrating all GitHub integration patterns."""
    # Replace with your actual GitHub token
    github_token = "your_github_token_here"

    if github_token == "your_github_token_here":
        logger.error("Please set a valid GitHub token")
        return

    # Initialize examples
    examples = GitHubIntegrationExamples(github_token)

    # Run all examples
    try:
        await examples.example_basic_operations()
        await examples.example_pull_request_monitoring()
        await examples.example_repository_analysis()
        await examples.example_pagination_handling()
        await examples.example_rate_limiting()
        await examples.example_error_handling()

    except Exception as e:
        logger.error(f"Example execution failed: {e}")

    finally:
        # Clean up
        await examples.client.close()


async def github_app_example():
    """Example using GitHub App authentication."""
    # Replace with your GitHub App credentials
    app_id = "your_app_id"
    private_key = "your_private_key"
    installation_id = "your_installation_id"

    if app_id == "your_app_id":
        logger.error("Please set valid GitHub App credentials")
        return

    app_example = GitHubAppExample(app_id, private_key, installation_id)

    try:
        await app_example.example_app_operations()
    except Exception as e:
        logger.error(f"GitHub App example failed: {e}")
    finally:
        await app_example.client.close()


if __name__ == "__main__":
    # Run comprehensive examples
    asyncio.run(comprehensive_github_example())

    # Uncomment to run GitHub App example
    # asyncio.run(github_app_example())
