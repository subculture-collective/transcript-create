import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type { TimelineBucket } from '../types/api';
import { formatDate, formatDuration, formatNumber } from '../features/archive/format';

function bucketRange(period: string) {
  if (/^\d{4}-\d{2}$/.test(period)) {
    const [year, month] = period.split('-').map(Number);
    const start = new Date(Date.UTC(year, month - 1, 1));
    const end = new Date(Date.UTC(year, month, 0, 23, 59, 59, 999));
    return { date_from: start.toISOString().slice(0, 10), date_to: end.toISOString().slice(0, 10) };
  }

  if (/^\d{4}$/.test(period)) {
    return { date_from: `${period}-01-01`, date_to: `${period}-12-31` };
  }

  return null;
}

export default function TimelinePage() {
  const [buckets, setBuckets] = useState<TimelineBucket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getTimeline()
      .then(setBuckets)
      .catch((err: unknown) => {
        console.error('Failed to load archive timeline', err);
        setBuckets([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-3">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">Timeline</div>
        <h1 className="page-title">Archive chronology</h1>
        <p className="max-w-2xl text-muted">
          Browse episodes by month and jump into the search results for any span of time.
        </p>
      </section>

      {loading ? (
        <div className="surface-card text-center text-muted">Loading timeline…</div>
      ) : buckets.length === 0 ? (
        <div className="surface-card text-center text-muted">No timeline data yet.</div>
      ) : (
        <div className="space-y-6">
          {buckets.map((bucket) => {
            const range = bucketRange(bucket.period);
            return (
            <section key={bucket.period} className="surface-card space-y-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="section-title">{bucket.label}</h2>
                <div className="text-sm text-muted">{formatNumber(bucket.video_count)} episodes · {formatDuration(bucket.total_duration_seconds)}</div>
              </div>

              <article className="rounded-2xl border border-border bg-surface-muted p-4">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                  <p className="text-sm text-muted">{bucket.video_count} episodes in this archive period.</p>
                  {range && (
                        <Link
                          to={`/episodes?date_from=${range.date_from}&date_to=${range.date_to}`}
                          className="action-link text-sm"
                        >
                          Browse this period
                        </Link>
                  )}
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {bucket.videos.map((video) => (
                          <Link
                            key={video.id}
                            to={`/v/${video.id}`}
                            className="rounded-xl border border-border bg-surface p-4 transition-colors hover:border-accent hover:bg-surface"
                          >
                            <div className="line-clamp-2 font-medium text-ink">{video.title || 'Untitled episode'}</div>
                            <div className="mt-2 text-sm text-muted">{video.channel_name || 'Unknown channel'}</div>
                            <div className="mt-3 flex flex-wrap gap-3 text-xs text-subtle">
                              <span>{formatDate(video.uploaded_at ?? video.created_at ?? null)}</span>
                              <span>{formatDuration(video.duration_seconds)}</span>
                            </div>
                          </Link>
                        ))}
                </div>
              </article>
            </section>
          );
          })}
        </div>
      )}
    </div>
  );
}
