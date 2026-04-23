import { useEffect, useState } from 'react'
import { api } from '../../api/client'

function fmtSeconds(s) {
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60).toString().padStart(2, '0')
  return `${m}:${sec}`
}

function SegmentCard({ seg }) {
  const duration = seg.source_end - seg.source_start
  return (
    <div className="px-5 py-4 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-gray-400 w-5 text-right">{seg.order}</span>
        <span
          className={[
            'text-xs font-semibold px-2 py-0.5 rounded-full',
            seg.is_broll
              ? 'bg-purple-100 text-purple-700'
              : 'bg-indigo-100 text-indigo-700',
          ].join(' ')}
        >
          {seg.is_broll ? 'B-roll' : 'A-roll'}
        </span>
        <span className="font-mono text-xs text-gray-500">{seg.clip_id.slice(0, 8)}</span>
        <span className="text-sm text-gray-700">
          {fmtSeconds(seg.source_start)} → {fmtSeconds(seg.source_end)}
          <span className="text-gray-400 ml-1">({fmtSeconds(duration)})</span>
        </span>
        {seg.b_roll_overlays?.length > 0 && (
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
            {seg.b_roll_overlays.length} B-roll overlay{seg.b_roll_overlays.length > 1 ? 's' : ''}
          </span>
        )}
        {seg.sound_cues?.length > 0 && (
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
            {seg.sound_cues.length} sound cue{seg.sound_cues.length > 1 ? 's' : ''}
          </span>
        )}
      </div>
      {seg.narration_note && (
        <p className="text-xs italic text-gray-400 pl-7">{seg.narration_note}</p>
      )}
    </div>
  )
}

export default function ReviewStep({ projectId, onNext, onBack }) {
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [rejecting, setRejecting] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [rejected, setRejected] = useState(false)

  useEffect(() => {
    api.getEditPlan(projectId)
      .then(setPlan)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId])

  async function handleApprove() {
    setSubmitting(true)
    setError(null)
    try {
      await api.approveEditPlan(projectId, true)
      onNext()
    } catch (e) {
      setError(e.message)
      setSubmitting(false)
    }
  }

  async function handleReject() {
    setSubmitting(true)
    setError(null)
    try {
      await api.approveEditPlan(projectId, false, feedback)
      setRejected(true)
    } catch (e) {
      setError(e.message)
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center gap-4 py-24">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-400 text-sm">Loading edit plan…</p>
      </div>
    )
  }

  if (rejected) {
    return (
      <div className="flex flex-col items-center gap-6 py-24">
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-6 py-4 text-sm text-amber-700 max-w-md text-center">
          Plan rejected. Go back to re-run analysis with your feedback.
        </div>
        <button onClick={onBack} className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold">
          Back to Analysis
        </button>
      </div>
    )
  }

  const segments = plan?.segments ?? []

  return (
    <div className="flex flex-col gap-6 py-10 max-w-2xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Review Edit Plan</h2>
        <p className="text-gray-500 mt-1 text-sm">
          Approve to start assembly, or request changes to regenerate.
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {plan && (
        <>
          <div className="rounded-xl bg-gray-50 border border-gray-200 px-5 py-4 space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-gray-700">Total duration</span>
              <span className="text-sm text-gray-500">
                {fmtSeconds(plan.total_duration_seconds ?? 0)}
              </span>
              <span className="text-sm text-gray-400">·</span>
              <span className="text-sm text-gray-500">{segments.length} segment{segments.length !== 1 ? 's' : ''}</span>
            </div>
            {plan.reasoning && (
              <p className="text-xs text-gray-500 leading-relaxed">{plan.reasoning}</p>
            )}
          </div>

          <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 overflow-hidden">
            {segments.length === 0 ? (
              <p className="px-5 py-6 text-sm text-gray-400 italic">No segments in this plan.</p>
            ) : (
              segments.map((seg) => <SegmentCard key={seg.order} seg={seg} />)
            )}
          </div>
        </>
      )}

      {rejecting ? (
        <div className="space-y-3">
          <label className="block text-sm font-medium text-gray-700">
            Feedback for regeneration
          </label>
          <textarea
            rows={4}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe what you'd like changed (min. 10 characters)…"
            className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
          <div className="flex gap-3">
            <button
              onClick={() => { setRejecting(false); setFeedback('') }}
              disabled={submitting}
              className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleReject}
              disabled={submitting || feedback.trim().length < 10}
              className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition font-semibold disabled:bg-red-300 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {submitting && (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              Confirm Rejection
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            disabled={submitting}
            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition disabled:cursor-not-allowed"
          >
            Back
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setRejecting(true)}
              disabled={submitting || !plan}
              className="px-5 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50 transition disabled:cursor-not-allowed disabled:text-gray-300"
            >
              Request Changes
            </button>
            <button
              onClick={handleApprove}
              disabled={submitting || !plan}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-semibold disabled:bg-indigo-300 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {submitting && (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              Approve & Assemble
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
