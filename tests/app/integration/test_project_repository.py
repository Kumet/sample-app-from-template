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
    ProjectHasTasksConflict,
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
from project_board.infrastructure.models import (
    ProjectModel,
    TagModel,
    TaskModel,
    TaskTagModel,
)
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
    engine = create_database_engine(f"sqlite:///{tmp_path / 'repository.sqlite3'}")
    initialize_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(isolated_engine: Engine) -> Iterator[Session]:
    session = create_session_factory(isolated_engine)()
    yield session
    session.close()


def make_project(*, name: str, created_at: datetime, project_id: int = 0) -> Project:
    return Project(
        id=project_id,
        name=name,
        description="Description",
        created_at=created_at,
        updated_at=created_at,
    )


def make_task(project_id: int, timestamp: datetime) -> Task:
    return Task(
        id=0,
        project_id=project_id,
        title="Blocking task",
        description=None,
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def create_tag(
    session: Session, project_id: int, name: str, timestamp: datetime
) -> Tag:
    return SQLAlchemyTagRepository(session).create(
        Tag(
            id=0,
            project_id=project_id,
            name=name,
            color=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def test_repository_crud_round_trip_and_ordering(session: Session) -> None:
    repository = SQLAlchemyProjectRepository(session)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    earlier = later - timedelta(days=1)

    second = repository.create(make_project(name="Second", created_at=later))
    first = repository.create(make_project(name="First", created_at=earlier))
    third = repository.create(make_project(name="Third", created_at=later))

    assert [project.id for project in repository.list()] == [
        first.id,
        second.id,
        third.id,
    ]
    assert repository.get(second.id) == second
    updated = replace(second, name="Updated", updated_at=later + timedelta(hours=1))
    assert repository.update(updated) == updated
    assert repository.delete(second.id) is True
    assert repository.get(second.id) is None
    assert repository.delete(second.id) is False


def test_repository_restores_timezone_aware_utc_values(session: Session) -> None:
    repository = SQLAlchemyProjectRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    created = repository.create(make_project(name="UTC", created_at=timestamp))
    session.expire_all()
    loaded = repository.get(created.id)

    assert loaded is not None
    assert loaded.created_at.tzinfo is UTC
    assert loaded.updated_at.tzinfo is UTC


def test_project_delete_conflict_preserves_records_and_session_is_reusable(
    session: Session,
) -> None:
    projects = SQLAlchemyProjectRepository(session)
    tasks = SQLAlchemyTaskRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    project = projects.create(make_project(name="Protected", created_at=timestamp))
    task = tasks.create(make_task(project.id, timestamp))
    tag = create_tag(session, project.id, "Protected tag", timestamp)
    SQLAlchemyTagRepository(session).attach(project.id, task.id, tag.id)

    with pytest.raises(ProjectHasTasksConflict) as captured:
        projects.delete(project.id)

    assert captured.value.project_id == project.id
    assert session.in_transaction() is False
    assert projects.get(project.id) == project
    assert tasks.get(project.id, task.id) == replace(task, tags=(tag,))
    assert SQLAlchemyTagRepository(session).get(project.id, tag.id) == tag
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 1

    assert tasks.delete(project.id, task.id) is True
    assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 0
    assert SQLAlchemyTagRepository(session).get(project.id, tag.id) == tag
    assert projects.delete(project.id) is True
    assert session.get(ProjectModel, project.id) is None
    assert session.get(TaskModel, task.id) is None
    assert session.get(TagModel, tag.id) is None


def test_task_free_project_delete_cascades_only_its_tags(session: Session) -> None:
    projects = SQLAlchemyProjectRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    selected = projects.create(make_project(name="Selected", created_at=timestamp))
    other = projects.create(make_project(name="Other", created_at=timestamp))
    selected_tags = (
        create_tag(session, selected.id, "Alpha", timestamp),
        create_tag(session, selected.id, "Beta", timestamp),
    )
    other_tag = create_tag(session, other.id, "Alpha", timestamp)

    assert projects.delete(selected.id) is True

    assert projects.get(selected.id) is None
    assert all(session.get(TagModel, tag.id) is None for tag in selected_tags)
    assert projects.get(other.id) == other
    assert SQLAlchemyTagRepository(session).get(other.id, other_tag.id) == other_tag


def test_failed_write_rolls_back_and_raises_stable_error(
    session: Session, isolated_engine: Engine
) -> None:
    repository = SQLAlchemyProjectRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    flushed_row_counts: list[int | None] = []

    def fail_after_write_is_flushed(
        flushed_session: Session, _flush_context: object
    ) -> None:
        flushed_row_counts.append(
            flushed_session.scalar(select(func.count()).select_from(ProjectModel))
        )
        raise SQLAlchemyError("forced failure after write flush")

    event.listen(
        session, "after_flush_postexec", fail_after_write_is_flushed, once=True
    )

    with pytest.raises(RepositoryError, match="persistence operation failed") as caught:
        repository.create(make_project(name="Will fail", created_at=timestamp))

    assert caught.value.args == ("Project persistence operation failed",)
    assert flushed_row_counts == [1]
    assert session.in_transaction() is False
    assert not session.new

    with create_session_factory(isolated_engine)() as verification_session:
        persisted_count = verification_session.scalar(
            select(func.count()).select_from(ProjectModel)
        )

    assert persisted_count == 0


def test_failed_update_rolls_back_and_leaves_transaction_clean(
    session: Session, isolated_engine: Engine
) -> None:
    repository = SQLAlchemyProjectRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    original = repository.create(make_project(name="Original", created_at=timestamp))
    updated = replace(
        original,
        name="Will fail",
        updated_at=timestamp + timedelta(hours=1),
    )

    def fail_after_write_is_flushed(
        _flushed_session: Session, _flush_context: object
    ) -> None:
        raise SQLAlchemyError("forced update failure after write flush")

    event.listen(
        session, "after_flush_postexec", fail_after_write_is_flushed, once=True
    )

    with pytest.raises(RepositoryError, match="persistence operation failed") as caught:
        repository.update(updated)

    assert caught.value.args == ("Project persistence operation failed",)
    assert session.in_transaction() is False
    assert not session.dirty

    with create_session_factory(isolated_engine)() as verification_session:
        persisted = verification_session.get(ProjectModel, original.id)

    assert persisted is not None
    assert persisted.name == "Original"
    assert persisted.updated_at == timestamp.replace(tzinfo=None)


def test_failed_delete_rolls_back_and_leaves_transaction_clean(
    session: Session, isolated_engine: Engine
) -> None:
    repository = SQLAlchemyProjectRepository(session)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    original = repository.create(make_project(name="Will remain", created_at=timestamp))
    tag = create_tag(session, original.id, "Will remain", timestamp)
    cascaded_tag_counts: list[int | None] = []

    def fail_after_write_is_flushed(
        flushed_session: Session, _flush_context: object
    ) -> None:
        cascaded_tag_counts.append(
            flushed_session.scalar(select(func.count()).select_from(TagModel))
        )
        raise SQLAlchemyError("forced delete failure after write flush")

    event.listen(
        session, "after_flush_postexec", fail_after_write_is_flushed, once=True
    )

    with pytest.raises(RepositoryError, match="persistence operation failed") as caught:
        repository.delete(original.id)

    assert caught.value.args == ("Project persistence operation failed",)
    assert cascaded_tag_counts == [0]
    assert session.in_transaction() is False
    assert not session.deleted

    with create_session_factory(isolated_engine)() as verification_session:
        persisted = verification_session.get(ProjectModel, original.id)
        persisted_tag = verification_session.get(TagModel, tag.id)

    assert persisted is not None
    assert persisted.name == "Will remain"
    assert persisted_tag is not None
    assert persisted_tag.name == "Will remain"
    assert repository.delete(original.id) is True
