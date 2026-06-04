import type { TranscriptResponse, VideoInfo } from '../../types/api';
import { formatDate, formatDuration, sourceLabel } from '../../features/archive/format';

type Props = {
  video: VideoInfo;
  transcriptSource?: TranscriptResponse['source'] | null;
};

export default function VideoDetailsPanel({ video, transcriptSource }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(16rem,0.8fr)]">
      <div className="rounded-lg border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">VOD details</div>
        <dl className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">Channel</dt>
            <dd className="mt-1 font-medium text-ink">{video.channel_name || 'Unknown channel'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">Upload date</dt>
            <dd className="mt-1 font-medium text-ink">{formatDate(video.uploaded_at ?? null)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">Duration</dt>
            <dd className="mt-1 font-medium text-ink">{formatDuration(video.duration_seconds)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">Transcript source</dt>
            <dd className="mt-1 font-medium text-ink">{sourceLabel(transcriptSource ?? 'best')}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">Video ID</dt>
            <dd className="mt-1 font-mono text-sm text-ink">{video.id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-subtle">YouTube ID</dt>
            <dd className="mt-1 font-mono text-sm text-ink">{video.youtube_id}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-lg border border-dashed border-border bg-surface p-4">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">Future work</div>
        <div className="mt-2 font-medium text-ink">Topic extraction coming later</div>
        <p className="mt-2 text-sm text-muted">
          This space stays intentionally disabled until citation-backed topic extraction exists.
        </p>
      </div>
    </div>
  );
}
