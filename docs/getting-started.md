# Getting Started — CreatorCutAI

This guide covers everything you need to run and test CreatorCutAI end-to-end.
Two inference paths are available: **local Ollama** (default, no network egress) and
**cloud fallback** (Anthropic API, opt-in via env var).

---

## Prerequisites

- **OS**: macOS, Linux, or WSL2 on Windows
- **Python 3.11+** with [uv](https://github.com/astral-sh/uv) (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 18+** with npm
- **FFmpeg** on your `PATH` (`sudo apt install ffmpeg` / `brew install ffmpeg`)
- **Rust** (for Tauri) — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Linux only**: WebKit2GTK — `sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev`

---

## Path A — Local Ollama (recommended, no API key needed)

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version   # confirm: ollama version 0.x.x
```

### 2. Start Ollama

```bash
ollama serve &
curl http://127.0.0.1:11434/api/tags   # should return {"models":[]}
```

### 3. Determine your tier and pull models

The app auto-detects your RAM tier at startup:

| Tier | Condition | VLM | LLM | Total download |
|---|---|---|---|---|
| `default` | ≥ 16 GB RAM | `qwen2.5vl:7b` | `qwen2.5:7b-instruct` | ~10 GB |
| `low_spec` | < 16 GB RAM | `moondream:1.8b` | `llama3.2:3b-instruct` | ~4 GB |

Pull the models for your tier:

```bash
# default tier (≥16 GB)
ollama pull qwen2.5vl:7b
ollama pull qwen2.5:7b-instruct

# low_spec tier (<16 GB)
ollama pull moondream:1.8b
ollama pull llama3.2:3b-instruct
```

Verify:

```bash
ollama list
```

### 4. Configure backend `.env`

Create (or edit) `backend/.env`:

```bash
# Required only if your RAM tier is low_spec (<16 GB):
CREATORCUT_OLLAMA_VLM_MODEL=moondream:1.8b
CREATORCUT_OLLAMA_LLM_MODEL=llama3.2:3b-instruct

# Optional — only needed for cloud fallback:
# ANTHROPIC_API_KEY=sk-ant-...
```

> **Why the overrides?** `Settings` defaults to the `default`-tier model names. If your RAM
> tier is `low_spec`, add these overrides so the pipeline calls the models you actually pulled.
> Without them, every AI call will fail with "model not found".

### 5. Install Python dependencies

```bash
cd backend
uv sync       # creates .venv and installs from requirements.txt
```

### 6. Start the backend

```bash
# From the frontend/ directory (uses the script in package.json):
cd frontend
npm install
npm run dev:backend
```

Expected startup output:

```
[OK] FFmpeg: ffmpeg version ...
[OK] Using Ollama for inference (cloud fallback disabled)
[OK] Database at ~/.creatorcut/projects.db
[OK] Ollama reachable at http://127.0.0.1:11434
Startup complete.
```

### 7. Start the frontend (second terminal)

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Path B — Cloud fallback (Anthropic API)

No Ollama required. Uses the Anthropic API for all AI calls.

### 1. Set up `backend/.env`

```bash
ANTHROPIC_API_KEY=sk-ant-...
CREATORCUT_CLOUD_FALLBACK=1
```

### 2. Start the backend and frontend

```bash
# Terminal 1
cd frontend && npm run dev:backend

# Terminal 2
cd frontend && npm run dev
```

Expected startup output includes:

```
[OK] Anthropic API key configured (cloud fallback active)
```

Open **http://localhost:5173**.

---

## Running with Tauri (native window)

`npm run dev:tauri` launches the full Tauri desktop experience. The Rust binary
automatically spawns and kills the Python backend — no separate backend terminal needed.

```bash
cd frontend
npm run dev:tauri
```

> **WSL2 note**: Requires a display. On Windows 11 with WSLg (default), it works automatically.
> On Windows 10 or without WSLg, run `wsl --update` in PowerShell and restart WSL.
> If you can't get a display, use the browser approach above — all functionality is identical.

---

## First-run model screen

When you open the app, the **ModelDownloadStep** appears first. It:

1. Calls `GET /api/models/tier` to auto-detect your RAM tier
2. Shows the required VLM and LLM models for that tier
3. If the models are already installed (pulled in Step 3 above), it auto-advances
4. If not, click **Pull** on each model and watch the progress bars

The rest of the app is gated until both models report as installed.

---

## Testing Workflow 1 — Movie Creator

This exercises the full pipeline: proxy → transcribe → Pass 1 VLM → Pass 2 LLM → assembly.

1. Click **Create a Movie** on the workflow selector
2. **Upload**: In browser mode, the file picker falls back to an amber dev-mode text area. Enter the absolute path to a short video clip (30–90 seconds, `.mp4` or `.mov`). Register 2–3 clips for a meaningful edit plan.
   ```bash
   find ~ -name "*.mp4" -size +1M -size -200M 2>/dev/null | head -5
   ```
3. **Brief**: Fill in title, story summary, target duration (e.g. `60`), and tone (e.g. `upbeat`). Click **Continue**.
4. **Analysis** — watch the SSE progress stream:
   | Stage | What's happening | Typical time |
   |---|---|---|
   | `proxying` | FFmpeg creates 1280×720 proxy per clip | 5–15s per clip |
   | `transcribing` | faster-whisper transcribes audio | 30–90s first run (model load); faster after |
   | `analyzing` | Ollama VLM analyses frames per clip | 30–120s per clip |
   | `planning` | Ollama LLM generates edit plan + self-critique | 30–60s |
   | `done` | Edit plan ready | — |
5. **Review**: Read the edit plan — segments with clip IDs, source time windows, B-roll notes. Click **Approve Plan**.
6. **Export**: Click **Start Assembly**. FFmpeg concatenates segments → output `.mp4` path shown on completion (under `~/.creatorcut/`).

---

## Testing Workflow 2 — Single Clip Editor

Faster to test. Exercises proxy → word-level transcription → filler detection → silence detection → rename suggestions.

1. Click **Edit a Single Clip** on the workflow selector
2. Register one clip via the dev-mode text area
3. Click **Process Clip** — watch: `proxying` → `transcribing` → `detecting` → `suggesting` → `done`
4. Review:
   - Transcript segments
   - Filler word spans (e.g. "um", "uh") with timestamps
   - Silence spans with timestamps
   - 3 AI-generated rename suggestions (≤ 60 characters each)
5. Toggle **Remove filler words** and/or **Remove silence**, pick a rename or type your own
6. Click **Apply** — FFmpeg cuts the edits and writes the output

---

## Verifying the API directly (no UI)

```bash
# Health check
curl http://localhost:8000/api/health

# Detected RAM tier + required models
curl http://localhost:8000/api/models/tier

# Installed vs required vs missing
curl http://localhost:8000/api/models/status

# Create a project
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project"}'
# → copy the "id" from the response

# Register a clip (substitute PROJECT_ID and file path)
curl -X POST http://localhost:8000/api/projects/PROJECT_ID/clips/register \
  -H "Content-Type: application/json" \
  -d '{"file_paths": ["/absolute/path/to/clip.mp4"]}'
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[FAIL] FFmpeg not found` | FFmpeg not on PATH | `sudo apt install ffmpeg` or `brew install ffmpeg` |
| ModelDownloadStep shows models as missing after pulling | Model name mismatch between `.env` and what was pulled | Check `ollama list` — names must match your `.env` overrides exactly |
| Analysis hangs at `transcribing` | Whisper model loading on first run | Wait 60–90s; it downloads/loads the model into RAM once then caches it |
| Ollama VLM returns bad JSON repeatedly | Model too small for the prompt | Switch to cloud fallback (`CREATORCUT_CLOUD_FALLBACK=1`) or pull a larger tier |
| `cannot open display` with Tauri on WSL2 | WSLg not enabled | Run `wsl --update` in PowerShell, restart WSL, retry; or use browser mode |
| Backend port 8000 already in use | Previous backend still running | `lsof -ti :8000 \| xargs kill` |
| `uv sync` fails | Python version mismatch | Ensure Python 3.11+ is active: `python --version` |

---

## Running tests

```bash
cd backend
.venv/bin/pytest tests/ -m "not e2e" -q
# expected: 163 passed
```
