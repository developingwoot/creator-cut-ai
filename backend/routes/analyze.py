from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlmodel import Session, select

from config import key_manager, settings
from exceptions import PipelineError
from models.clip import Clip, ClipAnalysis, ClipStatus
from models.edit_plan import EditPlan
from models.project import Project, ProjectStatus, StoryBrief
from pipeline.pass1_clip_analysis import run_pass1
from pipeline.pass2_edit_planning import run_pass2
from pipeline.proxy import generate_proxy
from pipeline.whisper_transcribe import transcribe_clip
from storage.database import get_engine
from storage.local import db_path, ensure_project_dirs, pipeline_lock_path

router = APIRouter(prefix="/projects", tags=["analyze"])


@router.post("/{project_id}/analyze")
async def analyze_project(
    project_id: str,
    brief: StoryBrief,
) -> StreamingResponse:
    """Start the analysis pipeline and stream SSE progress events.

    SSE event shape: {"stage": str, "clip_id": str|null, "progress": float, "message": str}
    Stages: proxying → transcribing → analyzing → planning → done (or error).
    The final "done" event carries an additional "edit_plan_id" field.
    """
    engine = get_engine(db_path(settings.base_dir))
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        clips = list(
            session.exec(
                select(Clip)
                .where(Clip.project_id == project_id)
                .order_by(Clip.order)
            ).all()
        )

    if not clips:
        raise HTTPException(status_code=422, detail="Project has no clips registered")

    return StreamingResponse(
        _pipeline_stream(project_id, clips, brief, engine),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Pipeline generator ────────────────────────────────────────────────────────


async def _pipeline_stream(
    project_id: str,
    clips: list[Clip],
    brief: StoryBrief,
    engine: Any,
) -> AsyncGenerator[str, None]:
    base_dir = settings.base_dir
    lock_path = pipeline_lock_path(base_dir, project_id)
    ensure_project_dirs(base_dir, project_id)

    def _emit(
        stage: str,
        *,
        clip_id: str | None = None,
        progress: float = 0.0,
        message: str = "",
        **extra: Any,
    ) -> str:
        data: dict[str, Any] = {
            "stage": stage,
            "clip_id": clip_id,
            "progress": progress,
            "message": message,
        }
        data.update(extra)
        return f"data: {json.dumps(data)}\n\n"

    def _save_clip(clip: Clip) -> None:
        # Reload by PK and apply fields so the in-flight `clip` object is never
        # attached to a session (which would expire it on commit and cause
        # DetachedInstanceError on the next attribute access).
        with Session(engine) as s:
            db_clip = s.get(Clip, clip.id)
            if db_clip is None:
                return
            db_clip.proxy_path = clip.proxy_path
            db_clip.status = clip.status
            db_clip.transcript = clip.transcript
            db_clip.analysis = clip.analysis
            db_clip.error_message = clip.error_message
            s.add(db_clip)
            s.commit()

    if lock_path.exists():
        yield _emit("error", message=f"Pipeline already running for project {project_id}")
        return

    lock_path.touch()
    n = len(clips)

    try:
        _set_project_status(engine, project_id, ProjectStatus.analyzing)

        # ── Stage 1: proxy + transcribe each clip ─────────────────────────────
        for i, clip in enumerate(clips):
            ingest_progress = i / n * 0.4  # ingest occupies 0–40% of overall progress

            yield _emit(
                "proxying",
                clip_id=clip.id,
                progress=ingest_progress,
                message=f"Generating proxy for {clip.filename}",
            )
            try:
                proxy = await asyncio.to_thread(generate_proxy, clip, project_id, base_dir)
                clip.proxy_path = str(proxy)
                clip.status = ClipStatus.proxied
            except Exception as exc:
                clip.status = ClipStatus.failed
                clip.error_message = str(exc)
                _save_clip(clip)
                logger.warning("Proxy failed for clip {}: {}", clip.id, exc)
                yield _emit(
                    "proxying",
                    clip_id=clip.id,
                    progress=ingest_progress,
                    message=f"Proxy failed for {clip.filename} — skipping",
                )
                continue
            _save_clip(clip)

            yield _emit(
                "transcribing",
                clip_id=clip.id,
                progress=ingest_progress + 0.2 / n,
                message=f"Transcribing {clip.filename}",
            )
            transcript = await asyncio.to_thread(transcribe_clip, clip, project_id, base_dir)
            clip.transcript = transcript
            clip.status = ClipStatus.transcribed
            _save_clip(clip)

        proxied_clips = [c for c in clips if c.status != ClipStatus.failed]
        if not proxied_clips:
            raise PipelineError("All clips failed during proxy generation", stage="ingest")

        # ── Stage 2: Pass 1 — per-clip analysis ──────────────────────────────
        yield _emit("analyzing", progress=0.4, message="Analysing clips with AI…")
        client = anthropic.Anthropic(api_key=key_manager.get_key())
        pass1_results = await run_pass1(proxied_clips, project_id, base_dir, client=client)

        successful: list[tuple[Clip, ClipAnalysis]] = []
        for idx, (clip, analysis) in enumerate(pass1_results):
            if analysis is not None:
                clip.analysis = analysis.model_dump()
                successful.append((clip, analysis))
            _save_clip(clip)
            yield _emit(
                "analyzing",
                clip_id=clip.id,
                progress=0.4 + 0.3 * (idx + 1) / len(pass1_results),
                message=f"Analysed {clip.filename}",
            )

        if not successful:
            raise PipelineError("No clips could be analysed successfully", stage="pass1")

        # ── Stage 3: Pass 2 — edit planning ──────────────────────────────────
        _set_project_status(engine, project_id, ProjectStatus.planning)
        yield _emit("planning", progress=0.75, message="Generating edit plan…")

        edit_plan: EditPlan = await asyncio.to_thread(
            run_pass2, successful, brief, project_id, base_dir, client
        )

        with Session(engine) as s:
            s.add(edit_plan)
            s.commit()
            s.refresh(edit_plan)
            plan_id = edit_plan.id

        _set_project_status(engine, project_id, ProjectStatus.ready_to_review)
        yield _emit("done", progress=1.0, message="Edit plan ready for review", edit_plan_id=plan_id)

    except Exception as exc:
        logger.exception("Pipeline failed for project {}", project_id)
        _set_project_status(engine, project_id, ProjectStatus.failed)
        yield _emit("error", message=str(exc))
    finally:
        lock_path.unlink(missing_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _set_project_status(engine: Any, project_id: str, status: ProjectStatus) -> None:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        if project:
            project.status = status
            s.add(project)
            s.commit()
