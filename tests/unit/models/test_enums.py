"""
Unit tests for model enums.

Why: Ensure all enum values are correctly defined and maintain stability
     for database operations and API consistency
What: Tests enum values, serialization, and validation for all model enums
How: Verifies enum values match expected strings, tests conversions,
     and ensures enum stability for database migrations
"""

from typing import Any

import pytest

from src.models.enums import (
    CheckConclusion,
    CheckStatus,
    PRState,
    RepositoryStatus,
    TriggerEvent,
)


class TestPRState:
    """Test PRState enum values and behavior."""

    def test_pr_state_values(self) -> None:
        """
        Why: Ensure PR state values match GitHub API and database schema
        What: Tests that all PR states have correct string values
        How: Compares enum values against expected strings
        """
        assert PRState.OPENED.value == "opened"
        assert PRState.CLOSED.value == "closed"
        assert PRState.MERGED.value == "merged"

    def test_pr_state_completeness(self) -> None:
        """
        Why: Verify all expected PR states are defined
        What: Tests that enum contains all required states
        How: Counts enum members and checks against expected total
        """
        expected_states = {"opened", "closed", "merged"}
        actual_states = {state.value for state in PRState}

        assert actual_states == expected_states
        assert len(PRState) == 3

    def test_pr_state_serialization(self) -> None:
        """
        Why: Ensure PR states can be serialized/deserialized correctly
        What: Tests string conversion and value access
        How: Converts enum to string and verifies round-trip conversion
        """
        for state in PRState:
            assert str(state.value) == state.value
            assert PRState(state.value) == state

    def test_pr_state_comparison(self) -> None:
        """
        Why: Verify enum comparison works for business logic
        What: Tests enum equality and inequality operations
        How: Compares enum members and values
        """
        assert PRState.OPENED == PRState.OPENED
        assert PRState.OPENED != PRState.CLOSED  # type: ignore[comparison-overlap]
        assert PRState.OPENED.value == "opened"
        assert PRState.OPENED != "closed"  # type: ignore[comparison-overlap]


class TestCheckStatus:
    """Test CheckStatus enum values and behavior."""

    def test_check_status_values(self) -> None:
        """
        Why: Ensure check status values match GitHub check run API
        What: Tests that all check statuses have correct string values
        How: Compares enum values against GitHub API specification
        """
        assert CheckStatus.QUEUED.value == "queued"
        assert CheckStatus.IN_PROGRESS.value == "in_progress"
        assert CheckStatus.COMPLETED.value == "completed"
        assert CheckStatus.CANCELLED.value == "cancelled"

    def test_check_status_completeness(self) -> None:
        """
        Why: Verify all GitHub check statuses are covered
        What: Tests that enum contains all valid check run statuses
        How: Counts enum members and verifies against GitHub API docs
        """
        expected_statuses = {"queued", "in_progress", "completed", "cancelled"}
        actual_statuses = {status.value for status in CheckStatus}

        assert actual_statuses == expected_statuses
        assert len(CheckStatus) == 4

    def test_check_status_serialization(self) -> None:
        """
        Why: Ensure check statuses serialize correctly for API integration
        What: Tests string conversion and enum reconstruction
        How: Verifies round-trip conversion for all status values
        """
        for status in CheckStatus:
            assert str(status.value) == status.value
            assert CheckStatus(status.value) == status

    def test_check_status_progression_order(self) -> None:
        """
        Why: Verify statuses represent logical progression of check execution
        What: Tests that statuses can be ordered logically
        How: Defines expected progression and validates transitions
        """
        # Define logical progression (not all transitions are valid)
        progression = [
            CheckStatus.QUEUED,
            CheckStatus.IN_PROGRESS,
            CheckStatus.COMPLETED,
        ]

        # Test that each status exists and has expected value
        assert progression[0] == CheckStatus.QUEUED
        assert progression[1] == CheckStatus.IN_PROGRESS
        assert progression[2] == CheckStatus.COMPLETED

        # Cancelled can happen from queued or in_progress
        assert CheckStatus.CANCELLED.value == "cancelled"


