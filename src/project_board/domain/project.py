"""Project domain model and its invariants."""

from dataclasses import dataclass
from datetime import UTC, datetime

from project_board.domain.errors import ProjectValidationError

MAX_PROJECT_NAME_LENGTH = 100
MAX_PROJECT_DESCRIPTION_LENGTH = 1000


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ProjectValidationError("Project name is required")
    if len(normalized) > MAX_PROJECT_NAME_LENGTH:
        raise ProjectValidationError(
            f"Project name must be at most {MAX_PROJECT_NAME_LENGTH} characters"
        )
    return normalized


def _normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    normalized = description.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_PROJECT_DESCRIPTION_LENGTH:
        raise ProjectValidationError(
            "Project description must be at most "
            f"{MAX_PROJECT_DESCRIPTION_LENGTH} characters"
        )
    return normalized


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProjectValidationError(f"Project {field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Project:
    """A validated Project independent of API and persistence frameworks."""

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_name(self.name))
        object.__setattr__(
            self, "description", _normalize_description(self.description)
        )
        object.__setattr__(
            self, "created_at", _normalize_datetime(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _normalize_datetime(self.updated_at, "updated_at")
        )
