"""Persistence boundary for read-only Project dashboard aggregates."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Protocol

from project_board.domain import (
    DashboardCommentCounts,
    DashboardDueCounts,
    DashboardTagCount,
    DashboardTaskCounts,
    TaskCommentActivity,
)
from project_board.domain.dashboard import DashboardInvariantError


@dataclass(frozen=True, slots=True)
class DashboardDueQuery:
    """UTC boundaries for the dashboard's mutually exclusive due buckets."""

    as_of: datetime
    today_end: datetime
    upcoming_end: datetime

    def __post_init__(self) -> None:
        for field_name in ("as_of", "today_end", "upcoming_end"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise DashboardInvariantError(
                    f"Dashboard due {field_name} must be a datetime"
                )
            if value.tzinfo is not UTC:
                raise DashboardInvariantError(
                    f"Dashboard due {field_name} must be normalized to UTC"
                )

        expected_today_end = datetime.combine(
            self.as_of.date() + timedelta(days=1), time.min, tzinfo=UTC
        )
        if self.today_end != expected_today_end:
            raise DashboardInvariantError(
                "Dashboard today_end must be the next UTC midnight"
            )
        if self.upcoming_end != self.today_end + timedelta(days=7):
            raise DashboardInvariantError(
                "Dashboard upcoming_end must be seven days after today_end"
            )


class ProjectDashboardRepository(Protocol):
    """Set-based, ownership-aware queries used to assemble one dashboard."""

    def get_task_counts(self, project_id: int) -> DashboardTaskCounts:
        """Return zero-inclusive Task status and priority aggregates."""
        ...

    def get_due_counts(
        self, project_id: int, query: DashboardDueQuery
    ) -> DashboardDueCounts:
        """Return mutually exclusive due aggregates for active Tasks."""
        ...

    def list_tag_counts(self, project_id: int) -> tuple[DashboardTagCount, ...]:
        """Return every owned Tag with its distinct owned Task count."""
        ...

    def get_comment_counts(self, project_id: int) -> DashboardCommentCounts:
        """Return current Comment totals for owned Tasks."""
        ...

    def list_recent_activities(
        self, project_id: int, limit: int
    ) -> tuple[TaskCommentActivity, ...]:
        """Return bounded payload-free activity in deterministic order."""
        ...
