"""Persistence boundary used by Task Comment application services."""

import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from project_board.domain import (
    CommentEventType,
    TaskComment,
    TaskCommentActivity,
    TaskCommentValidationError,
)
from project_board.repositories.task_repository import SortOrder


def _validate_pagination(limit: int, offset: int, subject: str) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise TaskCommentValidationError(
            f"{subject} list limit must be between 1 and 100"
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise TaskCommentValidationError(f"{subject} list offset must be at least 0")


def _normalize_order(value: SortOrder | str, subject: str) -> SortOrder:
    try:
        return SortOrder(value)
    except (TypeError, ValueError) as error:
        raise TaskCommentValidationError(
            f"Invalid {subject} list order: {value}"
        ) from error


@dataclass(frozen=True, slots=True)
class CommentListQuery:
    """Infrastructure-neutral inputs for a bounded Comment list query."""

    limit: int = 50
    offset: int = 0
    order: SortOrder = SortOrder.ASC

    def __post_init__(self) -> None:
        _validate_pagination(self.limit, self.offset, "Comment")
        object.__setattr__(self, "order", _normalize_order(self.order, "Comment"))


@dataclass(frozen=True, slots=True)
class ActivityListQuery:
    """Infrastructure-neutral inputs for a bounded Activity list query."""

    limit: int = 50
    offset: int = 0
    order: SortOrder = SortOrder.ASC
    event_type: CommentEventType | None = None

    def __post_init__(self) -> None:
        _validate_pagination(self.limit, self.offset, "Activity")
        object.__setattr__(self, "order", _normalize_order(self.order, "Activity"))
        if self.event_type is not None:
            try:
                normalized_event_type = CommentEventType(self.event_type)
            except (TypeError, ValueError) as error:
                raise TaskCommentValidationError(
                    f"Invalid Task Comment event type: {self.event_type}"
                ) from error
            object.__setattr__(self, "event_type", normalized_event_type)


class TaskCommentRepository(Protocol):
    """Atomic Comment mutations and read-only Activity access."""

    def create(self, comment: TaskComment, occurred_at: datetime) -> TaskComment:
        """Persist a Comment and its created event in one transaction."""
        ...

    def list(
        self, project_id: int, task_id: int, query: CommentListQuery
    ) -> list[TaskComment]:
        """Return matching Comments owned by a Project and Task."""
        ...

    def get(self, project_id: int, task_id: int, comment_id: int) -> TaskComment | None:
        """Return an owned Comment, or ``None`` when absent or mismatched."""
        ...

    def update(self, comment: TaskComment, occurred_at: datetime) -> TaskComment | None:
        """Persist a Comment update and its event in one transaction."""
        ...

    def delete(
        self, project_id: int, task_id: int, comment_id: int, occurred_at: datetime
    ) -> bool:
        """Persist a deleted event and physically remove its Comment atomically."""
        ...

    def list_activities(
        self, project_id: int, task_id: int, query: ActivityListQuery
    ) -> builtins.list[TaskCommentActivity]:
        """Return immutable lifecycle events owned by a Project and Task."""
        ...
