import { Link } from 'react-router-dom';
import type { DateField } from '../../features/streams/library';
import { formatDate, formatDuration } from '../../features/streams/library';
import type { VideoInfo } from '../../types/api';

type StreamCardProps = {
  video: VideoInfo;
  dateField: DateField;
};

export default function StreamCard({ video, dateField }: StreamCardProps) {
  const title = video.title || `Video ${video.youtube_id}`;
  const dateValue = video[dateField];

  return (
    <Link to={`/v/${video.id}`} className="surface-card-compact group flex h-full flex-col overflow-hidden border border-border/80 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:shadow-lg">
      <div className="relative overflow-hidden rounded-xl border border-border/60 bg-surface-muted">
        <img
          src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
          alt={title}
          loading="lazy"
          className="aspect-video w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
        />
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-black/75 via-black/25 to-transparent px-3 py-2 text-xs text-white">
          <span className="inline-flex items-center justify-center rounded-full bg-black/60 px-2 pb-[3px] pt-[7px] text-center font-medium leading-none backdrop-blur">
            {formatDuration(video.duration_seconds)}
          </span>
          <span className="inline-flex items-center justify-center rounded-full bg-black/60 px-2 pb-[3px] pt-[7px] text-center font-medium leading-none backdrop-blur">
            {formatDate(dateValue ?? null)}
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="space-y-2">
          <h2 className="line-clamp-2 text-lg font-semibold tracking-tight text-ink group-hover:text-accent">
            {title}
          </h2>
          <div className="text-sm text-muted">
            <div className="line-clamp-1">{video.channel_name || 'Unknown channel'}</div>
          </div>
        </div>

        <div className="mt-auto space-y-2 text-sm text-muted">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{formatDate(dateValue ?? null)}</span>
            {video.updated_at && <span>Updated {formatDate(video.updated_at)}</span>}
          </div>
        </div>
      </div>
    </Link>
  );
}
