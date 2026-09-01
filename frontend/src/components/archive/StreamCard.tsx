import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { DateField } from '../../features/streams/library';
import { formatDate, formatDuration } from '../../features/streams/library';
import type { VideoInfo } from '../../types/api';

type StreamCardProps = { video: VideoInfo; dateField: DateField };

export default function StreamCard({ video, dateField }: StreamCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const title = video.title || `Video ${video.youtube_id}`;
  const metadata = [
    ...(video.people ?? []).map((person) => person.display_name),
    ...(video.tags ?? []).map((tag) => tag.label),
  ].slice(0, 3);

  return (
    <article className="feed-card group">
      <Link
        to={`/v/${video.id}`}
        className="feed-card-media"
        aria-label={`Watch ${title} with transcript`}
      >
        {imageFailed ? (
          <div className="feed-card-image-fallback" role="img" aria-label="Thumbnail unavailable">
            <span aria-hidden="true">▶</span>
            <span>Preview unavailable</span>
          </div>
        ) : (
          <img
            src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
            alt=""
            loading="lazy"
            width="480"
            height="270"
            onError={() => setImageFailed(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.015]"
          />
        )}
        <div className="feed-card-overlay" aria-hidden="true">
          <span>{formatDate(video[dateField] ?? null)}</span>
          <span>{formatDuration(video.duration_seconds)}</span>
        </div>
      </Link>

      <div className="feed-card-body">
        <div className="min-w-0 flex-1">
          <Link to={`/v/${video.id}`} className="feed-card-title">
            {title}
          </Link>
          <p className="feed-card-support">
            {metadata.length > 0
              ? metadata.join(' · ')
              : video.channel_name || 'HasanAbi broadcast archive'}
          </p>
        </div>
        <details className="feed-card-menu">
          <summary aria-label={`More actions for ${title}`}>•••</summary>
          <div>
            <button type="button">Save</button>
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(`${location.origin}/v/${video.id}`)}
            >
              Copy link
            </button>
          </div>
        </details>
        <Link to={`/v/${video.id}`} className="feed-card-action">
          Watch with transcript <span aria-hidden="true">→</span>
        </Link>
      </div>
    </article>
  );
}
