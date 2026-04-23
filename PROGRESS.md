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
| 2c | ✅ Done | Context docs | all `docs/context/` files written |
| 3 | ✅ Done | Pipeline: Ingest | `pipeline/proxy.py`, `pipeline/whisper_transcribe.py` |
| 4 | ✅ Done | Pipeline: Pass 1 | `pipeline/pass1_clip_analysis.py` (frames + Claude call) |
| 5 | ✅ Done | Pipeline: Filler + B-roll | `pipeline/filler_removal.py`, `pipeline/broll_overlay.py` |
| 6 | ✅ Done (partial) | Pipeline: Pass 2 | `pipeline/pass2_edit_planning.py` (sound_design.py deferred to Stage 4) |
| 7 | ✅ Done | Pipeline: Assembly + Routes: Assemble + Frontend Brief/Analysis | `pipeline/assembly.py`, `routes/assemble.py`, `BriefForm.jsx`, `AnalysisProgress.jsx` |
| 8 | ✅ Done (partial) | Routes: Analyze + Assemble | `routes/analyze.py` done; `routes/assemble.py` next |
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

### Session 3 — 2026-04-22

#### Completed

- `backend/pipeline/proxy.py` — `generate_proxy()`: FFmpeg 1280×720 H.264 proxy; idempotent; raises `ProxyGenerationError` with stderr on failure; caller persists status
- `backend/pipeline/whisper_transcribe.py` — `transcribe_clip()`: faster-whisper local transcription; module-level model cache; idempotent (JSON cache); non-fatal on failure (returns `{"segments": []}`)
- `backend/models/clip.py` — added `proxied` and `transcribed` to `ClipStatus` enum
- `backend/exceptions.py` — fixed `ProxyGenerationError` and `FrameExtractionError` to extend `FFmpegError` (aligns with documented hierarchy; enables `stderr` kwarg)
- `backend/tests/conftest.py` — `fixture_clip_path` session-scoped fixture (FFmpeg `testsrc`, 3s synthetic MP4)
- `backend/tests/test_pipeline_ingest.py` — 11 tests, all green

#### Decisions made

- `ProxyGenerationError` and `FrameExtractionError` now extend `FFmpegError` (not `PipelineError`); the CLAUDE.md hierarchy diagram implied this but the code had them flat under `PipelineError`
- Whisper model loading is deferred (import inside `_load_model`) and cached in a module-level dict keyed by model size — avoids loading on import and reuses across clips in the same process
- `transcribe_clip` is non-fatal: catches all exceptions, logs, and returns `{"segments": []}` — consistent with PIPELINE.md spec

#### Blockers / open questions

- None

#### Next session should

1. Build `backend/pipeline/pass1_clip_analysis.py`:
   - Frame extraction with FFmpeg `select='gt(scene,0.3)'` filter, max 12 frames, JPEG quality 85
   - Claude call using `PASS1_SYSTEM_PROMPT` from `docs/context/AI_PROMPTS.md` with `cache_control: ephemeral`
   - Model: `claude-sonnet-4-6`
   - Output: `ClipAnalysis` dict stored in `clip.analysis`
   - Concurrent across clips via `asyncio.gather` + semaphore
2. Write tests for `pass1_clip_analysis.py` (mock Claude, real FFmpeg frames)

---

### Session 4 — 2026-04-22

#### Completed

- `backend/pipeline/prompts.py` — Python constants `PASS1_SYSTEM_PROMPT`, `PASS2_SYSTEM_PROMPT`, `FILLER_ONLY_SYSTEM_PROMPT` (canonical import for all pipeline stages; mirrors `docs/context/AI_PROMPTS.md`)
- `backend/models/clip.py` — added `KeyMoment`, `FillerSpan`, `ClipAnalysis` Pydantic models; `ClipAnalysis.quality_score` validator clamps to [0.0, 1.0]
- `backend/pipeline/pass1_clip_analysis.py` — `extract_frames()` (FFmpeg scene-change detection + uniform fallback + cap at 12); `analyse_clip()` (frames → Claude with cached system prompt, up to 2 retries on bad JSON or API error); `run_pass1()` (async gather + semaphore bounded by `settings.max_concurrent`)
- `backend/tests/test_pipeline_pass1.py` — 24 tests, all green (real FFmpeg frames, mocked Claude)

#### Decisions made

- `_extract_uniform_frames` fallback uses `fps=0.5` (1 frame/2 s) for clips where scene detection finds 0 frames (common in synthetic test footage with no real scene changes)
- Frame limit enforced post-extraction by `_downsample` (evenly distributed, preserves first and last frame)
- `MagicMock(spec=anthropic.Anthropic)` cannot be used for the client mock — `messages` is an instance attribute not visible to `spec`. Tests use plain `MagicMock()` instead.
- `ClipAnalysis` defined in `models/clip.py` (not inline in pipeline) so Pass 2 can import the type without creating a circular dependency

