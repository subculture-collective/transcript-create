import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type {
  ArchiveEvidenceMoment,
  ArchivePeriodOption,
  ExploreIntelligenceResponse,
} from '../types/api';
import { buildMonthRange, buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp } from '../features/archive/format';

type PeriodKind = 'latest' | 'week' | 'month' | 'event' | 'date';

const PERIOD_KIND_TABS: Array<{ kind: PeriodKind; label: string }> = [
  { kind: 'latest', label: 'Latest' },
  { kind: 'week', label: 'Weeks' },
  { kind: 'month', label: 'Months' },
  { kind: 'event', label: 'Events' },
  { kind: 'date', label: 'Dates' },
];

const TOPIC_LIMITS = [8, 12, 16] as const;
const PERIOD_OPTION_FETCH_LIMIT = 24;

const SECTION_IDS = ['overview', 'trending', 'suggested', 'topics', 'timeline', 'method'] as const;

function topicHref(label: string) {
  return `/topics/${encodeURIComponent(label)}`;
}

function evidenceHref(moment: ArchiveEvidenceMoment) {
  return buildTimestampLink(moment.video.id, moment.start_ms);
}

function normalizePeriodKind(kind?: string | null): PeriodKind | null {
  if (!kind) return null;
  const value = kind.toLowerCase();
  if (value === 'latest' || value === 'all') return 'latest';
  if (value.startsWith('week')) return 'week';
  if (value.startsWith('month')) return 'month';
  if (value.startsWith('event')) return 'event';
  if (value.startsWith('date')) return 'date';
  return null;
}

function formatPeriodRange(option?: ArchivePeriodOption | null) {
  if (!option) return null;
  return `${option.date_from} → ${option.date_to}`;
}

function periodBrowseHref(option?: ArchivePeriodOption | null) {
  if (!option) return null;

  const monthMatch = option.slug.match(/^(\d{4})-(\d{2})$/);
  if (monthMatch) {
    const [year, month] = monthMatch.slice(1).map(Number);
    const range = buildMonthRange(year, month);
    return `/episodes?date_from=${range.date_from}&date_to=${range.date_to}`;
  }

  if (option.date_from && option.date_to) {
    return `/episodes?date_from=${option.date_from}&date_to=${option.date_to}`;
  }

  return null;
}

