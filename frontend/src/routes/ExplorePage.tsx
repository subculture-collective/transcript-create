import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type { ArchiveEvidenceMoment, ArchivePeriodIntelligence, ExploreIntelligenceResponse } from '../types/api';
import { buildMonthRange, buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp } from '../features/archive/format';

function topicHref(label: string) {
  return `/topics/${encodeURIComponent(label)}`;
}

function periodBrowseHref(period: ArchivePeriodIntelligence) {
  const monthMatch = period.period.match(/^(\d{4})-(\d{2})$/);
  if (monthMatch) {
    const [year, month] = monthMatch.slice(1).map(Number);
    const range = buildMonthRange(year, month);
    return `/episodes?date_from=${range.date_from}&date_to=${range.date_to}`;
  }

  if (/^\d{4}$/.test(period.period)) {
    return `/episodes?date_from=${period.period}-01-01&date_to=${period.period}-12-31`;
  }

  return null;
}

function evidenceHref(moment: ArchiveEvidenceMoment) {
  return buildTimestampLink(moment.video.id, moment.start_ms);
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getExploreIntelligence()
      .then(setData)
      .catch((err: unknown) => {
        console.error('Failed to load archive intelligence', err);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="surface-card text-center text-muted">Loading archive intelligence…</div>;
  }

  if (!data) {
    return <div className="surface-card text-center text-muted">Archive intelligence is not available yet.</div>;
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <section className="surface-card space-y-5">
        <div className="archive-eyebrow">Explore</div>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,1fr)] lg:items-end">
          <div className="space-y-3">
            <h1 className="page-title">Archive Intelligence</h1>
            <p className="max-w-3xl text-muted">
              Follow topics, search momentum, and cited timeline summaries across the HasanAbi archive.
            </p>
            {data.exploration_modes.length > 0 && (
              <div className="flex flex-wrap gap-2 text-sm text-muted">
                {data.exploration_modes.map((mode) => (
                  <span key={mode} className="source-pill">
                    {mode}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold text-ink">{formatNumber(data.summary.video_count)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">VODs</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold text-ink">{formatDuration(data.summary.total_duration_seconds)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">Runtime</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-3">
              <div className="text-2xl font-semibold text-ink">{formatNumber(data.summary.transcript_word_count)}</div>
              <div className="text-xs uppercase tracking-wide text-subtle">Words</div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="surface-card space-y-3">
          <h2 className="section-title">Trending searches</h2>
          <div className="flex flex-wrap gap-2">
            {data.trending_searches.length > 0 ? (
              data.trending_searches.map((item) => (
                <Link key={item.term} to={`/search?q=${encodeURIComponent(item.term)}`} className="badge-warning">
                  {item.term}
                </Link>
              ))
            ) : (
              <div className="text-sm text-muted">No trending searches yet.</div>
            )}
          </div>
        </div>

        <div className="surface-card space-y-3">
          <h2 className="section-title">Suggested searches</h2>
          <div className="flex flex-wrap gap-2">
            {data.suggested_searches.length > 0 ? (
              data.suggested_searches.map((item) => (
                <Link key={item.term} to={`/search?q=${encodeURIComponent(item.term)}`} className="badge-warning">
                  {item.term}
                </Link>
              ))
            ) : (
              <div className="text-sm text-muted">No suggested searches yet.</div>
            )}
          </div>
        </div>
      </section>

      <section className="surface-card space-y-4">
        <h2 className="section-title">Topic atlas</h2>
        {data.topic_cards.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.topic_cards.map((topic) => (
              <Link
                key={topic.slug}
                to={topicHref(topic.label)}
                className="rounded-2xl border border-border bg-surface-muted p-4 transition-colors hover:border-accent hover:bg-surface"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-ink">{topic.label}</h3>
                    <div className="mt-1 text-xs uppercase tracking-wide text-subtle">{topic.source}</div>
                  </div>
                  <div className="text-right text-sm text-muted">
                    <div>{formatNumber(topic.total_moments)} moments</div>
                    <div>{formatNumber(topic.total_videos)} VODs</div>
                  </div>
                </div>
                {topic.evidence.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {topic.evidence.slice(0, 2).map((moment) => (
                      <div key={`${moment.video.id}-${moment.start_ms}`} className="rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                        <div className="text-xs uppercase tracking-wide text-subtle">{formatTimestamp(moment.start_ms)}</div>
                        <div className="mt-1 line-clamp-2 text-ink">{moment.snippet}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted">No topic cards available yet.</div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="section-title">Timeline intelligence</h2>
        {data.periods.length > 0 ? (
          <div className="space-y-4">
            {data.periods.map((period) => {
              const browseHref = periodBrowseHref(period);
              return (
                <article key={period.period} className="surface-card space-y-4">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                      <h3 className="text-xl font-semibold text-ink">{period.label}</h3>
                      <p className="text-sm text-muted">
                        {formatNumber(period.video_count)} VODs · {formatDuration(period.total_duration_seconds)}
                      </p>
                    </div>
                    {browseHref && (
                      <Link to={browseHref} className="action-link text-sm">
                        Browse period
                      </Link>
                    )}
                  </div>

                  <p className="text-muted">{period.summary}</p>

                  {period.top_topics.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {period.top_topics.map((topic) => (
                        <Link key={topic.slug} to={topicHref(topic.label)} className="badge-warning">
                          {topic.label}
                        </Link>
                      ))}
                    </div>
                  )}

                  {period.evidence.length > 0 && (
                    <div className="grid gap-3 md:grid-cols-2">
                      {period.evidence.map((moment) => (
                        <Link
                          key={`${moment.video.id}-${moment.start_ms}`}
                          to={evidenceHref(moment)}
                          className="rounded-xl border border-border bg-surface-muted p-3 transition-colors hover:border-accent hover:bg-surface"
                        >
                          <div className="text-xs uppercase tracking-wide text-subtle">
                            {formatTimestamp(moment.start_ms)} · Open cited moment
                          </div>
                          <div className="mt-2 line-clamp-2 text-sm text-ink">{moment.snippet}</div>
                          <div className="mt-2 line-clamp-1 text-xs text-muted">{moment.video.title || 'Untitled VOD'}</div>
                          <div className="mt-1 text-xs text-subtle">{formatDate(moment.video.uploaded_at ?? null)}</div>
                        </Link>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="surface-card text-center text-muted">No timeline intelligence available yet.</div>
        )}
      </section>
    </div>
  );
}
