import { useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'

const ACCEPTED = new Set(['.mp4', '.mov', '.avi', '.mkv', '.mxf', '.m4v'])

function ext(filename) {
  return filename.slice(filename.lastIndexOf('.')).toLowerCase()
}

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

export default function UploadZone({ projectId, onUploaded }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [clips, setClips] = useState([])
  const fileInputRef = useRef(null)
  // Counter prevents isDragging flickering when cursor moves over child elements
  const dragCounter = useRef(0)

  async function handleFiles(fileList) {
    const files = Array.from(fileList)
    const invalid = files.filter((f) => !ACCEPTED.has(ext(f.name)))
    if (invalid.length) {
      setUploadError(
        `Unsupported format: ${invalid.map((f) => f.name).join(', ')}. Use MP4, MOV, MKV, AVI, MXF, or M4V.`
      )
      return
    }

    setUploadError(null)
    setIsUploading(true)
    try {
      const newClips = await api.uploadClips(projectId, files)
      setClips((prev) => {
        const updated = [...prev, ...newClips]
        onUploaded?.(updated)
        return updated
      })
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
    }
  }

  function onDragEnter(e) {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current++
    setIsDragging(true)
  }

  function onDragOver(e) {
    e.preventDefault()
    e.stopPropagation()
  }

  function onDragLeave(e) {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current--
    if (dragCounter.current === 0) setIsDragging(false)
  }

  function onDrop(e) {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  function onInputChange(e) {
    if (e.target.files?.length) handleFiles(e.target.files)
    // Reset so the same file can be re-selected if removed
    e.target.value = ''
  }

  return (
    <div className="w-full max-w-lg flex flex-col gap-4">
      <div
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={[
          'border-2 border-dashed rounded-xl p-12 flex flex-col items-center gap-4 cursor-pointer transition select-none',
          isDragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-gray-300 bg-gray-50 hover:bg-gray-100',
        ].join(' ')}
      >
        {isUploading ? (
          <>
            <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-500">Uploading…</p>
          </>
        ) : (
          <>
            <div className="text-4xl text-gray-400">{isDragging ? '⬇' : '↑'}</div>
            <p className="text-gray-500">
              {isDragging ? 'Drop to upload' : 'Click to browse or drag files here'}
            </p>
          </>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".mp4,.mov,.avi,.mkv,.mxf,.m4v"
        className="hidden"
        onChange={onInputChange}
      />

      {uploadError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {uploadError}
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
