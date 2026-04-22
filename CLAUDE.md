# CreatorCutAI — Agent Instructions

You are working on **CreatorCutAI**, an AI-powered video editing tool for YouTube creators
and documentary filmmakers. Users provide raw footage and a story brief; the system produces
a near-finished edited video with A/B roll handling, filler word removal, contextual sound
design, and intelligent clip analysis — without the user needing to touch a timeline.

---

## Read Before Touching Anything

Read `PROGRESS.md` first in every session — it is the ground truth of current state.
Then read the relevant context files for what you're building.

| Area | File |
|---|---|
| **Current build state** | `PROGRESS.md` ← read this first, every session |
| Full project vision & roadmap | `docs/context/PROJECT_OVERVIEW.md` |
| System architecture & data flow | `docs/context/ARCHITECTURE.md` |
| The AI pipeline (core of the app) | `docs/context/PIPELINE.md` |
| All JSON schemas & data models | `docs/context/DATA_MODELS.md` |
| Actual Claude prompts + caching | `docs/context/AI_PROMPTS.md` |
| Tech stack decisions & rationale | `docs/context/TECH_STACK.md` |
| Subscription model & billing | `docs/context/MONETIZATION.md` |
| Testing strategy & fixtures | `docs/context/TESTING.md` |
| Edge cases & error handling | `docs/context/EDGE_CASES.md` |
| Architecture decision records | `docs/decisions/` (one file per ADR) |
| How to run locally | `DEVELOPMENT.md` |

Each major module also has its own agent instructions:
- `backend/CLAUDE.md` — FastAPI server, storage, API key management
- `backend/pipeline/CLAUDE.md` — The two-pass AI pipeline, FFmpeg, Whisper
- `frontend/CLAUDE.md` — React dashboard, step workflow, review UI

---

## Project Structure

```
creatorcut-ai/
├── CLAUDE.md                        ← You are here
├── docs/
│   ├── context/                     ← Architecture & design docs (read-only reference)
│   │   ├── PROJECT_OVERVIEW.md
│   │   ├── ARCHITECTURE.md
│   │   ├── PIPELINE.md
│   │   ├── DATA_MODELS.md
│   │   ├── AI_PROMPTS.md
│   │   ├── TECH_STACK.md
│   │   ├── MONETIZATION.md
│   │   ├── TESTING.md
│   │   └── EDGE_CASES.md
│   └── decisions/                   ← Architecture Decision Records
│       ├── ADR-000-template.md
│       ├── ADR-001-python-over-node.md
│       ├── ADR-002-local-first.md
│       ├── ADR-003-two-pass-pipeline.md
│       ├── ADR-004-subscription-model.md
│       ├── ADR-005-api-key-security.md
│       └── ADR-006-sqlite.md
│
├── backend/                         ← Python FastAPI server
│   ├── CLAUDE.md                    ← Backend agent instructions
│   ├── main.py                      ← FastAPI entry point
│   ├── config.py                    ← Settings, env vars, KeyManager
│   ├── exceptions.py                ← All custom exception classes (canonical)
│   ├── routes/
│   │   ├── projects.py
│   │   ├── upload.py
│   │   ├── analyze.py
│   │   ├── assemble.py
│   │   └── billing.py               ← Stripe webhooks (v2)
│   ├── pipeline/
│   │   ├── CLAUDE.md                ← Pipeline agent instructions
│   │   ├── pass1_clip_analysis.py
│   │   ├── pass2_edit_planning.py
│   │   ├── assembly.py
│   │   ├── filler_removal.py
│   │   ├── broll_overlay.py
│   │   ├── sound_design.py
│   │   ├── proxy.py                 ← 4K → proxy downscale
│   │   └── whisper_transcribe.py
│   ├── models/
│   │   ├── project.py
│   │   ├── clip.py
│   │   └── edit_plan.py
│   ├── storage/
│   │   ├── local.py                 ← Local file storage
│   │   └── database.py              ← SQLite via SQLModel
│   └── tests/
│
├── frontend/                        ← React dashboard
│   ├── CLAUDE.md                    ← Frontend agent instructions
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── upload/
│       │   ├── brief/
│       │   ├── analysis/
│       │   ├── timeline/
│       │   └── export/
│       └── api/
│           └── client.js
│
├── assets/
│   └── sfx/                         ← Local sound effects library
│       ├── manifest.json            ← SFX catalog with tags & mood
│       ├── transitions/
│       ├── impacts/
│       ├── ambient/
│       └── reactions/
│
└── projects/                        ← User project data (gitignored)
    └── {project_id}/
        ├── project.json
        ├── clips/
        ├── proxies/
        ├── frames/
        ├── transcripts/
        └── outputs/
```

---

## Agent Behavioral Rules

These govern *how* the agent works, not just *what* it builds.

**When to stop and ask vs proceed:**
- If a context file clearly covers the situation → proceed
- If two context files conflict → stop and ask which takes precedence
- If a design decision isn't covered anywhere → stop and ask, then write an ADR
- If the correct approach requires a new dependency not in `TECH_STACK.md` → stop and ask
- If a task would take >2 hours of uninterrupted work → break it into sessions and ask for confirmation on the plan first

**Scope per session:**
- One logical unit per session: one pipeline stage, one route file, one component
- Write tests alongside the implementation — not after
- Do not refactor unrelated code while implementing a feature
- If you notice a bug outside your current scope, note it in `PROGRESS.md` under "Open Issues" and keep going

