"""Transactional SQLAlchemy implementation of Project persistence."""

from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import Project, ProjectHasTasksConflict, RepositoryError
from project_board.infrastructure.models import ProjectModel, TaskModel


def _as_utc(value: datetime) -> datetime:
    """Restore UTC awareness lost by SQLite's datetime representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_domain(model: ProjectModel) -> Project:
    return Project(
        id=model.id,
        name=model.name,
        description=model.description,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SQLAlchemyProjectRepository:
    """Persist Projects using one caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, project: Project) -> Project:
        model = ProjectModel(
            name=project.name,
            description=project.description,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        self._session.add(model)
        self._commit()
        return _to_domain(model)

    def list(self) -> list[Project]:
        statement = select(ProjectModel).order_by(
            ProjectModel.created_at.asc(), ProjectModel.id.asc()
        )
        try:
            models = self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return [_to_domain(model) for model in models]

    def get(self, project_id: int) -> Project | None:
        try:
            model = self._session.get(ProjectModel, project_id)
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return None if model is None else _to_domain(model)

    def update(self, project: Project) -> Project | None:
        try:
            model = self._session.get(ProjectModel, project.id)
            if model is None:
                return None
            model.name = project.name
            model.description = project.description
            model.created_at = project.created_at
            model.updated_at = project.updated_at
            self._session.commit()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return _to_domain(model)

    def delete(self, project_id: int) -> bool:
        try:
            model = self._session.get(ProjectModel, project_id)
            if model is None:
                return False
            task_id = self._session.scalar(
                select(TaskModel.id).where(TaskModel.project_id == project_id).limit(1)
            )
            if task_id is not None:
                self._session.rollback()
                raise ProjectHasTasksConflict(project_id)
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
        raise RepositoryError("Project persistence operation failed") from error
