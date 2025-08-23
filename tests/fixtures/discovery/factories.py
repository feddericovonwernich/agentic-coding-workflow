"""
Factory functions for creating test data for PR Discovery components.

These factories provide realistic test data that can be customized for specific
testing scenarios while maintaining consistency and avoiding conflicts.
"""

import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from src.workers.discovery.interfaces import (
    ChangeType,
    DiscoveredCheckRun,
    DiscoveredPR,
    DiscoveryConfig,
    DiscoveryError,
    DiscoveryPriority,
    EntityType,
    PRDiscoveryResult,
    RepositoryState,
    StateChange,
    StoredPRState,
    SynchronizationResult,
)


class DiscoveredPRFactory:
    """Factory for creating DiscoveredPR test instances."""

    @staticmethod
    def create(**overrides: Any) -> DiscoveredPR:
        """
        Why: Provides consistent, realistic PR data for testing with customizable fields
        What: Creates DiscoveredPR instances with realistic GitHub-style data
        How: Uses realistic defaults that can be overridden for specific test scenarios
        """
        defaults = {
            "pr_number": random.randint(1, 9999),
            "title": (
                f"Fix: Handle edge case in PR processing "
                f"(#{random.randint(1000, 9999)})"
            ),
            "author": f"developer{random.randint(1, 999)}",
            "state": random.choice(["open", "closed", "merged"]),
            "draft": random.choice([True, False]),
            "base_branch": "main",
            "head_branch": f"feature/fix-{uuid.uuid4().hex[:8]}",
            "base_sha": f"a1b2c3d{uuid.uuid4().hex[:8]}e5f6789",
            "head_sha": f"z9y8x7w{uuid.uuid4().hex[:8]}v5u4321",
            "url": (
                f"https://github.com/test-org/test-repo/pull/{random.randint(1, 9999)}"
            ),
            "body": (
                f"This PR fixes a critical bug in the processing system.\n\n"
                f"Changes:\n- Add error handling\n- Update tests\n- Fix edge cases\n\n"
                f"Closes #{random.randint(100, 999)}"
            ),
            "created_at": datetime.utcnow() - timedelta(days=random.randint(1, 30)),
            "updated_at": datetime.utcnow() - timedelta(hours=random.randint(1, 24)),
            "merged_at": None,
            "metadata": {
                "additions": random.randint(10, 500),
                "deletions": random.randint(5, 200),
                "changed_files": random.randint(1, 20),
                "commits": random.randint(1, 10),
                "mergeable": True,
                "mergeable_state": "clean",
            },
            "check_runs": [],
        }
        defaults.update(overrides)

        # Set merged_at if state is merged
        if defaults["state"] == "merged" and defaults["merged_at"] is None:
            defaults["merged_at"] = defaults["updated_at"]

        return DiscoveredPR(
            pr_number=defaults["pr_number"],
            title=defaults["title"],
            author=defaults["author"],
            state=defaults["state"],
            draft=defaults["draft"],
            base_branch=defaults["base_branch"],
            head_branch=defaults["head_branch"],
            base_sha=defaults["base_sha"],
            head_sha=defaults["head_sha"],
            url=defaults["url"],
            body=defaults["body"],
            created_at=defaults["created_at"],
            updated_at=defaults["updated_at"],
            merged_at=defaults["merged_at"],
            metadata=defaults["metadata"],
            check_runs=defaults["check_runs"],
        )

    @staticmethod
    def create_with_check_runs(
        check_run_count: int = 3, **overrides: Any
    ) -> DiscoveredPR:
        """
        Why: Creates PRs with realistic check runs for testing CI/CD integration
             scenarios
        What: Generates PR with specified number of associated check runs
        How: Uses DiscoveredCheckRunFactory to create realistic check run data
        """
        check_runs = [
            DiscoveredCheckRunFactory.create() for _ in range(check_run_count)
        ]
        overrides["check_runs"] = check_runs
        return DiscoveredPRFactory.create(**overrides)

    @staticmethod
    def create_batch(
        count: int, repository_id: uuid.UUID | None = None, **overrides
    ) -> list[DiscoveredPR]:
        """
        Why: Creates multiple unique PRs for testing batch processing and pagination
        What: Generates list of PRs with unique PR numbers and consistent repository
        How: Ensures no duplicate PR numbers within the batch for the same repository
        """
        prs = []
        used_pr_numbers = set()

        for i in range(count):
            # Ensure unique PR numbers within the batch
            while True:
                pr_number = random.randint(1, 9999)
                if pr_number not in used_pr_numbers:
                    used_pr_numbers.add(pr_number)
                    break

            pr_overrides = {
                "pr_number": pr_number,
                "title": f"PR {i + 1}: {uuid.uuid4().hex[:8]} feature implementation",
                **overrides,
            }
            prs.append(DiscoveredPRFactory.create(**pr_overrides))

        return prs


