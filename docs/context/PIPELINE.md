# Pipeline

The pipeline is the core of CreatorCutAI. It transforms raw clips into a near-finished
edit in five stages. Stages 1–2 run concurrently across clips; stage 3 is a single call;
stages 4–5 are sequential post-processing.

---

## Stage Overview

```
Clips registered
    │
    ▼
[Stage 1] Ingest
    ├─ proxy.py           — FFmpeg: original → 1280×720 proxy
    └─ whisper_transcribe.py — local Whisper: proxy audio → transcript JSON

    │ (all clips concurrently, bounded by settings.max_concurrent)
    ▼
[Stage 2] Pass 1 — Per-clip Analysis
    pass1_clip_analysis.py
    ├─ FFmpeg scene-change detection → JPEG frames
    └─ Claude: frames + transcript → ClipAnalysis (key_moments, filler_spans, etc.)

    │ (all clips must complete before Pass 2 starts)
    ▼
[Stage 3] Pass 2 — Edit Planning
    pass2_edit_planning.py
    └─ Claude: all ClipAnalysis + StoryBrief → EditPlan (ordered segments)

    │
    ▼
[HUMAN REVIEW GATE — pipeline pauses here]
    User approves or rejects with optional feedback.
    Rejection re-runs Pass 2 with feedback injected as context.

    │
    ▼
[Stage 4] Post-processing (sequential, in assembly order)
    ├─ filler_removal.py  — trim filler_spans from each segment
    ├─ broll_overlay.py   — splice B-roll overlays over A-roll
    └─ sound_design.py    — mix SFX from local library

    │
    ▼
[Stage 5] Assembly
    assembly.py           — FFmpeg: render final MP4 from edit plan
```

---

## Stage 1: Ingest

### Proxy Generation (`pipeline/proxy.py`)

