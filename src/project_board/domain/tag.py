"""Tag domain model and its invariants."""

import re
from dataclasses import dataclass, field
from datetime import datetime

from project_board.domain.datetime import normalize_utc_datetime
from project_board.domain.errors import TagValidationError

MAX_TAG_NAME_LENGTH = 50
_TAG_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}\Z")


def normalize_tag_name(name: str) -> tuple[str, str]:
    """Return the trimmed display name and its internal uniqueness value."""
    display_name = name.strip()
    if not display_name:
        raise TagValidationError("Tag name is required")
    if len(display_name) > MAX_TAG_NAME_LENGTH:
        raise TagValidationError(
            f"Tag name must be at most {MAX_TAG_NAME_LENGTH} characters"
        )
    return display_name, display_name.casefold()


def normalize_tag_color(color: str | None) -> str | None:
    """Return an uppercase ``#RRGGBB`` color, preserving ``None``."""
    if color is None:
        return None
    if _TAG_COLOR_PATTERN.fullmatch(color) is None:
        raise TagValidationError("Tag color must be null or use #RRGGBB format")
    return color.upper()


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    try:
        return normalize_utc_datetime(value, f"Tag {field_name}")
    except ValueError as error:
        raise TagValidationError(str(error)) from error


@dataclass(frozen=True, slots=True)
class Tag:
    """A validated Project-owned Tag independent of API and persistence tools."""

    id: int
    project_id: int
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime
    normalized_name: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        name, normalized_name = normalize_tag_name(self.name)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "normalized_name", normalized_name)
        object.__setattr__(self, "color", normalize_tag_color(self.color))
        object.__setattr__(
            self, "created_at", _normalize_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _normalize_datetime(self.updated_at, "updated_at")
        )
