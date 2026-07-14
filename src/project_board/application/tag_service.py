"""Tag use cases orchestrated against persistence boundaries."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from project_board.application.project_service import UNSET, _UnsetType
from project_board.domain import ProjectNotFound, Tag, TagNotFound, TagValidationError
from project_board.repositories.project_repository import ProjectRepository
from project_board.repositories.tag_repository import TagRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TagService:
    """Implement Project-scoped Tag CRUD without framework dependencies."""

    def __init__(
        self,
        tag_repository: TagRepository,
        project_repository: ProjectRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._tags = tag_repository
        self._projects = project_repository
        self._clock = clock

    def create_tag(
        self,
        project_id: int,
        name: str,
        color: str | None = None,
    ) -> Tag:
        self._require_project(project_id)
        now = self._clock()
        tag = Tag(
            id=0,
            project_id=project_id,
            name=name,
            color=color,
            created_at=now,
            updated_at=now,
        )
        return self._tags.create(tag)

    def list_tags(self, project_id: int) -> list[Tag]:
        self._require_project(project_id)
        return self._tags.list(project_id)

    def get_tag(self, project_id: int, tag_id: int) -> Tag:
        self._require_project(project_id)
        tag = self._tags.get(project_id, tag_id)
        if tag is None:
            raise TagNotFound(project_id, tag_id)
        return tag

    def update_tag(
        self,
        project_id: int,
        tag_id: int,
        *,
        name: str | None | _UnsetType = UNSET,
        color: str | None | _UnsetType = UNSET,
    ) -> Tag:
        if isinstance(name, _UnsetType) and isinstance(color, _UnsetType):
            raise TagValidationError("At least one Tag field is required")
        if name is None:
            raise TagValidationError("Tag name is required")

        current = self.get_tag(project_id, tag_id)
        updated = replace(
            current,
            name=current.name if isinstance(name, _UnsetType) else name,
            color=current.color if isinstance(color, _UnsetType) else color,
            updated_at=self._clock(),
        )
        persisted = self._tags.update(updated)
        if persisted is None:
            raise TagNotFound(project_id, tag_id)
        return persisted

    def delete_tag(self, project_id: int, tag_id: int) -> None:
        self._require_project(project_id)
        if not self._tags.delete(project_id, tag_id):
            raise TagNotFound(project_id, tag_id)

    def _require_project(self, project_id: int) -> None:
        if self._projects.get(project_id) is None:
            raise ProjectNotFound(project_id)
