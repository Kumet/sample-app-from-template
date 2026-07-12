"""Project use cases orchestrated against the persistence boundary."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final

from project_board.domain import Project, ProjectNotFound, ProjectValidationError
from project_board.repositories import ProjectRepository


class _UnsetType:
    """Marker distinguishing an omitted update field from an explicit null."""

    __slots__ = ()


UNSET: Final = _UnsetType()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectService:
    """Implement Project CRUD without depending on delivery or persistence tools."""

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def create_project(self, name: str, description: str | None = None) -> Project:
        now = self._clock()
        project = Project(
            id=0,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        return self._repository.create(project)

    def list_projects(self) -> list[Project]:
        return self._repository.list()

    def get_project(self, project_id: int) -> Project:
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFound(project_id)
        return project

    def update_project(
        self,
        project_id: int,
        *,
        name: str | _UnsetType = UNSET,
        description: str | None | _UnsetType = UNSET,
    ) -> Project:
        if isinstance(name, _UnsetType) and isinstance(description, _UnsetType):
            raise ProjectValidationError("At least one Project field is required")

        current = self.get_project(project_id)
        updated = replace(
            current,
            name=current.name if isinstance(name, _UnsetType) else name,
            description=(
                current.description
                if isinstance(description, _UnsetType)
                else description
            ),
            updated_at=self._clock(),
        )
        persisted = self._repository.update(updated)
        if persisted is None:
            raise ProjectNotFound(project_id)
        return persisted

    def delete_project(self, project_id: int) -> None:
        if not self._repository.delete(project_id):
            raise ProjectNotFound(project_id)
