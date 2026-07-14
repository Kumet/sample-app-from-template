from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import (
    CommentEventType,
    TaskComment,
    TaskCommentActivity,
    TaskCommentNotFound,
    TaskCommentValidationError,
)


def make_comment(**changes: object) -> TaskComment:
    values = {
        "id": 1,
        "project_id": 2,
        "task_id": 3,
        "body": "A comment",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return TaskComment(**values)  # type: ignore[arg-type]


def make_activity(**changes: object) -> TaskCommentActivity:
    values = {
        "id": 4,
        "project_id": 2,
        "task_id": 3,
        "comment_id": 1,
        "event_type": CommentEventType.CREATED,
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return TaskCommentActivity(**values)  # type: ignore[arg-type]


def test_comment_trims_body_and_preserves_unicode_and_newlines() -> None:
    comment = make_comment(body="  日本語\nsecond line  ")

    assert comment.body == "日本語\nsecond line"


@pytest.mark.parametrize("body", [None, "", " ", "\t\n"])
def test_comment_rejects_missing_or_empty_body(body: str | None) -> None:
    with pytest.raises(TaskCommentValidationError, match="body"):
        make_comment(body=body)


def test_comment_accepts_2000_characters_after_trimming() -> None:
    assert make_comment(body=f" {'a' * 2000} ").body == "a" * 2000


def test_comment_rejects_2001_characters_after_trimming() -> None:
    with pytest.raises(TaskCommentValidationError, match="at most 2000"):
        make_comment(body=f" {'a' * 2001} ")


@pytest.mark.parametrize("field_name", ["id", "project_id", "task_id"])
@pytest.mark.parametrize("value", [0, -1, True, None])
def test_comment_rejects_non_positive_integer_ids(
    field_name: str, value: object
) -> None:
    with pytest.raises(TaskCommentValidationError, match="positive integer"):
        make_comment(**{field_name: value})


def test_comment_normalizes_aware_times_to_utc() -> None:
    offset = timezone(timedelta(hours=9))
    comment = make_comment(
        created_at=datetime(2026, 1, 1, 9, tzinfo=offset),
        updated_at=datetime(2026, 1, 2, 9, tzinfo=offset),
    )

    assert comment.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert comment.updated_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert comment.created_at.tzinfo is UTC
    assert comment.updated_at.tzinfo is UTC


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_comment_rejects_naive_times(field_name: str) -> None:
    with pytest.raises(TaskCommentValidationError, match=f"{field_name} must be"):
        make_comment(**{field_name: datetime(2026, 1, 1)})


def test_comment_rejects_updated_time_before_created_time() -> None:
    with pytest.raises(TaskCommentValidationError, match="must not be before"):
        make_comment(updated_at=datetime(2025, 12, 31, tzinfo=UTC))


def test_comment_is_frozen_and_replace_revalidates_body() -> None:
    comment = make_comment()

    with pytest.raises(FrozenInstanceError):
        comment.project_id = 9  # type: ignore[misc]

    assert replace(comment, body="  changed  ").body == "changed"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(event.value, event) for event in CommentEventType],
)
def test_activity_accepts_only_fixed_event_types(
    value: str, expected: CommentEventType
) -> None:
    assert make_activity(event_type=value).event_type is expected


def test_activity_rejects_unknown_event_type() -> None:
    with pytest.raises(TaskCommentValidationError, match="event type"):
        make_activity(event_type="comment_restored")


@pytest.mark.parametrize("field_name", ["id", "project_id", "task_id", "comment_id"])
def test_activity_rejects_non_positive_ids(field_name: str) -> None:
    with pytest.raises(TaskCommentValidationError, match="positive integer"):
        make_activity(**{field_name: 0})


def test_activity_normalizes_aware_time_and_rejects_naive_time() -> None:
    offset = timezone(timedelta(hours=9))
    activity = make_activity(occurred_at=datetime(2026, 1, 1, 9, tzinfo=offset))

    assert activity.occurred_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert activity.occurred_at.tzinfo is UTC
    with pytest.raises(TaskCommentValidationError, match="occurred_at must be"):
        make_activity(occurred_at=datetime(2026, 1, 1))


def test_activity_is_frozen_and_contains_no_comment_body() -> None:
    activity = make_activity()

    assert not hasattr(activity, "body")
    with pytest.raises(FrozenInstanceError):
        activity.comment_id = 9  # type: ignore[misc]


def test_comment_not_found_exposes_requested_ownership() -> None:
    error = TaskCommentNotFound(project_id=2, task_id=3, comment_id=4)

    assert (error.project_id, error.task_id, error.comment_id) == (2, 3, 4)
    assert isinstance(error, LookupError)
