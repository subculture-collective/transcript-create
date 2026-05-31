import { Link } from 'react-router-dom';

export default function UpgradeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="surface-card w-full max-w-md">
        <div className="archive-eyebrow mb-3">Pro export gate</div>
        <div className="mb-2 text-xl font-semibold tracking-[-0.03em] text-ink">Upgrade to export</div>
        <p className="text-sm leading-6 text-muted">
          Exports (SRT/VTT/JSON/PDF) are a Pro feature. Upgrade for unlimited search and full exports.
        </p>
        <div className="mt-5 flex justify-end gap-2">
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
