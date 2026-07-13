from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import (
    Project,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
)


def make_project(**changes: object) -> Project:
    values = {
        "id": 1,
        "name": "Sample project",
        "description": "Description",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return Project(**values)  # type: ignore[arg-type]


def test_project_normalizes_name_and_description() -> None:
    project = make_project(name="  Sample project  ", description="  Details  ")

    assert project.name == "Sample project"
    assert project.description == "Details"


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_project_rejects_empty_name(name: str) -> None:
    with pytest.raises(ProjectValidationError, match="name is required"):
        make_project(name=name)


def test_project_accepts_100_character_trimmed_name() -> None:
    assert make_project(name=f" {'a' * 100} ").name == "a" * 100


def test_project_rejects_name_over_100_characters_after_trimming() -> None:
    with pytest.raises(ProjectValidationError, match="at most 100"):
        make_project(name=f" {'a' * 101} ")


@pytest.mark.parametrize("description", [None, "", "  "])
def test_project_normalizes_missing_or_empty_description_to_none(
    description: str | None,
) -> None:
    assert make_project(description=description).description is None


def test_project_accepts_1000_character_trimmed_description() -> None:
    project = make_project(description=f" {'a' * 1000} ")

    assert project.description == "a" * 1000


def test_project_rejects_description_over_1000_characters_after_trimming() -> None:
    with pytest.raises(ProjectValidationError, match="at most 1000"):
        make_project(description=f" {'a' * 1001} ")


def test_project_converts_aware_datetimes_to_utc() -> None:
    offset = timezone(timedelta(hours=9))
    project = make_project(
        created_at=datetime(2026, 1, 1, 9, tzinfo=offset),
        updated_at=datetime(2026, 1, 2, 9, tzinfo=offset),
    )

    assert project.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert project.updated_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert project.created_at.tzinfo is UTC
    assert project.updated_at.tzinfo is UTC


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_project_rejects_naive_datetimes(field_name: str) -> None:
    with pytest.raises(ProjectValidationError, match=f"{field_name} must be"):
        make_project(**{field_name: datetime(2026, 1, 1)})


def test_replacing_project_fields_reapplies_domain_validation() -> None:
    project = make_project()

    updated = replace(project, name="  Updated  ", description="  ")

    assert updated.name == "Updated"
    assert updated.description is None


def test_project_not_found_exposes_the_missing_id() -> None:
    error = ProjectNotFound(42)

    assert error.project_id == 42
    assert str(error) == "Project 42 was not found"


def test_domain_errors_have_stable_base_types() -> None:
    assert isinstance(ProjectValidationError("invalid"), ValueError)
    assert isinstance(ProjectNotFound(1), LookupError)
    assert isinstance(RepositoryError("failed"), RuntimeError)
