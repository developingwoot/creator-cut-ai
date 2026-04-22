# Edge Cases & Error Handling

How the system should behave in non-happy-path situations.
Each entry names the scenario, the expected behaviour, and the exception or HTTP status used.

---

## Video File Issues

### Unsupported codec (MJPEG, PNG sequence, GIF)

`ffprobe` detects codec during clip registration.
Raise `UnsupportedCodecError` → HTTP 422 with message naming the codec.
The clip is not created in the database.

### Corrupted file (ffprobe fails)

`ffprobe` non-zero exit during registration → `InvalidClipError` → HTTP 422.

### Zero-duration or sub-1-second clip

ffprobe returns `duration_seconds < 1.0`.
Register the clip but set `clip.status = failed` and `error_message = "Clip too short for analysis (< 1s)"`.
Skip in Pass 1; note in Pass 2 that the clip was skipped.

### File deleted between registration and analysis

`clip.original_path` no longer exists when proxy generation starts.
Raise `ClipNotFoundError` → mark clip `failed`, continue pipeline with remaining clips.
If more than half the clips are missing, abort the pipeline with `PipelineError`.

### 4K / high-bitrate file takes too long to proxy

No timeout on proxy generation — FFmpeg will run to completion.
For very large files (> 50 GB) the user may need to wait 10–20 minutes.
Progress is reported via SSE; the frontend shows elapsed time.

---

## Transcription Issues

### Whisper fails (out of memory, model not downloaded, corrupt audio)

Log `TranscriptionError` with details. Continue pipeline with empty transcript.
Pass 1 will analyse frames only — Claude will note that no transcript is available.
Filler detection will be skipped for that clip.

### No speech detected (instrumental clip, b-roll only)

Whisper returns an empty segments list. This is not an error.
The clip's `transcript` field is `{"segments": []}`.
Pass 1 will still analyse frames; it will correctly classify the clip as b-roll.

### Transcript text contains non-ASCII characters

No special handling — Whisper outputs UTF-8; Claude accepts UTF-8. Pass through as-is.

---

## Claude API Issues

### Malformed JSON response

`json.loads` fails on Claude's output → `InvalidClaudeResponseError(raw_response=...)`.
Retry up to 2 times. If still malformed after 3 attempts, mark the clip as `failed`
and continue the pipeline.

Log the raw response at DEBUG level so it can be inspected in development.

### Claude API rate limit or timeout

`anthropic.APIStatusError` / `anthropic.APITimeoutError` → `ClaudeAPIError(attempts=n)`.
Retry with exponential backoff: 2s, 4s, 8s. Give up after 3 attempts.
Mark the affected clip or project as `failed` with the error message.

### Claude returns a segment referencing an unknown clip_id (Pass 2 hallucination)

Validate all `clip_id` values in the returned edit plan against the set of known clip IDs.
If any are unknown: raise `EditPlanValidationError`, retry Pass 2 up to 1 time.
On second failure: return the plan with unknown segments removed and a warning in `reasoning`.

### Edit plan duration wildly off-target (> 3× target)

Log a warning. Do not reject automatically — the user sees the plan and can reject it.
The frontend should visually flag when the planned duration is far from the brief's target.

---

## Pipeline Infrastructure

### Pipeline already running for this project

`pipeline_lock_path` exists when a new analysis or assembly request arrives.
Raise `PipelineLockError(project_id)` → HTTP 409 with message "Analysis already in progress for this project".

### Stale lock file (process crashed without cleanup)

A lock file older than 2 hours is considered stale and is automatically removed at
the start of a new pipeline run.

### Disk space exhaustion

Before starting proxy generation, estimate required space:
`original_file_size × 0.3` per clip (proxy is typically 30% of original).
If `shutil.disk_usage` shows less free space than required, raise `InsufficientDiskSpaceError`
→ HTTP 507 Insufficient Storage.

### Concurrent project runs

Each project has its own lock file. Multiple projects can run concurrently.
The per-process concurrency limit (`settings.max_concurrent`) applies per-project,
not globally — this is acceptable for v1 single-user use.

---

## Path Security

### Path traversal in filename (`../secret.txt`, `%2F`, absolute path)

`assert_safe_filename` in `storage/local.py` checks that the filename:
- Does not contain `/`
- Does not start with `.`
- Does not contain `..`
- Does not contain null bytes

Raises `PathTraversalError` → HTTP 422.

Note: the `register_clips` route validates that the provided path exists and is a file
before probing it. It does not restrict which directories the user can point to — this
is intentional for a local desktop tool where the user controls the filesystem.

---

## Assembly Issues

### A segment's source clip is missing its proxy at assembly time

The proxy should exist because Pass 1 created it. If missing: raise `AssemblyError(segment_order=n)`
with the segment index. Do not skip silently — a missing segment changes the narrative.

### FFmpeg assembly failure (non-zero exit)

Raise `AssemblyError` with the full FFmpeg stderr attached.
Surface to the user with the stderr text so they can diagnose codec/container issues.
The output file (if partially written) is deleted to avoid a corrupted output being found.

### B-roll clip not found at overlay time

The B-roll clip's `original_path` may have been moved by the user.
Check `Path(clip.original_path).exists()` before overlay. If missing: skip that overlay,
log a warning with the clip ID. Do not abort the assembly.

### SFX file missing from manifest

`sfx_id` not found in `assets/sfx/manifest.json` → skip that sound cue, log warning.
Never abort assembly for a missing sound effect.

---

## Frontend / API Issues

### Project creation fails on app launch

`App.jsx` calls `api.createProject()` on mount. If the backend is not running, the API
call fails silently and `projectId` remains `null`.
All subsequent API calls (register clips, start analysis) check `projectId !== null`
before calling — they show an error state "Could not connect to backend. Is the server running?"

### User refreshes the page mid-pipeline

State is not persisted in the browser. On refresh, `App.jsx` creates a new project.
The in-progress project is orphaned in the database (status stays `analyzing`).
This is acceptable for v1. A future improvement would restore state from a URL-encoded project ID.

### SSE connection drops during analysis

The frontend's `EventSource` auto-reconnects. The backend SSE route re-sends the latest
status on reconnect. No state is lost — the pipeline continues regardless of SSE connection.
