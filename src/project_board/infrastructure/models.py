"""SQLAlchemy persistence models, kept separate from domain objects."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from project_board.infrastructure.database import Base


class ProjectModel(Base):
    """Database representation of a Project."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TaskModel(Base):
    """Database representation of a Task owned by a Project."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("uq_tasks_project_id_id", "project_id", "id", unique=True),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_project_id_status", "project_id", "status"),
        Index("ix_tasks_project_id_priority", "project_id", "priority"),
        Index("ix_tasks_project_id_due_at", "project_id", "due_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TagModel(Base):
    """Database representation of a Tag owned by a Project."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "normalized_name",
            name="uq_tags_project_id_normalized_name",
        ),
        UniqueConstraint("project_id", "id", name="uq_tags_project_id_id"),
        Index(
            "ix_tags_project_id_normalized_name",
            "project_id",
            "normalized_name",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TaskTagModel(Base):
    """Project-owned association between a Task and a Tag."""

    __tablename__ = "task_tags"
    __table_args__ = (
        ForeignKeyConstraint(
            ("project_id", "task_id"),
            ("tasks.project_id", "tasks.id"),
            name="fk_task_tags_task_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("project_id", "tag_id"),
            ("tags.project_id", "tags.id"),
            name="fk_task_tags_tag_owner",
            ondelete="CASCADE",
        ),
        Index("ix_task_tags_project_id_tag_id", "project_id", "tag_id"),
    )

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True)
