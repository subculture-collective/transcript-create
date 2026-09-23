import type { VideoInfo } from '../../types/api';
import VideoMetadataChips from '../archive/VideoMetadataChips';

type Props = {
  video: VideoInfo;
};

const topicHref = (label: string) => `/topics/${encodeURIComponent(label)}`;

export default function VideoDetailsPanel({ video }: Props) {
  const people = (video.people ?? []).map((person) => ({
    key: person.slug,
    label: person.display_name,
  }));
  const tags = (video.tags ?? []).map((tag) => ({ key: tag.slug, label: tag.label }));

  if (people.length === 0 && tags.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      {people.length > 0 && (
        <section className="flex flex-wrap items-center gap-2" aria-label="People on stream">
          <span className="meta-label">Featuring</span>
          <VideoMetadataChips
            label="People on stream"
            items={people}
            limit={null}
            hrefFor={topicHref}
          />
        </section>
      )}
      {tags.length > 0 && (
        <section className="flex flex-wrap items-center gap-2" aria-label="Content tags">
          <span className="meta-label">Filed under</span>
          <VideoMetadataChips label="Content tags" items={tags} limit={null} hrefFor={topicHref} />
        </section>
      )}
    </div>
  );
}
