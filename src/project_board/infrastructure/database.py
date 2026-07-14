"""SQLAlchemy engine, session, and schema lifecycle helpers.

Schema creation is deliberately exposed as an explicit operation. Importing this
module, creating an engine, or creating a session factory does not modify the
database.
"""

from importlib import import_module
from sqlite3 import Connection as SQLiteConnection
from typing import TypeAlias

from sqlalchemy import Engine, create_engine, event
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
    """Explicitly create all tables registered in application metadata."""
    import_module("project_board.infrastructure.models")
    Base.metadata.create_all(engine)
