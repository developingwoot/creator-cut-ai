# CreatorCutAI — Progress Log

**This file is updated by the agent at the end of every session.**
It is the source of truth for current project state. When `CLAUDE.md` says
"Current Build Status", defer to this file — it is always more accurate.

---

## How To Update This File

At the end of every coding session, the agent appends a new session entry:

```markdown
### Session N — YYYY-MM-DD
**Completed:**
- List every file created or meaningfully modified

**Decisions made:**
- Any non-trivial choice (add to docs/decisions/ if architectural)

**Blockers / open questions:**
- Anything unresolved that will affect next session

**Next session should:**
- The first 1-3 things to do, in order, ready to paste as a task
```

Do not summarize vaguely. Future sessions — and future Claude instances with no
memory of prior sessions — depend on this being specific and accurate.

---

## Current State

**Phase:** Session 1 complete — scaffold + routes + frontend shell built

**Session 1 output (all created):**

- `backend/requirements.txt`, `backend/config.py`, `backend/exceptions.py`
- `backend/models/` (project, clip, edit_plan, \_\_init\_\_)
- `backend/storage/database.py`, `backend/storage/local.py`
- `backend/main.py`
- `backend/routes/projects.py`, `backend/routes/upload.py`
- `frontend/` (package.json, vite.config.js, tailwind, index.html, src/main.jsx, src/index.css)
- `frontend/src/api/client.js`, `frontend/src/App.jsx`
- `README.md`, `.gitignore`
- `backend/CLAUDE.md`, `backend/pipeline/CLAUDE.md`, `frontend/CLAUDE.md`, `docs/context/DATA_MODELS.md`

**Still missing (not on disk despite PROGRESS.md claiming otherwise):**

- `docs/context/PROJECT_OVERVIEW.md`, `ARCHITECTURE.md`, `PIPELINE.md`, `AI_PROMPTS.md`, `TECH_STACK.md`, `MONETIZATION.md`, `TESTING.md`, `EDGE_CASES.md`
- `docs/decisions/` ADR files (ADR-001 through ADR-006)
- `assets/sfx/manifest.json` — confirmed present

---

## Planned Session Order

| Session | Status | Focus | Key Files |
| --- | --- | --- | --- |
| 1 | ✅ Done | Scaffold + Routes | `requirements.txt`, `config.py`, `models/`, `storage/`, `main.py`, `routes/projects.py`, `routes/upload.py` |
| 2 | ✅ Done (merged into 1) | Routes | merged with Session 1 |
| 2b | ✅ Done | Pivot: Tauri desktop app, eliminate file copying | `routes/upload.py`, `frontend/src-tauri/`, `ClipSelector.jsx`, `client.js` |
| 3 | Next | Pipeline: Ingest | `pipeline/proxy.py`, `pipeline/whisper_transcribe.py` |
| 4 | | Pipeline: Pass 1 | `pipeline/pass1_clip_analysis.py` (frames + Claude call) |
| 5 | | Pipeline: Filler + B-roll | `pipeline/filler_removal.py`, `pipeline/broll_overlay.py` |
| 6 | | Pipeline: Pass 2 | `pipeline/pass2_edit_planning.py`, `pipeline/sound_design.py` |
| 7 | | Pipeline: Assembly | `pipeline/assembly.py` |
| 8 | | Routes: Analyze + Assemble | `routes/analyze.py`, `routes/assemble.py` |
| 9 | ✅ Done (merged into 1) | Frontend: Scaffold | merged with Session 1 |
| 10 | | Frontend: Upload + Brief | `components/upload/`, `components/brief/` |
| 11 | | Frontend: Analysis + Review | `components/analysis/`, `components/timeline/` |
| 12 | | Frontend: Export + Polish | `components/export/`, end-to-end test run |

---

## Session Log

### Session 1 — 2026-04-22

#### Completed

