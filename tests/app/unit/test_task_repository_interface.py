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

    assert query.status is None
    assert query.priority is None
    assert query.due_before is None
    assert query.due_after is None
    assert query.limit == 50
    assert query.offset == 0
    assert query.sort is TaskSort.CREATED_AT
    assert query.order is SortOrder.ASC


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


def test_importing_repository_package_does_not_load_concrete_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.repositories

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_project_repository",
    "project_board.repositories.sqlalchemy_task_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps([name for name in watched_modules if name in sys.modules]))
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
