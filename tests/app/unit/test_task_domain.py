from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import (
    ProjectHasTasksConflict,
    Task,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskValidationError,
)


def make_task(**changes: object) -> Task:
    values = {
        "id": 1,
        "project_id": 2,
        "title": "Sample task",
        "description": "Description",
        "status": TaskStatus.TODO,
        "priority": TaskPriority.MEDIUM,
        "due_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return Task(**values)  # type: ignore[arg-type]


def test_task_normalizes_title_and_description() -> None:
    task = make_task(title="  Sample task  ", description="  Details  ")

    assert task.title == "Sample task"
    assert task.description == "Details"


@pytest.mark.parametrize("title", ["", " ", "\t\n"])
def test_task_rejects_empty_title(title: str) -> None:
    with pytest.raises(TaskValidationError, match="title is required"):
        make_task(title=title)


def test_task_accepts_200_character_trimmed_title() -> None:
    assert make_task(title=f" {'a' * 200} ").title == "a" * 200


def test_task_rejects_title_over_200_characters_after_trimming() -> None:
    with pytest.raises(TaskValidationError, match="at most 200"):
        make_task(title=f" {'a' * 201} ")


@pytest.mark.parametrize("description", [None, "", "  "])
def test_task_normalizes_missing_or_empty_description_to_none(
    description: str | None,
) -> None:
    assert make_task(description=description).description is None


def test_task_accepts_2000_character_trimmed_description() -> None:
    task = make_task(description=f" {'a' * 2000} ")

    assert task.description == "a" * 2000


def test_task_rejects_description_over_2000_characters_after_trimming() -> None:
    with pytest.raises(TaskValidationError, match="at most 2000"):
        make_task(description=f" {'a' * 2001} ")


@pytest.mark.parametrize(
    ("status", "expected"),
    [(value.value, value) for value in TaskStatus],
)
def test_task_accepts_every_status(status: str, expected: TaskStatus) -> None:
    assert make_task(status=status).status is expected


@pytest.mark.parametrize(
    ("priority", "expected"),
    [(value.value, value) for value in TaskPriority],
)
def test_task_accepts_every_priority(priority: str, expected: TaskPriority) -> None:
    assert make_task(priority=priority).priority is expected


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("status", "doing"), ("priority", "urgent")],
)
def test_task_rejects_unknown_enum_values(field_name: str, value: str) -> None:
    with pytest.raises(TaskValidationError, match=f"Invalid Task {field_name}"):
        make_task(**{field_name: value})


def test_task_converts_all_aware_datetimes_to_utc() -> None:
    offset = timezone(timedelta(hours=9))
    task = make_task(
        due_at=datetime(2026, 1, 3, 9, tzinfo=offset),
        created_at=datetime(2026, 1, 1, 9, tzinfo=offset),
        updated_at=datetime(2026, 1, 2, 9, tzinfo=offset),
    )

    assert task.due_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert task.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert task.updated_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert task.due_at is not None and task.due_at.tzinfo is UTC


@pytest.mark.parametrize("field_name", ["due_at", "created_at", "updated_at"])
def test_task_rejects_naive_datetimes(field_name: str) -> None:
    with pytest.raises(TaskValidationError, match=f"{field_name} must be"):
        make_task(**{field_name: datetime(2026, 1, 1)})


def test_task_is_frozen_and_replacement_reapplies_validation() -> None:
    task = make_task()

    with pytest.raises(FrozenInstanceError):
        task.project_id = 3  # type: ignore[misc]

    updated = replace(task, title="  Updated  ", description=" ")
    assert updated.title == "Updated"
    assert updated.description is None


def test_task_not_found_exposes_requested_ownership() -> None:
    error = TaskNotFound(project_id=4, task_id=9)

    assert error.project_id == 4
    assert error.task_id == 9
    assert str(error) == "Task 9 was not found in Project 4"


def test_project_has_tasks_conflict_exposes_project_id() -> None:
    error = ProjectHasTasksConflict(4)

    assert error.project_id == 4
    assert str(error) == "Project 4 still has Tasks"
