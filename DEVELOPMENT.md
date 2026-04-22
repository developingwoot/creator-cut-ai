# CreatorCutAI — Development Guide

How to get the project running locally. Read by both humans and the agent —
the agent reads this to know how to verify its own work after implementing a stage.

---

## Prerequisites

```bash
# macOS
brew install ffmpeg python@3.11 node

# Ubuntu / Debian
sudo apt install ffmpeg python3.11 python3.11-venv nodejs npm

# Verify
ffmpeg -version        # must be 5.0+
python3.11 --version   # must be 3.11+
node --version         # must be 18+
```

---

## First-Time Setup

```bash
# 1. Backend — virtualenv and dependencies
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure Anthropic API key
#    Option A — environment variable (recommended for dev)
export ANTHROPIC_API_KEY=sk-ant-...

#    Option B — setup wizard (stores in OS keychain)
python -m creatorcut setup

# 3. Download Whisper model (first run only)
python -m creatorcut download-model medium

# 4. Download SFX library
cd ..
python scripts/download_sfx.py

# 5. Frontend
cd frontend && npm install
```

---

## Running in Development

Two terminals:

```bash
# Terminal 1 — Backend (http://localhost:8000)
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8000 --host 127.0.0.1

# Terminal 2 — Frontend (http://localhost:5173)
cd frontend && npm run dev
```

Frontend proxies all `/api/*` to the backend. Hot reload active on both sides.

---

## Running Tests

```bash
cd backend && source .venv/bin/activate

# Standard run — unit + integration + AI fixture (recorded cassettes, no API cost)
pytest tests/ -m "not e2e" -v

# Just unit tests (fastest, ~10s)
pytest tests/unit/ -v

# Just integration (real FFmpeg, ~60s)
pytest tests/integration/ -v

# Re-record one AI cassette (costs tokens, do deliberately)
RECORD_MODE=1 pytest tests/ai_fixture/test_pass1_quality.py::test_name -v

# Full E2E (slow, CI only)
pytest tests/e2e/ -v

# Coverage report
pytest tests/ -m "not e2e" --cov=. --cov-report=html && open htmlcov/index.html
```

---

## Startup Validation

The backend validates on startup and fails loudly:

```
[OK] FFmpeg 6.0 found
[OK] API key configured (keychain)
[OK] Database at ~/.creatorcut/projects.db
[OK] SFX library: 12 sounds
[FAIL] Whisper model not downloaded — run: python -m creatorcut download-model medium
```

Fix any `[FAIL]` before proceeding. The pipeline won't function without them.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | If no keychain | — | Anthropic API key |
| `CREATORCUT_BASE_DIR` | No | `~/.creatorcut` | Projects + DB root |
| `CREATORCUT_PORT` | No | `8000` | Backend port |
| `CREATORCUT_WHISPER_MODEL` | No | `medium` | Whisper model size |
| `CREATORCUT_MAX_CONCURRENT` | No | `5` | Max concurrent Claude API calls |
| `RECORD_MODE` | No | — | Set `1` to re-record AI test cassettes |
| `LOG_LEVEL` | No | `INFO` | Loguru level |

---

## Runtime File Locations

| What | Where |
|---|---|
| SQLite database | `~/.creatorcut/projects.db` |
| Project files | `~/.creatorcut/projects/{project_id}/` |
| API key (keychain) | OS keychain, service `creatorcut-ai` |
| API key (fallback) | `~/.creatorcut/config.json` |
| SFX library | `{repo}/assets/sfx/` |
| Frontend build | `{repo}/frontend/dist/` |

---

## Common Dev Tasks

**Add a Python dependency:**
```bash
pip install newpackage && pip freeze | grep newpackage >> requirements.txt
# Document in TECH_STACK.md with rationale
```

**Create an ADR:**
```bash
cp docs/decisions/ADR-000-template.md docs/decisions/ADR-007-description.md
# Fill it in — reference from the relevant context doc
```

**Add an SFX:**
```bash
# 1. Drop .wav into assets/sfx/
# 2. Add entry to assets/sfx/manifest.json (must be CC0, document source)
```

---

## Debugging

**Pipeline stuck / hung:**
```bash
ls ~/.creatorcut/projects/{id}/.pipeline.lock   # stale lock?
rm ~/.creatorcut/projects/{id}/.pipeline.lock
```

**FFmpeg error** — stderr is always included in `FFmpegError.message`. Test directly:
```bash
ffmpeg -i your_clip.mp4 -vf scale=1280:720 test_proxy.mp4
```

**Claude returning bad JSON** — enable debug logging to see raw responses:
```bash
LOG_LEVEL=DEBUG uvicorn main:app --reload
# Look for: "Raw Claude response:" in the log output
```

**Whisper too slow:**
```bash
python3 -c "import torch; print(torch.cuda.is_available())"
# If False, try the small model for development (less accurate but 4x faster)
CREATORCUT_WHISPER_MODEL=small uvicorn main:app --reload
```
