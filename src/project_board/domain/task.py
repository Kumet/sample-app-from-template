"""Task domain model and its invariants."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from project_board.domain.datetime import normalize_utc_datetime
from project_board.domain.errors import TaskValidationError

MAX_TASK_TITLE_LENGTH = 200
MAX_TASK_DESCRIPTION_LENGTH = 2000


class TaskStatus(StrEnum):
    """Allowed Task workflow states."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(StrEnum):
    """Allowed Task priorities in semantic ascending order."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _normalize_title(title: str) -> str:
    normalized = title.strip()
    if not normalized:
        raise TaskValidationError("Task title is required")
    if len(normalized) > MAX_TASK_TITLE_LENGTH:
        raise TaskValidationError(
            f"Task title must be at most {MAX_TASK_TITLE_LENGTH} characters"
        )
    return normalized


def _normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    normalized = description.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_TASK_DESCRIPTION_LENGTH:
        raise TaskValidationError(
            "Task description must be at most "
            f"{MAX_TASK_DESCRIPTION_LENGTH} characters"
        )
    return normalized


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    try:
        return normalize_utc_datetime(value, f"Task {field_name}")
    except ValueError as error:
        raise TaskValidationError(str(error)) from error


def _normalize_optional_datetime(
    value: datetime | None, field_name: str
) -> datetime | None:
    if value is None:
        return None
    return _normalize_datetime(value, field_name)


def _normalize_status(value: TaskStatus | str) -> TaskStatus:
    try:
        return TaskStatus(value)
    except ValueError as error:
        raise TaskValidationError(f"Invalid Task status: {value}") from error


def _normalize_priority(value: TaskPriority | str) -> TaskPriority:
    try:
        return TaskPriority(value)
    except ValueError as error:
        raise TaskValidationError(f"Invalid Task priority: {value}") from error


@dataclass(frozen=True, slots=True)
class Task:
    """A validated Task independent of API and persistence frameworks."""

    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _normalize_title(self.title))
        object.__setattr__(
            self, "description", _normalize_description(self.description)
        )
        object.__setattr__(self, "status", _normalize_status(self.status))
        object.__setattr__(self, "priority", _normalize_priority(self.priority))
        object.__setattr__(
            self, "due_at", _normalize_optional_datetime(self.due_at, "due_at")
        )
        object.__setattr__(
            self, "created_at", _normalize_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _normalize_datetime(self.updated_at, "updated_at")
        )
