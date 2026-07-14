"""Framework-independent domain models and errors."""

from project_board.domain.errors import (
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
    TaskNotFound,
    TaskValidationError,
)
from project_board.domain.project import Project
from project_board.domain.task import Task, TaskPriority, TaskStatus

__all__ = [
    "Project",
    "ProjectHasTasksConflict",
    "ProjectNotFound",
    "ProjectValidationError",
    "RepositoryError",
    "Task",
    "TaskNotFound",
    "TaskPriority",
    "TaskStatus",
    "TaskValidationError",
]
