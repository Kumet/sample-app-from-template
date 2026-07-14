from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import CommentEventType
from project_board.infrastructure import (
    create_database_engine,
    create_session_factory,
    initialize_schema,
)
from project_board.infrastructure.models import (
    ProjectModel,
    TaskCommentActivityModel,
    TaskCommentModel,
    TaskModel,
)
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


def activity_path(project_id: int, task_id: int) -> str:
    return f"/api/projects/{project_id}/tasks/{task_id}/activities"


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


def test_activity_api_lists_payload_free_lifecycle_history_after_comment_deletion(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)
    comments = comment_path(project_id, task_id)
    activities = activity_path(project_id, task_id)
    created = client.post(comments, json={"body": "Sensitive body"}).json()

    assert (
        client.patch(
            f"{comments}/{created['id']}", json={"body": "Changed body"}
        ).status_code
        == 200
    )
    assert client.delete(f"{comments}/{created['id']}").status_code == 204

    response = client.get(activities)

    assert response.status_code == 200
    history = response.json()
    assert [item["event_type"] for item in history] == [
        "comment_created",
        "comment_updated",
        "comment_deleted",
    ]
    assert {item["comment_id"] for item in history} == {created["id"]}
    assert all(item["project_id"] == project_id for item in history)
    assert all(item["task_id"] == task_id for item in history)
    assert all(item["id"] > 0 for item in history)
    assert all(item["occurred_at"].endswith("Z") for item in history)
    assert all("body" not in item for item in history)


def test_activity_api_filters_before_deterministic_order_and_pagination(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = comment_api_database
    project_id, task_id = create_task(client)
    comments = comment_path(project_id, task_id)
    activities = activity_path(project_id, task_id)
    first_comment = client.post(comments, json={"body": "First"}).json()
    second_comment = client.post(comments, json={"body": "Second"}).json()
    assert (
        client.patch(
            f"{comments}/{first_comment['id']}", json={"body": "First update"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{comments}/{second_comment['id']}", json={"body": "Second update"}
        ).status_code
        == 200
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE task_comment_activities "
                "SET occurred_at = '2026-01-01 00:00:00.000000'"
            )
        )

    all_history = client.get(activities).json()
    filtered_page = client.get(
        activities,
        params={
            "event_type": "comment_updated",
            "order": "desc",
            "limit": 1,
            "offset": 1,
        },
    ).json()
    updated_history = [
        item for item in all_history if item["event_type"] == "comment_updated"
    ]

    assert [item["id"] for item in all_history] == sorted(
        item["id"] for item in all_history
    )
    assert len(updated_history) == 2
    assert filtered_page == [updated_history[1]]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"order": "sideways"},
        {"event_type": "comment_restored"},
    ],
)
def test_activity_api_rejects_invalid_query_parameters(
    comment_api_database: tuple[TestClient, Engine], params: dict[str, object]
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)

    response = client.get(activity_path(project_id, task_id), params=params)

    assert response.status_code == 422


def test_activity_api_conceals_missing_and_foreign_owners(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = comment_api_database
    owner_project_id, owner_task_id = create_task(client, "Owner")
    other_project_id, other_task_id = create_task(client, "Other")
    owner_comments = comment_path(owner_project_id, owner_task_id)
    client.post(owner_comments, json={"body": "Private activity"})

    assert client.get(activity_path(owner_project_id, owner_task_id)).status_code == 200
    assert client.get(activity_path(other_project_id, other_task_id)).json() == []
    assert client.get(activity_path(999, owner_task_id)).json() == {
        "detail": "Project not found"
    }
    assert client.get(activity_path(owner_project_id, 999)).json() == {
        "detail": "Task not found"
    }
    assert client.get(activity_path(other_project_id, owner_task_id)).json() == {
        "detail": "Task not found"
    }


def test_task_delete_physically_cascades_comment_rows_without_cross_project_effects(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = comment_api_database
    owner_project_id, selected_task_id = create_task(client, "Owner")
    remaining_task = client.post(
        f"/api/projects/{owner_project_id}/tasks", json={"title": "Remaining"}
    ).json()
    other_project_id, other_task_id = create_task(client, "Other")

    selected_comment = client.post(
        comment_path(owner_project_id, selected_task_id),
        json={"body": "Selected private body"},
    ).json()
    deleted_comment = client.post(
        comment_path(owner_project_id, selected_task_id),
        json={"body": "Deleted private body"},
    ).json()
    assert (
        client.delete(
            f"{comment_path(owner_project_id, selected_task_id)}/"
            f"{deleted_comment['id']}"
        ).status_code
        == 204
    )
    remaining_comment = client.post(
        comment_path(owner_project_id, remaining_task["id"]),
        json={"body": "Remaining body"},
    ).json()
    other_comment = client.post(
        comment_path(other_project_id, other_task_id),
        json={"body": "Other body"},
    ).json()

    concealed_delete = client.delete(
        f"/api/projects/{other_project_id}/tasks/{selected_task_id}"
    )
    assert concealed_delete.status_code == 404
    assert concealed_delete.json() == {"detail": "Task not found"}

    response = client.delete(
        f"/api/projects/{owner_project_id}/tasks/{selected_task_id}"
    )

    assert response.status_code == 204
    assert response.content == b""
    with Session(engine) as session:
        assert session.get(TaskModel, selected_task_id) is None
        assert (
            session.scalars(
                select(TaskCommentModel).where(
                    TaskCommentModel.project_id == owner_project_id,
                    TaskCommentModel.task_id == selected_task_id,
                )
            ).all()
            == []
        )
        assert (
            session.scalars(
                select(TaskCommentActivityModel).where(
                    TaskCommentActivityModel.project_id == owner_project_id,
                    TaskCommentActivityModel.task_id == selected_task_id,
                )
            ).all()
            == []
        )
        assert session.get(TaskCommentModel, selected_comment["id"]) is None
        assert session.get(TaskCommentModel, remaining_comment["id"]) is not None
        assert session.get(TaskCommentModel, other_comment["id"]) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TaskCommentActivityModel)
                .where(
                    TaskCommentActivityModel.task_id.in_(
                        (remaining_task["id"], other_task_id)
                    )
                )
            )
            == 2
        )

    assert client.get(comment_path(owner_project_id, remaining_task["id"])).json() == [
        remaining_comment
    ]
    assert client.get(comment_path(other_project_id, other_task_id)).json() == [
        other_comment
    ]


