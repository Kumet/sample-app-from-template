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
    DuplicateTagName,
    Project,
    RepositoryError,
    Tag,
    Task,
    TaskPriority,
    TaskStatus,
)
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import TagModel, TaskTagModel
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)
from project_board.repositories.sqlalchemy_tag_repository import (
    SQLAlchemyTagRepository,
)
from project_board.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'tag-repository.sqlite3'}")
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


def make_tag(
    project_id: int,
    name: str,
    timestamp: datetime,
    *,
    color: str | None = None,
) -> Tag:
    return Tag(
        id=0,
        project_id=project_id,
        name=name,
        color=color,
        created_at=timestamp,
        updated_at=timestamp,
    )


def create_project(session: Session, name: str = "Project") -> Project:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    return SQLAlchemyProjectRepository(session).create(make_project(name, timestamp))


def create_task(session: Session, project_id: int) -> Task:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    return SQLAlchemyTaskRepository(session).create(
        Task(
            id=0,
            project_id=project_id,
            title="Task",
            description=None,
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            due_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def test_repository_crud_is_ownership_scoped_ordered_and_restores_utc(
    session: Session,
) -> None:
    first_project = create_project(session, "First")
    second_project = create_project(session, "Second")
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)

    zebra = repository.create(make_tag(first_project.id, "Zebra", timestamp))
    alpha = repository.create(
        make_tag(first_project.id, "alpha", timestamp, color="#12abef")
    )
    middle = repository.create(make_tag(first_project.id, "Middle", timestamp))
    repository.create(make_tag(second_project.id, "Hidden", timestamp))

    session.expire_all()
    loaded = repository.get(first_project.id, alpha.id)
    assert loaded == alpha
    assert loaded is not None
    assert loaded.color == "#12ABEF"
    assert loaded.created_at.tzinfo is UTC
    assert loaded.updated_at.tzinfo is UTC
    assert repository.get(second_project.id, alpha.id) is None
    assert [tag.id for tag in repository.list(first_project.id)] == [
        alpha.id,
        middle.id,
        zebra.id,
    ]
    assert repository.list(999_999) == []

    mismatched = replace(alpha, project_id=second_project.id, name="Hidden change")
    assert repository.update(mismatched) is None
    assert repository.get(first_project.id, alpha.id) == alpha

    updated = replace(
        alpha,
        name="Alpha renamed",
        color=None,
        updated_at=timestamp + timedelta(hours=1),
    )
    assert repository.update(updated) == updated
    assert repository.delete(second_project.id, alpha.id) is False
    assert repository.delete(first_project.id, alpha.id) is True
    assert repository.get(first_project.id, alpha.id) is None
    assert repository.delete(first_project.id, alpha.id) is False


def test_duplicate_names_are_project_local_and_case_only_self_rename_is_legal(
    session: Session,
) -> None:
    first_project = create_project(session, "First")
    second_project = create_project(session, "Second")
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    original = repository.create(make_tag(first_project.id, "Backend", timestamp))

    with pytest.raises(DuplicateTagName) as caught:
        repository.create(make_tag(first_project.id, "backend", timestamp))

    assert caught.value.project_id == first_project.id
    assert caught.value.name == "backend"
    assert session.in_transaction() is False
    other_project_tag = repository.create(
        make_tag(second_project.id, "backend", timestamp)
    )
    assert other_project_tag.name == "backend"

    renamed = replace(
        original,
        name="BACKEND",
        updated_at=timestamp + timedelta(seconds=1),
    )
    assert repository.update(renamed) == renamed
    assert repository.get(first_project.id, original.id) == renamed


def test_duplicate_rename_rolls_back_and_leaves_session_reusable(
    session: Session,
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    first = repository.create(make_tag(project.id, "First", timestamp))
    second = repository.create(make_tag(project.id, "Second", timestamp))

    with pytest.raises(DuplicateTagName):
        repository.update(
            replace(
                second,
                name="FIRST",
                updated_at=timestamp + timedelta(hours=1),
            )
        )

    assert session.in_transaction() is False
    assert repository.get(project.id, first.id) == first
    assert repository.get(project.id, second.id) == second


def test_non_duplicate_integrity_failure_is_sanitized_and_rolled_back(
    session: Session,
) -> None:
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)

    with pytest.raises(RepositoryError) as caught:
        repository.create(make_tag(999_999, "Orphan", timestamp))

    assert caught.value.args == ("Tag persistence operation failed",)
    assert session.in_transaction() is False
    assert not session.new
    project = create_project(session, "Recovered")
    recovered = repository.create(make_tag(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered


def test_failed_create_rolls_back_and_same_session_remains_reusable(
    session: Session, isolated_engine: Engine
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    flushed_counts: list[int | None] = []

    def fail_after_flush(flushed_session: Session, _flush_context: object) -> None:
        flushed_counts.append(
            flushed_session.scalar(select(func.count()).select_from(TagModel))
        )
        raise SQLAlchemyError("forced create failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.create(make_tag(project.id, "Failed", timestamp))

    assert caught.value.args == ("Tag persistence operation failed",)
    assert flushed_counts == [1]
    assert session.in_transaction() is False
    assert not session.new
    recovered = repository.create(make_tag(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered
    with create_session_factory(isolated_engine)() as verification_session:
        assert (
            verification_session.scalar(select(func.count()).select_from(TagModel)) == 1
        )


def test_failed_update_rolls_back_and_same_session_remains_reusable(
    session: Session,
) -> None:
    project = create_project(session)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    original = repository.create(make_tag(project.id, "Original", timestamp))
    changed = replace(
        original,
        name="Failed",
        updated_at=timestamp + timedelta(hours=1),
    )

    def fail_after_flush(_session: Session, _flush_context: object) -> None:
        raise SQLAlchemyError("forced update failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.update(changed)

    assert caught.value.args == ("Tag persistence operation failed",)
    assert session.in_transaction() is False
    assert not session.dirty
    assert repository.get(project.id, original.id) == original
    recovered = repository.create(make_tag(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered


def test_failed_delete_rolls_back_and_same_session_remains_reusable(
    session: Session,
) -> None:
    project = create_project(session)
    task = create_task(session, project.id)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    original = repository.create(make_tag(project.id, "Original", timestamp))
    repository.attach(project.id, task.id, original.id)
    cascaded_counts: list[int | None] = []

    def fail_after_flush(flushed_session: Session, _flush_context: object) -> None:
        cascaded_counts.append(
            flushed_session.scalar(select(func.count()).select_from(TaskTagModel))
        )
        raise SQLAlchemyError("forced delete failure")

    event.listen(session, "after_flush_postexec", fail_after_flush, once=True)
    with pytest.raises(RepositoryError) as caught:
        repository.delete(project.id, original.id)

    assert caught.value.args == ("Tag persistence operation failed",)
    assert cascaded_counts == [0]
    assert session.in_transaction() is False
    assert not session.deleted
    assert repository.get(project.id, original.id) == original
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 1
    assert SQLAlchemyTaskRepository(session).get(project.id, task.id) == replace(
        task, tags=(original,)
    )
    recovered = repository.create(make_tag(project.id, "Recovered", timestamp))
    assert repository.get(project.id, recovered.id) == recovered


def test_tag_delete_cascades_association_but_preserves_task_and_project(
    session: Session,
) -> None:
    project = create_project(session)
    task = create_task(session, project.id)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    tag = repository.create(make_tag(project.id, "Backend", timestamp))
    repository.attach(project.id, task.id, tag.id)

    assert repository.delete(project.id, tag.id) is True

    assert repository.get(project.id, tag.id) is None
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 0
    assert SQLAlchemyTaskRepository(session).get(project.id, task.id) == task
    assert SQLAlchemyProjectRepository(session).get(project.id) == project


def test_attach_and_detach_are_idempotent_and_change_one_association_row(
    session: Session,
) -> None:
    project = create_project(session)
    task = create_task(session, project.id)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    tag = repository.create(make_tag(project.id, "Backend", timestamp))

    repository.attach(project.id, task.id, tag.id)
    repository.attach(project.id, task.id, tag.id)
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 1

    repository.detach(project.id, task.id, tag.id)
    repository.detach(project.id, task.id, tag.id)
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 0


@pytest.mark.parametrize("operation", ["attach", "detach"])
def test_failed_association_write_rolls_back_and_session_remains_reusable(
    session: Session,
    operation: str,
) -> None:
    project = create_project(session)
    task = create_task(session, project.id)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    tag = repository.create(make_tag(project.id, "Backend", timestamp))
    if operation == "detach":
        repository.attach(project.id, task.id, tag.id)

    def fail_before_commit(_session: Session) -> None:
        raise SQLAlchemyError(f"forced {operation} failure")

    event.listen(session, "before_commit", fail_before_commit, once=True)
    with pytest.raises(RepositoryError, match="Tag persistence operation failed"):
        getattr(repository, operation)(project.id, task.id, tag.id)

    assert session.in_transaction() is False
    expected_count = 1 if operation == "detach" else 0
    assert (
        session.scalar(select(func.count()).select_from(TaskTagModel)) == expected_count
    )
    assert repository.get(project.id, tag.id) == tag
    expected_task = replace(task, tags=(tag,)) if operation == "detach" else task
    assert SQLAlchemyTaskRepository(session).get(project.id, task.id) == expected_task

    if operation == "attach":
        repository.attach(project.id, task.id, tag.id)
        expected_count = 1
    else:
        repository.detach(project.id, task.id, tag.id)
        expected_count = 0
    assert (
        session.scalar(select(func.count()).select_from(TaskTagModel)) == expected_count
    )


def test_repository_rejects_cross_project_association_without_parent_changes(
    session: Session,
) -> None:
    first_project = create_project(session, "First")
    second_project = create_project(session, "Second")
    task = create_task(session, first_project.id)
    repository = SQLAlchemyTagRepository(session)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    tag = repository.create(make_tag(second_project.id, "Foreign", timestamp))

    with pytest.raises(RepositoryError, match="Tag persistence operation failed"):
        repository.attach(first_project.id, task.id, tag.id)

    assert session.in_transaction() is False
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 0
    assert repository.get(second_project.id, tag.id) == tag
    assert SQLAlchemyTaskRepository(session).get(first_project.id, task.id) == task
