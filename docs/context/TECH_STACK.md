# Tech Stack

Every dependency and the reason it was chosen. Do not add new dependencies without
updating this file and getting approval (see root `CLAUDE.md`).

---

## Backend

### Runtime

| Package | Version | Role |
|---|---|---|
| Python | 3.11+ | Runtime — match machines target |
| FastAPI | latest | HTTP API framework |
| uvicorn | latest | ASGI server |

**Why FastAPI:** Native async, automatic OpenAPI docs, excellent Pydantic integration.
The ecosystem around ML/AI in Python (Whisper, ffmpeg-python, anthropic SDK) is
significantly more mature than the Node.js equivalents.

### Data / Storage

| Package | Version | Role |
|---|---|---|
| sqlmodel | latest | SQLite ORM (SQLAlchemy + Pydantic in one) |
| alembic | latest | DB migrations (not yet used, set up for v2 cloud migration) |
| pydantic-settings | latest | Config + env var management |

**Why SQLModel:** Eliminates the dual-model problem (separate SQLAlchemy + Pydantic
schemas). Type safety from DB to API with a single class definition.

**Why SQLite:** v1 is a local single-user tool. SQLite is zero-infrastructure, ships
in Python's stdlib, and handles single-user write workloads easily. Alembic is already
installed so migration to Postgres for v2 cloud is straightforward.

### AI / ML

| Package | Version | Role |
|---|---|---|
| anthropic | latest | Claude API client |
| faster-whisper | latest | Local speech-to-text (CTranslate2 backend) |

**Why faster-whisper over openai-whisper:** 4× faster inference, lower memory footprint,
same accuracy. Audio never leaves the machine — important for creator privacy.

**Why local Whisper over Whisper API:** Free (after hardware cost), offline-capable,
no data leaves the machine, no per-minute charges on long interviews.

### Video / Audio

| Package | Version | Role |
|---|---|---|
| ffmpeg-python | latest | FFmpeg wrapper for proxy generation, frame extraction, assembly |
| python-multipart | latest | FastAPI file uploads (future use) |

**Why ffmpeg-python:** The most mature Python FFmpeg binding. Fluent API for complex
filter chains. FFmpeg itself must be installed separately (`ffmpeg` on `PATH`).

**Why FFmpeg:** Industry standard, handles every codec and container, mature Python
bindings, scriptable complex filter graphs needed for filler removal and B-roll overlay.

### Utilities

| Package | Version | Role |
|---|---|---|
| loguru | latest | Structured logging with coloured output |
| python-dotenv | latest | Loads `backend/.env` at startup for local dev |

**Why loguru over stdlib logging:** Zero configuration, better default formatting,
context managers for temporary log levels. Negligible overhead.

---

## Frontend

### Framework

| Package | Version | Role |
|---|---|---|
| React | 18 | UI framework |
| Vite | 6 | Build tool + dev server |

**Why React:** Team familiarity. Functional components + hooks are sufficient for this
workflow (linear five-step wizard with minimal shared state).

**Why Vite:** Fastest HMR in dev, ESM-native, good Tauri integration (`strictPort`,
`clearScreen` options built in).

### Styling

| Package | Version | Role |
|---|---|---|
| Tailwind CSS | 3 | Utility-first styling |
| autoprefixer | latest | PostCSS vendor prefixes |
| postcss | latest | CSS processing pipeline |

**Why Tailwind:** No naming bike-shedding, no context switching between files, fast
iteration. The app has a simple visual design that doesn't need a component library.

### Desktop

| Package | Version | Role |
|---|---|---|
| @tauri-apps/api | ^2 | JavaScript bridge to Tauri Rust APIs |
| @tauri-apps/cli | ^2 | `npx tauri dev` / `npx tauri build` |
| @tauri-apps/plugin-dialog | ^2 | Native file picker (`dialog.open`) |

**Why Tauri v2:** Native file system access without copying files. 4K footage can be
hundreds of GB — uploading to a browser origin or copying to app storage is impractical.
Tauri gives us a native file picker that returns paths; the backend reads from those
paths directly. Electron was considered but Tauri has a smaller bundle size and better
WSL2 support.

### Dev

| Package | Version | Role |
|---|---|---|
| concurrently | latest | `npm run dev:all` runs backend + frontend in one terminal |

---

## Tauri / Rust

No application logic lives in Rust. The Tauri Rust host is purely a runtime container.
Capabilities granted: `dialog:default` (file open picker).

Rust and the WebKit2GTK system dependencies must be installed separately:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev  # Linux/WSL2
```

---

## Not in the Stack (and why)

| Tool | Why not |
|---|---|
| Redis | No need for a cache or job queue in a single-user local app |
| Postgres | Local tool v1 — SQLite is sufficient; Postgres is planned for v2 cloud |
| Celery / RQ | FastAPI's `asyncio.to_thread` handles CPU-bound pipeline tasks adequately |
| Electron | Heavier bundle; worse WSL2 support than Tauri |
| React Router | Five linear steps don't need a router |
| Redux / Zustand | State is simple enough for `useState` in `App.jsx` |
| OpenAI Whisper API | Per-minute cost, data leaves machine, requires network |
| Docker | Overkill for a local desktop tool; adds friction for non-technical users |
