from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from project_board.domain import TaskPriority, TaskStatus
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import ProjectModel, TaskModel
from project_board.repositories import DashboardDueQuery
from project_board.repositories.sqlalchemy_dashboard_repository import (
    SQLAlchemyProjectDashboardRepository,
)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'dashboard-repository.sqlite3'}"


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


def create_project(session: Session, name: str) -> int:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    project = ProjectModel(
        name=name,
        description=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(project)
    session.commit()
    return project.id


def add_task(
    session: Session,
    project_id: int,
    title: str,
    *,
    status: TaskStatus,
    priority: TaskPriority,
    due_at: datetime | None,
) -> None:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    session.add(
        TaskModel(
            project_id=project_id,
            title=title,
            description=None,
            status=status.value,
            priority=priority.value,
            due_at=due_at,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )


def due_query(as_of: datetime) -> DashboardDueQuery:
    today_end = datetime(2026, 7, 16, tzinfo=UTC)
    return DashboardDueQuery(
        as_of=as_of,
        today_end=today_end,
        upcoming_end=today_end + timedelta(days=7),
    )


def test_task_counts_are_zero_inclusive_grouped_and_ownership_scoped(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    as_of = datetime(2026, 7, 15, 10, 30, tzinfo=UTC)
    add_task(
        session,
        project_id,
        "Todo high",
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
        due_at=as_of,
    )
    add_task(
        session,
        project_id,
        "Todo low",
        status=TaskStatus.TODO,
        priority=TaskPriority.LOW,
        due_at=None,
    )
    add_task(
        session,
        project_id,
        "Done high",
        status=TaskStatus.DONE,
        priority=TaskPriority.HIGH,
        due_at=as_of - timedelta(days=1),
    )
    add_task(
        session,
        foreign_project_id,
        "Foreign medium",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    session.commit()

    repository = SQLAlchemyProjectDashboardRepository(session)

    counts = repository.get_task_counts(project_id)
    empty_counts = repository.get_task_counts(create_project(session, "Empty"))

    assert counts.total == 3
    assert list(counts.by_status.items()) == [
        (TaskStatus.TODO, 2),
        (TaskStatus.IN_PROGRESS, 0),
        (TaskStatus.DONE, 1),
    ]
    assert list(counts.by_priority.items()) == [
        (TaskPriority.LOW, 1),
        (TaskPriority.MEDIUM, 0),
        (TaskPriority.HIGH, 2),
    ]
    assert empty_counts.total == 0
    assert list(empty_counts.by_status.values()) == [0, 0, 0]
    assert list(empty_counts.by_priority.values()) == [0, 0, 0]


def test_due_counts_use_half_open_boundaries_and_exclude_terminal_tasks(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    as_of = datetime(2026, 7, 15, 10, 30, tzinfo=UTC)
    query = due_query(as_of)
    active_due_dates = (
        ("Overdue", as_of - timedelta(microseconds=1)),
        ("At as-of", as_of),
        ("Before midnight", query.today_end - timedelta(microseconds=1)),
        ("At midnight", query.today_end),
        ("Before upcoming endpoint", query.upcoming_end - timedelta(microseconds=1)),
        ("At upcoming endpoint", query.upcoming_end),
        ("No due date", None),
    )
    for title, due_at in active_due_dates:
        add_task(
            session,
            project_id,
            title,
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            due_at=due_at,
        )
    add_task(
        session,
        project_id,
        "Terminal overdue",
        status=TaskStatus.DONE,
        priority=TaskPriority.HIGH,
        due_at=as_of - timedelta(days=1),
    )
    add_task(
        session,
        foreign_project_id,
        "Foreign overdue",
        status=TaskStatus.TODO,
        priority=TaskPriority.LOW,
        due_at=as_of - timedelta(days=1),
    )
    session.commit()

    counts = SQLAlchemyProjectDashboardRepository(session).get_due_counts(
        project_id, query
    )

    assert counts.active_total == 7
    assert counts.overdue == 1
    assert counts.due_today == 2
    assert counts.upcoming_7_days == 2
    assert counts.later == 1
    assert counts.no_due_date == 1


@pytest.mark.parametrize("task_count", [0, 25])
def test_task_aggregates_use_three_parameterized_statements_independent_of_rows(
    session: Session, isolated_engine: Engine, task_count: int
) -> None:
    project_id = create_project(session, "Selected")
    as_of = datetime(2026, 7, 15, 10, 30, tzinfo=UTC)
    query = due_query(as_of)
    for index in range(task_count):
        add_task(
            session,
            project_id,
            f"Task {index}",
            status=tuple(TaskStatus)[index % len(TaskStatus)],
            priority=tuple(TaskPriority)[index % len(TaskPriority)],
            due_at=as_of + timedelta(days=index % 10),
        )
    session.commit()
    executed: list[tuple[str, object]] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        executed.append((statement, parameters))

    event.listen(isolated_engine, "before_cursor_execute", record_statement)
    try:
        repository = SQLAlchemyProjectDashboardRepository(session)
        repository.get_task_counts(project_id)
        repository.get_due_counts(project_id, query)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_statement)

    assert len(executed) == 3
    normalized = [" ".join(statement.upper().split()) for statement, _ in executed]
    assert all(statement.startswith("SELECT ") for statement in normalized)
    assert all("WHERE TASKS.PROJECT_ID = ?" in statement for statement in normalized)
    assert all("GROUP BY" in statement for statement in normalized[:2])
    assert "CASE WHEN" in normalized[2]
    assert "2026-07-15" not in executed[2][0]
    assert all(parameters for _statement, parameters in executed)
