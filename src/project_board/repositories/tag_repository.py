"""Persistence boundary used by Tag application services."""

from typing import Protocol

from project_board.domain import Tag


class TagRepository(Protocol):
    """Ownership-aware Tag and Task-Tag operations for the application layer."""

    def create(self, tag: Tag) -> Tag:
        """Persist a Tag and return it with its database-generated ID."""
        ...

    def list(self, project_id: int) -> list[Tag]:
        """Return owned Tags ordered by normalized name and then ID."""
        ...

    def get(self, project_id: int, tag_id: int) -> Tag | None:
        """Return an owned Tag, or ``None`` when absent or mismatched."""
        ...

    def update(self, tag: Tag) -> Tag | None:
        """Replace an owned persisted Tag, or return ``None`` when absent."""
        ...

    def delete(self, project_id: int, tag_id: int) -> bool:
        """Delete an owned Tag and report whether it existed."""
        ...

    def attach(self, project_id: int, task_id: int, tag_id: int) -> None:
        """Idempotently associate an owned Task and Tag."""
        ...

    def detach(self, project_id: int, task_id: int, tag_id: int) -> None:
        """Idempotently remove an owned Task and Tag association."""
        ...
