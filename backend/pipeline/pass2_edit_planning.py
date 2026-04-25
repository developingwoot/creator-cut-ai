from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

import anthropic

from config import key_manager, settings
from exceptions import (
    ClaudeAPIError,
    InvalidClaudeResponseError,
    InvalidOllamaResponseError,
    OllamaUnreachableError,
    PipelineError,
)
from models.clip import Clip, ClipAnalysis
from models.edit_plan import EditPlan, EditPlanStatus, EditSegment
from models.project import StoryBrief
from pipeline import ollama_client
from pipeline.prompts import PASS2_CRITIQUE_PROMPT, PASS2_SYSTEM_PROMPT

_MAX_RETRIES = 2
_SFX_MANIFEST = Path(__file__).resolve().parent.parent.parent / "assets" / "sfx" / "manifest.json"


# ── Context builders ──────────────────────────────────────────────────────────


def _load_sfx_ids() -> list[str]:
    try:
        manifest = json.loads(_SFX_MANIFEST.read_text())
        return [s["filename"] for s in manifest.get("sounds", [])]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("pass2: SFX manifest unreadable ({}), no SFX options sent", exc)
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
            f'"{rejection_feedback}"\n\nPlease revise the plan taking this feedback into account.'
        )

    return (
        f"Story Brief:\n"
        f"Title: {brief.title}\n"
        f"Summary: {brief.story_summary}\n"
        f"Target duration: {brief.target_duration_seconds}s ({minutes}m {seconds}s)\n"
        f"Tone: {brief.tone}\n"
        f"Key moments to include: {', '.join(brief.key_moments) or 'None specified'}\n"
        f"B-roll preferences: {', '.join(brief.b_roll_preferences) or 'None specified'}\n"
        f"\nAvailable SFX IDs:\n{sfx_block}\n"
        f"\nClip analyses:\n{_build_clip_analyses_json(clip_analyses)}"
        f"{rejection_block}"
    )


# ── Ollama interaction ────────────────────────────────────────────────────────


def _parse_plan_response(raw: str) -> tuple[list[dict], float, str]:
    data = json.loads(raw)
    segments_raw = data.get("segments")
    if not isinstance(segments_raw, list):
        raise ValueError("'segments' must be a list")
    segments = [EditSegment.model_validate(seg).model_dump() for seg in segments_raw]
    total_duration = float(data.get("total_duration_seconds", 0.0))
    reasoning = str(data.get("reasoning", ""))
    return segments, total_duration, reasoning


