import type { VideoInfo } from '../../types/api';
import { formatDate, formatDuration } from '../../features/archive/format';
import VideoMetadataChips from '../archive/VideoMetadataChips';

type Props = {
  video: VideoInfo;
};

export default function VideoDetailsPanel({ video }: Props) {
  const people = (video.people ?? []).map((person) => ({ key: person.slug, label: person.display_name }));
  const tags = (video.tags ?? []).map((tag) => ({ key: tag.slug, label: tag.label }));

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
        </dl>

        {(people.length > 0 || tags.length > 0) && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {people.length > 0 && (
              <section className="space-y-2" aria-label="People on stream">
                <div className="meta-label">People on stream</div>
                <VideoMetadataChips label="People on stream" items={people} limit={null} />
              </section>
            )}
            {tags.length > 0 && (
              <section className="space-y-2" aria-label="Content tags">
                <div className="meta-label">Content tags</div>
                <VideoMetadataChips label="Content tags" items={tags} limit={null} />
              </section>
            )}
          </div>
        )}
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