**How to handle uncertainty:**
- Never silently pick between two reasonable approaches — state the tradeoff and ask
- Never guess at a business requirement — check `PROJECT_OVERVIEW.md` or ask
- If the context docs are wrong or outdated, update them and note the change

**At the end of every session:**
1. Update `PROGRESS.md` — current state, next session, any blockers
2. Run `pytest tests/ -m "not e2e"` and confirm green
3. If a non-trivial architectural decision was made, append to `docs/decisions/ADR.md`

---

## Exception Hierarchy

All custom exceptions are defined in `backend/exceptions.py`. Read that file before
writing any error handling code. Never use bare `Exception` or `RuntimeError` in
pipeline or route code. The exception hierarchy is:

```
CreatorCutError
├── ConfigurationError
│   ├── APIKeyError
│   └── FFmpegNotFoundError
├── StorageError
│   ├── InsufficientDiskSpaceError
│   ├── ClipNotFoundError
│   ├── PathTraversalError
│   └── PipelineLockError
├── FFmpegError
│   ├── ProxyGenerationError
│   ├── AssemblyError
│   └── FrameExtractionError
├── TranscriptionError
├── PipelineError
│   ├── ClipAnalysisError
│   ├── FillerDetectionError
│   ├── EditPlanningError
│   └── InvalidClaudeResponseError
├── BriefValidationError
├── EditPlanValidationError
└── SubscriptionError (v2)
    └── EditLimitReachedError (v2)
```

---



## Absolute Rules

**Never break these regardless of what seems convenient:**

1. **Raw video never leaves the machine.** Only frame JPEGs (base64) and transcripts go to the
   Anthropic API. Never upload `.mp4`, `.mov`, or any video file to any external service.

2. **All API keys go through `KeyManager`.** Never access `os.environ` for API keys directly
   in pipeline or route code. Always use `from config import key_manager`.

3. **Edit plans are always human-reviewable before assembly.** The pipeline stops after pass 2
   and waits for explicit user approval. Never auto-assemble without approval.

4. **FFmpeg errors must never silently fail.** All FFmpeg calls wrap in try/except and surface
   errors to the user with the actual FFmpeg stderr output.

5. **Proxy files, not originals, go into the AI pipeline.** Original 4K files are only touched
   during final assembly. Everything else — frame extraction, scene detection — runs on proxies.

6. **SQLite is the only database for v1.** No Postgres, no Redis, no external database. This is
   a local tool first. The schema must be migration-friendly for when we go cloud.

7. **Always use prompt caching for Pass 1 and filler detection.** These are the
   repeated-prompt stages that make the unit economics work. See `AI_PROMPTS.md`.
   Breaking caching will 4x the cost per edit.

---

## Coding Conventions

### Python (backend)
- Python 3.11+
- Type hints on all function signatures
- Pydantic models for all data structures — never use raw dicts across module boundaries
- Async FastAPI routes; sync for CPU-bound pipeline tasks (run in threadpool via `asyncio.to_thread`)
- `loguru` for logging, not the stdlib logger
- All file paths as `pathlib.Path`, never raw strings

### React (frontend)
- Functional components with hooks only
- No class components
- Tailwind for styling — utility classes only, no custom CSS files
- API calls via the client in `frontend/src/api/client.js` — never use `fetch` directly in components
- Loading, error, and empty states required for every data-fetching component

### General
- No hardcoded paths — everything relative to a configured base directory
- Environment variables validated at startup, app refuses to start if required vars are missing
- Every pipeline step is independently testable with a fixture clip

---

## Current Build Status

**Phase:** Pre-v1 local tool

**Working:** Architecture and context docs (this file and the docs/ folder)

**Next to build:**
1. `backend/config.py` — KeyManager + settings
2. `backend/storage/database.py` — SQLite schema
3. `backend/pipeline/proxy.py` — FFmpeg proxy generation
4. `backend/pipeline/whisper_transcribe.py` — Local Whisper
5. `backend/pipeline/pass1_clip_analysis.py` — Per-clip Claude analysis
6. `backend/pipeline/pass2_edit_planning.py` — Edit plan generation
7. `backend/pipeline/filler_removal.py` — Contextual filler detection
8. `backend/pipeline/broll_overlay.py` — B-roll placement
9. `backend/pipeline/assembly.py` — FFmpeg final assembly
10. `frontend/` — React dashboard

**Do not build yet:**
- `routes/billing.py` — Stripe integration (v2)
- Cloud storage (v2)
- User authentication (v2)
- Multi-user support (v2)

---

## Key Design Decisions (Do Not Revisit Without Good Reason)

| Decision | Rationale |
|---|---|
| Python not Node.js | Whisper runs natively, richer ML ecosystem, ffmpeg-python more mature |
| Local-first | 4K footage can be 400GB+ — uploading is impractical and expensive |
| Two-pass pipeline | Single pass blows context window at scale (30 clips × frames) |
| Proxies for analysis | Never touch originals until final assembly render |
| Whisper local not API | Free, faster, works offline, no data leaves machine |
| SQLite not Postgres | Local tool v1 — migration path to Postgres planned for v2 cloud |
| Monthly subscription not BYOK-only | Lower friction for non-technical creators; BYOK remains as power-user tier |
| Scene detection before sampling | Reduces frames sent to Claude by ~80% with no quality loss |
| Edit plan requires human approval | AI makes mistakes; a bad auto-assembly wastes render time |
