from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from project_board.domain import CommentEventType
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import TaskCommentActivityModel
from project_board.main import create_app


@pytest.fixture
def comment_api_database(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'comment-api.sqlite3'}")
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def create_task(client: TestClient, project_name: str = "Project") -> tuple[int, int]:
    project_response = client.post("/api/projects", json={"name": project_name})
    assert project_response.status_code == 201
    project_id = int(project_response.json()["id"])
    task_response = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Task"}
    )
    assert task_response.status_code == 201
    return project_id, int(task_response.json()["id"])


def comment_path(project_id: int, task_id: int) -> str:
    return f"/api/projects/{project_id}/tasks/{task_id}/comments"


def test_comment_api_crud_round_trip_and_lifecycle_events(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = comment_api_database
    project_id, task_id = create_task(client)
    path = comment_path(project_id, task_id)

    create_response = client.post(
        path, json={"body": "  <script>alert('no')</script>\nUnicode: 雪  "}
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["id"] > 0
    assert created["project_id"] == project_id
    assert created["task_id"] == task_id
    assert created["body"] == "<script>alert('no')</script>\nUnicode: 雪"
    assert created["created_at"].endswith("Z")
    assert created["updated_at"].endswith("Z")

    detail_response = client.get(f"{path}/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json() == created
    assert client.get(path).json() == [created]

    update_response = client.patch(
        f"{path}/{created['id']}", json={"body": f"  {created['body']}  "}
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["body"] == created["body"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] > created["updated_at"]

    delete_response = client.delete(f"{path}/{created['id']}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert client.get(f"{path}/{created['id']}").status_code == 404
    assert client.get(path).json() == []

    with Session(engine) as session:
        activities = session.scalars(
            select(TaskCommentActivityModel).order_by(
                TaskCommentActivityModel.occurred_at.asc(),
                TaskCommentActivityModel.id.asc(),
            )
        ).all()
    assert [activity.event_type for activity in activities] == [
        CommentEventType.CREATED,
        CommentEventType.UPDATED,
        CommentEventType.DELETED,
    ]
    assert {activity.comment_id for activity in activities} == {created["id"]}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"body": None},
        {"body": ""},
        {"body": " \n\t "},
        {"body": "x" * 2001},
        {"body": "valid", "id": 1},
        {"body": "valid", "unknown": True},
    ],
)
def test_comment_create_rejects_invalid_payloads(
    comment_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)

    response = client.post(comment_path(project_id, task_id), json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"body": None},
        {"body": "  "},
        {"body": "x" * 2001},
        {"body": "valid", "id": 1},
        {"body": "valid", "project_id": 1},
        {"body": "valid", "task_id": 1},
        {"body": "valid", "created_at": "2026-01-01T00:00:00Z"},
        {"body": "valid", "updated_at": "2026-01-01T00:00:00Z"},
        {"body": "valid", "unknown": True},
    ],
)
def test_comment_patch_requires_only_a_non_null_body(
    comment_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)
    path = comment_path(project_id, task_id)
    comment_id = client.post(path, json={"body": "Original"}).json()["id"]

    response = client.patch(f"{path}/{comment_id}", json=payload)

    assert response.status_code == 422
    assert client.get(f"{path}/{comment_id}").json()["body"] == "Original"


def test_comment_list_is_bounded_paginated_and_deterministically_ordered(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = comment_api_database
    project_id, task_id = create_task(client)
    path = comment_path(project_id, task_id)
    first = client.post(path, json={"body": "First"}).json()
    second = client.post(path, json={"body": "Second"}).json()
    third = client.post(path, json={"body": "Third"}).json()

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE task_comments SET created_at = :created_at "
                "WHERE id IN (:first_id, :second_id)"
            ),
            {
                "created_at": "2026-01-01 00:00:00.000000",
                "first_id": first["id"],
                "second_id": second["id"],
            },
        )
        connection.execute(
            text("UPDATE task_comments SET created_at = :created_at WHERE id = :id"),
            {"created_at": "2026-01-02 00:00:00.000000", "id": third["id"]},
        )

    ascending = client.get(path).json()
    descending_page = client.get(
        path, params={"order": "desc", "limit": 2, "offset": 1}
    ).json()

    assert [comment["id"] for comment in ascending] == [
        first["id"],
        second["id"],
        third["id"],
    ]
    assert [comment["id"] for comment in descending_page] == [
        first["id"],
        second["id"],
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"order": "sideways"},
    ],
)
def test_comment_list_rejects_invalid_query_parameters(
    comment_api_database: tuple[TestClient, Engine], params: dict[str, object]
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)

    response = client.get(comment_path(project_id, task_id), params=params)

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_comment_detail_conceals_cross_project_and_cross_task_ownership(
    comment_api_database: tuple[TestClient, Engine], method: str
) -> None:
    client, _ = comment_api_database
    owner_project_id, owner_task_id = create_task(client, "Owner")
    other_project_id, other_task_id = create_task(client, "Other")
    owner_path = comment_path(owner_project_id, owner_task_id)
    comment_id = client.post(owner_path, json={"body": "Private"}).json()["id"]
    request = getattr(client, method)
    kwargs = {"json": {"body": "Changed"}} if method == "patch" else {}

    cross_project = request(
        f"{comment_path(other_project_id, other_task_id)}/{comment_id}", **kwargs
    )
    cross_task = request(
        f"{comment_path(owner_project_id, other_task_id)}/{comment_id}", **kwargs
    )

    assert cross_project.status_code == 404
    assert cross_project.json() == {"detail": "Comment not found"}
    assert cross_task.status_code == 404
    assert cross_task.json() == {"detail": "Task not found"}
    assert client.get(f"{owner_path}/{comment_id}").json()["body"] == "Private"


def test_comment_endpoints_distinguish_only_missing_container_kind(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)
    path = comment_path(project_id, task_id)

    assert client.get(comment_path(999, task_id)).json() == {
        "detail": "Project not found"
    }
    assert client.get(comment_path(project_id, 999)).json() == {
        "detail": "Task not found"
    }
    assert client.get(f"{path}/999").json() == {"detail": "Comment not found"}
