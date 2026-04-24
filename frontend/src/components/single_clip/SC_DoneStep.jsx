export default function SC_DoneStep({ outputPath, onReset }) {
  return (
    <div className="flex flex-col items-center gap-8 py-20 text-center">
      <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center text-4xl">
        ✓
      </div>
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Your clip is ready</h2>
        <p className="mt-2 text-gray-500 text-sm">The edited file has been saved to:</p>
        <p className="mt-3 font-mono text-sm text-gray-700 bg-gray-100 rounded-lg px-4 py-3 break-all max-w-lg mx-auto">
          {outputPath}
        </p>
      </div>
      <button
        onClick={onReset}
        className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition font-medium"
      >
        Start over
      </button>
    </div>
  )
}
