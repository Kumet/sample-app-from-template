"""Framework-independent domain models and errors."""

from project_board.domain.errors import (
    DuplicateTagName,
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
    TagNotFound,
    TagValidationError,
    TaskNotFound,
    TaskValidationError,
)
from project_board.domain.project import Project
from project_board.domain.tag import Tag
from project_board.domain.task import Task, TaskPriority, TaskStatus

__all__ = [
    "DuplicateTagName",
    "Project",
    "ProjectHasTasksConflict",
    "ProjectNotFound",
    "ProjectValidationError",
    "RepositoryError",
    "Tag",
    "TagNotFound",
    "TagValidationError",
    "Task",
    "TaskNotFound",
    "TaskPriority",
    "TaskStatus",
    "TaskValidationError",
]
