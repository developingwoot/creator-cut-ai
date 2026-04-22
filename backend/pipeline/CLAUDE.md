# backend/pipeline/CLAUDE.md — Pipeline Agent Instructions

Read this when working on any pipeline stage. Also read `backend/CLAUDE.md` and
`docs/context/PIPELINE.md` (when it exists).

---

## The Two-Pass Architecture

**Pass 1 — per-clip analysis** (`pass1_clip_analysis.py`)
- Input: proxy video + transcript per clip
- Extracts frames with scene-change detection (FFmpeg `select` filter)
- Sends frames (base64 JPEG) + transcript to Claude
- Output: per-clip `ClipAnalysis` (key moments, quality score, b-roll tags, filler spans)
- Runs concurrently across clips (bounded by `settings.max_concurrent`)
- **Must use prompt caching** on the system prompt — see `docs/context/AI_PROMPTS.md`

**Pass 2 — edit planning** (`pass2_edit_planning.py`)
- Input: all `ClipAnalysis` results + story brief
- Single Claude call with full project context
- Output: ordered `EditPlan` with segments, b-roll placements, sound cues
- **Must use prompt caching** on the system prompt
- Writes the plan to the database; pipeline stops here to await human approval

---

## Absolute Rules for Pipeline Code

1. **Only proxies, never originals**, go into frame extraction and analysis.
   Original paths are stored in the DB but only touched during final assembly.

2. **Never send video bytes to the API.** Only frame JPEGs (base64-encoded) and
   text (transcripts) go to Claude. This is both a cost and a privacy constraint.

3. **FFmpeg errors must never silently fail.** Wrap every `ffmpeg-python` call in
   try/except and include `stderr` in the raised exception. Use `FFmpegError`.

4. **Prompt caching is not optional.** Pass 1 and filler detection have repeated
   system prompts across many clips. Without caching, the unit economics don't work.
   See `AI_PROMPTS.md` for the cache breakpoint placement.

5. **Pipeline lock.** Acquire `pipeline_lock_path` before starting and release on
   completion or error. Raise `PipelineLockError` if already locked.

6. **Each stage must be independently testable.** Every pipeline module must
   accept a `project_id` and derive all paths from `storage/local.py` functions.
   No global state, no hardcoded paths.

---

## Frame Extraction Strategy

Use FFmpeg scene change detection (`select='gt(scene,0.3)'`) to pick semantically
distinct frames rather than sampling at a fixed interval. Then cap at N frames per
clip to bound the token cost.

Recommended defaults:
- Scene change threshold: `0.3`
- Max frames per clip: `12`
- Frame resolution: `1280x720` (proxy resolution, not 4K)
- Format: JPEG at quality 85

---

## Whisper Transcription (`whisper_transcribe.py`)

- Use `faster-whisper` (CTranslate2 backend — runs locally, no API cost)
- Model size from `settings.whisper_model` (default `medium`)
- Transcribe from proxy path (not original)
- Output: list of `{start, end, text}` segments saved to `transcript_path()`
- Non-fatal: if transcription fails, log `TranscriptionError` and continue with
  empty transcript — Claude will still analyse frames

---

## Claude API Usage Pattern

```python
import anthropic
from config import key_manager

client = anthropic.Anthropic(api_key=key_manager.get_key())

response = client.messages.create(
    model="claude-opus-4-7",  # or claude-sonnet-4-6 for Pass 1
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # cache the system prompt
        }
    ],
    messages=[{"role": "user", "content": user_content}],
)
```

Parse the response as JSON via `json.loads(response.content[0].text)`.
If parsing fails, raise `InvalidClaudeResponseError` with `raw_response=response.content[0].text`.
Retry up to 2 times on `InvalidClaudeResponseError` before giving up.

---

## Exception Usage in Pipeline

| Situation | Exception |
|---|---|
| FFmpeg non-zero exit | `FFmpegError(message, stderr=stderr)` |
| Proxy generation failed | `ProxyGenerationError` (subclass of `PipelineError`) |
| Frame extraction failed | `FrameExtractionError` |
| Whisper failed | `TranscriptionError` (non-fatal — log and continue) |
| Claude returned bad JSON | `InvalidClaudeResponseError(raw_response=...)` |
| Claude API error | `ClaudeAPIError(attempts=n)` |
| Pipeline already running | `PipelineLockError(project_id)` |
| Assembly segment failed | `AssemblyError(segment_order=n)` |

Never raise bare `Exception` or `PipelineError` directly — always a specific subclass.

---

## Concurrency

Pass 1 runs clips concurrently using `asyncio.gather` with a semaphore:

```python
sem = asyncio.Semaphore(settings.max_concurrent)

async def analyse_one(clip):
    async with sem:
        return await asyncio.to_thread(run_clip_analysis, clip)

results = await asyncio.gather(*[analyse_one(c) for c in clips])
```

CPU-bound pipeline tasks (FFmpeg, Whisper) must run in a thread pool via
`asyncio.to_thread`, never blocking the event loop.
