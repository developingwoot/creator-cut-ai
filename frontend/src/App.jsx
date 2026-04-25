import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import ClipSelector from './components/upload/ClipSelector'
import BriefForm from './components/brief/BriefForm'
import AnalysisProgress from './components/analysis/AnalysisProgress'
import ReviewStep from './components/timeline/ReviewStep'
import ExportStep from './components/export/ExportStep'
import WorkflowSelector from './components/workflow_selector/WorkflowSelector'
import SC_UploadStep from './components/single_clip/SC_UploadStep'
import SC_ProcessStep from './components/single_clip/SC_ProcessStep'
import SC_ReviewStep from './components/single_clip/SC_ReviewStep'
import SC_DoneStep from './components/single_clip/SC_DoneStep'
import ModelDownloadStep from './components/setup/ModelDownloadStep'

const MOVIE_STEPS = [
  { id: 1, label: 'Upload' },
  { id: 2, label: 'Brief' },
  { id: 3, label: 'Analysis' },
  { id: 4, label: 'Review' },
  { id: 5, label: 'Export' },
]

const SC_STEPS = [
  { id: 1, label: 'Upload' },
  { id: 2, label: 'Process' },
  { id: 3, label: 'Edit' },
]

function MovieStepIndicator({ currentStep }) {
  return (
    <nav className="flex items-center justify-center gap-0">
      {MOVIE_STEPS.map((step, i) => {
        const done = step.id < currentStep
        const active = step.id === currentStep
        return (
          <div key={step.id} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold',
                  done ? 'bg-indigo-600 text-white' : '',
                  active ? 'bg-indigo-600 text-white ring-4 ring-indigo-200' : '',
                  !done && !active ? 'bg-gray-200 text-gray-500' : '',
                ].join(' ')}
              >
                {done ? '✓' : step.id}
              </div>
              <span className={`mt-1 text-xs ${active ? 'text-indigo-600 font-semibold' : 'text-gray-400'}`}>
                {step.label}
              </span>
            </div>
            {i < MOVIE_STEPS.length - 1 && (
              <div className={`w-16 h-0.5 mb-4 ${done ? 'bg-indigo-600' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </nav>
  )
}

function SCStepIndicator({ currentStep }) {
  return (
    <p className="text-sm text-gray-500">
      Step <span className="font-semibold text-gray-700">{currentStep}</span> of {SC_STEPS.length}
      {' — '}
      <span className="text-indigo-600 font-medium">
        {SC_STEPS.find((s) => s.id === currentStep)?.label}
      </span>
    </p>
  )
}

function UploadStep({ projectId, projectLoading, onNext }) {
  const [clips, setClips] = useState([])

  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Select Your Footage</h2>
      <p className="text-gray-500 max-w-md text-center">
        Pick your raw video clips from disk. Files stay where they are — nothing is copied.
      </p>
      {projectLoading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-indigo-500 rounded-full animate-spin" />
          Initialising project…
        </div>
      ) : (
        <ClipSelector projectId={projectId} onRegistered={setClips} />
      )}
      <button
        onClick={onNext}
        disabled={clips.length === 0}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold disabled:bg-indigo-300 disabled:cursor-not-allowed"
      >
        Continue{clips.length > 0 ? ` with ${clips.length} clip${clips.length > 1 ? 's' : ''}` : ''}
      </button>
    </div>
  )
}

function BriefStep({ onNext, onBack }) {
  const [error, setError] = useState(null)

  function handleSubmit(brief) {
    setError(null)
    onNext(brief)
  }

  return <BriefForm onSubmit={handleSubmit} onBack={onBack} error={error} />
}

function AnalysisStep({ projectId, brief, onNext, onBack }) {
  if (!brief) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-gray-500">No brief found — go back and fill in the story brief.</p>
        <button onClick={onBack} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition">
          Back to Brief
        </button>
      </div>
    )
  }
  return <AnalysisProgress projectId={projectId} brief={brief} onNext={onNext} onBack={onBack} />
}

export default function App() {
  // ── First-run model gate ──────────────────────────────────────────────────
  const [modelsReady, setModelsReady] = useState(false)

  // ── Shared state ──────────────────────────────────────────────────────────
  const [workflowMode, setWorkflowMode] = useState(null) // null | 'movie' | 'single_clip'
  const [projectId, setProjectId] = useState(null)
  const [projectError, setProjectError] = useState(null)
  const creatingProject = useRef(false)

  // ── Workflow 1 (movie) state ───────────────────────────────────────────────
  const [step, setStep] = useState(1)
  const [brief, setBrief] = useState(null)

  // ── Workflow 2 (single clip) state ────────────────────────────────────────
  const [scStep, setScStep] = useState(1)
  const [scProcessResult, setScProcessResult] = useState(null)
  const [scOutputPath, setScOutputPath] = useState(null)

  function initProject(name = 'New Project') {
    setProjectError(null)
    creatingProject.current = true
    api.createProject(name)
      .then((project) => {
        creatingProject.current = false
        setProjectId(project.id)
      })
      .catch((err) => {
        creatingProject.current = false
        setProjectError(err.message ?? 'Could not create project. Is the backend running?')
      })
  }

  useEffect(() => {
    if (!workflowMode || creatingProject.current || projectId) return
    const name = workflowMode === 'single_clip' ? 'Single Clip Edit' : 'New Project'
    initProject(name)
  }, [workflowMode]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleWorkflowSelect(mode) {
    setWorkflowMode(mode)
    setProjectId(null)
    setProjectError(null)
    creatingProject.current = false
  }

  function handleReset() {
    setWorkflowMode(null)
    setProjectId(null)
    setProjectError(null)
    setStep(1)
    setBrief(null)
    setScStep(1)
    setScProcessResult(null)
    setScOutputPath(null)
    creatingProject.current = false
  }

  function goNext(data) {
    if (step === 2 && data) setBrief(data)
    setStep((s) => Math.min(s + 1, MOVIE_STEPS.length))
  }

  function goBack() {
    setStep((s) => Math.max(s - 1, 1))
  }

  if (!modelsReady) {
    return (
      <div className="min-h-screen bg-white">
        <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
          <span className="font-bold text-xl text-indigo-600 tracking-tight">CreatorCutAI</span>
          <div /><div />
        </header>
        <main className="max-w-3xl mx-auto px-6">
          <ModelDownloadStep onReady={() => setModelsReady(true)} />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
        <span className="font-bold text-xl text-indigo-600 tracking-tight">CreatorCutAI</span>

        {workflowMode === 'movie' && <MovieStepIndicator currentStep={step} />}
        {workflowMode === 'single_clip' && scStep <= SC_STEPS.length && (
          <SCStepIndicator currentStep={scStep} />
        )}
        {!workflowMode && <div />}

        <div className="w-40 flex justify-end">
          {workflowMode && (
            <button
              onClick={handleReset}
              className="text-sm text-gray-400 hover:text-gray-600 transition"
            >
              ← Change workflow
            </button>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6">
        {projectError && (
          <div className="mt-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600 flex items-center justify-between">
            <span>{projectError}</span>
            <button
              onClick={() => { creatingProject.current = false; initProject(workflowMode === 'single_clip' ? 'Single Clip Edit' : 'New Project') }}
              className="ml-4 underline hover:no-underline shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {/* ── Workflow selector ─────────────────────────────────────── */}
        {!workflowMode && (
          <WorkflowSelector onSelect={handleWorkflowSelect} />
        )}

        {/* ── Workflow 1: Movie maker ───────────────────────────────── */}
        {workflowMode === 'movie' && (
          <>
            {step === 1 && (
              <UploadStep
                projectId={projectId}
                projectLoading={!projectId && !projectError}
                onNext={goNext}
                onBack={goBack}
              />
            )}
            {step === 2 && <BriefStep onNext={goNext} onBack={goBack} />}
            {step === 3 && (
              <AnalysisStep projectId={projectId} brief={brief} onNext={goNext} onBack={goBack} />
            )}
            {step === 4 && <ReviewStep projectId={projectId} onNext={goNext} onBack={goBack} />}
            {step === 5 && <ExportStep projectId={projectId} />}
          </>
        )}

        {/* ── Workflow 2: Single clip editor ────────────────────────── */}
        {workflowMode === 'single_clip' && (
          <>
            {scStep === 1 && (
              <SC_UploadStep
                projectId={projectId}
                onRegistered={() => {}}
                onNext={() => setScStep(2)}
              />
            )}
            {scStep === 2 && (
              <SC_ProcessStep
                projectId={projectId}
                onDone={(result) => {
                  setScProcessResult(result)
                  setScStep(3)
                }}
                onBack={() => setScStep(1)}
              />
            )}
            {scStep === 3 && scProcessResult && (
              <SC_ReviewStep
                projectId={projectId}
                transcript={scProcessResult.transcript}
                fillerSpans={scProcessResult.filler_spans}
                silenceSpans={scProcessResult.silence_spans}
                renameSuggestions={scProcessResult.rename_suggestions}
                onDone={(path) => {
                  setScOutputPath(path)
                  setScStep(4)
                }}
                onBack={() => setScStep(2)}
              />
            )}
            {scStep === 4 && (
              <SC_DoneStep outputPath={scOutputPath} onReset={handleReset} />
            )}
          </>
        )}
      </main>
    </div>
  )
}
