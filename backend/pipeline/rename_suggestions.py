from __future__ import annotations

import json

import anthropic as _anthropic
from loguru import logger

from config import key_manager, settings
from pipeline import ollama_client

_PROMPT_TEMPLATE = """\
You are a YouTube video editor helping a creator name their video clip.
Given the transcript, suggest 3 concise, descriptive filenames (without extension).
Good names are specific, search-optimized, and under 60 characters each.

Return ONLY valid JSON — no markdown, no explanation:
{{"suggestions": ["<name 1>", "<name 2>", "<name 3>"]}}

Clip filename: {clip_filename}

Transcript:
{transcript_text}
"""


async def suggest_renames(
    transcript_text: str,
    clip_filename: str,
) -> list[str]:
    """Call local Ollama LLM to generate 3 rename suggestions for a clip.

    Returns a list of 3 strings (no file extension).
    Degrades gracefully — returns [clip_filename]*3 if the call fails or
    the response cannot be parsed after 2 attempts.
    """
    if not transcript_text.strip():
        logger.warning("empty transcript for '{}' — skipping rename suggestions", clip_filename)
        return [clip_filename, clip_filename, clip_filename]

    if settings.cloud_fallback:
        return await _suggest_renames_anthropic(transcript_text, clip_filename)
    return await _suggest_renames_ollama(transcript_text, clip_filename)


async def _suggest_renames_ollama(transcript_text: str, clip_filename: str) -> list[str]:
    prompt = _PROMPT_TEMPLATE.format(clip_filename=clip_filename, transcript_text=transcript_text)
    model = settings.ollama_llm_model
    for attempt in range(1, 3):
        try:
            raw = await ollama_client.generate(model=model, prompt=prompt, fmt="json")
            data = json.loads(raw.strip())
            suggestions = data["suggestions"]
            if isinstance(suggestions, list) and len(suggestions) == 3:
                return [str(s) for s in suggestions]
            raise ValueError("suggestions field malformed or wrong length")
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("rename ollama attempt {}/2 failed for '{}': {}", attempt, clip_filename, exc)
        except Exception as exc:
            logger.warning("rename ollama error attempt {}/2 for '{}': {}", attempt, clip_filename, exc)
    logger.warning("rename suggestions exhausted retries for '{}' — using filename", clip_filename)
    return [clip_filename, clip_filename, clip_filename]


async def _suggest_renames_anthropic(transcript_text: str, clip_filename: str) -> list[str]:
    _SYSTEM = (
        "You are a YouTube video editor. Suggest 3 concise descriptive filenames (no extension, under 60 chars).\n"
        "Return ONLY valid JSON: {\"suggestions\": [\"<name 1>\", \"<name 2>\", \"<name 3>\"]}"
    )
    client = _anthropic.Anthropic(api_key=key_manager.get_key())
    user = f"Clip filename: {clip_filename}\n\nTranscript:\n{transcript_text}"
    for attempt in range(1, 3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)
            suggestions = data["suggestions"]
            if isinstance(suggestions, list) and len(suggestions) == 3:
                return [str(s) for s in suggestions]
            raise ValueError("malformed")
        except Exception as exc:
            logger.warning("rename cloud attempt {}/2 failed for '{}': {}", attempt, clip_filename, exc)
    return [clip_filename, clip_filename, clip_filename]
