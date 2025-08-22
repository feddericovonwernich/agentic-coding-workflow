"""Monitor worker package for PR discovery and processing.

This module implements the core PR discovery and processing engine that:
1. Fetches PRs and check runs from GitHub repositories
2. Detects state changes between GitHub and database
3. Synchronizes changes to the database
4. Provides comprehensive error handling and reporting

Main Classes:
- PRProcessor: Core processing engine
- PRDiscoveryEngine: GitHub API discovery
- StateChangeDetector: Change detection logic
- DataSynchronizer: Database synchronization
"""

from .change_detection import StateChangeDetector
from .discovery import PRDiscoveryEngine
from .models import (
    ChangeSet,
    CheckRunData,
    PRData,
    ProcessingError,
    ProcessingResult,
    RepositoryConfig,
    StateChange,
)
from .processor import PRProcessor
from .synchronization import DataSynchronizer

__all__ = [
    # Core processor
    "PRProcessor",
    
    # Component classes
    "PRDiscoveryEngine", 
    "StateChangeDetector",
    "DataSynchronizer",
    
    # Data models
    "PRData",
    "CheckRunData", 
    "RepositoryConfig",
    "ProcessingResult",
    "ProcessingError",
    "ChangeSet",
    "StateChange",
]