from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import anthropic
import ffmpeg
from loguru import logger
from pydantic import ValidationError

from config import key_manager, settings
from exceptions import ClaudeAPIError, FrameExtractionError, InvalidClaudeResponseError
from models.clip import Clip, ClipAnalysis, ClipStatus
from pipeline.prompts import PASS1_SYSTEM_PROMPT
from storage.local import ensure_project_dirs, frames_subdir

_MODEL = "claude-sonnet-4-6"
_MAX_FRAMES = 12
_SCENE_THRESHOLD = 0.3
_MAX_RETRIES = 2


# ── Frame extraction ──────────────────────────────────────────────────────────


def extract_frames(
    proxy: Path,
    out_dir: Path,
    max_frames: int = _MAX_FRAMES,
    scene_threshold: float = _SCENE_THRESHOLD,
) -> list[Path]:
    """Extract up to max_frames JPEG frames from proxy using scene-change detection.

    Falls back to uniform sampling if scene detection yields no frames.
    Returns a sorted list of frame paths (at most max_frames).

    Raises FrameExtractionError (with FFmpeg stderr) on failure.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    scene_frames = _extract_scene_frames(proxy, out_dir, scene_threshold)

    if not scene_frames:
        logger.debug("no scene-change frames found for {}, falling back to uniform sampling", proxy.name)
        scene_frames = _extract_uniform_frames(proxy, out_dir, max_frames)

    return _downsample(scene_frames, max_frames)


def _extract_scene_frames(proxy: Path, out_dir: Path, threshold: float) -> list[Path]:
    pattern = str(out_dir / "scene_%04d.jpg")
    try:
        (
            ffmpeg
            .input(str(proxy))
            .output(
                pattern,
                vf=f"select='gt(scene,{threshold})'",
                vsync="vfr",
                **{"q:v": 3},
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise FrameExtractionError(
            f"FFmpeg scene detection failed for {proxy.name}",
            stderr=stderr,
        ) from exc
    return sorted(out_dir.glob("scene_*.jpg"))


def _extract_uniform_frames(proxy: Path, out_dir: Path, max_frames: int) -> list[Path]:
    pattern = str(out_dir / "uniform_%04d.jpg")
    try:
        (
            ffmpeg
            .input(str(proxy))
            .output(
                pattern,
                vf="fps=0.5",
                **{"frames:v": max_frames, "q:v": 3},
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise FrameExtractionError(
            f"FFmpeg uniform sampling failed for {proxy.name}",
            stderr=stderr,
        ) from exc
    return sorted(out_dir.glob("uniform_*.jpg"))


def _downsample(frames: list[Path], max_frames: int) -> list[Path]:
    if len(frames) <= max_frames:
        return frames
    step = (len(frames) - 1) / (max_frames - 1)
    indices = {round(i * step) for i in range(max_frames)}
    return [frames[i] for i in sorted(indices)]


# ── Claude interaction ────────────────────────────────────────────────────────


def _transcript_text(transcript: dict[str, Any] | None) -> str:
    if not transcript or not transcript.get("segments"):
        return "(no transcript available)"
    return " ".join(seg["text"].strip() for seg in transcript["segments"] if seg.get("text"))


def _build_user_content(
    frame_paths: list[Path],
    transcript: dict[str, Any] | None,
    duration_seconds: float | None,
) -> list[dict]:
    duration = duration_seconds or 0.0
    text_block: dict = {
        "type": "text",
        "text": (
            f"Clip duration: {duration:.1f} seconds\n"
            f"Transcript:\n{_transcript_text(transcript)}\n\n"
            f"Frames from this clip ({len(frame_paths)} frames, extracted at scene changes):"
        ),
    }
    image_blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(p.read_bytes()).decode(),
            },
        }
        for p in frame_paths
    ]
    return [text_block, *image_blocks]


def _call_claude_with_retry(
    client: anthropic.Anthropic,
    user_content: list[dict],
    clip_id: str,
) -> ClipAnalysis:
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": PASS1_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text
            data = json.loads(raw)
            return ClipAnalysis.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("clip {} attempt {}: bad Claude response — {}", clip_id, attempt, exc)
            last_exc = InvalidClaudeResponseError(
                f"Claude returned invalid JSON/schema for clip {clip_id} (attempt {attempt})",
                raw_response=locals().get("raw"),
                attempts=attempt,
                clip_id=clip_id,
            )
        except anthropic.APIError as exc:
            logger.warning("clip {} attempt {}: Anthropic API error — {}", clip_id, attempt, exc)
            last_exc = ClaudeAPIError(
                f"Anthropic API error for clip {clip_id} (attempt {attempt}): {exc}",
                attempts=attempt,
                clip_id=clip_id,
            )

    raise last_exc  # type: ignore[misc]


# ── Public API ────────────────────────────────────────────────────────────────


def analyse_clip(
    clip: Clip,
    project_id: str,
    base_dir: Path,
    client: anthropic.Anthropic | None = None,
) -> ClipAnalysis:
    """Run Pass 1 analysis for a single clip.

    Extracts frames from clip.proxy_path, calls Claude, validates the response.
    Updates clip.status in-place. The caller is responsible for persisting the clip.

    Raises InvalidClaudeResponseError or ClaudeAPIError after exhausting retries.
    Raises FrameExtractionError if FFmpeg frame extraction fails.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=key_manager.get_key())

    ensure_project_dirs(base_dir, project_id)
    out_dir = frames_subdir(base_dir, project_id, clip.id)

    clip.status = ClipStatus.analyzing
    logger.info("pass1: analysing clip {}", clip.id)

    proxy = Path(clip.proxy_path) if clip.proxy_path else None
    if proxy is None or not proxy.exists():
        raise FrameExtractionError(
            f"Proxy not found for clip {clip.id} — run ingest first",
            clip_id=clip.id,
        )

    frame_paths = extract_frames(proxy, out_dir)
    if not frame_paths:
        raise FrameExtractionError(
            f"Frame extraction yielded no frames for clip {clip.id}",
            clip_id=clip.id,
        )

    user_content = _build_user_content(frame_paths, clip.transcript, clip.duration_seconds)
    analysis = _call_claude_with_retry(client, user_content, clip.id)

    clip.status = ClipStatus.analyzed
    logger.info("pass1: clip {} done — quality={:.2f}", clip.id, analysis.quality_score)
    return analysis


async def run_pass1(
    clips: list[Clip],
    project_id: str,
    base_dir: Path,
    client: anthropic.Anthropic | None = None,
) -> list[tuple[Clip, ClipAnalysis | None]]:
    """Analyse all clips concurrently, bounded by settings.max_concurrent.

    Returns a list of (clip, analysis) pairs.
    On per-clip failure the clip status is set to failed, analysis is None, and
    processing continues for the remaining clips.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=key_manager.get_key())

    sem = asyncio.Semaphore(settings.max_concurrent)
    results: list[tuple[Clip, ClipAnalysis | None]] = []

    async def _analyse_one(clip: Clip) -> tuple[Clip, ClipAnalysis | None]:
        async with sem:
            try:
                analysis = await asyncio.to_thread(
                    analyse_clip, clip, project_id, base_dir, client
                )
                return clip, analysis
            except Exception as exc:
                logger.error("pass1: clip {} failed — {}", clip.id, exc)
                clip.status = ClipStatus.failed
                clip.error_message = str(exc)
                return clip, None

    pairs = await asyncio.gather(*[_analyse_one(c) for c in clips])
    results.extend(pairs)
    return results
