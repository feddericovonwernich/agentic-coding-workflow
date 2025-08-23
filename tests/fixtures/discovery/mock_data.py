"""
Mock data and response generators for GitHub API testing.

Provides realistic GitHub API responses and data structures for testing
PR discovery, check run analysis, and API interaction scenarios.
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional


class MockGitHubAPIResponses:
    """Collection of realistic GitHub API response templates."""

    @staticmethod
    def pull_request_response(**overrides: Any) -> dict[str, Any]:
        """
        Why: Provides realistic GitHub API PR response data for testing
        What: Creates GitHub-style PR response with all standard fields
        How: Uses realistic field values that match GitHub API structure
        """
        pr_number = overrides.get("number", random.randint(1, 9999))
        defaults = {
            "id": random.randint(1000000, 9999999),
            "number": pr_number,
            "state": random.choice(["open", "closed"]),
            "locked": False,
            "title": f"Fix critical bug in PR processing (#{pr_number})",
            "user": {
                "login": f"developer{random.randint(1, 999)}",
                "id": random.randint(1000, 9999),
                "type": "User",
                "site_admin": False,
            },
            "body": (
                "This PR addresses a critical issue in the "
                "PR processing pipeline.\n\n"
                "## Changes\n"
                "- Add null pointer validation\n"
                "- Improve error handling\n"
                "- Update unit tests\n\n"
                "## Testing\n"
                "- [x] Unit tests pass\n"
                "- [x] Integration tests pass\n"
                "- [ ] Manual testing in staging\n\n"
                f"Closes #{random.randint(100, 999)}"
            ),
            "created_at": (
                datetime.utcnow() - timedelta(days=random.randint(1, 30))
            ).isoformat()
            + "Z",
            "updated_at": (
                datetime.utcnow() - timedelta(hours=random.randint(1, 24))
            ).isoformat()
            + "Z",
            "closed_at": None,
            "merged_at": None,
            "assignee": None,
            "assignees": [],
            "requested_reviewers": [],
            "draft": random.choice([True, False]),
            "head": {
                "label": (
                    f"developer{random.randint(1, 999)}:feature/fix-"
                    f"{uuid.uuid4().hex[:8]}"
                ),
                "ref": f"feature/fix-{uuid.uuid4().hex[:8]}",
                "sha": f"a1b2c3d{uuid.uuid4().hex[:32]}",
                "repo": {
                    "id": random.randint(100000, 999999),
                    "name": "test-repo",
                    "full_name": "test-org/test-repo",
                    "private": False,
                    "owner": {
                        "login": "test-org",
                        "id": random.randint(1000, 9999),
                        "type": "Organization",
                    },
                },
            },
            "base": {
                "label": "test-org:main",
                "ref": "main",
                "sha": f"z9y8x7w{uuid.uuid4().hex[:32]}",
                "repo": {
                    "id": random.randint(100000, 999999),
                    "name": "test-repo",
                    "full_name": "test-org/test-repo",
                    "private": False,
                    "owner": {
                        "login": "test-org",
                        "id": random.randint(1000, 9999),
                        "type": "Organization",
                    },
                },
            },
            "html_url": f"https://github.com/test-org/test-repo/pull/{pr_number}",
            "diff_url": f"https://github.com/test-org/test-repo/pull/{pr_number}.diff",
            "patch_url": f"https://github.com/test-org/test-repo/pull/{pr_number}.patch",
            "mergeable": True,
            "mergeable_state": "clean",
            "merged": False,
            "merge_commit_sha": None,
            "comments": random.randint(0, 10),
            "review_comments": random.randint(0, 5),
            "commits": random.randint(1, 10),
            "additions": random.randint(10, 500),
            "deletions": random.randint(5, 200),
            "changed_files": random.randint(1, 20),
        }
        defaults.update(overrides)

        # Set merged_at and closed_at for merged/closed PRs
        if defaults["state"] == "closed":
            closed_time = datetime.fromisoformat(defaults["updated_at"].rstrip("Z"))
            defaults["closed_at"] = closed_time.isoformat() + "Z"

            if defaults.get("merged", False):
                defaults["merged_at"] = defaults["closed_at"]
                defaults["merge_commit_sha"] = f"m{uuid.uuid4().hex[:39]}"

        return defaults

    @staticmethod
    def check_run_response(**overrides: Any) -> dict[str, Any]:
        """
        Why: Provides realistic GitHub check run API response data
        What: Creates GitHub-style check run response with status and output
        How: Uses realistic check run fields matching GitHub API structure
        """
        check_id = overrides.get("id", random.randint(1000000, 9999999))
        check_types = ["lint", "test", "build", "security", "coverage"]
        check_type = random.choice(check_types)

        defaults = {
            "id": check_id,
            "head_sha": f"abc{uuid.uuid4().hex[:37]}",
            "external_id": f"check-{uuid.uuid4().hex[:12]}",
            "url": f"https://api.github.com/repos/test-org/test-repo/check-runs/{check_id}",
            "html_url": f"https://github.com/test-org/test-repo/runs/{check_id}",
            "details_url": f"https://github.com/test-org/test-repo/runs/{check_id}",
            "status": random.choice(["queued", "in_progress", "completed"]),
            "conclusion": None,
            "started_at": (
                datetime.utcnow() - timedelta(minutes=random.randint(5, 60))
            ).isoformat()
            + "Z",
            "completed_at": None,
            "name": f"{check_type}-check",
            "check_suite": {
                "id": random.randint(100000, 999999),
                "head_branch": "main",
                "head_sha": f"abc{uuid.uuid4().hex[:37]}",
            },
            "app": {
                "id": random.randint(10000, 99999),
                "name": f"{check_type}-app",
                "owner": {
                    "login": f"{check_type}-bot",
                    "id": random.randint(10000, 99999),
                    "type": "Bot",
                },
            },
            "output": {
                "title": f"{check_type.title()} Check",
                "summary": f"{check_type.title()} check completed successfully",
                "text": None,
                "annotations_count": 0,
                "annotations_url": f"https://api.github.com/repos/test-org/test-repo/check-runs/{check_id}/annotations",
            },
        }
        defaults.update(overrides)

        # Set conclusion and completed_at for completed checks
        if defaults["status"] == "completed":
            if defaults["conclusion"] is None:
                defaults["conclusion"] = random.choice(
                    ["success", "failure", "cancelled", "skipped"]
                )
            if defaults["completed_at"] is None:
                start_time = datetime.fromisoformat(defaults["started_at"].rstrip("Z"))
                completed_time = start_time + timedelta(minutes=random.randint(1, 30))
                defaults["completed_at"] = completed_time.isoformat() + "Z"

            # Add failure details for failed checks
            if defaults["conclusion"] == "failure":
                defaults["output"]["title"] = f"{check_type.title()} Check Failed"
                defaults["output"]["summary"] = (
                    f"The {check_type} check found issues that need to be addressed"
                )
                defaults["output"]["text"] = f"""## {check_type.title()} Errors

