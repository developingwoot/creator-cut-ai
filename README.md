# CreatorCutAI

AI-powered video editing for YouTube creators and documentary filmmakers. Upload raw footage and a story brief; get back a near-finished edit with A/B roll, filler word removal, contextual sound design, and intelligent clip analysis — without touching a timeline.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | `brew install python@3.11` / `apt install python3.11` |
| FFmpeg | 5.0+ | `brew install ffmpeg` / `apt install ffmpeg` |
| Node.js | 18+ | `brew install node` / `apt install nodejs npm` |

Verify:

```bash
python3.11 --version
ffmpeg -version
node --version
```

---

## Installation

```bash
# 1. Clone the repo
git clone <repo-url> creator-cut-ai
cd creator-cut-ai

# 2. Backend — create virtualenv and install dependencies
cd backend
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend — install Node dependencies
cd ../frontend
npm install
```

---

## Configure Anthropic API Key

You need an [Anthropic API key](https://console.anthropic.com/) with access to Claude.

**Option A — environment variable (recommended for development):**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Option B — stored in OS keychain (persists across sessions):**

```bash
# macOS keychain / Linux secret-service via the setup wizard
python -m creatorcut setup
```

---

## Running in Development

Open two terminals:

```bash
# Terminal 1 — Backend (http://localhost:8000)
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000 --host 127.0.0.1

# Terminal 2 — Frontend (http://localhost:5173)
cd frontend
npm run dev
```

Open http://localhost:5173. The frontend proxies all `/api/*` requests to the backend automatically.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required if no keychain entry) |
| `CREATORCUT_BASE_DIR` | `~/.creatorcut` | Where projects and the DB are stored |
| `CREATORCUT_PORT` | `8000` | Backend port |
| `CREATORCUT_WHISPER_MODEL` | `medium` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `CREATORCUT_MAX_CONCURRENT` | `5` | Max concurrent Claude API calls during Pass 1 |
| `LOG_LEVEL` | `INFO` | Loguru log level |

---

## Project Structure

```
creatorcut-ai/
├── backend/
│   ├── main.py              ← FastAPI entry point
│   ├── config.py            ← Settings + KeyManager
│   ├── exceptions.py        ← All custom exceptions
│   ├── models/              ← SQLModel + Pydantic schemas
│   ├── routes/              ← FastAPI route handlers
│   ├── pipeline/            ← AI pipeline stages
│   ├── storage/             ← Database + local file helpers
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          ← Main app shell (5-step workflow)
│   │   ├── api/client.js    ← API client (all endpoints)
│   │   └── components/      ← Step components
│   └── package.json
├── assets/sfx/              ← Local CC0 sound effects library
├── docs/                    ← Architecture docs + ADRs
├── CLAUDE.md                ← Agent instructions
└── PROGRESS.md              ← Build state (read first each session)
```

---

## Startup Validation

The backend validates all dependencies on startup:

```
[OK] FFmpeg 6.0 found
[OK] API key configured
[OK] Database at ~/.creatorcut/projects.db
[OK] SFX library: 12 sounds
```

Any `[FAIL]` line must be resolved before the pipeline will function.

---

## Running Tests

```bash
cd backend && source .venv/bin/activate

# Unit + integration (no API cost, ~60s)
pytest tests/ -m "not e2e" -v

# Unit only (~10s)
pytest tests/unit/ -v
```
