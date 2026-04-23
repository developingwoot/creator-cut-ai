import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import ClipSelector from './components/upload/ClipSelector'
import BriefForm from './components/brief/BriefForm'
import AnalysisProgress from './components/analysis/AnalysisProgress'

const STEPS = [
  { id: 1, label: 'Upload' },
  { id: 2, label: 'Brief' },
  { id: 3, label: 'Analysis' },
  { id: 4, label: 'Review' },
  { id: 5, label: 'Export' },
]

function StepIndicator({ currentStep }) {
  return (
    <nav className="flex items-center justify-center gap-0">
      {STEPS.map((step, i) => {
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
            {i < STEPS.length - 1 && (
              <div className={`w-16 h-0.5 mb-4 ${done ? 'bg-indigo-600' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </nav>
  )
}

function UploadStep({ projectId, onNext }) {
  const [clips, setClips] = useState([])

  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Select Your Footage</h2>
      <p className="text-gray-500 max-w-md text-center">
        Pick your raw video clips from disk. Files stay where they are — nothing is copied.
      </p>
      <ClipSelector projectId={projectId} onRegistered={setClips} />
      <button
        onClick={onNext}
        disabled={clips.length === 0}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold disabled:bg-indigo-300 disabled:cursor-not-allowed"
      >
        Continue
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

function AnalysisStep({ projectId, brief, onNext }) {
  if (!brief) {
    return (
      <div className="py-16 text-center text-gray-500">
        No brief found — go back and fill in the story brief.
      </div>
    )
  }
  return <AnalysisProgress projectId={projectId} brief={brief} onNext={onNext} />
}

function ReviewStep({ onNext, onBack }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Review Edit Plan</h2>
      <p className="text-gray-500 max-w-md text-center">
        Review the AI's proposed edit. Approve to start assembly, or reject with feedback
        to regenerate.
      </p>
      <div className="w-full max-w-lg bg-gray-50 border rounded-xl p-6 space-y-3 text-sm text-gray-700">
        <p className="font-semibold text-gray-800">Proposed segments:</p>
        <p className="text-gray-400 italic">Edit plan will appear here after analysis completes.</p>
      </div>
      <div className="flex gap-4">
        <button onClick={onBack} className="px-6 py-2 border rounded-lg text-gray-600 hover:bg-gray-50 transition">
          Back
        </button>
        <button
          onClick={onNext}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold"
        >
          Approve & Assemble
        </button>
      </div>
    </div>
  )
}

function ExportStep({ onBack }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Export</h2>
      <p className="text-gray-500 max-w-md text-center">
        Your video is being assembled. When it's done, you can download the finished file.
      </p>
      <div className="w-32 h-32 rounded-full bg-indigo-100 flex items-center justify-center text-4xl text-indigo-600">
        🎬
      </div>
      <p className="text-gray-400 text-sm">Assembly in progress…</p>
      <button
        disabled
        className="px-6 py-2 bg-indigo-300 text-white rounded-lg font-semibold cursor-not-allowed"
      >
        Download (ready soon)
      </button>
    </div>
  )
}

export default function App() {
  const [step, setStep] = useState(1)
  const [projectId, setProjectId] = useState(null)
  const [brief, setBrief] = useState(null)
  const creatingProject = useRef(false)

  useEffect(() => {
    if (creatingProject.current) return
    creatingProject.current = true
    api.createProject('New Project').then((project) => setProjectId(project.id))
  }, [])

  function goNext(data) {
    if (step === 2 && data) setBrief(data)
    setStep((s) => Math.min(s + 1, STEPS.length))
  }

  function goBack() {
    setStep((s) => Math.max(s - 1, 1))
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
        <span className="font-bold text-xl text-indigo-600 tracking-tight">CreatorCutAI</span>
        <StepIndicator currentStep={step} />
        <div className="w-32" />
      </header>

      <main className="max-w-3xl mx-auto px-6">
        {step === 1 && <UploadStep projectId={projectId} onNext={goNext} onBack={goBack} />}
        {step === 2 && <BriefStep onNext={goNext} onBack={goBack} />}
        {step === 3 && <AnalysisStep projectId={projectId} brief={brief} onNext={goNext} />}
        {step === 4 && <ReviewStep onNext={goNext} onBack={goBack} />}
        {step === 5 && <ExportStep onBack={goBack} />}
      </main>
    </div>
  )
}
