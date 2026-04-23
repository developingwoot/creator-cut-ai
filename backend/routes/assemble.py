from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlmodel import Session, select

from config import settings
from exceptions import AssemblyError, ClipNotFoundError, FFmpegError, PipelineLockError
from models.clip import Clip
from models.edit_plan import EditPlan, EditPlanApprove, EditPlanRead, EditPlanStatus
from models.project import Project, ProjectStatus
from pipeline.assembly import assemble
from storage.database import get_engine, get_session
from storage.local import db_path, pipeline_lock_path

router = APIRouter(prefix="/projects", tags=["assemble"])


# ── GET /projects/{project_id}/edit-plan ─────────────────────────────────────


@router.get("/{project_id}/edit-plan", response_model=EditPlanRead)
def get_edit_plan(
    project_id: str,
    session: Session = Depends(get_session),
) -> EditPlanRead:
    """Return the most recently created edit plan for this project."""
    _require_project(session, project_id)
    plan = session.exec(
        select(EditPlan)
        .where(EditPlan.project_id == project_id)
        .order_by(EditPlan.created_at.desc())
        .limit(1)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No edit plan found for project {project_id}")
    return EditPlanRead.model_validate(plan)


# ── POST /projects/{project_id}/edit-plan/approve ────────────────────────────


@router.post("/{project_id}/edit-plan/approve", response_model=EditPlanRead)
def approve_edit_plan(
    project_id: str,
    body: EditPlanApprove,
    session: Session = Depends(get_session),
) -> EditPlanRead:
    """Approve or reject the current draft edit plan."""
    _require_project(session, project_id)
    plan = session.exec(
        select(EditPlan)
        .where(EditPlan.project_id == project_id)
        .order_by(EditPlan.created_at.desc())
        .limit(1)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No edit plan found for project {project_id}")
    if plan.status != EditPlanStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=f"Edit plan is already '{plan.status}' — only draft plans can be approved or rejected",
        )
    if body.approved:
        plan.status = EditPlanStatus.approved
        plan.approved_at = datetime.utcnow()
    else:
        plan.status = EditPlanStatus.rejected
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return EditPlanRead.model_validate(plan)


# ── POST /projects/{project_id}/assemble ─────────────────────────────────────


@router.post("/{project_id}/assemble")
async def assemble_project(project_id: str) -> StreamingResponse:
    """Assemble the approved edit plan into output.mp4 and stream SSE progress.

    SSE event shape: {"stage": str, "progress": float, "message": str}
    Stages: assembling → done (or error).
    The "done" event carries an additional "output_path" field.
    """
    engine = get_engine(db_path(settings.base_dir))
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        plan = session.exec(
            select(EditPlan)
            .where(EditPlan.project_id == project_id)
            .where(EditPlan.status == EditPlanStatus.approved)
            .order_by(EditPlan.approved_at.desc())
            .limit(1)
        ).first()
        if plan is None:
            raise HTTPException(
                status_code=409,
                detail="No approved edit plan found — approve the plan before assembling",
            )

        clips = list(
            session.exec(select(Clip).where(Clip.project_id == project_id)).all()
        )

    clips_by_id = {c.id: c for c in clips}

    return StreamingResponse(
        _assembly_stream(project_id, plan, clips_by_id, engine),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Assembly generator ────────────────────────────────────────────────────────


async def _assembly_stream(
    project_id: str,
    plan: EditPlan,
    clips_by_id: dict[str, Clip],
    engine: Any,
) -> AsyncGenerator[str, None]:
    base_dir = settings.base_dir
    lock_path = pipeline_lock_path(base_dir, project_id)

    def _emit(stage: str, *, progress: float = 0.0, message: str = "", **extra: Any) -> str:
        data: dict[str, Any] = {"stage": stage, "progress": progress, "message": message}
        data.update(extra)
        return f"data: {json.dumps(data)}\n\n"

    if lock_path.exists():
        yield _emit("error", message=f"Pipeline already running for project {project_id}")
        return

    lock_path.touch()
    try:
        _set_project_status(engine, project_id, ProjectStatus.assembling)
        yield _emit("assembling", progress=0.0, message="Assembling segments…")

        output = await asyncio.to_thread(assemble, plan, clips_by_id, project_id, base_dir)

        _set_project_status(engine, project_id, ProjectStatus.complete)
        yield _emit(
            "done",
            progress=1.0,
            message="Assembly complete",
            output_path=str(output),
        )

    except (ClipNotFoundError, AssemblyError, FFmpegError) as exc:
        logger.exception("Assembly failed for project {}", project_id)
        _set_project_status(engine, project_id, ProjectStatus.failed)
        yield _emit("error", message=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during assembly for project {}", project_id)
        _set_project_status(engine, project_id, ProjectStatus.failed)
        yield _emit("error", message=f"Unexpected error: {exc}")
    finally:
        lock_path.unlink(missing_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


def _set_project_status(engine: Any, project_id: str, status: ProjectStatus) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        if project:
            project.status = status
            s.add(project)
            s.commit()