- `backend/requirements.txt` — pinned versions for fastapi, uvicorn, sqlmodel, anthropic, faster-whisper, ffmpeg-python, pydantic-settings, loguru, python-multipart, alembic
- `backend/config.py` — `Settings` (pydantic-settings, env_prefix=CREATORCUT_), `KeyManager` (env → keychain → config.json), `validate_startup()`
- `backend/exceptions.py` — already existed; used as-is
- `backend/models/project.py` — `Project` (SQLModel table), `StoryBrief`, `ProjectCreate/Read/Update`, `ProjectStatus` enum
- `backend/models/clip.py` — `Clip` (SQLModel table), `ClipRead`, `ClipStatus` enum
- `backend/models/edit_plan.py` — `EditPlan` (SQLModel table), `EditSegment`, `BRollPlacement`, `SoundDesignCue`, `EditPlanRead/Approve`, `EditPlanStatus` enum
- `backend/models/__init__.py` — re-exports all public names
- `backend/storage/database.py` — SQLite engine (WAL mode, FK ON), `get_session()` FastAPI dep, `create_tables()`
- `backend/storage/local.py` — all path helpers (`db_path`, `project_dir`, `clips_dir`, `proxies_dir`, `frames_dir`, `transcripts_dir`, `outputs_dir`, `pipeline_lock_path`, `clip_path`, `proxy_path`, `transcript_path`, `frames_subdir`, `output_path`, `ensure_project_dirs`), `assert_safe_filename`
- `backend/storage/__init__.py`
- `backend/main.py` — FastAPI app, CORS, lifespan startup validation, routers, health endpoint, static file serving
- `backend/routes/projects.py` — `POST/GET /api/projects`, `GET/PATCH/DELETE /api/projects/{id}`, `GET /api/projects/{id}/clips`
- `backend/routes/upload.py` — `POST /api/projects/{id}/clips` (multipart, ffprobe validation), `DELETE /api/projects/{id}/clips/{clip_id}`
- `backend/routes/__init__.py`
- `frontend/package.json` — Vite 6 + React 18 + Tailwind 3
- `frontend/vite.config.js` — `/api` proxy to localhost:8000
- `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- `frontend/index.html`, `frontend/src/main.jsx`, `frontend/src/index.css`
- `frontend/src/api/client.js` — full API client (`api.*` methods, `ApiError`, SSE `progressStream`)
- `frontend/src/App.jsx` — 5-step app shell with `StepIndicator` and placeholder step components
- `README.md` — setup instructions, prerequisites, env vars, project structure
- `.gitignore`
- **Missing context files created:** `backend/CLAUDE.md`, `backend/pipeline/CLAUDE.md`, `frontend/CLAUDE.md`, `docs/context/DATA_MODELS.md`

#### Decisions made

- `ClaudeAPIError` added to exceptions (was implied by CLAUDE.md hierarchy but not listed) — kept consistent with existing `InvalidClaudeResponseError` which extends it
- `validate_startup` raises `FFmpegNotFoundError` as the first fatal error if FFmpeg is missing; raises `APIKeyMissingError` if only the key is missing — order matches the startup log sequence
- `upload.py` uses `ffprobe` directly via `subprocess` (not `ffmpeg-python`) for metadata extraction — ffmpeg-python wraps the full encoder, not the probe tool cleanly
- `routes/projects.py` includes `GET /api/projects/{id}/clips` (not in original route list but needed by the frontend before the analyze routes exist)
- Chose `PATCH` (not `PUT`) for project updates — partial update semantics are the right fit for status transitions

#### Blockers / open questions

- `docs/context/AI_PROMPTS.md`, `ARCHITECTURE.md`, `PIPELINE.md`, `TECH_STACK.md`, `EDGE_CASES.md`, `TESTING.md`, `MONETIZATION.md` were listed as written but do not exist on disk — needed before Sessions 3–8
- `docs/decisions/` ADR files (ADR-001 through ADR-006) similarly missing — write before pipeline sessions
- No tests exist yet — Session 2 or 3 should add unit tests for `storage/local.py` and `config.py` (KeyManager resolution order)

#### Next session should

1. Verify backend starts cleanly: `cd backend && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --port 8000`
2. Verify frontend builds: `cd frontend && npm install && npm run dev`
3. Write the missing `docs/context/` files (ARCHITECTURE, PIPELINE, AI_PROMPTS, TECH_STACK) — required reference for Sessions 3–8
4. Then begin Session 3: `pipeline/proxy.py` (FFmpeg proxy generation) + `pipeline/whisper_transcribe.py`

---

### Session 2b — 2026-04-22 (Tauri pivot)

**Files changed:**

- `backend/routes/upload.py` — replaced multipart `POST /clips` with `POST /clips/register` (accepts `{file_paths: [...]}`, no copying); `delete_clip` now only removes derived files (proxy, transcript, frames) — never touches `original_path`
- `frontend/src/api/client.js` — replaced `uploadClips()` with `registerClips(projectId, filePaths)`
- `frontend/src/components/upload/ClipSelector.jsx` — new component using Tauri `dialog.open()` for native file picker
- `frontend/src/App.jsx` — `UploadStep` now uses `ClipSelector`; auto-creates project on mount; Continue disabled until clips registered
- `frontend/src-tauri/` — Tauri v2 scaffolding: `tauri.conf.json`, `Cargo.toml`, `build.rs`, `src/main.rs`, `src/lib.rs`, `capabilities/default.json`
- `frontend/vite.config.js` — added `strictPort: true`, `host: 'localhost'`, `clearScreen: false` (Tauri requirements)
- `frontend/package.json` — added `@tauri-apps/api`, `@tauri-apps/cli`, `@tauri-apps/plugin-dialog`, `concurrently`; added `dev:backend` and `dev:all` scripts
- `.gitignore` — added `frontend/src-tauri/target/`
- `backend/main.py` — added `python-dotenv` `load_dotenv()` at startup so `backend/.env` is loaded automatically
- `backend/config.py` — `FileNotFoundError` → `OSError` in keychain subprocess calls (broader compatibility)
- `backend/models/{project,clip,edit_plan}.py` — removed `from __future__ import annotations` (caused SQLModel forward-ref resolution issues)
- `backend/routes/projects.py` — added `response_model=None` to DELETE endpoint (suppresses FastAPI 204 schema warning)

**Decisions:**

- Files reference in-place via `original_path` (the user's real filesystem path) — no copy, no symlink. Pipeline reads `original_path` directly when generating proxies, which is correct.
- `ClipStatus.uploaded` enum value kept as-is (renaming would need a migration; semantics are close enough)
- Backend subprocess management deferred — in dev, run the FastAPI backend in a separate terminal. Bundled sidecar (PyInstaller) is a v2 task.

**Blockers:**

- **Rust not installed** — `rustup` must be installed before `npx tauri dev` will work. Install instructions below.
- `docs/context/` files still missing (carried over from Session 1 blocker)

**Next session:**

1. Install Rust + Linux prerequisites (see "Running the App" below), then verify `npx tauri dev` launches the window
2. Write the missing `docs/context/` files (ARCHITECTURE, PIPELINE, AI_PROMPTS, TECH_STACK)
3. Begin Session 3: `pipeline/proxy.py` (FFmpeg proxy generation from `original_path`) + `pipeline/whisper_transcribe.py`

---

## Running the App (Tauri)

**Prerequisites (one-time):**

```bash
# 1. Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 2. Install Linux WebKit2GTK (required by Tauri on Linux/WSL2)
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev

# 3. Install Python deps
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

**Dev workflow (two terminals):**

```bash
# Terminal 1 — backend
cd backend && source .venv/bin/activate
CREATORCUT_ANTHROPIC_API_KEY=sk-ant-... uvicorn main:app --port 8000

# Terminal 2 — Tauri app
cd frontend && npx tauri dev
```

**What changed from the old workflow:**

| Before | After |
| --- | --- |
| `npm run dev` | `npx tauri dev` |
| Files dragged into browser upload zone | Native OS file picker — files stay in place |
| Files copied to `~/.creatorcut/projects/{id}/clips/` | `original_path` points to user's file; nothing copied |

---

## Known Issues

*(Populated during development)*

---

## Deferred Decisions

*(Things that came up during development but deliberately punted — revisit before v2)*
