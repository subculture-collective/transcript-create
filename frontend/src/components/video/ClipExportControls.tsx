import { useState } from 'react';
import { useAuth } from '../../services';
import { buildApiUrl, http } from '../../services/api';
import type { PassageRange } from '../../features/passages/range';

type ClipJob = { id: string; status: string; expires_at: number; error?: string | null };
export default function ClipExportControls({
  videoId,
  range,
}: {
  videoId: string;
  range: PassageRange;
}) {
  const { user } = useAuth();
  const [job, setJob] = useState<ClipJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function request() {
    setBusy(true);
    setError('');
    try {
      setJob(
        await http
          .post('clips', {
            json: { video_id: videoId, start_ms: range.startMs, end_ms: range.endMs },
          })
          .json<ClipJob>()
      );
    } catch {
      setError(
        'Export unavailable. This account needs an authorized, registered original, a selection of at most two minutes, and available rendering capacity.'
      );
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    if (!job) return;
    setBusy(true);
    setError('');
    try {
      setJob(await http.get(`clips/${job.id}`).json<ClipJob>());
    } catch {
      setJob(undefined);
      setError('This export is no longer available to this account.');
    } finally {
      setBusy(false);
    }
  }
  if (!user)
    return (
      <p className="text-sm text-muted mt-4">
        Sign in to request exports from your registered originals.
      </p>
    );
  return (
    <section
      className="mt-4 border-t border-border pt-4 space-y-2"
      aria-label="Original clip export"
    >
      <h3 className="font-semibold">Export from an authorized original</h3>
      <p className="text-sm text-muted">
        Available only to the registered original’s owner. Up to two minutes; downloads expire after
        24 hours. Nothing is published automatically.
      </p>
      <button
        type="button"
        className="btn-secondary"
        disabled={busy || range.endMs - range.startMs > 120000}
        onClick={() => void request()}
      >
        Request selected clip
      </button>
      {job && (
        <div className="space-y-2">
          <p role="status">
            Export {job.status}. Expires {new Date(job.expires_at * 1000).toLocaleString()}.
          </p>
          {job.error && <p role="alert">{job.error}</p>}
          {job.status === 'completed' ? (
            <a className="btn-primary" href={buildApiUrl(`clips/${job.id}/download`)}>
              Download private MP4
            </a>
          ) : (
            job.status !== 'expired' && (
              <button
                type="button"
                className="btn-ghost"
                disabled={busy}
                onClick={() => void refresh()}
              >
                Check export status
              </button>
            )
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm">
          {error}
        </p>
      )}
    </section>
  );
}
