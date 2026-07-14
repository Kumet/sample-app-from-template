from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from project_board.api.dependencies import get_task_service
from project_board.api.routes import router
from project_board.application import TaskService
from project_board.domain import Task, TaskPriority, TaskStatus
from project_board.repositories import SortOrder, TaskListQuery, TaskSort


class RecordingTaskService:
    def __init__(self) -> None:
        self.listed: tuple[int, TaskListQuery] | None = None

    def list_tasks(self, project_id: int, query: TaskListQuery) -> list[Task]:
        self.listed = (project_id, query)
        return []


@pytest.fixture
def task_list_api() -> tuple[TestClient, RecordingTaskService]:
    service = RecordingTaskService()
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_task_service] = lambda: cast(
        TaskService, service
    )
    return TestClient(application), service


def test_task_list_api_preserves_parameter_defaults(
    task_list_api: tuple[TestClient, RecordingTaskService],
) -> None:
    client, service = task_list_api

    response = client.get("/api/projects/17/tasks")

    assert response.status_code == 200
    assert response.json() == []
    assert service.listed == (17, TaskListQuery())


def test_task_list_api_parses_trimmed_q_and_scalar_filters_compatibly(
    task_list_api: tuple[TestClient, RecordingTaskService],
) -> None:
    client, service = task_list_api

    response = client.get(
        "/api/projects/17/tasks",
        params={
            "q": "  release notes  ",
            "status": "in_progress",
            "priority": "high",
            "limit": "100",
            "offset": "4",
            "sort": "updated_at",
            "order": "desc",
        },
    )

    assert response.status_code == 200
    assert service.listed == (
        17,
        TaskListQuery(
            q="release notes",
            statuses=(TaskStatus.IN_PROGRESS,),
            priorities=(TaskPriority.HIGH,),
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            limit=100,
            offset=4,
            sort=TaskSort.UPDATED_AT,
            order=SortOrder.DESC,
        ),
    )


def test_task_list_api_parses_repeated_filters_and_deduplicates_values(
    task_list_api: tuple[TestClient, RecordingTaskService],
) -> None:
    client, service = task_list_api

    response = client.get(
        "/api/projects/17/tasks",
        params=[
            ("status", "todo"),
            ("status", "done"),
            ("status", "todo"),
            ("priority", "high"),
            ("priority", "low"),
            ("priority", "high"),
        ],
    )

    assert response.status_code == 200
    assert service.listed == (
        17,
        TaskListQuery(
            statuses=(TaskStatus.TODO, TaskStatus.DONE),
            priorities=(TaskPriority.HIGH, TaskPriority.LOW),
        ),
    )


@pytest.mark.parametrize("q", ["", "   ", "x" * 101])
def test_task_list_api_rejects_invalid_q(
    task_list_api: tuple[TestClient, RecordingTaskService], q: str
) -> None:
    client, service = task_list_api

    response = client.get("/api/projects/17/tasks", params={"q": q})

    assert response.status_code == 422
    assert service.listed is None


@pytest.mark.parametrize(
    "params",
    [
        [("status", "todo"), ("status", "blocked")],
        [("priority", "low"), ("priority", "urgent")],
    ],
)
def test_task_list_api_rejects_invalid_repeated_enum_values(
    task_list_api: tuple[TestClient, RecordingTaskService],
    params: list[tuple[str, str]],
) -> None:
    client, service = task_list_api

    response = client.get("/api/projects/17/tasks", params=params)

    assert response.status_code == 422
    assert service.listed is None
