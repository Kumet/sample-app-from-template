from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.main import create_app


@pytest.fixture
def task_api_database(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'task-api.sqlite3'}")
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def create_project(client: TestClient, name: str = "Project") -> int:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def test_task_create_defaults_and_nested_detail_round_trip(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "  Implement Task API  ", "description": "  "},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["project_id"] == project_id
    assert created["title"] == "Implement Task API"
    assert created["description"] is None
    assert created["status"] == "todo"
    assert created["priority"] == "medium"
    assert created["due_at"] is None
    assert created["created_at"].endswith("Z")
    assert created["updated_at"].endswith("Z")

    detail = client.get(f"/api/projects/{project_id}/tasks/{created['id']}")
    assert detail.status_code == 200
    assert detail.json() == created


def test_task_create_accepts_optional_values_and_normalizes_due_at(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/tasks",
        json={
            "title": "Task",
            "description": "  Details  ",
            "status": "in_progress",
            "priority": "high",
            "due_at": "2026-07-31T09:00:00+09:00",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["description"] == "Details"
    assert created["status"] == "in_progress"
    assert created["priority"] == "high"
    assert created["due_at"] == "2026-07-31T00:00:00Z"

    remaining_enum_values = client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Completed task", "status": "done", "priority": "low"},
    )
    assert remaining_enum_values.status_code == 201
    assert remaining_enum_values.json()["status"] == "done"
    assert remaining_enum_values.json()["priority"] == "low"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "  "},
        {"title": "x" * 201},
        {"title": "Task", "description": "x" * 2001},
        {"title": "Task", "status": "doing"},
        {"title": "Task", "priority": "urgent"},
        {"title": "Task", "due_at": "2026-07-31T00:00:00"},
        {"title": "Task", "project_id": 999},
    ],
)
def test_task_create_rejects_invalid_payloads(
    task_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/tasks", json=payload)

    assert response.status_code == 422


def test_task_create_returns_404_for_missing_project(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = task_api_database

    response = client.post("/api/projects/999/tasks", json={"title": "Task"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM tasks")) == 0


def test_task_detail_hides_cross_project_ownership(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    owner_id = create_project(client, "Owner")
    other_id = create_project(client, "Other")
    task = client.post(
        f"/api/projects/{owner_id}/tasks", json={"title": "Private task"}
    ).json()

    missing_project = client.get(f"/api/projects/999/tasks/{task['id']}")
    missing_task = client.get(f"/api/projects/{owner_id}/tasks/999")
    mismatched = client.get(f"/api/projects/{other_id}/tasks/{task['id']}")

    assert missing_project.status_code == 404
    assert missing_project.json() == {"detail": "Project not found"}
    assert missing_task.status_code == 404
    assert missing_task.json() == {"detail": "Task not found"}
    assert mismatched.status_code == 404
    assert mismatched.json() == {"detail": "Task not found"}


def test_task_repository_failure_response_is_generic_and_sanitized(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = task_api_database
    project_id = create_project(client)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE tasks"))

    response = client.post(f"/api/projects/{project_id}/tasks", json={"title": "Task"})

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected persistence error occurred"}
    response_text = response.text.lower()
    assert "sqlite" not in response_text
    assert "insert" not in response_text
    assert "task-api.sqlite3" not in response_text


def test_task_patch_updates_supplied_fields_and_clears_nullable_fields(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks",
        json={
            "title": "Original",
            "description": "Details",
            "status": "todo",
            "priority": "medium",
            "due_at": "2026-08-01T09:00:00+09:00",
        },
    ).json()

    response = client.patch(
        f"/api/projects/{project_id}/tasks/{created['id']}",
        json={
            "title": "  Updated  ",
            "description": None,
            "status": "done",
            "priority": "high",
            "due_at": None,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Updated"
    assert updated["description"] is None
    assert updated["status"] == "done"
    assert updated["priority"] == "high"
    assert updated["due_at"] is None
    assert updated["project_id"] == project_id
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] != created["updated_at"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"status": None},
        {"priority": None},
        {"id": 999},
        {"project_id": 999},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"updated_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_task_patch_rejects_empty_null_required_and_immutable_fields_unchanged(
    task_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Original", "description": "Details"},
    ).json()

    response = client.patch(
        f"/api/projects/{project_id}/tasks/{created['id']}", json=payload
    )

    assert response.status_code == 422
    persisted = client.get(f"/api/projects/{project_id}/tasks/{created['id']}")
    assert persisted.status_code == 200
    assert persisted.json() == created


def test_task_patch_rejects_invalid_values_without_changing_task(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Original"}
    ).json()

    for payload in (
        {"title": "  "},
        {"title": "x" * 201},
        {"description": "x" * 2001},
        {"status": "doing"},
        {"priority": "urgent"},
        {"due_at": "2026-08-01T00:00:00"},
    ):
        response = client.patch(
            f"/api/projects/{project_id}/tasks/{created['id']}", json=payload
        )
        assert response.status_code == 422

    persisted = client.get(f"/api/projects/{project_id}/tasks/{created['id']}")
    assert persisted.json() == created


def test_task_patch_and_delete_hide_cross_project_ownership(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    owner_id = create_project(client, "Owner")
    other_id = create_project(client, "Other")
    task = client.post(
        f"/api/projects/{owner_id}/tasks", json={"title": "Owned"}
    ).json()

    patch_response = client.patch(
        f"/api/projects/{other_id}/tasks/{task['id']}", json={"title": "Changed"}
    )
    delete_response = client.delete(f"/api/projects/{other_id}/tasks/{task['id']}")
    missing_delete = client.delete(f"/api/projects/{owner_id}/tasks/999")

    assert patch_response.status_code == 404
    assert patch_response.json() == {"detail": "Task not found"}
    assert delete_response.status_code == 404
    assert delete_response.json() == {"detail": "Task not found"}
    assert missing_delete.status_code == 404
    assert missing_delete.json() == {"detail": "Task not found"}
    persisted = client.get(f"/api/projects/{owner_id}/tasks/{task['id']}")
    assert persisted.json() == task


def test_task_delete_removes_only_selected_task_and_returns_empty_204(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    selected = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Selected"}
    ).json()
    remaining = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Remaining"}
    ).json()

    response = client.delete(f"/api/projects/{project_id}/tasks/{selected['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert (
        client.get(f"/api/projects/{project_id}/tasks/{selected['id']}").status_code
        == 404
    )
    assert (
        client.get(f"/api/projects/{project_id}/tasks/{remaining['id']}").status_code
        == 200
    )


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_task_mutation_repository_failures_are_generic_and_sanitized(
    task_api_database: tuple[TestClient, Engine], method: str
) -> None:
    client, engine = task_api_database
    project_id = create_project(client)
    task = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Task"}
    ).json()
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE tasks"))

    url = f"/api/projects/{project_id}/tasks/{task['id']}"
    response = (
        client.patch(url, json={"title": "Updated"})
        if method == "patch"
        else client.delete(url)
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected persistence error occurred"}
    response_text = response.text.lower()
    assert "sqlite" not in response_text
    assert "tasks" not in response_text
    assert "task-api.sqlite3" not in response_text
