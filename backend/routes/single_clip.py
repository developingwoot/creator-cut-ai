from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session, select

from config import key_manager, settings
from exceptions import PipelineError, SingleClipNotProcessedError
from models.clip import Clip, ClipStatus, SingleClipAnalysis
from models.project import Project
from pipeline.filler_detection import detect_fillers_from_words
from pipeline.proxy import generate_proxy
from pipeline.rename_suggestions import suggest_renames
from pipeline.silence_detection import detect_silence
from pipeline.single_clip_apply import apply_single_clip_edits
from pipeline.whisper_word_transcribe import transcribe_clip_with_words
from storage.database import get_engine
from storage.local import (
    assert_safe_filename,
    db_path,
    ensure_project_dirs,
    pipeline_lock_path,
    single_clip_output_path,
)

router = APIRouter(prefix="/projects", tags=["single_clip"])


# ── Process endpoint ──────────────────────────────────────────────────────────


@router.post("/{project_id}/single-clip/process")
async def process_single_clip(project_id: str) -> StreamingResponse:
    """Proxy → transcribe (word-level) → detect fillers → detect silence → suggest renames.

    SSE stages: proxying → transcribing → detecting → suggesting → done | error
    The "done" event carries: transcript, filler_spans, silence_spans, rename_suggestions.
    """
    engine = get_engine(db_path(settings.base_dir))
    clip = _get_single_clip(engine, project_id)

    return StreamingResponse(
        _process_stream(project_id, clip, engine),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Apply endpoint ────────────────────────────────────────────────────────────


class SingleClipApplyRequest(BaseModel):
    remove_fillers: bool = False
    remove_silence: bool = False
    chosen_filename: str | None = None


@router.post("/{project_id}/single-clip/apply")
async def apply_single_clip(
    project_id: str,
    body: SingleClipApplyRequest,
) -> StreamingResponse:
    """Apply filler/silence removal and (optionally) rename the output file.

    SSE stages: applying → done | error
    The "done" event carries: output_path.
    """
    if body.chosen_filename:
        try:
            assert_safe_filename(body.chosen_filename)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    engine = get_engine(db_path(settings.base_dir))
    clip = _get_single_clip(engine, project_id)

    if not clip.analysis or clip.status != ClipStatus.sc_ready:
        raise HTTPException(
            status_code=422,
            detail=f"Clip {clip.id} has not been processed — run the process step first.",
        )

    return StreamingResponse(
        _apply_stream(project_id, clip, body, engine),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Stream generators ─────────────────────────────────────────────────────────


async def _process_stream(
    project_id: str,
    clip: Clip,
    engine: Any,
) -> AsyncGenerator[str, None]:
    base_dir = settings.base_dir
    lock_path = pipeline_lock_path(base_dir, project_id)
    ensure_project_dirs(base_dir, project_id)

    def _emit(stage: str, *, progress: float = 0.0, message: str = "", **extra: Any) -> str:
        data: dict[str, Any] = {"stage": stage, "progress": progress, "message": message}
        data.update(extra)
        return f"data: {json.dumps(data)}\n\n"

    def _save_clip(c: Clip) -> None:
        with Session(engine) as s:
            db_clip = s.get(Clip, c.id)
            if db_clip is None:
                return
            db_clip.proxy_path = c.proxy_path
            db_clip.status = c.status
            db_clip.transcript = c.transcript
            db_clip.analysis = c.analysis
            db_clip.error_message = c.error_message
            s.add(db_clip)
            s.commit()

    if lock_path.exists():
        yield _emit("error", message=f"Pipeline already running for project {project_id}")
        return

    lock_path.touch()

    try:
        # ── Stage 1: proxy ────────────────────────────────────────────────────
        yield _emit("proxying", progress=0.05, message=f"Generating proxy for {clip.filename}…")
        proxy = await asyncio.to_thread(generate_proxy, clip, project_id, base_dir)
        clip.proxy_path = str(proxy)
        clip.status = ClipStatus.proxied
        _save_clip(clip)

        # ── Stage 2: transcribe with word timestamps ──────────────────────────
        yield _emit("transcribing", progress=0.25, message="Transcribing audio…")
        transcript = await asyncio.to_thread(
            transcribe_clip_with_words, clip, project_id, base_dir
        )
        clip.transcript = transcript
        clip.status = ClipStatus.transcribed
        _save_clip(clip)

        # ── Stage 3: filler + silence detection ───────────────────────────────
        yield _emit("detecting", progress=0.55, message="Detecting filler words and silence…")

        words = transcript.get("words", [])
        filler_spans = detect_fillers_from_words(words)

        try:
            silence_spans = await asyncio.to_thread(detect_silence, proxy)
        except Exception as exc:
            logger.warning("silence detection failed — continuing without: {}", exc)
            silence_spans = []

        # ── Stage 4: rename suggestions ───────────────────────────────────────
        yield _emit("suggesting", progress=0.80, message="Generating rename suggestions…")

        segments = transcript.get("segments", [])
        transcript_text = " ".join(s["text"] for s in segments).strip()

        client = anthropic.Anthropic(api_key=key_manager.get_key())
        rename_suggestions = await asyncio.to_thread(
            suggest_renames, transcript_text, clip.filename, client
        )

        # ── Persist analysis ──────────────────────────────────────────────────
        analysis = SingleClipAnalysis(
            filler_spans=[
                {"start": f["start"], "end": f["end"], "word": f["word"]}
                for f in filler_spans
            ],
            silence_spans=[{"start": s["start"], "end": s["end"]} for s in silence_spans],
            rename_suggestions=rename_suggestions,
            full_transcript_text=transcript_text,
        )
        clip.analysis = analysis.model_dump()
        clip.status = ClipStatus.sc_ready
        _save_clip(clip)

        yield _emit(
            "done",
            progress=1.0,
            message="Processing complete",
            transcript=segments,
            filler_spans=[{"start": f["start"], "end": f["end"], "word": f["word"]} for f in filler_spans],
            silence_spans=[{"start": s["start"], "end": s["end"]} for s in silence_spans],
            rename_suggestions=rename_suggestions,
        )

    except Exception as exc:
        logger.exception("Single-clip process failed for project {}", project_id)
        yield _emit("error", message=str(exc))
    finally:
        lock_path.unlink(missing_ok=True)


async def _apply_stream(
    project_id: str,
    clip: Clip,
    body: SingleClipApplyRequest,
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
        yield _emit("applying", progress=0.1, message="Applying edits…")

        out_path = await asyncio.to_thread(
            apply_single_clip_edits,
            clip,
            project_id,
            base_dir,
            body.remove_fillers,
            body.remove_silence,
        )

        if body.chosen_filename:
            final_path = out_path.parent / f"{body.chosen_filename}.mp4"
            out_path.rename(final_path)
            out_path = final_path

        logger.info("single-clip apply done → {}", out_path)
        yield _emit("done", progress=1.0, message="Done", output_path=str(out_path))

    except SingleClipNotProcessedError as exc:
        yield _emit("error", message=str(exc))
    except Exception as exc:
        logger.exception("Single-clip apply failed for project {}", project_id)
        yield _emit("error", message=str(exc))
    finally:
        lock_path.unlink(missing_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_single_clip(engine: Any, project_id: str) -> Clip:
    """Fetch the project and verify it has exactly one clip."""
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        clips = list(
            session.exec(select(Clip).where(Clip.project_id == project_id)).all()
        )

    if not clips:
        raise HTTPException(status_code=422, detail="Project has no clips registered")
    if len(clips) > 1:
        raise HTTPException(
            status_code=422,
            detail="Single-clip workflow requires exactly one clip; this project has multiple",
        )
    return clips[0]
