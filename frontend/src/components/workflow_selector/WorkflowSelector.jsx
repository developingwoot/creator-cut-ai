export default function WorkflowSelector({ onSelect }) {
  return (
    <div className="flex flex-col items-center gap-10 py-20">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-gray-800">What would you like to do?</h2>
        <p className="mt-2 text-gray-500">Choose a workflow to get started.</p>
      </div>

      <div className="flex gap-6 flex-wrap justify-center">
        <button
          onClick={() => onSelect('movie')}
          className="group flex flex-col gap-4 items-start w-72 rounded-2xl border-2 border-gray-200 p-8 text-left transition hover:border-indigo-400 hover:shadow-md cursor-pointer bg-white"
        >
          <div className="text-4xl">🎬</div>
          <div>
            <h3 className="text-lg font-semibold text-gray-800 group-hover:text-indigo-600 transition">
              Create a Movie
            </h3>
            <p className="mt-1 text-sm text-gray-500">
              Upload multiple clips, describe your story, and let AI assemble a polished edit.
            </p>
          </div>
          <span className="mt-2 text-sm font-medium text-indigo-600 group-hover:underline">
            Start →
          </span>
        </button>

        <button
          onClick={() => onSelect('single_clip')}
          className="group flex flex-col gap-4 items-start w-72 rounded-2xl border-2 border-gray-200 p-8 text-left transition hover:border-indigo-400 hover:shadow-md cursor-pointer bg-white"
        >
          <div className="text-4xl">✂️</div>
          <div>
            <h3 className="text-lg font-semibold text-gray-800 group-hover:text-indigo-600 transition">
              Edit a Single Clip
            </h3>
            <p className="mt-1 text-sm text-gray-500">
              Upload one clip to transcribe it, remove fillers or silence, and rename it.
            </p>
          </div>
          <span className="mt-2 text-sm font-medium text-indigo-600 group-hover:underline">
            Start →
          </span>
        </button>
      </div>
    </div>
  )
}
