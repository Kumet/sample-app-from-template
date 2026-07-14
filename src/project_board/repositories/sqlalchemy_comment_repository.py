"""Transactional SQLAlchemy persistence for Task Comments and Activity."""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import (
    CommentEventType,
    RepositoryError,
    TaskComment,
    TaskCommentActivity,
)
from project_board.infrastructure.models import (
    TaskCommentActivityModel,
    TaskCommentModel,
)
from project_board.repositories.comment_repository import (
    ActivityListQuery,
    CommentListQuery,
)
from project_board.repositories.task_repository import SortOrder


def _as_utc(value: datetime) -> datetime:
    """Restore UTC awareness lost by SQLite's datetime representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_comment(model: TaskCommentModel) -> TaskComment:
    return TaskComment(
        id=model.id,
        project_id=model.project_id,
        task_id=model.task_id,
        body=model.body,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _to_activity(model: TaskCommentActivityModel) -> TaskCommentActivity:
    return TaskCommentActivity(
        id=model.id,
        project_id=model.project_id,
        task_id=model.task_id,
        comment_id=model.comment_id,
        event_type=CommentEventType(model.event_type),
        occurred_at=_as_utc(model.occurred_at),
    )


class SQLAlchemyTaskCommentRepository:
    """Own atomic Comment mutations and append-only Activity persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, comment: TaskComment, occurred_at: datetime) -> TaskComment:
        model = TaskCommentModel(
            project_id=comment.project_id,
            task_id=comment.task_id,
            body=comment.body,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
        self._session.add(model)
        try:
            # The generated Comment ID is required by the paired Activity row.
            # Flushing does not commit; both rows still share one transaction.
            self._session.flush()
            self._append_activity(
                model.project_id,
                model.task_id,
                model.id,
                CommentEventType.CREATED,
                occurred_at,
            )
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return _to_comment(model)

    def list(
        self, project_id: int, task_id: int, query: CommentListQuery
    ) -> builtins.list[TaskComment]:
        primary_order = (
            TaskCommentModel.created_at.asc()
            if query.order is SortOrder.ASC
            else TaskCommentModel.created_at.desc()
        )
        statement = (
            select(TaskCommentModel)
            .where(
                TaskCommentModel.project_id == project_id,
                TaskCommentModel.task_id == task_id,
            )
            .order_by(primary_order, TaskCommentModel.id.asc())
            .limit(query.limit)
            .offset(query.offset)
        )
        try:
            models = self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return [_to_comment(model) for model in models]

    def get(self, project_id: int, task_id: int, comment_id: int) -> TaskComment | None:
        statement = select(TaskCommentModel).where(
            TaskCommentModel.project_id == project_id,
            TaskCommentModel.task_id == task_id,
            TaskCommentModel.id == comment_id,
        )
        try:
            model = self._session.scalar(statement)
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return None if model is None else _to_comment(model)

    def update(self, comment: TaskComment, occurred_at: datetime) -> TaskComment | None:
        statement = select(TaskCommentModel).where(
            TaskCommentModel.project_id == comment.project_id,
            TaskCommentModel.task_id == comment.task_id,
            TaskCommentModel.id == comment.id,
        )
        try:
            model = self._session.scalar(statement)
            if model is None:
                return None
            model.body = comment.body
            model.updated_at = comment.updated_at
            self._append_activity(
                model.project_id,
                model.task_id,
                model.id,
                CommentEventType.UPDATED,
                occurred_at,
            )
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return _to_comment(model)

    def delete(
        self,
        project_id: int,
        task_id: int,
        comment_id: int,
        occurred_at: datetime,
    ) -> bool:
        statement = select(TaskCommentModel).where(
            TaskCommentModel.project_id == project_id,
            TaskCommentModel.task_id == task_id,
            TaskCommentModel.id == comment_id,
        )
        try:
            model = self._session.scalar(statement)
            if model is None:
                return False
            self._append_activity(
                project_id,
                task_id,
                comment_id,
                CommentEventType.DELETED,
                occurred_at,
            )
            self._session.delete(model)
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return True

    def list_activities(
        self, project_id: int, task_id: int, query: ActivityListQuery
    ) -> builtins.list[TaskCommentActivity]:
        statement = select(TaskCommentActivityModel).where(
            TaskCommentActivityModel.project_id == project_id,
            TaskCommentActivityModel.task_id == task_id,
        )
        if query.event_type is not None:
            statement = statement.where(
                TaskCommentActivityModel.event_type == query.event_type.value
            )
        primary_order = (
            TaskCommentActivityModel.occurred_at.asc()
            if query.order is SortOrder.ASC
            else TaskCommentActivityModel.occurred_at.desc()
        )
        statement = (
            statement.order_by(primary_order, TaskCommentActivityModel.id.asc())
            .limit(query.limit)
            .offset(query.offset)
        )
        try:
            models = self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return [_to_activity(model) for model in models]

    def _append_activity(
        self,
        project_id: int,
        task_id: int,
        comment_id: int,
        event_type: CommentEventType,
        occurred_at: datetime,
    ) -> None:
        self._session.add(
            TaskCommentActivityModel(
                project_id=project_id,
                task_id=task_id,
                comment_id=comment_id,
                event_type=event_type.value,
                occurred_at=occurred_at,
            )
        )

    def _rollback_and_raise(self, error: SQLAlchemyError) -> NoReturn:
        self._session.rollback()
        raise RepositoryError("Task Comment persistence operation failed") from error
