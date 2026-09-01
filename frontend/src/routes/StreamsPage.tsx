import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { StreamCard } from '../components/archive';
import { buildTimestampLink, formatTimestamp } from '../features/archive/format';
import { DEFAULT_LIMIT } from '../features/streams/library';
import { api } from '../services';
import type { MomentDiscoveryItem, PageInfo, TopicDiscoveryItem, VideoInfo } from '../types/api';

type FeedTab = 'latest' | 'topics' | 'moments';
type FeedItem = VideoInfo | TopicDiscoveryItem | MomentDiscoveryItem;
type FeedState = {
  items: FeedItem[];
  page: PageInfo | null;
  loading: boolean;
  error: string | null;
};

const emptyFeed = (): FeedState => ({ items: [], page: null, loading: false, error: null });

function uniqueItems(previous: FeedItem[], incoming: FeedItem[]) {
  const key = (item: FeedItem) => {
    if ('kind' in item && item.kind === 'topic') return `topic:${item.topic.slug}`;
    if ('kind' in item && item.kind === 'moment')
      return `moment:${item.video.id}:${item.start_ms}:${item.end_ms}`;
    return `video:${(item as VideoInfo).id}`;
  };
  const seen = new Set(previous.map(key));
  return [...previous, ...incoming.filter((item) => !seen.has(key(item)))];
}

