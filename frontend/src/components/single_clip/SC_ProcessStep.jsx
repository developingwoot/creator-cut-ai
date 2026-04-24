import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

const STAGES = [
  { key: 'proxying',     label: 'Generating proxy' },
  { key: 'transcribing', label: 'Transcribing audio' },
  { key: 'detecting',    label: 'Detecting fillers & silence' },
  { key: 'suggesting',   label: 'Generating rename suggestions' },
]

function stageIndex(key) {
  return STAGES.findIndex((s) => s.key === key)
}

export default function SC_ProcessStep({ projectId, onDone, onBack }) {
  const [currentStage, setCurrentStage] = useState(null)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    abortRef.current = controller

    api.singleClipProcessStream(
      projectId,
      (event) => {
        if (event.stage === 'error') {
          setError(event.message || 'Processing failed.')
        } else if (event.stage === 'done') {
          onDone(event)
        } else {
          setCurrentStage(event.stage)
        }
      },
      controller.signal,
    ).catch((err) => {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Connection error.')
      }
    })

    return () => controller.abort()
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  const activeIdx = stageIndex(currentStage)

  return (
    <div className="flex flex-col items-center gap-8 py-16 max-w-md mx-auto">
      <h2 className="text-2xl font-bold text-gray-800">Processing Your Clip</h2>
      <p className="text-gray-500 text-center text-sm">This may take a minute — Whisper runs locally.</p>

      {error ? (
        <div className="w-full rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600 flex flex-col gap-3">
          <span>{error}</span>
          <button
            onClick={onBack}
            className="self-start text-sm text-red-700 underline hover:no-underline"
          >
            ← Go back
          </button>
        </div>
      ) : (
        <ul className="w-full flex flex-col gap-3">
          {STAGES.map((stage, i) => {
            const done = activeIdx > i || currentStage === 'done'
            const active = activeIdx === i
            return (
              <li key={stage.key} className="flex items-center gap-4">
                <div
                  className={[
                    'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                    done ? 'bg-indigo-600' : active ? 'bg-indigo-100' : 'bg-gray-100',
                  ].join(' ')}
                >
                  {done ? (
                    <span className="text-white text-sm">✓</span>
                  ) : active ? (
                    <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <div className="w-3 h-3 rounded-full bg-gray-300" />
                  )}
                </div>
                <span
                  className={[
                    'text-sm',
                    done ? 'text-gray-500 line-through' : active ? 'text-gray-800 font-medium' : 'text-gray-400',
                  ].join(' ')}
                >
                  {stage.label}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
