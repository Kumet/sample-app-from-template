import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_board.application import ProjectDashboardService
from project_board.domain import (
    DashboardCommentCounts,
    DashboardDueCounts,
    DashboardInvariantError,
    DashboardTaskCounts,
    Project,
    ProjectNotFound,
    TaskPriority,
    TaskStatus,
)
from project_board.repositories import DashboardDueQuery

AS_OF = datetime(2026, 7, 15, 15, 30, tzinfo=UTC)


class StubProjectRepository:
    def __init__(self, project: Project | None) -> None:
        self.project = project
        self.requested_ids: list[int] = []

    def get(self, project_id: int) -> Project | None:
        self.requested_ids.append(project_id)
        if self.project is not None and self.project.id == project_id:
            return self.project
        return None


class StubDashboardRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, object | None]] = []
        self.tasks = DashboardTaskCounts(
            total=0,
            by_status={status: 0 for status in TaskStatus},
            by_priority={priority: 0 for priority in TaskPriority},
        )
        self.due = DashboardDueCounts(
            active_total=0,
            overdue=0,
            due_today=0,
            upcoming_7_days=0,
            later=0,
            no_due_date=0,
        )
        self.comments = DashboardCommentCounts(total=0, tasks_with_comments=0)

    def get_task_counts(self, project_id: int) -> DashboardTaskCounts:
        self.calls.append(("tasks", project_id, None))
        return self.tasks

    def get_due_counts(
        self, project_id: int, query: DashboardDueQuery
    ) -> DashboardDueCounts:
        self.calls.append(("due", project_id, query))
        return self.due

    def list_tag_counts(self, project_id: int) -> tuple[()]:
        self.calls.append(("tags", project_id, None))
        return ()

    def get_comment_counts(self, project_id: int) -> DashboardCommentCounts:
        self.calls.append(("comments", project_id, None))
        return self.comments

    def list_recent_activities(self, project_id: int, limit: int) -> tuple[()]:
        self.calls.append(("activities", project_id, limit))
        return ()


def make_project(project_id: int = 1) -> Project:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    return Project(project_id, "Dashboard", None, created_at, created_at)


def test_importing_dashboard_service_does_not_load_sqlalchemy_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.application.project_dashboard_service

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_dashboard_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps([name for name in watched_modules if name in sys.modules]))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_empty_dashboard_uses_one_clock_and_complete_repository_orchestration() -> None:
    clock_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        return AS_OF

    dashboard_repository = StubDashboardRepository()
    service = ProjectDashboardService(
        dashboard_repository, StubProjectRepository(make_project()), clock=clock
    )

    result = service.get_dashboard(1)

    assert clock_calls == 1
    assert result.project_id == 1
    assert result.as_of == AS_OF
    assert tuple(result.tasks.by_status) == tuple(TaskStatus)
    assert tuple(result.tasks.by_priority) == tuple(TaskPriority)
    assert result.tasks.total == result.due.active_total == 0
    assert result.tags == result.recent_activities == ()
    assert result.comments.total == result.comments.tasks_with_comments == 0
    assert [call[0] for call in dashboard_repository.calls] == [
        "tasks",
        "due",
        "tags",
        "comments",
        "activities",
    ]
    assert dashboard_repository.calls[-1] == ("activities", 1, 10)
    due_query = dashboard_repository.calls[1][2]
    assert isinstance(due_query, DashboardDueQuery)
    assert due_query == DashboardDueQuery(
        as_of=AS_OF,
        today_end=datetime(2026, 7, 16, tzinfo=UTC),
        upcoming_end=datetime(2026, 7, 23, tzinfo=UTC),
    )


def test_clock_is_normalized_to_utc_once_before_aggregation() -> None:
    local_as_of = datetime(2026, 7, 16, 0, 30, tzinfo=timezone(timedelta(hours=9)))
    dashboard_repository = StubDashboardRepository()
    service = ProjectDashboardService(
        dashboard_repository,
        StubProjectRepository(make_project()),
        clock=lambda: local_as_of,
    )

    result = service.get_dashboard(1, activity_limit=4)

    assert result.as_of == AS_OF
    assert result.as_of.tzinfo is UTC
    due_query = dashboard_repository.calls[1][2]
    assert isinstance(due_query, DashboardDueQuery)
    assert due_query.as_of is result.as_of
    assert dashboard_repository.calls[-1] == ("activities", 1, 4)


@pytest.mark.parametrize("clock_value", [datetime(2026, 7, 15), "not-a-date"])
def test_invalid_clock_fails_before_aggregate_queries(clock_value: object) -> None:
    dashboard_repository = StubDashboardRepository()
    service = ProjectDashboardService(
        dashboard_repository,
        StubProjectRepository(make_project()),
        clock=lambda: clock_value,  # type: ignore[return-value]
    )

    with pytest.raises(DashboardInvariantError, match="as_of"):
        service.get_dashboard(1)

    assert dashboard_repository.calls == []


def test_missing_project_fails_before_clock_or_aggregate_queries() -> None:
    dashboard_repository = StubDashboardRepository()

    def forbidden_clock() -> datetime:
        raise AssertionError("missing Projects must not read the dashboard clock")

    service = ProjectDashboardService(
        dashboard_repository, StubProjectRepository(None), clock=forbidden_clock
    )

    with pytest.raises(ProjectNotFound) as captured:
        service.get_dashboard(9)

    assert captured.value.project_id == 9
    assert dashboard_repository.calls == []


def test_result_cross_invariants_are_checked_before_return() -> None:
    dashboard_repository = StubDashboardRepository()
    dashboard_repository.tasks = DashboardTaskCounts(
        total=1,
        by_status={
            TaskStatus.TODO: 1,
            TaskStatus.IN_PROGRESS: 0,
            TaskStatus.DONE: 0,
        },
        by_priority={
            TaskPriority.LOW: 1,
            TaskPriority.MEDIUM: 0,
            TaskPriority.HIGH: 0,
        },
    )
    service = ProjectDashboardService(
        dashboard_repository, StubProjectRepository(make_project()), clock=lambda: AS_OF
    )

    with pytest.raises(DashboardInvariantError, match="exclude exactly"):
        service.get_dashboard(1)
