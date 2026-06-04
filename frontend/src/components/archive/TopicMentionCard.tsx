import { Link } from 'react-router-dom';
import type { SearchHit } from '../../types/api';
import { buildTimestampLink, formatTimestamp, sourceLabel } from '../../features/archive/format';

type TopicMentionCardProps = {
  label: string;
  moment: SearchHit & { video?: { id?: string } | null };
};

export default function TopicMentionCard({ label, moment }: TopicMentionCardProps) {
  const videoId = moment.video?.id ?? moment.video_id;

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="text-xs uppercase tracking-wide text-subtle">{label}</div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
        <span>{formatTimestamp(moment.start_ms)}</span>
        <span>{sourceLabel(moment.source ?? 'best')}</span>
        {videoId && <Link className="action-link" to={buildTimestampLink(videoId, moment.start_ms, moment.id)}>Open cited moment</Link>}
      </div>
      <div className="prose prose-sm mt-3 max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: moment.snippet }} />
    </div>
  );
}