export default function StreamsPage() {
  const [params, setParams] = useSearchParams();
  const requestedTab = params.get('tab');
  const tab: FeedTab =
    requestedTab === 'topics' || requestedTab === 'moments' ? requestedTab : 'latest';
  const q = params.get('q') ?? '';
  const sort =
    params.get('sort') === 'longest' || params.get('sort') === 'relevance'
      ? params.get('sort')!
      : 'latest';
  const [searchDraft, setSearchDraft] = useState(q);
  const [dateFromDraft, setDateFromDraft] = useState(params.get('date_from') ?? '');
  const [dateToDraft, setDateToDraft] = useState(params.get('date_to') ?? '');
  const [feeds, setFeeds] = useState<Record<FeedTab, FeedState>>({
    latest: emptyFeed(),
    topics: emptyFeed(),
    moments: emptyFeed(),
  });
  const [requestVersion, setRequestVersion] = useState(0);
  const [isMobile, setIsMobile] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia?.('(max-width: 639px)').matches
  );
  const sentinel = useRef<HTMLDivElement>(null);
  const tabScrollPositions = useRef<Record<FeedTab, number>>({ latest: 0, topics: 0, moments: 0 });
  const loadedVersion = useRef<Record<FeedTab, number>>({ latest: -1, topics: -1, moments: -1 });
  const active = feeds[tab];

  const dateFrom = params.get('date_from') ?? '';
  const dateTo = params.get('date_to') ?? '';

  useEffect(() => setSearchDraft(q), [q]);
  useEffect(() => setDateFromDraft(dateFrom), [dateFrom]);
  useEffect(() => setDateToDraft(dateTo), [dateTo]);
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 639px)');
    if (!query) return;
    const update = () => setIsMobile(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);
  useEffect(() => {
    const retired = ['min_duration', 'max_duration', 'transcript_source', 'source'];
    if (!retired.some((name) => params.has(name))) return;
    const next = new URLSearchParams(params);
    retired.forEach((name) => next.delete(name));
    setParams(next, { replace: true });
  }, [params, setParams]);
  useEffect(() => {
    window.requestAnimationFrame(() => window.scrollTo({ top: tabScrollPositions.current[tab] }));
  }, [tab]);
  const load = useCallback(
    async (target: FeedTab, append: boolean, signal?: AbortSignal) => {
      const current = feeds[target];
      if (current.loading || (append && !current.page?.has_next_page)) return;
      setFeeds((all) => ({
        ...all,
        [target]: { ...all[target], loading: true, error: null },
      }));
      try {
        const response =
          target === 'latest'
            ? await api.listStreamLibrary(
                {
                  limit: DEFAULT_LIMIT,
                  cursor: append ? (current.page?.next_cursor ?? undefined) : undefined,
                  sort: sort as 'latest' | 'relevance' | 'longest',
                  q: q || undefined,
                  date_field: 'uploaded_at',
                  date_from: dateFrom || undefined,
                  date_to: dateTo || undefined,
                },
                signal
              )
            : await api.listDiscovery(
                target,
                DEFAULT_LIMIT,
                append ? (current.page?.next_cursor ?? undefined) : undefined,
                signal
              );
        setFeeds((all) => ({
          ...all,
          [target]: {
            items: append ? uniqueItems(all[target].items, response.items) : response.items,
            page: response.page_info,
            loading: false,
            error: null,
          },
        }));
      } catch (error) {
        if (signal?.aborted) return;
        console.error('Failed to load discovery feed', error);
        setFeeds((all) => ({
          ...all,
          [target]: { ...all[target], loading: false, error: 'This feed could not refresh.' },
        }));
      }
    },
    [dateFrom, dateTo, feeds, q, sort]
  );

  useEffect(() => {
    const version = tab === 'latest' ? requestVersion : 0;
    if (loadedVersion.current[tab] === version && feeds[tab].page) return;
    loadedVersion.current[tab] = version;
    const controller = new AbortController();
    void load(tab, false, controller.signal);
    return () => controller.abort();
    // A new query/filter version deliberately resets only the active tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, requestVersion]);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !active.page?.has_next_page || active.loading) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void load(tab, true);
      },
      { rootMargin: '0px 0px 580px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [active.loading, active.page?.has_next_page, load, tab]);

  function setTab(next: FeedTab) {
    tabScrollPositions.current[tab] = window.scrollY;
    const nextParams = new URLSearchParams(params);
    if (next === 'latest') nextParams.delete('tab');
    else nextParams.set('tab', next);
    setParams(nextParams, { replace: true });
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const next = new URLSearchParams(params);
    const normalized = searchDraft.trim();
    if (normalized) next.set('q', normalized);
    else next.delete('q');
    if (next.get('sort') === 'relevance' && !normalized) next.delete('sort');
    setParams(next);
    setRequestVersion((value) => value + 1);
  }

  function updateFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value && value !== 'any') next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  function applyDates() {
    const next = new URLSearchParams(params);
    if (dateFromDraft) next.set('date_from', dateFromDraft);
    else next.delete('date_from');
    if (dateToDraft) next.set('date_to', dateToDraft);
    else next.delete('date_to');
    setParams(next, { replace: true });
    setRequestVersion((value) => value + 1);
  }

  function clearDates() {
    setDateFromDraft('');
    setDateToDraft('');
    const next = new URLSearchParams(params);
    next.delete('date_from');
    next.delete('date_to');
    setParams(next, { replace: true });
    setRequestVersion((value) => value + 1);
  }

  function dateRangeControls(prefix: string) {
    return (
      <fieldset className="feed-date-range">
        <legend className="sr-only">VOD date range</legend>
        <label htmlFor={`${prefix}-date-from`}>
          <span>From</span>
          <input
            id={`${prefix}-date-from`}
            type="date"
            className="form-control"
            value={dateFromDraft}
            onChange={(event) => setDateFromDraft(event.target.value)}
          />
        </label>
        <label htmlFor={`${prefix}-date-to`}>
          <span>To</span>
          <input
            id={`${prefix}-date-to`}
            type="date"
            className="form-control"
            value={dateToDraft}
            onChange={(event) => setDateToDraft(event.target.value)}
          />
        </label>
        <button type="button" className="btn-secondary" onClick={applyDates}>
          Apply dates
        </button>
        {(dateFrom || dateTo) && (
          <button type="button" className="btn-ghost" onClick={clearDates}>
            Clear dates
          </button>
        )}
      </fieldset>
    );
  }

  return (
    <div className="feed-shell">
      <header className="feed-header">
        <div className="feed-heading-row">
          <div>
            <p className="archive-eyebrow">Public archive</p>
            <h1 tabIndex={-1} className="text-2xl font-semibold tracking-[-0.04em] text-ink">
              Browse HasanAbi VODs
            </h1>
          </div>
          <p className="feed-count">
            {active.page?.total_count == null
              ? 'Citation-backed discovery'
              : tab === 'latest'
                ? `${active.page.total_count.toLocaleString()} ${active.page.total_count === 1 ? 'VOD' : 'VODs'}`
                : `${active.page.total_count.toLocaleString()} ${tab}`}
          </p>
        </div>

        <div className="feed-tabs" role="tablist" aria-label="Archive feeds">
          {(['latest', 'topics', 'moments'] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => setTab(value)}
            >
              {value[0].toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>

        {tab === 'latest' && (
          <form className="feed-tools" role="search" onSubmit={submitSearch}>
            <label className="sr-only" htmlFor="feed-search">
              Search VODs
            </label>
            <input
              id="feed-search"
              className="form-control"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="Search VODs"
            />
            <select
              aria-label="Sort VODs"
              className="form-control feed-sort"
              value={sort}
              onChange={(event) => {
                updateFilter('sort', event.target.value);
                setRequestVersion((value) => value + 1);
              }}
            >
              <option value="latest">Latest</option>
              <option value="relevance" disabled={!q}>
                Relevance
              </option>
              <option value="longest">Longest</option>
            </select>
            <button type="submit" className="btn-primary">
              Search
            </button>
            {isMobile ? (
              <details className="feed-date-mobile">
                <summary>Date range</summary>
                {dateRangeControls('mobile')}
              </details>
            ) : (
              <div className="feed-date-desktop">{dateRangeControls('desktop')}</div>
            )}
          </form>
        )}
      </header>

      {active.loading && active.items.length === 0 ? (
        <section aria-label="Loading feed" className="feed-grid">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="feed-card feed-skeleton animate-pulse" />
          ))}
        </section>
      ) : active.error && active.items.length === 0 ? (
        <div className="surface-card text-center" role="alert">
          <h2 className="section-title">VOD library unavailable</h2>
          <p className="mt-2 text-muted">The last request failed. Your filters are still here.</p>
          <button type="button" className="btn-primary mt-4" onClick={() => void load(tab, false)}>
            Retry
          </button>
        </div>
      ) : active.items.length === 0 ? (
        <div className="surface-card text-center">
          <h2 className="section-title">No VODs match these filters.</h2>
          <p className="mt-2 text-muted">Try broadening the date range or removing a filter.</p>
        </div>
      ) : (
        <section aria-label={`${tab} feed`} className="feed-grid">
          {active.items.map((item) => {
            if ('kind' in item && item.kind === 'topic') {
              return (
                <Link
                  className="discovery-card"
                  key={item.topic.slug}
                  to={`/topics/${encodeURIComponent(item.topic.slug)}`}
                >
                  <span className="archive-eyebrow">Topic</span>
                  <h2>{item.topic.label}</h2>
                  <p>
                    {item.topic.total_videos} VODs · {item.topic.total_moments} cited moments
                  </p>
                  <span className="action-link">Explore evidence →</span>
                </Link>
              );
            }
            if ('kind' in item && item.kind === 'moment') {
              return (
                <Link
                  className="discovery-card moment-card"
                  key={`${item.video.id}:${item.start_ms}`}
                  to={buildTimestampLink(item.video.id, item.start_ms)}
                >
                  <span className="timestamp-pill">{formatTimestamp(item.start_ms)}</span>
                  <blockquote>“{item.snippet}”</blockquote>
                  <p>
                    {item.video.title} {item.topic ? `· ${item.topic}` : ''}
                  </p>
                  <span className="action-link">Play cited moment →</span>
                </Link>
              );
            }
            return (
              <StreamCard
                key={(item as VideoInfo).id}
                video={item as VideoInfo}
                dateField="uploaded_at"
              />
            );
          })}
        </section>
      )}

      <div ref={sentinel} className="feed-load-more">
        {active.error && active.items.length > 0 && (
          <p role="alert">Couldn’t load the next page. Existing results are preserved.</p>
        )}
        {active.page?.has_next_page && (
          <button
            type="button"
            className="btn-secondary"
            disabled={active.loading}
            onClick={() => void load(tab, true)}
          >
            {active.loading ? 'Loading…' : active.error ? 'Retry' : 'Load more'}
          </button>
        )}
      </div>
    </div>
  );
}
