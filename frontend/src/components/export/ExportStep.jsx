import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

const INITIAL = 'idle'
const STREAMING = 'streaming'
const DONE = 'done'
const ERROR = 'error'

export default function ExportStep({ projectId }) {
  const [phase, setPhase] = useState(INITIAL)
  const [message, setMessage] = useState('')
  const [outputPath, setOutputPath] = useState(null)
  const [errorMsg, setErrorMsg] = useState(null)
  const abortRef = useRef(null)

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  function handleStart() {
    const controller = new AbortController()
    abortRef.current = controller
    setPhase(STREAMING)
    setMessage('Starting assembly…')
    setErrorMsg(null)

    api.assembleStream(
      projectId,
      (event) => {
        if (event.stage === 'done') {
          setOutputPath(event.output_path ?? null)
          setPhase(DONE)
        } else if (event.stage === 'error') {
          setErrorMsg(event.message ?? 'Assembly failed.')
          setPhase(ERROR)
        } else {
          setMessage(event.message ?? '')
        }
      },
      controller.signal,
    ).catch((e) => {
      if (e.name !== 'AbortError') {
        setErrorMsg(e.message ?? 'Assembly failed.')
        setPhase(ERROR)
      }
    })
  }

  function handleRetry() {
    setPhase(INITIAL)
    setMessage('')
    setOutputPath(null)
    setErrorMsg(null)
  }

  if (phase === DONE) {
    return (
      <div className="flex flex-col items-center gap-6 py-20 max-w-xl mx-auto">
        <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center text-3xl">
          ✓
        </div>
        <h2 className="text-2xl font-bold text-gray-800">Assembly complete!</h2>
        {outputPath && (
          <div className="w-full rounded-xl bg-gray-50 border border-gray-200 px-5 py-4">
            <p className="text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">Output file</p>
            <p className="font-mono text-sm text-gray-700 break-all">{outputPath}</p>
          </div>
        )}
        <p className="text-sm text-gray-400 text-center">
          Your video is saved at the path above. Open it in your preferred player.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-6 py-20 max-w-xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-800">Export</h2>

      {phase === INITIAL && (
        <>
          <p className="text-gray-500 text-sm text-center max-w-sm">
            Your edit plan is approved. Click below to assemble your final video.
          </p>
          <button
            onClick={handleStart}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold"
          >
            Start Assembly
          </button>
        </>
      )}

      {phase === STREAMING && (
        <>
          <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-600">{message}</p>
          <div className="w-full max-w-sm h-2 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-indigo-400 rounded-full animate-pulse w-full" />
          </div>
          <p className="text-xs text-gray-400">This may take a few minutes…</p>
        </>
      )}

      {phase === ERROR && (
        <>
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600 w-full max-w-sm">
            {errorMsg}
          </div>
          <button
            onClick={handleRetry}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold"
          >
            Try Again
          </button>
        </>
      )}
    </div>
  )
}
