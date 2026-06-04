import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type {
  ArchiveEvidenceMoment,
  ArchivePeriodOption,
  ExploreIntelligenceResponse,
  VideoInfo,
} from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp } from '../features/archive/format';
import { VideoMetadataChips } from '../components/archive';

type PeriodKind = 'latest' | 'month' | 'week' | 'event' | 'leadup' | 'fallout' | 'holiday' | 'anniversary' | 'date';

const PERIOD_KIND_TABS: Array<{ kind: PeriodKind; label: string }> = [
  { kind: 'latest', label: 'Latest' },
  { kind: 'month', label: 'Months' },
  { kind: 'week', label: 'Weeks' },
  { kind: 'event', label: 'Events' },
  { kind: 'leadup', label: 'Leadups' },
  { kind: 'fallout', label: 'Fallout' },
  { kind: 'holiday', label: 'Holidays' },
  { kind: 'anniversary', label: 'Anniversaries' },
  { kind: 'date', label: 'Dates' },
];

const PERIOD_OPTION_FETCH_LIMIT = 24;

function topicHref(label: string) {
  return `/topics/${encodeURIComponent(label)}`;
}

function facetHref(label: string) {
  return `/search?q=${encodeURIComponent(label)}`;
}

function evidenceHref(moment: ArchiveEvidenceMoment) {
  return buildTimestampLink(moment.video.id, moment.start_ms);
}

function normalizePeriodKind(kind?: string | null): PeriodKind | null {
  if (!kind) return null;
  const value = kind.toLowerCase();
  if (value === 'latest' || value === 'all') return 'latest';
  if (value.startsWith('month')) return 'month';
  if (value.startsWith('week')) return 'week';
  if (value.startsWith('event')) return 'event';
  if (value.startsWith('leadup')) return 'leadup';
  if (value.startsWith('fallout')) return 'fallout';
  if (value.startsWith('holiday')) return 'holiday';
  if (value.startsWith('anniversary')) return 'anniversary';
  if (value.startsWith('date')) return 'date';
  return null;
}

function formatPeriodRange(option?: ArchivePeriodOption | null) {
  if (!option) return null;
  if (option.recurring_month && option.recurring_day) {
    const sample = new Date(Date.UTC(2024, option.recurring_month - 1, option.recurring_day));
    if (!Number.isNaN(sample.getTime())) {
      return `Every ${sample.toLocaleDateString(undefined, { month: 'long', day: 'numeric', timeZone: 'UTC' })}`;
    }
    return `Every ${option.recurring_month}/${option.recurring_day}`;
  }
  return `${option.date_from} → ${option.date_to}`;
}

function uniquePeriodOptions(...groups: Array<ArchivePeriodOption[] | undefined>) {
  const seen = new Set<string>();
  return groups.flat().filter((option): option is ArchivePeriodOption => {
    if (!option || seen.has(option.slug)) return false;
    seen.add(option.slug);
    return true;
  });
}

function periodKindLabel(kind?: string | null) {
  const normalized = normalizePeriodKind(kind) ?? 'latest';
  return PERIOD_KIND_TABS.find((tab) => tab.kind === normalized)?.label ?? 'Latest';
}

function topicKindLabel(kind?: string | null) {
  const value = (kind || 'topic').toLowerCase();
  if (value.includes('series')) return 'Series';
  if (value.includes('category')) return 'Category';
  if (value.includes('person')) return 'Person';
  return 'Topic';
}