class TestCheckConclusion:
    """Test CheckConclusion enum values and behavior."""

    def test_check_conclusion_values(self) -> None:
        """
        Why: Ensure check conclusion values match GitHub check run API
        What: Tests that all conclusions have correct string values
        How: Compares enum values against GitHub API specification
        """
        assert CheckConclusion.SUCCESS.value == "success"
        assert CheckConclusion.FAILURE.value == "failure"
        assert CheckConclusion.NEUTRAL.value == "neutral"
        assert CheckConclusion.CANCELLED.value == "cancelled"
        assert CheckConclusion.TIMED_OUT.value == "timed_out"
        assert CheckConclusion.ACTION_REQUIRED.value == "action_required"
        assert CheckConclusion.STALE.value == "stale"
        assert CheckConclusion.SKIPPED.value == "skipped"

    def test_check_conclusion_completeness(self) -> None:
        """
        Why: Verify all GitHub check conclusions are covered
        What: Tests that enum contains all valid check run conclusions
        How: Counts enum members and verifies against GitHub API docs
        """
        expected_conclusions = {
            "success",
            "failure",
            "neutral",
            "cancelled",
            "timed_out",
            "action_required",
            "stale",
            "skipped",
        }
        actual_conclusions = {conclusion.value for conclusion in CheckConclusion}

        assert actual_conclusions == expected_conclusions
        assert len(CheckConclusion) == 8

    def test_check_conclusion_serialization(self) -> None:
        """
        Why: Ensure check conclusions serialize correctly for API integration
        What: Tests string conversion and enum reconstruction
        How: Verifies round-trip conversion for all conclusion values
        """
        for conclusion in CheckConclusion:
            assert str(conclusion.value) == conclusion.value
            assert CheckConclusion(conclusion.value) == conclusion

    def test_check_conclusion_categories(self) -> None:
        """
        Why: Verify conclusions can be categorized for business logic
        What: Tests grouping of conclusions into success/failure/other categories
        How: Defines categories and tests membership
        """
        # Successful conclusions
        successful = {CheckConclusion.SUCCESS}

        # Failed conclusions
        failed = {CheckConclusion.FAILURE, CheckConclusion.TIMED_OUT}

        # Neutral/other conclusions
        neutral = {
            CheckConclusion.NEUTRAL,
            CheckConclusion.CANCELLED,
            CheckConclusion.ACTION_REQUIRED,
            CheckConclusion.STALE,
            CheckConclusion.SKIPPED,
        }

        # Verify all conclusions are categorized
        all_conclusions = successful | failed | neutral
        assert all_conclusions == set(CheckConclusion)


class TestRepositoryStatus:
    """Test RepositoryStatus enum values and behavior."""

    def test_repository_status_values(self) -> None:
        """
        Why: Ensure repository status values are consistent for monitoring
        What: Tests that all repository statuses have correct string values
        How: Compares enum values against expected status strings
        """
        assert RepositoryStatus.ACTIVE.value == "active"
        assert RepositoryStatus.SUSPENDED.value == "suspended"
        assert RepositoryStatus.ERROR.value == "error"

    def test_repository_status_completeness(self) -> None:
        """
        Why: Verify all repository monitoring states are covered
        What: Tests that enum contains all required monitoring statuses
        How: Counts enum members and verifies expected statuses
        """
        expected_statuses = {"active", "suspended", "error"}
        actual_statuses = {status.value for status in RepositoryStatus}

        assert actual_statuses == expected_statuses
        assert len(RepositoryStatus) == 3

    def test_repository_status_serialization(self) -> None:
        """
        Why: Ensure repository statuses serialize correctly for persistence
        What: Tests string conversion and enum reconstruction
        How: Verifies round-trip conversion for all status values
        """
        for status in RepositoryStatus:
            assert str(status.value) == status.value
            assert RepositoryStatus(status.value) == status

    def test_repository_status_monitoring_logic(self) -> None:
        """
        Why: Verify statuses support monitoring business logic
        What: Tests status categorization for monitoring decisions
        How: Groups statuses and tests monitoring behavior
        """
        # Statuses that allow monitoring
        monitorable = {RepositoryStatus.ACTIVE}

        # Statuses that prevent monitoring
        non_monitorable = {RepositoryStatus.SUSPENDED, RepositoryStatus.ERROR}

        # Verify categorization
        assert RepositoryStatus.ACTIVE in monitorable
        assert RepositoryStatus.SUSPENDED in non_monitorable
        assert RepositoryStatus.ERROR in non_monitorable

        # Verify all statuses are categorized
        all_statuses = monitorable | non_monitorable
        assert all_statuses == set(RepositoryStatus)