#### Blockers / open questions

- None

#### Next session should

1. Build `backend/pipeline/pass2_edit_planning.py`:
   - Input: all `ClipAnalysis` results (from `clip.analysis`) + `StoryBrief` + SFX manifest IDs
   - Claude call with `PASS2_SYSTEM_PROMPT` (cached), model `claude-opus-4-7`
   - Output: `EditPlan` written to `edit_plans` table with `status = draft`
   - Handle optional `rejection_feedback` for re-run path
2. Write tests for `pass2_edit_planning.py` (mock Claude, validate `EditPlan` schema)

---

### Session 5 — 2026-04-22

#### Completed

- `backend/pipeline/pass2_edit_planning.py` — `run_pass2()` (single Claude Opus call: clip analyses + brief → EditPlan draft); `_load_sfx_ids()` (non-fatal manifest read); `_build_clip_analyses_json()`; `_build_user_message()` (brief + analyses + SFX list + optional rejection feedback block); `_parse_plan_response()` (validates segments via `EditSegment.model_validate`); `_call_claude()` (cached system prompt, up to 2 retries on bad JSON or API error)
- `backend/tests/test_pipeline_pass2.py` — 26 tests, all green

#### Decisions made

- Caller pre-filters to successful analyses only — `run_pass2` accepts `list[tuple[Clip, ClipAnalysis]]` with no `None`s; raises `PipelineError` if list is empty
- SFX manifest path resolved relative to `__file__` (`…/assets/sfx/manifest.json`); missing/malformed manifest logs a warning and passes an empty list to Claude — not fatal
- `base_dir` parameter kept in signature (unused now) to match the pattern of other pipeline stages and for future lock/output path use

#### Blockers / open questions

- None

#### Next session should

1. Build `backend/pipeline/filler_removal.py` — for each approved `EditPlan` segment, trim `filler_spans` that fall within `source_start`–`source_end` using FFmpeg `select` + `asetpts`/`setpts`; write tests
2. Build `backend/pipeline/broll_overlay.py` — splice B-roll clips at `b_roll_overlays` timecodes using FFmpeg `overlay` filter; write tests
3. Build `backend/routes/analyze.py` — SSE route that runs ingest → pass1 → pass2, emits progress events, writes EditPlan to DB

---

### Session 6 — 2026-04-23

#### Completed

- `backend/pipeline/filler_removal.py` — `remove_fillers(segment, clip, project_id, base_dir) -> Path`: trims filler spans (segment-relative, clamped) from a proxy using FFmpeg `select`/`aselect`/`setpts`/`asetpts`; falls back to simple trim when no fillers; writes to `outputs/{project_id}/segments/seg_{order:04d}.mp4`
- `backend/pipeline/broll_overlay.py` — `apply_broll(segment, clips_by_id, project_id, base_dir, input_path) -> Path`: composites B-roll video over A-roll (keeps A-roll audio) using subprocess + dynamic `filter_complex`; non-fatal on missing/invalid placements; returns `input_path` unchanged if no valid placements
- `backend/routes/analyze.py` — `POST /api/projects/{id}/analyze`: SSE route wiring the full ingest → pass1 → pass2 pipeline; emits `proxying`/`transcribing`/`analyzing`/`planning`/`done`/`error` events; acquires pipeline lock (try/finally release); persists `EditPlan` and `Project.status` to DB; handles per-clip proxy failures without halting the whole pipeline
- `backend/main.py` — registered `analyze_router` under `/api`
- `backend/tests/test_pipeline_filler.py` — 12 tests (unit: `_active_spans`; integration: real FFmpeg trim + filler removal)
- `backend/tests/test_pipeline_broll.py` — 9 tests (unit: `_resolve_placements`; integration: real FFmpeg overlay)
- `backend/tests/test_routes_analyze.py` — 7 tests (validation 404/422; SSE stage ordering; lock behavior; lock cleanup on success + error)
- All 93 tests pass

#### Decisions made

- `_save_clip` in `analyze.py` reloads the Clip by PK in a fresh session instead of `session.add(detached_obj)` — avoids SQLAlchemy `DetachedInstanceError` caused by commit-triggered expiry on the in-flight clip object
- `broll_overlay.py` uses `subprocess` (not ffmpeg-python) for the dynamic multi-input `filter_complex` — ffmpeg-python's API becomes unwieldy for N dynamically-chained overlay inputs
- `remove_fillers` always writes a segment file even when there are no filler spans — gives assembly a consistent set of pre-trimmed per-segment files to concatenate
- B-roll overlay timecodes are segment-relative (per DATA_MODELS.md spec); filler span timestamps are clip-absolute and converted to segment-relative in `_active_spans`

