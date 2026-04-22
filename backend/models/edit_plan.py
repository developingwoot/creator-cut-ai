import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator
from sqlmodel import Column, Field, JSON, SQLModel


class EditPlanStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class BRollPlacement(BaseModel):
    clip_id: str
    start_seconds: float
    end_seconds: float
    description: str


class SoundDesignCue(BaseModel):
    sfx_id: str
    at_seconds: float
    duration_seconds: float
    volume: float = 1.0


class EditSegment(BaseModel):
    """One continuous segment in the final edit."""
    order: int
    clip_id: str
    source_start: float
    source_end: float
    is_broll: bool = False
    narration_note: str = ""
    b_roll_overlays: list[BRollPlacement] = []
    sound_cues: list[SoundDesignCue] = []

    @field_validator("source_end")
    @classmethod
    def end_after_start(cls, v: float, info) -> float:
        start = info.data.get("source_start", 0)
        if v <= start:
            raise ValueError("source_end must be after source_start")
        return v


class EditPlan(SQLModel, table=True):
    __tablename__ = "edit_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    status: EditPlanStatus = EditPlanStatus.draft
    segments: list | None = Field(default=None, sa_column=Column(JSON))
    total_duration_seconds: float | None = None
    reasoning: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None


class EditPlanRead(BaseModel):
    id: str
    project_id: str
    status: EditPlanStatus
    segments: list | None
    total_duration_seconds: float | None
    reasoning: str | None
    created_at: datetime
    approved_at: datetime | None

    model_config = {"from_attributes": True}


class EditPlanApprove(BaseModel):
    approved: bool
    feedback: str | None = None
