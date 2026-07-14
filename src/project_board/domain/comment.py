"""Task Comment and Comment Activity domain models and invariants."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from project_board.domain.datetime import normalize_utc_datetime
from project_board.domain.errors import TaskCommentValidationError

MAX_COMMENT_BODY_LENGTH = 2000


class CommentEventType(StrEnum):
    """The fixed lifecycle events recorded for Task Comments."""

    CREATED = "comment_created"
    UPDATED = "comment_updated"
    DELETED = "comment_deleted"


def _normalize_positive_id(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TaskCommentValidationError(
            f"Task Comment {field_name} must be a positive integer"
        )
    return value


def normalize_comment_body(body: str) -> str:
    """Return a trimmed Comment body satisfying the public size contract."""
    if not isinstance(body, str):
        raise TaskCommentValidationError("Task Comment body must be a string")
    normalized = body.strip()
    if not normalized:
        raise TaskCommentValidationError("Task Comment body is required")
    if len(normalized) > MAX_COMMENT_BODY_LENGTH:
        raise TaskCommentValidationError(
            f"Task Comment body must be at most {MAX_COMMENT_BODY_LENGTH} characters"
        )
    return normalized


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TaskCommentValidationError(
            f"Task Comment {field_name} must be a datetime"
        )
    try:
        return normalize_utc_datetime(value, f"Task Comment {field_name}")
    except ValueError as error:
        raise TaskCommentValidationError(str(error)) from error


def _normalize_event_type(value: CommentEventType | str) -> CommentEventType:
    try:
        return CommentEventType(value)
    except (TypeError, ValueError) as error:
        raise TaskCommentValidationError(
            f"Invalid Task Comment event type: {value}"
        ) from error


@dataclass(frozen=True, slots=True)
class TaskComment:
    """A validated Project- and Task-owned Comment."""

    id: int
    project_id: int
    task_id: int
    body: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("id", "project_id", "task_id"):
            object.__setattr__(
                self,
                field_name,
                _normalize_positive_id(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "body", normalize_comment_body(self.body))
        object.__setattr__(
            self, "created_at", _normalize_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _normalize_datetime(self.updated_at, "updated_at")
        )
        if self.updated_at < self.created_at:
            raise TaskCommentValidationError(
                "Task Comment updated_at must not be before created_at"
            )


@dataclass(frozen=True, slots=True)
class TaskCommentActivity:
    """An immutable, payload-free Task Comment lifecycle event."""

    id: int
    project_id: int
    task_id: int
    comment_id: int
    event_type: CommentEventType
    occurred_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("id", "project_id", "task_id", "comment_id"):
            object.__setattr__(
                self,
                field_name,
                _normalize_positive_id(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "event_type", _normalize_event_type(self.event_type))
        object.__setattr__(
            self,
            "occurred_at",
            _normalize_datetime(self.occurred_at, "occurred_at"),
        )
