"""
Configuration Tools Package

This package provides command-line tools for working with configuration files:

- validate.py: Comprehensive configuration validation
- diff.py: Configuration comparison and difference analysis

These tools can be used during development, deployment, and maintenance
to ensure configuration correctness and track changes between environments.
"""

from .diff import ConfigDiff, ConfigurationDiffer, DiffSeverity, DiffType
from .validate import ConfigurationValidator

__all__ = [
    "ConfigDiff",
    "ConfigurationDiffer",
    "ConfigurationValidator",
    "DiffSeverity",
    "DiffType",
]
