#!/usr/bin/env python3
"""
Configuration Diff Tool

This tool compares configuration files between different environments,
highlighting differences, security concerns, and providing migration guidance.

Usage:
    python -m src.config.tools.diff [options] config1.yaml config2.yaml
    python src/config/tools/diff.py [options] config1.yaml config2.yaml
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class DiffType(Enum):
    """Types of configuration differences."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    TYPE_CHANGED = "type_changed"


class DiffSeverity(Enum):
    """Severity levels for configuration differences."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ConfigDiff:
    """Represents a single configuration difference."""

    path: str
    diff_type: DiffType
    old_value: Any
    new_value: Any
    severity: DiffSeverity
    description: str
    recommendations: list[str]


class ConfigurationDiffer:
    """Compare configuration files and identify differences."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.diffs: list[ConfigDiff] = []

        # Security-sensitive paths that require special attention
        self.security_sensitive_paths = {
            "database.url",
            "queue.url",
            "llm.*.api_key",
            "notification.channels.*.telegram_bot_token",
            "notification.channels.*.slack_webhook_url",
            "notification.channels.*.email_password",
            "repositories.*.auth_token",
        }

        # Performance-critical paths
        self.performance_critical_paths = {
            "database.pool_size",
            "database.max_overflow",
            "database.pool_timeout",
            "queue.batch_size",
            "queue.visibility_timeout",
            "system.worker_timeout",
            "system.max_retry_attempts",
            "llm.*.timeout",
            "llm.*.rate_limit_rpm",
        }

    def compare_configs(self, config1_path: str, config2_path: str) -> list[ConfigDiff]:
        """
        Compare two configuration files and return list of differences.

        Args:
            config1_path: Path to first configuration file (baseline)
            config2_path: Path to second configuration file (comparison)

        Returns:
            List of ConfigDiff objects representing differences
        """
        self.diffs.clear()

        # Load configuration files
        config1 = self._load_config_file(config1_path)
        config2 = self._load_config_file(config2_path)

        if config1 is None or config2 is None:
            return self.diffs

        # Perform deep comparison
        self._compare_nested_dicts(config1, config2, "")

        # Sort diffs by severity and path
        self.diffs.sort(key=lambda d: (d.severity.value, d.path))

        return self.diffs

    def _load_config_file(self, file_path: str) -> dict[Any, Any] | None:
        """Load and parse a configuration file."""
        try:
            if not os.path.exists(file_path):
                self.diffs.append(
                    ConfigDiff(
                        path=file_path,
                        diff_type=DiffType.REMOVED,
                        old_value=None,
                        new_value=None,
                        severity=DiffSeverity.CRITICAL,
                        description=f"Configuration file not found: {file_path}",
                        recommendations=[
                            "Ensure the configuration file exists and is accessible"
                        ],
                    )
                )
                return None

            with open(file_path) as f:
                config = yaml.safe_load(f)

            if self.verbose:
                print(f"✅ Loaded configuration: {file_path}")

            # Ensure we return a dict or None
            if config is None:
                return None
            if not isinstance(config, dict):
                self.diffs.append(
                    ConfigDiff(
                        path=file_path,
                        diff_type=DiffType.CHANGED,
                        old_value=None,
                        new_value=None,
                        severity=DiffSeverity.CRITICAL,
                        description=f"Configuration file is not a dict: {file_path}",
                        recommendations=[
                            "Ensure the configuration file contains a YAML dict at the "
                            "root level"
                        ],
                    )
                )
                return None
            return config

        except yaml.YAMLError as e:
            self.diffs.append(
                ConfigDiff(
                    path=file_path,
                    diff_type=DiffType.CHANGED,
                    old_value=None,
                    new_value=None,
                    severity=DiffSeverity.CRITICAL,
                    description=f"YAML parsing error in {file_path}: {e}",
                    recommendations=[
                        "Fix YAML syntax errors in the configuration file"
                    ],
                )
            )
            return None
        except Exception as e:
            self.diffs.append(
                ConfigDiff(
                    path=file_path,
                    diff_type=DiffType.CHANGED,
                    old_value=None,
                    new_value=None,
                    severity=DiffSeverity.CRITICAL,
                    description=f"Error loading {file_path}: {e}",
                    recommendations=["Check file permissions and accessibility"],
                )
            )
            return None

    def _compare_nested_dicts(
        self, dict1: dict[Any, Any], dict2: dict[Any, Any], path: str
    ) -> None:
        """Recursively compare nested dictionaries."""
        # Get all keys from both dictionaries
        all_keys = set(dict1.keys()) | set(dict2.keys())

        for key in all_keys:
            current_path = f"{path}.{key}" if path else key

            if key not in dict1:
                # Key added in dict2
                self._handle_added_key(current_path, dict2[key])
            elif key not in dict2:
                # Key removed from dict1
                self._handle_removed_key(current_path, dict1[key])
            else:
                # Key exists in both, compare values
                self._compare_values(current_path, dict1[key], dict2[key])

    def _compare_values(self, path: str, value1: Any, value2: Any) -> None:
        """Compare two values and handle differences."""
        if type(value1) is not type(value2):
            # Type changed
            self._handle_type_change(path, value1, value2)
        elif isinstance(value1, dict) and isinstance(value2, dict):
            # Both are dictionaries, recurse
            self._compare_nested_dicts(value1, value2, path)
        elif isinstance(value1, list) and isinstance(value2, list):
            # Both are lists, compare
            self._compare_lists(path, value1, value2)
        elif value1 != value2:
            # Values are different
            self._handle_value_change(path, value1, value2)

    def _compare_lists(self, path: str, list1: list, list2: list) -> None:
        """Compare two lists."""
        if len(list1) != len(list2):
            self._handle_value_change(path, list1, list2)
            return

        # Compare each element
        for i, (item1, item2) in enumerate(zip(list1, list2, strict=False)):
            item_path = f"{path}[{i}]"
            self._compare_values(item_path, item1, item2)

    def _handle_added_key(self, path: str, value: Any) -> None:
        """Handle a key that was added."""
        severity = self._determine_severity(path, DiffType.ADDED, None, value)
        description = f"New configuration key added: {path}"
        recommendations = self._get_recommendations(path, DiffType.ADDED, None, value)

        self.diffs.append(
            ConfigDiff(
                path=path,
                diff_type=DiffType.ADDED,
                old_value=None,
                new_value=value,
                severity=severity,
                description=description,
                recommendations=recommendations,
            )
        )

    def _handle_removed_key(self, path: str, value: Any) -> None:
        """Handle a key that was removed."""
        severity = self._determine_severity(path, DiffType.REMOVED, value, None)
        description = f"Configuration key removed: {path}"
        recommendations = self._get_recommendations(path, DiffType.REMOVED, value, None)

        self.diffs.append(
            ConfigDiff(
                path=path,
                diff_type=DiffType.REMOVED,
                old_value=value,
                new_value=None,
                severity=severity,
                description=description,
                recommendations=recommendations,
            )
        )

    def _handle_value_change(self, path: str, old_value: Any, new_value: Any) -> None:
        """Handle a value that changed."""
        severity = self._determine_severity(
            path, DiffType.CHANGED, old_value, new_value
        )
        description = f"Configuration value changed: {path}"
        recommendations = self._get_recommendations(
            path, DiffType.CHANGED, old_value, new_value
        )

        self.diffs.append(
            ConfigDiff(
                path=path,
                diff_type=DiffType.CHANGED,
                old_value=old_value,
                new_value=new_value,
                severity=severity,
                description=description,
                recommendations=recommendations,
            )
        )

    def _handle_type_change(self, path: str, old_value: Any, new_value: Any) -> None:
        """Handle a value type that changed."""
        severity = DiffSeverity.HIGH  # Type changes are usually significant
        description = (
            f"Configuration value type changed: {path} "
            f"({type(old_value).__name__} → {type(new_value).__name__})"
        )
        recommendations = [
            "Review the schema to ensure the new type is correct",
            "Update any code that depends on the old type",
            "Test thoroughly to ensure compatibility",
        ]

        self.diffs.append(
            ConfigDiff(
                path=path,
                diff_type=DiffType.TYPE_CHANGED,
                old_value=old_value,
                new_value=new_value,
                severity=severity,
                description=description,
                recommendations=recommendations,
            )
        )

    def _determine_severity(
        self, path: str, diff_type: DiffType, old_value: Any, new_value: Any
    ) -> DiffSeverity:
        """Determine the severity of a configuration difference."""
        # Check if this is a security-sensitive path
        if self._is_security_sensitive(path):
            if diff_type == DiffType.REMOVED:
                return DiffSeverity.CRITICAL
            else:
                return DiffSeverity.HIGH

        # Check if this is a performance-critical path
        if self._is_performance_critical(path):
            return DiffSeverity.MEDIUM

        # Check specific path patterns
        if path.startswith("system.environment"):
            return DiffSeverity.HIGH

        if path.startswith("system.debug_mode") and new_value is True:
            return DiffSeverity.MEDIUM

        if (
            "password" in path.lower()
            or "secret" in path.lower()
            or "token" in path.lower()
        ):
            return DiffSeverity.HIGH

        if path.startswith("repositories") and diff_type in [
            DiffType.ADDED,
            DiffType.REMOVED,
        ]:
            return DiffSeverity.MEDIUM

        if path.endswith(".enabled") and diff_type == DiffType.CHANGED:
            return DiffSeverity.MEDIUM

        # Default severity
        return DiffSeverity.LOW

    def _is_security_sensitive(self, path: str) -> bool:
        """Check if a path is security-sensitive."""
        for sensitive_path in self.security_sensitive_paths:
            if self._path_matches_pattern(path, sensitive_path):
                return True
        return False

    def _is_performance_critical(self, path: str) -> bool:
        """Check if a path is performance-critical."""
        for critical_path in self.performance_critical_paths:
            if self._path_matches_pattern(path, critical_path):
                return True
        return False

    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if a path matches a pattern (supporting * wildcards)."""
        import re

        # Convert pattern to regex
        regex_pattern = pattern.replace("*", "[^.]+")
        regex_pattern = f"^{regex_pattern}$"

        return bool(re.match(regex_pattern, path))

    def _get_recommendations(
        self, path: str, diff_type: DiffType, old_value: Any, new_value: Any
    ) -> list[str]:
        """Get recommendations for handling a specific difference."""
        recommendations = []

        # General recommendations based on diff type
        if diff_type == DiffType.ADDED:
            recommendations.append(
                "Verify that the new configuration is intentional and "
                "properly documented"
            )
            if self._is_security_sensitive(path):
                recommendations.append(
                    "Ensure new security-sensitive values use environment variables"
                )

        elif diff_type == DiffType.REMOVED:
            recommendations.append(
                "Confirm that removing this configuration is intentional"
            )
            recommendations.append(
                "Check for any code that might depend on this configuration"
            )
            if self._is_security_sensitive(path):
                recommendations.append(
                    "CRITICAL: Security-sensitive configuration removed - "
                    "verify this is safe"
                )

        elif diff_type == DiffType.CHANGED:
            if self._is_security_sensitive(path):
                recommendations.append(
                    "Security-sensitive value changed - verify credentials are correct"
                )
                recommendations.append("Test connectivity with new credentials")

            if self._is_performance_critical(path):
                recommendations.append(
                    "Performance-critical value changed - monitor system performance"
                )
                if isinstance(old_value, int | float) and isinstance(
                    new_value, int | float
                ):
                    change_percent = (
                        abs((new_value - old_value) / old_value * 100)
                        if old_value != 0
                        else 100
                    )
                    if change_percent > 50:
                        recommendations.append(
                            f"Large change ({change_percent:.1f}%) - "
                            f"consider gradual rollout"
                        )

        # Specific recommendations based on path
        if path.startswith("database"):
            recommendations.append("Test database connectivity after applying changes")
            if "pool" in path:
                recommendations.append("Monitor database connection pool metrics")

        elif path.startswith("llm"):
            recommendations.append("Test LLM provider connectivity and functionality")
            if "rate_limit" in path:
                recommendations.append("Monitor API rate limit usage")

        elif path.startswith("notification"):
            recommendations.append("Test notification delivery")

        elif path.startswith("repositories"):
            recommendations.append("Test repository monitoring and GitHub API access")

        elif path == "system.environment":
            recommendations.append(
                "CRITICAL: Environment changed - ensure deployment target is correct"
            )
            recommendations.append("Review all environment-specific configurations")

        elif path == "system.debug_mode" and new_value is True:
            recommendations.append("Debug mode enabled - ensure this is not production")
            recommendations.append(
                "Debug mode may expose sensitive information in logs"
            )

        # Default recommendation if none added
        if not recommendations:
            recommendations.append("Review change for correctness and test thoroughly")

        return recommendations

    def generate_summary(self) -> dict[str, Any]:
        """Generate a summary of all differences."""
        summary: dict[str, Any] = {
            "total_differences": len(self.diffs),
            "by_type": {},
            "by_severity": {},
            "critical_changes": [],
            "security_changes": [],
            "performance_changes": [],
        }

        # Count by type
        by_type: dict[str, int] = {}
        for diff_type in DiffType:
            count = sum(1 for d in self.diffs if d.diff_type == diff_type)
            by_type[diff_type.value] = count
        summary["by_type"] = by_type

        # Count by severity
        by_severity: dict[str, int] = {}
        for severity in DiffSeverity:
            count = sum(1 for d in self.diffs if d.severity == severity)
            by_severity[severity.value] = count
        summary["by_severity"] = by_severity

        # Identify critical, security, and performance changes
        critical_changes: list[dict[str, str]] = []
        security_changes: list[dict[str, str]] = []
        performance_changes: list[dict[str, str]] = []

        for diff in self.diffs:
            if diff.severity == DiffSeverity.CRITICAL:
                critical_changes.append(
                    {
                        "path": diff.path,
                        "type": diff.diff_type.value,
                        "description": diff.description,
                    }
                )

            if self._is_security_sensitive(diff.path):
                security_changes.append(
                    {
                        "path": diff.path,
                        "type": diff.diff_type.value,
                        "description": diff.description,
                    }
                )

            if self._is_performance_critical(diff.path):
                performance_changes.append(
                    {
                        "path": diff.path,
                        "type": diff.diff_type.value,
                        "description": diff.description,
                    }
                )

        summary["critical_changes"] = critical_changes
        summary["security_changes"] = security_changes
        summary["performance_changes"] = performance_changes

        return summary

    def mask_sensitive_values(self, diffs: list[ConfigDiff]) -> list[ConfigDiff]:
        """Mask sensitive values in diffs for safe display."""
        masked_diffs = []

        for diff in diffs:
            masked_diff = ConfigDiff(
                path=diff.path,
                diff_type=diff.diff_type,
                old_value=self._mask_value(diff.path, diff.old_value),
                new_value=self._mask_value(diff.path, diff.new_value),
                severity=diff.severity,
                description=diff.description,
                recommendations=diff.recommendations,
            )
            masked_diffs.append(masked_diff)

        return masked_diffs

    def _mask_value(self, path: str, value: Any) -> Any:
        """Mask a value if it's sensitive."""
        if value is None:
            return None

        # Check for sensitive paths
        sensitive_keywords = ["password", "secret", "token", "key", "credential"]

        if any(keyword in path.lower() for keyword in sensitive_keywords):
            if isinstance(value, str) and len(value) > 0:
                if len(value) <= 4:
                    return "*" * len(value)
                else:
                    return value[:2] + "*" * (len(value) - 4) + value[-2:]
            else:
                return "***MASKED***"

        return value


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare Agentic Coding Workflow configuration files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare development and production configs
  python -m src.config.tools.diff config/examples/development.yaml \
      config/examples/production.yaml
  # Compare with detailed output
  python -m src.config.tools.diff --verbose --show-values config1.yaml config2.yaml
  # Get JSON output for automation
  python -m src.config.tools.diff --json config1.yaml config2.yaml
  # Focus on security and performance changes
  python -m src.config.tools.diff --security-focus config1.yaml config2.yaml""",
    )

    parser.add_argument("config1", help="First configuration file (baseline)")

    parser.add_argument("config2", help="Second configuration file (comparison)")

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    parser.add_argument(
        "--show-values",
        action="store_true",
        help="Show actual values in output (may expose sensitive data)",
    )

    parser.add_argument(
        "--security-focus",
        action="store_true",
        help="Focus on security-related changes",
    )

    parser.add_argument(
        "--performance-focus",
        action="store_true",
        help="Focus on performance-related changes",
    )

    parser.add_argument(
        "--severity-filter",
        choices=[s.value for s in DiffSeverity],
        help="Filter by minimum severity level",
    )

    args = parser.parse_args()

    # Run comparison
    differ = ConfigurationDiffer(args.verbose)

    try:
        diffs = differ.compare_configs(args.config1, args.config2)

        # Apply filters
        filtered_diffs = diffs

        if args.security_focus:
            filtered_diffs = [
                d for d in filtered_diffs if differ._is_security_sensitive(d.path)
            ]

        if args.performance_focus:
            filtered_diffs = [
                d for d in filtered_diffs if differ._is_performance_critical(d.path)
            ]

        if args.severity_filter:
            min_severity = DiffSeverity(args.severity_filter)
            severity_order = [
                DiffSeverity.LOW,
                DiffSeverity.MEDIUM,
                DiffSeverity.HIGH,
                DiffSeverity.CRITICAL,
            ]
            min_level = severity_order.index(min_severity)
            filtered_diffs = [
                d
                for d in filtered_diffs
                if severity_order.index(d.severity) >= min_level
            ]

        # Mask sensitive values unless explicitly requested
        if not args.show_values:
            filtered_diffs = differ.mask_sensitive_values(filtered_diffs)

        # Generate summary
        summary = differ.generate_summary()

        # Output results
        if args.json:
            result = {
                "comparison": {"config1": args.config1, "config2": args.config2},
                "summary": summary,
                "differences": [
                    {
                        "path": d.path,
                        "type": d.diff_type.value,
                        "severity": d.severity.value,
                        "description": d.description,
                        "old_value": d.old_value,
                        "new_value": d.new_value,
                        "recommendations": d.recommendations,
                    }
                    for d in filtered_diffs
                ],
            }
            print(json.dumps(result, indent=2, default=str))
        else:
            # Human-readable output
            print("\n📋 Configuration Comparison Report")
            print(f"{'=' * 60}")
            print(f"Baseline:   {args.config1}")
            print(f"Comparison: {args.config2}")

            print("\n📊 SUMMARY:")
            print(f"  Total differences: {summary['total_differences']}")
            print(f"  Critical: {summary['by_severity'].get('critical', 0)}")
            print(f"  High:     {summary['by_severity'].get('high', 0)}")
            print(f"  Medium:   {summary['by_severity'].get('medium', 0)}")
            print(f"  Low:      {summary['by_severity'].get('low', 0)}")

            if summary["critical_changes"]:
                print("\n🚨 CRITICAL CHANGES:")
                for change in summary["critical_changes"]:
                    print(f"  • {change['path']} ({change['type']})")

            if summary["security_changes"]:
                print("\n🔒 SECURITY CHANGES:")
                for change in summary["security_changes"]:
                    print(f"  • {change['path']} ({change['type']})")

            if summary["performance_changes"]:
                print("\n⚡ PERFORMANCE CHANGES:")
                for change in summary["performance_changes"]:
                    print(f"  • {change['path']} ({change['type']})")

            if filtered_diffs:
                print("\n📝 DETAILED DIFFERENCES:")

                for diff in filtered_diffs:
                    severity_emoji = {
                        DiffSeverity.CRITICAL: "🚨",
                        DiffSeverity.HIGH: "🔴",
                        DiffSeverity.MEDIUM: "🟡",
                        DiffSeverity.LOW: "🟢",
                    }

                    type_emoji = {
                        DiffType.ADDED: "+",
                        DiffType.REMOVED: "-",
                        DiffType.CHANGED: "🔄",
                        DiffType.TYPE_CHANGED: "🔀",
                    }

                    severity_icon = severity_emoji[diff.severity]
                    type_icon = type_emoji[diff.diff_type]
                    print(f"\n{severity_icon} {type_icon} {diff.path}")
                    print(f"   {diff.description}")

                    if diff.diff_type == DiffType.CHANGED:
                        print(f"   Old: {diff.old_value}")
                        print(f"   New: {diff.new_value}")
                    elif diff.diff_type == DiffType.ADDED:
                        print(f"   Added: {diff.new_value}")
                    elif diff.diff_type == DiffType.REMOVED:
                        print(f"   Removed: {diff.old_value}")
                    elif diff.diff_type == DiffType.TYPE_CHANGED:
                        print(
                            f"   {type(diff.old_value).__name__} → "
                            f"{type(diff.new_value).__name__}"
                        )

                    if diff.recommendations:
                        print("   Recommendations:")
                        for rec in diff.recommendations:
                            print(f"   • {rec}")
            else:
                print("\n✅ No differences found (or all filtered out)")

        # Exit with appropriate code
        critical_count = summary["by_severity"].get("critical", 0)
        sys.exit(1 if critical_count > 0 else 0)

    except KeyboardInterrupt:
        print("\n⚠️  Comparison interrupted by user")
        sys.exit(1)
    except Exception as e:
        if args.json:
            result = {
                "comparison": {"config1": args.config1, "config2": args.config2},
                "error": str(e),
                "summary": {},
                "differences": [],
            }
            print(json.dumps(result, indent=2))
        else:
            print(f"\n💥 Fatal error during comparison: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