def test_project_delete_stays_blocked_until_task_cascade_removes_child_rows(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, engine = comment_api_database
    selected_project_id, selected_task_id = create_task(client, "Selected")
    other_project_id, other_task_id = create_task(client, "Other")
    selected_comment = client.post(
        comment_path(selected_project_id, selected_task_id),
        json={"body": "Selected child"},
    ).json()
    other_comment = client.post(
        comment_path(other_project_id, other_task_id), json={"body": "Other child"}
    ).json()

    conflict = client.delete(f"/api/projects/{selected_project_id}")

    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Project has tasks"}
    with Session(engine) as session:
        assert session.get(ProjectModel, selected_project_id) is not None
        assert session.get(TaskModel, selected_task_id) is not None
        assert session.get(TaskCommentModel, selected_comment["id"]) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TaskCommentActivityModel)
                .where(TaskCommentActivityModel.task_id == selected_task_id)
            )
            == 1
        )

    task_delete = client.delete(
        f"/api/projects/{selected_project_id}/tasks/{selected_task_id}"
    )
    project_delete = client.delete(f"/api/projects/{selected_project_id}")

    assert task_delete.status_code == 204
    assert project_delete.status_code == 204
    with Session(engine) as session:
        assert session.get(ProjectModel, selected_project_id) is None
        assert session.get(TaskModel, selected_task_id) is None
        assert (
            session.scalars(
                select(TaskCommentModel).where(
                    TaskCommentModel.project_id == selected_project_id
                )
            ).all()
            == []
        )
        assert (
            session.scalars(
                select(TaskCommentActivityModel).where(
                    TaskCommentActivityModel.project_id == selected_project_id
                )
            ).all()
            == []
        )
        assert session.get(ProjectModel, other_project_id) is not None
        assert session.get(TaskModel, other_task_id) is not None
        assert session.get(TaskCommentModel, other_comment["id"]) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TaskCommentActivityModel)
                .where(TaskCommentActivityModel.task_id == other_task_id)
            )
            == 1
        )


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_activity_api_has_no_mutation_routes(
    comment_api_database: tuple[TestClient, Engine], method: str
) -> None:
    client, _ = comment_api_database
    project_id, task_id = create_task(client)

    response = client.request(
        method,
        activity_path(project_id, task_id),
        json={"event_type": "comment_created"},
    )

    assert response.status_code == 405


def test_activity_api_contract_exposes_only_the_read_only_collection_route(
    comment_api_database: tuple[TestClient, Engine],
) -> None:
    client, _ = comment_api_database
    paths = client.get("/openapi.json").json()["paths"]
    activity_routes = {
        path: operations for path, operations in paths.items() if "activities" in path
    }
    collection_path = "/api/projects/{project_id}/tasks/{task_id}/activities"

    assert set(activity_routes) == {collection_path}
    assert set(activity_routes[collection_path]) == {"get"}


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_comment_mutation_failure_is_atomic_and_returns_only_sanitized_error(
    comment_api_database: tuple[TestClient, Engine], operation: str
) -> None:
    client, engine = comment_api_database
    project_id, task_id = create_task(client)
    path = comment_path(project_id, task_id)
    original = None
    if operation != "create":
        original = client.post(path, json={"body": "Original"}).json()

    def fail_activity_insert(*_args: object) -> None:
        raise SQLAlchemyError(
            "forced SQL failure: task_comment_activities /private/db.sqlite3"
        )

    event.listen(
        TaskCommentActivityModel, "before_insert", fail_activity_insert, once=True
    )
    if operation == "create":
        failed = client.post(path, json={"body": "Failed"})
    elif operation == "update":
        assert original is not None
        failed = client.patch(f"{path}/{original['id']}", json={"body": "Failed"})
    else:
        assert original is not None
        failed = client.delete(f"{path}/{original['id']}")

    assert failed.status_code == 500
    assert failed.json() == {"detail": "An unexpected persistence error occurred"}
    assert "task_comment_activities" not in failed.text
    assert "db.sqlite3" not in failed.text

    with Session(engine) as session:
        comments = session.scalars(select(TaskCommentModel)).all()
        event_types = session.scalars(
            select(TaskCommentActivityModel.event_type).order_by(
                TaskCommentActivityModel.id
            )
        ).all()
        assert session.scalar(
            select(func.count()).select_from(TaskCommentActivityModel)
        ) == len(event_types)

    if operation == "create":
        assert comments == []
        assert event_types == []
        recovered = client.post(path, json={"body": "Recovered"})
        assert recovered.status_code == 201
        return

    assert original is not None
    assert len(comments) == 1
    assert comments[0].id == original["id"]
    assert comments[0].body == "Original"
    assert event_types == [CommentEventType.CREATED.value]

    if operation == "update":
        recovered = client.patch(f"{path}/{original['id']}", json={"body": "Recovered"})
        assert recovered.status_code == 200
        assert recovered.json()["body"] == "Recovered"
    else:
        recovered = client.delete(f"{path}/{original['id']}")
        assert recovered.status_code == 204
