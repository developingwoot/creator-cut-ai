from __future__ import annotations

import json
from pathlib import Path

import anthropic
from loguru import logger
from pydantic import ValidationError

from config import key_manager
from exceptions import ClaudeAPIError, InvalidClaudeResponseError, PipelineError
from models.clip import Clip, ClipAnalysis
from models.edit_plan import EditPlan, EditPlanStatus, EditSegment
from models.project import StoryBrief
from pipeline.prompts import PASS2_SYSTEM_PROMPT

_MODEL = "claude-opus-4-7"
_MAX_RETRIES = 2
_SFX_MANIFEST = Path(__file__).resolve().parent.parent.parent / "assets" / "sfx" / "manifest.json"


# ── Context builders ──────────────────────────────────────────────────────────


def _load_sfx_ids() -> list[str]:
    try:
        manifest = json.loads(_SFX_MANIFEST.read_text())
        return [s["filename"] for s in manifest.get("sounds", [])]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("pass2: SFX manifest unreadable ({}), Claude will receive no SFX options", exc)
        return []


def _build_clip_analyses_json(clip_analyses: list[tuple[Clip, ClipAnalysis]]) -> str:
    data = {
        clip.id: {
            "filename": clip.filename,
            "duration_seconds": clip.duration_seconds,
            **analysis.model_dump(),
        }
        for clip, analysis in clip_analyses
    }
    return json.dumps(data, indent=2)


def _build_user_message(
    brief: StoryBrief,
    clip_analyses: list[tuple[Clip, ClipAnalysis]],
    sfx_ids: list[str],
    rejection_feedback: str | None,
) -> str:
    sfx_block = "\n".join(f"- {s}" for s in sfx_ids) if sfx_ids else "(none available)"

    minutes = brief.target_duration_seconds // 60
    seconds = brief.target_duration_seconds % 60

    rejection_block = ""
    if rejection_feedback:
        rejection_block = (
            f'\nPrevious edit plan was rejected. Editor\'s feedback:\n'
            f'"{rejection_feedback}"\n\n'
            f"Please revise the plan taking this feedback into account."
        )

    return (
        f"Story Brief:\n"
        f"Title: {brief.title}\n"
        f"Summary: {brief.story_summary}\n"
        f"Target duration: {brief.target_duration_seconds}s ({minutes}m {seconds}s)\n"
        f"Tone: {brief.tone}\n"
        f"Key moments to include: {', '.join(brief.key_moments) or 'None specified'}\n"
        f"B-roll preferences: {', '.join(brief.b_roll_preferences) or 'None specified'}\n"
        f"\nAvailable SFX IDs (from local library):\n{sfx_block}\n"
        f"\nClip analyses:\n{_build_clip_analyses_json(clip_analyses)}"
        f"{rejection_block}"
    )


# ── Claude interaction ────────────────────────────────────────────────────────


def _parse_plan_response(raw: str) -> tuple[list[dict], float, str]:
    data = json.loads(raw)

    segments_raw = data.get("segments")
    if not isinstance(segments_raw, list):
        raise ValueError("'segments' must be a list")

    segments = [EditSegment.model_validate(seg).model_dump() for seg in segments_raw]
    total_duration = float(data.get("total_duration_seconds", 0.0))
    reasoning = str(data.get("reasoning", ""))
    return segments, total_duration, reasoning


def _call_claude(
    client: anthropic.Anthropic,
    user_message: str,
    project_id: str,
) -> tuple[list[dict], float, str]:
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            response = client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": PASS2_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text
            return _parse_plan_response(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("pass2 attempt {}: bad Claude response — {}", attempt, exc)
            last_exc = InvalidClaudeResponseError(
                f"Claude returned invalid edit plan (attempt {attempt}): {exc}",
                raw_response=locals().get("raw"),
                attempts=attempt,
                stage="pass2",
            )
        except anthropic.APIError as exc:
            logger.warning("pass2 attempt {}: Anthropic API error — {}", attempt, exc)
            last_exc = ClaudeAPIError(
                f"Anthropic API error during pass2 (attempt {attempt}): {exc}",
                attempts=attempt,
                stage="pass2",
            )

    raise last_exc  # type: ignore[misc]


# ── Public API ────────────────────────────────────────────────────────────────


def run_pass2(
    clip_analyses: list[tuple[Clip, ClipAnalysis]],
    brief: StoryBrief,
    project_id: str,
    base_dir: Path,  # noqa: ARG001 — reserved for future lock/output path use
    client: anthropic.Anthropic | None = None,
    rejection_feedback: str | None = None,
) -> EditPlan:
    """Run Pass 2 edit planning — single Claude Opus call.

    Accepts only successful clip analyses (caller pre-filters).
    Returns an EditPlan with status=draft. Caller is responsible for persisting it.

    Raises PipelineError if clip_analyses is empty.
    Raises InvalidClaudeResponseError or ClaudeAPIError after retries exhausted.
    """
    if not clip_analyses:
        raise PipelineError(
            "pass2 requires at least one successful clip analysis",
            stage="pass2",
        )

    if client is None:
        client = anthropic.Anthropic(api_key=key_manager.get_key())

    logger.info("pass2: planning edit for project {} ({} clips)", project_id, len(clip_analyses))

    sfx_ids = _load_sfx_ids()
    user_message = _build_user_message(brief, clip_analyses, sfx_ids, rejection_feedback)

    segments, total_duration, reasoning = _call_claude(client, user_message, project_id)

    plan = EditPlan(
        project_id=project_id,
        status=EditPlanStatus.draft,
        segments=segments,
        total_duration_seconds=total_duration,
        reasoning=reasoning,
    )

    logger.info(
        "pass2: edit plan created — {} segments, {:.0f}s total",
        len(segments),
        total_duration,
    )
    return plan
