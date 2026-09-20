import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../services';
import type { ArchivePeriodOption, ExploreIntelligenceResponse } from '../types/api';
import {
  formatDate,
  formatAggregateDuration,
  formatNumber,
  formatTimestamp,
} from '../features/archive/format';
import { VideoMetadataChips } from '../components/archive';
import { AsyncError } from '../components/async/AsyncFeedback';
import {
  evidenceHref,
  facetHref,
  formatPeriodRange,
  metadataChips,
  normalizePeriodKind,
  PERIOD_KIND_TABS,
  PERIOD_OPTION_FETCH_LIMIT,
  periodKindLabel,
  topicHref,
  topicKindLabel,
  uniquePeriodOptions,
} from '../features/archive/exploreModel';
import type { PeriodKind } from '../features/archive/exploreModel';

export default function ExplorePage() {
  const [urlParams, setUrlParams] = useSearchParams();
  const initialKind = normalizePeriodKind(urlParams.get('kind')) ?? 'latest';
  const [data, setData] = useState<ExploreIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriodSlug, setSelectedPeriodSlug] = useState<string | null>(
    urlParams.get('period')
  );
  const [periodKind, setPeriodKind] = useState<PeriodKind>(initialKind);
  const [granularity, setGranularity] = useState<'week' | 'month'>(
    urlParams.get('granularity') === 'week' ? 'week' : 'month'
  );
  const [dateFrom, setDateFrom] = useState(urlParams.get('date_from') ?? '');
  const [dateTo, setDateTo] = useState(urlParams.get('date_to') ?? '');
  const [periodOptionsByKind, setPeriodOptionsByKind] = useState<
    Partial<Record<Exclude<PeriodKind, 'latest'>, ArchivePeriodOption[]>>
  >({});
  const [periodOptionsLoading, setPeriodOptionsLoading] = useState(false);
  const [periodOptionsError, setPeriodOptionsError] = useState<string | null>(null);
  const [periodOptionsRetry, setPeriodOptionsRetry] = useState(0);
  const [periodSearch, setPeriodSearch] = useState('');
  const [topicLimit, setTopicLimit] = useState(6);
  const [evidenceLimit, setEvidenceLimit] = useState(3);
  const cachedPeriodOptions = periodKind === 'latest' ? undefined : periodOptionsByKind[periodKind];

  const loadIntelligence = async (queryPeriod?: string | null, initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const result = await api.getExploreIntelligence({
        ...(queryPeriod ? { period: queryPeriod } : {}),
        ...(granularity !== 'month' ? { granularity } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      });
      setData(result);
      if (result.selected_period?.slug) setSelectedPeriodSlug(result.selected_period.slug);
      else if (queryPeriod) setSelectedPeriodSlug(queryPeriod);
    } catch (err: unknown) {
      console.error('Failed to load archive intelligence', err);
      setError(
        'Archive intelligence could not be refreshed. The last successful snapshot is still shown.'
      );
      if (!data) setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadIntelligence(urlParams.get('period'), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const periodOptions = useMemo(
    () => uniquePeriodOptions(data?.period_options, cachedPeriodOptions),
    [data?.period_options, cachedPeriodOptions]
  );
  const filteredPeriodOptions = useMemo(
    () =>
      periodKind === 'latest'
        ? periodOptions
        : periodOptions.filter((option) => normalizePeriodKind(option.kind) === periodKind),
    [periodKind, periodOptions]
  );
  const searchedPeriodOptions = useMemo(() => {
    const needle = periodSearch.trim().toLocaleLowerCase();
    return needle
      ? filteredPeriodOptions.filter((option) =>
          `${option.label} ${option.description ?? ''}`.toLocaleLowerCase().includes(needle)
        )
      : filteredPeriodOptions;
  }, [filteredPeriodOptions, periodSearch]);
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
    if (
      data.periods.length === 1 &&
      currentPeriod?.label &&
      data.periods[0]?.label === currentPeriod.label
    )
      return data.periods[0];
    return null;
  }, [
    currentPeriod?.label,
    currentPeriod?.slug,
    data?.periods,
    data?.selected_period?.slug,
    selectedPeriodSlug,
  ]);

  const selectedPeriodNarrative = selectedPeriodRecord?.summary ?? currentPeriod?.description ?? '';
  const selectedPeriodSummary = useMemo(() => {
    const pieces = [currentPeriod?.label ?? 'Latest'];
    const range = formatPeriodRange(currentPeriod);
    if (range) pieces.push(range);
    pieces.push('best available topics');
    return pieces.join(' · ');
  }, [currentPeriod]);
  const selectedPeriodKindLabel = useMemo(
    () =>
      periodKind === 'latest' ? periodKindLabel(currentPeriod?.kind) : periodKindLabel(periodKind),
    [currentPeriod?.kind, periodKind]
  );
  const selectedPeriodVods = currentPeriod?.video_count ?? selectedPeriodRecord?.video_count ?? 0;
  const selectedPeriodDuration =
    currentPeriod?.total_duration_seconds ?? selectedPeriodRecord?.total_duration_seconds ?? 0;
  const selectedPeriodEvidence = selectedPeriodRecord?.evidence ?? [];
  const selectedPeriodVideos = selectedPeriodRecord?.videos ?? [];
  const selectedPeriodIsEmpty = selectedPeriodVods === 0;

  useEffect(() => {
    if (periodKind === 'latest' || cachedPeriodOptions !== undefined) {
      setPeriodOptionsLoading(false);
      setPeriodOptionsError(null);
      return;
    }
    let cancelled = false;
    setPeriodOptionsLoading(true);
    setPeriodOptionsError(null);
    void api
      .getExplorePeriods({ kind: periodKind, limit: PERIOD_OPTION_FETCH_LIMIT })
      .then((response) => {
        if (!cancelled)
          setPeriodOptionsByKind((current) => ({
            ...current,
            [periodKind]: response.periods ?? [],
          }));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.error('Failed to load predefined periods', err);
          setPeriodOptionsError('Predefined archive periods could not be loaded.');
        }
      })
      .finally(() => {
        if (!cancelled) setPeriodOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cachedPeriodOptions, periodKind, periodOptionsRetry]);

  const selectPeriodKind = (kind: PeriodKind) => {
    setPeriodKind(kind);
    const next = new URLSearchParams(urlParams);
    if (kind === 'latest') next.delete('kind');
    else next.set('kind', kind);
    if (kind === 'latest') {
      setSelectedPeriodSlug(null);
      next.delete('period');
      void loadIntelligence(undefined);
    }
    setUrlParams(next);
  };

  const selectPeriodBySlug = async (slug: string) => {
    if (!slug) return;
    const option =
      periodOptions.find((item) => item.slug === slug) ?? data?.selected_period ?? null;
    if (!option) return;
    setPeriodKind(normalizePeriodKind(option.kind) ?? 'latest');
    setSelectedPeriodSlug(option.slug);
    const next = new URLSearchParams(urlParams);
    next.set('period', option.slug);
    next.set('kind', normalizePeriodKind(option.kind) ?? 'latest');
    setUrlParams(next);
    await loadIntelligence(option.slug);
  };

  const applyRange = () => {
    const next = new URLSearchParams(urlParams);
    if (granularity === 'month') next.delete('granularity');
    else next.set('granularity', granularity);
    if (dateFrom) next.set('date_from', dateFrom);
    else next.delete('date_from');
    if (dateTo) next.set('date_to', dateTo);
    else next.delete('date_to');
    setUrlParams(next);
    void loadIntelligence(selectedPeriodSlug);
  };

  if (loading) {
    return (
      <div
        className="archive-masthead min-h-[34rem] animate-pulse p-8"
        role="status"
        aria-live="polite"
      >
        <h1 className="sr-only">Explore the recording archive</h1>
        <div className="h-5 w-28 rounded bg-surface-muted" />
        <div className="mt-7 h-14 max-w-3xl rounded bg-surface-muted" />
        <div className="mt-5 h-5 max-w-xl rounded bg-surface-muted" />
        <span className="sr-only">Loading archive intelligence…</span>
      </div>
    );
  }

  if (!data)
    return (
      <div className="archive-section text-center text-muted">
        <h1 className="page-title">Explore the recording archive</h1>
        <p className="mt-3">Archive intelligence is not available yet.</p>
        {error ? (
          <div className="mt-4">
            <AsyncError
              onRetry={() => void loadIntelligence(urlParams.get('period'), true)}
              retryLabel="Retry archive intelligence"
            >
              Archive intelligence could not be loaded.
            </AsyncError>
          </div>
        ) : null}
      </div>
    );

  return (
    <div className="space-y-5 lg:space-y-7">
      {error && (
        <AsyncError
          onRetry={() => void loadIntelligence(selectedPeriodSlug ?? urlParams.get('period'))}
          retryLabel="Retry archive intelligence"
        >
          {error}
        </AsyncError>
      )}

      <section className="archive-masthead">
        <div className="relative z-10 grid gap-8 p-5 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,0.7fr)] lg:items-end lg:p-10">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="archive-eyebrow">Explore</div>
              {refreshing && (
                <span className="source-pill border-accent/30 text-accent">Refreshing</span>
              )}
              <span className="source-pill">{selectedPeriodKindLabel}</span>
            </div>
            <h1 className="mt-5 max-w-4xl text-5xl font-semibold leading-[0.92] tracking-[-0.06em] text-ink sm:text-7xl">
              Explore the recording archive
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-muted sm:text-lg">
              Follow a period, topic, person, or recurring stream label into the broadcasts and
              cited transcript moments behind it.
            </p>
          </div>

          <div className="archive-panel space-y-4">
            <div className="archive-rule-title">Choose a window</div>
            <label htmlFor="selected-period" className="meta-label">
              Selected period
            </label>
            <select
              id="selected-period"
              className="form-control min-h-[50px]"
              value={currentPeriod?.slug ?? data.selected_period?.slug ?? ''}
              onChange={(event) => void selectPeriodBySlug(event.target.value)}
              disabled={periodOptionsLoading && periodOptions.length === 0}
            >
              <option value="">Select a period</option>
              {periodOptions.map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.label} — {formatPeriodRange(option)}
                </option>
              ))}
            </select>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtle">
              <span>{formatPeriodRange(currentPeriod)}</span>
              <span>{formatNumber(selectedPeriodVods)} VODs</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="meta-label">
                From
                <input
                  name="date_from"
                  type="date"
                  className="form-control mt-1 min-h-11 w-full"
                  value={dateFrom}
                  onChange={(event) => setDateFrom(event.target.value)}
                />
              </label>
              <label className="meta-label">
                To
                <input
                  name="date_to"
                  type="date"
                  className="form-control mt-1 min-h-11 w-full"
                  value={dateTo}
                  onChange={(event) => setDateTo(event.target.value)}
                />
              </label>
              <label className="meta-label">
                Granularity
                <select
                  name="granularity"
                  className="form-control mt-1 min-h-11 w-full"
                  value={granularity}
                  onChange={(event) =>
                    setGranularity(event.target.value === 'week' ? 'week' : 'month')
                  }
                >
                  <option value="week">Week</option>
                  <option value="month">Month</option>
                </select>
              </label>
              <button type="button" className="btn min-h-11 self-end" onClick={applyRange}>
                Apply range
              </button>
            </div>
          </div>
        </div>

        <div
          role="group"
          aria-label="Period kind"
          className="relative z-10 flex gap-1 overflow-x-auto border-t border-border bg-canvas/35 p-2 scrollbar-hidden sm:px-5"
        >
          {PERIOD_KIND_TABS.map((tab) => {
            const active = periodKind === tab.kind;
            return (
              <button
                key={tab.kind}
                type="button"
                onClick={() => selectPeriodKind(tab.kind)}
                aria-pressed={active}
                className={`min-h-11 shrink-0 rounded-lg px-4 py-2.5 text-xs font-bold uppercase tracking-[0.12em] transition-colors ${active ? 'bg-accent text-accent-contrast' : 'text-muted hover:bg-surface-muted hover:text-ink'}`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[17rem_minmax(0,1fr)] lg:items-start">
        <nav
          aria-label="Discovery rail"
          className="overflow-hidden rounded-2xl border border-border bg-surface/90 lg:sticky lg:top-24"
        >
          <div className="border-b border-border p-4">
            <div className="archive-eyebrow">Discovery rail</div>
            <p className="mt-3 text-sm leading-6 text-muted">
              {periodOptionsLoading
                ? 'Loading periods…'
                : `${searchedPeriodOptions.length} ${selectedPeriodKindLabel.toLowerCase()} windows`}
            </p>
            <label className="sr-only" htmlFor="period-search">
              Search periods
            </label>
            <input
              id="period-search"
              className="form-control mt-3"
              type="search"
              value={periodSearch}
              onChange={(event) => setPeriodSearch(event.target.value)}
              placeholder="Search periods"
            />
          </div>
          <div className="max-h-[32rem] overflow-y-auto">
            {periodOptionsError && (
              <div className="border-b border-border p-4">
                <AsyncError
                  onRetry={() => setPeriodOptionsRetry((value) => value + 1)}
                  retryLabel="Retry predefined periods"
                >
                  {periodOptionsError}
                </AsyncError>
              </div>
            )}
            {searchedPeriodOptions.length > 0 ? (
              searchedPeriodOptions.map((option) => {
                const active = option.slug === (currentPeriod?.slug ?? data.selected_period?.slug);
                return (
                  <button
                    key={option.slug}
                    type="button"
                    onClick={() => void selectPeriodBySlug(option.slug)}
                    aria-pressed={active}
                    className={`period-button ${active ? 'period-button-active' : ''}`}
                    disabled={refreshing}
                  >
                    <span className="block text-sm font-semibold text-ink">{option.label}</span>
                    <span className="mt-1 block font-mono text-[9px] uppercase tracking-[0.12em] text-subtle">
                      {periodKindLabel(option.kind)} · {formatNumber(option.video_count)} VODs
                    </span>
                    {option.description && (
                      <span className="mt-2 line-clamp-2 block text-xs leading-5 text-muted">
                        {option.description}
                      </span>
                    )}
                  </button>
                );
              })
            ) : (
              <div className="p-4 text-sm leading-6 text-muted">
                {periodOptionsLoading
                  ? 'Loading predefined periods…'
                  : periodOptionsError
                    ? 'Predefined periods are temporarily unavailable.'
                    : 'No predefined periods are available for this kind yet.'}
              </div>
            )}
          </div>
        </nav>

        <div className="min-w-0 space-y-5">
          <section aria-label="Selected period panel" className="archive-section">
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(17rem,0.8fr)]">
              <div>
                <div className="archive-eyebrow">Current window</div>
                <h2 className="mt-4 text-4xl font-semibold tracking-[-0.055em] text-ink sm:text-5xl">
                  {currentPeriod?.label ?? 'Latest archive window'}
                </h2>
                <p className="mt-3 font-mono text-xs uppercase tracking-[0.1em] text-subtle">
                  {selectedPeriodSummary}
                </p>
                <p className="mt-5 max-w-3xl text-base leading-7 text-muted">
                  {selectedPeriodNarrative ||
                    (selectedPeriodIsEmpty
                      ? 'No archived VODs were found for this period. Try a nearby window.'
                      : 'A calculated snapshot of the strongest topics and cited moments in this archive window.')}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border">
                {[
                  ['VODs', formatNumber(selectedPeriodVods)],
                  ['Runtime', formatAggregateDuration(selectedPeriodDuration)],
                  ['Labels', formatNumber(data.topic_cards.length)],
                  ['Evidence', formatNumber(selectedPeriodEvidence.length)],
                ].map(([label, value]) => (
                  <div key={label} className="bg-surface-muted p-4">
                    <dt className="meta-label">{label}</dt>
                    <dd className="mt-2 font-mono text-lg font-semibold text-ink">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <section id="topics" className="archive-section space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="archive-eyebrow">Label discovery</div>
                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
                  Detected topics and stream labels
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Transcript-derived subjects, recurring series, and people, ranked with evidence.
                </p>
              </div>
              <div className="font-mono text-xs uppercase tracking-[0.18em] text-subtle">
                {formatNumber(data.topic_cards.length)} labels
              </div>
            </div>

            {data.topic_cards.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {data.topic_cards.slice(0, topicLimit).map((topic, index) => (
                  <Link
                    key={topic.slug}
                    to={topicHref(topic.label)}
                    className="signal-card min-h-[15rem]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <span className="source-pill">{topicKindLabel(topic.kind)}</span>
                        <h3 className="mt-3 text-xl font-semibold tracking-[-0.035em] text-ink group-hover:text-accent">
                          {topic.label}
                        </h3>
                      </div>
                      <span className="font-mono text-[10px] text-subtle">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                    </div>
                    <div className="mt-5 grid grid-cols-3 gap-3 border-y border-border/70 py-3">
                      <div>
                        <div className="meta-label">Moments</div>
                        <div className="mt-1 font-mono text-sm text-ink">
                          {formatNumber(topic.total_moments)}
                        </div>
                      </div>
                      <div>
                        <div className="meta-label">VODs</div>
                        <div className="mt-1 font-mono text-sm text-ink">
                          {formatNumber(topic.total_videos)}
                        </div>
                      </div>
                      <div>
                        <div className="meta-label">90d</div>
                        <div className="mt-1 font-mono text-sm text-ink">
                          {formatNumber(topic.recent_mentions_90d)}
                        </div>
                      </div>
                    </div>
                    {topic.evidence[0] ? (
                      <blockquote className="mt-4 line-clamp-3 font-serif text-sm leading-6 text-muted">
                        “{topic.evidence[0].snippet}”
                      </blockquote>
                    ) : (
                      <p className="mt-4 text-sm text-muted">
                        Open the topic map to inspect this label across the archive.
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
                No topic cards are available for this window yet.
              </div>
            )}
            {data.topic_cards.length > topicLimit && (
              <button
                type="button"
                className="btn-secondary w-full"
                onClick={() => setTopicLimit((value) => value + 6)}
              >
                Load more topics
              </button>
            )}
          </section>

          <section className="archive-section space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="archive-eyebrow">Source material</div>
                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
                  VODs and cited moments
                </h2>
              </div>
              <div className="font-mono text-xs uppercase tracking-[0.18em] text-subtle">
                {formatNumber(selectedPeriodVideos.length)} representative VODs
              </div>
            </div>

            {selectedPeriodRecord ? (
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.85fr)]">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {selectedPeriodVideos.length > 0 ? (
                    selectedPeriodVideos.slice(0, 3).map((video) => (
                      <Link
                        to={`/v/${video.id}`}
                        key={video.id}
                        className="group overflow-hidden rounded-xl border border-border bg-surface-muted transition-colors hover:border-accent/60"
                      >
                        <div className="aspect-video overflow-hidden bg-canvas">
                          <img
                            src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
                            alt={video.title || 'VOD thumbnail'}
                            className="h-full w-full object-cover opacity-85 transition duration-500 group-hover:scale-[1.025] group-hover:opacity-100"
                            loading="lazy"
                            width="480"
                            height="360"
                          />
                        </div>
                        <div className="p-3">
                          <div className="line-clamp-2 text-sm font-semibold text-ink group-hover:text-accent">
                            {video.title || 'Untitled VOD'}
                          </div>
                          <div className="mt-2 font-mono text-[9px] uppercase tracking-[0.1em] text-subtle">
                            {formatDate(video.uploaded_at ?? null)}
                          </div>
                          {metadataChips(video).length > 0 && (
                            <VideoMetadataChips
                              label="VOD metadata"
                              items={metadataChips(video)}
                              limit={3}
                              className="mt-3 flex flex-wrap gap-1"
                            />
                          )}
                        </div>
                      </Link>
                    ))
                  ) : (
                    <div className="col-span-full rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
                      No representative VODs are available for this period yet.
                    </div>
                  )}
                </div>

                <div className="overflow-hidden rounded-xl border border-border bg-surface-muted/40">
                  <div className="border-b border-border px-4 py-3">
                    <div className="archive-rule-title">Cited moments</div>
                  </div>
                  {selectedPeriodEvidence.length > 0 ? (
                    selectedPeriodEvidence.slice(0, evidenceLimit).map((moment, index) => (
                      <Link
                        key={`${moment.video.id}-${moment.start_ms}`}
                        to={evidenceHref(moment)}
                        aria-label={`Open cited moment at ${formatTimestamp(moment.start_ms)} in ${moment.video.title || 'VOD'}`}
                        className="group grid grid-cols-[3.5rem_minmax(0,1fr)] gap-3 border-b border-border/70 p-4 last:border-b-0 hover:bg-surface-muted"
                      >
                        <div>
                          <div className="font-mono text-[9px] text-subtle">
                            {String(index + 1).padStart(2, '0')}
                          </div>
                          <div className="mt-1 font-mono text-xs font-semibold text-warning">
                            {formatTimestamp(moment.start_ms)}
                          </div>
                        </div>
                        <div>
                          <div className="line-clamp-2 text-sm leading-6 text-ink">
                            {moment.snippet}
                          </div>
                          <div className="mt-2 line-clamp-1 text-xs text-subtle group-hover:text-accent">
                            {moment.video.title || 'Untitled VOD'} →
                          </div>
                        </div>
                      </Link>
                    ))
                  ) : (
                    <div className="p-5 text-sm leading-6 text-muted">
                      No cited moments are available for this selected period yet.
                    </div>
                  )}
                  {selectedPeriodEvidence.length > evidenceLimit && (
                    <button
                      type="button"
                      className="btn-secondary m-3 w-[calc(100%-1.5rem)]"
                      onClick={() => setEvidenceLimit((value) => value + 5)}
                    >
                      Show more evidence
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
                No calculated source material is available for this period yet.
              </div>
            )}
          </section>

          <section className="archive-section">
            <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
              <div>
                <div className="archive-eyebrow">Discovery facets</div>
                <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
                  People and tags
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Open a facet as a transcript search.
                </p>
              </div>
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <div className="archive-rule-title">People</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {data.people?.length ? (
                      data.people.map((person) => (
                        <Link
                          key={person.slug}
                          to={facetHref(person.display_name)}
                          className="btn-secondary min-h-9 px-3 text-sm"
                        >
                          {person.display_name}
                        </Link>
                      ))
                    ) : (
                      <span className="text-sm text-muted">No people facets yet.</span>
                    )}
                  </div>
                </div>
                <div>
                  <div className="archive-rule-title">Tags</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {data.tags?.length ? (
                      data.tags.map((tag) => (
                        <Link
                          key={tag.slug}
                          to={facetHref(tag.label)}
                          className="btn-secondary min-h-9 px-3 text-sm"
                        >
                          {tag.label}
                        </Link>
                      ))
                    ) : (
                      <span className="text-sm text-muted">No tag facets yet.</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
