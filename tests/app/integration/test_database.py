import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, inspect, text
from sqlalchemy.engine import Engine

from project_board.infrastructure.database import (
    Base,
    create_database_engine,
    create_session_factory,
    initialize_schema,
)


@pytest.fixture
def isolated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    yield engine
    engine.dispose()


def test_schema_initialization_is_explicit(isolated_engine: Engine) -> None:
    table = Table(
        "schema_probe", Base.metadata, Column("id", Integer, primary_key=True)
    )

    try:
        assert inspect(isolated_engine).get_table_names() == []

        initialize_schema(isolated_engine)

        assert inspect(isolated_engine).get_table_names() == [
            "projects",
            "schema_probe",
        ]
    finally:
        Base.metadata.remove(table)


def test_schema_initialization_registers_models_in_fresh_interpreter(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).parents[3] / "src"
    database_url = f"sqlite:///{tmp_path / 'standalone.sqlite3'}"
    script = """
sys.path.insert(0, sys.argv[1])

from sqlalchemy import inspect
from project_board.infrastructure import create_database_engine, initialize_schema

engine = create_database_engine(sys.argv[2])
try:
    tables_before_initialization = inspect(engine).get_table_names()
    assert tables_before_initialization == [], tables_before_initialization

    initialize_schema(engine)
    print(*inspect(engine).get_table_names(), sep="\\n")
finally:
    engine.dispose()
"""

    result = subprocess.run(  # noqa: B603 - command and script are test constants
        [
            sys.executable,
            "-c",
            "import sys\n" + script,
            str(source_root),
            database_url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == ["projects"]


def test_session_factory_uses_only_its_configured_database(tmp_path: Path) -> None:
    first_engine = create_database_engine(f"sqlite:///{tmp_path / 'first.sqlite3'}")
    second_engine = create_database_engine(f"sqlite:///{tmp_path / 'second.sqlite3'}")
    try:
        metadata = MetaData()
        Table("isolated_value", metadata, Column("value", Integer, nullable=False))
        metadata.create_all(first_engine)
        metadata.create_all(second_engine)
        first_sessions = create_session_factory(first_engine)
        second_sessions = create_session_factory(second_engine)

        with first_sessions.begin() as session:
            session.execute(text("INSERT INTO isolated_value (value) VALUES (1)"))

        with first_sessions() as session:
            first_count = session.scalar(text("SELECT COUNT(*) FROM isolated_value"))
        with second_sessions() as session:
            second_count = session.scalar(text("SELECT COUNT(*) FROM isolated_value"))

        assert first_count == 1
        assert second_count == 0
    finally:
        first_engine.dispose()
        second_engine.dispose()


def test_non_sqlite_engine_is_rejected() -> None:
    with pytest.raises(ValueError, match="Only SQLite"):
        create_database_engine("postgresql://localhost/project_board")
