from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.main import create_app


@pytest.fixture
def dashboard_api(tmp_path: Path) -> Iterator[tuple[TestClient, Engine]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'dashboard-api.sqlite3'}")
    initialize_schema(engine)
    application = create_app(session_factory=create_session_factory(engine))

    with TestClient(application) as client:
        yield client, engine

    engine.dispose()


def create_project(client: TestClient, name: str = "Project") -> int:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def dashboard_path(project_id: int) -> str:
    return f"/api/projects/{project_id}/dashboard"


def test_empty_dashboard_has_complete_zero_shape_and_owned_tags(
    dashboard_api: tuple[TestClient, Engine],
) -> None:
    client, _ = dashboard_api
    project_id = create_project(client)
    tag = client.post(
        f"/api/projects/{project_id}/tags", json={"name": "Unattached"}
    ).json()

    response = client.get(dashboard_path(project_id))

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["as_of"].endswith("Z")
    assert body["tasks"] == {
        "total": 0,
        "by_status": {"todo": 0, "in_progress": 0, "done": 0},
        "by_priority": {"low": 0, "medium": 0, "high": 0},
    }
    assert body["due"] == {
        "active_total": 0,
        "overdue": 0,
        "due_today": 0,
        "upcoming_7_days": 0,
        "later": 0,
        "no_due_date": 0,
    }
    assert body["tags"] == [{"id": tag["id"], "name": "Unattached", "task_count": 0}]
    assert body["comments"] == {"total": 0, "tasks_with_comments": 0}
    assert body["recent_activities"] == []


def test_dashboard_missing_project_uses_sanitized_404(
    dashboard_api: tuple[TestClient, Engine],
) -> None:
    client, _ = dashboard_api

    response = client.get(dashboard_path(999_999))

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_dashboard_activity_limit_controls_only_payload_free_recent_activity(
    dashboard_api: tuple[TestClient, Engine],
) -> None:
    client, _ = dashboard_api
    project_id = create_project(client)
    task = client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Task"}
    ).json()
    comments_path = f"/api/projects/{project_id}/tasks/{task['id']}/comments"
    for index in range(12):
        response = client.post(comments_path, json={"body": f"Comment {index}"})
        assert response.status_code == 201

    default_body = client.get(dashboard_path(project_id)).json()
    zero_body = client.get(
        dashboard_path(project_id), params={"activity_limit": 0}
    ).json()
    maximum_body = client.get(
        dashboard_path(project_id), params={"activity_limit": 50}
    ).json()

    assert len(default_body["recent_activities"]) == 10
    assert zero_body["recent_activities"] == []
    assert len(maximum_body["recent_activities"]) == 12
    assert default_body["tasks"] == zero_body["tasks"] == maximum_body["tasks"]
    assert default_body["comments"] == zero_body["comments"] == maximum_body["comments"]
    assert list(default_body["recent_activities"][0]) == [
        "id",
        "project_id",
        "task_id",
        "comment_id",
        "event_type",
        "occurred_at",
    ]
    activity_ids = [item["id"] for item in maximum_body["recent_activities"]]
    assert activity_ids == sorted(activity_ids, reverse=True)


@pytest.mark.parametrize(
    "value",
    [-1, 51, "true", "false", "1.0", "1.5", "ten", ""],
)
def test_dashboard_rejects_invalid_activity_limits(
    dashboard_api: tuple[TestClient, Engine], value: object
) -> None:
    client, _ = dashboard_api
    project_id = create_project(client)

    response = client.get(dashboard_path(project_id), params={"activity_limit": value})

    assert response.status_code == 422
