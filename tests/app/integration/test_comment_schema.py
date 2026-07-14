from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_board.infrastructure import create_database_engine, initialize_schema
from project_board.infrastructure.models import (
    ProjectModel,
    TaskCommentActivityModel,
    TaskCommentModel,
    TaskModel,
)


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'comments.sqlite3'}")
    yield engine
    engine.dispose()


def test_comment_tables_have_required_columns_ownership_cascades_and_indexes(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    inspector = inspect(isolated_engine)

    comment_columns = {
        column["name"]: column for column in inspector.get_columns("task_comments")
    }
    assert set(comment_columns) == {
        "id",
        "project_id",
        "task_id",
        "body",
        "created_at",
        "updated_at",
    }
    assert comment_columns["id"]["primary_key"] == 1
    assert all(not column["nullable"] for column in comment_columns.values())
    assert _foreign_key_shapes(inspector, "task_comments") == {
        "fk_task_comments_project": (
            ("project_id",),
            "projects",
            ("id",),
            "CASCADE",
        ),
        "fk_task_comments_task_owner": (
            ("project_id", "task_id"),
            "tasks",
            ("project_id", "id"),
            "CASCADE",
        ),
    }
    assert _index_shapes(inspector, "task_comments") == {
        "ix_task_comments_project_id_task_id_created_at_id": (
            "project_id",
            "task_id",
            "created_at",
            "id",
        )
    }

    activity_columns = {
        column["name"]: column
        for column in inspector.get_columns("task_comment_activities")
    }
    assert set(activity_columns) == {
        "id",
        "project_id",
        "task_id",
        "comment_id",
        "event_type",
        "occurred_at",
    }
    assert activity_columns["id"]["primary_key"] == 1
    assert all(not column["nullable"] for column in activity_columns.values())
    assert _foreign_key_shapes(inspector, "task_comment_activities") == {
        "fk_task_comment_activities_project": (
            ("project_id",),
            "projects",
            ("id",),
            "CASCADE",
        ),
        "fk_task_comment_activities_task_owner": (
            ("project_id", "task_id"),
            "tasks",
            ("project_id", "id"),
            "CASCADE",
        ),
    }
    assert _index_shapes(inspector, "task_comment_activities") == {
        "ix_task_comment_activities_project_id_task_id_occurred_at_id": (
            "project_id",
            "task_id",
            "occurred_at",
            "id",
        )
    }


def test_database_rejects_cross_project_comment_ownership(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)

    with Session(isolated_engine, expire_on_commit=False) as session:
        first_project, second_project, task = _create_cross_project_fixture(
            session, timestamp
        )

        session.add(
            TaskCommentModel(
                project_id=second_project.id,
                task_id=task.id,
                body="Foreign ownership",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        assert session.get(ProjectModel, first_project.id) is not None
        assert session.get(TaskModel, task.id) is not None
        assert session.scalars(select(TaskCommentModel)).all() == []


def test_database_rejects_cross_project_activity_ownership(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    timestamp = datetime(2026, 7, 15, tzinfo=UTC)

    with Session(isolated_engine, expire_on_commit=False) as session:
        first_project, second_project, task = _create_cross_project_fixture(
            session, timestamp
        )

        session.add(
            TaskCommentActivityModel(
                project_id=second_project.id,
                task_id=task.id,
                comment_id=123,
                event_type="comment_created",
                occurred_at=timestamp,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        assert session.get(ProjectModel, first_project.id) is not None
        assert session.get(TaskModel, task.id) is not None
        assert session.scalars(select(TaskCommentActivityModel)).all() == []


def _foreign_key_shapes(
    inspector: object, table_name: str
) -> dict[str, tuple[tuple[str, ...], str, tuple[str, ...], str]]:
    return {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
            foreign_key["options"]["ondelete"],
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _index_shapes(inspector: object, table_name: str) -> dict[str, tuple[str, ...]]:
    return {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes(table_name)
    }


def _create_cross_project_fixture(
    session: Session, timestamp: datetime
) -> tuple[ProjectModel, ProjectModel, TaskModel]:
    first_project = ProjectModel(
        name="First", description=None, created_at=timestamp, updated_at=timestamp
    )
    second_project = ProjectModel(
        name="Second", description=None, created_at=timestamp, updated_at=timestamp
    )
    session.add_all((first_project, second_project))
    session.flush()
    task = TaskModel(
        project_id=first_project.id,
        title="Owned task",
        description=None,
        status="todo",
        priority="medium",
        due_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(task)
    session.commit()
    return first_project, second_project, task
