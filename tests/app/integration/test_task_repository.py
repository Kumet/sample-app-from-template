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
    Project,
    RepositoryError,
    Task,
    TaskPriority,
    TaskStatus,
)
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import TaskModel
from project_board.repositories import SortOrder, TaskListQuery, TaskSort
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)
from project_board.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'task-repository.sqlite3'}"


@pytest.fixture
def isolated_engine(database_url: str) -> Iterator[Engine]:
    engine = create_database_engine(database_url)
    initialize_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(isolated_engine: Engine) -> Iterator[Session]:
    session = create_session_factory(isolated_engine)()
    yield session
    session.close()


def make_project(name: str, timestamp: datetime) -> Project:
    return Project(
        id=0,
        name=name,
        description=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def make_task(
    project_id: int,
    title: str,
    timestamp: datetime,
    *,
    status: TaskStatus = TaskStatus.TODO,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Task:
    return Task(
        id=0,
        project_id=project_id,
        title=title,
        description=None,
        status=status,
        priority=priority,
        due_at=due_at,
        created_at=timestamp,
        updated_at=timestamp if updated_at is None else updated_at,
    )


def create_project(session: Session, name: str = "Project") -> Project:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    return SQLAlchemyProjectRepository(session).create(make_project(name, timestamp))


def test_repository_crud_is_ownership_scoped_and_restores_utc(session: Session) -> None:
    first_project = create_project(session, "First")
    second_project = create_project(session, "Second")
    repository = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    created = repository.create(
        make_task(
            first_project.id,
            "Original",
            timestamp,
            due_at=timestamp + timedelta(days=1),
        )
    )

    session.expire_all()
    loaded = repository.get(first_project.id, created.id)
    assert loaded == created
    assert loaded is not None
    assert loaded.created_at.tzinfo is UTC
    assert loaded.updated_at.tzinfo is UTC
    assert loaded.due_at is not None and loaded.due_at.tzinfo is UTC
    assert repository.get(second_project.id, created.id) is None

    mismatched = replace(created, project_id=second_project.id, title="Hidden")
    assert repository.update(mismatched) is None
    assert repository.get(first_project.id, created.id) == created

    updated = replace(
        created,
        title="Updated",
        status=TaskStatus.DONE,
        priority=TaskPriority.HIGH,
        due_at=None,
        updated_at=timestamp + timedelta(hours=1),
    )
    assert repository.update(updated) == updated
    assert repository.delete(second_project.id, created.id) is False
    assert repository.delete(first_project.id, created.id) is True
    assert repository.get(first_project.id, created.id) is None
    assert repository.delete(first_project.id, created.id) is False


def test_list_applies_project_filters_strict_due_bounds_and_pagination(
    session: Session,
) -> None:
    project = create_project(session, "Listed")
    other_project = create_project(session, "Other")
    repository = SQLAlchemyTaskRepository(session)
    base = datetime(2026, 7, 14, tzinfo=UTC)
    before = repository.create(
        make_task(
            project.id,
            "Before",
            base,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            due_at=base + timedelta(days=1),
        )
    )
    boundary = repository.create(
        make_task(
            project.id,
            "Boundary",
            base + timedelta(seconds=1),
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            due_at=base + timedelta(days=2),
        )
    )
    after = repository.create(
        make_task(
            project.id,
            "After",
            base + timedelta(seconds=2),
            status=TaskStatus.DONE,
            priority=TaskPriority.LOW,
            due_at=base + timedelta(days=3),
        )
    )
    repository.create(make_task(other_project.id, "Not visible", base))

    filtered = repository.list(
        project.id,
        TaskListQuery(
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            due_after=base,
            due_before=base + timedelta(days=2),
        ),
    )
    assert [task.id for task in filtered] == [before.id]

    paged = repository.list(project.id, TaskListQuery(limit=1, offset=1))
    assert [task.id for task in paged] == [boundary.id]
    assert [task.id for task in repository.list(project.id, TaskListQuery())] == [
        before.id,
        boundary.id,
        after.id,
    ]


@pytest.mark.parametrize(
    ("sort", "order", "expected_titles"),
    [
        (TaskSort.CREATED_AT, SortOrder.ASC, ["Low", "High", "No due"]),
        (TaskSort.CREATED_AT, SortOrder.DESC, ["No due", "Low", "High"]),
        (TaskSort.UPDATED_AT, SortOrder.ASC, ["No due", "High", "Low"]),
        (TaskSort.UPDATED_AT, SortOrder.DESC, ["Low", "High", "No due"]),
        (TaskSort.DUE_AT, SortOrder.ASC, ["High", "Low", "No due"]),
        (TaskSort.DUE_AT, SortOrder.DESC, ["Low", "High", "No due"]),
        (TaskSort.PRIORITY, SortOrder.ASC, ["Low", "No due", "High"]),
        (TaskSort.PRIORITY, SortOrder.DESC, ["High", "No due", "Low"]),
    ],
)
def test_list_supports_every_deterministic_sort_with_null_due_dates_last(
    session: Session,
    sort: TaskSort,
    order: SortOrder,
    expected_titles: list[str],
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTaskRepository(session)
    base = datetime(2026, 7, 14, tzinfo=UTC)
    repository.create(
        make_task(
            project.id,
            "Low",
            base,
            priority=TaskPriority.LOW,
            due_at=base + timedelta(days=2),
            updated_at=base + timedelta(hours=2),
        )
    )
    repository.create(
        make_task(
            project.id,
            "High",
            base,
            priority=TaskPriority.HIGH,
            due_at=base + timedelta(days=1),
            updated_at=base + timedelta(hours=1),
        )
    )
    repository.create(
        make_task(
            project.id,
            "No due",
            base + timedelta(seconds=1),
            priority=TaskPriority.MEDIUM,
            updated_at=base,
        )
    )

    tasks = repository.list(project.id, TaskListQuery(sort=sort, order=order))

    assert [task.title for task in tasks] == expected_titles


def test_equal_primary_sort_values_always_use_ascending_id(session: Session) -> None:
    project = create_project(session)
    repository = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    first = repository.create(make_task(project.id, "First", timestamp))
    second = repository.create(make_task(project.id, "Second", timestamp))

    for order in SortOrder:
        tasks = repository.list(
            project.id,
            TaskListQuery(sort=TaskSort.CREATED_AT, order=order),
        )
        assert [task.id for task in tasks] == [first.id, second.id]


def test_data_persists_after_engine_restart(database_url: str) -> None:
    first_engine = create_database_engine(database_url)
    initialize_schema(first_engine)
    with create_session_factory(first_engine)() as first_session:
        project = create_project(first_session)
        created = SQLAlchemyTaskRepository(first_session).create(
            make_task(project.id, "Persistent", datetime(2026, 7, 14, tzinfo=UTC))
        )
    first_engine.dispose()

    second_engine = create_database_engine(database_url)
    try:
        with create_session_factory(second_engine)() as second_session:
            loaded = SQLAlchemyTaskRepository(second_session).get(
                project.id, created.id
            )
        assert loaded == created
    finally:
        second_engine.dispose()


def test_failed_create_rolls_back_and_same_session_remains_reusable(
    session: Session, isolated_engine: Engine
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    flushed_counts: list[int | None] = []

    def fail_after_flush(flushed_session: Session, _flush_context: object) -> None:
        flushed_counts.append(
            flushed_session.scalar(select(func.count()).select_from(TaskModel))
        )
        raise SQLAlchemyError("forced create failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.create(make_task(project.id, "Failed", timestamp))

    assert caught.value.args == ("Task persistence operation failed",)
    assert flushed_counts == [1]
    assert session.in_transaction() is False
    assert not session.new
    recovered = repository.create(make_task(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered
    with create_session_factory(isolated_engine)() as verification_session:
        assert (
            verification_session.scalar(select(func.count()).select_from(TaskModel))
            == 1
        )


def test_failed_update_rolls_back_and_same_session_remains_reusable(
    session: Session,
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    original = repository.create(make_task(project.id, "Original", timestamp))
    changed = replace(
        original,
        title="Failed",
        updated_at=timestamp + timedelta(hours=1),
    )

    def fail_after_flush(_session: Session, _flush_context: object) -> None:
        raise SQLAlchemyError("forced update failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.update(changed)

    assert caught.value.args == ("Task persistence operation failed",)
    assert session.in_transaction() is False
    assert not session.dirty
    assert repository.get(project.id, original.id) == original
    recovered = repository.create(make_task(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered


def test_failed_delete_rolls_back_and_same_session_remains_reusable(
    session: Session,
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    original = repository.create(make_task(project.id, "Original", timestamp))

    def fail_after_flush(_session: Session, _flush_context: object) -> None:
        raise SQLAlchemyError("forced delete failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.delete(project.id, original.id)

    assert caught.value.args == ("Task persistence operation failed",)
    assert session.in_transaction() is False
    assert not session.deleted
    assert repository.get(project.id, original.id) == original
    recovered = repository.create(make_task(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered
