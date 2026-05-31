import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, apiAddFavorite, favorites, track, useAuth } from '../services';
import type {
  ArchiveSearchFilters,
  GroupedSearchResponse,
  SearchHit,
} from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp, sourceLabel } from '../features/archive/format';

type SearchMode = 'grouped' | 'flat' | null;

function readFilters(params: URLSearchParams): ArchiveSearchFilters & { q: string } {
  return {
    q: params.get('q') ?? '',
    source: (params.get('source') as ArchiveSearchFilters['source']) ?? undefined,
    category: params.get('category') ?? undefined,
    date_from: params.get('date_from') ?? undefined,
    date_to: params.get('date_to') ?? undefined,
    min_duration: params.get('min_duration') ? Number(params.get('min_duration')) : undefined,
    max_duration: params.get('max_duration') ? Number(params.get('max_duration')) : undefined,
    sort_by: params.get('sort_by') ?? undefined,
    video_id: params.get('video_id') ?? undefined,
    limit: params.get('limit') ? Number(params.get('limit')) : undefined,
    offset: params.get('offset') ? Number(params.get('offset')) : undefined,
  };
}

function serializeFilters(filters: ArchiveSearchFilters & { q: string }) {
  const next = new URLSearchParams();
  if (filters.q.trim()) next.set('q', filters.q.trim());
  if (filters.source) next.set('source', filters.source);
  if (filters.category) next.set('category', filters.category);
  if (filters.date_from) next.set('date_from', filters.date_from);
  if (filters.date_to) next.set('date_to', filters.date_to);
  if (filters.min_duration != null && !Number.isNaN(filters.min_duration)) next.set('min_duration', String(filters.min_duration));
  if (filters.max_duration != null && !Number.isNaN(filters.max_duration)) next.set('max_duration', String(filters.max_duration));
  if (filters.sort_by) next.set('sort_by', filters.sort_by);
  if (filters.video_id) next.set('video_id', filters.video_id);
  if (filters.limit != null && !Number.isNaN(filters.limit)) next.set('limit', String(filters.limit));
  if (filters.offset != null && !Number.isNaN(filters.offset)) next.set('offset', String(filters.offset));
  return next;
}

function buildCurrentFilters(
  q: string,
  source: ArchiveSearchFilters['source'],
  dateFrom: string,
  dateTo: string,
  category: string,
  minDuration: string,
  maxDuration: string,
  sortBy: string,
  existing: ArchiveSearchFilters & { video_id?: string; limit?: number; offset?: number }
) {
  return serializeFilters({
    q,
    source,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    category: category || undefined,
    min_duration: minDuration ? Number(minDuration) : undefined,
    max_duration: maxDuration ? Number(maxDuration) : undefined,
    sort_by: sortBy,
    video_id: existing.video_id,
    limit: existing.limit,
    offset: existing.offset,
  });
}

function groupHitsByVideo(hits: SearchHit[]): Array<[string, SearchHit[]]> {
  const groups = new Map<string, SearchHit[]>();
  hits.forEach((hit) => {
    const current = groups.get(hit.video_id) ?? [];
    groups.set(hit.video_id, [...current, hit]);
  });
  return Array.from(groups.entries());
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
}

function plainTextFromSnippet(snippet: string) {
  return snippet.replace(/<mark>/gi, '').replace(/<\/mark>/gi, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function buildQuoteText(videoId: string, moment: SearchHit, title: string) {
  const url = `${window.location.origin}${buildTimestampLink(videoId, moment.start_ms, moment.id)}`;
  return `“${plainTextFromSnippet(moment.snippet)}”\n\n— ${title}, ${formatTimestamp(moment.start_ms)}\n${url}`;
}

function buildPlayMatchesLink(videoId: string, moment: SearchHit, query: string) {
  const seconds = Math.floor(moment.start_ms / 1000);
  const params = new URLSearchParams({ t: String(seconds), q: query, play: 'matches' });
  return `/v/${videoId}?${params.toString()}#seg-${moment.id}`;
}

function SearchMomentsList({
  videoId,
  moments,
  fallbackTitle,
  defaultSource,
  query,
  savedKeys,
  onSaveMoment,
}: {
  videoId: string;
  moments: SearchHit[];
  fallbackTitle: string;
  defaultSource?: ArchiveSearchFilters['source'];
  query: string;
  savedKeys: Set<string>;
  onSaveMoment: (videoId: string, moment: SearchHit, title: string) => void;
}) {
  return (
    <ul className="space-y-3">
      {moments.map((moment) => (
        <li key={moment.id} className="group rounded-lg border border-border bg-surface-muted/80 p-4 transition-all hover:border-border-strong hover:bg-surface-muted/95">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <time className="timestamp-pill">
              {formatTimestamp(moment.start_ms)}–{formatTimestamp(moment.end_ms)}
            </time>
            <span className="source-pill">{sourceLabel(moment.source ?? defaultSource ?? 'best')}</span>
            {query && <span className="match-pill">match</span>}
          </div>
          <div className="archive-snippet" dangerouslySetInnerHTML={{ __html: moment.snippet }} />
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            <Link
              to={buildTimestampLink(videoId, moment.start_ms, moment.id)}
              className="action-link"
              onClick={() => track({ type: 'result_click', payload: { videoId, start_ms: moment.start_ms, id: moment.id } })}
            >
              Open at timestamp
            </Link>
            <button
              type="button"
              className="nav-link"
              onClick={() => copyText(`${window.location.origin}${buildTimestampLink(videoId, moment.start_ms, moment.id)}`)}
            >
              Copy timestamp
            </button>
            <button
              type="button"
              className="nav-link"
              onClick={() => copyText(buildQuoteText(videoId, moment, fallbackTitle))}
            >
              Copy quote
            </button>
            <button
              type="button"
              className="nav-link"
              disabled={savedKeys.has(`${videoId}:${moment.start_ms}:${moment.end_ms}`)}
              onClick={() => onSaveMoment(videoId, moment, fallbackTitle)}
            >
              {savedKeys.has(`${videoId}:${moment.start_ms}:${moment.end_ms}`) ? 'Saved moment' : 'Save moment'}
            </button>
            {query && (
              <Link to={buildPlayMatchesLink(videoId, moment, query)} className="action-link">
                Play from here
              </Link>
            )}
            <Link to={`/v/${videoId}`} className="action-link">
              Open episode
            </Link>
          </div>
          <p className="mt-3 text-xs text-subtle">{fallbackTitle}</p>
        </li>
      ))}
    </ul>
  );
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const [q, setQ] = useState(filters.q);
  const [source, setSource] = useState<ArchiveSearchFilters['source']>(filters.source);
  const [category, setCategory] = useState(filters.category ?? '');
  const [dateFrom, setDateFrom] = useState(filters.date_from ?? '');
  const [dateTo, setDateTo] = useState(filters.date_to ?? '');
  const [minDuration, setMinDuration] = useState(filters.min_duration?.toString() ?? '');
  const [maxDuration, setMaxDuration] = useState(filters.max_duration?.toString() ?? '');
  const [sortBy, setSortBy] = useState(filters.sort_by ?? 'relevance');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<SearchMode>(null);
  const [grouped, setGrouped] = useState<GroupedSearchResponse | null>(null);
  const [flatHits, setFlatHits] = useState<SearchHit[]>([]);
  const [quotaError, setQuotaError] = useState<{ message: string; used: number; limit: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const { user } = useAuth();
  const shouldFetch = Boolean(filters.q.trim());
  const canSubmitSearch = Boolean(q.trim());

  useEffect(() => {
    setQ(filters.q);
    setSource(filters.source);
    setCategory(filters.category ?? '');
    setDateFrom(filters.date_from ?? '');
    setDateTo(filters.date_to ?? '');
    setMinDuration(filters.min_duration?.toString() ?? '');
    setMaxDuration(filters.max_duration?.toString() ?? '');
    setSortBy(filters.sort_by ?? 'relevance');
  }, [filters.q, filters.source, filters.category, filters.date_from, filters.date_to, filters.min_duration, filters.max_duration, filters.sort_by]);

  useEffect(() => {
    const query = filters.q.trim();
    if (!shouldFetch) {
      setGrouped(null);
      setFlatHits([]);
      setMode(null);
      setLoading(false);
      setError(null);
      setQuotaError(null);
      return;
    }

    const activeFilters: ArchiveSearchFilters = {
      source: filters.source,
      category: filters.category,
      date_from: filters.date_from,
      date_to: filters.date_to,
      min_duration: filters.min_duration,
      max_duration: filters.max_duration,
      sort_by: filters.sort_by && filters.sort_by !== 'relevance' ? filters.sort_by : undefined,
      video_id: filters.video_id,
      limit: filters.limit,
      offset: filters.offset,
    };

    setLoading(true);
    setError(null);
    setQuotaError(null);
    track({ type: 'search', payload: { q: query, ...activeFilters } });

    api
      .searchGrouped(query, activeFilters)
      .then((response) => {
        setGrouped(response);
        setFlatHits([]);
        setMode('grouped');
      })
      .catch(async (groupedError: unknown) => {
        const err = groupedError as {
          response?: { status?: number; json: () => Promise<{ limit?: number; used?: number; message?: string }> };
        };
        if (err?.response?.status === 402 || err?.response?.status === 429) {
          const data = await err.response.json().catch(() => null);
          if (data?.limit != null) {
            setQuotaError({
              message: data.message || 'Upgrade required',
              used: data.used || 0,
              limit: data.limit || 0,
            });
            setLoading(false);
            return;
          }
        }

        return api
          .search(query, activeFilters)
          .then((response) => {
            setGrouped(null);
            setFlatHits(response.hits ?? []);
            setMode('flat');
          })
          .catch(async (flatError: unknown) => {
            const flat = flatError as {
              response?: { status?: number; json: () => Promise<{ limit?: number; used?: number; message?: string }> };
            };
            if (flat?.response?.status === 402 || flat?.response?.status === 429) {
              const data = await flat.response.json().catch(() => null);
              if (data?.limit != null) {
                setQuotaError({
                  message: data.message || 'Upgrade required',
                  used: data.used || 0,
                  limit: data.limit || 0,
                });
                return;
              }
            }
            console.error(flatError);
            setError('Search failed.');
          });
      })
      .finally(() => setLoading(false));
  }, [filters.category, filters.date_from, filters.date_to, filters.limit, filters.max_duration, filters.min_duration, filters.offset, filters.q, filters.sort_by, filters.source, filters.video_id, shouldFetch]);

  function submitFilters(event: React.FormEvent) {
    event.preventDefault();
    setParams(serializeFilters({ q, source, category: category || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, min_duration: minDuration ? Number(minDuration) : undefined, max_duration: maxDuration ? Number(maxDuration) : undefined, sort_by: sortBy, video_id: filters.video_id, limit: filters.limit, offset: filters.offset }));
  }

  function resetFilters() {
    setQ('');
    setSource(undefined);
    setCategory('');
    setDateFrom('');
    setDateTo('');
    setMinDuration('');
    setMaxDuration('');
    setSortBy('relevance');
    setParams(new URLSearchParams());
  }

  const groupedGroups = grouped?.groups ?? [];
  const totalMoments = grouped?.total_moments ?? flatHits.length;
  const totalVideos = grouped?.total_videos ?? groupHitsByVideo(flatHits).length;
  const fallbackGroups = useMemo(() => groupHitsByVideo(flatHits), [flatHits]);

  async function saveMoment(videoId: string, moment: SearchHit, title: string) {
    const key = `${videoId}:${moment.start_ms}:${moment.end_ms}`;
    const text = plainTextFromSnippet(moment.snippet);
    try {
      if (user) {
        await apiAddFavorite({ video_id: videoId, start_ms: moment.start_ms, end_ms: moment.end_ms, text });
      } else {
        favorites.toggle({ videoId, segIndex: moment.id, startMs: moment.start_ms, endMs: moment.end_ms, text });
      }
      setSavedKeys((current) => new Set([...current, key]));
      track({ type: 'favorite_add', payload: { videoId, start_ms: moment.start_ms, title } });
    } catch (err) {
      console.error('Failed to save moment', err);
      setError('Could not save this moment. Sign in again or try later.');
    }
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <section className="surface-card overflow-hidden space-y-6">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(183,255,60,0.10),transparent_22%),radial-gradient(circle_at_20%_15%,rgba(192,132,252,0.08),transparent_18%)]" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-4xl space-y-4">
            <div className="archive-eyebrow">Search deck</div>
            <div>
              <h1 className="page-title">Search the creator archive.</h1>
              <p className="mt-3 max-w-2xl text-muted">
                Find where a topic was mentioned, when it was discussed, and which episode it came from — with timestamped results and dossier-style metadata.
              </p>
            </div>
          </div>

          {filters.q && (
            <div className="flex flex-wrap gap-3">
              <Link to={`/topics/${encodeURIComponent(filters.q)}`} className="btn-secondary">
                Open topic page
              </Link>
              <Link to={`/saved?${buildCurrentFilters(q, source, dateFrom, dateTo, category, minDuration, maxDuration, sortBy, filters).toString()}`} className="btn-secondary">
                Save this search
              </Link>
            </div>
          )}
        </div>

        <form onSubmit={submitFilters} className="space-y-3">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_12rem_11rem_auto]">
            <div>
              <label className="sr-only" htmlFor="search-query">
                Search query
              </label>
              <input
                id="search-query"
                type="search"
                value={q}
                onChange={(event) => setQ(event.target.value)}
                placeholder="Search the archive..."
                className="form-control min-h-[48px] px-4 text-base tracking-[-0.02em]"
              />
            </div>

            <div>
              <label className="sr-only" htmlFor="search-source">
                Source
              </label>
              <select id="search-source" className="form-control min-h-[48px]" value={source ?? ''} onChange={(event) => setSource((event.target.value || undefined) as ArchiveSearchFilters['source'])}>
                <option value="">Best available</option>
                <option value="native">Whisper transcript</option>
                <option value="youtube">YouTube captions</option>
              </select>
            </div>

            <div>
              <label className="sr-only" htmlFor="search-sort">
                Sort
              </label>
              <select id="search-sort" className="form-control min-h-[48px]" value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
                <option value="relevance">Best match</option>
                <option value="date_desc">Most recent</option>
                <option value="date_asc">Oldest</option>
                <option value="duration_desc">Longest</option>
                <option value="duration_asc">Shortest</option>
              </select>
            </div>

            <div className="flex gap-2 lg:justify-end">
              <button type="submit" className="btn min-h-[48px] px-5" disabled={!canSubmitSearch || loading}>
                Search
              </button>
              <button type="button" className="btn-secondary min-h-[48px] px-4" onClick={resetFilters}>
                Reset
              </button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            <input id="search-category" type="text" className="form-control" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Video type" aria-label="Video type" />
            <input id="search-date-from" type="date" className="form-control" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label="From date" />
            <input id="search-date-to" type="date" className="form-control" value={dateTo} onChange={(event) => setDateTo(event.target.value)} aria-label="To date" />
            <input id="search-min-duration" type="number" min="0" step="1" inputMode="numeric" placeholder="Min seconds" className="form-control" value={minDuration} onChange={(event) => setMinDuration(event.target.value)} aria-label="Minimum duration" />
            <input id="search-max-duration" type="number" min="0" step="1" inputMode="numeric" placeholder="Max seconds" className="form-control" value={maxDuration} onChange={(event) => setMaxDuration(event.target.value)} aria-label="Maximum duration" />
          </div>

          <div className="flex flex-wrap gap-1.5 text-sm text-muted">
            <span className="source-pill">grouped by episode</span>
            <span className="source-pill">timestamp pills</span>
            <span className="match-pill">highlighted snippets</span>
          </div>
        </form>
      </section>

      {filters.q && (
        <section className="archive-panel flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="archive-eyebrow">Topic map</div>
            <p className="mt-2 text-muted">
              {loading ? 'Updating counts…' : `${formatNumber(totalMoments)} moments across ${formatNumber(totalVideos)} episodes`}
            </p>
          </div>
          <Link to={`/topics/${encodeURIComponent(filters.q)}`} className="action-link">
            Open mention map
          </Link>
        </section>
      )}

      {quotaError && (
        <div className="alert-warning" role="alert">
          <div className="font-medium">Daily search limit reached</div>
          <div className="mt-1 text-sm">
            You used {quotaError.used}/{quotaError.limit} searches today. {quotaError.message}
          </div>
          <Link to="/pricing" className="action-link mt-2 inline-block">
            See pricing
          </Link>
        </div>
      )}

      {error && <div className="alert-warning" role="alert">{error}</div>}

      {loading && filters.q && (
        <div className="archive-panel p-8 text-center text-muted" role="status" aria-live="polite">
          Searching the archive…
        </div>
      )}

      {!shouldFetch && (
        <div className="surface-card text-center text-muted">
          Search the archive to reveal grouped episodes and timestamped moments.
        </div>
      )}

      {shouldFetch && !loading && !quotaError && mode === 'grouped' && groupedGroups.length > 0 && (
        <div className="space-y-4">
          {groupedGroups.map((group) => {
            const title = group.video.title || `Episode ${group.video.id.slice(0, 8)}…`;
            return (
              <article key={group.video.id} className="surface-card space-y-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="archive-eyebrow">Episode dossier</div>
                    <Link to={`/v/${group.video.id}`} className="block text-2xl font-semibold tracking-[-0.03em] text-ink hover:text-accent">
                      {title}
                    </Link>
                    <div className="flex flex-wrap gap-2 text-sm text-muted">
                      <span className="source-pill">{group.video.channel_name || 'Unknown channel'}</span>
                      <span className="timestamp-pill">{formatDate(group.video.uploaded_at ?? null)}</span>
                      <span className="source-pill">{formatDuration(group.video.duration_seconds)}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="match-pill">
                      {group.moments.length} {group.moments.length === 1 ? 'moment' : 'moments'}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3 text-sm">
                  {group.moments[0] && filters.q && (
                    <Link to={buildPlayMatchesLink(group.video.id, group.moments[0] as SearchHit, filters.q)} className="btn-secondary">
                      Play all matches
                    </Link>
                  )}
                </div>
                <SearchMomentsList videoId={group.video.id} moments={group.moments as SearchHit[]} fallbackTitle={title} defaultSource={source} query={filters.q} savedKeys={savedKeys} onSaveMoment={saveMoment} />
              </article>
            );
          })}
        </div>
      )}

      {shouldFetch && !loading && !quotaError && mode === 'flat' && fallbackGroups.length > 0 && (
        <div className="space-y-4">
          {fallbackGroups.map(([videoId, hits]) => {
            const title = `Episode ${videoId.slice(0, 8)}…`;
            return (
              <article key={videoId} className="surface-card space-y-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="archive-eyebrow">Episode dossier</div>
                    <Link to={`/v/${videoId}`} className="block text-2xl font-semibold tracking-[-0.03em] text-ink hover:text-accent">
                      {title}
                    </Link>
                    <p className="text-sm text-muted">Flat search fallback</p>
                  </div>
                  <div className="match-pill">{hits.length} matches</div>
                </div>
                <SearchMomentsList videoId={videoId} moments={hits} fallbackTitle={title} defaultSource={source} query={filters.q} savedKeys={savedKeys} onSaveMoment={saveMoment} />
              </article>
            );
          })}
        </div>
      )}

      {shouldFetch && !loading && !quotaError && mode === 'grouped' && groupedGroups.length === 0 && (
        <div className="archive-panel text-center text-muted">
          No matches found for “{filters.q}”. Try fewer filters or a broader date range.
        </div>
      )}

      {shouldFetch && !loading && !quotaError && mode === 'flat' && fallbackGroups.length === 0 && (
        <div className="archive-panel text-center text-muted">
          No matches found for “{filters.q}”.
        </div>
      )}
    </div>
  );
}
