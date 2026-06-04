import { Link } from 'react-router-dom';
import type { RecentVideo } from '../../types/api';
import { formatDate, formatDuration } from '../../features/archive/format';

type VideoCardProps = {
  video: RecentVideo;
};

export default function VideoCard({ video }: VideoCardProps) {
  return (
    <Link
      to={`/v/${video.id}`}
      className="surface-card-compact block border-border/80 transition-all hover:-translate-y-0.5 hover:border-accent/70 hover:shadow-[0_18px_35px_rgba(0,0,0,0.25)]"
    >
      <div className="line-clamp-2 font-semibold tracking-[-0.03em] text-ink">{video.title || 'Untitled VOD'}</div>
      <div className="mt-2 text-sm text-muted">{video.channel_name || 'Unknown channel'}</div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="timestamp-pill">{formatDuration(video.duration_seconds)}</span>
        <span className="source-pill">{formatDate(video.uploaded_at ?? null)}</span>
        <span className="match-pill">{video.has_whisper_transcript ? 'whisper ready' : 'pending transcript'}</span>
      </div>
    </Link>
  );
}