Input: `clip.original_path` (user's original file, never modified)
Output: `proxies/{clip_id}.mp4`

FFmpeg transcode parameters:
- Resolution: `scale=1280:720` (preserve AR with `force_original_aspect_ratio=decrease`)
- Codec: `libx264` with `crf=23`, `preset=fast`
- Audio: `aac`, `128k`
- Container: `.mp4`

Raises `ProxyGenerationError` (with FFmpeg stderr) if the transcode fails.
Updates `clip.proxy_path` and `clip.status = ClipStatus.proxying → proxied`.

### Transcription (`pipeline/whisper_transcribe.py`)

Input: `clip.proxy_path`
Output: `transcripts/{clip_id}.json` — `{"segments": [{"start": 0.0, "end": 2.1, "text": "..."}]}`

Uses `faster-whisper` with `settings.whisper_model` (default: `"medium"`).
Model size trades speed for accuracy: `tiny` is ~8× faster than `large-v2` but misses
filler words more often — `medium` is the right default for filler detection.

Non-fatal: if transcription fails, logs `TranscriptionError` and continues with an empty
transcript. Claude will still analyse frames; filler detection will be skipped for that clip.

Updates `clip.transcript` in the database.

---

## Stage 2: Pass 1 — Per-clip Analysis (`pipeline/pass1_clip_analysis.py`)

Runs once per clip, concurrently across all clips.

### Frame Extraction

Uses FFmpeg `select` filter with scene-change detection (`gt(scene,0.3)`) to pick
frames at semantic boundaries rather than fixed intervals. This reduces tokens sent to
Claude by ~80% compared to uniform sampling, with no quality loss for analysis.

Parameters:
- Scene change threshold: `0.3`
- Max frames per clip: `12` (cap to bound token cost on long clips)
- Frame resolution: proxy resolution (1280×720) — already downscaled
- Format: JPEG, quality 85
- Output: `frames/{clip_id}/frame_{n:04d}.jpg`

### Claude Call

Sends frames (base64-encoded JPEG) and transcript text to Claude claude-sonnet-4-6.
System prompt is cached (see `AI_PROMPTS.md`).

Input to Claude:
- System: clip analysis instructions (cached)
- User: N frames as `image` content blocks + transcript as text

Output: JSON conforming to the `ClipAnalysis` schema (see `DATA_MODELS.md`).

If Claude returns malformed JSON: raise `InvalidClaudeResponseError`, retry up to 2 times,
then mark the clip as `failed` and continue with remaining clips.

Updates `clip.analysis` and `clip.status = ClipStatus.analyzed`.

---

## Stage 3: Pass 2 — Edit Planning (`pipeline/pass2_edit_planning.py`)

Single call. Waits for all Pass 1 analyses to complete.

### Input to Claude

- System: edit planning instructions (cached, see `AI_PROMPTS.md`)
- User:
  - `StoryBrief` (title, summary, target duration, tone, key moments, B-roll preferences)
  - All `ClipAnalysis` results, keyed by `clip_id`
  - Total available footage duration
  - Optional: prior rejection feedback (if this is a re-run)

### Output

JSON conforming to the `EditPlan` schema:
```json
{
  "segments": [...],
  "total_duration_seconds": 487.3,
  "reasoning": "..."
}
```

Writes to `edit_plans` table with `status = EditPlanStatus.draft`.
**Pipeline stops here.** The route returns the plan; the frontend shows it for review.

### Re-runs

If the user rejects the plan with feedback, the route calls `pass2` again with the
feedback appended to the user message. The old draft plan is replaced in the database.

---

## Stage 4: Post-processing

Each module takes the approved `EditPlan` and operates on the clip proxies.
All output is written to a staging area in `outputs/` before assembly.

### Filler Removal (`pipeline/filler_removal.py`)

For each segment in the plan, removes the `filler_spans` identified in Pass 1.
Uses FFmpeg `select` filter + `asetpts`/`setpts` to cut and rejoin without re-encoding.
Frame-accurate: cuts to the exact millisecond of each span boundary.

A filler span is only removed if it falls within the segment's `source_start`–`source_end`
window. Spans that overlap boundaries are truncated.

### B-roll Overlay (`pipeline/broll_overlay.py`)

Inserts B-roll clips at the timecodes specified in each segment's `b_roll_overlays`.
The B-roll clip plays over the A-roll audio (or both audio streams can be mixed — TBD).
Uses FFmpeg `overlay` filter with `enable` expression for time-bounded overlays.

B-roll clips are sourced from `clip.original_path` (the user's own footage, registered
as clips with `is_broll=True`). They are transcoded to proxy resolution before overlay.

### Sound Design (`pipeline/sound_design.py`)

Mixes SFX from `assets/sfx/` at the timecodes specified in each segment's `sound_cues`.
Uses the `sfx_id` to look up the file path from `assets/sfx/manifest.json`.
Mixing is done with FFmpeg `amix` filter, respecting `volume` (0.0–1.0) per cue.

SFX playback is non-fatal: a missing `sfx_id` logs a warning and continues.

---

## Stage 5: Assembly (`pipeline/assembly.py`)

Takes the post-processed segments and renders a single output MP4.

Uses FFmpeg concat demuxer (via a generated `concat.txt` list) to join segments.
Applies fade transitions if specified in the edit plan (TBD for v1).

Output: `outputs/{project_id}.mp4`
Updates `project.status = ProjectStatus.complete`.

---

## Pipeline Lock

Before starting analysis or assembly, `pipeline_lock_path(base_dir, project_id)` is
created as a lock file. If a second request comes in while the lock exists, the route
raises `PipelineLockError` → HTTP 409.

The lock is released (file deleted) on completion or on any unhandled exception.

---

## Progress Reporting

The analysis and assembly routes emit Server-Sent Events (SSE) so the frontend can
display live progress. Events have the shape:

```json
{"stage": "proxying", "clip_id": "uuid", "progress": 0.45, "message": "Generating proxy for clip 2/5"}
```

The frontend subscribes via `api.progressStream(projectId)`.
