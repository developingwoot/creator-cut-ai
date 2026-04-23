import { useState } from 'react'

export default function BriefForm({ onSubmit, onBack, error }) {
  const [form, setForm] = useState({
    title: '',
    story_summary: '',
    target_duration_seconds: '',
    tone: '',
  })

  function set(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const isValid =
    form.title.trim() &&
    form.story_summary.trim() &&
    Number(form.target_duration_seconds) > 0 &&
    form.tone.trim()

  function handleSubmit(e) {
    e.preventDefault()
    if (!isValid) return
    onSubmit({
      title: form.title.trim(),
      story_summary: form.story_summary.trim(),
      target_duration_seconds: Number(form.target_duration_seconds),
      tone: form.tone.trim(),
    })
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Story Brief</h2>
      <p className="text-gray-500 mb-8">Tell the AI what story you want to tell.</p>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Video title
          </label>
          <input
            type="text"
            value={form.title}
            onChange={set('title')}
            placeholder="e.g. My Weekend in Tokyo"
            className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Story summary
          </label>
          <textarea
            rows={4}
            value={form.story_summary}
            onChange={set('story_summary')}
            placeholder="Describe the story arc, key moments, and what you want viewers to feel..."
            className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Target duration (seconds)
            </label>
            <input
              type="number"
              min="1"
              value={form.target_duration_seconds}
              onChange={set('target_duration_seconds')}
              placeholder="e.g. 600"
              className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tone
            </label>
            <input
              type="text"
              value={form.tone}
              onChange={set('tone')}
              placeholder="e.g. upbeat, cinematic, reflective"
              className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="flex justify-between pt-2">
          <button
            type="button"
            onClick={onBack}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition"
          >
            Back
          </button>
          <button
            type="submit"
            disabled={!isValid}
            className={`px-6 py-2 rounded-lg text-sm font-medium text-white transition ${
              isValid
                ? 'bg-indigo-600 hover:bg-indigo-700'
                : 'bg-indigo-300 cursor-not-allowed'
            }`}
          >
            Start Analysis
          </button>
        </div>
      </form>
    </div>
  )
}
