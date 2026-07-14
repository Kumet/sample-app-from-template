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
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from project_board.infrastructure import create_database_engine, initialize_schema
from project_board.infrastructure.models import (
    ProjectModel,
    TagModel,
    TaskModel,
    TaskTagModel,
)


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'tags.sqlite3'}")
    yield engine
    engine.dispose()


def test_initialization_preserves_existing_project_and_task_rows(
    isolated_engine: Engine,
) -> None:
    legacy_metadata = MetaData()
    projects = Table(
        "projects",
        legacy_metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", String(100), nullable=False),
        Column("description", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    tasks = Table(
        "tasks",
        legacy_metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("project_id", Integer, nullable=False),
        Column("title", String(200), nullable=False),
        Column("description", Text, nullable=True),
        Column("status", String(20), nullable=False),
        Column("priority", String(10), nullable=False),
        Column("due_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    legacy_metadata.create_all(isolated_engine)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    with isolated_engine.begin() as connection:
        connection.execute(
            projects.insert().values(
                id=7,
                name="Existing project",
                description=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        connection.execute(
            tasks.insert().values(
                id=11,
                project_id=7,
                title="Existing task",
                description=None,
                status="todo",
                priority="medium",
                due_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    initialize_schema(isolated_engine)
    initialize_schema(isolated_engine)

    inspector = inspect(isolated_engine)
    task_indexes = {index["name"]: index for index in inspector.get_indexes("tasks")}
    assert task_indexes["uq_tasks_project_id_id"]["column_names"] == [
        "project_id",
        "id",
    ]
    assert task_indexes["uq_tasks_project_id_id"]["unique"] == 1
    with isolated_engine.connect() as connection:
        assert connection.execute(select(projects.c.id, projects.c.name)).one() == (
            7,
            "Existing project",
        )
        assert connection.execute(select(tasks.c.id, tasks.c.title)).one() == (
            11,
            "Existing task",
        )


def test_tag_and_association_schema_has_ownership_constraints_and_indexes(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    inspector = inspect(isolated_engine)

    tag_columns = {column["name"]: column for column in inspector.get_columns("tags")}
    assert set(tag_columns) == {
        "id",
        "project_id",
        "name",
        "normalized_name",
        "color",
        "created_at",
        "updated_at",
    }
    assert tag_columns["color"]["nullable"] is True
    assert all(
        not tag_columns[name]["nullable"]
        for name in (
            "id",
            "project_id",
            "name",
            "normalized_name",
            "created_at",
            "updated_at",
        )
    )
    assert {
        (constraint["name"], tuple(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints("tags")
    } == {
        ("uq_tags_project_id_id", ("project_id", "id")),
        (
            "uq_tags_project_id_normalized_name",
            ("project_id", "normalized_name"),
        ),
    }
    assert {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("tags")
    } == {
        "ix_tags_project_id_normalized_name": (
            "project_id",
            "normalized_name",
            "id",
        )
    }

    association_columns = {
        column["name"]: column for column in inspector.get_columns("task_tags")
    }
    assert set(association_columns) == {"project_id", "task_id", "tag_id"}
    assert inspector.get_pk_constraint("task_tags")["constrained_columns"] == [
        "project_id",
        "task_id",
        "tag_id",
    ]
    foreign_keys = {
        foreign_key["name"]: foreign_key
        for foreign_key in inspector.get_foreign_keys("task_tags")
    }
    assert set(foreign_keys) == {
        "fk_task_tags_tag_owner",
        "fk_task_tags_task_owner",
    }
    assert foreign_keys["fk_task_tags_task_owner"]["constrained_columns"] == [
        "project_id",
        "task_id",
    ]
    assert foreign_keys["fk_task_tags_task_owner"]["referred_columns"] == [
        "project_id",
        "id",
    ]
    assert foreign_keys["fk_task_tags_task_owner"]["options"] == {"ondelete": "CASCADE"}
    assert foreign_keys["fk_task_tags_tag_owner"]["constrained_columns"] == [
        "project_id",
        "tag_id",
    ]
    assert foreign_keys["fk_task_tags_tag_owner"]["referred_columns"] == [
        "project_id",
        "id",
    ]
    assert foreign_keys["fk_task_tags_tag_owner"]["options"] == {"ondelete": "CASCADE"}
    assert {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("task_tags")
    } == {"ix_task_tags_project_id_tag_id": ("project_id", "tag_id")}


def test_database_rejects_cross_project_association_without_mutating_parents(
    isolated_engine: Engine,
) -> None:
    initialize_schema(isolated_engine)
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    with Session(isolated_engine, expire_on_commit=False) as session:
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
        tag = TagModel(
            project_id=second_project.id,
            name="Foreign",
            normalized_name="foreign",
            color=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add_all((task, tag))
        session.commit()

        session.add(
            TaskTagModel(project_id=first_project.id, task_id=task.id, tag_id=tag.id)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        assert session.get(TaskModel, task.id) is not None
        assert session.get(TagModel, tag.id) is not None
        assert session.scalars(select(TaskTagModel)).all() == []
