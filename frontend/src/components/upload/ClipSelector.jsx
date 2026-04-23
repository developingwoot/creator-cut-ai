import { useState } from 'react'
import { api, ApiError } from '../../api/client'

const IS_TAURI = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

function formatDuration(seconds) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSize(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${(bytes / 1e3).toFixed(0)} KB`
}

async function openTauriPicker() {
  const { open } = await import('@tauri-apps/plugin-dialog')
  return open({
    multiple: true,
    filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'avi', 'mkv', 'mxf', 'm4v'] }],
  })
}

export default function ClipSelector({ projectId, onRegistered }) {
  const [isSelecting, setIsSelecting] = useState(false)
  const [error, setError] = useState(null)
  const [clips, setClips] = useState([])
  const [devPaths, setDevPaths] = useState('')

  async function registerPaths(filePaths) {
    const newClips = await api.registerClips(projectId, filePaths)
    setClips((prev) => {
      const updated = [...prev, ...newClips]
      onRegistered?.(updated)
      return updated
    })
  }

  async function selectFiles() {
    setError(null)
    setIsSelecting(true)
    try {
      const selected = await openTauriPicker()
      if (!selected || (Array.isArray(selected) && selected.length === 0)) return
      const filePaths = Array.isArray(selected) ? selected : [selected]
      await registerPaths(filePaths)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not register clips. Please try again.')
    } finally {
      setIsSelecting(false)
    }
  }

  async function submitDevPaths() {
    setError(null)
    const filePaths = devPaths
      .split('\n')
      .map((p) => p.trim())
      .filter(Boolean)
    if (filePaths.length === 0) return
    setIsSelecting(true)
    try {
      await registerPaths(filePaths)
      setDevPaths('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not register clips. Please try again.')
    } finally {
      setIsSelecting(false)
    }
  }

  return (
    <div className="w-full max-w-lg flex flex-col gap-4">
      {IS_TAURI ? (
        <button
          onClick={selectFiles}
          disabled={!projectId || isSelecting}
          className={[
            'border-2 border-dashed rounded-xl p-12 flex flex-col items-center gap-4 transition select-none',
            !projectId || isSelecting
              ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
              : 'border-gray-300 bg-gray-50 hover:bg-gray-100 hover:border-indigo-400 cursor-pointer',
          ].join(' ')}
        >
          {isSelecting ? (
            <>
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-gray-500">Reading file info…</p>
            </>
          ) : (
            <>
              <div className="text-5xl text-gray-300">+</div>
              <p className="text-gray-600 font-medium">Click to select video clips</p>
              <p className="text-gray-400 text-sm">MP4 · MOV · MKV · AVI · MXF · M4V</p>
              <p className="text-gray-400 text-xs">Files stay where they are — nothing is copied</p>
            </>
          )}
        </button>
      ) : (
        <div className="border-2 border-dashed border-amber-300 rounded-xl p-6 flex flex-col gap-3 bg-amber-50">
          <p className="text-sm font-medium text-amber-700">Dev mode — enter absolute file paths</p>
          <textarea
            rows={3}
            value={devPaths}
            onChange={(e) => setDevPaths(e.target.value)}
            placeholder="/home/user/videos/clip1.mp4&#10;/home/user/videos/clip2.mp4"
            disabled={!projectId || isSelecting}
            className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none disabled:opacity-50"
          />
          <button
            onClick={submitDevPaths}
            disabled={!projectId || isSelecting || !devPaths.trim()}
            className="self-start px-4 py-1.5 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600 transition font-medium disabled:bg-amber-200 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSelecting && (
              <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            )}
            Register clips
          </button>
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {clips.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200 overflow-hidden text-sm">
          {clips.map((clip) => (
            <li key={clip.id} className="flex items-center justify-between px-4 py-3 bg-white">
              <span className="font-medium text-gray-800 truncate max-w-xs" title={clip.filename}>
                {clip.filename}
              </span>
              <span className="text-gray-400 shrink-0 ml-4">
                {formatDuration(clip.duration_seconds)} · {formatSize(clip.file_size_bytes)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
