from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import TagModel, TaskTagModel
from project_board.main import create_app


@pytest.fixture
def tag_api_database(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'tag-api.sqlite3'}")
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def create_project(client: TestClient, name: str = "Project") -> int:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def create_task(client: TestClient, project_id: int, title: str = "Task") -> int:
    response = client.post(f"/api/projects/{project_id}/tasks", json={"title": title})
    assert response.status_code == 201
    return int(response.json()["id"])


def create_tag(
    client: TestClient,
    project_id: int,
    name: str = "Backend",
    color: str | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/projects/{project_id}/tags",
        json={"name": name, "color": color},
    )
    assert response.status_code == 201
    return response.json()


def test_tag_api_crud_normalizes_public_fields_and_returns_empty_delete(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)

    created_response = client.post(
        f"/api/projects/{project_id}/tags",
        json={"name": "  Backend  ", "color": "#a1b2c3"},
    )

    assert created_response.status_code == 201
    created = created_response.json()
    assert set(created) == {
        "id",
        "project_id",
        "name",
        "color",
        "created_at",
        "updated_at",
    }
    assert created["id"] > 0
    assert created["project_id"] == project_id
    assert created["name"] == "Backend"
    assert created["color"] == "#A1B2C3"
    assert created["created_at"].endswith("Z")
    assert created["updated_at"].endswith("Z")

    detail = client.get(f"/api/projects/{project_id}/tags/{created['id']}")
    assert detail.status_code == 200
    assert detail.json() == created

    updated_response = client.patch(
        f"/api/projects/{project_id}/tags/{created['id']}",
        json={"name": "  API  ", "color": None},
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["name"] == "API"
    assert updated["color"] is None
    assert updated["created_at"] == created["created_at"]

    delete_response = client.delete(f"/api/projects/{project_id}/tags/{created['id']}")
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert (
        client.get(f"/api/projects/{project_id}/tags/{created['id']}").status_code
        == 404
    )


def test_tag_list_uses_deterministic_normalized_name_order(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)
    create_tag(client, project_id, "zebra")
    api = create_tag(client, project_id, "API")
    create_tag(client, project_id, "backend")

    response = client.get(f"/api/projects/{project_id}/tags")

    assert response.status_code == 200
    assert [tag["name"] for tag in response.json()] == ["API", "backend", "zebra"]
    assert response.json()[0] == api


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": "  "},
        {"name": "x" * 51},
        {"name": "Tag", "color": ""},
        {"name": "Tag", "color": "#12345"},
        {"name": "Tag", "color": "#GGGGGG"},
        {"name": "Tag", "color": 123456},
        {"name": "Tag", "id": 1},
        {"name": "Tag", "project_id": 1},
        {"name": "Tag", "created_at": "2026-07-14T00:00:00Z"},
        {"name": "Tag", "updated_at": "2026-07-14T00:00:00Z"},
        {"name": "Tag", "normalized_name": "tag"},
    ],
)
def test_tag_create_rejects_invalid_and_forbidden_fields(
    tag_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)

    response = client.post(f"/api/projects/{project_id}/tags", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": "  "},
        {"name": "x" * 51},
        {"color": ""},
        {"color": "#12345g"},
        {"id": 1},
        {"project_id": 1},
        {"created_at": "2026-07-14T00:00:00Z"},
        {"updated_at": "2026-07-14T00:00:00Z"},
        {"normalized_name": "backend"},
    ],
)
def test_tag_patch_rejects_invalid_and_immutable_fields_without_changes(
    tag_api_database: tuple[TestClient, Engine], payload: dict[str, object]
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)
    tag = create_tag(client, project_id, color="#AABBCC")

    response = client.patch(
        f"/api/projects/{project_id}/tags/{tag['id']}", json=payload
    )

    assert response.status_code == 422
    persisted = client.get(f"/api/projects/{project_id}/tags/{tag['id']}").json()
    assert persisted == tag


