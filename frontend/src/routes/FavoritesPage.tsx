import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  apiCreateSavedSearch,
  apiDeleteFavorite,
  apiDeleteSavedSearch,
  apiListFavorites,
  apiListSavedSearches,
  favorites,
  useAuth,
} from '../services';
import type { SavedSearch, SavedSearchFilters } from '../types/api';
import { formatDate, sourceLabel } from '../features/archive/format';

function readSavedSearchFilters(params: URLSearchParams): { query: string; filters: SavedSearchFilters } {
  return {
    query: params.get('query') ?? params.get('q') ?? '',
    filters: {
      source: (params.get('source') as SavedSearchFilters['source']) ?? undefined,
      category: params.get('category') ?? undefined,
      date_from: params.get('date_from') ?? undefined,
      date_to: params.get('date_to') ?? undefined,
      min_duration: params.get('min_duration') ? Number(params.get('min_duration')) : undefined,
      max_duration: params.get('max_duration') ? Number(params.get('max_duration')) : undefined,
      sort_by: params.get('sort_by') ?? undefined,
      video_id: params.get('video_id') ?? undefined,
      limit: params.get('limit') ? Number(params.get('limit')) : undefined,
      offset: params.get('offset') ? Number(params.get('offset')) : undefined,
    },
  };
}

