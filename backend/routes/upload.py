from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from loguru import logger
from sqlmodel import Session, select

from config import settings
from exceptions import InvalidClipError, PathTraversalError, UnsupportedCodecError
from models.clip import Clip, ClipRead, ClipStatus
from models.project import Project, ProjectStatus
from storage.database import get_session
from storage.local import clip_path, ensure_project_dirs

router = APIRouter(prefix="/projects", tags=["upload"])

_SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".m4v"}
_CHUNK_SIZE = 1024 * 1024  # 1 MB


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

    import json
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

    # Reject obviously unsupported codecs
    if codec in {"mjpeg", "png", "gif"}:
        raise UnsupportedCodecError(path.name, codec)

    width = stream.get("width")
    height = stream.get("height")
    resolution = f"{width}x{height}" if width and height else None

    # r_frame_rate is a fraction string like "30000/1001"
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


@router.post("/{project_id}/clips", response_model=list[ClipRead], status_code=201)
async def upload_clips(
    project_id: str,
    files: list[UploadFile],
    session: Session = Depends(get_session),
) -> list[Clip]:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.status not in (ProjectStatus.created, ProjectStatus.uploading):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot upload clips — project is in '{project.status}' state",
        )

    # Count existing clips to determine order offset
    existing = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    order_offset = len(existing)

    ensure_project_dirs(settings.base_dir, project_id)
    created_clips: list[Clip] = []

    for i, upload in enumerate(files):
        filename = upload.filename or f"clip_{i}"
        ext = Path(filename).suffix.lower()

        if ext not in _SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"'{filename}' has unsupported extension '{ext}'. "
                       f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}",
            )

        try:
            dest = clip_path(settings.base_dir, project_id, filename)
        except PathTraversalError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        # Write file to disk in chunks
        try:
            with dest.open("wb") as f:
                while chunk := await upload.read(_CHUNK_SIZE):
                    f.write(chunk)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to write '{filename}': {exc}")

        # Probe the saved file
        try:
            probe = _probe_clip(dest)
        except (InvalidClipError, UnsupportedCodecError) as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc))

        clip = Clip(
            project_id=project_id,
            filename=filename,
            original_path=str(dest),
            order=order_offset + i,
            **probe,
        )
        session.add(clip)
        created_clips.append(clip)
        logger.info(f"Uploaded clip '{filename}' to project {project_id}")

    project.status = ProjectStatus.uploading
    project.updated_at = datetime.utcnow()
    session.add(project)
    session.commit()
    for clip in created_clips:
        session.refresh(clip)

    return created_clips


@router.delete("/{project_id}/clips/{clip_id}", status_code=204)
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

    # Remove the file from disk; don't fail if already gone
    original = Path(clip.original_path)
    if original.exists():
        original.unlink()
        logger.info(f"Deleted clip file {original}")

    session.delete(clip)
    session.commit()
