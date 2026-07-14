from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import (
    CommentEventType,
    Project,
    RepositoryError,
    Task,
    TaskComment,
    TaskPriority,
    TaskStatus,
)
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import (
    TaskCommentActivityModel,
    TaskCommentModel,
)
from project_board.repositories import ActivityListQuery, CommentListQuery, SortOrder
from project_board.repositories.sqlalchemy_comment_repository import (
    SQLAlchemyTaskCommentRepository,
)
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)
from project_board.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(
        f"sqlite:///{tmp_path / 'comment-repository.sqlite3'}"
    )
    initialize_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(isolated_engine: Engine) -> Iterator[Session]:
    session = create_session_factory(isolated_engine)()
    yield session
    session.close()


def create_task(session: Session, name: str = "Project") -> Task:
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)
    project = SQLAlchemyProjectRepository(session).create(
        Project(
            id=0,
            name=name,
            description=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    return SQLAlchemyTaskRepository(session).create(
        Task(
            id=0,
            project_id=project.id,
            title="Task",
            description=None,
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            due_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def make_comment(task: Task, body: str, timestamp: datetime) -> TaskComment:
    return TaskComment(
        id=1,
        project_id=task.project_id,
        task_id=task.id,
        body=body,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_comment_lifecycle_commits_one_append_only_event_per_mutation(
    session: Session,
) -> None:
    task = create_task(session)
    repository = SQLAlchemyTaskCommentRepository(session)
    created_at = datetime(2026, 7, 15, 1, tzinfo=UTC)
    updated_at = created_at + timedelta(minutes=1)
    deleted_at = updated_at + timedelta(minutes=1)

    created = repository.create(make_comment(task, "Original", created_at), created_at)
    assert created.id > 0
    assert created.created_at.tzinfo is UTC
    assert repository.get(task.project_id, task.id, created.id) == created

    updated = replace(created, body="Updated", updated_at=updated_at)
    assert repository.update(updated, updated_at) == updated
    assert repository.delete(task.project_id, task.id, created.id, deleted_at) is True
    assert repository.get(task.project_id, task.id, created.id) is None

    activities = repository.list_activities(
        task.project_id, task.id, ActivityListQuery()
    )
    assert [activity.event_type for activity in activities] == [
        CommentEventType.CREATED,
        CommentEventType.UPDATED,
        CommentEventType.DELETED,
    ]
    assert [activity.comment_id for activity in activities] == [created.id] * 3
    assert [activity.occurred_at for activity in activities] == [
        created_at,
        updated_at,
        deleted_at,
    ]
    assert all(activity.occurred_at.tzinfo is UTC for activity in activities)
    assert repository.delete(task.project_id, task.id, created.id, deleted_at) is False


def test_reads_are_ownership_scoped_filtered_ordered_and_paginated(
    session: Session,
) -> None:
    first_task = create_task(session, "First")
    second_task = create_task(session, "Second")
    repository = SQLAlchemyTaskCommentRepository(session)
    timestamp = datetime(2026, 7, 15, 1, tzinfo=UTC)
    first = repository.create(make_comment(first_task, "First", timestamp), timestamp)
    second = repository.create(make_comment(first_task, "Second", timestamp), timestamp)
    repository.create(make_comment(second_task, "Hidden", timestamp), timestamp)
    changed = replace(
        first, body="Changed", updated_at=timestamp + timedelta(minutes=1)
    )
    repository.update(changed, changed.updated_at)

    assert repository.get(second_task.project_id, second_task.id, first.id) is None
    assert (
        repository.list(second_task.project_id, first_task.id, CommentListQuery()) == []
    )
    assert repository.list(
        first_task.project_id,
        first_task.id,
        CommentListQuery(limit=1, offset=1, order=SortOrder.DESC),
    ) == [second]
    filtered = repository.list_activities(
        first_task.project_id,
        first_task.id,
        ActivityListQuery(event_type=CommentEventType.CREATED),
    )
    assert [activity.comment_id for activity in filtered] == [first.id, second.id]


def test_activity_insert_failure_rolls_back_create_and_reuses_session(
    session: Session,
) -> None:
    task = create_task(session)
    repository = SQLAlchemyTaskCommentRepository(session)
    timestamp = datetime(2026, 7, 15, 1, tzinfo=UTC)

    def fail_activity_insert(*_args: object) -> None:
        raise SQLAlchemyError("forced activity failure")

    event.listen(
        TaskCommentActivityModel, "before_insert", fail_activity_insert, once=True
    )
    with pytest.raises(RepositoryError) as caught:
        repository.create(make_comment(task, "Failed", timestamp), timestamp)

    assert caught.value.args == ("Task Comment persistence operation failed",)
    assert session.in_transaction() is False
    assert session.scalar(select(func.count()).select_from(TaskCommentModel)) == 0
    assert (
        session.scalar(select(func.count()).select_from(TaskCommentActivityModel)) == 0
    )
    recovered = repository.create(make_comment(task, "Recovered", timestamp), timestamp)
    assert repository.get(task.project_id, task.id, recovered.id) == recovered


def test_activity_insert_failure_rolls_back_update_and_reuses_session(
    session: Session,
) -> None:
    task = create_task(session)
    repository = SQLAlchemyTaskCommentRepository(session)
    timestamp = datetime(2026, 7, 15, 1, tzinfo=UTC)
    original = repository.create(make_comment(task, "Original", timestamp), timestamp)
    changed = replace(
        original, body="Failed", updated_at=timestamp + timedelta(minutes=1)
    )

    def fail_activity_insert(*_args: object) -> None:
        raise SQLAlchemyError("forced activity failure")

    event.listen(
        TaskCommentActivityModel, "before_insert", fail_activity_insert, once=True
    )
    with pytest.raises(RepositoryError):
        repository.update(changed, changed.updated_at)

    assert session.in_transaction() is False
    assert repository.get(task.project_id, task.id, original.id) == original
    assert [
        activity.event_type
        for activity in repository.list_activities(
            task.project_id, task.id, ActivityListQuery()
        )
    ] == [CommentEventType.CREATED]


@pytest.mark.parametrize("failure_target", ["activity", "comment"])
def test_delete_failure_preserves_comment_and_adds_no_event(
    session: Session, failure_target: str
) -> None:
    task = create_task(session)
    repository = SQLAlchemyTaskCommentRepository(session)
    timestamp = datetime(2026, 7, 15, 1, tzinfo=UTC)
    original = repository.create(make_comment(task, "Original", timestamp), timestamp)

    def fail_delete(*_args: object) -> None:
        raise SQLAlchemyError(f"forced {failure_target} failure")

    target = (
        TaskCommentActivityModel if failure_target == "activity" else TaskCommentModel
    )
    operation = "before_insert" if failure_target == "activity" else "before_delete"
    event.listen(target, operation, fail_delete, once=True)
    with pytest.raises(RepositoryError):
        repository.delete(
            task.project_id,
            task.id,
            original.id,
            timestamp + timedelta(minutes=1),
        )

    assert session.in_transaction() is False
    assert repository.get(task.project_id, task.id, original.id) == original
    assert [
        activity.event_type
        for activity in repository.list_activities(
            task.project_id, task.id, ActivityListQuery()
        )
    ] == [CommentEventType.CREATED]


def test_constraint_failure_is_sanitized_rolled_back_and_session_is_reusable(
    session: Session,
) -> None:
    task = create_task(session)
    repository = SQLAlchemyTaskCommentRepository(session)
    timestamp = datetime(2026, 7, 15, 1, tzinfo=UTC)
    orphan = replace(make_comment(task, "Orphan", timestamp), task_id=999_999)

    with pytest.raises(RepositoryError) as caught:
        repository.create(orphan, timestamp)

    assert caught.value.args == ("Task Comment persistence operation failed",)
    assert session.in_transaction() is False
    assert session.scalar(select(func.count()).select_from(TaskCommentModel)) == 0
    recovered = repository.create(make_comment(task, "Recovered", timestamp), timestamp)
    assert repository.get(task.project_id, task.id, recovered.id) == recovered
