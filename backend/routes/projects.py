from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from exceptions import CreatorCutError
from models.project import Project, ProjectCreate, ProjectRead, ProjectUpdate, StoryBrief
from models.clip import ClipRead
from storage.database import get_session
from storage.local import ensure_project_dirs
from config import settings

router = APIRouter(prefix="/projects", tags=["projects"])


def _now() -> datetime:
    return datetime.utcnow()


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(body: ProjectCreate, session: Session = Depends(get_session)) -> Project:
    project = Project(
        name=body.name,
        brief=body.brief.model_dump() if body.brief else None,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    ensure_project_dirs(settings.base_dir, project.id)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.created_at.desc())).all())


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    session: Session = Depends(get_session),
) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    update_data = body.model_dump(exclude_unset=True)
    if "brief" in update_data and update_data["brief"] is not None:
        update_data["brief"] = StoryBrief(**update_data["brief"]).model_dump()

    for field, value in update_data.items():
        setattr(project, field, value)
    project.updated_at = _now()

    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_session)) -> None:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    session.delete(project)
    session.commit()


@router.get("/{project_id}/clips", response_model=list[ClipRead])
def list_clips(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    from models.clip import Clip
    from sqlmodel import select
    clips = session.exec(
        select(Clip)
        .where(Clip.project_id == project_id)
        .order_by(Clip.order)
    ).all()
    return list(clips)
