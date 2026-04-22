from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlmodel import Column, Field, JSON, Relationship, SQLModel

if TYPE_CHECKING:
    from models.project import Project


class ClipStatus(str, Enum):
    uploaded = "uploaded"
    proxying = "proxying"
    transcribing = "transcribing"
    analyzing = "analyzing"
    analyzed = "analyzed"
    failed = "failed"


class Clip(SQLModel, table=True):
    __tablename__ = "clips"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    filename: str
    original_path: str
    proxy_path: str | None = None
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    codec: str | None = None
    resolution: str | None = None
    fps: float | None = None
    order: int = 0
    status: ClipStatus = ClipStatus.uploaded
    transcript: dict | None = Field(default=None, sa_column=Column(JSON))
    analysis: dict | None = Field(default=None, sa_column=Column(JSON))
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    project: "Project" = Relationship(back_populates="clips")


class ClipRead(BaseModel):
    id: str
    project_id: str
    filename: str
    duration_seconds: float | None
    file_size_bytes: int | None
    codec: str | None
    resolution: str | None
    fps: float | None
    order: int
    status: ClipStatus
    transcript: dict | None
    analysis: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
