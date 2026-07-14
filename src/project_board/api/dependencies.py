"""Request-scoped dependency construction for the application APIs."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from project_board.application import (
    ProjectService,
    TagService,
    TaskCommentService,
    TaskService,
)
from project_board.infrastructure import SessionFactory
from project_board.repositories.sqlalchemy_comment_repository import (
    SQLAlchemyTaskCommentRepository,
)
from project_board.repositories.sqlalchemy_project_repository import (
    SQLAlchemyProjectRepository,
)
from project_board.repositories.sqlalchemy_tag_repository import (
    SQLAlchemyTagRepository,
)
from project_board.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
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


def get_task_service(
    session: Annotated[Session, Depends(get_session)],
) -> TaskService:
    """Build the nested Task service against request-scoped repositories."""
    return TaskService(
        SQLAlchemyTaskRepository(session),
        SQLAlchemyProjectRepository(session),
        SQLAlchemyTagRepository(session),
    )


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]


def get_tag_service(
    session: Annotated[Session, Depends(get_session)],
) -> TagService:
    """Build the nested Tag service against request-scoped repositories."""
    return TagService(
        SQLAlchemyTagRepository(session),
        SQLAlchemyProjectRepository(session),
        SQLAlchemyTaskRepository(session),
    )


TagServiceDependency = Annotated[TagService, Depends(get_tag_service)]


def get_task_comment_service(
    session: Annotated[Session, Depends(get_session)],
) -> TaskCommentService:
    """Build the nested Comment service against request-scoped repositories."""
    return TaskCommentService(
        SQLAlchemyTaskCommentRepository(session),
        SQLAlchemyProjectRepository(session),
        SQLAlchemyTaskRepository(session),
    )


TaskCommentServiceDependency = Annotated[
    TaskCommentService, Depends(get_task_comment_service)
]
