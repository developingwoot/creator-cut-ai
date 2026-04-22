import { useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api, ApiError } from '../../api/client'

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

export default function ClipSelector({ projectId, onRegistered }) {
  const [isSelecting, setIsSelecting] = useState(false)
  const [error, setError] = useState(null)
  const [clips, setClips] = useState([])

  async function selectFiles() {
    setError(null)
    setIsSelecting(true)
    try {
      const selected = await open({
        multiple: true,
        filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'avi', 'mkv', 'mxf', 'm4v'] }],
      })

      // User cancelled the dialog
      if (!selected || (Array.isArray(selected) && selected.length === 0)) return

      const filePaths = Array.isArray(selected) ? selected : [selected]
      const newClips = await api.registerClips(projectId, filePaths)

      setClips((prev) => {
        const updated = [...prev, ...newClips]
        onRegistered?.(updated)
        return updated
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not register clips. Please try again.')
    } finally {
      setIsSelecting(false)
    }
  }

  return (
    <div className="w-full max-w-lg flex flex-col gap-4">
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
