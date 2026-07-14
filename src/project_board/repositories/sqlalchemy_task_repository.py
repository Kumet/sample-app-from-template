"""Transactional SQLAlchemy implementation of Task persistence."""

from datetime import UTC, datetime
from typing import Any, NoReturn, cast

from sqlalchemy import case, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from project_board.domain import RepositoryError, Task, TaskPriority, TaskStatus
from project_board.infrastructure.models import TaskModel
from project_board.repositories.task_repository import (
    SortOrder,
    TaskListQuery,
    TaskSort,
)


def _as_utc(value: datetime) -> datetime:
    """Restore UTC awareness lost by SQLite's datetime representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_as_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)


def _to_domain(model: TaskModel) -> Task:
    return Task(
        id=model.id,
        project_id=model.project_id,
        title=model.title,
        description=model.description,
        status=TaskStatus(model.status),
        priority=TaskPriority(model.priority),
        due_at=_optional_as_utc(model.due_at),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SQLAlchemyTaskRepository:
    """Persist ownership-scoped Tasks using one caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, task: Task) -> Task:
        model = TaskModel(
            project_id=task.project_id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority.value,
            due_at=task.due_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self._session.add(model)
        self._commit()
        return _to_domain(model)

    def list(self, project_id: int, query: TaskListQuery) -> list[Task]:
        statement = select(TaskModel).where(TaskModel.project_id == project_id)
        if query.status is not None:
            statement = statement.where(TaskModel.status == query.status.value)
        if query.priority is not None:
            statement = statement.where(TaskModel.priority == query.priority.value)
        if query.due_before is not None:
            statement = statement.where(TaskModel.due_at < query.due_before)
        if query.due_after is not None:
            statement = statement.where(TaskModel.due_at > query.due_after)

        primary_sort: ColumnElement[Any]
        if query.sort is TaskSort.PRIORITY:
            primary_sort = case(
                (TaskModel.priority == "low", 0),
                (TaskModel.priority == "medium", 1),
                (TaskModel.priority == "high", 2),
            )
        else:
            primary_sort = cast(
                ColumnElement[Any],
                {
                    TaskSort.CREATED_AT: TaskModel.created_at,
                    TaskSort.UPDATED_AT: TaskModel.updated_at,
                    TaskSort.DUE_AT: TaskModel.due_at,
                }[query.sort],
            )

        ordering = []
        if query.sort is TaskSort.DUE_AT:
            ordering.append(case((TaskModel.due_at.is_(None), 1), else_=0).asc())
        ordering.append(
            primary_sort.asc() if query.order is SortOrder.ASC else primary_sort.desc()
        )
        ordering.append(TaskModel.id.asc())
        statement = (
            statement.order_by(*ordering).limit(query.limit).offset(query.offset)
        )

        try:
            models = self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return [_to_domain(model) for model in models]

    def get(self, project_id: int, task_id: int) -> Task | None:
        statement = select(TaskModel).where(
            TaskModel.project_id == project_id,
            TaskModel.id == task_id,
        )
        try:
            model = self._session.scalar(statement)
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return None if model is None else _to_domain(model)

    def update(self, task: Task) -> Task | None:
        statement = select(TaskModel).where(
            TaskModel.project_id == task.project_id,
            TaskModel.id == task.id,
        )
        try:
            model = self._session.scalar(statement)
            if model is None:
                return None
            model.title = task.title
            model.description = task.description
            model.status = task.status.value
            model.priority = task.priority.value
            model.due_at = task.due_at
            model.updated_at = task.updated_at
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return _to_domain(model)

    def delete(self, project_id: int, task_id: int) -> bool:
        statement = select(TaskModel).where(
            TaskModel.project_id == project_id,
            TaskModel.id == task_id,
        )
        try:
            model = self._session.scalar(statement)
            if model is None:
                return False
            self._session.delete(model)
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return True

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)

    def _rollback_and_raise(self, error: SQLAlchemyError) -> NoReturn:
        self._session.rollback()
        raise RepositoryError("Task persistence operation failed") from error
