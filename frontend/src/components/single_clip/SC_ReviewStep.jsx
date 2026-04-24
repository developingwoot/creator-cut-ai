import { useRef, useState } from 'react'
import { api } from '../../api/client'

function TranscriptViewer({ transcript, fillerSpans }) {
  if (!transcript || transcript.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic">No transcript available for this clip.</p>
    )
  }

  const fillerRanges = fillerSpans || []

  function isInFillerSpan(start, end) {
    return fillerRanges.some((f) => f.start < end && f.end > start)
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-4 max-h-48 overflow-y-auto text-sm text-gray-700 leading-relaxed">
      {transcript.map((seg, i) => (
        <span
          key={i}
          className={isInFillerSpan(seg.start, seg.end) ? 'bg-yellow-100 text-yellow-800 rounded px-0.5' : ''}
          title={isInFillerSpan(seg.start, seg.end) ? 'Filler word detected' : undefined}
        >
          {seg.text}{' '}
        </span>
      ))}
    </div>
  )
}

export default function SC_ReviewStep({
  projectId,
  transcript,
  fillerSpans,
  silenceSpans,
  renameSuggestions,
  onDone,
  onBack,
}) {
  const [chosenFilename, setChosenFilename] = useState(renameSuggestions?.[0] ?? '')
  const [removeFillers, setRemoveFillers] = useState((fillerSpans?.length ?? 0) > 0)
  const [removeSilence, setRemoveSilence] = useState(false)
  const [phase, setPhase] = useState('idle') // idle | applying | done | error
  const [applyMessage, setApplyMessage] = useState('')
  const abortRef = useRef(null)

  const fillerCount = fillerSpans?.length ?? 0
  const silenceCount = silenceSpans?.length ?? 0

  function selectSuggestion(name) {
    setChosenFilename(name)
  }

  async function handleApply() {
    setPhase('applying')
    setApplyMessage('Applying edits…')

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await api.singleClipApplyStream(
        projectId,
        {
          remove_fillers: removeFillers,
          remove_silence: removeSilence,
          chosen_filename: chosenFilename.trim() || null,
        },
        (event) => {
          if (event.stage === 'error') {
            setPhase('error')
            setApplyMessage(event.message || 'Apply failed.')
          } else if (event.stage === 'done') {
            setPhase('done')
            onDone(event.output_path)
          } else {
            setApplyMessage(event.message || '')
          }
        },
        controller.signal,
      )
    } catch (err) {
      if (err.name !== 'AbortError') {
        setPhase('error')
        setApplyMessage(err.message || 'Connection error.')
      }
    }
  }

  return (
    <div className="flex flex-col gap-8 py-10 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-800">Review & Apply Edits</h2>

      {/* ── Rename section ──────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Rename clip</h3>
        <div className="flex flex-wrap gap-2">
          {(renameSuggestions ?? []).map((name) => (
            <button
              key={name}
              onClick={() => selectSuggestion(name)}
              className={[
                'px-3 py-1.5 rounded-full text-sm border transition',
                chosenFilename === name
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'border-gray-300 text-gray-700 hover:border-indigo-400 hover:text-indigo-600',
              ].join(' ')}
            >
              {name}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={chosenFilename}
          onChange={(e) => setChosenFilename(e.target.value)}
          placeholder="Custom name (no extension)"
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <p className="text-xs text-gray-400">The output file will be saved with this name.</p>
      </section>

      {/* ── Transcript section ──────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Transcript
          {fillerCount > 0 && (
            <span className="ml-2 normal-case font-normal text-yellow-700 bg-yellow-100 rounded-full px-2 py-0.5">
              {fillerCount} filler{fillerCount > 1 ? 's' : ''} highlighted
            </span>
          )}
        </h3>
        <TranscriptViewer transcript={transcript} fillerSpans={fillerSpans} />
      </section>

      {/* ── Edit options ────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Edit options</h3>
        <label
          className={[
            'flex items-start gap-3 rounded-xl border px-4 py-3 cursor-pointer transition',
            fillerCount === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:border-indigo-300',
            removeFillers && fillerCount > 0 ? 'border-indigo-300 bg-indigo-50' : 'border-gray-200',
          ].join(' ')}
        >
          <input
            type="checkbox"
            checked={removeFillers}
            onChange={(e) => setRemoveFillers(e.target.checked)}
            disabled={fillerCount === 0}
            className="mt-0.5 accent-indigo-600"
          />
          <div>
            <p className="text-sm font-medium text-gray-800">
              Remove filler words
              <span className="ml-2 text-gray-500 font-normal">
                ({fillerCount} detected)
              </span>
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              Cuts um, uh, like, you know, and similar words.
            </p>
          </div>
        </label>

        <label
          className={[
            'flex items-start gap-3 rounded-xl border px-4 py-3 cursor-pointer transition',
            silenceCount === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:border-indigo-300',
            removeSilence && silenceCount > 0 ? 'border-indigo-300 bg-indigo-50' : 'border-gray-200',
          ].join(' ')}
        >
          <input
            type="checkbox"
            checked={removeSilence}
            onChange={(e) => setRemoveSilence(e.target.checked)}
            disabled={silenceCount === 0}
            className="mt-0.5 accent-indigo-600"
          />
          <div>
            <p className="text-sm font-medium text-gray-800">
              Remove silence / dead air
              <span className="ml-2 text-gray-500 font-normal">
                ({silenceCount} span{silenceCount !== 1 ? 's' : ''} detected)
              </span>
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              Removes pauses longer than 0.5 s at −30 dB.
            </p>
          </div>
        </label>
      </section>

      {/* ── Apply feedback ──────────────────────────────────────────────── */}
      {phase === 'applying' && (
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          {applyMessage}
        </div>
      )}
      {phase === 'error' && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {applyMessage}
        </div>
      )}

      {/* ── Action row ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-100">
        <button
          onClick={onBack}
          disabled={phase === 'applying'}
          className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ← Back
        </button>
        <button
          onClick={handleApply}
          disabled={phase === 'applying' || !chosenFilename.trim()}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold disabled:bg-indigo-300 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {phase === 'applying' && (
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          )}
          Apply Edits & Save
        </button>
      </div>
    </div>
  )
}
