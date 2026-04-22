# Architecture

## Overview

CreatorCutAI is a Tauri v2 desktop app. A React webview handles the UI; a FastAPI server
running locally handles all processing. Files never leave the machine.

```
┌──────────────────────────────────────────────────────────┐
│  Tauri Desktop App (Rust host)                           │
│  ┌────────────────────────┐                              │
│  │  React 18 webview      │  ← user interface            │
│  │  Vite + Tailwind CSS   │                              │
│  └────────────┬───────────┘                              │
│               │ HTTP /api/*  (localhost:8000)            │
│  ┌────────────▼───────────┐                              │
│  │  FastAPI backend       │  ← all logic lives here      │
│  │  Python 3.11           │                              │
│  │  uvicorn (local only)  │                              │
│  └──┬──────────┬──────────┘                              │
│     │          │                                         │
│  ┌──▼──┐  ┌───▼──────────────────┐                      │
│  │SQLite│  │  Pipeline            │                      │
│  │ DB  │  │  FFmpeg  Whisper      │                      │
│  └─────┘  │  Claude API (HTTPS)  │                      │
│           └──────────────────────┘                      │
└──────────────────────────────────────────────────────────┘
```

The Anthropic API is the only network call. Everything else is local.

---

## Components

### Tauri Host (Rust)

Wraps the webview and grants OS-level capabilities:
- `dialog.open` — native file picker (grants read access to selected paths)
- Window management, app lifecycle

The Rust layer has no application logic. It exists solely to host the webview and
provide native OS capabilities that a browser cannot access.

### React Frontend (`frontend/src/`)

Five-step wizard (Upload → Brief → Analysis → Review → Export).
State is managed with `useState` in `App.jsx` — no external state library.
All API calls go through `src/api/client.js`; components never call `fetch` directly.

### FastAPI Backend (`backend/`)

The only process with real logic. Runs on `localhost:8000`. In v1 development the user
starts it manually; in v2 it will be bundled as a PyInstaller sidecar that Tauri launches.

Sub-components:
- **Routes** (`routes/`) — HTTP endpoints, input validation, error translation
- **Pipeline** (`pipeline/`) — the AI processing stages (see `PIPELINE.md`)
- **Models** (`models/`) — SQLModel table definitions + Pydantic schemas
- **Storage** (`storage/`) — SQLite session factory + path helpers

### SQLite Database

Located at `~/.creatorcut/projects.db`. Three tables: `projects`, `clips`, `edit_plans`.
WAL journal mode; foreign keys enabled. Schema is migration-friendly (Alembic is installed).

### File Layout on Disk

```
~/.creatorcut/
├── projects.db            ← SQLite database
├── config.json            ← API key fallback (if keychain unavailable)
└── projects/
    └── {project_id}/
        ├── proxies/       ← 1280×720 working copies (never the 4K originals)
        ├── frames/        ← JPEG frames extracted per clip
        │   └── {clip_id}/
        ├── transcripts/   ← Whisper JSON output per clip
        └── outputs/       ← Final assembled video
```

Original clip files stay exactly where the user selected them. `clips.original_path`
points to those locations; the pipeline reads from there when generating proxies, but
never modifies or copies the originals.

---

## Data Flow

```
User selects files
    │
    ▼
POST /api/projects/{id}/clips/register
    │   (validates paths exist, runs ffprobe, stores metadata)
    ▼
clips table: original_path, duration, codec, resolution, fps
    │
    ▼
POST /api/projects/{id}/analyze   (Session 3+)
    │
    ├─ For each clip (concurrent, bounded by max_concurrent):
    │   ├─ proxy.py          → proxies/{clip_id}.mp4
    │   ├─ whisper.py        → transcripts/{clip_id}.json
    │   └─ pass1.py          → clips.analysis (key_moments, filler_spans, b_roll_tags)
    │
    ▼
pass2.py  (single call, all clip analyses + brief)
    │   → edit_plans table (segments, b_roll_placements, sound_cues)
    │
    ▼
[HUMAN REVIEW GATE]
    │   User approves or rejects + provides feedback
    │   If rejected → re-run pass2 with feedback
    ▼
POST /api/projects/{id}/assemble
    │
    ├─ filler_removal.py     → trims filler spans from each segment
    ├─ broll_overlay.py      → splices B-roll over A-roll cuts
    ├─ sound_design.py       → mixes in SFX from assets/sfx/
    └─ assembly.py           → FFmpeg final render → outputs/{project_id}.mp4
```

---

## Security Boundaries

- The FastAPI server binds to `127.0.0.1` only — not reachable from the network
- CORS allows only `localhost:5173` (the Tauri webview)
- Path traversal is guarded by `assert_safe_filename` in `storage/local.py`
- API keys are stored in OS keychain or `~/.creatorcut/config.json` (mode 0600)
- No video bytes leave the machine — only base64 JPEG frames and transcript text go to Claude

---

## Dev vs Production

| | Development | Production (v2 target) |
|---|---|---|
| Backend start | Manual (`uvicorn main:app`) | Tauri sidecar (PyInstaller) |
| Frontend | `npx tauri dev` | Bundled in Tauri `.app` / `.deb` |
| DB location | `~/.creatorcut/projects.db` | Same |
| API base | `localhost:8000` (Vite proxy) | Same (sidecar on same port) |
