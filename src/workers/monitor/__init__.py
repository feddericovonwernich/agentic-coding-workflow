"""PR Monitor Worker - Data models and interfaces.

This package provides data models and abstract interfaces for the PR Monitor Worker,
which is responsible for discovering pull requests and check runs from GitHub
repositories, detecting state changes, and synchronizing data with the local database.

The package follows a clean architecture pattern with clear separation between:
- Data models: Immutable data structures for type safety
- Interfaces: Abstract base classes defining contracts between components
- Validation: Comprehensive data integrity checks
- Error handling: Integration with existing GitHub API exception hierarchy

Main Components:
- Data Models: ProcessingMetrics, DiscoveryResult, CheckRunDiscovery,
  StateChangeEvent, SyncOperation
- Interfaces: PRDiscoveryInterface, CheckRunDiscoveryInterface,
  StateDetectorInterface, DataSynchronizerInterface

All models are designed to integrate seamlessly with existing SQLAlchemy
models and provide comprehensive debugging and serialization capabilities.
"""

from .models import (
    # Enums
    ChangeType,
    # Data Models
    CheckRunDiscovery,
    # Abstract Interfaces
    CheckRunDiscoveryInterface,
    DataSynchronizerInterface,
    DiscoveryResult,
    OperationStatus,
    PRDiscoveryInterface,
    ProcessingMetrics,
    SeverityLevel,
    StateChangeEvent,
    StateDetectorInterface,
    SyncOperation,
)

__all__ = [
    # Enums
    "ChangeType",
    # Data Models
    "CheckRunDiscovery",
    # Abstract Interfaces
    "CheckRunDiscoveryInterface",
    "DataSynchronizerInterface",
    "DiscoveryResult",
    "OperationStatus",
    "PRDiscoveryInterface",
    "ProcessingMetrics",
    "SeverityLevel",
    "StateChangeEvent",
    "StateDetectorInterface",
    "SyncOperation",
]

# Package metadata
__version__ = "1.0.0"
__author__ = "Agentic Coding Workflow System"
__description__ = "Data models and interfaces for PR monitoring operations"
