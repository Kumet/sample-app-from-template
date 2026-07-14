"""Framework-independent domain models and errors."""

from project_board.domain.comment import (
    MAX_COMMENT_BODY_LENGTH,
    CommentEventType,
    TaskComment,
    TaskCommentActivity,
    normalize_comment_body,
)
from project_board.domain.dashboard import (
    DashboardCommentCounts,
    DashboardDueCounts,
    DashboardInvariantError,
    DashboardTagCount,
    DashboardTaskCounts,
    ProjectDashboard,
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
from project_board.domain.task import (
    TERMINAL_TASK_STATUSES,
    Task,
    TaskPriority,
    TaskStatus,
    is_terminal_task_status,
)

__all__ = [
    "CommentEventType",
    "DashboardCommentCounts",
    "DashboardDueCounts",
    "DashboardInvariantError",
    "DashboardTagCount",
    "DashboardTaskCounts",
    "DuplicateTagName",
    "MAX_COMMENT_BODY_LENGTH",
    "Project",
    "ProjectDashboard",
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
    "TERMINAL_TASK_STATUSES",
    "is_terminal_task_status",
    "normalize_comment_body",
]