function metadataChips(video: VideoInfo) {
  return [
    ...(video.people ?? []).map((person) => ({ key: `person-${person.slug}`, label: person.display_name })),
    ...(video.tags ?? []).map((tag) => ({ key: `tag-${tag.slug}`, label: tag.label })),
  ];
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriodSlug, setSelectedPeriodSlug] = useState<string | null>(null);
  const [periodKind, setPeriodKind] = useState<PeriodKind>('latest');
  const [periodOptionsByKind, setPeriodOptionsByKind] = useState<Partial<Record<Exclude<PeriodKind, 'latest'>, ArchivePeriodOption[]>>>({});
  const [periodOptionsLoading, setPeriodOptionsLoading] = useState(false);
  const cachedPeriodOptions = periodKind === 'latest' ? undefined : periodOptionsByKind[periodKind];

  const loadIntelligence = async (queryPeriod?: string | null, initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);

    try {
      const result = await api.getExploreIntelligence({
        ...(queryPeriod ? { period: queryPeriod } : {}),
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
    void loadIntelligence(undefined, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const selectedPeriodRecord = useMemo(() => {
    if (!data?.periods?.length) return null;
    const slug = currentPeriod?.slug ?? selectedPeriodSlug ?? data.selected_period?.slug ?? null;
    if (!slug) return data.periods[0] ?? null;
    const exactMatch = data.periods.find((period) => period.period === slug);
    if (exactMatch) return exactMatch;
    if (data.periods.length === 1 && currentPeriod?.label && data.periods[0]?.label === currentPeriod.label) {
      return data.periods[0];
    }
    return null;
  }, [currentPeriod?.label, currentPeriod?.slug, data?.periods, data?.selected_period?.slug, selectedPeriodSlug]);

  const selectedPeriodNarrative = selectedPeriodRecord?.summary ?? currentPeriod?.description ?? '';

  const selectedPeriodSummary = useMemo(() => {
    const pieces = [currentPeriod?.label ?? 'Latest'];
    const range = formatPeriodRange(currentPeriod);
    if (range) pieces.push(range);
    pieces.push('best available topics');
    return pieces.join(' · ');
  }, [currentPeriod]);

  const selectedPeriodKindLabel = useMemo(
    () => (periodKind === 'latest' ? periodKindLabel(currentPeriod?.kind) : periodKindLabel(periodKind)),
    [currentPeriod?.kind, periodKind]
  );

  const selectedPeriodVods = currentPeriod?.video_count ?? selectedPeriodRecord?.video_count ?? 0;
  const selectedPeriodDuration = currentPeriod?.total_duration_seconds ?? selectedPeriodRecord?.total_duration_seconds ?? 0;
  const selectedPeriodEvidence = selectedPeriodRecord?.evidence ?? [];
  const selectedPeriodVideos = selectedPeriodRecord?.videos ?? [];
  const selectedPeriodIsEmpty = selectedPeriodVods === 0;

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
      setSelectedPeriodSlug(null);
      void loadIntelligence(undefined);
    }
  };

  const selectPeriodBySlug = async (slug: string) => {
    if (!slug) return;
    const option = periodOptions.find((item) => item.slug === slug) ?? data?.selected_period ?? null;
    if (!option) return;
    const nextKind = normalizePeriodKind(option.kind) ?? 'latest';
    setPeriodKind(nextKind);
    setSelectedPeriodSlug(option.slug);
    await loadIntelligence(option.slug);
  };


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

      <section className="surface-card space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="archive-eyebrow">Explore</div>
              {refreshing && <span className="source-pill border-accent/30 text-accent">Refreshing</span>}
              <span className="source-pill">{selectedPeriodKindLabel}</span>
            </div>
            <div className="space-y-2">
              <h1 className="page-title">Explore the HasanAbi VOD archive</h1>
              <p className="max-w-3xl text-muted">
                Browse predefined archive periods, surface people, tags, and stream labels, then jump from a selected slice into cited moments.
              </p>
            </div>
          </div>

          <div className="grid w-full gap-3 sm:grid-cols-3 lg:max-w-3xl">
            <div className="rounded-2xl border border-border bg-surface-muted p-4">
              <div className="text-xs uppercase tracking-wide text-subtle">Total VODs</div>
              <div className="mt-1 text-2xl font-semibold text-ink">{formatNumber(data.summary.video_count)}</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-4">
              <div className="text-xs uppercase tracking-wide text-subtle">Transcript hours</div>
              <div className="mt-1 text-2xl font-semibold text-ink">{formatDuration(data.summary.total_duration_seconds)}</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface-muted p-4">
              <div className="text-xs uppercase tracking-wide text-subtle">Selected period VODs</div>
              <div className="mt-1 text-2xl font-semibold text-ink">{formatNumber(selectedPeriodVods)}</div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)] xl:items-end">
          <div className="space-y-4">
            <div>
              <div className="meta-label">Period kind</div>
              <div role="tablist" aria-label="Period kind" className="mt-3 flex flex-wrap gap-2">
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
            </div>

            <div>
              <label htmlFor="selected-period" className="meta-label">
                Selected period
              </label>
              <select
                id="selected-period"
                className="mt-3 w-full rounded-2xl border border-border bg-surface px-4 py-3 text-sm text-ink shadow-[0_8px_20px_rgba(0,0,0,0.12)] outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/25"
                value={currentPeriod?.slug ?? data.selected_period?.slug ?? ''}
                onChange={(event) => {
                  void selectPeriodBySlug(event.target.value);
                }}
                disabled={periodOptionsLoading && periodOptions.length === 0}
              >
                <option value="">Select a period</option>
                {periodOptions.map((option) => (
                  <option key={option.slug} value={option.slug}>
                    {option.label} — {formatPeriodRange(option)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-surface-muted/70 p-4 shadow-[0_8px_24px_rgba(0,0,0,0.16)]">
            <div className="meta-label">Label discovery</div>
            <p className="mt-2 text-sm text-muted">
              Topics and stream labels are generated from available Whisper and YouTube transcripts, then the strongest cited cards are surfaced automatically.
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)] lg:items-start">
        <nav aria-label="Discovery rail" className="surface-card space-y-4 lg:sticky lg:top-24">
          <div className="space-y-1">
            <div className="archive-eyebrow">Discovery rail</div>
            <p className="text-sm text-muted">Browse the loaded periods for the selected kind.</p>
          </div>

          <div className="rounded-2xl border border-border bg-surface-muted/70 p-3 text-xs text-muted">
            <div className="meta-label">Current kind</div>
            <div className="mt-1 font-medium text-ink">{selectedPeriodKindLabel}</div>
            <div className="mt-1">{periodOptionsLoading ? 'Loading periods…' : `${filteredPeriodOptions.length} options`}</div>
          </div>

          {filteredPeriodOptions.length > 0 ? (
            <div className="space-y-3">
              {filteredPeriodOptions.map((option) => {
                const active = option.slug === (currentPeriod?.slug ?? data.selected_period?.slug);
                const kindLabel = periodKindLabel(option.kind);
                return (
                  <button
                    key={option.slug}
                    type="button"
                    onClick={() => {
                      void selectPeriodBySlug(option.slug);
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
                      <div className="space-y-1">
                        <div className="text-base font-semibold text-ink">{option.label}</div>
                        <div className="text-xs uppercase tracking-[0.2em] text-subtle">{kindLabel}</div>
                      </div>
                      <div className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-subtle">
                        {formatNumber(option.video_count)} VODs · {formatDuration(option.total_duration_seconds)}
                      </div>
                    </div>
                    <div className="mt-3 text-sm text-muted">{formatPeriodRange(option)}</div>
                    {option.description && <p className="mt-3 line-clamp-2 text-sm text-muted">{option.description}</p>}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-surface p-4 text-sm text-muted">
              {periodOptionsLoading ? 'Loading predefined periods…' : 'No predefined periods available for this kind yet.'}
            </div>
          )}
        </nav>

        <div className="space-y-6 lg:space-y-8">
          <section aria-label="Selected period panel" className="surface-card space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="meta-label">Selected period</div>
                <h2 className="mt-1 text-2xl font-semibold text-ink">{currentPeriod?.label ?? 'Latest'}</h2>
                <p className="mt-1 text-sm text-muted">{selectedPeriodSummary}</p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs text-muted sm:min-w-[18rem]">
                <div className="rounded-2xl border border-border bg-surface-muted p-3">
                  <div className="text-subtle">Period kind</div>
                  <div className="mt-1 font-semibold text-ink">{selectedPeriodKindLabel}</div>
                </div>
                <div className="rounded-2xl border border-border bg-surface-muted p-3">
                  <div className="text-subtle">Range</div>
                  <div className="mt-1 font-semibold text-ink">{formatPeriodRange(currentPeriod) ?? '—'}</div>
                </div>
                <div className="rounded-2xl border border-border bg-surface-muted p-3">
                  <div className="text-subtle">Duration</div>
                  <div className="mt-1 font-semibold text-ink">{formatDuration(selectedPeriodDuration)}</div>
                </div>
              </div>
            </div>

            {currentPeriod?.description && <p className="max-w-4xl text-sm text-muted">{currentPeriod.description}</p>}

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(16rem,0.85fr)]">
              <div>
                <div className="meta-label">Evidence moments</div>
                {selectedPeriodEvidence.length > 0 ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {selectedPeriodEvidence.map((moment) => (
                      <Link
                        key={`${moment.video.id}-${moment.start_ms}`}
                        to={evidenceHref(moment)}
                        className="rounded-2xl border border-border bg-surface p-4 transition-colors hover:border-accent hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-accent/35"
                      >
                        <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
                          <span>{formatTimestamp(moment.start_ms)} · Open cited moment</span>
                          <span className="line-clamp-1 text-right">{moment.video.title || 'Untitled VOD'}</span>
                        </div>
                        <div className="mt-2 line-clamp-2 text-sm text-ink">{moment.snippet}</div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-2xl border border-border bg-surface-muted p-4 text-sm text-muted">No cited moments for this period yet.</div>
                )}
              </div>

              <div className="rounded-2xl border border-border bg-surface-muted/70 p-4">
                <div className="meta-label">Period summary</div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <div className="rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                    <div className="text-subtle">VOD count</div>
                    <div className="mt-1 font-semibold text-ink">{formatNumber(selectedPeriodVods)}</div>
                  </div>
                  <div className="rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                    <div className="text-subtle">Label cards</div>
                    <div className="mt-1 font-semibold text-ink">{formatNumber(data.topic_cards.length)}</div>
                  </div>
                </div>
                {selectedPeriodNarrative ? (
                  <div className="mt-4 space-y-2 text-sm text-muted">
                    <p>{selectedPeriodNarrative}</p>
                    {selectedPeriodIsEmpty ? <p>No archived VODs were found for this selected period yet. Try a nearby month, week, or broader event window.</p> : null}
                  </div>
                ) : selectedPeriodIsEmpty ? (
                  <p className="mt-4 text-sm text-muted">
                    No archived VODs were found for this selected period yet. Try a nearby month, week, or broader event window.
                  </p>
                ) : (
                  <p className="mt-4 text-sm text-muted">
                    Selected periods are calculated snapshots. Use the kind tabs, the period rail, and the dropdown to jump between predefined archive slices.
                  </p>
                )}
              </div>
            </div>
          </section>

          <section className="surface-card space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="section-title">Discovery facets</h2>
                <p className="text-sm text-muted">People and tags surfaced from top-level archive intelligence facets.</p>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-2xl border border-border bg-surface-muted p-4">
                <div className="meta-label">People</div>
                {data.people?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {data.people.map((person) => (
                      <Link
                        key={person.slug}
                        to={facetHref(person.display_name)}
                        className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/35"
                      >
                        {person.display_name}
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 text-sm text-muted">No people facets yet.</div>
                )}
              </div>

              <div className="rounded-2xl border border-border bg-surface-muted p-4">
                <div className="meta-label">Tags</div>
                {data.tags?.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {data.tags.map((tag) => (
                      <Link
                        key={tag.slug}
                        to={facetHref(tag.label)}
                        className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-2 text-sm font-medium text-ink transition-colors hover:border-accent hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/35"
                      >
                        {tag.label}
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 text-sm text-muted">No tags facets yet.</div>
                )}
              </div>
            </div>
          </section>

          <section id="topics" className="surface-card space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="section-title">Detected topics and stream labels</h2>
                <p className="text-sm text-muted">Topic, series, category, and person cards with momentum, aliases, and cited evidence.</p>
              </div>
              <div className="text-xs uppercase tracking-[0.22em] text-subtle">{formatNumber(data.topic_cards.length)} labels</div>
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
                        <span className="source-pill">{topicKindLabel(topic.kind)}</span>
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

          <section className="surface-card space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="section-title">Timeline / evidence</h2>
                <p className="text-sm text-muted">Scoped to the selected period with representative thumbnails and cited moments.</p>
              </div>
              <div className="text-xs uppercase tracking-[0.22em] text-subtle">{formatNumber(selectedPeriodVideos.length)} VODs</div>
            </div>

            {selectedPeriodRecord ? (
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
                {selectedPeriodVideos.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {selectedPeriodVideos.slice(0, 3).map((video) => (
                      <article key={video.id} className="overflow-hidden rounded-2xl border border-border bg-surface-muted shadow-[0_8px_18px_rgba(0,0,0,0.16)]">
                        <img
                          src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
                          alt={video.title || 'VOD thumbnail'}
                          className="aspect-video w-full object-cover"
                          loading="lazy"
                        />
                        <div className="space-y-2 p-3 text-xs text-muted">
                          <div className="line-clamp-2 font-medium text-ink">{video.title || 'Untitled VOD'}</div>
                          <div className="line-clamp-1 text-subtle">{formatDate(video.uploaded_at ?? null)}</div>
                          {metadataChips(video).length > 0 ? (
                            <VideoMetadataChips label="VOD metadata" items={metadataChips(video)} limit={3} className="flex flex-wrap gap-1" />
                          ) : null}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-border bg-surface-muted p-5 text-center text-muted">
                    {selectedPeriodIsEmpty ? 'No archived VODs were found in this selected period.' : 'No representative VODs calculated for this period yet.'}
                  </div>
                )}

                <div className="space-y-3">
                  <div className="meta-label">Cited moments</div>
                  {selectedPeriodEvidence.length > 0 ? (
                    <div className="space-y-3">
                      {selectedPeriodEvidence.map((moment) => (
                        <Link
                          key={`timeline-${moment.video.id}-${moment.start_ms}`}
                          to={evidenceHref(moment)}
                          className="block rounded-2xl border border-border bg-surface p-4 transition-colors hover:border-accent hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-accent/35"
                        >
                          <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-wide text-subtle">
                            <span>{formatTimestamp(moment.start_ms)} · Open cited moment</span>
                            <span className="line-clamp-1 text-right">{moment.video.title || 'Untitled VOD'}</span>
                          </div>
                          <div className="mt-2 line-clamp-2 text-sm text-ink">{moment.snippet}</div>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-border bg-surface-muted p-4 text-sm text-muted">No cited moments for this selected period yet.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-surface-muted p-5 text-center text-muted">
                {selectedPeriodIsEmpty ? 'No archived VODs were found for this selected period yet.' : 'No calculated stats for this predefined period yet.'}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
