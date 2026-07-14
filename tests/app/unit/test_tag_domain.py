from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from project_board.domain import (
    DuplicateTagName,
    Tag,
    TagNotFound,
    TagValidationError,
)


def make_tag(**changes: object) -> Tag:
    values = {
        "id": 1,
        "project_id": 2,
        "name": "Backend",
        "color": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    values.update(changes)
    return Tag(**values)  # type: ignore[arg-type]


def test_tag_trims_display_name_and_casefolds_internal_name() -> None:
    tag = make_tag(name="  Straße  ")

    assert tag.name == "Straße"
    assert tag.normalized_name == "strasse"


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_tag_rejects_empty_name(name: str) -> None:
    with pytest.raises(TagValidationError, match="name is required"):
        make_tag(name=name)


def test_tag_accepts_50_character_trimmed_name() -> None:
    tag = make_tag(name=f" {'a' * 50} ")

    assert tag.name == "a" * 50
    assert tag.normalized_name == "a" * 50


def test_tag_rejects_name_over_50_characters_after_trimming() -> None:
    with pytest.raises(TagValidationError, match="at most 50"):
        make_tag(name=f" {'a' * 51} ")


@pytest.mark.parametrize(
    ("color", "expected"),
    [(None, None), ("#A1B2C3", "#A1B2C3"), ("#a1b2c3", "#A1B2C3")],
)
def test_tag_normalizes_valid_colors(color: str | None, expected: str | None) -> None:
    assert make_tag(color=color).color == expected


@pytest.mark.parametrize(
    "color",
    ["", " ", "A1B2C3", "#12345", "#1234567", "#GG0000", " #A1B2C3 "],
)
def test_tag_rejects_invalid_colors(color: str) -> None:
    with pytest.raises(TagValidationError, match="#RRGGBB"):
        make_tag(color=color)


def test_tag_converts_aware_datetimes_to_utc() -> None:
    offset = timezone(timedelta(hours=9))
    tag = make_tag(
        created_at=datetime(2026, 1, 1, 9, tzinfo=offset),
        updated_at=datetime(2026, 1, 2, 9, tzinfo=offset),
    )

    assert tag.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert tag.updated_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert tag.created_at.tzinfo is UTC
    assert tag.updated_at.tzinfo is UTC


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_tag_rejects_naive_datetimes(field_name: str) -> None:
    with pytest.raises(TagValidationError, match=f"{field_name} must be"):
        make_tag(**{field_name: datetime(2026, 1, 1)})


def test_tag_is_frozen_and_replacement_recomputes_internal_values() -> None:
    tag = make_tag()

    with pytest.raises(FrozenInstanceError):
        tag.project_id = 3  # type: ignore[misc]

    updated = replace(tag, name=" backend ", color="#abcdef")
    assert updated.name == "backend"
    assert updated.normalized_name == "backend"
    assert updated.color == "#ABCDEF"


def test_tag_not_found_exposes_requested_ownership() -> None:
    error = TagNotFound(project_id=4, tag_id=9)

    assert error.project_id == 4
    assert error.tag_id == 9
    assert str(error) == "Tag 9 was not found in Project 4"


def test_duplicate_tag_name_exposes_conflicting_project_and_display_name() -> None:
    error = DuplicateTagName(project_id=4, name="Backend")

    assert error.project_id == 4
    assert error.name == "Backend"
    assert str(error) == "Tag name 'Backend' already exists in Project 4"


def test_tag_errors_have_stable_base_types() -> None:
    assert isinstance(TagValidationError("invalid"), ValueError)
    assert isinstance(TagNotFound(1, 2), LookupError)
    assert isinstance(DuplicateTagName(1, "backend"), RuntimeError)
