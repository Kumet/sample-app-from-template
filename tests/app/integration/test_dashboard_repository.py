from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from project_board.application import ProjectDashboardService
from project_board.domain import CommentEventType, TaskPriority, TaskStatus
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import (
    ProjectModel,
    TagModel,
    TaskCommentActivityModel,
    TaskCommentModel,
    TaskModel,
    TaskTagModel,
)
from project_board.repositories import DashboardDueQuery
from project_board.repositories.sqlalchemy_dashboard_repository import (
    SQLAlchemyProjectDashboardRepository,
)
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)

DASHBOARD_TABLES = (
    ProjectModel.__table__,
    TaskModel.__table__,
    TagModel.__table__,
    TaskTagModel.__table__,
    TaskCommentModel.__table__,
    TaskCommentActivityModel.__table__,
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
) -> int:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    task = TaskModel(
        project_id=project_id,
        title=title,
        description=None,
        status=status.value,
        priority=priority.value,
        due_at=due_at,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(task)
    session.flush()
    return task.id


def add_tag(session: Session, project_id: int, name: str, normalized_name: str) -> int:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    tag = TagModel(
        project_id=project_id,
        name=name,
        normalized_name=normalized_name,
        color=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(tag)
    session.flush()
    return tag.id


def add_comment(
    session: Session, project_id: int, task_id: int, body: str
) -> TaskCommentModel:
    timestamp = datetime(2026, 7, 14, tzinfo=UTC)
    comment = TaskCommentModel(
        project_id=project_id,
        task_id=task_id,
        body=body,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(comment)
    session.flush()
    return comment


def add_activity(
    session: Session,
    project_id: int,
    task_id: int,
    comment_id: int,
    event_type: CommentEventType,
    occurred_at: datetime,
) -> int:
    activity = TaskCommentActivityModel(
        project_id=project_id,
        task_id=task_id,
        comment_id=comment_id,
        event_type=event_type.value,
        occurred_at=occurred_at,
    )
    session.add(activity)
    session.flush()
    return activity.id


def due_query(as_of: datetime) -> DashboardDueQuery:
    today_end = datetime(2026, 7, 16, tzinfo=UTC)
    return DashboardDueQuery(
        as_of=as_of,
        today_end=today_end,
        upcoming_end=today_end + timedelta(days=7),
    )


def database_fingerprint(session: Session) -> dict[str, tuple[tuple[object, ...], ...]]:
    """Return every dashboard-relevant row in stable primary-key order."""
    fingerprint: dict[str, tuple[tuple[object, ...], ...]] = {}
    for table in DASHBOARD_TABLES:
        statement = select(*table.c).order_by(*table.primary_key.columns)
        fingerprint[table.name] = tuple(
            tuple(row) for row in session.execute(statement).all()
        )
    return fingerprint


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


def test_tag_counts_include_unattached_tags_and_confine_distinct_owned_tasks(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    first_task_id = add_task(
        session,
        project_id,
        "First",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    second_task_id = add_task(
        session,
        project_id,
        "Second",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        due_at=None,
    )
    foreign_task_id = add_task(
        session,
        foreign_project_id,
        "Foreign",
        status=TaskStatus.TODO,
        priority=TaskPriority.LOW,
        due_at=None,
    )
    zeta_id = add_tag(session, project_id, "Zeta", "zeta")
    alpha_id = add_tag(session, project_id, "Alpha", "alpha")
    beta_id = add_tag(session, project_id, "Beta", "beta")
    foreign_tag_id = add_tag(session, foreign_project_id, "Foreign", "foreign")
    deleted_tag_id = add_tag(session, project_id, "Deleted", "deleted")
    session.add_all(
        [
            TaskTagModel(project_id=project_id, task_id=first_task_id, tag_id=alpha_id),
            TaskTagModel(
                project_id=project_id, task_id=second_task_id, tag_id=alpha_id
            ),
            TaskTagModel(project_id=project_id, task_id=first_task_id, tag_id=zeta_id),
            TaskTagModel(
                project_id=foreign_project_id,
                task_id=foreign_task_id,
                tag_id=foreign_tag_id,
            ),
        ]
    )
    deleted_tag = session.get(TagModel, deleted_tag_id)
    assert deleted_tag is not None
    session.delete(deleted_tag)
    session.commit()

    counts = SQLAlchemyProjectDashboardRepository(session).list_tag_counts(project_id)

    assert [(count.id, count.name, count.task_count) for count in counts] == [
        (alpha_id, "Alpha", 2),
        (beta_id, "Beta", 0),
        (zeta_id, "Zeta", 1),
    ]
    assert [count.normalized_name for count in counts] == ["alpha", "beta", "zeta"]


def test_comment_counts_include_only_current_comments_on_owned_tasks(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    first_task_id = add_task(
        session,
        project_id,
        "First",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    second_task_id = add_task(
        session,
        project_id,
        "Second",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    add_task(
        session,
        project_id,
        "Without comments",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    foreign_task_id = add_task(
        session,
        foreign_project_id,
        "Foreign",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    deleted_comment = add_comment(session, project_id, first_task_id, "Deleted")
    add_comment(session, project_id, first_task_id, "Current first")
    add_comment(session, project_id, second_task_id, "Current second")
    add_comment(session, foreign_project_id, foreign_task_id, "Foreign")
    deleted_comment_id = deleted_comment.id
    session.delete(deleted_comment)
    session.add(
        TaskCommentActivityModel(
            project_id=project_id,
            task_id=first_task_id,
            comment_id=deleted_comment_id,
            event_type=CommentEventType.DELETED.value,
            occurred_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
    )
    session.commit()

    repository = SQLAlchemyProjectDashboardRepository(session)

    counts = repository.get_comment_counts(project_id)
    empty_counts = repository.get_comment_counts(create_project(session, "Empty"))

    assert counts.total == 2
    assert counts.tasks_with_comments == 2
    assert empty_counts.total == 0
    assert empty_counts.tasks_with_comments == 0


def test_recent_activities_are_bounded_ordered_typed_and_ownership_scoped(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    task_id = add_task(
        session,
        project_id,
        "Selected Task",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    foreign_task_id = add_task(
        session,
        foreign_project_id,
        "Foreign Task",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    deleted_comment = add_comment(session, project_id, task_id, "Deleted body")
    deleted_comment_id = deleted_comment.id
    session.delete(deleted_comment)
    older_id = add_activity(
        session,
        project_id,
        task_id,
        deleted_comment_id,
        CommentEventType.DELETED,
        datetime(2026, 7, 14, tzinfo=UTC),
    )
    tied_first_id = add_activity(
        session,
        project_id,
        task_id,
        deleted_comment_id,
        CommentEventType.UPDATED,
        datetime(2026, 7, 15, tzinfo=UTC),
    )
    tied_second_id = add_activity(
        session,
        project_id,
        task_id,
        deleted_comment_id,
        CommentEventType.CREATED,
        datetime(2026, 7, 15, tzinfo=UTC),
    )
    add_activity(
        session,
        foreign_project_id,
        foreign_task_id,
        999,
        CommentEventType.CREATED,
        datetime(2026, 7, 16, tzinfo=UTC),
    )
    session.commit()

    activities = SQLAlchemyProjectDashboardRepository(session).list_recent_activities(
        project_id, limit=2
    )

    assert [activity.id for activity in activities] == [
        tied_second_id,
        tied_first_id,
    ]
    assert older_id not in {activity.id for activity in activities}
    assert all(activity.project_id == project_id for activity in activities)
    assert all(activity.occurred_at.tzinfo is UTC for activity in activities)
    assert [activity.event_type for activity in activities] == [
        CommentEventType.CREATED,
        CommentEventType.UPDATED,
    ]
    assert all(not hasattr(activity, "body") for activity in activities)


def test_recent_activities_disappear_when_their_task_is_deleted(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    task_id = add_task(
        session,
        project_id,
        "Soon deleted",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    add_activity(
        session,
        project_id,
        task_id,
        1,
        CommentEventType.DELETED,
        datetime(2026, 7, 15, tzinfo=UTC),
    )
    session.commit()
    task = session.get(TaskModel, task_id)
    assert task is not None
    session.delete(task)
    session.commit()

    activities = SQLAlchemyProjectDashboardRepository(session).list_recent_activities(
        project_id, limit=10
    )

    assert activities == ()


@pytest.mark.parametrize("row_count", [0, 25])
def test_complete_dashboard_uses_seven_parameterized_statements_at_any_scale(
    session: Session, isolated_engine: Engine, row_count: int
) -> None:
    project_id = create_project(session, "Selected")
    as_of = datetime(2026, 7, 15, 10, 30, tzinfo=UTC)
    for index in range(row_count):
        task_id = add_task(
            session,
            project_id,
            f"Task {index}",
            status=tuple(TaskStatus)[index % len(TaskStatus)],
            priority=tuple(TaskPriority)[index % len(TaskPriority)],
            due_at=as_of + timedelta(days=index % 10),
        )
        tag_id = add_tag(session, project_id, f"Tag {index}", f"tag-{index:02}")
        session.add(TaskTagModel(project_id=project_id, task_id=task_id, tag_id=tag_id))
        comment = add_comment(session, project_id, task_id, f"Comment {index}")
        add_activity(
            session,
            project_id,
            task_id,
            comment.id,
            tuple(CommentEventType)[index % len(CommentEventType)],
            as_of + timedelta(seconds=index),
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
        result = ProjectDashboardService(
            SQLAlchemyProjectDashboardRepository(session),
            SQLAlchemyProjectRepository(session),
            clock=lambda: as_of,
        ).get_dashboard(project_id, activity_limit=50)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_statement)

    assert result.tasks.total == row_count
    assert len(result.tags) == row_count
    assert result.comments.total == row_count
    assert len(result.recent_activities) == min(row_count, 50)
    assert len(executed) == 7
    assert len(executed) <= 8
    normalized = [" ".join(statement.upper().split()) for statement, _ in executed]
    assert all(statement.startswith("SELECT ") for statement in normalized)
    assert all("?" in statement for statement, _parameters in executed)
    assert all(parameters for _statement, parameters in executed)
    assert "WHERE PROJECTS.ID = ?" in normalized[0]
    assert all("GROUP BY" in statement for statement in normalized[1:3])
    assert "CASE WHEN" in normalized[3]
    assert "COUNT(DISTINCT TASKS.ID)" in normalized[4]
    assert "COUNT(DISTINCT TASKS.ID)" in normalized[5]
    assert "LIMIT ?" in normalized[6]
    assert all("2026-07-15" not in statement for statement, _ in executed)
    assert not any(
        "SELECT TASKS.ID, TASKS.PROJECT_ID, TASKS.TITLE" in statement
        for statement in normalized
    )


def test_dashboard_is_deterministic_isolated_and_does_not_mutate_any_table(
    session: Session,
) -> None:
    project_id = create_project(session, "Selected")
    foreign_project_id = create_project(session, "Foreign")
    as_of = datetime(2026, 7, 15, 10, 30, tzinfo=UTC)
    selected_task_id = add_task(
        session,
        project_id,
        "Selected Task",
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
        due_at=as_of,
    )
    selected_tag_id = add_tag(session, project_id, "Selected Tag", "selected-tag")
    session.add(
        TaskTagModel(
            project_id=project_id,
            task_id=selected_task_id,
            tag_id=selected_tag_id,
        )
    )
    selected_comment = add_comment(
        session, project_id, selected_task_id, "Selected comment"
    )
    selected_activity_id = add_activity(
        session,
        project_id,
        selected_task_id,
        selected_comment.id,
        CommentEventType.CREATED,
        as_of,
    )
    foreign_task_id = add_task(
        session,
        foreign_project_id,
        "Foreign Task",
        status=TaskStatus.DONE,
        priority=TaskPriority.LOW,
        due_at=as_of - timedelta(days=1),
    )
    foreign_tag_id = add_tag(session, foreign_project_id, "Foreign Tag", "foreign-tag")
    session.add(
        TaskTagModel(
            project_id=foreign_project_id,
            task_id=foreign_task_id,
            tag_id=foreign_tag_id,
        )
    )
    foreign_comment = add_comment(
        session, foreign_project_id, foreign_task_id, "Foreign comment"
    )
    add_activity(
        session,
        foreign_project_id,
        foreign_task_id,
        foreign_comment.id,
        CommentEventType.CREATED,
        as_of + timedelta(days=1),
    )
    session.commit()
    before = database_fingerprint(session)
    lifecycle_events: list[str] = []

    def record_flush(
        _session: Session, _flush_context: object, _instances: object
    ) -> None:
        lifecycle_events.append("flush")

    def record_commit(_session: Session) -> None:
        lifecycle_events.append("commit")

    event.listen(session, "before_flush", record_flush)
    event.listen(session, "before_commit", record_commit)
    try:
        service = ProjectDashboardService(
            SQLAlchemyProjectDashboardRepository(session),
            SQLAlchemyProjectRepository(session),
            clock=lambda: as_of,
        )
        first = service.get_dashboard(project_id, activity_limit=50)
        second = service.get_dashboard(project_id, activity_limit=50)
    finally:
        event.remove(session, "before_flush", record_flush)
        event.remove(session, "before_commit", record_commit)

    after = database_fingerprint(session)

    assert first == second
    assert first.tasks.total == first.due.active_total == 1
    assert [(tag.id, tag.task_count) for tag in first.tags] == [(selected_tag_id, 1)]
    assert first.comments.total == first.comments.tasks_with_comments == 1
    assert [activity.id for activity in first.recent_activities] == [
        selected_activity_id
    ]
    assert all(
        activity.project_id == project_id for activity in first.recent_activities
    )
    assert before == after
    assert lifecycle_events == []
    assert not session.new
    assert not session.dirty
    assert not session.deleted


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


@pytest.mark.parametrize("row_count", [0, 25])
def test_tag_and_comment_aggregates_use_two_parameterized_set_based_statements(
    session: Session, isolated_engine: Engine, row_count: int
) -> None:
    project_id = create_project(session, "Selected")
    for index in range(row_count):
        task_id = add_task(
            session,
            project_id,
            f"Task {index}",
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            due_at=None,
        )
        tag_id = add_tag(session, project_id, f"Tag {index}", f"tag-{index:02}")
        session.add(TaskTagModel(project_id=project_id, task_id=task_id, tag_id=tag_id))
        add_comment(session, project_id, task_id, f"Comment {index}")
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
        repository.list_tag_counts(project_id)
        repository.get_comment_counts(project_id)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_statement)

    assert len(executed) == 2
    normalized = [" ".join(statement.upper().split()) for statement, _ in executed]
    assert all(statement.startswith("SELECT ") for statement in normalized)
    assert "LEFT OUTER JOIN TASK_TAGS" in normalized[0]
    assert "LEFT OUTER JOIN TASKS" in normalized[0]
    assert "COUNT(DISTINCT TASKS.ID)" in normalized[0]
    assert "GROUP BY" in normalized[0]
    assert "ORDER BY TAGS.NORMALIZED_NAME ASC, TAGS.ID ASC" in normalized[0]
    assert "JOIN TASKS" in normalized[1]
    assert "COUNT(DISTINCT TASKS.ID)" in normalized[1]
    assert all(parameters for _statement, parameters in executed)


@pytest.mark.parametrize("row_count", [0, 75])
def test_recent_activity_uses_one_parameterized_bounded_statement(
    session: Session, isolated_engine: Engine, row_count: int
) -> None:
    project_id = create_project(session, "Selected")
    task_id = add_task(
        session,
        project_id,
        "Selected Task",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        due_at=None,
    )
    for index in range(row_count):
        add_activity(
            session,
            project_id,
            task_id,
            index + 1,
            tuple(CommentEventType)[index % len(CommentEventType)],
            datetime(2026, 7, 15, tzinfo=UTC) + timedelta(seconds=index),
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
        activities = SQLAlchemyProjectDashboardRepository(
            session
        ).list_recent_activities(project_id, limit=50)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", record_statement)

    assert len(activities) == min(row_count, 50)
    assert len(executed) == 1
    statement, parameters = executed[0]
    normalized = " ".join(statement.upper().split())
    assert normalized.startswith("SELECT ")
    assert "JOIN TASKS" in normalized
    assert "JOIN TASK_COMMENTS" not in normalized
    assert "ORDER BY TASK_COMMENT_ACTIVITIES.OCCURRED_AT DESC" in normalized
    assert "TASK_COMMENT_ACTIVITIES.ID DESC" in normalized
    assert "LIMIT ?" in normalized
    assert "50" not in statement
    assert parameters
