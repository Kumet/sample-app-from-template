import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_board.application import TagService
from project_board.domain import (
    DuplicateTagName,
    Project,
    ProjectNotFound,
    RepositoryError,
    Tag,
    TagNotFound,
    TagValidationError,
)

NOW = datetime(2026, 2, 1, 12, tzinfo=UTC)
LATER = datetime(2026, 2, 2, 12, tzinfo=UTC)


def make_project(project_id: int = 1) -> Project:
    return Project(project_id, "Project", None, NOW, NOW)


def make_tag(tag_id: int = 1, project_id: int = 1, **changes: object) -> Tag:
    values = {
        "id": tag_id,
        "project_id": project_id,
        "name": "Backend",
        "color": "#112233",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return Tag(**values)  # type: ignore[arg-type]


class StubProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects = {project.id: project for project in projects or []}

    def create(self, project: Project) -> Project:
        raise NotImplementedError

    def list(self) -> list[Project]:
        return list(self.projects.values())

    def get(self, project_id: int) -> Project | None:
        return self.projects.get(project_id)

    def update(self, project: Project) -> Project | None:
        raise NotImplementedError

    def delete(self, project_id: int) -> bool:
        raise NotImplementedError


class StubTagRepository:
    def __init__(self, tags: list[Tag] | None = None) -> None:
        self.tags = {(tag.project_id, tag.id): tag for tag in tags or []}
        self.created: Tag | None = None
        self.updated: Tag | None = None
        self.deleted_key: tuple[int, int] | None = None
        self.listed_project_id: int | None = None

    def create(self, tag: Tag) -> Tag:
        self.created = tag
        persisted = replace(tag, id=10)
        self.tags[(persisted.project_id, persisted.id)] = persisted
        return persisted

    def list(self, project_id: int) -> list[Tag]:
        self.listed_project_id = project_id
        return [
            tag
            for (owned_project_id, _), tag in self.tags.items()
            if owned_project_id == project_id
        ]

    def get(self, project_id: int, tag_id: int) -> Tag | None:
        return self.tags.get((project_id, tag_id))

    def update(self, tag: Tag) -> Tag | None:
        self.updated = tag
        key = (tag.project_id, tag.id)
        if key not in self.tags:
            return None
        self.tags[key] = tag
        return tag

    def delete(self, project_id: int, tag_id: int) -> bool:
        self.deleted_key = (project_id, tag_id)
        return self.tags.pop((project_id, tag_id), None) is not None

    def attach(self, project_id: int, task_id: int, tag_id: int) -> None:
        raise NotImplementedError

    def detach(self, project_id: int, task_id: int, tag_id: int) -> None:
        raise NotImplementedError


def make_service(
    tags: StubTagRepository,
    projects: StubProjectRepository | None = None,
) -> TagService:
    return TagService(
        tags,
        projects or StubProjectRepository([make_project()]),
        clock=lambda: LATER,
    )


def test_importing_tag_service_does_not_load_sqlalchemy_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.application.tag_service

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_project_repository",
    "project_board.repositories.sqlalchemy_tag_repository",
    "project_board.infrastructure.database",
    "project_board.infrastructure.models",
)
print(json.dumps([name for name in watched_modules if name in sys.modules]))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=repository_root,
        env={"PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert json.loads(completed.stdout) == []


def test_create_tag_requires_project_and_delegates_normalized_tag() -> None:
    repository = StubTagRepository()

    created = make_service(repository).create_tag(1, "  Backend  ", "#a1b2c3")

    assert created.id == 10
    assert repository.created == Tag(0, 1, "Backend", "#A1B2C3", LATER, LATER)

    missing_project_repository = StubTagRepository()
    with pytest.raises(ProjectNotFound):
        make_service(missing_project_repository, StubProjectRepository()).create_tag(
            7, "Backend"
        )
    assert missing_project_repository.created is None


def test_create_tag_applies_domain_validation_before_persistence() -> None:
    repository = StubTagRepository()

    with pytest.raises(TagValidationError):
        make_service(repository).create_tag(1, " ")

    assert repository.created is None


def test_list_tags_requires_project_and_delegates_owned_scope() -> None:
    owned = make_tag(2)
    repository = StubTagRepository([owned, make_tag(3, project_id=2)])

    assert make_service(repository).list_tags(1) == [owned]
    assert repository.listed_project_id == 1

    missing_project_repository = StubTagRepository([owned])
    with pytest.raises(ProjectNotFound):
        make_service(missing_project_repository, StubProjectRepository()).list_tags(1)
    assert missing_project_repository.listed_project_id is None


def test_get_tag_returns_only_owned_tag() -> None:
    tag = make_tag(4)

    assert make_service(StubTagRepository([tag])).get_tag(1, 4) is tag


def test_get_tag_distinguishes_missing_project_from_missing_owned_tag() -> None:
    repository = StubTagRepository([make_tag(4, project_id=2)])

    with pytest.raises(ProjectNotFound):
        make_service(repository, StubProjectRepository()).get_tag(1, 4)

    with pytest.raises(TagNotFound) as captured:
        make_service(repository).get_tag(1, 4)
    assert captured.value.project_id == 1
    assert captured.value.tag_id == 4


def test_update_tag_changes_only_supplied_fields_and_timestamp() -> None:
    original = make_tag(3)
    repository = StubTagRepository([original])

    updated = make_service(repository).update_tag(1, 3, name=" backend ")

    assert updated.name == "backend"
    assert updated.normalized_name == "backend"
    assert updated.color == original.color
    assert updated.created_at == original.created_at
    assert updated.updated_at == LATER
    assert repository.updated is updated


def test_update_tag_explicit_null_clears_color() -> None:
    repository = StubTagRepository([make_tag(3)])

    assert make_service(repository).update_tag(1, 3, color=None).color is None


def test_update_tag_rejects_empty_patch_without_lookup_or_timestamp_change() -> None:
    original = make_tag(3)
    repository = StubTagRepository([original])

    with pytest.raises(TagValidationError, match="At least one Tag field"):
        make_service(repository).update_tag(1, 3)

    assert repository.tags[(1, 3)] is original
    assert repository.updated is None


def test_update_tag_rejects_null_name_without_persistence() -> None:
    original = make_tag(3)
    repository = StubTagRepository([original])

    with pytest.raises(TagValidationError, match="Tag name is required"):
        make_service(repository).update_tag(1, 3, name=None)

    assert repository.tags[(1, 3)] is original
    assert repository.updated is None


def test_update_tag_raises_not_found_when_tag_disappears() -> None:
    class DisappearingTagRepository(StubTagRepository):
        def update(self, tag: Tag) -> Tag | None:
            self.updated = tag
            return None

    repository = DisappearingTagRepository([make_tag(3)])

    with pytest.raises(TagNotFound):
        make_service(repository).update_tag(1, 3, color="#AABBCC")


def test_delete_tag_delegates_to_owned_repository_operation() -> None:
    repository = StubTagRepository([make_tag(4)])

    assert make_service(repository).delete_tag(1, 4) is None
    assert repository.deleted_key == (1, 4)


def test_delete_tag_raises_not_found_for_missing_or_mismatched_tag() -> None:
    with pytest.raises(TagNotFound):
        make_service(StubTagRepository()).delete_tag(1, 4)

    mismatched = StubTagRepository([make_tag(4, project_id=2)])
    with pytest.raises(TagNotFound):
        make_service(mismatched).delete_tag(1, 4)


@pytest.mark.parametrize("operation", ["create", "update"])
def test_duplicate_tag_name_propagates_unchanged(operation: str) -> None:
    error = DuplicateTagName(1, "Backend")

    class DuplicateTagRepository(StubTagRepository):
        def create(self, tag: Tag) -> Tag:
            raise error

        def update(self, tag: Tag) -> Tag | None:
            raise error

    repository = DuplicateTagRepository([make_tag(3)])
    service = make_service(repository)

    with pytest.raises(DuplicateTagName) as captured:
        if operation == "create":
            service.create_tag(1, "Backend")
        else:
            service.update_tag(1, 3, name="Backend")

    assert captured.value is error


def test_repository_errors_propagate_unchanged() -> None:
    error = RepositoryError("sanitized failure")

    class FailingTagRepository(StubTagRepository):
        def delete(self, project_id: int, tag_id: int) -> bool:
            raise error

    service = make_service(FailingTagRepository([make_tag(3)]))

    with pytest.raises(RepositoryError) as captured:
        service.delete_tag(1, 3)

    assert captured.value is error
