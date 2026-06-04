import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type {
  ArchiveEvidenceMoment,
  ArchivePeriodIntelligence,
  ExploreIntelligenceQuery,
  ExploreIntelligenceResponse,
} from '../types/api';
import { buildMonthRange, buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp } from '../features/archive/format';

const DEFAULT_QUERY: Required<Pick<ExploreIntelligenceQuery, 'granularity' | 'topic_limit' | 'period_limit'>> = {
  granularity: 'month',
  topic_limit: 8,
  period_limit: 24,
};

const SECTION_IDS = ['overview', 'trending', 'suggested', 'topics', 'timeline', 'method'] as const;

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
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<ExploreIntelligenceQuery>(DEFAULT_QUERY);
  const [activeSection, setActiveSection] = useState<(typeof SECTION_IDS)[number]>('overview');

  const filterSummary = useMemo(() => {
    const parts = [filters.granularity === 'week' ? 'Weekly' : 'Monthly', `${filters.topic_limit ?? DEFAULT_QUERY.topic_limit} topics`];
    if (filters.date_from || filters.date_to) {
      parts.push([filters.date_from || 'start', filters.date_to || 'now'].join(' → '));
    }
    return parts.join(' · ');
  }, [filters.date_from, filters.date_to, filters.granularity, filters.topic_limit]);

  const loadIntelligence = async (query: ExploreIntelligenceQuery, initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);

    try {
      const result = await api.getExploreIntelligence(query);
      setData(result);
    } catch (err: unknown) {
      console.error('Failed to load archive intelligence', err);
      setError('Archive intelligence could not be refreshed right now. Showing the last successful snapshot when available.');
      if (!data) setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadIntelligence(DEFAULT_QUERY, true);
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = (window.location.hash ?? '').replace('#', '');
      if ((SECTION_IDS as readonly string[]).includes(hash)) {
        setActiveSection(hash as (typeof SECTION_IDS)[number]);
      }
    };

    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    const observedSections = SECTION_IDS.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => Boolean(el));
    if (typeof IntersectionObserver === 'undefined' || observedSections.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target?.id && (SECTION_IDS as readonly string[]).includes(visible[0].target.id)) {
          setActiveSection(visible[0].target.id as (typeof SECTION_IDS)[number]);
        }
      },
      {
        rootMargin: '-20% 0px -60% 0px',
        threshold: [0.08, 0.2, 0.45],
      }
    );

    observedSections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [data]);

  const applyFilters = async () => {
    await loadIntelligence({
      granularity: filters.granularity,
      topic_limit: filters.topic_limit,
      period_limit: DEFAULT_QUERY.period_limit,
      date_from: filters.date_from,
      date_to: filters.date_to,
    });
  };

  const resetFilters = async () => {
    setFilters(DEFAULT_QUERY);
    await loadIntelligence(DEFAULT_QUERY);
  };

  const sectionsNav = (
    <nav aria-label="Explore sections" className="flex h-full flex-col rounded-2xl border border-border bg-surface/90 p-2 shadow-[0_12px_34px_rgba(0,0,0,0.18)] backdrop-blur-xl lg:sticky lg:top-24 lg:p-3">
      <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
        {[
          ['overview', 'Overview'],
          ['trending', 'Trending'],
          ['suggested', 'Suggested'],
          ['topics', 'Topic Atlas'],
          ['timeline', 'Timeline'],
          ['method', 'Method'],
        ].map(([id, label]) => {
          const isActive = activeSection === id;
          return (
            <a
              key={id}
              href={`#${id}`}
              aria-current={isActive ? 'page' : undefined}
              className={`whitespace-nowrap rounded-full border px-3 py-2 text-sm font-medium transition-all focus:outline-none focus:ring-2 focus:ring-accent/35 ${
                isActive
                  ? 'border-accent/60 bg-accent/15 text-ink shadow-[0_0_0_1px_rgba(183,255,60,0.12)]'
                  : 'border-border bg-surface-muted/80 text-muted hover:border-border-strong hover:bg-surface hover:text-ink'
              }`}
            >
              {label}
            </a>
          );
        })}
      </div>
      <div className="mt-3 hidden flex-1 rounded-xl border border-border bg-surface-muted/70 p-3 text-xs text-muted lg:block">
        <div className="meta-label">Active view</div>
        <div className="mt-1 font-medium text-ink">{activeSection.replace(/^[a-z]/, (m) => m.toUpperCase())}</div>
        <div className="mt-2">{filterSummary}</div>
      </div>
    </nav>
  );

  if (loading) {
    return <div className="surface-card text-center text-muted">Loading archive intelligence…</div>;
  }

  if (!data) {
    return <div className="surface-card text-center text-muted">Archive intelligence is not available yet.</div>;
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      {error && <div className="rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning" role="alert">{error}</div>}

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-stretch">
        <div className="lg:order-1">{sectionsNav}</div>

        <div className="lg:order-2">
          <section id="overview" className="surface-card scroll-mt-24 space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <div className="archive-eyebrow">Explore</div>
              {refreshing && <span className="source-pill border-accent/30 text-accent">Refreshing</span>}
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,1fr)] xl:items-end">
              <div className="space-y-3">
                <h1 className="page-title">Archive Intelligence</h1>
                <p className="max-w-3xl text-muted">
                  Follow topics, search momentum, and cited timeline summaries across the HasanAbi archive.
                </p>
                <p className="text-sm text-subtle">{filterSummary}</p>
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

            <form
              className="rounded-2xl border border-border bg-surface-muted/70 p-4 shadow-[0_8px_24px_rgba(0,0,0,0.16)]"
              onSubmit={(event) => {
                event.preventDefault();
                void applyFilters();
              }}
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <fieldset className="space-y-2">
                  <legend className="meta-label">Granularity</legend>
                  <div className="flex gap-2">
                    {(['month', 'week'] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setFilters((current) => ({ ...current, granularity: value }))}
                        aria-pressed={filters.granularity === value}
                        className={`btn-ghost rounded-full border px-4 py-2 text-sm ${
                          filters.granularity === value ? 'border-accent/60 bg-accent/15 text-ink' : ''
                        }`}
                      >
                        {value === 'month' ? 'Month' : 'Week'}
                      </button>
                    ))}
                  </div>
                </fieldset>

                <fieldset className="space-y-2">
                  <legend className="meta-label">Topic limit</legend>
                  <div className="flex flex-wrap gap-2">
                    {[8, 12, 16].map((value) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setFilters((current) => ({ ...current, topic_limit: value }))}
                        aria-pressed={filters.topic_limit === value}
                        className={`btn-ghost min-w-24 rounded-xl border px-4 py-2 text-sm ${
                          filters.topic_limit === value ? 'border-accent/60 bg-accent/15 text-ink' : ''
                        }`}
                      >
                        {value} topics
                      </button>
                    ))}
                  </div>
                </fieldset>

                <label className="space-y-2">
                  <span className="meta-label">Date from</span>
                  <input
                    type="date"
                    value={filters.date_from ?? ''}
                    onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value || undefined }))}
                    className="form-control"
                  />
                </label>

                <label className="space-y-2">
                  <span className="meta-label">Date to</span>
                  <input
                    type="date"
                    value={filters.date_to ?? ''}
                    onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value || undefined }))}
                    className="form-control"
                  />
                </label>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button type="submit" className="btn-primary" disabled={refreshing}>
                  {refreshing ? 'Applying…' : 'Apply'}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    void resetFilters();
                  }}
                  disabled={refreshing}
                >
                  Reset
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>

      <main className="space-y-6 lg:space-y-8">
        <section id="trending" className="surface-card scroll-mt-24 space-y-4">
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
        </section>

        <section id="suggested" className="surface-card scroll-mt-24 space-y-4">
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
        </section>

        <section id="topics" className="surface-card scroll-mt-24 space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="section-title">Topic atlas</h2>
              <p className="text-sm text-muted">Topic cards with momentum, aliases, and cited evidence.</p>
            </div>
            <div className="text-xs uppercase tracking-[0.22em] text-subtle">{formatNumber(data.topic_cards.length)} topics</div>
          </div>
          {data.topic_cards.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {data.topic_cards.map((topic) => (
                <Link
                  key={topic.slug}
                  to={topicHref(topic.label)}
                  className="group rounded-2xl border border-border bg-surface-muted p-4 transition-all hover:-translate-y-0.5 hover:border-accent hover:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/35"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold text-ink group-hover:text-accent">{topic.label}</h3>
                    </div>
                    <div className="text-right text-sm text-muted">
                      <div className="text-base font-semibold text-ink">{formatNumber(topic.trend_score)}</div>
                      <div className="text-xs uppercase tracking-wide text-subtle">Trend score</div>
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-muted">
                    <div className="rounded-xl border border-border bg-surface p-3">
                      <div className="text-subtle">Moments</div>
                      <div className="mt-1 text-sm font-semibold text-ink">{formatNumber(topic.total_moments)}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface p-3">
                      <div className="text-subtle">VODs</div>
                      <div className="mt-1 text-sm font-semibold text-ink">{formatNumber(topic.total_videos)}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface p-3">
                      <div className="text-subtle">90d</div>
                      <div className="mt-1 text-sm font-semibold text-ink">{formatNumber(topic.recent_mentions_90d)}</div>
                    </div>
                  </div>

                  {topic.aliases.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {topic.aliases.slice(0, 3).map((alias) => (
                        <span key={alias} className="source-pill">
                          {alias}
                        </span>
                      ))}
                    </div>
                  )}

                  {topic.evidence.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {topic.evidence.slice(0, 2).map((moment) => (
                        <div key={`${moment.video.id}-${moment.start_ms}`} className="rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                          <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
                            <span>{formatTimestamp(moment.start_ms)}</span>
                            <span>{moment.video.title || 'Untitled VOD'}</span>
                          </div>
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

        <section id="timeline" className="space-y-4 scroll-mt-24">
          <div className="surface-card space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="section-title">Timeline intelligence</h2>
                <p className="text-sm text-muted">Period summaries with thumbnails, topic spikes, and cited moments.</p>
              </div>
              <div className="text-xs uppercase tracking-[0.22em] text-subtle">{formatNumber(data.periods.length)} periods</div>
            </div>

            {data.periods.length > 0 ? (
              <div className="space-y-4">
                {data.periods.map((period) => {
                  const browseHref = periodBrowseHref(period);
                  const thumbnails = period.videos.filter((video) => Boolean(video.youtube_id)).slice(0, 3);
                  return (
                    <article key={period.period} className="rounded-2xl border border-border bg-surface-muted p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="space-y-2">
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

                      {thumbnails.length > 0 && (
                        <div className="mt-4 grid gap-3 sm:grid-cols-3">
                          {thumbnails.map((video) => (
                            <div key={video.id} className="overflow-hidden rounded-xl border border-border bg-surface shadow-[0_8px_18px_rgba(0,0,0,0.16)]">
                              <img
                                src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
                                alt={video.title || 'VOD thumbnail'}
                                className="aspect-video w-full object-cover"
                                loading="lazy"
                              />
                              <div className="p-3 text-xs text-muted">
                                <div className="line-clamp-2 font-medium text-ink">{video.title || 'Untitled VOD'}</div>
                                <div className="mt-1 line-clamp-1 text-subtle">{formatDate(video.uploaded_at ?? null)}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      <p className="mt-4 text-muted">{period.summary}</p>

                      {period.top_topics.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {period.top_topics.map((topic) => (
                            <Link
                              key={topic.slug}
                              to={topicHref(topic.label)}
                              className="rounded-full border border-border bg-surface px-3 py-2 text-xs font-medium text-ink transition-colors hover:border-accent hover:text-accent"
                            >
                              {topic.label}
                              <span className="ml-2 text-subtle">
                                {formatNumber(topic.total_moments)} · {formatNumber(topic.total_videos)}
                              </span>
                            </Link>
                          ))}
                        </div>
                      )}

                      {period.evidence.length > 0 && (
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          {period.evidence.map((moment) => (
                            <Link
                              key={`${moment.video.id}-${moment.start_ms}`}
                              to={evidenceHref(moment)}
                              className="rounded-xl border border-border bg-surface p-3 transition-colors hover:border-accent hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-accent/35"
                            >
                              <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
                                <span>{formatTimestamp(moment.start_ms)} · Open cited moment</span>
                                <span>{moment.video.title || 'Untitled VOD'}</span>
                              </div>
                              <div className="mt-2 line-clamp-2 text-sm text-ink">{moment.snippet}</div>
                            </Link>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="text-center text-muted">No timeline intelligence available yet.</div>
            )}
          </div>
        </section>

        <section id="method" className="surface-card scroll-mt-24 space-y-4">
          <h2 className="section-title">Method</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <p className="rounded-2xl border border-border bg-surface-muted p-4 text-muted">
              Topics are a hybrid of curated labels and automatic discovery. Automatic topics are published by default, and editable topics can be refined later.
            </p>
            <p className="rounded-2xl border border-border bg-surface-muted p-4 text-muted">
              Trends combine transcript mentions with search behavior. Summaries are citation-backed and mostly extractive today, with more generated synthesis coming later.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