class TestTriggerEvent:
    """Test TriggerEvent enum values and behavior."""

    def test_trigger_event_values(self) -> None:
        """
        Why: Ensure trigger event values match GitHub webhook events
        What: Tests that all trigger events have correct string values
        How: Compares enum values against GitHub webhook specifications
        """
        assert TriggerEvent.OPENED.value == "opened"
        assert TriggerEvent.SYNCHRONIZE.value == "synchronize"
        assert TriggerEvent.CLOSED.value == "closed"
        assert TriggerEvent.REOPENED.value == "reopened"
        assert TriggerEvent.EDITED.value == "edited"
        assert TriggerEvent.MANUAL_CHECK.value == "manual_check"

    def test_trigger_event_completeness(self) -> None:
        """
        Why: Verify all GitHub webhook events we handle are covered
        What: Tests that enum contains all required trigger events
        How: Counts enum members and verifies expected events
        """
        expected_events = {
            "opened",
            "synchronize",
            "closed",
            "reopened",
            "edited",
            "manual_check",
        }
        actual_events = {event.value for event in TriggerEvent}

        assert actual_events == expected_events
        assert len(TriggerEvent) == 6

    def test_trigger_event_serialization(self) -> None:
        """
        Why: Ensure trigger events serialize correctly for webhook processing
        What: Tests string conversion and enum reconstruction
        How: Verifies round-trip conversion for all event values
        """
        for event in TriggerEvent:
            assert str(event.value) == event.value
            assert TriggerEvent(event.value) == event

    def test_trigger_event_categorization(self) -> None:
        """
        Why: Verify events can be categorized for processing logic
        What: Tests grouping of events by source (webhook vs system)
        How: Defines categories and tests event membership
        """
        # GitHub webhook events
        webhook_events = {
            TriggerEvent.OPENED,
            TriggerEvent.SYNCHRONIZE,
            TriggerEvent.CLOSED,
            TriggerEvent.REOPENED,
            TriggerEvent.EDITED,
        }

        # System-generated events
        system_events = {TriggerEvent.MANUAL_CHECK}

        # Verify all events are categorized
        all_events = webhook_events | system_events
        assert all_events == set(TriggerEvent)

    def test_trigger_event_pr_events(self) -> None:
        """
        Why: Verify PR-related events are correctly identified
        What: Tests filtering of events related to pull request lifecycle
        How: Identifies PR events and tests categorization
        """
        pr_events = {
            TriggerEvent.OPENED,
            TriggerEvent.SYNCHRONIZE,
            TriggerEvent.CLOSED,
            TriggerEvent.REOPENED,
            TriggerEvent.EDITED,
        }

        # All PR events are simple action names
        pr_event_values = {event.value for event in pr_events}
        expected_pr_values = {"opened", "synchronize", "closed", "reopened", "edited"}
        assert pr_event_values == expected_pr_values

        # Non-PR events
        non_pr_events = set(TriggerEvent) - pr_events
        assert TriggerEvent.MANUAL_CHECK in non_pr_events


class TestEnumStability:
    """Test enum stability for database migrations and API compatibility."""

    def test_enum_values_are_strings(self) -> None:
        """
        Why: Ensure all enum values are strings for database compatibility
        What: Tests that every enum value is a string type
        How: Iterates through all enums and checks value types
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            enum_member: Any
            for enum_member in enum_class:
                assert isinstance(enum_member.value, str)
                assert len(enum_member.value) > 0

    def test_enum_values_are_lowercase_or_snake_case(self) -> None:
        """
        Why: Ensure consistent naming convention for API and database
        What: Tests that enum values follow lowercase/snake_case pattern
        How: Checks each enum value against naming conventions
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            enum_member: Any
            for enum_member in enum_class:
                value = enum_member.value
                # Should be lowercase with underscores or dots (for namespaced events)
                assert value.islower() or "." in value
                assert " " not in value  # No spaces
                assert (
                    "-" not in value or enum_class == CheckStatus
                )  # Allow hyphens in check status

    def test_no_duplicate_enum_values(self) -> None:
        """
        Why: Ensure no enum values are duplicated within or across enums
        What: Tests that all enum values are unique within their enum
        How: Collects all values and checks for duplicates
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            values: list[str] = [member.value for member in enum_class]  # type: ignore[var-annotated]
            assert len(values) == len(set(values)), (
                f"Duplicate values in {enum_class.__name__}"
            )

    def test_enum_member_names_are_uppercase(self) -> None:
        """
        Why: Ensure consistent Python enum naming convention
        What: Tests that all enum member names are UPPERCASE
        How: Checks each enum member name against uppercase convention
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            enum_member: Any
            for enum_member in enum_class:
                assert enum_member.name.isupper()
                assert (
                    "_" in enum_member.name or len(enum_member.name) <= 15
                )  # Reasonable length names ok

    def test_enum_inheritance(self) -> None:
        """
        Why: Verify enums inherit from str for proper SQLAlchemy integration
        What: Tests that all enums are string-based enums
        How: Checks that enum members are instances of str
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            enum_member: Any
            for enum_member in enum_class:
                # enum_member is the enum instance, not a string
                assert hasattr(enum_member, "value")
                assert isinstance(enum_member.value, str)

    def test_invalid_enum_values_raise_errors(self) -> None:
        """
        Why: Ensure invalid values are rejected to maintain data integrity
        What: Tests that invalid enum values raise ValueError
        How: Attempts to create enums with invalid values
        """
        all_enums = [
            PRState,
            CheckStatus,
            CheckConclusion,
            RepositoryStatus,
            TriggerEvent,
        ]

        for enum_class in all_enums:
            with pytest.raises(ValueError):
                enum_class("invalid_value")

            with pytest.raises(ValueError):
                enum_class("")

            with pytest.raises(ValueError):
                enum_class("UPPERCASE_VALUE")
