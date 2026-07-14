from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import TaskModel


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'tasks.sqlite3'}")
    yield engine
    engine.dispose()


def test_initialization_adds_tasks_without_replacing_project_rows(
    isolated_engine: Engine,
) -> None:
    legacy_metadata = MetaData()
    projects = Table(
        "projects",
        legacy_metadata,
        # This reproduces the pre-Task schema without application metadata.
        # Existing local Project data must survive metadata create_all().
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(100), nullable=False),
        Column("description", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    legacy_metadata.create_all(isolated_engine)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    with isolated_engine.begin() as connection:
        connection.execute(
            projects.insert().values(
                id=41,
                name="Existing project",
                description=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    initialize_schema(isolated_engine)

    assert inspect(isolated_engine).get_table_names() == ["projects", "tasks"]
    with isolated_engine.connect() as connection:
        assert connection.execute(text("SELECT id, name FROM projects")).one() == (
            41,
            "Existing project",
        )


def test_task_table_has_required_columns_foreign_key_and_indexes(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    inspector = inspect(isolated_engine)

    columns = {column["name"]: column for column in inspector.get_columns("tasks")}
    assert set(columns) == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "priority",
        "due_at",
        "created_at",
        "updated_at",
    }
    assert columns["id"]["primary_key"] == 1
    assert columns["description"]["nullable"] is True
    assert columns["due_at"]["nullable"] is True
    assert all(
        columns[name]["nullable"] is False
        for name in (
            "id",
            "project_id",
            "title",
            "status",
            "priority",
            "created_at",
            "updated_at",
        )
    )

    assert inspector.get_foreign_keys("tasks") == [
        {
            "name": None,
            "constrained_columns": ["project_id"],
            "referred_schema": None,
            "referred_table": "projects",
            "referred_columns": ["id"],
            "options": {},
        }
    ]
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("tasks")
    }
    assert indexes == {
        "ix_tasks_project_id": ("project_id",),
        "ix_tasks_project_id_due_at": ("project_id", "due_at"),
        "ix_tasks_project_id_priority": ("project_id", "priority"),
        "ix_tasks_project_id_status": ("project_id", "status"),
    }


def test_every_connection_enforces_foreign_keys_and_rejects_orphan_tasks(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    sessions = create_session_factory(isolated_engine)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)

    with isolated_engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1

    with sessions() as session:
        session.add(
            TaskModel(
                project_id=999,
                title="Orphan",
                description=None,
                status="todo",
                priority="medium",
                due_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    isolated_engine.dispose()
    with Session(isolated_engine) as new_connection_session:
        assert new_connection_session.scalar(text("PRAGMA foreign_keys")) == 1