#### Blockers / open questions

- None

#### Next session should

1. Build `backend/pipeline/assembly.py` — concat all `segments/` files (with B-roll applied) into `outputs/output.mp4` using FFmpeg `concat` demuxer; write tests
2. Build `backend/routes/assemble.py` — `POST /api/projects/{id}/assemble` + `GET /api/projects/{id}/plans` + `POST /api/projects/{id}/plans/{plan_id}/approve`; approve sets `EditPlan.status=approved` and triggers assembly
3. Wire frontend Step 3 (Brief) → Step 4 (Analysis SSE progress view) to the new `/analyze` endpoint

---

### Session 7 — 2026-04-23

#### Completed

- `backend/pipeline/assembly.py` — `assemble(plan, clips_by_id, project_id, base_dir) -> Path`: parses `EditPlan.segments` (JSON), sorts by order, runs each through `remove_fillers` → `apply_broll`, writes an FFmpeg concat list, runs `ffmpeg -f concat -safe 0 -c copy` to produce `outputs/output.mp4`; raises `AssemblyError` on FFmpeg failure, `ClipNotFoundError` for missing clips
- `backend/tests/test_pipeline_assembly.py` — 7 tests: unit (empty segments, missing clip, ordering guarantee) + integration (single segment, two-segment concat with duration check); all pass
- `backend/routes/assemble.py` — three endpoints: `GET /projects/{id}/edit-plan` (latest plan), `POST /projects/{id}/edit-plan/approve` (approve/reject with 409 guard on non-draft), `POST /projects/{id}/assemble` (SSE stream: assembling → done/error, pipeline lock, ProjectStatus transitions)
- `backend/main.py` — registered `assemble_router` under `/api`
- `backend/tests/test_routes_assemble.py` — 13 tests: GET plan (404 no project, 404 no plan, returns plan), approve (404 variants, approve sets approved_at, reject keeps approved_at null, 409 on non-draft), assemble SSE (404 no project, 409 no approved plan, lock emits error, happy path emits done, lock released on success + error); all pass
- `frontend/src/api/client.js` — added `analyzeStream(projectId, brief, onEvent, signal)` and `assembleStream(projectId, onEvent, signal)` using fetch + ReadableStream for POST SSE; updated `startAnalysis` to pass brief body
- `frontend/src/components/brief/BriefForm.jsx` — controlled form for title / story_summary / target_duration_seconds / tone; validates all fields before enabling submit; calls `onSubmit(brief)` with clean data
- `frontend/src/components/analysis/AnalysisProgress.jsx` — opens `analyzeStream` on mount with AbortController; shows ordered stage list (proxying → transcribing → analyzing → planning → done) with spinner/checkmark/pending states; progress bar; auto-advances via `onNext()` 800ms after done event; error banner on failure
- `frontend/src/App.jsx` — added `brief` state; `goNext(data)` captures brief when leaving Step 2; replaced inline placeholder `BriefStep` and `AnalysisStep` bodies with `<BriefForm>` and `<AnalysisProgress>`; step rendering switched from `STEP_COMPONENTS` array to explicit per-step JSX to support prop threading
- All 113 tests pass

#### Decisions made

- `AssemblyError` extends `PipelineError` (not `FFmpegError`) — it has no `stderr` kwarg; FFmpeg stderr is embedded in the message string directly
- Approval endpoint queries the most-recently-created plan (not a specific plan_id) — matches the client.js API shape already written; one project has one active plan at a time for v1
- `POST /assemble` finds the most-recently-approved plan automatically — caller sends no body, backend selects it; simplifies the frontend
- `analyzeStream` / `assembleStream` use fetch + ReadableStream rather than EventSource — EventSource is GET-only; both endpoints are POST with a body
- `goNext(data)` in App.jsx accepts optional data and saves it as brief when leaving Step 2 — avoids prop drilling through all steps while keeping the pattern extensible

#### Blockers / open questions

- None

#### Next session should

1. Frontend: `components/timeline/` — ReviewStep showing actual EditPlan segments (fetched via `api.getEditPlan`), approve/reject buttons wired to `api.approveEditPlan`, rejection feedback textarea
2. Frontend: `components/export/` — ExportStep wired to `api.assembleStream`, shows SSE progress, displays output path on done
3. End-to-end smoke test: full 5-step flow from clip registration to assembled output.mp4

---

## Known Issues

None yet — populated during development.

---

## Deferred Decisions

None yet — things that came up during development but were deliberately punted will be listed here for revisiting before v2.
