"""Pydantic request and response schemas for the Project API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from project_board.domain.project import (
    MAX_PROJECT_DESCRIPTION_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
)


def _trim_description(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    return trimmed or None


class ProjectCreate(BaseModel):
    """Payload accepted when creating a Project."""

    name: str = Field(max_length=MAX_PROJECT_NAME_LENGTH)
    description: str | None = Field(
        default=None, max_length=MAX_PROJECT_DESCRIPTION_LENGTH
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Project name is required")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        return _trim_description(value)


class ProjectUpdate(BaseModel):
    """Payload accepted for a partial Project update."""

    name: str | None = Field(default=None, max_length=MAX_PROJECT_NAME_LENGTH)
    description: str | None = Field(
        default=None, max_length=MAX_PROJECT_DESCRIPTION_LENGTH
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Project name is required")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        return _trim_description(value)

    @model_validator(mode="after")
    def require_update_field(self) -> "ProjectUpdate":
        if not self.model_fields_set.intersection({"name", "description"}):
            raise ValueError("At least one Project field is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Project name cannot be null")
        return self


class ProjectResponse(BaseModel):
    """Serialized Project returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
