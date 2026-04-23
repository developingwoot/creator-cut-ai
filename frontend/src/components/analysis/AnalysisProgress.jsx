import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

const STAGES = [
  { key: 'proxying',     label: 'Generating proxies' },
  { key: 'transcribing', label: 'Transcribing audio' },
  { key: 'analyzing',   label: 'Analysing clips (Pass 1)' },
  { key: 'planning',    label: 'Planning edit (Pass 2)' },
  { key: 'done',        label: 'Edit plan ready' },
]

const STAGE_ORDER = Object.fromEntries(STAGES.map((s, i) => [s.key, i]))

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-indigo-600"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8H4z"
      />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  )
}

export default function AnalysisProgress({ projectId, brief, onNext }) {
  const [currentStage, setCurrentStage] = useState(null)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [error, setError] = useState(null)
  const advancedRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()

    api
      .analyzeStream(
        projectId,
        brief,
        (event) => {
          setCurrentStage(event.stage)
          setProgress(event.progress ?? 0)
          setMessage(event.message ?? '')

          if (event.stage === 'done' && !advancedRef.current) {
            advancedRef.current = true
            // Brief pause so user sees the completed state before advancing
            setTimeout(() => onNext(), 800)
          }
          if (event.stage === 'error') {
            setError(event.message || 'Analysis failed.')
          }
        },
        controller.signal,
      )
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })

    return () => controller.abort()
  }, [projectId, brief]) // eslint-disable-line react-hooks/exhaustive-deps

  const currentIndex = currentStage ? (STAGE_ORDER[currentStage] ?? -1) : -1

  return (
    <div className="max-w-xl mx-auto py-12 px-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Analysing your footage</h2>
      <p className="text-gray-500 mb-10">This may take a few minutes depending on your clip count.</p>

      {/* Stage list */}
      <ol className="space-y-4 mb-10">
        {STAGES.map((stage, i) => {
          const isDone = i < currentIndex || currentStage === 'done'
          const isActive = i === currentIndex && currentStage !== 'done'
          const isPending = i > currentIndex || currentStage === null

          return (
            <li key={stage.key} className="flex items-center gap-3">
              <span className="w-5 flex items-center justify-center flex-shrink-0">
                {isDone ? <CheckIcon /> : isActive ? <Spinner /> : (
                  <span className="h-4 w-4 rounded-full border-2 border-gray-300" />
                )}
              </span>
              <span className={`text-sm ${isDone ? 'text-gray-500 line-through' : isActive ? 'text-indigo-700 font-medium' : 'text-gray-400'}`}>
                {stage.label}
              </span>
            </li>
          )
        })}
      </ol>

      {/* Progress bar — visible while streaming */}
      {currentStage && currentStage !== 'done' && !error && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{message}</span>
            <span>{Math.round(progress * 100)}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
            <div
              className="h-2 rounded-full bg-indigo-600 transition-all duration-300"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Loading state — before first event */}
      {!currentStage && !error && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Spinner />
          <span>Starting analysis…</span>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}
    </div>
  )
}
