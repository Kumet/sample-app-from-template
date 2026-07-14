from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_board.application import TaskCommentService
from project_board.domain import (
    CommentEventType,
    Project,
    ProjectNotFound,
    Task,
    TaskComment,
    TaskCommentActivity,
    TaskCommentNotFound,
    TaskCommentValidationError,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
)
from project_board.repositories import ActivityListQuery, CommentListQuery

NOW = datetime(2026, 7, 15, 1, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)


def make_project(project_id: int = 1) -> Project:
    return Project(project_id, "Project", None, NOW, NOW)


def make_task(task_id: int = 2, project_id: int = 1) -> Task:
    return Task(
        task_id,
        project_id,
        "Task",
        None,
        TaskStatus.TODO,
        TaskPriority.MEDIUM,
        None,
        NOW,
        NOW,
    )


def make_comment(
    comment_id: int = 3, project_id: int = 1, task_id: int = 2, **changes: object
) -> TaskComment:
    values = {
        "id": comment_id,
        "project_id": project_id,
        "task_id": task_id,
        "body": "Original",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return TaskComment(**values)  # type: ignore[arg-type]


class StubProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects = {project.id: project for project in projects or []}
        self.requested_ids: list[int] = []

    def get(self, project_id: int) -> Project | None:
        self.requested_ids.append(project_id)
        return self.projects.get(project_id)


class StubTaskRepository:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self.tasks = {(task.project_id, task.id): task for task in tasks or []}
        self.requested_keys: list[tuple[int, int]] = []

    def get(self, project_id: int, task_id: int) -> Task | None:
        self.requested_keys.append((project_id, task_id))
        return self.tasks.get((project_id, task_id))


class StubCommentRepository:
    def __init__(self, comments: list[TaskComment] | None = None) -> None:
        self.comments = {
            (comment.project_id, comment.task_id, comment.id): comment
            for comment in comments or []
        }
        self.created: tuple[TaskComment, datetime] | None = None
        self.updated: tuple[TaskComment, datetime] | None = None
        self.deleted: tuple[int, int, int, datetime] | None = None
        self.listed: tuple[int, int, CommentListQuery] | None = None
        self.activities_listed: tuple[int, int, ActivityListQuery] | None = None

    def create(self, comment: TaskComment, occurred_at: datetime) -> TaskComment:
        self.created = (comment, occurred_at)
        persisted = replace(comment, id=10)
        self.comments[(persisted.project_id, persisted.task_id, persisted.id)] = (
            persisted
        )
        return persisted

    def list(
        self, project_id: int, task_id: int, query: CommentListQuery
    ) -> list[TaskComment]:
        self.listed = (project_id, task_id, query)
        return [
            comment
            for (owned_project_id, owned_task_id, _), comment in self.comments.items()
            if (owned_project_id, owned_task_id) == (project_id, task_id)
        ]

    def get(self, project_id: int, task_id: int, comment_id: int) -> TaskComment | None:
        return self.comments.get((project_id, task_id, comment_id))

    def update(self, comment: TaskComment, occurred_at: datetime) -> TaskComment | None:
        self.updated = (comment, occurred_at)
        key = (comment.project_id, comment.task_id, comment.id)
        if key not in self.comments:
            return None
        self.comments[key] = comment
        return comment

    def delete(
        self, project_id: int, task_id: int, comment_id: int, occurred_at: datetime
    ) -> bool:
        self.deleted = (project_id, task_id, comment_id, occurred_at)
        return self.comments.pop((project_id, task_id, comment_id), None) is not None

    def list_activities(
        self, project_id: int, task_id: int, query: ActivityListQuery
    ) -> list[TaskCommentActivity]:
        self.activities_listed = (project_id, task_id, query)
        return [
            TaskCommentActivity(
                1,
                project_id,
                task_id,
                3,
                CommentEventType.CREATED,
                NOW,
            )
        ]


def make_service(
    comments: StubCommentRepository,
    projects: StubProjectRepository | None = None,
    tasks: StubTaskRepository | None = None,
    *,
    clock: object = None,
) -> TaskCommentService:
    selected_clock = (lambda: LATER) if clock is None else clock
    return TaskCommentService(
        comments,
        projects or StubProjectRepository([make_project()]),
        tasks or StubTaskRepository([make_task()]),
        clock=selected_clock,  # type: ignore[arg-type]
    )


def test_importing_comment_service_does_not_load_persistence_implementations() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.application.task_comment_service

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_comment_repository",
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


def test_create_comment_verifies_owners_and_uses_one_utc_timestamp() -> None:
    comments = StubCommentRepository()
    offset = timezone(timedelta(hours=9))
    local_time = datetime(2026, 7, 15, 10, tzinfo=offset)

    created = make_service(comments, clock=lambda: local_time).create_comment(
        1, 2, "  Hello\nworld  "
    )

    assert created.id == 10
    assert comments.created is not None
    transient, occurred_at = comments.created
    assert transient.body == "Hello\nworld"
    assert transient.created_at == NOW
    assert transient.updated_at == NOW
    assert occurred_at == NOW


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.create_comment(1, 2, "Body"),
        lambda service: service.list_comments(1, 2, CommentListQuery()),
        lambda service: service.get_comment(1, 2, 3),
        lambda service: service.update_comment(1, 2, 3, body="Body"),
        lambda service: service.delete_comment(1, 2, 3),
        lambda service: service.list_activities(1, 2, ActivityListQuery()),
    ],
)
def test_every_operation_rejects_missing_project_before_other_repositories(
    operation: object,
) -> None:
    comments = StubCommentRepository([make_comment()])
    tasks = StubTaskRepository([make_task()])

    with pytest.raises(ProjectNotFound):
        operation(  # type: ignore[operator]
            make_service(comments, StubProjectRepository(), tasks)
        )

    assert tasks.requested_keys == []
    assert comments.created is None
    assert comments.updated is None
    assert comments.deleted is None
    assert comments.listed is None
    assert comments.activities_listed is None


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.create_comment(1, 2, "Body"),
        lambda service: service.list_comments(1, 2, CommentListQuery()),
        lambda service: service.get_comment(1, 2, 3),
        lambda service: service.update_comment(1, 2, 3, body="Body"),
        lambda service: service.delete_comment(1, 2, 3),
        lambda service: service.list_activities(1, 2, ActivityListQuery()),
    ],
)
def test_every_operation_conceals_missing_or_foreign_task(operation: object) -> None:
    comments = StubCommentRepository([make_comment()])
    tasks = StubTaskRepository([make_task(project_id=2)])

    with pytest.raises(TaskNotFound):
        operation(make_service(comments, tasks=tasks))  # type: ignore[operator]

    assert tasks.requested_keys == [(1, 2)]
    assert comments.created is None
    assert comments.updated is None
    assert comments.deleted is None
    assert comments.listed is None
    assert comments.activities_listed is None


