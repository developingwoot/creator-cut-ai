# frontend/CLAUDE.md — Frontend Agent Instructions

Read this when working on any frontend code.

---

## Stack

- Vite + React 18 (functional components + hooks only)
- Tailwind CSS (utility classes only — no custom CSS files)
- No React Router — navigation is simple state in `App.jsx`
- No additional state management libraries for v1

---

## API Client (`src/api/client.js`)

All API calls go through the `api` object exported from `src/api/client.js`.
Never use `fetch` directly in a component. The client:

- Uses `/api` as the base path (Vite proxies to `localhost:8000` in dev)
- Throws `ApiError` (with `.status` and `.message`) on non-2xx responses
- Returns `null` for 204 No Content responses

### Available methods

| Method | Description |
|---|---|
| `api.health()` | GET /api/health |
| `api.createProject(name, brief)` | POST /api/projects |
| `api.listProjects()` | GET /api/projects |
| `api.getProject(id)` | GET /api/projects/{id} |
| `api.updateProject(id, updates)` | PATCH /api/projects/{id} |
| `api.deleteProject(id)` | DELETE /api/projects/{id} |
| `api.listClips(projectId)` | GET /api/projects/{id}/clips |
| `api.uploadClips(projectId, files)` | POST /api/projects/{id}/clips (multipart) |
| `api.deleteClip(projectId, clipId)` | DELETE /api/projects/{id}/clips/{clipId} |
| `api.startAnalysis(projectId)` | POST /api/projects/{id}/analyze |
| `api.getAnalysisStatus(projectId)` | GET /api/projects/{id}/analyze/status |
| `api.getEditPlan(projectId)` | GET /api/projects/{id}/edit-plan |
| `api.approveEditPlan(id, approved, feedback)` | POST /api/projects/{id}/edit-plan/approve |
| `api.startAssembly(projectId)` | POST /api/projects/{id}/assemble |
| `api.getAssemblyStatus(projectId)` | GET /api/projects/{id}/assemble/status |
| `api.progressStream(projectId)` | Returns `EventSource` for SSE progress |

---

## Component Requirements

Every component that fetches data must render three states:
- **Loading** — spinner or skeleton
- **Error** — user-readable message from `ApiError.message`
- **Empty** — helpful prompt (e.g. "No clips yet — upload some above")

---

## App Structure (`src/App.jsx`)

Five-step workflow managed with `useState`. Steps:

| Step | Component | Route |
|---|---|---|
| 1 | `UploadStep` | Upload footage |
| 2 | `BriefStep` | Story brief form |
| 3 | `AnalysisStep` | Progress display (SSE) |
| 4 | `ReviewStep` | Edit plan review + approve/reject |
| 5 | `ExportStep` | Assembly progress + download |

The step indicator in the header shows completed steps with a checkmark and highlights
the current step. Completed steps use `bg-indigo-600`, pending use `bg-gray-200`.

---

## Styling Conventions

- Indigo (`indigo-600`) is the primary brand colour
- All interactive buttons: `hover:` variant + `transition` class
- Disabled buttons: `bg-indigo-300 cursor-not-allowed` (not the full `opacity-50` pattern)
- Error states: `text-red-600` / `bg-red-50 border-red-200`
- Mono log output: `font-mono text-sm text-gray-600 bg-gray-100 rounded-xl`

---

## Build & Dev

```bash
npm run dev      # Vite dev server on :5173, proxies /api to :8000
npm run build    # Outputs to frontend/dist/ — served by FastAPI in production
```
