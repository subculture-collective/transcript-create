import { Link } from 'react-router-dom';
import type { DateField } from '../../features/streams/library';
import { dateFieldLabel, formatDate, formatDuration, statusBadge, titleCase } from '../../features/streams/library';
import type { VideoInfo } from '../../types/api';

type StreamCardProps = {
  video: VideoInfo;
  dateField: DateField;
};

export default function StreamCard({ video, dateField }: StreamCardProps) {
  const status = statusBadge(video);
  const title = video.title || `Video ${video.youtube_id}`;
  const dateValue = video[dateField];

  return (
    <article className="surface-card-compact group flex h-full flex-col overflow-hidden border border-border/80 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:shadow-lg">
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
            {dateFieldLabel(dateField)} {formatDate(dateValue ?? null)}
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <span className={status.className}>{status.label}</span>
            <span
              className={
                video.has_whisper_transcript
                  ? 'badge-success'
                  : 'inline-flex items-center justify-center rounded-full bg-surface-muted px-2 pb-[3px] pt-[7px] text-center font-medium leading-none text-muted'
              }
            >
              {video.has_whisper_transcript ? 'Whisper transcript' : 'No Whisper transcript'}
            </span>
            <span
              className={
                video.has_youtube_transcript
                  ? 'badge-warning'
                  : 'inline-flex items-center justify-center rounded-full bg-surface-muted px-2 pb-[3px] pt-[7px] text-center font-medium leading-none text-muted'
              }
            >
              {video.has_youtube_transcript ? 'YouTube captions' : 'No YouTube captions'}
            </span>
            {!video.has_whisper_transcript && !video.has_youtube_transcript && (
              <span className="inline-flex items-center justify-center rounded-full bg-danger-soft px-2 pb-[3px] pt-[7px] text-center font-medium leading-none text-danger">
                No transcript yet
              </span>
            )}
          </div>

          <h2 className="line-clamp-2 text-lg font-semibold tracking-tight text-ink group-hover:text-accent">
            <Link to={`/v/${video.id}`} className="hover:underline focus:underline">
              {title}
            </Link>
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
          <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-subtle">
            <span>{video.youtube_id.slice(0, 8)}</span>
            {video.category && <span>{titleCase(video.category)}</span>}
            <Link to={`/v/${video.id}`} className="action-link group-hover:underline">
              Open VOD
            </Link>
            {video.has_whisper_transcript && (
              <Link to={`/?source=native&q=${encodeURIComponent(title)}`} className="action-link">
                Search Whisper
              </Link>
            )}
            {video.has_youtube_transcript && (
              <Link to={`/?source=youtube&q=${encodeURIComponent(title)}`} className="action-link">
                Search YouTube captions
              </Link>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
