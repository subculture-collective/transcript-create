import { Link } from 'react-router-dom';

export default function UpgradeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-4 shadow-lg">
        <div className="mb-2 text-lg font-semibold">Upgrade to export</div>
        <p className="text-sm text-gray-700">
          Exports (SRT/VTT/JSON/PDF) are a Pro feature. Upgrade for unlimited search and full
          exports.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border px-3 py-1.5">
            Close
          </button>
          <Link to="/pricing" className="rounded bg-stone-900 px-3 py-1.5 text-white">
            See pricing
          </Link>
        </div>
      </div>
    </div>
  );
}
