from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import ProjectModel, TaskModel
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
        {"title": None},
        {"title": "  "},
        {"title": "x" * 201},
        {"title": "Task", "description": "x" * 2001},
        {"title": "Task", "status": None},
        {"title": "Task", "status": "doing"},
        {"title": "Task", "priority": None},
        {"title": "Task", "priority": "urgent"},
        {"title": "Task", "due_at": "2026-07-31T00:00:00"},
        {"title": "Task", "id": 999},
        {"title": "Task", "project_id": 999},
        {"title": "Task", "created_at": "2026-01-01T00:00:00Z"},
        {"title": "Task", "updated_at": "2026-01-01T00:00:00Z"},
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


def test_task_list_filters_strict_due_bounds_paginates_and_isolates_projects(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client, "Listed")
    other_project_id = create_project(client, "Other")
    base = datetime(2026, 7, 14, tzinfo=UTC)

    for title, task_status, priority, due_at in (
        ("Before", "in_progress", "high", base + timedelta(days=1)),
        ("Boundary", "in_progress", "high", base + timedelta(days=2)),
        ("After", "done", "low", base + timedelta(days=3)),
        ("No due", "todo", "medium", None),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "title": title,
                "status": task_status,
                "priority": priority,
                "due_at": None if due_at is None else due_at.isoformat(),
            },
        )
        assert response.status_code == 201
    client.post(
        f"/api/projects/{other_project_id}/tasks", json={"title": "Not visible"}
    )

    filtered = client.get(
        f"/api/projects/{project_id}/tasks",
        params={
            "status": "in_progress",
            "priority": "high",
            "due_after": base.isoformat(),
            "due_before": (base + timedelta(days=2)).isoformat(),
        },
    )
    status_filtered = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"status": "in_progress"},
    )
    priority_filtered = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"priority": "high"},
    )
    due_after_filtered = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"due_after": (base + timedelta(days=2)).isoformat()},
    )
    due_before_filtered = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"due_before": (base + timedelta(days=2)).isoformat()},
    )
    paged = client.get(
        f"/api/projects/{project_id}/tasks", params={"limit": 1, "offset": 1}
    )

    assert filtered.status_code == 200
    assert [task["title"] for task in filtered.json()] == ["Before"]
    assert [task["title"] for task in status_filtered.json()] == [
        "Before",
        "Boundary",
    ]
    assert [task["title"] for task in priority_filtered.json()] == [
        "Before",
        "Boundary",
    ]
    assert [task["title"] for task in due_after_filtered.json()] == ["After"]
    assert [task["title"] for task in due_before_filtered.json()] == ["Before"]
    assert [task["title"] for task in paged.json()] == ["Boundary"]


def test_task_list_normalizes_aware_due_filters_to_utc(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "UTC boundary", "due_at": "2026-07-14T00:00:00Z"},
    )
    assert created.status_code == 201

    before = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"due_before": "2026-07-14T09:00:01+09:00"},
    )
    after = client.get(
        f"/api/projects/{project_id}/tasks",
        params={"due_after": "2026-07-14T08:59:59+09:00"},
    )

    assert before.status_code == 200
    assert [task["title"] for task in before.json()] == ["UTC boundary"]
    assert after.status_code == 200
    assert [task["title"] for task in after.json()] == ["UTC boundary"]


@pytest.mark.parametrize(
    ("params", "expected_titles"),
    [
        ({"sort": "due_at", "order": "asc"}, ["High", "Low", "No due"]),
        ({"sort": "due_at", "order": "desc"}, ["Low", "High", "No due"]),
        ({"sort": "priority", "order": "asc"}, ["Low", "No due", "High"]),
        ({"sort": "priority", "order": "desc"}, ["High", "No due", "Low"]),
    ],
)
def test_task_list_deterministic_due_and_semantic_priority_sorting(
    task_api_database: tuple[TestClient, Engine],
    params: dict[str, str],
    expected_titles: list[str],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    base = datetime(2026, 7, 14, tzinfo=UTC)
    for title, priority, due_at in (
        ("Low", "low", base + timedelta(days=2)),
        ("High", "high", base + timedelta(days=1)),
        ("No due", "medium", None),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "title": title,
                "priority": priority,
                "due_at": None if due_at is None else due_at.isoformat(),
            },
        )
        assert response.status_code == 201

    response = client.get(f"/api/projects/{project_id}/tasks", params=params)

    assert response.status_code == 200
    assert [task["title"] for task in response.json()] == expected_titles


