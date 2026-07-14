"""Framework-independent domain models and errors."""

from project_board.domain.comment import (
    MAX_COMMENT_BODY_LENGTH,
    CommentEventType,
    TaskComment,
    TaskCommentActivity,
    normalize_comment_body,
)
from project_board.domain.errors import (
    DuplicateTagName,
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
    TagNotFound,
    TagValidationError,
    TaskCommentNotFound,
    TaskCommentValidationError,
    TaskNotFound,
    TaskValidationError,
)
from project_board.domain.project import Project
from project_board.domain.tag import Tag
from project_board.domain.task import Task, TaskPriority, TaskStatus

__all__ = [
    "CommentEventType",
    "DuplicateTagName",
    "MAX_COMMENT_BODY_LENGTH",
    "Project",
    "ProjectHasTasksConflict",
    "ProjectNotFound",
    "ProjectValidationError",
    "RepositoryError",
    "Tag",
    "TagNotFound",
    "TagValidationError",
    "Task",
    "TaskComment",
    "TaskCommentActivity",
    "TaskCommentNotFound",
    "TaskCommentValidationError",
    "TaskNotFound",
    "TaskPriority",
    "TaskStatus",
    "TaskValidationError",
    "normalize_comment_body",
]
