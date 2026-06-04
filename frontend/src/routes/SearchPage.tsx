import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, apiAddFavorite, favorites, track, useAuth } from '../services';
import type {
  ArchiveSearchFilters,
  GroupedSearchResponse,
  SearchHit,
} from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber } from '../features/archive/format';
import { buildCurrentFilters, readFilters, serializeFilters } from '../features/search/filters';
import { buildPlayMatchesLink, buildQuoteText, plainTextFromSnippet } from '../features/search/moments';
import { groupHitsByVideo } from '../features/searchTranscript/matches';

import { SearchFiltersPanel, SearchMomentsList } from '../components/archive';

type SearchMode = 'grouped' | 'flat' | null;

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const [q, setQ] = useState(filters.q);
  const [dateFrom, setDateFrom] = useState(filters.date_from ?? '');
  const [dateTo, setDateTo] = useState(filters.date_to ?? '');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<SearchMode>(null);
  const [grouped, setGrouped] = useState<GroupedSearchResponse | null>(null);
  const [flatHits, setFlatHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const { user } = useAuth();
  const shouldFetch = Boolean(filters.q.trim());
  const canSubmitSearch = Boolean(q.trim());

  useEffect(() => {
    setQ(filters.q);
    setDateFrom(filters.date_from ?? '');
    setDateTo(filters.date_to ?? '');
  }, [filters.q, filters.date_from, filters.date_to]);

  useEffect(() => {
    const query = filters.q.trim();
    if (!shouldFetch) {
      setGrouped(null);
      setFlatHits([]);
      setMode(null);
      setLoading(false);
      setError(null);
      return;
    }

    const activeFilters: ArchiveSearchFilters = {
      source: undefined,
      category: undefined,
      date_from: filters.date_from,
      date_to: filters.date_to,
      min_duration: undefined,
      max_duration: undefined,
      sort_by: undefined,
      video_id: filters.video_id,
      limit: filters.limit,
      offset: filters.offset,
    };

    setLoading(true);
    setError(null);
    track({ type: 'search', payload: { q: query, ...activeFilters } });

    api
      .searchGrouped(query, activeFilters)
      .then((response) => {
        setGrouped(response);
        setFlatHits([]);
        setMode('grouped');
      })
      .catch(() => {
        return api
          .search(query, activeFilters)
          .then((response) => {
            setGrouped(null);
            setFlatHits(response.hits ?? []);
            setMode('flat');
          })
          .catch((flatError: unknown) => {
            console.error(flatError);
            setError('Search failed.');
          });
      })
      .finally(() => setLoading(false));
  }, [filters.date_from, filters.date_to, filters.limit, filters.offset, filters.q, filters.video_id, shouldFetch]);

  function submitFilters(event: FormEvent) {
    event.preventDefault();
    setParams(serializeFilters({ q, date_from: dateFrom || undefined, date_to: dateTo || undefined, video_id: filters.video_id, limit: filters.limit, offset: filters.offset }));
  }

  function resetFilters() {
    setQ('');
    setDateFrom('');
    setDateTo('');
    setParams(new URLSearchParams());
  }

  const groupedGroups = grouped?.groups ?? [];
  const totalMoments = grouped?.total_moments ?? flatHits.length;
  const fallbackGroups = useMemo(() => groupHitsByVideo(flatHits), [flatHits]);
  const totalVideos = grouped?.total_videos ?? fallbackGroups.length;

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

  function copyMomentTimestamp(videoId: string, moment: SearchHit) {
    copyText(`${window.location.origin}${buildTimestampLink(videoId, moment.start_ms, moment.id)}`);
  }

  function copyMomentQuote(videoId: string, moment: SearchHit, title: string) {
    copyText(buildQuoteText(videoId, moment, title));
  }

  return (
    <div className="space-y-6 lg:space-y-8">
      <section className="surface-card space-y-6 overflow-hidden">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-4xl space-y-4">
            <div className="archive-eyebrow">Search deck</div>
            <div>
              <h1 className="page-title">Search the HasanAbi archive.</h1>
              <p className="mt-3 max-w-2xl text-muted">
                Find when Hasan covered a topic, what was said, and which VOD it came from — with timestamped results and dossier-style metadata.
              </p>
            </div>
          </div>

          {filters.q && (
            <div className="flex flex-wrap gap-3">
              <Link to={`/topics/${encodeURIComponent(filters.q)}`} className="btn-secondary">
                Open topic page
              </Link>
              <Link to={`/saved?${buildCurrentFilters(q, undefined, dateFrom, dateTo, '', '', '', 'relevance', filters).toString()}`} className="btn-secondary">
                Save this search
              </Link>
            </div>
          )}
        </div>

        <SearchFiltersPanel
          q={q}
          dateFrom={dateFrom}
          dateTo={dateTo}
          loading={loading}
          canSubmitSearch={canSubmitSearch}
          onQChange={setQ}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
          onSubmit={submitFilters}
          onReset={resetFilters}
        />
      </section>

      {filters.q && (
        <section className="archive-panel flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="archive-eyebrow">Topic map</div>
            <p className="mt-2 text-muted">
              {loading ? 'Updating counts…' : `${formatNumber(totalMoments)} moments across ${formatNumber(totalVideos)} VODs`}
            </p>
          </div>
          <Link to={`/topics/${encodeURIComponent(filters.q)}`} className="action-link">
            Open mention map
          </Link>
        </section>
      )}

      {error && <div className="alert-warning" role="alert">{error}</div>}

      {loading && filters.q && (
        <div className="archive-panel p-8 text-center text-muted" role="status" aria-live="polite">
          Searching the archive…
        </div>
      )}

      {!shouldFetch && (
        <div className="surface-card text-center text-muted">
          Search the HasanAbi archive to reveal grouped VODs and timestamped moments.
        </div>
      )}

      {shouldFetch && !loading && mode === 'grouped' && groupedGroups.length > 0 && (
        <div className="space-y-4">
          {groupedGroups.map((group) => {
            const title = group.video.title || `VOD ${group.video.id.slice(0, 8)}…`;
            return (
              <article key={group.video.id} className="surface-card space-y-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="archive-eyebrow">VOD dossier</div>
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
                <SearchMomentsList
                  videoId={group.video.id}
                  moments={group.moments as SearchHit[]}
                  fallbackTitle={title}
                  query={filters.q}
                  savedKeys={savedKeys}
                  onSaveMoment={saveMoment}
                  onCopyTimestamp={copyMomentTimestamp}
                  onCopyQuote={copyMomentQuote}
                  onTrackResultClick={(resultVideoId, moment) => track({ type: 'result_click', payload: { videoId: resultVideoId, start_ms: moment.start_ms, id: moment.id } })}
                />
              </article>
            );
          })}
        </div>
      )}

      {shouldFetch && !loading && mode === 'flat' && fallbackGroups.length > 0 && (
        <div className="space-y-4">
          {fallbackGroups.map(([videoId, hits]) => {
            const title = `VOD ${videoId.slice(0, 8)}…`;
            return (
              <article key={videoId} className="surface-card space-y-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="archive-eyebrow">VOD dossier</div>
                    <Link to={`/v/${videoId}`} className="block text-2xl font-semibold tracking-[-0.03em] text-ink hover:text-accent">
                      {title}
                    </Link>
                    <p className="text-sm text-muted">Flat search fallback</p>
                  </div>
                  <div className="match-pill">{hits.length} matches</div>
                </div>
                <SearchMomentsList
                  videoId={videoId}
                  moments={hits}
                  fallbackTitle={title}
                  query={filters.q}
                  savedKeys={savedKeys}
                  onSaveMoment={saveMoment}
                  onCopyTimestamp={copyMomentTimestamp}
                  onCopyQuote={copyMomentQuote}
                  onTrackResultClick={(resultVideoId, moment) => track({ type: 'result_click', payload: { videoId: resultVideoId, start_ms: moment.start_ms, id: moment.id } })}
                />
              </article>
            );
          })}
        </div>
      )}

      {shouldFetch && !loading && mode === 'grouped' && groupedGroups.length === 0 && (
        <div className="archive-panel text-center text-muted">
          No matches found for “{filters.q}”. Try fewer filters or a broader date range.
        </div>
      )}

      {shouldFetch && !loading && mode === 'flat' && fallbackGroups.length === 0 && (
        <div className="archive-panel text-center text-muted">
          No matches found for “{filters.q}”.
        </div>
      )}
    </div>
  );
}
