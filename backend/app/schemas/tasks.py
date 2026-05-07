"""Schemas for task CRUD and task comment API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel

from app.schemas.common import NonEmptyStr
from app.schemas.tags import TagRef
from app.schemas.task_custom_fields import TaskCustomFieldValues

TaskStatus = Literal["inbox", "in_progress", "review", "done"]
STATUS_REQUIRED_ERROR = "status is required"
# Keep these symbols as runtime globals so Pydantic can resolve
# deferred annotations reliably.
RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr, TagRef)


class TaskBase(SQLModel):
    """Shared task fields used by task create/read payloads."""

    title: str
    description: str | None = None
    status: TaskStatus = "inbox"
    priority: str = "medium"
    due_at: datetime | None = None
    assigned_agent_id: UUID | None = None
    story_points: int | None = None
    depends_on_task_ids: list[UUID] = Field(default_factory=list)
    tag_ids: list[UUID] = Field(default_factory=list)


MAX_STORY_POINTS = 5
_POINTS_ERROR = f"story_points must be {MAX_STORY_POINTS} or fewer — split into smaller stories"


class TaskCreate(TaskBase):
    """Payload for creating a task."""

    created_by_user_id: UUID | None = None
    custom_field_values: TaskCustomFieldValues = Field(default_factory=dict)

    @field_validator("story_points", mode="before")
    @classmethod
    def cap_story_points(cls, value: object) -> object:
        if value is not None and int(value) > MAX_STORY_POINTS:
            raise ValueError(_POINTS_ERROR)
        return value


class TaskUpdate(SQLModel):
    """Payload for partial task updates."""

    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: str | None = None
    due_at: datetime | None = None
    assigned_agent_id: UUID | None = None
    story_points: int | None = None
    depends_on_task_ids: list[UUID] | None = None
    tag_ids: list[UUID] | None = None
    custom_field_values: TaskCustomFieldValues | None = None
    comment: NonEmptyStr | None = None

    @field_validator("story_points", mode="before")
    @classmethod
    def cap_story_points(cls, value: object) -> object:
        if value is not None and int(value) > MAX_STORY_POINTS:
            raise ValueError(_POINTS_ERROR)
        return value

    @field_validator("comment", mode="before")
    @classmethod
    def normalize_comment(cls, value: object) -> object | None:
        """Normalize blank comment strings to `None`."""
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        """Ensure explicitly supplied status is not null."""
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError(STATUS_REQUIRED_ERROR)
        return self


class TaskRead(TaskBase):
    """Task payload returned from read endpoints."""

    id: UUID
    board_id: UUID | None
    created_by_user_id: UUID | None
    in_progress_at: datetime | None
    created_at: datetime
    updated_at: datetime
    blocked_by_task_ids: list[UUID] = Field(default_factory=list)
    is_blocked: bool = False
    tags: list[TagRef] = Field(default_factory=list)
    custom_field_values: TaskCustomFieldValues | None = None


class TaskCommentCreate(SQLModel):
    """Payload for creating a task comment."""

    message: NonEmptyStr


class TaskCommentRead(SQLModel):
    """Task comment payload returned from read endpoints."""

    id: UUID
    message: str | None
    actor_type: str | None = None
    agent_id: UUID | None
    user_id: UUID | None = None
    task_id: UUID | None
    created_at: datetime


class TaskMovementRead(SQLModel):
    """Structured task movement audit payload returned from read endpoints."""

    id: UUID
    task_id: UUID | None
    board_id: UUID | None
    message: str | None
    actor_type: str | None = None
    agent_id: UUID | None = None
    user_id: UUID | None = None
    previous_status: str | None = None
    new_status: str | None = None
    previous_assigned_agent_id: UUID | None = None
    new_assigned_agent_id: UUID | None = None
    created_at: datetime
