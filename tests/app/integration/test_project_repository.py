from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import Project, RepositoryError
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import ProjectModel
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
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
