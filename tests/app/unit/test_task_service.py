import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_board.application import TaskService
from project_board.domain import (
    Project,
    ProjectNotFound,
    RepositoryError,
    Task,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskValidationError,
)
from project_board.repositories import TaskListQuery

NOW = datetime(2026, 2, 1, 12, tzinfo=UTC)
LATER = datetime(2026, 2, 2, 12, tzinfo=UTC)


def make_project(project_id: int = 1) -> Project:
    return Project(project_id, "Project", None, NOW, NOW)


def make_task(task_id: int = 1, project_id: int = 1, **changes: object) -> Task:
    values = {
        "id": task_id,
        "project_id": project_id,
        "title": "Sample task",
        "description": "Description",
        "status": TaskStatus.TODO,
        "priority": TaskPriority.MEDIUM,
        "due_at": datetime(2026, 3, 1, tzinfo=UTC),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return Task(**values)  # type: ignore[arg-type]


class StubProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects = {project.id: project for project in projects or []}

    def create(self, project: Project) -> Project:
        raise NotImplementedError

    def list(self) -> list[Project]:
        return list(self.projects.values())

    def get(self, project_id: int) -> Project | None:
        return self.projects.get(project_id)

    def update(self, project: Project) -> Project | None:
        raise NotImplementedError

    def delete(self, project_id: int) -> bool:
        raise NotImplementedError


class StubTaskRepository:
    def __init__(self, tasks: list[Task] | None = None) -> None:
        self.tasks = {(task.project_id, task.id): task for task in tasks or []}
        self.created: Task | None = None
        self.updated: Task | None = None
        self.deleted_key: tuple[int, int] | None = None
        self.listed_query: tuple[int, TaskListQuery] | None = None

    def create(self, task: Task) -> Task:
        self.created = task
        persisted = replace(task, id=10)
        self.tasks[(persisted.project_id, persisted.id)] = persisted
        return persisted

    def list(self, project_id: int, query: TaskListQuery) -> list[Task]:
        self.listed_query = (project_id, query)
        return [
            task
            for (owned_project_id, _), task in self.tasks.items()
            if owned_project_id == project_id
        ]

    def get(self, project_id: int, task_id: int) -> Task | None:
        return self.tasks.get((project_id, task_id))

    def update(self, task: Task) -> Task | None:
        self.updated = task
        key = (task.project_id, task.id)
        if key not in self.tasks:
            return None
        self.tasks[key] = task
        return task

    def delete(self, project_id: int, task_id: int) -> bool:
        self.deleted_key = (project_id, task_id)
        return self.tasks.pop((project_id, task_id), None) is not None


def make_service(
    tasks: StubTaskRepository,
    projects: StubProjectRepository | None = None,
) -> TaskService:
    return TaskService(
        tasks,
        projects or StubProjectRepository([make_project()]),
        clock=lambda: LATER,
    )


def test_importing_task_service_does_not_load_sqlalchemy_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.application.task_service

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_project_repository",
    "project_board.repositories.sqlalchemy_task_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps([name for name in watched_modules if name in sys.modules]))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_create_task_applies_defaults_and_delegates_to_repository() -> None:
    repository = StubTaskRepository()

    created = make_service(repository).create_task(1, "  New task  ")

    assert created.id == 10
    assert repository.created == Task(
        0,
        1,
        "New task",
        None,
        TaskStatus.TODO,
        TaskPriority.MEDIUM,
        None,
        LATER,
        LATER,
    )


def test_create_task_accepts_optional_values_and_normalizes_due_at() -> None:
    repository = StubTaskRepository()
    offset = timezone(timedelta(hours=9))

    created = make_service(repository).create_task(
        1,
        "Task",
        "  Details  ",
        TaskStatus.IN_PROGRESS,
        TaskPriority.HIGH,
        datetime(2026, 3, 1, 9, tzinfo=offset),
    )

    assert created.description == "Details"
    assert created.status is TaskStatus.IN_PROGRESS
    assert created.priority is TaskPriority.HIGH
    assert created.due_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_create_task_rejects_missing_project_without_persisting() -> None:
    repository = StubTaskRepository()
    service = make_service(repository, StubProjectRepository())

    with pytest.raises(ProjectNotFound):
        service.create_task(7, "Task")

    assert repository.created is None


def test_get_task_returns_only_owned_task() -> None:
    task = make_task(4)

    assert make_service(StubTaskRepository([task])).get_task(1, 4) is task


def test_get_task_distinguishes_missing_project_from_missing_owned_task() -> None:
    repository = StubTaskRepository([make_task(4, project_id=2)])

    with pytest.raises(ProjectNotFound):
        make_service(repository, StubProjectRepository()).get_task(1, 4)

    with pytest.raises(TaskNotFound):
        make_service(repository).get_task(1, 4)


def test_list_tasks_requires_project_and_delegates_query() -> None:
    owned = make_task(4)
    repository = StubTaskRepository([owned, make_task(5, project_id=2)])
    query = TaskListQuery(status=TaskStatus.TODO, limit=10, offset=2)

    assert make_service(repository).list_tasks(1, query) == [owned]
    assert repository.listed_query == (1, query)

    missing_project_repository = StubTaskRepository([owned])
    with pytest.raises(ProjectNotFound):
        make_service(missing_project_repository, StubProjectRepository()).list_tasks(
            1, query
        )
    assert missing_project_repository.listed_query is None


def test_update_task_changes_only_supplied_fields() -> None:
    original = make_task(3)
    repository = StubTaskRepository([original])

    updated = make_service(repository).update_task(
        1,
        3,
        title="  Renamed  ",
        status=TaskStatus.DONE,
    )

    assert updated.title == "Renamed"
    assert updated.description == original.description
    assert updated.status is TaskStatus.DONE
    assert updated.priority is original.priority
    assert updated.due_at == original.due_at
    assert updated.created_at == original.created_at
    assert updated.updated_at == LATER
    assert repository.updated is updated


def test_update_task_explicit_null_clears_nullable_fields() -> None:
    repository = StubTaskRepository([make_task(3)])

    updated = make_service(repository).update_task(1, 3, description=None, due_at=None)

    assert updated.description is None
    assert updated.due_at is None


@pytest.mark.parametrize("field_name", ["title", "status", "priority"])
def test_update_task_rejects_null_required_fields(field_name: str) -> None:
    repository = StubTaskRepository([make_task(3)])

    with pytest.raises(TaskValidationError, match=f"Task {field_name} is required"):
        make_service(repository).update_task(1, 3, **{field_name: None})

    assert repository.updated is None


def test_update_task_rejects_empty_patch_without_lookup_or_timestamp_change() -> None:
    original = make_task(3)
    repository = StubTaskRepository([original])

    with pytest.raises(TaskValidationError, match="At least one Task field"):
        make_service(repository).update_task(1, 3)

    assert repository.tasks[(1, 3)] is original
    assert repository.updated is None


def test_update_task_raises_not_found_when_task_disappears() -> None:
    class DisappearingTaskRepository(StubTaskRepository):
        def update(self, task: Task) -> Task | None:
            self.updated = task
            return None

    repository = DisappearingTaskRepository([make_task(3)])

    with pytest.raises(TaskNotFound):
        make_service(repository).update_task(1, 3, title="Renamed")


def test_delete_task_delegates_to_owned_repository_operation() -> None:
    repository = StubTaskRepository([make_task(4)])

    assert make_service(repository).delete_task(1, 4) is None
    assert repository.deleted_key == (1, 4)


def test_delete_task_raises_not_found_for_missing_or_mismatched_task() -> None:
    repository = StubTaskRepository([make_task(4, project_id=2)])

    with pytest.raises(TaskNotFound):
        make_service(repository).delete_task(1, 4)


def test_repository_errors_propagate_unchanged() -> None:
    error = RepositoryError("sanitized failure")

    class FailingTaskRepository(StubTaskRepository):
        def create(self, task: Task) -> Task:
            raise error

    service = make_service(FailingTaskRepository())

    with pytest.raises(RepositoryError) as captured:
        service.create_task(1, "Task")

    assert captured.value is error
