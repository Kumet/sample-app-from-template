from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import event
from sqlalchemy.engine import Engine

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.main import create_app


@pytest.fixture
def regression_database(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_database_engine(
        f"sqlite:///{tmp_path / 'comment-regressions.sqlite3'}"
    )
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def create_project(client: TestClient, name: str) -> int:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def create_task(client: TestClient, project_id: int, title: str) -> int:
    response = client.post(f"/api/projects/{project_id}/tasks", json={"title": title})
    assert response.status_code == 201
    return int(response.json()["id"])


def add_comments(client: TestClient, project_id: int, task_id: int, count: int) -> None:
    path = f"/api/projects/{project_id}/tasks/{task_id}/comments"
    for number in range(count):
        response = client.post(path, json={"body": f"Comment {number}"})
        assert response.status_code == 201


def capture_selects(
    engine: Engine, request: Callable[[], Response]
) -> tuple[Response, list[str]]:
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select"):
            statements.append(normalized)

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)
    return response, statements


def test_comment_and_activity_lists_have_constant_statement_counts(
    regression_database: tuple[TestClient, Engine],
) -> None:
    client, engine = regression_database
    project_id = create_project(client, "Statement counts")
    small_task_id = create_task(client, project_id, "One row")
    large_task_id = create_task(client, project_id, "Many rows")
    add_comments(client, project_id, small_task_id, 1)
    add_comments(client, project_id, large_task_id, 25)

    def list_path(task_id: int, collection: str) -> tuple[Response, list[str]]:
        return capture_selects(
            engine,
            lambda: client.get(
                f"/api/projects/{project_id}/tasks/{task_id}/{collection}",
                params={"limit": 100},
            ),
        )

    small_comments, small_comment_statements = list_path(small_task_id, "comments")
    large_comments, large_comment_statements = list_path(large_task_id, "comments")
    small_activities, small_activity_statements = list_path(small_task_id, "activities")
    large_activities, large_activity_statements = list_path(large_task_id, "activities")

    assert small_comments.status_code == large_comments.status_code == 200
    assert small_activities.status_code == large_activities.status_code == 200
    assert len(small_comments.json()) == len(small_activities.json()) == 1
    assert len(large_comments.json()) == len(large_activities.json()) == 25
    assert len(small_comment_statements) == len(large_comment_statements)
    assert len(small_activity_statements) == len(large_activity_statements)
    assert (
        sum(
            " from task_comments " in statement
            for statement in large_comment_statements
        )
        == 1
    )
    assert (
        sum(
            " from task_comment_activities " in statement
            for statement in large_activity_statements
        )
        == 1
    )


def test_comments_do_not_change_task_contract_or_add_task_list_queries(
    regression_database: tuple[TestClient, Engine],
) -> None:
    client, engine = regression_database
    project_id = create_project(client, "Prior feature regression")
    task_id = create_task(client, project_id, "Unchanged Task")
    tag = client.post(
        f"/api/projects/{project_id}/tags",
        json={"name": "Regression", "color": "#123456"},
    ).json()
    association = client.put(
        f"/api/projects/{project_id}/tasks/{task_id}/tags/{tag['id']}"
    )
    assert association.status_code == 204

    before, before_statements = capture_selects(
        engine, lambda: client.get(f"/api/projects/{project_id}/tasks")
    )
    comment_path = f"/api/projects/{project_id}/tasks/{task_id}/comments"
    comment = client.post(comment_path, json={"body": "Lifecycle"}).json()
    update = client.patch(
        f"{comment_path}/{comment['id']}", json={"body": "Updated lifecycle"}
    )
    assert update.status_code == 200

    after, after_statements = capture_selects(
        engine, lambda: client.get(f"/api/projects/{project_id}/tasks")
    )
    detail = client.get(f"/api/projects/{project_id}/tasks/{task_id}")

    assert before.status_code == after.status_code == detail.status_code == 200
    assert after.json() == before.json()
    assert detail.json() == before.json()[0]
    assert set(detail.json()) == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "priority",
        "due_at",
        "created_at",
        "updated_at",
        "tags",
    }
    assert detail.json()["tags"] == [tag]
    assert len(after_statements) == len(before_statements)
    assert not any(
        " from task_comments " in statement
        or " from task_comment_activities " in statement
        for statement in after_statements
    )
