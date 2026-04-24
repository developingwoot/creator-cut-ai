from __future__ import annotations

import json

import anthropic
from loguru import logger

from exceptions import InvalidClaudeResponseError

_SYSTEM_PROMPT = """\
You are a YouTube video editor helping a creator name their video clip.
Given a full transcript, suggest 3 concise, descriptive filenames (without extension).
Good names are specific, search-optimized, and under 60 characters.

Return ONLY valid JSON — no markdown, no explanation:
{"suggestions": ["<name 1>", "<name 2>", "<name 3>"]}\
"""


def suggest_renames(
    transcript_text: str,
    clip_filename: str,
    client: anthropic.Anthropic,
) -> list[str]:
    """Call Claude Sonnet to generate 3 rename suggestions for a clip.

    Returns a list of 3 strings (no file extension).
    Degrades gracefully — returns [clip_filename, clip_filename, clip_filename]
    if the API call fails or the response cannot be parsed after 2 attempts.
    """
    if not transcript_text.strip():
        logger.warning("empty transcript for '{}' — skipping rename suggestions", clip_filename)
        return [clip_filename, clip_filename, clip_filename]

    user_message = f"Clip filename: {clip_filename}\n\nTranscript:\n{transcript_text}"

    for attempt in range(1, 3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)
            suggestions = data["suggestions"]
            if isinstance(suggestions, list) and len(suggestions) == 3:
                return [str(s) for s in suggestions]
            raise InvalidClaudeResponseError(
                "suggestions field malformed", raw_response=raw
            )
        except (json.JSONDecodeError, KeyError, InvalidClaudeResponseError) as exc:
            logger.warning(
                "rename suggestion attempt {}/2 failed for '{}': {}",
                attempt, clip_filename, exc,
            )
        except Exception as exc:
            logger.warning(
                "rename suggestion API error attempt {}/2 for '{}': {}",
                attempt, clip_filename, exc,
            )

    logger.warning("rename suggestions exhausted retries for '{}' — using filename", clip_filename)
    return [clip_filename, clip_filename, clip_filename]
