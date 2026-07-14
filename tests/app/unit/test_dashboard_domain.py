from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import (
    TERMINAL_TASK_STATUSES,
    DashboardCommentCounts,
    DashboardDueCounts,
    DashboardInvariantError,
    DashboardTaskCounts,
    ProjectDashboard,
    TaskPriority,
    TaskStatus,
    is_terminal_task_status,
)


def make_task_counts(**changes: object) -> DashboardTaskCounts:
    values = {
        "total": 3,
        "by_status": {
            TaskStatus.TODO: 1,
            TaskStatus.IN_PROGRESS: 1,
            TaskStatus.DONE: 1,
        },
        "by_priority": {
            TaskPriority.LOW: 1,
            TaskPriority.MEDIUM: 1,
            TaskPriority.HIGH: 1,
        },
    }
    values.update(changes)
    return DashboardTaskCounts(**values)  # type: ignore[arg-type]


def make_due_counts(**changes: int) -> DashboardDueCounts:
    values = {
        "active_total": 2,
        "overdue": 1,
        "due_today": 1,
        "upcoming_7_days": 0,
        "later": 0,
        "no_due_date": 0,
    }
    values.update(changes)
    return DashboardDueCounts(**values)


def test_done_is_the_only_terminal_task_status() -> None:
    assert frozenset({TaskStatus.DONE}) == TERMINAL_TASK_STATUSES
    assert [status for status in TaskStatus if is_terminal_task_status(status)] == [
        TaskStatus.DONE
    ]


def test_task_counts_preserve_enum_order_and_are_immutable() -> None:
    counts = make_task_counts()

    assert tuple(counts.by_status) == tuple(TaskStatus)
    assert tuple(counts.by_priority) == tuple(TaskPriority)
    assert counts.terminal_total == 1
    with pytest.raises(TypeError):
        counts.by_status[TaskStatus.TODO] = 2  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        counts.total = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"total": -1}, "non-negative integer"),
        (
            {
                "by_status": {
                    TaskStatus.IN_PROGRESS: 1,
                    TaskStatus.TODO: 1,
                    TaskStatus.DONE: 1,
                }
            },
            "every key in enum order",
        ),
        (
            {
                "by_status": {
                    TaskStatus.TODO: 1,
                    TaskStatus.IN_PROGRESS: 1,
                }
            },
            "every key in enum order",
        ),
        (
            {
                "by_priority": {
                    TaskPriority.LOW: 1,
                    TaskPriority.MEDIUM: 1,
                    TaskPriority.HIGH: 0,
                }
            },
            "priority counts must sum",
        ),
    ],
)
def test_task_counts_reject_invalid_aggregates(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(DashboardInvariantError, match=message):
        make_task_counts(**changes)


def test_due_counts_require_mutually_exclusive_complete_partition() -> None:
    assert make_due_counts().active_total == 2

    with pytest.raises(DashboardInvariantError, match="sum to active total"):
        make_due_counts(later=1)


def test_project_dashboard_ties_active_total_to_terminal_policy() -> None:
    dashboard = ProjectDashboard(
        project_id=1,
        as_of=datetime(2026, 7, 15, tzinfo=UTC),
        tasks=make_task_counts(),
        due=make_due_counts(),
        tags=(),
        comments=DashboardCommentCounts(total=0, tasks_with_comments=0),
        recent_activities=(),
    )

    assert dashboard.as_of == datetime(2026, 7, 15, tzinfo=UTC)
    assert dashboard.as_of.tzinfo is UTC

    with pytest.raises(DashboardInvariantError, match="exclude exactly"):
        ProjectDashboard(
            project_id=1,
            as_of=datetime(2026, 7, 15, tzinfo=UTC),
            tasks=make_task_counts(),
            due=DashboardDueCounts(
                active_total=1,
                overdue=1,
                due_today=0,
                upcoming_7_days=0,
                later=0,
                no_due_date=0,
            ),
            tags=(),
            comments=DashboardCommentCounts(total=0, tasks_with_comments=0),
            recent_activities=(),
        )


@pytest.mark.parametrize(
    "as_of",
    [
        datetime(2026, 7, 15),
        datetime(2026, 7, 15, tzinfo=timezone(timedelta(hours=9))),
        "not-a-datetime",
    ],
)
def test_project_dashboard_rejects_invalid_as_of(as_of: object) -> None:
    with pytest.raises(DashboardInvariantError, match="as_of"):
        ProjectDashboard(
            project_id=1,
            as_of=as_of,  # type: ignore[arg-type]
            tasks=make_task_counts(),
            due=make_due_counts(),
            tags=(),
            comments=DashboardCommentCounts(total=0, tasks_with_comments=0),
            recent_activities=(),
        )
