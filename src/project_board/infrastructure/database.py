"""SQLAlchemy engine, session, and schema lifecycle helpers.

Schema creation is deliberately exposed as an explicit operation. Importing this
module, creating an engine, or creating a session factory does not modify the
database.
"""

from importlib import import_module
from sqlite3 import Connection as SQLiteConnection
from typing import TypeAlias

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class whose metadata contains application ORM mappings."""


SessionFactory: TypeAlias = sessionmaker[Session]


def _enable_sqlite_foreign_keys(
    dbapi_connection: SQLiteConnection, _connection_record: object
) -> None:
    """Enable SQLite foreign-key checks for one newly opened connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(database_url: str) -> Engine:
    """Create an engine for a SQLite database without initializing its schema."""
    if not database_url.startswith("sqlite:"):
        msg = "Only SQLite database URLs are supported"
        raise ValueError(msg)

    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create a factory for independent SQLAlchemy sessions."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_schema(engine: Engine) -> None:
    """Create development/test tables and safely extend existing Task schemas."""
    models = import_module("project_board.infrastructure.models")
    ownership_child_tables = (
        models.TaskCommentModel.__table__,
        models.TaskCommentActivityModel.__table__,
        models.TaskTagModel.__table__,
    )

    # Composite child foreign keys require their parent ownership keys.
    # Create every parent table first, including any test-only metadata tables.
    parent_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table not in ownership_child_tables
    ]
    Base.metadata.create_all(engine, tables=parent_tables)

    task_ownership_index = next(
        index
        for index in models.TaskModel.__table__.indexes
        if index.name == "uq_tasks_project_id_id"
    )
    task_ownership_index.create(engine, checkfirst=True)

    ownership_indexes = {
        index["name"]: index for index in inspect(engine).get_indexes("tasks")
    }
    ownership_index = ownership_indexes.get("uq_tasks_project_id_id")
    if ownership_index is None or (
        tuple(ownership_index["column_names"]) != ("project_id", "id")
        or not ownership_index["unique"]
    ):
        msg = "tasks must have a unique (project_id, id) ownership index"
        raise RuntimeError(msg)

    for child_table in ownership_child_tables:
        child_table.create(engine, checkfirst=True)
