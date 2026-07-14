import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_board.domain import TaskPriority, TaskStatus, TaskValidationError
from project_board.repositories import SortOrder, TaskListQuery, TaskSort


def test_task_list_query_has_contract_defaults() -> None:
    query = TaskListQuery()

    assert query.q is None
    assert query.statuses == ()
    assert query.priorities == ()
    assert query.status is None
    assert query.priority is None
    assert query.due_before is None
    assert query.due_after is None
    assert query.tag_id is None
    assert query.limit == 50
    assert query.offset == 0
    assert query.sort is TaskSort.CREATED_AT
    assert query.order is SortOrder.ASC


@pytest.mark.parametrize("q", ["x", "x" * 100])
def test_task_list_query_trims_valid_search_boundaries(q: str) -> None:
    assert TaskListQuery(q=f"  {q}  ").q == q


@pytest.mark.parametrize("q", ["", "   ", "x" * 101])
def test_task_list_query_rejects_invalid_search_length(q: str) -> None:
    with pytest.raises(
        TaskValidationError, match="q must be between 1 and 100 characters"
    ):
        TaskListQuery(q=q)


def test_task_list_query_normalizes_and_deduplicates_repeated_filters() -> None:
    query = TaskListQuery(
        statuses=(TaskStatus.TODO, TaskStatus.DONE, TaskStatus.TODO),
        priorities=(TaskPriority.HIGH, TaskPriority.LOW, TaskPriority.HIGH),
    )

    assert query.statuses == (TaskStatus.TODO, TaskStatus.DONE)
    assert query.priorities == (TaskPriority.HIGH, TaskPriority.LOW)


def test_task_list_query_accepts_typed_string_filter_values() -> None:
    query = TaskListQuery(
        statuses=("todo", "in_progress"),  # type: ignore[arg-type]
        priorities=("medium",),  # type: ignore[arg-type]
    )

    assert query.statuses == (TaskStatus.TODO, TaskStatus.IN_PROGRESS)
    assert query.priorities == (TaskPriority.MEDIUM,)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("statuses", ("blocked",), "Invalid Task status"),
        ("priorities", ("urgent",), "Invalid Task priority"),
    ],
)
def test_task_list_query_rejects_invalid_repeated_filters(
    field_name: str, value: tuple[str, ...], message: str
) -> None:
    with pytest.raises(TaskValidationError, match=message):
        TaskListQuery(**{field_name: value})


def test_task_list_query_keeps_enum_filters() -> None:
    query = TaskListQuery(
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        sort=TaskSort.PRIORITY,
        order=SortOrder.DESC,
    )

    assert query.status is TaskStatus.IN_PROGRESS
    assert query.priority is TaskPriority.HIGH
    assert query.sort is TaskSort.PRIORITY
    assert query.order is SortOrder.DESC


@pytest.mark.parametrize("field_name", ["due_before", "due_after"])
def test_task_list_query_normalizes_aware_due_filters(field_name: str) -> None:
    offset = timezone(timedelta(hours=9))

    query = TaskListQuery(**{field_name: datetime(2026, 1, 1, 9, tzinfo=offset)})

    assert getattr(query, field_name) == datetime(2026, 1, 1, tzinfo=UTC)
    assert getattr(query, field_name).tzinfo is UTC


@pytest.mark.parametrize("field_name", ["due_before", "due_after"])
def test_task_list_query_rejects_naive_due_filters(field_name: str) -> None:
    with pytest.raises(TaskValidationError, match=f"{field_name} must be"):
        TaskListQuery(**{field_name: datetime(2026, 1, 1)})


@pytest.mark.parametrize(
    ("due_after", "due_before"),
    [
        (
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
    ],
)
def test_task_list_query_rejects_non_increasing_due_range(
    due_after: datetime, due_before: datetime
) -> None:
    with pytest.raises(
        TaskValidationError, match="due_after must be before due_before"
    ):
        TaskListQuery(due_after=due_after, due_before=due_before)


@pytest.mark.parametrize("limit", [0, 101])
def test_task_list_query_rejects_out_of_bounds_limit(limit: int) -> None:
    with pytest.raises(TaskValidationError, match="limit must be between 1 and 100"):
        TaskListQuery(limit=limit)


def test_task_list_query_rejects_negative_offset() -> None:
    with pytest.raises(TaskValidationError, match="offset must be at least 0"):
        TaskListQuery(offset=-1)


@pytest.mark.parametrize("tag_id", [0, -1])
def test_task_list_query_rejects_non_positive_tag_id(tag_id: int) -> None:
    with pytest.raises(TaskValidationError, match="tag_id must be a positive integer"):
        TaskListQuery(tag_id=tag_id)


def test_task_list_query_accepts_positive_tag_id() -> None:
    assert TaskListQuery(tag_id=7).tag_id == 7


@pytest.mark.parametrize(
    "module_name",
    [
        "project_board.domain",
        "project_board.repositories",
        "project_board.repositories.task_repository",
        "project_board.application",
        "project_board.application.task_service",
    ],
)
def test_boundary_imports_do_not_load_concrete_infrastructure(
    module_name: str,
) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = f"""
import importlib
import json
import sys

importlib.import_module({module_name!r})

forbidden_prefixes = (
    "sqlalchemy",
    "project_board.infrastructure",
    "project_board.repositories.sqlalchemy_",
)
print(json.dumps(sorted(
    name
    for name in sys.modules
    if any(name.startswith(prefix) for prefix in forbidden_prefixes)
)))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == []
