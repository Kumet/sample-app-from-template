"""Read-only SQLAlchemy aggregates for the Project dashboard."""

from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import (
    TERMINAL_TASK_STATUSES,
    CommentEventType,
    DashboardCommentCounts,
    DashboardDueCounts,
    DashboardInvariantError,
    DashboardTagCount,
    DashboardTaskCounts,
    RepositoryError,
    TaskCommentActivity,
    TaskPriority,
    TaskStatus,
)
from project_board.infrastructure.models import (
    TagModel,
    TaskCommentActivityModel,
    TaskCommentModel,
    TaskModel,
    TaskTagModel,
)
from project_board.repositories.dashboard_repository import DashboardDueQuery

MAX_RECENT_ACTIVITY_LIMIT = 50


def _as_utc(value: datetime) -> datetime:
    """Restore UTC awareness lost by SQLite's datetime representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_activity_limit(limit: int) -> None:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not (0 <= limit <= MAX_RECENT_ACTIVITY_LIMIT)
    ):
        raise DashboardInvariantError(
            f"Dashboard activity limit must be an integer from 0 to "
            f"{MAX_RECENT_ACTIVITY_LIMIT}"
        )


class SQLAlchemyProjectDashboardRepository:
    """Read ownership-scoped dashboard aggregates in one caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_task_counts(self, project_id: int) -> DashboardTaskCounts:
        """Return grouped Task status and priority counts without loading Tasks."""
        status_statement = (
            select(TaskModel.status, func.count(TaskModel.id))
            .where(TaskModel.project_id == project_id)
            .group_by(TaskModel.status)
        )
        priority_statement = (
            select(TaskModel.priority, func.count(TaskModel.id))
            .where(TaskModel.project_id == project_id)
            .group_by(TaskModel.priority)
        )

        try:
            status_rows = self._session.execute(status_statement).all()
            priority_rows = self._session.execute(priority_statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

        status_counts = {TaskStatus(value): count for value, count in status_rows}
        priority_counts = {TaskPriority(value): count for value, count in priority_rows}
        by_status = {status: status_counts.get(status, 0) for status in TaskStatus}
        by_priority = {
            priority: priority_counts.get(priority, 0) for priority in TaskPriority
        }
        total = sum(by_status.values())
        return DashboardTaskCounts(
            total=total,
            by_status=by_status,
            by_priority=by_priority,
        )

    def get_due_counts(
        self, project_id: int, query: DashboardDueQuery
    ) -> DashboardDueCounts:
        """Return mutually exclusive due buckets for non-terminal Tasks."""
        statement = select(
            func.count(TaskModel.id).label("active_total"),
            func.sum(case((TaskModel.due_at < query.as_of, 1), else_=0)).label(
                "overdue"
            ),
            func.sum(
                case(
                    (
                        (TaskModel.due_at >= query.as_of)
                        & (TaskModel.due_at < query.today_end),
                        1,
                    ),
                    else_=0,
                )
            ).label("due_today"),
            func.sum(
                case(
                    (
                        (TaskModel.due_at >= query.today_end)
                        & (TaskModel.due_at < query.upcoming_end),
                        1,
                    ),
                    else_=0,
                )
            ).label("upcoming_7_days"),
            func.sum(case((TaskModel.due_at >= query.upcoming_end, 1), else_=0)).label(
                "later"
            ),
            func.sum(case((TaskModel.due_at.is_(None), 1), else_=0)).label(
                "no_due_date"
            ),
        ).where(
            TaskModel.project_id == project_id,
            TaskModel.status.not_in(status.value for status in TERMINAL_TASK_STATUSES),
        )

        try:
            row = self._session.execute(statement).one()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

        return DashboardDueCounts(
            active_total=int(row.active_total),
            overdue=int(row.overdue or 0),
            due_today=int(row.due_today or 0),
            upcoming_7_days=int(row.upcoming_7_days or 0),
            later=int(row.later or 0),
            no_due_date=int(row.no_due_date or 0),
        )

    def list_tag_counts(self, project_id: int) -> tuple[DashboardTagCount, ...]:
        """Return every owned Tag and its distinct owned Task count."""
        statement = (
            select(
                TagModel.id,
                TagModel.name,
                TagModel.normalized_name,
                func.count(distinct(TaskModel.id)).label("task_count"),
            )
            .select_from(TagModel)
            .outerjoin(
                TaskTagModel,
                and_(
                    TaskTagModel.project_id == TagModel.project_id,
                    TaskTagModel.tag_id == TagModel.id,
                ),
            )
            .outerjoin(
                TaskModel,
                and_(
                    TaskModel.project_id == TaskTagModel.project_id,
                    TaskModel.id == TaskTagModel.task_id,
                ),
            )
            .where(TagModel.project_id == project_id)
            .group_by(
                TagModel.id,
                TagModel.name,
                TagModel.normalized_name,
            )
            .order_by(TagModel.normalized_name.asc(), TagModel.id.asc())
        )

        try:
            rows = self._session.execute(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

        return tuple(
            DashboardTagCount(
                id=row.id,
                name=row.name,
                normalized_name=row.normalized_name,
                task_count=int(row.task_count),
            )
            for row in rows
        )

    def get_comment_counts(self, project_id: int) -> DashboardCommentCounts:
        """Return current Comment totals confined to existing owned Tasks."""
        statement = (
            select(
                func.count(TaskCommentModel.id).label("total"),
                func.count(distinct(TaskModel.id)).label("tasks_with_comments"),
            )
            .select_from(TaskCommentModel)
            .join(
                TaskModel,
                and_(
                    TaskModel.project_id == TaskCommentModel.project_id,
                    TaskModel.id == TaskCommentModel.task_id,
                ),
            )
            .where(
                TaskCommentModel.project_id == project_id,
                TaskModel.project_id == project_id,
            )
        )

        try:
            row = self._session.execute(statement).one()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

        return DashboardCommentCounts(
            total=int(row.total),
            tasks_with_comments=int(row.tasks_with_comments),
        )

    def list_recent_activities(
        self, project_id: int, limit: int
    ) -> tuple[TaskCommentActivity, ...]:
        """Return bounded payload-free Activity metadata for existing owned Tasks."""
        _validate_activity_limit(limit)
        if limit == 0:
            return ()

        statement = (
            select(
                TaskCommentActivityModel.id,
                TaskCommentActivityModel.project_id,
                TaskCommentActivityModel.task_id,
                TaskCommentActivityModel.comment_id,
                TaskCommentActivityModel.event_type,
                TaskCommentActivityModel.occurred_at,
            )
            .select_from(TaskCommentActivityModel)
            .join(
                TaskModel,
                and_(
                    TaskModel.project_id == TaskCommentActivityModel.project_id,
                    TaskModel.id == TaskCommentActivityModel.task_id,
                ),
            )
            .where(
                TaskCommentActivityModel.project_id == project_id,
                TaskModel.project_id == project_id,
            )
            .order_by(
                TaskCommentActivityModel.occurred_at.desc(),
                TaskCommentActivityModel.id.desc(),
            )
            .limit(limit)
        )

        try:
            rows = self._session.execute(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

        return tuple(
            TaskCommentActivity(
                id=row.id,
                project_id=row.project_id,
                task_id=row.task_id,
                comment_id=row.comment_id,
                event_type=CommentEventType(row.event_type),
                occurred_at=_as_utc(row.occurred_at),
            )
            for row in rows
        )

    def _rollback_and_raise(self, error: SQLAlchemyError) -> NoReturn:
        self._session.rollback()
        raise RepositoryError("Dashboard persistence operation failed") from error