async def _call_anthropic_with_retry(
    user_message: str,
    project_id: str,
) -> tuple[list[dict], float, str]:
    """Cloud-fallback path: call Anthropic Opus with cached system prompt."""
    import json as _json
    from pydantic import ValidationError as _VE

    client = anthropic.Anthropic(api_key=key_manager.get_key())
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=[{"type": "text", "text": PASS2_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text
            return _parse_plan_response(raw)
        except (_json.JSONDecodeError, _VE, ValueError) as exc:
            logger.warning("pass2 cloud attempt {}: bad response — {}", attempt, exc)
            last_exc = InvalidClaudeResponseError(
                f"Cloud edit plan invalid (attempt {attempt}): {exc}",
                raw_response=locals().get("raw"),
                attempts=attempt,
                stage="pass2",
            )
        except anthropic.APIError as exc:
            logger.warning("pass2 cloud attempt {}: API error — {}", attempt, exc)
            last_exc = ClaudeAPIError(
                f"Anthropic error during pass2 (attempt {attempt}): {exc}",
                attempts=attempt,
                stage="pass2",
            )
    raise last_exc  # type: ignore[misc]


async def _call_ollama_with_retry(
    prompt: str,
    project_id: str,
    label: str = "pass2",
) -> tuple[list[dict], float, str]:
    """Call Ollama director LLM; retry up to _MAX_RETRIES on bad JSON/schema."""
    model = settings.ollama_llm_model
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            raw = await ollama_client.generate(
                model=model,
                prompt=f"{PASS2_SYSTEM_PROMPT}\n\n{prompt}",
                fmt="json",
            )
            return _parse_plan_response(raw)
        except OllamaUnreachableError:
            raise
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("{} attempt {}: bad Ollama response — {}", label, attempt, exc)
            last_exc = InvalidOllamaResponseError(
                f"Ollama returned invalid edit plan (attempt {attempt}): {exc}",
                raw_response=locals().get("raw"),
                stage="pass2",
            )
        except Exception as exc:
            logger.warning("{} attempt {}: Ollama error — {}", label, attempt, exc)
            last_exc = InvalidOllamaResponseError(
                f"Ollama error during {label} (attempt {attempt}): {exc}",
                stage="pass2",
            )

    raise last_exc  # type: ignore[misc]


async def _self_critique(
    draft_segments: list[dict],
    draft_duration: float,
    draft_reasoning: str,
    user_message: str,
    project_id: str,
) -> tuple[list[dict], float, str]:
    """Ask the LLM to review its own draft and return corrected output if needed."""
    model = settings.ollama_llm_model
    draft_json = json.dumps({
        "segments": draft_segments,
        "total_duration_seconds": draft_duration,
        "reasoning": draft_reasoning,
    }, indent=2)
    critique_prompt = (
        f"Original brief and clip data:\n{user_message}\n\n"
        f"Draft edit plan:\n{draft_json}\n\n"
        f"{PASS2_CRITIQUE_PROMPT}"
    )
    try:
        raw = await ollama_client.generate(model=model, prompt=critique_prompt, fmt="json")
        revised_segments, revised_duration, revised_reasoning = _parse_plan_response(raw)
        logger.info("pass2: self-critique completed — {} segments", len(revised_segments))
        return revised_segments, revised_duration, revised_reasoning
    except Exception as exc:
        # Self-critique is best-effort — fall back to the draft on failure
        logger.warning("pass2: self-critique failed ({}), using draft plan", exc)
        return draft_segments, draft_duration, draft_reasoning


# ── Public API ────────────────────────────────────────────────────────────────


async def run_pass2(
    clip_analyses: list[tuple[Clip, ClipAnalysis]],
    brief: StoryBrief,
    project_id: str,
    base_dir: Path,  # noqa: ARG001 — reserved for future lock/output path use
    rejection_feedback: str | None = None,
) -> EditPlan:
    """Run Pass 2 edit planning via local Ollama LLM + one self-critique pass.

    Accepts only successful clip analyses (caller pre-filters).
    Returns an EditPlan with status=draft. Caller persists it.

    Raises PipelineError if clip_analyses is empty.
    Raises InvalidOllamaResponseError after retries exhausted.
    """
    if not clip_analyses:
        raise PipelineError(
            "pass2 requires at least one successful clip analysis",
            stage="pass2",
        )

    logger.info("pass2: planning edit for project {} ({} clips)", project_id, len(clip_analyses))

    sfx_ids = _load_sfx_ids()
    user_message = _build_user_message(brief, clip_analyses, sfx_ids, rejection_feedback)

    if settings.cloud_fallback:
        logger.debug("pass2: using cloud fallback for project {}", project_id)
        segments, total_duration, reasoning = await _call_anthropic_with_retry(user_message, project_id)
    else:
        # Draft pass + self-critique
        segments, total_duration, reasoning = await _call_ollama_with_retry(user_message, project_id)
        segments, total_duration, reasoning = await _self_critique(
            segments, total_duration, reasoning, user_message, project_id
        )

    plan = EditPlan(
        project_id=project_id,
        status=EditPlanStatus.draft,
        segments=segments,
        total_duration_seconds=total_duration,
        reasoning=reasoning,
    )

    logger.info("pass2: edit plan created — {} segments, {:.0f}s total", len(segments), total_duration)
    return plan
