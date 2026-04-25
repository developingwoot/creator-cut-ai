const BASE = '/api'

async function request(method, path, body) {
  const opts = {
    method,
    headers: {},
  }

  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE}${path}`, opts)

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const json = await res.json()
      detail = json.detail || detail
    } catch {
      // response body was not JSON; use status text
    }
    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return null
  return res.json()
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// ── SSE helper ────────────────────────────────────────────────────────────────

async function _streamSse(url, fetchOpts, onEvent) {
  const res = await fetch(url, fetchOpts)
  if (!res.ok) {
    const json = await res.json().catch(() => ({}))
    throw new ApiError(json.detail || `HTTP ${res.status}`, res.status)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop()
      for (const chunk of chunks) {
        if (chunk.startsWith('data: ')) onEvent(JSON.parse(chunk.slice(6)))
      }
    }
  } finally {
    reader.cancel()
  }
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request('GET', '/health'),

  // Models / first-run setup
  getModelStatus: () => request('GET', '/models/status'),
  getModelTier: () => request('GET', '/models/tier'),
  pullModel: (model, onEvent, signal) =>
    _streamSse(
      `/api/models/pull`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }), signal },
      onEvent,
    ),

  // Projects
  createProject: (name, brief = null) =>
    request('POST', '/projects', { name, brief }),

  listProjects: () =>
    request('GET', '/projects'),

  getProject: (projectId) =>
    request('GET', `/projects/${projectId}`),

  updateProject: (projectId, updates) =>
    request('PATCH', `/projects/${projectId}`, updates),

  deleteProject: (projectId) =>
    request('DELETE', `/projects/${projectId}`),

  // Clips
  listClips: (projectId) =>
    request('GET', `/projects/${projectId}/clips`),

  registerClips: (projectId, filePaths) =>
    request('POST', `/projects/${projectId}/clips/register`, { file_paths: filePaths }),

  deleteClip: (projectId, clipId) =>
    request('DELETE', `/projects/${projectId}/clips/${clipId}`),

  // Analysis
  startAnalysis: (projectId, brief) =>
    request('POST', `/projects/${projectId}/analyze`, brief),

  // Edit plan
  getEditPlan: (projectId) =>
    request('GET', `/projects/${projectId}/edit-plan`),

  approveEditPlan: (projectId, approved, feedback = null) =>
    request('POST', `/projects/${projectId}/edit-plan/approve`, { approved, feedback }),

  // Workflow 1: SSE streams
  analyzeStream: (projectId, brief, onEvent, signal) =>
    _streamSse(
      `${BASE}/projects/${projectId}/analyze`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(brief), signal },
      onEvent,
    ),

  assembleStream: (projectId, onEvent, signal) =>
    _streamSse(
      `${BASE}/projects/${projectId}/assemble`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal },
      onEvent,
    ),

  // Workflow 2: single-clip SSE streams
  singleClipProcessStream: (projectId, onEvent, signal) =>
    _streamSse(
      `${BASE}/projects/${projectId}/single-clip/process`,
      { method: 'POST', signal },
      onEvent,
    ),

  singleClipApplyStream: (projectId, body, onEvent, signal) =>
    _streamSse(
      `${BASE}/projects/${projectId}/single-clip/apply`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal },
      onEvent,
    ),
}

export default api
