import { Link } from 'react-router-dom';
import type { EpisodeSearchGroup } from '../../types/api';
import { formatVideoTitle } from '../../features/archive/format';

type Props = {
  query: string;
  groups: EpisodeSearchGroup[];
  related: string[];
};

type Bucket = { key: string; label: string; count: number };

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Group loaded moments by broadcast year, or by month when they span one year. */
// eslint-disable-next-line react-refresh/only-export-components
export function bucketMomentsByDate(groups: EpisodeSearchGroup[]): Bucket[] {
  const dated = groups
    .map((group) => ({
      date: group.video.uploaded_at ? new Date(group.video.uploaded_at) : null,
      count: group.moments.length,
    }))
    .filter((item): item is { date: Date; count: number } =>
      Boolean(item.date && !Number.isNaN(item.date.getTime()))
    );
  if (dated.length === 0) return [];
  const years = new Set(dated.map((item) => item.date.getUTCFullYear()));
  const byMonth = years.size === 1;
  const buckets = new Map<string, Bucket>();
  for (const { date, count } of dated) {
    const year = date.getUTCFullYear();
    const month = date.getUTCMonth();
    const key = byMonth ? `${year}-${String(month + 1).padStart(2, '0')}` : String(year);
    const label = byMonth ? MONTHS[month] : String(year);
    const bucket = buckets.get(key) ?? { key, label, count: 0 };
    bucket.count += count;
    buckets.set(key, bucket);
  }
  // Include empty periods between the first and last so gaps read as gaps.
  const keys = [...buckets.keys()].sort();
  const filled: Bucket[] = [];
  if (byMonth) {
    const [year] = [...years];
    const first = Number(keys[0].slice(5)) - 1;
    const last = Number(keys[keys.length - 1].slice(5)) - 1;
    for (let month = first; month <= last; month += 1) {
      const key = `${year}-${String(month + 1).padStart(2, '0')}`;
      filled.push(buckets.get(key) ?? { key, label: MONTHS[month], count: 0 });
    }
  } else {
    for (let year = Number(keys[0]); year <= Number(keys[keys.length - 1]); year += 1)
      filled.push(
        buckets.get(String(year)) ?? { key: String(year), label: String(year), count: 0 }
      );
  }
  return filled;
}

export default function SearchInsights({ query, groups, related }: Props) {
  const buckets = bucketMomentsByDate(groups);
  const total = groups.reduce((sum, group) => sum + group.moments.length, 0);
  const peak = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const topEpisodes = [...groups]
    .sort((left, right) => right.moments.length - left.moments.length)
    .slice(0, 5)
    .filter((group) => group.moments.length > 0);

  if (total === 0 && related.length === 0) return null;

  return (
    <section className="archive-section space-y-6" aria-labelledby="search-insights-title">
      <h2 id="search-insights-title" className="archive-rule-title">
        Insights
      </h2>

      {buckets.length > 1 && (
        <figure>
          <figcaption className="mb-2 text-sm font-semibold text-ink">When it came up</figcaption>
          <svg
            className="insight-bars"
            viewBox={`0 0 ${buckets.length * 10} 40`}
            preserveAspectRatio="none"
            role="img"
            aria-label={buckets.map((bucket) => `${bucket.label}: ${bucket.count}`).join(', ')}
          >
            {buckets.map((bucket, index) => {
              const height = bucket.count ? Math.max(2, (bucket.count / peak) * 40) : 0.75;
              return (
                <rect
                  key={bucket.key}
                  x={index * 10 + 1}
                  y={40 - height}
                  width={8}
                  height={height}
                  rx={1}
                >
                  <title>{`${bucket.label}: ${bucket.count}`}</title>
                </rect>
              );
            })}
          </svg>
          <div className="mt-1 flex justify-between font-mono text-[11px] text-subtle">
            <span>{buckets[0].label}</span>
            <span>{buckets[buckets.length - 1].label}</span>
          </div>
          <p className="mt-2 text-xs leading-5 text-subtle">
            Across the {total} loaded {total === 1 ? 'moment' : 'moments'}, by broadcast date.
          </p>
        </figure>
      )}

      {topEpisodes.length > 1 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">Most matches</h3>
          <ol className="space-y-1">
            {topEpisodes.map((group) => (
              <li key={group.video.id}>
                <Link
                  to={`/v/${group.video.id}?q=${encodeURIComponent(query)}`}
                  className="insight-row"
                >
                  <span className="line-clamp-1 min-w-0">
                    {formatVideoTitle(group.video.title, group.video.uploaded_at)}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-accent">
                    {group.moments.length}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </div>
      )}

      {related.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">Related and popular searches</h3>
          <div className="flex flex-wrap gap-2">
            {related.slice(0, 12).map((term) => (
              <Link key={term} to={`/search?q=${encodeURIComponent(term)}`} className="topic-chip">
                {term}
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
