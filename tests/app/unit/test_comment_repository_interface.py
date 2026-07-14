import json
import subprocess
import sys
from pathlib import Path

import pytest

from project_board.domain import CommentEventType, TaskCommentValidationError
from project_board.repositories import (
    ActivityListQuery,
    CommentListQuery,
    SortOrder,
    TaskCommentRepository,
)


def test_comment_list_query_has_bounded_defaults() -> None:
    query = CommentListQuery()

    assert (query.limit, query.offset, query.order) == (50, 0, SortOrder.ASC)


def test_activity_list_query_has_bounded_defaults() -> None:
    query = ActivityListQuery()

    assert (query.limit, query.offset, query.order, query.event_type) == (
        50,
        0,
        SortOrder.ASC,
        None,
    )


@pytest.mark.parametrize("query_type", [CommentListQuery, ActivityListQuery])
@pytest.mark.parametrize("limit", [0, 101, True])
def test_list_queries_reject_invalid_limit(query_type: type, limit: object) -> None:
    with pytest.raises(TaskCommentValidationError, match="limit"):
        query_type(limit=limit)


@pytest.mark.parametrize("query_type", [CommentListQuery, ActivityListQuery])
@pytest.mark.parametrize("offset", [-1, True])
def test_list_queries_reject_invalid_offset(query_type: type, offset: object) -> None:
    with pytest.raises(TaskCommentValidationError, match="offset"):
        query_type(offset=offset)


@pytest.mark.parametrize("query_type", [CommentListQuery, ActivityListQuery])
def test_list_queries_normalize_string_order(query_type: type) -> None:
    assert query_type(order="desc").order is SortOrder.DESC


def test_activity_query_normalizes_fixed_event_filter() -> None:
    query = ActivityListQuery(event_type="comment_deleted")  # type: ignore[arg-type]

    assert query.event_type is CommentEventType.DELETED


def test_activity_query_rejects_unknown_event_filter() -> None:
    with pytest.raises(TaskCommentValidationError, match="event type"):
        ActivityListQuery(event_type="comment_restored")  # type: ignore[arg-type]


def test_repository_protocol_exposes_no_activity_mutation() -> None:
    assert TaskCommentRepository.__name__ == "TaskCommentRepository"
    assert not hasattr(TaskCommentRepository, "update_activity")
    assert not hasattr(TaskCommentRepository, "delete_activity")


@pytest.mark.parametrize(
    "module_name",
    [
        "project_board.domain",
        "project_board.domain.comment",
        "project_board.repositories",
        "project_board.repositories.comment_repository",
    ],
)
def test_comment_boundary_imports_do_not_load_infrastructure(
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
