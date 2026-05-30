import { Link } from 'react-router-dom';

export default function UpgradeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="surface-card w-full max-w-md">
        <div className="mb-2 text-lg font-semibold text-ink">Upgrade to export</div>
        <p className="text-sm text-muted">
          Exports (SRT/VTT/JSON/PDF) are a Pro feature. Upgrade for unlimited search and full
          exports.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">
            Close
          </button>
          <Link to="/pricing" className="btn-primary">
            See pricing
          </Link>
        </div>
      </div>
    </div>
  );
}
