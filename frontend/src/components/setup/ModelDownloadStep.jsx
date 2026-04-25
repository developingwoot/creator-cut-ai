import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

const TIER_LABELS = {
  default: 'Standard (≥16 GB RAM) — best quality',
  low_spec: 'Low-spec (<16 GB RAM) — faster, smaller models',
}

function formatBytes(bytes) {
  if (!bytes) return ''
  const gb = bytes / (1024 ** 3)
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  const mb = bytes / (1024 ** 2)
  return `${mb.toFixed(0)} MB`
}

function ModelRow({ model, onPull }) {
  const [progress, setProgress] = useState(null) // null = not started, {completed, total, status}
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  async function handlePull() {
    setProgress({ completed: 0, total: 0, status: 'starting' })
    setError(null)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await api.pullModel(
        model,
        (event) => {
          if (event.status === 'success') {
            setDone(true)
            onPull()
          } else if (event.status === 'error') {
            setError(event.message || 'Pull failed')
            setProgress(null)
          } else {
            setProgress({ completed: event.completed || 0, total: event.total || 0, status: event.status })
          }
        },
        controller.signal,
      )
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
      setProgress(null)
    }
  }

  const pct = progress && progress.total > 0
    ? Math.round((progress.completed / progress.total) * 100)
    : null

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-sm text-gray-800">{model}</span>
        {done ? (
          <span className="text-sm font-medium text-green-600">✓ Ready</span>
        ) : progress ? (
          <span className="text-xs text-gray-500">
            {progress.status}
            {pct !== null ? ` ${pct}%` : ''}
            {progress.total > 0 ? ` · ${formatBytes(progress.completed)} / ${formatBytes(progress.total)}` : ''}
          </span>
        ) : (
          <button
            onClick={handlePull}
            className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 transition"
          >
            Pull
          </button>
        )}
      </div>
      {progress && !done && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className="h-2 rounded-full bg-indigo-500 transition-all"
            style={{ width: pct !== null ? `${pct}%` : '100%' }}
          />
        </div>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

export default function ModelDownloadStep({ onReady }) {
  const [tier, setTier] = useState(null)
  const [status, setStatus] = useState(null) // { installed, required, missing, ollama_reachable }
  const [tierOverride, setTierOverride] = useState(null)
  const [pulledModels, setPulledModels] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [ollamaError, setOllamaError] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const [tierData, statusData] = await Promise.all([
        api.getModelTier(),
        api.getModelStatus(),
      ])
      setTier(tierData)
      setStatus(statusData)
      if (!statusData.ollama_reachable) setOllamaError(true)
    } catch {
      setOllamaError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Re-check whenever a pull completes
  async function handlePulled() {
    const s = await api.getModelStatus().catch(() => null)
    if (s) setStatus(s)
    if (s && s.missing.length === 0) onReady()
  }

  // Auto-advance if all models already installed
  useEffect(() => {
    if (status && status.missing.length === 0 && status.ollama_reachable) onReady()
  }, [status])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Checking Ollama…</p>
      </div>
    )
  }

  if (ollamaError || !status?.ollama_reachable) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h2 className="text-xl font-semibold text-gray-900 mb-3">Ollama required</h2>
        <p className="text-gray-600 mb-6">
          CreatorCutAI runs AI models locally via Ollama. Install it to continue.
        </p>
        <a
          href="https://ollama.com/download"
          target="_blank"
          rel="noreferrer"
          className="inline-block rounded-lg bg-indigo-600 px-6 py-3 text-sm font-medium text-white hover:bg-indigo-700 transition"
        >
          Download Ollama
        </a>
        <button
          onClick={load}
          className="mt-4 block mx-auto text-sm text-indigo-600 hover:underline"
        >
          Re-check
        </button>
      </div>
    )
  }

  const activeTier = tierOverride || tier?.tier
  const required = tier ? (
    activeTier === 'default'
      ? [tier.vlm, tier.llm]
      : [
          activeTier === 'low_spec' && tier.tier === 'low_spec' ? tier.vlm : 'moondream:1.8b',
          activeTier === 'low_spec' && tier.tier === 'low_spec' ? tier.llm : 'llama3.2:3b-instruct',
        ]
  ) : []
  const missing = status ? status.missing : []
  const modelsToShow = required.length > 0 ? required : missing

  return (
    <div className="mx-auto max-w-lg py-12">
      <h2 className="text-2xl font-semibold text-gray-900 mb-2">First-run setup</h2>
      <p className="text-gray-600 mb-6">
        CreatorCutAI needs two local AI models. These are downloaded once and stored on your machine.
        All inference runs locally — nothing is sent to the cloud.
      </p>

      {/* Tier selector */}
      <div className="mb-6">
        <p className="text-sm font-medium text-gray-700 mb-2">
          Detected tier: <span className="font-semibold">{tier?.tier}</span>
        </p>
        <div className="flex gap-3">
          {['default', 'low_spec'].map((t) => (
            <button
              key={t}
              onClick={() => setTierOverride(t === tier?.tier ? null : t)}
              className={`flex-1 rounded-lg border px-3 py-2 text-xs text-left transition ${
                activeTier === t
                  ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
              }`}
            >
              <div className="font-medium mb-0.5">
                {t === 'default' ? 'Standard (~11 GB)' : 'Low-spec (~4 GB)'}
              </div>
              <div className="text-xs opacity-75">
                {t === 'default'
                  ? 'qwen2.5vl:7b + qwen2.5:7b-instruct'
                  : 'moondream:1.8b + llama3.2:3b-instruct'}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Model rows */}
      <div className="flex flex-col gap-3 mb-6">
        {modelsToShow.map((model) => (
          <ModelRow key={model} model={model} onPull={handlePulled} />
        ))}
      </div>

      {missing.length === 0 && (
        <button
          onClick={onReady}
          className="w-full rounded-lg bg-indigo-600 py-3 text-sm font-medium text-white hover:bg-indigo-700 transition"
        >
          Continue →
        </button>
      )}

      <p className="mt-4 text-center text-xs text-gray-400">
        Disk space required: {activeTier === 'default' ? '~11.2 GB' : '~4.2 GB'} for models
      </p>
    </div>
  )
}
