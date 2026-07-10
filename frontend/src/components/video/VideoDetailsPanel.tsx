import type { VideoInfo } from '../../types/api';
import { formatDate, formatDuration } from '../../features/archive/format';
import VideoMetadataChips from '../archive/VideoMetadataChips';

type Props = {
  video: VideoInfo;
};

export default function VideoDetailsPanel({ video }: Props) {
  const people = (video.people ?? []).map((person) => ({
    key: person.slug,
    label: person.display_name,
  }));
  const tags = (video.tags ?? []).map((tag) => ({ key: tag.slug, label: tag.label }));

  return (
    <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <dl className="grid flex-1 grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:max-w-2xl">
        <div>
          <dt className="meta-label">Channel</dt>
          <dd className="mt-1.5 font-medium text-ink">{video.channel_name || 'Unknown channel'}</dd>
        </div>
        <div>
          <dt className="meta-label">Broadcast</dt>
          <dd className="mt-1.5 font-mono text-sm text-ink">
            {formatDate(video.uploaded_at ?? null)}
          </dd>
        </div>
        <div>
          <dt className="meta-label">Runtime</dt>
          <dd className="mt-1.5 font-mono text-sm text-ink">
            {formatDuration(video.duration_seconds)}
          </dd>
        </div>
      </dl>

      {(people.length > 0 || tags.length > 0) && (
        <div className="flex max-w-2xl flex-col gap-3 lg:items-end">
          {people.length > 0 && (
            <section
              className="flex flex-wrap items-center gap-2 lg:justify-end"
              aria-label="People on stream"
            >
              <span className="meta-label mr-1">Featuring</span>
              <VideoMetadataChips label="People on stream" items={people} limit={null} />
            </section>
          )}
          {tags.length > 0 && (
            <section
              className="flex flex-wrap items-center gap-2 lg:justify-end"
              aria-label="Content tags"
            >
              <span className="meta-label mr-1">Filed under</span>
              <VideoMetadataChips label="Content tags" items={tags} limit={null} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}