def test_comment_reads_are_owned_and_delegate_queries_unchanged() -> None:
    owned = make_comment()
    foreign = make_comment(4, project_id=2)
    comments = StubCommentRepository([owned, foreign])
    service = make_service(comments)
    query = CommentListQuery(limit=10, offset=1)

    assert service.list_comments(1, 2, query) == [owned]
    assert comments.listed == (1, 2, query)
    assert service.get_comment(1, 2, 3) is owned
    with pytest.raises(TaskCommentNotFound):
        service.get_comment(1, 2, 4)


def test_same_body_update_advances_time_and_appends_through_repository() -> None:
    original = make_comment()
    comments = StubCommentRepository([original])

    updated = make_service(comments, clock=lambda: NOW).update_comment(
        1, 2, 3, body="  Original  "
    )

    assert updated.body == "Original"
    assert updated.created_at == NOW
    assert updated.updated_at == NOW + timedelta(microseconds=1)
    assert comments.updated == (updated, updated.updated_at)


def test_update_conceals_comment_that_disappears_during_persistence() -> None:
    class DisappearingCommentRepository(StubCommentRepository):
        def update(
            self, comment: TaskComment, occurred_at: datetime
        ) -> TaskComment | None:
            self.updated = (comment, occurred_at)
            return None

    comments = DisappearingCommentRepository([make_comment()])

    with pytest.raises(TaskCommentNotFound):
        make_service(comments).update_comment(1, 2, 3, body="Updated")


def test_delete_uses_utc_timestamp_and_conceals_missing_comment() -> None:
    comments = StubCommentRepository([make_comment()])

    assert make_service(comments).delete_comment(1, 2, 3) is None
    assert comments.deleted == (1, 2, 3, LATER)

    with pytest.raises(TaskCommentNotFound):
        make_service(comments).delete_comment(1, 2, 3)


def test_activity_list_requires_owners_and_delegates_filter_query() -> None:
    comments = StubCommentRepository()
    query = ActivityListQuery(event_type=CommentEventType.UPDATED, limit=7, offset=2)

    activities = make_service(comments).list_activities(1, 2, query)

    assert activities[0].event_type is CommentEventType.CREATED
    assert comments.activities_listed == (1, 2, query)


@pytest.mark.parametrize("clock_value", [datetime(2026, 7, 15), "not-a-date"])
def test_mutations_reject_invalid_clock_values(clock_value: object) -> None:
    comments = StubCommentRepository([make_comment()])
    service = make_service(comments, clock=lambda: clock_value)

    with pytest.raises(TaskCommentValidationError, match="timestamp"):
        service.create_comment(1, 2, "Body")
    with pytest.raises(TaskCommentValidationError, match="timestamp"):
        service.update_comment(1, 2, 3, body="Body")
    with pytest.raises(TaskCommentValidationError, match="timestamp"):
        service.delete_comment(1, 2, 3)

    assert comments.created is None
    assert comments.updated is None
    assert comments.deleted is None
