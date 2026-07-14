"""Project dashboard use case orchestrated against persistence boundaries."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from project_board.domain import (
    DashboardInvariantError,
    ProjectDashboard,
    ProjectNotFound,
)
from project_board.domain.datetime import normalize_utc_datetime
from project_board.repositories.dashboard_repository import (
    DashboardDueQuery,
    ProjectDashboardRepository,
)
from project_board.repositories.project_repository import ProjectRepository

DEFAULT_ACTIVITY_LIMIT = 10


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectDashboardService:
    """Assemble one immutable, ownership-scoped Project dashboard."""

    def __init__(
        self,
        dashboard_repository: ProjectDashboardRepository,
        project_repository: ProjectRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._projects = project_repository
        self._dashboard = dashboard_repository
        self._clock = clock

    def get_dashboard(
        self, project_id: int, activity_limit: int = DEFAULT_ACTIVITY_LIMIT
    ) -> ProjectDashboard:
        """Return current dashboard aggregates for an existing Project."""
        if self._projects.get(project_id) is None:
            raise ProjectNotFound(project_id)

        as_of = self._as_of()
        today_end = datetime.combine(
            as_of.date() + timedelta(days=1), time.min, tzinfo=UTC
        )
        due_query = DashboardDueQuery(
            as_of=as_of,
            today_end=today_end,
            upcoming_end=today_end + timedelta(days=7),
        )

        return ProjectDashboard(
            project_id=project_id,
            as_of=as_of,
            tasks=self._dashboard.get_task_counts(project_id),
            due=self._dashboard.get_due_counts(project_id, due_query),
            tags=self._dashboard.list_tag_counts(project_id),
            comments=self._dashboard.get_comment_counts(project_id),
            recent_activities=self._dashboard.list_recent_activities(
                project_id, activity_limit
            ),
        )

    def _as_of(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise DashboardInvariantError("Dashboard as_of must be a datetime")
        try:
            return normalize_utc_datetime(value, "Dashboard as_of")
        except ValueError as error:
            raise DashboardInvariantError(str(error)) from error
