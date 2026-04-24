import { useState } from 'react'
import { api, ApiError } from '../../api/client'

const IS_TAURI = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

async function openTauriPicker() {
  const { open } = await import('@tauri-apps/plugin-dialog')
  return open({
    multiple: false,
    filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'avi', 'mkv', 'mxf', 'm4v'] }],
  })
}

export default function SC_UploadStep({ projectId, onRegistered, onNext }) {
  const [isSelecting, setIsSelecting] = useState(false)
  const [error, setError] = useState(null)
  const [clip, setClip] = useState(null)
  const [devPath, setDevPath] = useState('')

  async function registerPath(filePath) {
    const clips = await api.registerClips(projectId, [filePath])
    const registered = clips[0]
    setClip(registered)
    onRegistered?.(registered)
  }

  async function selectFile() {
    setError(null)
    setIsSelecting(true)
    try {
      const selected = await openTauriPicker()
      if (!selected) return
      const path = Array.isArray(selected) ? selected[0] : selected
      await registerPath(path)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not register clip. Please try again.')
    } finally {
      setIsSelecting(false)
    }
  }

  async function submitDevPath() {
    setError(null)
    const path = devPath.trim()
    if (!path) return
    setIsSelecting(true)
    try {
      await registerPath(path)
      setDevPath('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not register clip. Please try again.')
    } finally {
      setIsSelecting(false)
    }
  }

  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Select Your Clip</h2>
      <p className="text-gray-500 max-w-md text-center">
        Pick a single video file. It stays where it is — nothing is copied.
      </p>

      <div className="w-full max-w-lg flex flex-col gap-4">
        {IS_TAURI ? (
          <button
            onClick={selectFile}
            disabled={!projectId || isSelecting || !!clip}
            className={[
              'border-2 border-dashed rounded-xl p-12 flex flex-col items-center gap-4 transition select-none',
              !projectId || isSelecting || clip
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
                <p className="text-gray-600 font-medium">Click to select a video clip</p>
                <p className="text-gray-400 text-sm">MP4 · MOV · MKV · AVI · MXF · M4V</p>
                <p className="text-gray-400 text-xs">One clip only</p>
              </>
            )}
          </button>
        ) : (
          <div className="border-2 border-dashed border-amber-300 rounded-xl p-6 flex flex-col gap-3 bg-amber-50">
            <p className="text-sm font-medium text-amber-700">Dev mode — enter the absolute file path</p>
            <input
              type="text"
              value={devPath}
              onChange={(e) => setDevPath(e.target.value)}
              placeholder="/home/user/videos/clip.mp4"
              disabled={!projectId || isSelecting || !!clip}
              className="w-full rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-50"
            />
            <button
              onClick={submitDevPath}
              disabled={!projectId || isSelecting || !devPath.trim() || !!clip}
              className="self-start px-4 py-1.5 bg-amber-500 text-white text-sm rounded-lg hover:bg-amber-600 transition font-medium disabled:bg-amber-200 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isSelecting && (
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              Register clip
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {clip && (
          <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 flex items-center gap-3">
            <span className="text-green-500 text-xl">✓</span>
            <div>
              <p className="text-sm font-medium text-gray-800">{clip.filename}</p>
              {clip.duration_seconds && (
                <p className="text-xs text-gray-500">
                  {Math.floor(clip.duration_seconds / 60)}:{String(Math.floor(clip.duration_seconds % 60)).padStart(2, '0')}
                  {clip.resolution && ` · ${clip.resolution}`}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <button
        onClick={onNext}
        disabled={!clip}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold disabled:bg-indigo-300 disabled:cursor-not-allowed"
      >
        Continue
      </button>
    </div>
  )
}
