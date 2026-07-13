"""Request-scoped dependency construction for the Project API."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from project_board.application import ProjectService
from project_board.infrastructure import SessionFactory
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)


def get_session(request: Request) -> Iterator[Session]:
    """Yield and reliably close a session owned by the current request."""
    session_factory: SessionFactory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_project_service(
    session: Annotated[Session, Depends(get_session)],
) -> ProjectService:
    """Build the service against the request's repository."""
    return ProjectService(SQLAlchemyProjectRepository(session))


ProjectServiceDependency = Annotated[ProjectService, Depends(get_project_service)]
