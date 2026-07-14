"""Task Comment use cases orchestrated against persistence boundaries."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from project_board.domain import (
    ProjectNotFound,
    TaskComment,
    TaskCommentActivity,
    TaskCommentNotFound,
    TaskCommentValidationError,
    TaskNotFound,
)
from project_board.domain.datetime import normalize_utc_datetime
from project_board.repositories.comment_repository import (
    ActivityListQuery,
    CommentListQuery,
    TaskCommentRepository,
)
from project_board.repositories.project_repository import ProjectRepository
from project_board.repositories.task_repository import TaskRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TaskCommentService:
    """Implement owned Comment CRUD and read-only Activity queries."""

    def __init__(
        self,
        comment_repository: TaskCommentRepository,
        project_repository: ProjectRepository,
        task_repository: TaskRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._comments = comment_repository
        self._projects = project_repository
        self._tasks = task_repository
        self._clock = clock

    def create_comment(self, project_id: int, task_id: int, body: str) -> TaskComment:
        self._require_task(project_id, task_id)
        now = self._timestamp()
        comment = TaskComment(
            # Persistence replaces this valid transient identifier with the
            # database-generated identifier before returning the Comment.
            id=1,
            project_id=project_id,
            task_id=task_id,
            body=body,
            created_at=now,
            updated_at=now,
        )
        return self._comments.create(comment, now)

    def list_comments(
        self, project_id: int, task_id: int, query: CommentListQuery
    ) -> list[TaskComment]:
        self._require_task(project_id, task_id)
        return self._comments.list(project_id, task_id, query)

    def get_comment(
        self, project_id: int, task_id: int, comment_id: int
    ) -> TaskComment:
        self._require_task(project_id, task_id)
        comment = self._comments.get(project_id, task_id, comment_id)
        if comment is None:
            raise TaskCommentNotFound(project_id, task_id, comment_id)
        return comment

    def update_comment(
        self, project_id: int, task_id: int, comment_id: int, *, body: str
    ) -> TaskComment:
        current = self.get_comment(project_id, task_id, comment_id)
        updated_at = self._timestamp()
        if updated_at <= current.updated_at:
            updated_at = current.updated_at + timedelta(microseconds=1)
        updated = replace(current, body=body, updated_at=updated_at)
        persisted = self._comments.update(updated, updated_at)
        if persisted is None:
            raise TaskCommentNotFound(project_id, task_id, comment_id)
        return persisted

    def delete_comment(self, project_id: int, task_id: int, comment_id: int) -> None:
        self._require_task(project_id, task_id)
        if not self._comments.delete(
            project_id, task_id, comment_id, self._timestamp()
        ):
            raise TaskCommentNotFound(project_id, task_id, comment_id)

    def list_activities(
        self, project_id: int, task_id: int, query: ActivityListQuery
    ) -> list[TaskCommentActivity]:
        self._require_task(project_id, task_id)
        return self._comments.list_activities(project_id, task_id, query)

    def _require_task(self, project_id: int, task_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFound(project_id)
        if self._tasks.get(project_id, task_id) is None:
            raise TaskNotFound(project_id, task_id)

    def _timestamp(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TaskCommentValidationError(
                "Task Comment timestamp must be a timezone-aware datetime"
            )
        try:
            return normalize_utc_datetime(value, "Task Comment timestamp")
        except ValueError as error:
            raise TaskCommentValidationError(str(error)) from error
