from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from project_board.domain import DashboardInvariantError
from project_board.repositories import DashboardDueQuery
from project_board.repositories.sqlalchemy_dashboard_repository import (
    SQLAlchemyProjectDashboardRepository,
)


class QueryForbiddenSession:
    def execute(self, _statement: object) -> Any:
        raise AssertionError("zero activity limit must not execute SQL")


def test_due_query_accepts_one_normalized_utc_boundary_policy() -> None:
    query = DashboardDueQuery(
        as_of=datetime(2026, 7, 15, 12, tzinfo=UTC),
        today_end=datetime(2026, 7, 16, tzinfo=UTC),
        upcoming_end=datetime(2026, 7, 23, tzinfo=UTC),
    )

    assert query.as_of == datetime(2026, 7, 15, 12, tzinfo=UTC)
    assert query.today_end == datetime(2026, 7, 16, tzinfo=UTC)
    assert query.upcoming_end == datetime(2026, 7, 23, tzinfo=UTC)
    assert query.as_of.tzinfo is UTC


@pytest.mark.parametrize("field_name", ["as_of", "today_end", "upcoming_end"])
@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 7, 15),
        datetime(2026, 7, 15, tzinfo=timezone(timedelta(hours=9))),
        "not-a-datetime",
    ],
)
def test_due_query_rejects_invalid_boundaries(field_name: str, value: object) -> None:
    values: dict[str, object] = {
        "as_of": datetime(2026, 7, 15, 12, tzinfo=UTC),
        "today_end": datetime(2026, 7, 16, tzinfo=UTC),
        "upcoming_end": datetime(2026, 7, 23, tzinfo=UTC),
    }
    values[field_name] = value

    with pytest.raises(DashboardInvariantError, match=field_name):
        DashboardDueQuery(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("today_end", "upcoming_end", "message"),
    [
        (
            datetime(2026, 7, 16, 1, tzinfo=UTC),
            datetime(2026, 7, 23, 1, tzinfo=UTC),
            "next UTC midnight",
        ),
        (
            datetime(2026, 7, 16, tzinfo=UTC),
            datetime(2026, 7, 22, tzinfo=UTC),
            "seven days",
        ),
    ],
)
def test_due_query_rejects_policy_drift(
    today_end: datetime, upcoming_end: datetime, message: str
) -> None:
    with pytest.raises(DashboardInvariantError, match=message):
        DashboardDueQuery(
            as_of=datetime(2026, 7, 15, 12, tzinfo=UTC),
            today_end=today_end,
            upcoming_end=upcoming_end,
        )


def test_zero_activity_limit_returns_without_querying_the_session() -> None:
    repository = SQLAlchemyProjectDashboardRepository(
        cast(Session, QueryForbiddenSession())
    )

    assert repository.list_recent_activities(project_id=1, limit=0) == ()


@pytest.mark.parametrize("limit", [-1, 51, True, 1.5, "10"])
def test_activity_query_rejects_unbounded_or_non_integer_limits(
    limit: object,
) -> None:
    repository = SQLAlchemyProjectDashboardRepository(
        cast(Session, QueryForbiddenSession())
    )

    with pytest.raises(DashboardInvariantError, match="activity limit"):
        repository.list_recent_activities(1, limit)  # type: ignore[arg-type]