function uniquePeriodOptions(...groups: Array<ArchivePeriodOption[] | undefined>) {
  const seen = new Set<string>();
  return groups.flat().filter((option): option is ArchivePeriodOption => {
    if (!option || seen.has(option.slug)) return false;
    seen.add(option.slug);
    return true;
  });
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<(typeof SECTION_IDS)[number]>('overview');
  const [topicLimit, setTopicLimit] = useState<(typeof TOPIC_LIMITS)[number]>(8);
  const [selectedPeriodSlug, setSelectedPeriodSlug] = useState<string | null>(null);
  const [periodKind, setPeriodKind] = useState<PeriodKind>('latest');
  const [periodOptionsByKind, setPeriodOptionsByKind] = useState<Partial<Record<Exclude<PeriodKind, 'latest'>, ArchivePeriodOption[]>>>({});
  const [periodOptionsLoading, setPeriodOptionsLoading] = useState(false);
  const cachedPeriodOptions = periodKind === 'latest' ? undefined : periodOptionsByKind[periodKind];

  const loadIntelligence = async (queryPeriod?: string | null, queryTopicLimit = topicLimit, initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);

    try {
      const result = await api.getExploreIntelligence({
        ...(queryPeriod ? { period: queryPeriod } : {}),
        topic_limit: queryTopicLimit,
      });
      setData(result);
      if (result.selected_period?.slug) {
        setSelectedPeriodSlug(result.selected_period.slug);
      } else if (queryPeriod) {
        setSelectedPeriodSlug(queryPeriod);
      }
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
    void loadIntelligence(undefined, topicLimit, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const periodOptions = useMemo(() => uniquePeriodOptions(data?.period_options, cachedPeriodOptions), [data?.period_options, cachedPeriodOptions]);

  const filteredPeriodOptions = useMemo(() => {
    if (periodKind === 'latest') return periodOptions;
    return periodOptions.filter((option) => normalizePeriodKind(option.kind) === periodKind);
  }, [periodKind, periodOptions]);

  const currentPeriod = useMemo(() => {
    const slug = selectedPeriodSlug ?? data?.selected_period?.slug ?? null;
    if (!slug) return data?.selected_period ?? null;
    return periodOptions.find((option) => option.slug === slug) ?? data?.selected_period ?? null;
  }, [data?.selected_period, periodOptions, selectedPeriodSlug]);

  const currentPeriodSummary = useMemo(() => {
    const pieces = [currentPeriod?.label ?? 'Latest'];
    const range = formatPeriodRange(currentPeriod);
    if (range) pieces.push(range);
    pieces.push(`${topicLimit} topics`);
    return pieces.join(' · ');
  }, [currentPeriod, topicLimit]);

  const currentPeriodKindLabel = useMemo(() => {
    if (!currentPeriod?.kind) return 'Latest';
    const kind = normalizePeriodKind(currentPeriod.kind) ?? 'latest';
    return PERIOD_KIND_TABS.find((tab) => tab.kind === kind)?.label ?? currentPeriod.kind;
  }, [currentPeriod?.kind]);

  const selectedOptionForTimeline = useMemo(() => {
    if (!data?.periods?.length) return null;
    const slug = currentPeriod?.slug ?? selectedPeriodSlug ?? data.selected_period?.slug;
    return data.period_options.find((option) => option.slug === slug) ?? currentPeriod ?? data.selected_period ?? null;
  }, [currentPeriod, data?.period_options, data?.periods?.length, data?.selected_period, selectedPeriodSlug]);

  const timelinePeriods = useMemo(() => {
    if (!data?.periods?.length) return [];
    const selectedSlug = currentPeriod?.slug ?? selectedPeriodSlug ?? data.selected_period?.slug ?? null;
    if (!selectedSlug) return data.periods;

    const primary = data.periods.find((period) => period.period === selectedSlug);
    if (!primary) return data.periods;

    return [primary, ...data.periods.filter((period) => period.period !== selectedSlug)];
  }, [currentPeriod?.slug, data?.periods, data?.selected_period?.slug, selectedPeriodSlug]);

  useEffect(() => {
    if (periodKind === 'latest') {
      setPeriodOptionsLoading(false);
      return;
    }

    if (filteredPeriodOptions.length > 0) {
      setPeriodOptionsLoading(false);
      return;
    }

    let cancelled = false;
    setPeriodOptionsLoading(true);

    void api
      .getExplorePeriods({ kind: periodKind, limit: PERIOD_OPTION_FETCH_LIMIT })
      .then((response) => {
        if (cancelled) return;
        setPeriodOptionsByKind((current) => ({
          ...current,
          [periodKind]: response.periods ?? [],
        }));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        console.error('Failed to load predefined periods', err);
      })
      .finally(() => {
        if (!cancelled) setPeriodOptionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filteredPeriodOptions.length, periodKind]);

  const selectPeriodKind = (kind: PeriodKind) => {
    setPeriodKind(kind);
    if (kind === 'latest') {
      setSelectedPeriodSlug(data?.selected_period?.slug ?? null);
    }
  };

  const selectPeriod = async (option: ArchivePeriodOption) => {
    const nextKind = normalizePeriodKind(option.kind) ?? 'latest';
    setPeriodKind(nextKind);
    setSelectedPeriodSlug(option.slug);
    await loadIntelligence(option.slug, topicLimit);
  };

  const selectTopicLimit = async (limit: (typeof TOPIC_LIMITS)[number]) => {
    setTopicLimit(limit);
    await loadIntelligence(selectedPeriodSlug ?? data?.selected_period?.slug ?? null, limit);
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
        <div className="mt-2">{currentPeriodSummary}</div>
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
      {error && (
        <div className="rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning" role="alert">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-stretch">
        <div className="lg:order-1">{sectionsNav}</div>

        <div className="lg:order-2">
          <section id="overview" className="surface-card scroll-mt-24 space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <div className="archive-eyebrow">Explore</div>
              {refreshing && <span className="source-pill border-accent/30 text-accent">Refreshing</span>}
              <span className="source-pill">{currentPeriodKindLabel}</span>
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(18rem,1fr)] xl:items-end">
              <div className="space-y-3">
                <h1 className="page-title">Archive Intelligence</h1>
                <p className="max-w-3xl text-muted">Follow topics, search momentum, and cited timeline summaries across the HasanAbi archive.</p>
                <p className="text-sm text-subtle">{currentPeriodSummary}</p>
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

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
              <div className="rounded-2xl border border-border bg-surface-muted/70 p-4 shadow-[0_8px_24px_rgba(0,0,0,0.16)]">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="meta-label">Predefined periods</div>
                    <p className="text-sm text-muted">Period slices are calculated by the backfill/refresher pipeline, not by free-form live date filters.</p>
                  </div>
                  <div className="rounded-full border border-border bg-surface px-3 py-1 text-xs uppercase tracking-[0.18em] text-subtle">Backfilled</div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {PERIOD_KIND_TABS.map((tab) => {
                    const active = periodKind === tab.kind;
                    return (
                      <button
                        key={tab.kind}
                        type="button"
                        onClick={() => selectPeriodKind(tab.kind)}
                        aria-pressed={active}
                        className={`btn-ghost rounded-full border px-4 py-2 text-sm transition-colors ${
                          active ? 'border-accent/60 bg-accent/15 text-ink' : ''
                        }`}
                      >
                        {tab.label}
                      </button>
                    );
                  })}
                </div>

                <div className="mt-5 rounded-2xl border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="meta-label">Selected period</div>
                      <div className="mt-1 text-lg font-semibold text-ink">{currentPeriod?.label ?? 'Latest'}</div>
                      <div className="mt-1 text-sm text-muted">{currentPeriodSummary}</div>
                    </div>
                    {currentPeriod?.description && <p className="max-w-sm text-sm text-muted">{currentPeriod.description}</p>}
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-xl border border-border bg-surface-muted p-3 text-sm text-muted">
                      <div className="text-subtle">Period kind</div>
                      <div className="mt-1 font-semibold text-ink">{currentPeriodKindLabel}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-muted p-3 text-sm text-muted">
                      <div className="text-subtle">Range</div>
                      <div className="mt-1 font-semibold text-ink">{formatPeriodRange(currentPeriod) ?? '—'}</div>
                    </div>
                    <div className="rounded-xl border border-border bg-surface-muted p-3 text-sm text-muted">
                      <div className="text-subtle">Topics shown</div>
                      <div className="mt-1 font-semibold text-ink">{formatNumber(topicLimit)}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-border bg-surface-muted/70 p-4 shadow-[0_8px_24px_rgba(0,0,0,0.16)]">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="meta-label">Topic cards shown</div>
                    <p className="text-sm text-muted">Changing this refetches the currently selected predefined period immediately.</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {TOPIC_LIMITS.map((value) => {
                    const active = topicLimit === value;
                    return (
                      <button
                        key={value}
                        type="button"
                        onClick={() => {
                          void selectTopicLimit(value);
                        }}
                        aria-pressed={active}
                        className={`btn-ghost min-w-24 rounded-xl border px-4 py-2 text-sm transition-colors ${
                          active ? 'border-accent/60 bg-accent/15 text-ink' : ''
                        }`}
                        disabled={refreshing}
                      >
                        {value} topics
                      </button>
                    );
                  })}
                </div>

                <div className="mt-5 flex items-center justify-between gap-3">
                  <div>
                    <div className="meta-label">Period picker</div>
                    <p className="text-sm text-muted">Choose a predefined slice to refresh the intelligence snapshot instantly.</p>
                  </div>
                  <div className="text-xs uppercase tracking-[0.22em] text-subtle">
                    {periodOptionsLoading ? 'Loading periods…' : `${filteredPeriodOptions.length} options`}
                  </div>
                </div>

                {filteredPeriodOptions.length > 0 ? (
                  <div className="mt-4 max-h-[28rem] space-y-3 overflow-auto pr-1">
                    {filteredPeriodOptions.map((option) => {
                      const active = option.slug === (selectedPeriodSlug ?? data.selected_period?.slug);
                      const kindLabel = PERIOD_KIND_TABS.find((tab) => tab.kind === (normalizePeriodKind(option.kind) ?? 'latest'))?.label ?? option.kind;
                      return (
                        <button
                          key={option.slug}
                          type="button"
                          onClick={() => {
                            void selectPeriod(option);
                          }}
                          aria-pressed={active}
                          className={`w-full rounded-2xl border p-4 text-left transition-all focus:outline-none focus:ring-2 focus:ring-accent/35 ${
                            active
                              ? 'border-accent/60 bg-accent/10 shadow-[0_0_0_1px_rgba(183,255,60,0.12)]'
                              : 'border-border bg-surface hover:border-accent/50 hover:bg-surface-muted'
                          }`}
                          disabled={refreshing}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="text-base font-semibold text-ink">{option.label}</div>
                              <div className="mt-1 text-xs uppercase tracking-[0.2em] text-subtle">{kindLabel}</div>
                            </div>
                            <div className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-subtle">
                              {formatNumber(option.video_count)} VODs · {formatDuration(option.total_duration_seconds)}
                            </div>
                          </div>
                          <div className="mt-3 text-sm text-muted">{option.date_from} → {option.date_to}</div>
                          {option.description && <p className="mt-3 line-clamp-2 text-sm text-muted">{option.description}</p>}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-4 rounded-2xl border border-border bg-surface p-4 text-sm text-muted">
                    {periodOptionsLoading ? 'Loading predefined periods…' : 'No predefined periods available for this kind yet.'}
                  </div>
                )}
              </div>
            </div>
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

            {timelinePeriods.length > 0 ? (
              <div className="space-y-4">
                {timelinePeriods.map((period, index) => {
                  const isPrimary = index === 0;
                  const periodOption =
                    data.period_options.find((option) => option.slug === period.period) ??
                    (selectedOptionForTimeline?.slug === period.period ? selectedOptionForTimeline : null);
                  const browseHref = periodBrowseHref(periodOption);
                  const thumbnails = period.videos.filter((video) => Boolean(video.youtube_id)).slice(0, 3);

                  return (
                    <article
                      key={period.period}
                      className={`rounded-2xl border bg-surface-muted p-4 ${isPrimary ? 'border-accent/50 shadow-[0_0_0_1px_rgba(183,255,60,0.12)]' : 'border-border'}`}
                    >
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-xl font-semibold text-ink">{period.label}</h3>
                            {isPrimary && <span className="source-pill border-accent/30 text-accent">Selected period</span>}
                          </div>
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
              <div className="rounded-2xl border border-border bg-surface-muted p-5 text-center text-muted">No calculated stats for this predefined period yet.</div>
            )}
          </div>
        </section>

        <section id="method" className="surface-card scroll-mt-24 space-y-4">
          <h2 className="section-title">Method</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <p className="rounded-2xl border border-border bg-surface-muted p-4 text-muted">
              Predefined periods are materialized by a backfill/refresher pipeline, so Explore shows consistent slices instead of live date-window guesses.
            </p>
            <p className="rounded-2xl border border-border bg-surface-muted p-4 text-muted">
              Topics combine curated labels and automatic discovery. Summaries are citation-backed and mostly extractive today, with more generated synthesis coming later.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