def test_duplicate_tag_create_and_rename_map_to_stable_conflict(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)
    original = create_tag(client, project_id, "Backend")
    renamed = create_tag(client, project_id, "API")

    duplicate_create = client.post(
        f"/api/projects/{project_id}/tags", json={"name": "backend"}
    )
    duplicate_rename = client.patch(
        f"/api/projects/{project_id}/tags/{renamed['id']}",
        json={"name": "BACKEND"},
    )

    assert duplicate_create.status_code == 409
    assert duplicate_create.json() == {"detail": "Tag name already exists"}
    assert duplicate_rename.status_code == 409
    assert duplicate_rename.json() == {"detail": "Tag name already exists"}
    assert (
        client.get(f"/api/projects/{project_id}/tags/{original['id']}").json()
        == original
    )
    assert (
        client.get(f"/api/projects/{project_id}/tags/{renamed['id']}").json() == renamed
    )


def test_case_only_self_rename_succeeds_through_tag_api(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    project_id = create_project(client)
    tag = create_tag(client, project_id, "Backend")

    response = client.patch(
        f"/api/projects/{project_id}/tags/{tag['id']}",
        json={"name": "BACKEND"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "BACKEND"


def test_tag_endpoints_hide_cross_project_ownership_and_missing_resources(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    owner_id = create_project(client, "Owner")
    other_id = create_project(client, "Other")
    tag = create_tag(client, owner_id)

    missing_project = client.get("/api/projects/999/tags")
    missing_tag = client.get(f"/api/projects/{owner_id}/tags/999")
    mismatched = client.get(f"/api/projects/{other_id}/tags/{tag['id']}")

    assert missing_project.status_code == 404
    assert missing_project.json() == {"detail": "Project not found"}
    assert missing_tag.status_code == 404
    assert missing_tag.json() == {"detail": "Tag not found"}
    assert mismatched.status_code == 404
    assert mismatched.json() == {"detail": "Tag not found"}

    for method, payload in ((client.patch, {"name": "Hidden"}), (client.delete, None)):
        kwargs = {} if payload is None else {"json": payload}
        response = method(f"/api/projects/{other_id}/tags/{tag['id']}", **kwargs)
        assert response.status_code == 404
        assert response.json() == {"detail": "Tag not found"}


def test_task_tag_attach_and_detach_are_idempotent_empty_204_operations(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = tag_api_database
    project_id = create_project(client)
    task_id = create_task(client, project_id)
    tag = create_tag(client, project_id)
    path = f"/api/projects/{project_id}/tasks/{task_id}/tags/{tag['id']}"

    for _ in range(2):
        response = client.put(path)
        assert response.status_code == 204
        assert response.content == b""

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 1

    for _ in range(2):
        response = client.delete(path)
        assert response.status_code == 204
        assert response.content == b""

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TaskTagModel)) == 0


def test_task_tag_association_maps_missing_and_cross_project_owners_to_404(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = tag_api_database
    owner_id = create_project(client, "Owner")
    other_id = create_project(client, "Other")
    task_id = create_task(client, owner_id)
    tag = create_tag(client, owner_id)

    cases = (
        (f"/api/projects/999/tasks/{task_id}/tags/{tag['id']}", "Project not found"),
        (f"/api/projects/{owner_id}/tasks/999/tags/{tag['id']}", "Task not found"),
        (
            f"/api/projects/{other_id}/tasks/{task_id}/tags/{tag['id']}",
            "Task not found",
        ),
        (f"/api/projects/{owner_id}/tasks/{task_id}/tags/999", "Tag not found"),
    )
    for path, detail in cases:
        for method in (client.put, client.delete):
            response = method(path)
            assert response.status_code == 404
            assert response.json() == {"detail": detail}


def test_tag_repository_failure_response_is_generic_and_sanitized(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = tag_api_database
    project_id = create_project(client)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE tags"))

    response = client.get(f"/api/projects/{project_id}/tags")

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected persistence error occurred"}
    response_text = response.text.lower()
    assert "sqlite" not in response_text
    assert "select" not in response_text
    assert "tag-api.sqlite3" not in response_text


def test_tag_api_persists_internal_normalized_name_without_disclosing_it(
    tag_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = tag_api_database
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/tags", json={"name": "  Straße  "}
    )

    assert response.status_code == 201
    assert "normalized_name" not in response.json()
    with Session(engine) as session:
        persisted = session.scalar(select(TagModel))
        assert persisted is not None
        assert persisted.name == "Straße"
        assert persisted.normalized_name == "strasse"