@pytest.mark.parametrize(
    "params",
    [
        {"status": "doing"},
        {"priority": "urgent"},
        {"due_before": "2026-07-14T00:00:00"},
        {"due_after": "2026-07-14T00:00:00"},
        {"limit": "0"},
        {"limit": "101"},
        {"offset": "-1"},
        {"sort": "title"},
        {"order": "sideways"},
    ],
)
def test_task_list_rejects_invalid_query_values(
    task_api_database: tuple[TestClient, Engine], params: dict[str, str]
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)

    response = client.get(f"/api/projects/{project_id}/tasks", params=params)

    assert response.status_code == 422


def test_task_list_returns_missing_project_and_repository_errors_safely(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = task_api_database
    missing = client.get("/api/projects/999/tasks")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Project not found"}

    project_id = create_project(client)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE tasks"))

    failed = client.get(f"/api/projects/{project_id}/tasks")
    assert failed.status_code == 500
    assert failed.json() == {"detail": "An unexpected persistence error occurred"}
    assert "sqlite" not in failed.text.lower()


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


def test_task_patch_preserves_every_omitted_mutable_field(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks",
        json={
            "title": "Original",
            "description": "Keep this",
            "status": "in_progress",
            "priority": "high",
            "due_at": "2026-08-01T00:00:00Z",
        },
    ).json()

    response = client.patch(
        f"/api/projects/{project_id}/tasks/{created['id']}",
        json={"title": "Renamed"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Renamed"
    for field_name in ("description", "status", "priority", "due_at"):
        assert updated[field_name] == created[field_name]
    assert updated["id"] == created["id"]
    assert updated["project_id"] == created["project_id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] != created["updated_at"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"status": None},
        {"priority": None},
    ],
)
def test_task_patch_rejects_empty_and_null_required_fields_unchanged(
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


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", 999),
        ("project_id", 999),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("updated_at", "2026-01-01T00:00:00Z"),
    ],
)
def test_task_patch_rejects_each_immutable_field_without_persisting_changes(
    task_api_database: tuple[TestClient, Engine],
    field_name: str,
    value: object,
) -> None:
    client, engine = task_api_database
    project_id = create_project(client)
    created = client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Original", "description": "Details"},
    ).json()
    with engine.connect() as connection:
        before = dict(
            connection.execute(select(TaskModel).where(TaskModel.id == created["id"]))
            .mappings()
            .one()
        )

    response = client.patch(
        f"/api/projects/{project_id}/tasks/{created['id']}",
        json={field_name: value},
    )

    assert response.status_code == 422
    assert any(
        error["loc"] == ["body", field_name] and error["type"] == "extra_forbidden"
        for error in response.json()["detail"]
    )
    with engine.connect() as connection:
        after = dict(
            connection.execute(select(TaskModel).where(TaskModel.id == created["id"]))
            .mappings()
            .one()
        )
    assert after == before
    assert (
        client.get(f"/api/projects/{project_id}/tasks/{created['id']}").json()
        == created
    )


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
    client, engine = task_api_database
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
    with engine.connect() as connection:
        selected_row = connection.scalar(
            select(TaskModel.id).where(TaskModel.id == selected["id"])
        )
        remaining_row = connection.scalar(
            select(TaskModel.id).where(TaskModel.id == remaining["id"])
        )
        project_row = connection.scalar(
            select(ProjectModel.id).where(ProjectModel.id == project_id)
        )
    assert selected_row is None
    assert remaining_row == remaining["id"]
    assert project_row == project_id


def test_complete_task_lifecycle_remains_isolated_between_projects(
    task_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = task_api_database
    owner_id = create_project(client, "Owner")
    other_id = create_project(client, "Other")

    created_response = client.post(
        f"/api/projects/{owner_id}/tasks",
        json={"title": "Lifecycle", "priority": "high"},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    detail = client.get(f"/api/projects/{owner_id}/tasks/{created['id']}")
    assert detail.status_code == 200
    assert detail.json() == created

    updated_response = client.patch(
        f"/api/projects/{owner_id}/tasks/{created['id']}",
        json={"title": "Completed", "status": "done"},
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["title"] == "Completed"
    assert updated["status"] == "done"

    owner_list = client.get(f"/api/projects/{owner_id}/tasks")
    other_list = client.get(f"/api/projects/{other_id}/tasks")
    assert owner_list.status_code == 200
    assert owner_list.json() == [updated]
    assert other_list.status_code == 200
    assert other_list.json() == []

    deleted = client.delete(f"/api/projects/{owner_id}/tasks/{created['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/projects/{owner_id}/tasks").json() == []


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
