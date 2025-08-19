"""Enums for database models."""

import enum


class PRState(str, enum.Enum):
    """Pull request state enum."""

    OPENED = "opened"
    CLOSED = "closed"
    MERGED = "merged"


class CheckStatus(str, enum.Enum):
    """Check run status enum."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CheckConclusion(str, enum.Enum):
    """Check run conclusion enum."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    STALE = "stale"
    SKIPPED = "skipped"


class RepositoryStatus(str, enum.Enum):
    """Repository status enum."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ERROR = "error"


class TriggerEvent(str, enum.Enum):
    """Trigger event enum for state transitions."""

    OPENED = "opened"
    SYNCHRONIZE = "synchronize"
    CLOSED = "closed"
    REOPENED = "reopened"
    EDITED = "edited"
    MANUAL_CHECK = "manual_check"
