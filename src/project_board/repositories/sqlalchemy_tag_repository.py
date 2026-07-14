"""Transactional SQLAlchemy implementation of Tag persistence."""

from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from project_board.domain import DuplicateTagName, RepositoryError, Tag
from project_board.infrastructure.models import TagModel


def _as_utc(value: datetime) -> datetime:
    """Restore UTC awareness lost by SQLite's datetime representation."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_domain(model: TagModel) -> Tag:
    return Tag(
        id=model.id,
        project_id=model.project_id,
        name=model.name,
        color=model.color,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class SQLAlchemyTagRepository:
    """Persist ownership-scoped Tags using one caller-owned session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, tag: Tag) -> Tag:
        model = TagModel(
            project_id=tag.project_id,
            name=tag.name,
            normalized_name=tag.normalized_name,
            color=tag.color,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
        )
        self._session.add(model)
        try:
            self._session.commit()
        except SQLAlchemyError as error:
            self._raise_write_error(error, tag)
        return _to_domain(model)

    def list(self, project_id: int) -> list[Tag]:
        statement = (
            select(TagModel)
            .where(TagModel.project_id == project_id)
            .order_by(TagModel.normalized_name.asc(), TagModel.id.asc())
        )
        try:
            models = self._session.scalars(statement).all()
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return [_to_domain(model) for model in models]

    def get(self, project_id: int, tag_id: int) -> Tag | None:
        statement = select(TagModel).where(
            TagModel.project_id == project_id,
            TagModel.id == tag_id,
        )
        try:
            model = self._session.scalar(statement)
        except SQLAlchemyError as error:
            self._rollback_and_raise(error)
        return None if model is None else _to_domain(model)

    def update(self, tag: Tag) -> Tag | None:
        statement = select(TagModel).where(
            TagModel.project_id == tag.project_id,
            TagModel.id == tag.id,
        )
        try:
            model = self._session.scalar(statement)
            if model is None:
                return None
            model.name = tag.name
            model.normalized_name = tag.normalized_name
            model.color = tag.color
            model.updated_at = tag.updated_at
            self._session.commit()
        except SQLAlchemyError as error:
            self._raise_write_error(error, tag, exclude_id=tag.id)
        return _to_domain(model)

    def delete(self, project_id: int, tag_id: int) -> bool:
        statement = select(TagModel).where(
            TagModel.project_id == project_id,
            TagModel.id == tag_id,
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

    def _raise_write_error(
        self,
        error: SQLAlchemyError,
        tag: Tag,
        *,
        exclude_id: int | None = None,
    ) -> NoReturn:
        self._session.rollback()
        if isinstance(error, IntegrityError) and self._duplicate_exists(
            tag, exclude_id=exclude_id
        ):
            raise DuplicateTagName(tag.project_id, tag.name) from error
        raise RepositoryError("Tag persistence operation failed") from error

    def _duplicate_exists(self, tag: Tag, *, exclude_id: int | None) -> bool:
        statement = select(TagModel.id).where(
            TagModel.project_id == tag.project_id,
            TagModel.normalized_name == tag.normalized_name,
        )
        if exclude_id is not None:
            statement = statement.where(TagModel.id != exclude_id)
        try:
            duplicate_id = self._session.scalar(statement)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise RepositoryError("Tag persistence operation failed") from error
        self._session.rollback()
        return duplicate_id is not None

    def _rollback_and_raise(self, error: SQLAlchemyError) -> NoReturn:
        self._session.rollback()
        raise RepositoryError("Tag persistence operation failed") from error
