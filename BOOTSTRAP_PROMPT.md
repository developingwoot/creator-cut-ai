# CreatorCutAI — Bootstrap Prompt
# Paste this into Claude Code (VS Code extension) to initialize the project.
# Run this from the root of your empty project directory.

---

I'm building **CreatorCutAI**, an AI-powered video editing tool for YouTube creators.
The full context docs and CLAUDE.md files already exist in this project.
Please read ALL of the following files before doing anything else:

1. `CLAUDE.md` — root agent instructions and absolute rules
2. `docs/context/PROJECT_OVERVIEW.md` — what we're building and why
3. `docs/context/ARCHITECTURE.md` — system design and data flow
4. `docs/context/PIPELINE.md` — the AI pipeline in detail
5. `docs/context/DATA_MODELS.md` — all Pydantic schemas
6. `docs/context/AI_PROMPTS.md` — actual Claude prompts + caching strategy
7. `docs/context/TECH_STACK.md` — technology choices and rationale
8. `docs/context/MONETIZATION.md` — subscription model
9. `docs/context/TESTING.md` — testing strategy and fixtures
10. `docs/context/EDGE_CASES.md` — edge case handling
11. `backend/CLAUDE.md` — backend-specific instructions
12. `backend/pipeline/CLAUDE.md` — pipeline-specific instructions
13. `frontend/CLAUDE.md` — frontend-specific instructions
14. `PROGRESS.md` — current build state (always read this first in real sessions)
15. `DEVELOPMENT.md` — how to run and test the project
16. `docs/decisions/ADR-001-python-over-node.md` through `ADR-006-sqlite.md` — key decisions

Once you have read all of those, do the following:

## Task: Initialize the Project

### 1. Create `backend/requirements.txt`
Include exact pinned versions for:
- fastapi
- uvicorn[standard]
- sqlmodel
- anthropic
- faster-whisper
- ffmpeg-python
- pydantic-settings
- loguru
- python-multipart
- alembic

### 2. Create `backend/config.py`
Implement the full `Settings` and `KeyManager` classes exactly as specified in
`backend/CLAUDE.md`. Include startup validation logic.

### 3. Create `backend/storage/database.py`
SQLModel engine setup with WAL mode, foreign keys enabled, and a `get_session`
dependency for FastAPI. Include all model table definitions from DATA_MODELS.md
(Project, Clip tables).

### 4. Create `backend/models/project.py`, `backend/models/clip.py`, `backend/models/edit_plan.py`
Full Pydantic/SQLModel models matching DATA_MODELS.md exactly. Include all enums,
nested models, and validators.

### 5. Create `backend/storage/local.py`
All path helper functions as specified in `backend/CLAUDE.md`. Every path the
pipeline needs must be accessible via a function here.

### 6. Create `backend/main.py`
FastAPI app with:
- CORS middleware
- Static file serving for the React build
- All routers registered
- Startup validation event
- Health check endpoint

### 7. Create `backend/routes/projects.py` and `backend/routes/upload.py`
Implement these two routes first — they're needed before the pipeline:
- `POST /api/projects` — create project
- `GET /api/projects` — list projects  
- `GET /api/projects/{id}` — get project
- `POST /api/projects/{id}/clips` — upload clips (multipart)
- `DELETE /api/projects/{id}/clips/{clip_id}` — remove clip

### 8. Create `frontend/package.json` and `frontend/vite.config.js`
Vite + React + Tailwind setup. Proxy all `/api` requests to `localhost:8000`
during development.

### 9. Create `frontend/src/api/client.js`
Full API client as specified in `frontend/CLAUDE.md`. Every endpoint the frontend
will need, including the SSE progress stream.

### 10. Create `frontend/src/App.jsx`
The main app shell with:
- Step indicator header (5 steps)
- Router between steps (use simple state, not React Router for v1)
- Placeholder components for each step

### 11. Create `README.md`
Setup instructions:
- Prerequisites: Python 3.11+, FFmpeg, Node.js 18+
- Installation steps
- How to get an Anthropic API key and configure it
- How to run in development
- Project structure explanation

---

After completing all of the above, confirm what was created and flag any
ambiguities you encountered in the context docs that need clarification.

The next session (Session 1 in PROGRESS.md) will implement the project scaffold:
`backend/requirements.txt`, `backend/config.py`, `backend/storage/database.py`,
all models, `storage/local.py`, `main.py`, and the projects + upload routes.
