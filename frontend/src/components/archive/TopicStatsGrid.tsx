import { Link } from 'react-router-dom';
import type { MentionMapResponse } from '../../types/api';
import { formatNumber } from '../../features/archive/format';

type TopicStatsGridProps = {
  mentionMap: MentionMapResponse | null;
  topic: string;
  loading: boolean;
};

export default function TopicStatsGrid({ mentionMap, topic, loading }: TopicStatsGridProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Query</div>
        <div className="mt-1 text-2xl font-semibold text-ink">“{mentionMap?.query ?? topic}”</div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">First mentioned</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : mentionMap?.first_mentioned_year ?? '—'}</div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Most discussed</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : mentionMap?.most_discussed_period ?? '—'}</div>
        {!loading && mentionMap?.most_discussed_count ? <div className="mt-1 text-xs text-muted">{formatNumber(mentionMap.most_discussed_count)} moments</div> : null}
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Recent mentions</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.recent_mentions_90d ?? 0)}</div>
        <div className="mt-1 text-xs text-muted">last 90 days</div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Related topics</div>
        <div className="mt-2 flex flex-wrap gap-2 text-sm text-ink">
          {(mentionMap?.related_topics ?? []).length > 0 ? mentionMap!.related_topics!.map((term) => (
            <Link key={term} to={`/topics/${encodeURIComponent(term)}`} className="inline-flex items-center justify-center rounded-full border border-border bg-surface px-2 pb-[3px] pt-[7px] text-center leading-none hover:border-accent">
              {term}
            </Link>
          )) : <span className="text-muted">No co-occurring terms yet</span>}
        </div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Top VODs</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.top_episodes_count ?? mentionMap?.top_episodes?.length ?? 0)}</div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">Total moments</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.total_moments)}</div>
      </div>
      <div className="rounded-xl border border-border bg-surface-muted p-4">
        <div className="text-xs uppercase tracking-wide text-subtle">VODs</div>
        <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.total_videos)}</div>
      </div>
    </div>
  );
}
