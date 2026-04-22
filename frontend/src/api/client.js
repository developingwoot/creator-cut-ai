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

// ── Projects ──────────────────────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request('GET', '/health'),

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

  uploadClips: (projectId, files) => {
    const form = new FormData()
    for (const file of files) {
      form.append('files', file)
    }
    return request('POST', `/projects/${projectId}/clips`, form)
  },

  deleteClip: (projectId, clipId) =>
    request('DELETE', `/projects/${projectId}/clips/${clipId}`),

  // Analysis (routes to be implemented in Session 8)
  startAnalysis: (projectId) =>
    request('POST', `/projects/${projectId}/analyze`),

  getAnalysisStatus: (projectId) =>
    request('GET', `/projects/${projectId}/analyze/status`),

  // Edit plan
  getEditPlan: (projectId) =>
    request('GET', `/projects/${projectId}/edit-plan`),

  approveEditPlan: (projectId, approved, feedback = null) =>
    request('POST', `/projects/${projectId}/edit-plan/approve`, { approved, feedback }),

  // Assembly (Session 8)
  startAssembly: (projectId) =>
    request('POST', `/projects/${projectId}/assemble`),

  getAssemblyStatus: (projectId) =>
    request('GET', `/projects/${projectId}/assemble/status`),

  // SSE progress stream — returns an EventSource the caller must close
  progressStream: (projectId) => {
    return new EventSource(`${BASE}/projects/${projectId}/progress`)
  },
}

export default api
