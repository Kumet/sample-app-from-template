"""Persistence boundary used by Project application services."""

from typing import Protocol

from project_board.domain import Project


class ProjectRepository(Protocol):
    """Repository operations available to the application layer."""

    def create(self, project: Project) -> Project:
        """Persist a new Project and return it with its database-generated ID."""
        ...

    def list(self) -> list[Project]:
        """Return Projects ordered by creation time and then ID."""
        ...

    def get(self, project_id: int) -> Project | None:
        """Return a Project by ID, or ``None`` when it does not exist."""
        ...

    def update(self, project: Project) -> Project | None:
        """Replace a persisted Project, or return ``None`` when absent."""
        ...

    def delete(self, project_id: int) -> bool:
        """Physically delete a Project and report whether it existed."""
        ...
