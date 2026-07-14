"""Pydantic request and response schemas for the application APIs."""

from datetime import datetime
from typing import Annotated, TypeAlias

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from project_board.domain.datetime import normalize_utc_datetime
from project_board.domain.project import (
    MAX_PROJECT_DESCRIPTION_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
)
from project_board.domain.tag import (
    MAX_TAG_NAME_LENGTH,
    normalize_tag_color,
    normalize_tag_name,
)
from project_board.domain.task import (
    MAX_TASK_DESCRIPTION_LENGTH,
    MAX_TASK_TITLE_LENGTH,
    TaskPriority,
    TaskStatus,
)


def _trim_description(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    return trimmed or None


def _normalize_aware_utc_datetime(value: datetime) -> datetime:
    return normalize_utc_datetime(value, "datetime query parameter")


AwareUtcDatetime: TypeAlias = Annotated[
    datetime, AfterValidator(_normalize_aware_utc_datetime)
]


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


class TagCreate(BaseModel):
    """Payload accepted when creating a Tag under a Project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=MAX_TAG_NAME_LENGTH)
    color: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_tag_name(value)[0]

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        return normalize_tag_color(value)


class TagUpdate(BaseModel):
    """Payload accepted for a partial Tag update."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=MAX_TAG_NAME_LENGTH)
    color: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        return normalize_tag_name(value)[0]

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        return normalize_tag_color(value)

    @model_validator(mode="after")
    def require_update_field(self) -> "TagUpdate":
        if not self.model_fields_set.intersection({"name", "color"}):
            raise ValueError("At least one Tag field is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Tag name cannot be null")
        return self


class TagResponse(BaseModel):
    """Serialized public Tag returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    """Payload accepted when creating a Task under a Project."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(
        default=None, max_length=MAX_TASK_DESCRIPTION_LENGTH
    )
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: datetime | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Task title is required")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        return _trim_description(value)

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return normalize_utc_datetime(value, "Task due_at")


class TaskUpdate(BaseModel):
    """Payload accepted for a partial Task update."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=MAX_TASK_TITLE_LENGTH)
    description: str | None = Field(
        default=None, max_length=MAX_TASK_DESCRIPTION_LENGTH
    )
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Task title is required")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        return _trim_description(value)

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return normalize_utc_datetime(value, "Task due_at")

    @model_validator(mode="after")
    def require_update_field(self) -> "TaskUpdate":
        mutable_fields = {"title", "description", "status", "priority", "due_at"}
        if not self.model_fields_set.intersection(mutable_fields):
            raise ValueError("At least one Task field is required")
        for field_name in ("title", "status", "priority"):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"Task {field_name} cannot be null")
        return self


class TaskResponse(BaseModel):
    """Serialized Task returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse]