Found the following issues:

### Critical Issues
- Line 45: Missing error handling for null values
- Line 78: Potential memory leak in loop

### Warnings
- Line 123: Consider using more descriptive variable name
- Line 156: Function complexity is high (consider refactoring)

Please address these issues before merging."""
                defaults["output"]["annotations_count"] = random.randint(1, 10)

        return defaults

    @staticmethod
    def check_runs_list_response(
        check_count: int = 5, **overrides: Any
    ) -> dict[str, Any]:
        """
        Why: Provides realistic GitHub check runs list API response
        What: Creates list response with multiple check runs for a commit
        How: Generates array of check runs with realistic distribution of statuses
        """
        check_runs = []
        for _i in range(check_count):
            check_run = MockGitHubAPIResponses.check_run_response()
            check_runs.append(check_run)

        defaults = {"total_count": check_count, "check_runs": check_runs}
        defaults.update(overrides)

        return defaults

    @staticmethod
    def rate_limit_response(**overrides: Any) -> dict[str, Any]:
        """
        Why: Provides realistic GitHub rate limit API response data
        What: Creates rate limit response with current usage and reset times
        How: Uses realistic GitHub rate limit structure and values
        """
        defaults = {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": random.randint(100, 4999),
                    "reset": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                    "used": random.randint(1, 4900),
                },
                "search": {
                    "limit": 30,
                    "remaining": random.randint(5, 29),
                    "reset": int(
                        (datetime.utcnow() + timedelta(minutes=1)).timestamp()
                    ),
                    "used": random.randint(1, 25),
                },
                "graphql": {
                    "limit": 5000,
                    "remaining": random.randint(100, 4999),
                    "reset": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                    "used": random.randint(1, 4900),
                },
            },
            "rate": {
                "limit": 5000,
                "remaining": random.randint(100, 4999),
                "reset": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                "used": random.randint(1, 4900),
            },
        }
        defaults.update(overrides)

        return defaults


class MockDiscoveryResponses:
    """Mock responses for internal discovery operations."""

    @staticmethod
    def discovery_cache_response(hit: bool = True, **overrides: Any) -> dict[str, Any]:
        """
        Why: Provides mock cache response data for testing caching scenarios
        What: Creates cache response with hit/miss information and ETag data
        How: Simulates Redis/memory cache responses with realistic timing
        """
        if hit:
            defaults = {
                "cache_hit": True,
                "data": MockGitHubAPIResponses.pull_request_response(),
                "etag": f'"abc{uuid.uuid4().hex[:32]}"',
                "cached_at": (
                    datetime.utcnow() - timedelta(minutes=random.randint(1, 10))
                ).isoformat(),
                "ttl_seconds": random.randint(60, 300),
                "response_time_ms": random.uniform(1.0, 10.0),
            }
        else:
            defaults = {
                "cache_hit": False,
                "data": None,
                "etag": None,
                "cached_at": None,
                "ttl_seconds": 0,
                "response_time_ms": random.uniform(0.1, 1.0),
            }

        defaults.update(overrides)
        return defaults


def create_mock_github_pr_response(
    pr_number: int, state: str = "open", has_check_runs: bool = True, **overrides: Any
) -> dict[str, Any]:
    """
    Why: Creates comprehensive mock GitHub PR data for specific test scenarios
    What: Generates realistic PR response with customizable key attributes
    How: Uses MockGitHubAPIResponses with specific overrides for test needs
    """
    pr_overrides = {"number": pr_number, "state": state, **overrides}

    response = MockGitHubAPIResponses.pull_request_response(**pr_overrides)

    # Add check runs data if requested
    if has_check_runs:
        response["_check_runs"] = MockGitHubAPIResponses.check_runs_list_response(
            check_count=random.randint(2, 6)
        )

    return response


def create_mock_github_check_runs_response(
    commit_sha: str, failure_count: int = 0, **overrides: Any
) -> dict[str, Any]:
    """
    Why: Creates mock check runs response for testing CI/CD integration scenarios
    What: Generates check runs list with specified failure count and commit SHA
    How: Uses MockGitHubAPIResponses with failure injection for error testing
    """
    check_count = overrides.get("check_count", 5)
    check_runs = []

    # Create failed check runs first
    for _i in range(failure_count):
        failed_check = MockGitHubAPIResponses.check_run_response(
            head_sha=commit_sha, status="completed", conclusion="failure"
        )
        check_runs.append(failed_check)

    # Create successful check runs for the rest
    for _i in range(check_count - failure_count):
        success_check = MockGitHubAPIResponses.check_run_response(
            head_sha=commit_sha, status="completed", conclusion="success"
        )
        check_runs.append(success_check)

    response_overrides = {
        "total_count": check_count,
        "check_runs": check_runs,
        **overrides,
    }

    return MockGitHubAPIResponses.check_runs_list_response(**response_overrides)


def create_realistic_pr_data(
    repository_id: uuid.UUID,
    pr_count: int = 10,
    include_drafts: bool = True,
    include_merged: bool = True,
) -> list[dict[str, Any]]:
    """
    Why: Creates batch of realistic PR data for testing pagination and bulk operations
    What: Generates list of PR responses with realistic distribution of states
    How: Creates varied PR data with proper state distribution and unique identifiers
    """
    prs = []
    used_numbers = set()

    for i in range(pr_count):
        # Ensure unique PR numbers
        while True:
            pr_number = random.randint(1, 9999)
            if pr_number not in used_numbers:
                used_numbers.add(pr_number)
                break

        # Create realistic state distribution
        if i == 0:
            state = "open"  # At least one open PR
        elif i == pr_count - 1 and include_merged:
            state = "closed"
            merged = True
        elif i < pr_count // 2:
            state = "open"
        else:
            state = "closed"
            merged = random.choice([True, False])

        # Handle drafts
        draft = False
        if include_drafts and state == "open" and random.random() < 0.3:
            draft = True

        pr_data = create_mock_github_pr_response(
            pr_number=pr_number,
            state=state,
            draft=draft,
            merged=merged if state == "closed" else False,
            has_check_runs=not draft,  # Drafts typically don't have check runs
        )

        prs.append(pr_data)

    return prs


def create_realistic_check_run_data(
    commit_sha: str, include_failures: bool = True, failure_rate: float = 0.2
) -> dict[str, Any]:
    """
    Why: Creates realistic check run data with configurable failure scenarios
    What: Generates check runs with realistic CI/CD patterns and failure rates
    How: Creates mixed status checks with realistic failure distribution
    """
    check_types = ["lint", "test", "build", "security", "coverage", "integration"]
    check_runs = []

    for check_type in check_types:
        # Determine if this check should fail
        should_fail = include_failures and random.random() < failure_rate

        if should_fail:
            status = "completed"
            conclusion = "failure"
        else:
            # Mix of completed and in-progress checks
            if random.random() < 0.8:  # 80% completed
                status = "completed"
                conclusion = "success"
            else:  # 20% still running
                status = random.choice(["queued", "in_progress"])
                conclusion = None

        check_run = MockGitHubAPIResponses.check_run_response(
            name=f"{check_type}-check",
            head_sha=commit_sha,
            status=status,
            conclusion=conclusion,
        )

        check_runs.append(check_run)

    return {"total_count": len(check_runs), "check_runs": check_runs}
