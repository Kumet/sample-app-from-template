from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import DashboardInvariantError
from project_board.repositories import DashboardDueQuery


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