function savedSearchUrl(saved: SavedSearch) {
  const params = new URLSearchParams({ q: saved.query });
  Object.entries(saved.filters ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  return `/search?${params.toString()}`;
}

export default function FavoritesPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [items, setItems] = useState(favorites.list());
  const [remote, setRemote] = useState<Array<{ id: string; video_id: string; start_ms: number; end_ms: number; text?: string }> | null>(null);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[] | null>(null);
  const [query, setQuery] = useState(readSavedSearchFilters(params).query);
  const [filters, setFilters] = useState<SavedSearchFilters>(readSavedSearchFilters(params).filters);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const next = readSavedSearchFilters(params);
    setQuery(next.query);
    setFilters(next.filters);
  }, [params]);

  useEffect(() => {
    if (user) {
      apiListFavorites()
        .then((r) => setRemote(r.items))
        .catch(() => setRemote(null));
      apiListSavedSearches()
        .then((r) => setSavedSearches(r.items))
        .catch(() => setSavedSearches(null));
    } else {
      setRemote(null);
      setSavedSearches(null);
    }
  }, [user]);

  useEffect(() => {
    if (!user) {
      const id = setInterval(() => setItems(favorites.list()), 1000);
      return () => clearInterval(id);
    }
  }, [user]);

  async function saveSearch() {
    const trimmed = query.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await apiCreateSavedSearch({ query: trimmed, filters });
      const next = await apiListSavedSearches().catch(() => null);
      if (next) setSavedSearches(next.items);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-3">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">Saved</div>
        <h1 className="page-title">Saved moments and searches</h1>
        <p className="max-w-2xl text-muted">
          Keep interesting moments handy and preserve the searches that matter.
        </p>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
        <div className="surface-card space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="section-title">Saved moments</h2>
            <Link to="/search" className="action-link text-sm">
              Search archive
            </Link>
          </div>

          {user && remote !== null ? (
            remote.length === 0 ? (
              <p className="text-muted">No saved moments yet.</p>
            ) : (
              <ul className="space-y-3">
                {remote.map((f) => (
                  <li key={f.id} className="surface-card-compact flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-2 line-clamp-2">{f.text}</div>
                      <Link className="action-link" to={`/v/${f.video_id}?t=${Math.floor(f.start_ms / 1000)}`}>
                        Open moment
                      </Link>
                    </div>
                    <button
                      className="nav-link text-danger"
                      onClick={async () => {
                        await apiDeleteFavorite(f.id).catch(() => {});
                        const next = await apiListFavorites().catch(() => null);
                        if (next) setRemote(next.items);
                      }}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )
          ) : (
            <>
              {items.length === 0 && <p className="text-muted">No saved moments yet.</p>}
              <ul className="space-y-3">
                {items.map((f, i) => (
                  <li key={i} className="surface-card-compact flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs text-subtle">Segment {f.segIndex}</div>
                      <div className="mb-2 line-clamp-2">{f.text}</div>
                      <Link className="action-link" to={`/v/${f.videoId}?t=${Math.floor(f.startMs / 1000)}#seg-${f.segIndex}`}>
                        Open moment
                      </Link>
                    </div>
                    <button
                      className="nav-link text-danger"
                      onClick={() => {
                        favorites.toggle(f);
                        setItems(favorites.list());
                      }}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <aside className="space-y-6">
          <div className="surface-card space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="section-title">Saved searches</h2>
              {user ? <span className="badge-success">Synced</span> : <span className="badge-warning">Local only</span>}
            </div>

            {user ? (
              <>
                <div className="space-y-3 rounded-2xl border border-border bg-surface-muted p-4">
                  <div className="text-xs uppercase tracking-[0.24em] text-subtle">Save current search</div>
                  <label className="block text-sm text-muted">
                    Query
                    <input className="form-control mt-1" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Enter a search term" />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm text-muted">
                      Source
                      <select
                        className="form-control mt-1"
                        value={filters.source ?? ''}
                        onChange={(event) => setFilters((current) => ({ ...current, source: (event.target.value || undefined) as SavedSearchFilters['source'] }))}
                      >
                        <option value="">Best available</option>
                        <option value="native">Whisper transcript</option>
                        <option value="youtube">YouTube captions</option>
                      </select>
                    </label>
                    <label className="block text-sm text-muted">
                      Video type
                      <input className="form-control mt-1" type="text" value={filters.category ?? ''} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value || undefined }))} placeholder="Podcast, interview, short…" />
                    </label>
                    <label className="block text-sm text-muted">
                      Sort
                      <select
                        className="form-control mt-1"
                        value={filters.sort_by ?? 'relevance'}
                        onChange={(event) => setFilters((current) => ({ ...current, sort_by: event.target.value || undefined }))}
                      >
                        <option value="relevance">Best match</option>
                        <option value="date_desc">Most recent</option>
                        <option value="date_asc">Oldest</option>
                      </select>
                    </label>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm text-muted">
                      From date
                      <input className="form-control mt-1" type="date" value={filters.date_from ?? ''} onChange={(event) => setFilters((current) => ({ ...current, date_from: event.target.value || undefined }))} />
                    </label>
                    <label className="block text-sm text-muted">
                      To date
                      <input className="form-control mt-1" type="date" value={filters.date_to ?? ''} onChange={(event) => setFilters((current) => ({ ...current, date_to: event.target.value || undefined }))} />
                    </label>
                    <label className="block text-sm text-muted">
                      Min duration
                      <input className="form-control mt-1" type="number" min="0" value={filters.min_duration ?? ''} onChange={(event) => setFilters((current) => ({ ...current, min_duration: event.target.value ? Number(event.target.value) : undefined }))} />
                    </label>
                    <label className="block text-sm text-muted">
                      Max duration
                      <input className="form-control mt-1" type="number" min="0" value={filters.max_duration ?? ''} onChange={(event) => setFilters((current) => ({ ...current, max_duration: event.target.value ? Number(event.target.value) : undefined }))} />
                    </label>
                  </div>
                  <button type="button" className="btn w-full" onClick={saveSearch} disabled={saving || !query.trim()}>
                    {saving ? 'Saving…' : 'Save search'}
                  </button>
                </div>

                {savedSearches && savedSearches.length > 0 ? (
                  <div className="space-y-3">
                    {savedSearches.map((saved) => (
                      <div key={saved.id} className="rounded-2xl border border-border bg-surface-muted p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-semibold text-ink">{saved.query}</div>
                            <div className="mt-1 text-sm text-muted">Saved {formatDate(saved.created_at ?? null)}</div>
                            <div className="mt-2 flex flex-wrap gap-2 text-xs text-subtle">
                              {saved.filters.source && <span>{sourceLabel(saved.filters.source)}</span>}
                              {saved.filters.category && <span>Type {saved.filters.category}</span>}
                              {saved.filters.date_from && <span>From {saved.filters.date_from}</span>}
                              {saved.filters.date_to && <span>To {saved.filters.date_to}</span>}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="nav-link text-danger"
                            onClick={async () => {
                              await apiDeleteSavedSearch(saved.id).catch(() => {});
                              const next = await apiListSavedSearches().catch(() => null);
                              if (next) setSavedSearches(next.items);
                            }}
                          >
                            Delete
                          </button>
                        </div>
                        <Link className="action-link mt-3 inline-block" to={savedSearchUrl(saved)}>
                          Reopen search
                        </Link>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted">No saved searches yet.</p>
                )}
              </>
            ) : (
              <div className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted">
                Sign in to sync saved searches across devices. Local moments still work in this browser.
              </div>
            )}
          </div>
        </aside>
      </section>
    </div>
  );
}
