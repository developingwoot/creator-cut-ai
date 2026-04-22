from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator
from sqlmodel import Column, Field, JSON, Relationship, SQLModel

if TYPE_CHECKING:
    from models.clip import Clip


class ProjectStatus(str, Enum):
    created = "created"
    uploading = "uploading"
    analyzing = "analyzing"
    planning = "planning"
    ready_to_review = "ready_to_review"
    assembling = "assembling"
    complete = "complete"
    failed = "failed"


class StoryBrief(BaseModel):
    """Validated story brief provided by the user before analysis begins."""
    title: str
    story_summary: str
    target_duration_seconds: int
    tone: str
    key_moments: list[str] = []
    b_roll_preferences: list[str] = []

    @field_validator("target_duration_seconds")
    @classmethod
    def duration_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("target_duration_seconds must be positive")
        return v

    @field_validator("title", "story_summary", "tone")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be blank")
        return v.strip()


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    status: ProjectStatus = ProjectStatus.created
    brief: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None

    clips: list["Clip"] = Relationship(back_populates="project")


class ProjectCreate(BaseModel):
    name: str
    brief: StoryBrief | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v.strip()


class ProjectRead(BaseModel):
    id: str
    name: str
    status: ProjectStatus
    brief: dict | None
    created_at: datetime
    updated_at: datetime
    error_message: str | None

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    name: str | None = None
    brief: StoryBrief | None = None
    status: ProjectStatus | None = None
    error_message: str | None = None
