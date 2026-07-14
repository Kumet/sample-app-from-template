import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_board.application import ProjectService
from project_board.domain import (
    Project,
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
)


def test_importing_project_service_does_not_load_sqlalchemy_infrastructure() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    script = """
import json
import sys

import project_board.application.project_service

watched_modules = (
    "sqlalchemy",
    "project_board.repositories.sqlalchemy_project_repository",
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


def make_project(project_id: int = 1, **changes: object) -> Project:
    values = {
        "id": project_id,
        "name": "Sample project",
        "description": "Description",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return Project(**values)  # type: ignore[arg-type]


class StubProjectRepository:
    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects = {project.id: project for project in projects or []}
        self.created: Project | None = None
        self.updated: Project | None = None
        self.deleted_id: int | None = None

    def create(self, project: Project) -> Project:
        self.created = project
        persisted = replace(project, id=10)
        self.projects[persisted.id] = persisted
        return persisted

    def list(self) -> list[Project]:
        return list(self.projects.values())

    def get(self, project_id: int) -> Project | None:
        return self.projects.get(project_id)

    def update(self, project: Project) -> Project | None:
        self.updated = project
        if project.id not in self.projects:
            return None
        self.projects[project.id] = project
        return project

    def delete(self, project_id: int) -> bool:
        self.deleted_id = project_id
        return self.projects.pop(project_id, None) is not None


NOW = datetime(2026, 2, 1, 12, tzinfo=UTC)


def test_create_project_validates_and_delegates_to_repository() -> None:
    repository = StubProjectRepository()
    service = ProjectService(repository, clock=lambda: NOW)

    created = service.create_project("  New project  ", "  Details  ")

    assert created.id == 10
    assert created.name == "New project"
    assert repository.created == Project(0, "New project", "Details", NOW, NOW)


def test_create_project_applies_domain_validation_before_persistence() -> None:
    repository = StubProjectRepository()
    service = ProjectService(repository, clock=lambda: NOW)

    with pytest.raises(ProjectValidationError):
        service.create_project("  ")

    assert repository.created is None


def test_list_projects_returns_repository_result() -> None:
    projects = [make_project(2), make_project(1)]
    service = ProjectService(StubProjectRepository(projects))

    assert service.list_projects() == projects


def test_get_project_returns_existing_project() -> None:
    project = make_project(7)
    service = ProjectService(StubProjectRepository([project]))

    assert service.get_project(7) is project


def test_get_project_raises_not_found_for_missing_id() -> None:
    service = ProjectService(StubProjectRepository())

    with pytest.raises(ProjectNotFound) as captured:
        service.get_project(7)

    assert captured.value.project_id == 7


def test_update_project_changes_only_supplied_fields_and_timestamp() -> None:
    original = make_project(3)
    repository = StubProjectRepository([original])
    service = ProjectService(repository, clock=lambda: NOW)

    updated = service.update_project(3, name="  Renamed  ")

    assert updated.name == "Renamed"
    assert updated.description == original.description
    assert updated.created_at == original.created_at
    assert updated.updated_at == NOW
    assert repository.updated is updated


def test_update_project_explicit_null_clears_description() -> None:
    service = ProjectService(
        StubProjectRepository([make_project(3)]), clock=lambda: NOW
    )

    assert service.update_project(3, description=None).description is None


def test_update_project_rejects_empty_patch() -> None:
    service = ProjectService(StubProjectRepository([make_project(3)]))

    with pytest.raises(ProjectValidationError, match="At least one"):
        service.update_project(3)


def test_update_project_raises_not_found_when_lookup_is_missing() -> None:
    service = ProjectService(StubProjectRepository())

    with pytest.raises(ProjectNotFound):
        service.update_project(8, name="Renamed")


def test_update_project_raises_not_found_when_project_disappears() -> None:
    class DisappearingRepository(StubProjectRepository):
        def update(self, project: Project) -> Project | None:
            return None

    service = ProjectService(
        DisappearingRepository([make_project(8)]), clock=lambda: NOW
    )

    with pytest.raises(ProjectNotFound):
        service.update_project(8, name="Renamed")


def test_delete_project_delegates_to_repository() -> None:
    repository = StubProjectRepository([make_project(4)])
    service = ProjectService(repository)

    assert service.delete_project(4) is None
    assert repository.deleted_id == 4


def test_delete_project_raises_not_found_for_missing_id() -> None:
    service = ProjectService(StubProjectRepository())

    with pytest.raises(ProjectNotFound):
        service.delete_project(4)


def test_delete_project_propagates_task_conflict_unchanged() -> None:
    conflict = ProjectHasTasksConflict(4)

    class ConflictingRepository(StubProjectRepository):
        def delete(self, project_id: int) -> bool:
            raise conflict

    service = ProjectService(ConflictingRepository([make_project(4)]))

    with pytest.raises(ProjectHasTasksConflict) as captured:
        service.delete_project(4)

    assert captured.value is conflict


def test_repository_errors_propagate_unchanged() -> None:
    error = RepositoryError("sanitized failure")

    class FailingRepository(StubProjectRepository):
        def list(self) -> list[Project]:
            raise error

    service = ProjectService(FailingRepository())

    with pytest.raises(RepositoryError) as captured:
        service.list_projects()

    assert captured.value is error
