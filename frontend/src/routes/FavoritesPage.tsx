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
import { SavedMomentItem, SavedSearchForm, SavedSearchItem } from '../components/favorites';

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
                  <SavedMomentItem
                    key={f.id}
                    mode="remote"
                    item={f}
                    onRemove={async () => {
                      await apiDeleteFavorite(f.id).catch(() => {});
                      const next = await apiListFavorites().catch(() => null);
                      if (next) setRemote(next.items);
                    }}
                  />
                ))}
              </ul>
            )
          ) : (
            <>
              {items.length === 0 && <p className="text-muted">No saved moments yet.</p>}
              <ul className="space-y-3">
                {items.map((f, i) => (
                  <SavedMomentItem
                    key={i}
                    mode="local"
                    item={f}
                    onRemove={() => {
                      favorites.toggle(f);
                      setItems(favorites.list());
                    }}
                  />
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
                <SavedSearchForm
                  query={query}
                  filters={filters}
                  saving={saving}
                  onQueryChange={setQuery}
                  onFiltersChange={setFilters}
                  onSave={saveSearch}
                />

                {savedSearches && savedSearches.length > 0 ? (
                  <div className="space-y-3">
                    {savedSearches.map((saved) => (
                      <SavedSearchItem
                        key={saved.id}
                        saved={saved}
                        onDelete={async () => {
                          await apiDeleteSavedSearch(saved.id).catch(() => {});
                          const next = await apiListSavedSearches().catch(() => null);
                          if (next) setSavedSearches(next.items);
                        }}
                      />
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
