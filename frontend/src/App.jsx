import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import ClipSelector from './components/upload/ClipSelector'

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
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Story Brief</h2>
      <p className="text-gray-500 max-w-md text-center">
        Tell the AI what story you want to tell. The more context, the better the edit.
      </p>
      <div className="w-full max-w-lg flex flex-col gap-4">
        <input
          className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Video title"
        />
        <textarea
          className="border rounded-lg px-4 py-2 w-full h-28 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Story summary — what happens, who's in it, what feeling should the viewer leave with?"
        />
        <input
          className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Target duration (e.g. 8 minutes)"
        />
        <input
          className="border rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-indigo-400"
          placeholder="Tone (e.g. upbeat, cinematic, documentary)"
        />
      </div>
      <div className="flex gap-4">
        <button onClick={onBack} className="px-6 py-2 border rounded-lg text-gray-600 hover:bg-gray-50 transition">
          Back
        </button>
        <button
          onClick={onNext}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold"
        >
          Start Analysis
        </button>
      </div>
    </div>
  )
}

function AnalysisStep({ onNext, onBack }) {
  return (
    <div className="flex flex-col items-center gap-6 py-16">
      <h2 className="text-2xl font-bold text-gray-800">Analysing Footage</h2>
      <p className="text-gray-500 max-w-md text-center">
        The AI is reviewing your clips, transcribing audio, and building an edit plan.
        This takes a few minutes.
      </p>
      <div className="w-full max-w-lg bg-gray-100 rounded-xl p-6 font-mono text-sm text-gray-600 space-y-1 min-h-32">
        <p>⏳ Generating proxies…</p>
        <p className="text-gray-400">⏳ Transcribing audio…</p>
        <p className="text-gray-400">⏳ Analysing clips (Pass 1)…</p>
        <p className="text-gray-400">⏳ Planning edit (Pass 2)…</p>
      </div>
      <button
        onClick={onNext}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold"
      >
        View Edit Plan (demo)
      </button>
    </div>
  )
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

const STEP_COMPONENTS = [UploadStep, BriefStep, AnalysisStep, ReviewStep, ExportStep]

export default function App() {
  const [step, setStep] = useState(1)
  const [projectId, setProjectId] = useState(null)
  const creatingProject = useRef(false)

  useEffect(() => {
    if (creatingProject.current) return
    creatingProject.current = true
    api.createProject('New Project').then((project) => setProjectId(project.id))
  }, [])

  const StepComponent = STEP_COMPONENTS[step - 1]

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
        <span className="font-bold text-xl text-indigo-600 tracking-tight">CreatorCutAI</span>
        <StepIndicator currentStep={step} />
        <div className="w-32" />
      </header>

      <main className="max-w-3xl mx-auto px-6">
        <StepComponent
          projectId={projectId}
          onNext={() => setStep((s) => Math.min(s + 1, STEPS.length))}
          onBack={() => setStep((s) => Math.max(s - 1, 1))}
        />
      </main>
    </div>
  )
}
