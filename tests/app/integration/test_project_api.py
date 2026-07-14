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
def api_database(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    database_path = tmp_path / "api.sqlite3"
    engine = create_database_engine(f"sqlite:///{database_path}")
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def test_project_api_crud_round_trip_and_health_regression(
    api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = api_database

    created_response = client.post(
        "/api/projects",
        json={"name": "  Sample project  ", "description": "  Details  "},
    )

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["id"] > 0
    assert created["name"] == "Sample project"
    assert created["description"] == "Details"
    assert created["created_at"].endswith("Z")
    assert created["updated_at"].endswith("Z")

    project_id = created["id"]
    assert client.get(f"/api/projects/{project_id}").json() == created

    updated_response = client.patch(
        f"/api/projects/{project_id}", json={"description": "  "}
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["name"] == "Sample project"
    assert updated["description"] is None
    assert updated["created_at"] == created["created_at"]

    delete_response = client.delete(f"/api/projects/{project_id}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert client.get(f"/api/projects/{project_id}").status_code == 404

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_project_api_patch_with_null_clears_description(
    api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = api_database
    created_response = client.post(
        "/api/projects",
        json={"name": "Sample project", "description": "Details"},
    )
    assert created_response.status_code == 201
    created = created_response.json()

    response = client.patch(
        f"/api/projects/{created['id']}", json={"description": None}
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_project_delete_returns_conflict_until_owned_tasks_are_deleted(
    api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = api_database
    project = client.post("/api/projects", json={"name": "Protected"}).json()
    task = client.post(
        f"/api/projects/{project['id']}/tasks",
        json={"title": "Blocking task"},
    ).json()

    conflict_response = client.delete(f"/api/projects/{project['id']}")

    assert conflict_response.status_code == 409
    assert conflict_response.json() == {"detail": "Project has tasks"}
    assert client.get(f"/api/projects/{project['id']}").json() == project
    assert (
        client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json() == task
    )

    assert (
        client.delete(f"/api/projects/{project['id']}/tasks/{task['id']}").status_code
        == 204
    )
    delete_response = client.delete(f"/api/projects/{project['id']}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""


def test_project_list_is_ordered_by_creation_time_then_id(
    api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = api_database
    first = client.post("/api/projects", json={"name": "First"}).json()
    second = client.post("/api/projects", json={"name": "Second"}).json()
    third = client.post("/api/projects", json={"name": "Third"}).json()
    reassigned_second_id = second["id"] + 100

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE projects SET id = :new_id WHERE id = :old_id"),
            {"new_id": reassigned_second_id, "old_id": second["id"]},
        )
        connection.execute(
            text(
                "UPDATE projects SET created_at = :created_at "
                "WHERE id IN (:second_id, :third_id)"
            ),
            {
                "created_at": "2025-01-02 00:00:00.000000",
                "second_id": reassigned_second_id,
                "third_id": third["id"],
            },
        )
        connection.execute(
            text("UPDATE projects SET created_at = :created_at WHERE id = :first_id"),
            {
                "created_at": "2025-01-01 00:00:00.000000",
                "first_id": first["id"],
            },
        )

    response = client.get("/api/projects")

    assert response.status_code == 200
    projects = response.json()
    assert [project["id"] for project in projects] == [
        first["id"],
        third["id"],
        reassigned_second_id,
    ]
    assert [project["name"] for project in projects] == ["First", "Third", "Second"]


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_project_api_returns_404_for_missing_projects(
    api_database: tuple[TestClient, Engine], method: str
) -> None:
    client, _ = api_database
    request = getattr(client, method)
    kwargs = {"json": {"name": "Updated"}} if method == "patch" else {}

    response = request("/api/projects/999", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/projects", {}),
        ("/api/projects", {"name": "  "}),
        ("/api/projects", {"name": "x" * 101}),
        ("/api/projects", {"name": "Valid", "description": "x" * 1001}),
        ("/api/projects/1", {}),
        ("/api/projects/1", {"name": None}),
        ("/api/projects/1", {"name": "  "}),
        ("/api/projects/1", {"name": "x" * 101}),
        ("/api/projects/1", {"description": "x" * 1001}),
    ],
)
def test_project_api_returns_422_for_invalid_requests(
    api_database: tuple[TestClient, Engine], path: str, payload: dict[str, object]
) -> None:
    client, _ = api_database
    request = client.patch if path.endswith("/1") else client.post

    response = request(path, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "payload", "sql_keyword"),
    [
        ("get", None, "select"),
        ("post", {"name": "Sample project"}, "insert"),
    ],
)
def test_repository_failure_response_is_generic_and_sanitized(
    api_database: tuple[TestClient, Engine],
    method: str,
    payload: dict[str, object] | None,
    sql_keyword: str,
) -> None:
    client, engine = api_database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE projects"))

    request = getattr(client, method)
    kwargs = {"json": payload} if payload is not None else {}
    response = request("/api/projects", **kwargs)

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected persistence error occurred"}
    response_text = response.text.lower()
    assert "sqlite" not in response_text
    assert sql_keyword not in response_text
    assert "api.sqlite3" not in response_text