class DiscoveredCheckRunFactory:
    """Factory for creating DiscoveredCheckRun test instances."""

    @staticmethod
    def create(**overrides: Any) -> DiscoveredCheckRun:
        """
        Why: Provides realistic check run data for testing CI/CD workflow scenarios
        What: Creates DiscoveredCheckRun instances with common CI check patterns
        How: Uses realistic check names, statuses, and output structures
        """
        check_types = ["lint", "test", "build", "security", "coverage"]
        check_type = random.choice(check_types)

        defaults = {
            "external_id": f"check-run-{uuid.uuid4().hex[:12]}",
            "name": f"{check_type}-check-{random.randint(1, 999)}",
            "status": random.choice(["queued", "in_progress", "completed"]),
            "conclusion": None,
            "started_at": datetime.utcnow() - timedelta(minutes=random.randint(5, 60)),
            "completed_at": None,
            "details_url": (
                f"https://github.com/test-org/test-repo/runs/"
                f"{random.randint(1000000, 9999999)}"
            ),
            "output": {
                "title": f"{check_type.title()} Check",
                "summary": f"{check_type.title()} check completed",
                "text": f"Detailed {check_type} check output would appear here",
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
                start_time = defaults["started_at"]
                if isinstance(start_time, datetime):
                    defaults["completed_at"] = start_time + timedelta(
                        minutes=random.randint(1, 30)
                    )
                else:
                    defaults["completed_at"] = datetime.utcnow()

        return DiscoveredCheckRun(
            external_id=defaults["external_id"],
            name=defaults["name"],
            status=defaults["status"],
            conclusion=defaults["conclusion"],
            started_at=defaults["started_at"],
            completed_at=defaults["completed_at"],
            details_url=defaults["details_url"],
            output=defaults["output"],
        )

    @staticmethod
    def create_failed(**overrides) -> DiscoveredCheckRun:
        """
        Why: Creates failed check runs for testing error analysis and fix workflows
        What: Generates check run with failure status and realistic error output
        How: Sets status to completed with failure conclusion and error details
        """
        defaults = {
            "status": "completed",
            "conclusion": "failure",
            "completed_at": datetime.utcnow()
            - timedelta(minutes=random.randint(1, 30)),
            "output": {
                "title": "Check Failed",
                "summary": "One or more checks failed",
                "text": """Error: Linting failed
/src/worker.py:45:1: E302 expected 2 blank lines, found 1
/src/utils.py:123:80: E501 line too long (85 > 79 characters)
Found 2 errors in 2 files""",
            },
        }
        defaults.update(overrides)
        return DiscoveredCheckRunFactory.create(**defaults)

    @staticmethod
    def create_batch_mixed_status(count: int, **overrides) -> list[DiscoveredCheckRun]:
        """
        Why: Creates realistic mix of check run statuses for comprehensive testing
        What: Generates check runs with varied statuses (success, failure, pending)
        How: Distributes status types realistically across the batch
        """
        check_runs = []
        for i in range(count):
            # Create realistic distribution of check statuses
            if i == 0:  # First check always successful
                status_overrides = {"status": "completed", "conclusion": "success"}
            elif i == count - 1 and count > 2:  # Last check sometimes fails
                status_overrides = {"status": "completed", "conclusion": "failure"}
            else:  # Mixed statuses for middle checks
                status_overrides = {}

            check_runs.append(
                DiscoveredCheckRunFactory.create(**status_overrides, **overrides)
            )

        return check_runs


class PRDiscoveryResultFactory:
    """Factory for creating PRDiscoveryResult test instances."""

    @staticmethod
    def create(**overrides: Any) -> PRDiscoveryResult:
        """
        Why: Provides comprehensive discovery result data for testing orchestration
        What: Creates PRDiscoveryResult with realistic metrics and PR data
        How: Generates results with consistent PR data and realistic performance metrics
        """
        repository_id = overrides.get("repository_id", uuid.uuid4())
        discovered_prs = overrides.get(
            "discovered_prs",
            DiscoveredPRFactory.create_batch(random.randint(5, 25), repository_id),
        )

        defaults = {
            "repository_id": repository_id,
            "repository_url": f"https://github.com/test-org/repo-{repository_id.hex[:8]}",
            "discovered_prs": discovered_prs,
            "discovery_timestamp": datetime.utcnow(),
            "api_calls_used": random.randint(10, 100),
            "cache_hits": random.randint(5, 50),
            "cache_misses": random.randint(2, 20),
            "processing_time_ms": random.uniform(100.0, 5000.0),
            "errors": [],
        }
        defaults.update(overrides)

        return PRDiscoveryResult(**defaults)

    @staticmethod
    def create_with_errors(error_count: int = 2, **overrides) -> PRDiscoveryResult:
        """
        Why: Creates discovery results with errors for testing error handling
        What: Generates results with realistic error scenarios
        How: Includes common discovery errors like rate limits and network issues
        """
        errors = [
            DiscoveryErrorFactory.create(
                error_type=random.choice(["rate_limit", "network", "parse_error"])
            )
            for _ in range(error_count)
        ]
        overrides["errors"] = errors
        return PRDiscoveryResultFactory.create(**overrides)


class DiscoveryErrorFactory:
    """Factory for creating DiscoveryError test instances."""

    @staticmethod
    def create(**overrides: Any) -> DiscoveryError:
        """
        Why: Provides realistic error data for testing error handling scenarios
        What: Creates DiscoveryError instances with common failure patterns
        How: Uses realistic error types, messages, and recovery information
        """
        error_types = {
            "rate_limit": {
                "message": (
                    "API rate limit exceeded. Limit: 5000, Remaining: 0, "
                    "Reset: 2024-01-01T12:00:00Z"
                ),
                "recoverable": True,
                "context": {
                    "limit": 5000,
                    "remaining": 0,
                    "reset_time": "2024-01-01T12:00:00Z",
                },
            },
            "network": {
                "message": "Connection timeout after 30 seconds",
                "recoverable": True,
                "context": {"timeout": 30, "retry_count": 2},
            },
            "auth": {
                "message": "Authentication failed: invalid token",
                "recoverable": False,
                "context": {"token_valid": False},
            },
            "parse_error": {
                "message": "Failed to parse JSON response",
                "recoverable": False,
                "context": {"response_size": 1024, "parse_location": "line 45"},
            },
        }

        error_type = overrides.get(
            "error_type", random.choice(list(error_types.keys()))
        )
        error_template = error_types[error_type]

        defaults = {
            "error_type": error_type,
            "message": error_template["message"],
            "context": error_template["context"],
            "timestamp": datetime.utcnow(),
            "recoverable": error_template["recoverable"],
        }
        defaults.update(overrides)

        return DiscoveryError(**defaults)


class StateChangeFactory:
    """Factory for creating StateChange test instances."""

    @staticmethod
    def create(**overrides: Any) -> StateChange:
        """
        Why: Provides realistic state change data for testing change detection
        What: Creates StateChange instances with common transition patterns
        How: Uses realistic entity types, state transitions, and metadata
        """
        entity_types = [EntityType.PULL_REQUEST, EntityType.CHECK_RUN]
        entity_type = overrides.get("entity_type", random.choice(entity_types))

        if entity_type == EntityType.PULL_REQUEST:
            state_transitions = [
                ("open", "closed"),
                ("open", "merged"),
                (None, "open"),  # New PR
                ("draft", "open"),
            ]
        else:  # CHECK_RUN
            state_transitions = [
                ("queued", "in_progress"),
                ("in_progress", "completed"),
                (None, "queued"),  # New check
                ("completed", "completed"),  # Re-run
            ]

        old_state, new_state = random.choice(state_transitions)
        change_type = (
            ChangeType.CREATED if old_state is None else ChangeType.STATE_CHANGED
        )

        defaults = {
            "entity_type": entity_type,
            "entity_id": uuid.uuid4(),
            "external_id": f"{entity_type.value}-{random.randint(1, 9999)}",
            "old_state": old_state,
            "new_state": new_state,
            "change_type": change_type,
            "metadata": {
                "changed_by": "system",
                "reason": "automated_detection",
                "confidence": 0.95,
            },
            "detected_at": datetime.utcnow(),
        }
        defaults.update(overrides)

        return StateChange(**defaults)


class RepositoryStateFactory:
    """Factory for creating RepositoryState test instances."""

    @staticmethod
    def create(**overrides: Any) -> RepositoryState:
        """
        Why: Provides current repository state data for testing state comparison
        What: Creates RepositoryState with realistic PR and check data
        How: Generates state with multiple PRs in various states
        """
        repository_id = overrides.get("repository_id", uuid.uuid4())
        pr_count = overrides.get("pr_count", random.randint(5, 20))

        pull_requests = {}
        for i in range(pr_count):
            pr_number = i + 1
            pr_state = StoredPRStateFactory.create(pr_number=pr_number)
            pull_requests[pr_number] = pr_state

        defaults = {
            "repository_id": repository_id,
            "pull_requests": pull_requests,
            "last_updated": datetime.utcnow()
            - timedelta(minutes=random.randint(5, 60)),
        }
        defaults.update(overrides)

        return RepositoryState(**defaults)


class StoredPRStateFactory:
    """Factory for creating StoredPRState test instances."""

    @staticmethod
    def create(**overrides: Any) -> StoredPRState:
        """
        Why: Provides stored PR state data for testing state change detection
        What: Creates StoredPRState representing current database state
        How: Generates realistic PR state with check run status map
        """
        defaults = {
            "pr_id": uuid.uuid4(),
            "pr_number": random.randint(1, 9999),
            "state": random.choice(["open", "closed", "merged"]),
            "head_sha": f"abc{uuid.uuid4().hex[:8]}def",
            "updated_at": datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
            "check_runs": {
                "lint-check": random.choice(["success", "failure", "pending"]),
                "test-check": random.choice(["success", "failure", "pending"]),
                "build-check": random.choice(["success", "failure", "pending"]),
            },
        }
        defaults.update(overrides)

        return StoredPRState(**defaults)


class SynchronizationResultFactory:
    """Factory for creating SynchronizationResult test instances."""

    @staticmethod
    def create(**overrides: Any) -> SynchronizationResult:
        """
        Why: Provides synchronization result data for testing database operations
        What: Creates SynchronizationResult with realistic operation statistics
        How: Generates results with consistent counts and performance metrics
        """
        total_prs = random.randint(10, 100)
        total_checks = random.randint(20, 300)

        defaults = {
            "total_prs_processed": total_prs,
            "prs_created": random.randint(0, total_prs // 3),
            "prs_updated": random.randint(0, total_prs - (total_prs // 3)),
            "total_checks_processed": total_checks,
            "checks_created": random.randint(0, total_checks // 2),
            "checks_updated": random.randint(0, total_checks - (total_checks // 2)),
            "state_changes_recorded": random.randint(5, 50),
            "errors": [],
            "processing_time_ms": random.uniform(100.0, 2000.0),
        }
        defaults.update(overrides)

        return SynchronizationResult(**defaults)

    @staticmethod
    def create_with_errors(**overrides: Any) -> SynchronizationResult:
        """
        Why: Creates synchronization results with errors for testing failure scenarios
        What: Generates results with database operation errors
        How: Includes realistic database constraint and connection errors
        """
        errors = [
            DiscoveryErrorFactory.create(error_type="database"),
            DiscoveryErrorFactory.create(error_type="constraint_violation"),
        ]
        overrides["errors"] = errors
        return SynchronizationResultFactory.create(**overrides)


class DiscoveryConfigFactory:
    """Factory for creating DiscoveryConfig test instances."""

    @staticmethod
    def create(**overrides: Any) -> DiscoveryConfig:
        """
        Why: Provides discovery configuration data for testing various scenarios
        What: Creates DiscoveryConfig with realistic performance and limit settings
        How: Uses practical defaults that can be customized for specific tests
        """
        defaults = {
            "max_concurrent_repositories": 10,
            "max_prs_per_repository": 1000,
            "cache_ttl_seconds": 300,
            "use_etag_caching": True,
            "batch_size": 100,
            "discovery_timeout_seconds": 300,
            "priority_scheduling": True,
        }
        defaults.update(overrides)

        return DiscoveryConfig(**defaults)

    @staticmethod
    def create_performance_optimized(**overrides: Any) -> DiscoveryConfig:
        """
        Why: Creates configuration optimized for performance testing scenarios
        What: Generates config with higher concurrency and batch sizes
        How: Sets values suitable for load testing and performance validation
        """
        performance_overrides = {
            "max_concurrent_repositories": 20,
            "max_prs_per_repository": 2000,
            "cache_ttl_seconds": 600,
            "batch_size": 200,
            "discovery_timeout_seconds": 600,
        }
        performance_overrides.update(overrides)
        return DiscoveryConfigFactory.create(**performance_overrides)
