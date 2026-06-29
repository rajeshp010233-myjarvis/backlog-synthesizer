interface JiraConfirmModalProps {
  count: number;
  projectKey: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function JiraConfirmModal({ count, projectKey, onConfirm, onCancel }: JiraConfirmModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4 p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
            <span className="text-blue-600 text-lg">↑</span>
          </div>
          <div>
            <h2 className="font-semibold text-gray-900 text-base">Create tickets in Jira?</h2>
            <p className="text-sm text-gray-500 mt-0.5">This action cannot be undone.</p>
          </div>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 mb-5 text-sm text-gray-700 space-y-1">
          <p><span className="font-medium">Project:</span> {projectKey}</p>
          <p><span className="font-medium">Stories to create:</span> {count}</p>
          <p className="text-xs text-gray-400 pt-1">
            Each ticket will include the full acceptance criteria and source evidence
            (transcript, speaker, and original quote) for traceability.
          </p>
        </div>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            Yes, create {count} ticket{count > 1 ? "s" : ""}
          </button>
        </div>
      </div>
    </div>
  );
}
