from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session, select

from config import settings
from exceptions import InvalidClipError, PathTraversalError, UnsupportedCodecError
from models.clip import Clip, ClipRead, ClipStatus
from models.project import Project, ProjectStatus
from storage.database import get_session
from storage.local import (
    assert_safe_filename,
    ensure_project_dirs,
    frames_subdir,
    proxy_path,
    transcript_path,
)

router = APIRouter(prefix="/projects", tags=["upload"])

_SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".m4v"}


def _probe_clip(path: Path) -> dict:
    """Run ffprobe to extract codec, duration, resolution, fps. Raises InvalidClipError on failure."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,r_frame_rate,duration",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise InvalidClipError(path.name, f"ffprobe failed: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise InvalidClipError(path.name, "ffprobe returned unreadable output")

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    if not streams:
        raise InvalidClipError(path.name, "no video stream found")

    stream = streams[0]
    codec = stream.get("codec_name", "unknown")

    if codec in {"mjpeg", "png", "gif"}:
        raise UnsupportedCodecError(path.name, codec)

    width = stream.get("width")
    height = stream.get("height")
    resolution = f"{width}x{height}" if width and height else None

    fps_str = stream.get("r_frame_rate", "0/1")
    try:
        num, den = fps_str.split("/")
        fps = round(float(num) / float(den), 3) if int(den) != 0 else None
    except (ValueError, ZeroDivisionError):
        fps = None

    duration = float(stream.get("duration") or fmt.get("duration") or 0) or None
    size = int(fmt.get("size", 0)) or path.stat().st_size

    return {
        "codec": codec,
        "resolution": resolution,
        "fps": fps,
        "duration_seconds": duration,
        "file_size_bytes": size,
    }


class ClipRegisterRequest(BaseModel):
    file_paths: list[str]


@router.post("/{project_id}/clips/register", response_model=list[ClipRead], status_code=201)
def register_clips(
    project_id: str,
    body: ClipRegisterRequest,
    session: Session = Depends(get_session),
) -> list[Clip]:
    """Register clips by their existing paths on disk. No copying — files stay where they are."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.status not in (ProjectStatus.created, ProjectStatus.uploading):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot register clips — project is in '{project.status}' state",
        )

    existing = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    order_offset = len(existing)

    # Create derived-file directories (clips/ dir is no longer used)
    ensure_project_dirs(settings.base_dir, project_id)
    created_clips: list[Clip] = []

    for i, file_path_str in enumerate(body.file_paths):
        path = Path(file_path_str)

        if not path.exists():
            raise HTTPException(status_code=422, detail=f"File not found: {file_path_str}")

        if not path.is_file():
            raise HTTPException(status_code=422, detail=f"Not a file: {file_path_str}")

        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"'{path.name}' has unsupported extension '{ext}'. "
                       f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}",
            )

        try:
            assert_safe_filename(path.name)
        except PathTraversalError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        try:
            probe = _probe_clip(path)
        except (InvalidClipError, UnsupportedCodecError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        clip = Clip(
            project_id=project_id,
            filename=path.name,
            original_path=str(path.resolve()),
            order=order_offset + i,
            **probe,
        )
        session.add(clip)
        created_clips.append(clip)
        logger.info(f"Registered clip '{path.name}' for project {project_id} at {path.resolve()}")

    project.status = ProjectStatus.uploading
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    for clip in created_clips:
        session.refresh(clip)

    return created_clips


@router.delete("/{project_id}/clips/{clip_id}", status_code=204, response_model=None)
def delete_clip(
    project_id: str,
    clip_id: str,
    session: Session = Depends(get_session),
) -> None:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    clip = session.get(Clip, clip_id)
    if not clip or clip.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found")

    if project.status not in (ProjectStatus.created, ProjectStatus.uploading):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete clips — project is in '{project.status}' state",
        )

    # Delete derived files only — original_path is the user's file; never touch it
    for derived in (
        proxy_path(settings.base_dir, project_id, clip_id),
        transcript_path(settings.base_dir, project_id, clip_id),
    ):
        if derived.exists():
            derived.unlink()
            logger.info(f"Deleted derived file {derived}")

    frames = frames_subdir(settings.base_dir, project_id, clip_id)
    if frames.exists():
        shutil.rmtree(frames)
        logger.info(f"Deleted frames directory {frames}")

    session.delete(clip)
    session.commit()
