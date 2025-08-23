"""
Test fixtures and factories for PR Discovery and Processing components.

This module provides comprehensive test fixtures, factories, and utilities
for testing all discovery components including PR scanning, check discovery,
state detection, and data synchronization.
"""

from .factories import (
    DiscoveredCheckRunFactory,
    DiscoveredPRFactory,
    DiscoveryConfigFactory,
    DiscoveryErrorFactory,
    PRDiscoveryResultFactory,
    RepositoryStateFactory,
    StateChangeFactory,
    StoredPRStateFactory,
    SynchronizationResultFactory,
)
from .mock_data import (
    MockDiscoveryResponses,
    MockGitHubAPIResponses,
    create_mock_github_check_runs_response,
    create_mock_github_pr_response,
    create_realistic_check_run_data,
    create_realistic_pr_data,
)

__all__ = [
    "DiscoveredCheckRunFactory",
    # Factories
    "DiscoveredPRFactory",
    "DiscoveryConfigFactory",
    "DiscoveryErrorFactory",
    # Mock Data
    "MockDiscoveryResponses",
    "MockGitHubAPIResponses",
    "PRDiscoveryResultFactory",
    "RepositoryStateFactory",
    "StateChangeFactory",
    "StoredPRStateFactory",
    "SynchronizationResultFactory",
    "create_mock_github_check_runs_response",
    "create_mock_github_pr_response",
    "create_realistic_check_run_data",
    "create_realistic_pr_data",
]
