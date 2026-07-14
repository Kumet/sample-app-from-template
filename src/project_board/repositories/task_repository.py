"""Persistence boundary used by Task application services."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from project_board.domain import Task, TaskPriority, TaskStatus
from project_board.domain.datetime import normalize_utc_datetime
from project_board.domain.errors import TaskValidationError


class TaskSort(StrEnum):
    """Allow-listed Task list sort fields."""

    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DUE_AT = "due_at"
    PRIORITY = "priority"


class SortOrder(StrEnum):
    """Allow-listed sort directions."""

    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class TaskListQuery:
    """Infrastructure-neutral inputs for a bounded Task list query."""

    q: str | None = None
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
    tag_id: int | None = None
    limit: int = 50
    offset: int = 0
    sort: TaskSort = TaskSort.CREATED_AT
    order: SortOrder = SortOrder.ASC

    def __post_init__(self) -> None:
        if self.q is not None:
            normalized_q = self.q.strip()
            if not 1 <= len(normalized_q) <= 100:
                raise TaskValidationError(
                    "Task list q must be between 1 and 100 characters"
                )
            object.__setattr__(self, "q", normalized_q)

        try:
            statuses = tuple(
                dict.fromkeys(TaskStatus(value) for value in self.statuses)
            )
        except ValueError as error:
            raise TaskValidationError(
                f"Invalid Task status: {error.args[0]}"
            ) from error
        object.__setattr__(self, "statuses", statuses)

        try:
            priorities = tuple(
                dict.fromkeys(TaskPriority(value) for value in self.priorities)
            )
        except ValueError as error:
            raise TaskValidationError(
                f"Invalid Task priority: {error.args[0]}"
            ) from error
        object.__setattr__(self, "priorities", priorities)

        if not 1 <= self.limit <= 100:
            raise TaskValidationError("Task list limit must be between 1 and 100")
        if self.offset < 0:
            raise TaskValidationError("Task list offset must be at least 0")
        if self.tag_id is not None and self.tag_id <= 0:
            raise TaskValidationError("Task list tag_id must be a positive integer")

        for field_name in ("due_before", "due_after"):
            value = getattr(self, field_name)
            if value is None:
                continue
            try:
                normalized = normalize_utc_datetime(value, field_name)
            except ValueError as error:
                raise TaskValidationError(str(error)) from error
            object.__setattr__(self, field_name, normalized)

        if (
            self.due_after is not None
            and self.due_before is not None
            and self.due_after >= self.due_before
        ):
            raise TaskValidationError("Task list due_after must be before due_before")


class TaskRepository(Protocol):
    """Ownership-aware Task operations available to the application layer."""

    def create(self, task: Task) -> Task:
        """Persist a Task and return it with its database-generated ID."""
        ...

    def list(self, project_id: int, query: TaskListQuery) -> list[Task]:
        """Return matching Tasks owned by a Project."""
        ...

    def get(self, project_id: int, task_id: int) -> Task | None:
        """Return an owned Task, or ``None`` when absent or mismatched."""
        ...

    def update(self, task: Task) -> Task | None:
        """Replace an owned persisted Task, or return ``None`` when absent."""
        ...

    def delete(self, project_id: int, task_id: int) -> bool:
        """Physically delete an owned Task and report whether it existed."""
        ...
