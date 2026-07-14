"""Framework-independent Project dashboard values and invariants."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TypeVar

from project_board.domain.comment import TaskCommentActivity
from project_board.domain.task import (
    TERMINAL_TASK_STATUSES,
    TaskPriority,
    TaskStatus,
)

CountKey = TypeVar("CountKey", TaskStatus, TaskPriority)


class DashboardInvariantError(ValueError):
    """Raised when repository aggregates violate the dashboard contract."""


def _count(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DashboardInvariantError(
            f"Dashboard {field_name} must be a non-negative integer"
        )
    return value


def _positive_id(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DashboardInvariantError(
            f"Dashboard {field_name} must be a positive integer"
        )
    return value


def _ordered_counts(
    values: Mapping[CountKey, int],
    expected: tuple[CountKey, ...],
    field_name: str,
) -> Mapping[CountKey, int]:
    if tuple(values) != expected:
        raise DashboardInvariantError(
            f"Dashboard {field_name} must contain every key in enum order"
        )
    return MappingProxyType(
        {key: _count(values[key], f"{field_name}.{key.value}") for key in expected}
    )


@dataclass(frozen=True, slots=True)
class DashboardTaskCounts:
    """Zero-inclusive Task totals grouped in stable enum order."""

    total: int
    by_status: Mapping[TaskStatus, int]
    by_priority: Mapping[TaskPriority, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "total", _count(self.total, "tasks.total"))
        object.__setattr__(
            self,
            "by_status",
            _ordered_counts(self.by_status, tuple(TaskStatus), "tasks.by_status"),
        )
        object.__setattr__(
            self,
            "by_priority",
            _ordered_counts(self.by_priority, tuple(TaskPriority), "tasks.by_priority"),
        )
        if sum(self.by_status.values()) != self.total:
            raise DashboardInvariantError(
                "Dashboard status counts must sum to Task total"
            )
        if sum(self.by_priority.values()) != self.total:
            raise DashboardInvariantError(
                "Dashboard priority counts must sum to Task total"
            )

    @property
    def terminal_total(self) -> int:
        """Return the number of Tasks excluded from due aggregates."""
        return sum(self.by_status[status] for status in TERMINAL_TASK_STATUSES)


@dataclass(frozen=True, slots=True)
class DashboardDueCounts:
    """Mutually exclusive due buckets for active Tasks."""

    active_total: int
    overdue: int
    due_today: int
    upcoming_7_days: int
    later: int
    no_due_date: int

    def __post_init__(self) -> None:
        for field_name in (
            "active_total",
            "overdue",
            "due_today",
            "upcoming_7_days",
            "later",
            "no_due_date",
        ):
            object.__setattr__(
                self,
                field_name,
                _count(getattr(self, field_name), f"due.{field_name}"),
            )
        bucket_total = (
            self.overdue
            + self.due_today
            + self.upcoming_7_days
            + self.later
            + self.no_due_date
        )
        if bucket_total != self.active_total:
            raise DashboardInvariantError(
                "Dashboard due buckets must sum to active total"
            )


@dataclass(frozen=True, slots=True)
class DashboardTagCount:
    """An owned Tag and its distinct owned Task-association count."""

    id: int
    name: str
    normalized_name: str
    task_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _positive_id(self.id, "tag id"))
        if not isinstance(self.name, str) or not self.name:
            raise DashboardInvariantError("Dashboard tag name must not be empty")
        if not isinstance(self.normalized_name, str) or not self.normalized_name:
            raise DashboardInvariantError(
                "Dashboard tag normalized_name must not be empty"
            )
        object.__setattr__(
            self, "task_count", _count(self.task_count, "tag task_count")
        )


@dataclass(frozen=True, slots=True)
class DashboardCommentCounts:
    """Current Comment totals for owned Tasks."""

    total: int
    tasks_with_comments: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "total", _count(self.total, "comments.total"))
        object.__setattr__(
            self,
            "tasks_with_comments",
            _count(self.tasks_with_comments, "comments.tasks_with_comments"),
        )
        if self.tasks_with_comments > self.total:
            raise DashboardInvariantError(
                "Dashboard Tasks with Comments must not exceed Comment total"
            )


@dataclass(frozen=True, slots=True)
class ProjectDashboard:
    """Complete immutable dashboard result returned by the application layer."""

    project_id: int
    as_of: datetime
    tasks: DashboardTaskCounts
    due: DashboardDueCounts
    tags: tuple[DashboardTagCount, ...]
    comments: DashboardCommentCounts
    recent_activities: tuple[TaskCommentActivity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "project_id", _positive_id(self.project_id, "project_id")
        )
        if not isinstance(self.as_of, datetime):
            raise DashboardInvariantError("Dashboard as_of must be a datetime")
        if self.as_of.tzinfo is not UTC:
            raise DashboardInvariantError(
                "Dashboard as_of must be timezone-aware and normalized to UTC"
            )
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "recent_activities", tuple(self.recent_activities))

        if self.due.active_total != self.tasks.total - self.tasks.terminal_total:
            raise DashboardInvariantError(
                "Dashboard active total must exclude exactly the terminal Tasks"
            )
        tag_order = tuple((tag.normalized_name, tag.id) for tag in self.tags)
        if tag_order != tuple(sorted(tag_order)):
            raise DashboardInvariantError(
                "Dashboard Tags must be ordered by normalized name and ID"
            )
        if any(
            activity.project_id != self.project_id
            for activity in self.recent_activities
        ):
            raise DashboardInvariantError(
                "Dashboard activities must belong to the requested Project"
            )
        activity_order = tuple(
            (activity.occurred_at, activity.id) for activity in self.recent_activities
        )
        if activity_order != tuple(sorted(activity_order, reverse=True)):
            raise DashboardInvariantError(
                "Dashboard activities must be ordered by occurred_at and ID descending"
            )
