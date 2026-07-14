"""Task use cases orchestrated against persistence boundaries."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from project_board.application.project_service import UNSET, _UnsetType
from project_board.domain import (
    ProjectNotFound,
    TagNotFound,
    Task,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskValidationError,
)
from project_board.repositories.project_repository import ProjectRepository
from project_board.repositories.tag_repository import TagRepository
from project_board.repositories.task_repository import TaskListQuery, TaskRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TaskService:
    """Implement nested Task CRUD without delivery or persistence dependencies."""

    def __init__(
        self,
        task_repository: TaskRepository,
        project_repository: ProjectRepository,
        tag_repository: TagRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._tasks = task_repository
        self._projects = project_repository
        self._tags = tag_repository
        self._clock = clock

    def create_task(
        self,
        project_id: int,
        title: str,
        description: str | None = None,
        status: TaskStatus = TaskStatus.TODO,
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_at: datetime | None = None,
    ) -> Task:
        self._require_project(project_id)
        now = self._clock()
        task = Task(
            id=0,
            project_id=project_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_at=due_at,
            created_at=now,
            updated_at=now,
        )
        return self._tasks.create(task)

    def get_task(self, project_id: int, task_id: int) -> Task:
        self._require_project(project_id)
        task = self._tasks.get(project_id, task_id)
        if task is None:
            raise TaskNotFound(project_id, task_id)
        return task

    def list_tasks(self, project_id: int, query: TaskListQuery) -> list[Task]:
        self._require_project(project_id)
        if (
            query.tag_id is not None
            and self._tags.get(project_id, query.tag_id) is None
        ):
            raise TagNotFound(project_id, query.tag_id)
        return self._tasks.list(project_id, query)

    def update_task(
        self,
        project_id: int,
        task_id: int,
        *,
        title: str | None | _UnsetType = UNSET,
        description: str | None | _UnsetType = UNSET,
        status: TaskStatus | None | _UnsetType = UNSET,
        priority: TaskPriority | None | _UnsetType = UNSET,
        due_at: datetime | None | _UnsetType = UNSET,
    ) -> Task:
        fields = (title, description, status, priority, due_at)
        if all(isinstance(value, _UnsetType) for value in fields):
            raise TaskValidationError("At least one Task field is required")
        if title is None:
            raise TaskValidationError("Task title is required")
        if status is None:
            raise TaskValidationError("Task status is required")
        if priority is None:
            raise TaskValidationError("Task priority is required")

        current = self.get_task(project_id, task_id)
        updated = replace(
            current,
            title=current.title if isinstance(title, _UnsetType) else title,
            description=(
                current.description
                if isinstance(description, _UnsetType)
                else description
            ),
            status=current.status if isinstance(status, _UnsetType) else status,
            priority=(
                current.priority if isinstance(priority, _UnsetType) else priority
            ),
            due_at=current.due_at if isinstance(due_at, _UnsetType) else due_at,
            updated_at=self._clock(),
        )
        persisted = self._tasks.update(updated)
        if persisted is None:
            raise TaskNotFound(project_id, task_id)
        return persisted

    def delete_task(self, project_id: int, task_id: int) -> None:
        self._require_project(project_id)
        if not self._tasks.delete(project_id, task_id):
            raise TaskNotFound(project_id, task_id)

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFound(project_id)
