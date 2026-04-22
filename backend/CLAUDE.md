# backend/CLAUDE.md — Backend Agent Instructions

Read this file when working on any backend code. It supplements the root `CLAUDE.md`.

---

## Settings (`config.py`)

`Settings` is a `pydantic-settings` `BaseSettings` class with `env_prefix="CREATORCUT_"`.

| Field | Env var | Default |
|---|---|---|
| `base_dir` | `CREATORCUT_BASE_DIR` | `~/.creatorcut` |
| `port` | `CREATORCUT_PORT` | `8000` |
| `whisper_model` | `CREATORCUT_WHISPER_MODEL` | `medium` |
| `max_concurrent` | `CREATORCUT_MAX_CONCURRENT` | `5` |
| `log_level` | `LOG_LEVEL` | `INFO` |

The singleton instances `settings` and `key_manager` are exported at module level from `config.py`.
Route and pipeline code must import them: `from config import settings, key_manager`.
Never access `os.environ` directly for any of these values.

---

## KeyManager (`config.py`)

Resolves the Anthropic API key in this order:

1. `ANTHROPIC_API_KEY` environment variable
2. OS keychain — service `"creatorcut-ai"`, username `"api-key"` (macOS `security` CLI)
3. `~/.creatorcut/config.json` — `{"anthropic_api_key": "sk-ant-..."}`

**Raises** `APIKeyMissingError` if no key is found anywhere.

`key_manager.get_key()` is the only correct way to obtain the key.
`key_manager.store_key(key)` persists to keychain or falls back to config.json.

---

## Path Helpers (`storage/local.py`)

All file paths are `pathlib.Path` objects. Every path the pipeline touches is
accessible via a helper function in `storage/local.py`. Never construct raw path
strings in route or pipeline code.

| Function | Returns |
|---|---|
| `db_path(base_dir)` | SQLite database file |
| `project_dir(base_dir, project_id)` | Root of one project |
| `clips_dir(base_dir, project_id)` | Uploaded original clips |
| `proxies_dir(base_dir, project_id)` | FFmpeg-generated proxy files |
| `frames_dir(base_dir, project_id)` | Extracted JPEG frames |
| `transcripts_dir(base_dir, project_id)` | Whisper JSON transcripts |
| `outputs_dir(base_dir, project_id)` | Final assembled video |
| `pipeline_lock_path(base_dir, project_id)` | Pipeline mutex lock file |
| `clip_path(base_dir, project_id, filename)` | One clip (validates filename) |
| `proxy_path(base_dir, project_id, clip_id)` | One proxy file |
| `transcript_path(base_dir, project_id, clip_id)` | One transcript |
| `frames_subdir(base_dir, project_id, clip_id)` | Frames for one clip |
| `output_path(base_dir, project_id, filename)` | Output video |
| `ensure_project_dirs(base_dir, project_id)` | Creates all subdirs |

`assert_safe_filename(filename)` guards against path traversal; `clip_path` calls it automatically.

---

## Database (`storage/database.py`)

- SQLite via SQLModel (`sqlmodel`)
- WAL journal mode, foreign keys ON, synchronous=NORMAL (set on engine init)
- `get_engine(db_path)` — singleton, initialised once at startup
- `create_tables(db_path)` — called at startup via lifespan event
- `get_session()` — FastAPI dependency (yields `Session`)

Import all models in `database.py` before calling `create_all` so SQLModel
registers their metadata correctly. This is already done — don't remove those imports.

---

## Models (`models/`)

See `docs/context/DATA_MODELS.md` for the full schema.

Key points:
- `Project` and `Clip` and `EditPlan` are SQLModel table models
- `StoryBrief`, `EditSegment`, `BRollPlacement`, `SoundDesignCue` are Pydantic-only (not tables)
- JSON columns use `sa_column=Column(JSON)` — never store nested objects as raw strings
- All IDs are UUIDs generated with `uuid.uuid4()` at creation time
- `updated_at` must be set manually in route handlers on every write

---

## Routes

### Error handling pattern

```python
from exceptions import InsufficientDiskSpaceError, InvalidClipError, PipelineLockError, PipelineError

try:
    ...
except InsufficientDiskSpaceError as e:
    raise HTTPException(status_code=507, detail=str(e))
except InvalidClipError as e:
    raise HTTPException(status_code=422, detail=str(e))
except PipelineLockError as e:
    raise HTTPException(status_code=409, detail=str(e))
except PipelineError as e:
    raise HTTPException(status_code=500, detail=str(e))
```

Never let `CreatorCutError` subclasses propagate to FastAPI unhandled — they produce 500s with
no useful client message. Convert them at the route boundary.

### Upload (`routes/upload.py`)

- `POST /api/projects/{id}/clips` — multipart, `files: list[UploadFile]`
- Writes to `clips_dir`, calls `ffprobe` to validate and extract metadata
- Rejects unsupported extensions (`.mp4 .mov .mkv .avi .mxf .m4v` allowed)
- Calls `assert_safe_filename` via `clip_path` — raises `PathTraversalError` → 422
- Streams upload in 1 MB chunks to avoid memory exhaustion

### Projects (`routes/projects.py`)

Standard CRUD. `POST /api/projects` creates dirs immediately via `ensure_project_dirs`.
`PATCH /api/projects/{id}` accepts partial updates (`model_dump(exclude_unset=True)`).

---

## Startup Validation (`config.py :: validate_startup`)

Called in the FastAPI lifespan event before the server accepts requests.

Checks (in order):
1. FFmpeg on `PATH` — fatal if missing
2. Anthropic API key — fatal if missing
3. `base_dir` writable — fatal if fails
4. SFX manifest present — warning only

`validate_startup` logs `[OK]` / `[FAIL]` / `[WARN]` for each check.
If any fatal check fails, it raises the appropriate `ConfigurationError` subclass,
which causes uvicorn to exit before accepting any requests.
